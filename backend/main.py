import os
import uuid
import asyncio
import tempfile
import shutil
import logging
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google import genai

from backend.models import (
    VideoIngestRequest, VideoIngestResponse, JobResponse, SubJobInfo,
    VideoListItem, VideoDetailResponse, ChunkItem,
    SearchRequest, SearchResponse, SearchResultItem, StatusResponse
)
from backend.pipeline import (
    extract_metadata_and_expand_urls, download_audio_and_chunk,
    transcribe_with_backoff, merge_segments_to_chunks, embed_texts,
    embed_query, get_gemini_client, DEFAULT_EMBEDDING_MODEL
)
from backend.db import init_database, BaseDatabase, SupabaseDatabase
from dotenv import load_dotenv

load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backend.main")

app = FastAPI(title="YouTube Study RAG Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database with strict loud startup validation
db: BaseDatabase = init_database()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = get_gemini_client()


def format_seconds(seconds: float) -> str:
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def extract_youtube_id(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Quickly extracts video ID and playlist ID from URL without network requests."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if "youtube.com" in hostname:
            qs = parse_qs(parsed.query)
            vid = qs.get("v", [None])[0]
            plist = qs.get("list", [None])[0]
            return (vid, plist)
        elif "youtu.be" in hostname:
            vid = parsed.path.lstrip("/").split("?")[0]
            qs = parse_qs(parsed.query)
            plist = qs.get("list", [None])[0]
            return (vid, plist)
    except Exception:
        pass
    return (None, None)


async def process_video_pipeline(job_id: str, entry: dict):
    """
    Executes the full end-to-end ingestion pipeline with cooperative cancellation:
    1. Idempotency check: Reuses already-ready video if exists with 100% progress.
    2. Audio downloading & long-video chunking.
    3. Groq Whisper transcription with timestamp offset compensation.
    4. Semantic chunking (30-60s sentence boundaries).
    5. Gemini gemini-embedding-001 vector embeddings (768-dim, normalized).
    6. Supabase / database persistence.
    """
    job = await asyncio.to_thread(db.get_job, job_id)
    if not job:
        return

    def is_cancelled_sync() -> bool:
        fresh = db.get_job(job_id)
        return fresh is not None and fresh.get("status") == "cancelled"

    async def is_cancelled_async() -> bool:
        fresh = await asyncio.to_thread(db.get_job, job_id)
        return fresh is not None and fresh.get("status") == "cancelled"

    if await is_cancelled_async():
        logger.info(f"Job {job_id} was cancelled before starting. Halting.")
        return

    youtube_id = entry.get("youtube_id")
    title = entry.get("title", "Lecture Video")
    thumbnail_url = entry.get("thumbnail")
    duration_seconds = int(entry.get("duration") or 0)
    channel_name = entry.get("channel_name")
    description = entry.get("description")

    def set_job_stage_sync(stage_name: str):
        if not is_cancelled_sync():
            fresh_job = db.get_job(job_id)
            sub_jobs = list(fresh_job.get("sub_jobs") or []) if fresh_job else []
            for sj in sub_jobs:
                if sj.get("video_id") in [youtube_id, entry.get("youtube_id")]:
                    sj["status"] = stage_name
            db.update_job(job_id, {
                "status": "processing",
                "stage": stage_name,
                "sub_jobs": sub_jobs if sub_jobs else None,
            })
            if "video_id" in locals() and stage_name in ["downloading", "transcribing", "indexing", "waiting_on_rate_limit"]:
                db.update_video(video_id, {"status": stage_name})

    async def set_job_stage_async(stage_name: str):
        if not await is_cancelled_async():
            fresh_job = await asyncio.to_thread(db.get_job, job_id)
            sub_jobs = list(fresh_job.get("sub_jobs") or []) if fresh_job else []
            for sj in sub_jobs:
                if sj.get("video_id") in [youtube_id, entry.get("youtube_id")]:
                    sj["status"] = stage_name
            await asyncio.to_thread(db.update_job, job_id, {
                "status": "processing",
                "stage": stage_name,
                "sub_jobs": sub_jobs if sub_jobs else None,
            })
            if "video_id" in locals() and stage_name in ["downloading", "transcribing", "indexing", "waiting_on_rate_limit"]:
                await asyncio.to_thread(db.update_video, video_id, {"status": stage_name})

    try:
        # 1. Idempotency check: If video already indexed and ready, short-circuit with 100% progress
        if youtube_id:
            existing = await asyncio.to_thread(db.get_video_by_youtube_id, youtube_id)
            if existing and existing.get("status") == "ready":
                logger.info(f"Video {youtube_id} already indexed ({existing['id']}). Skipping ingestion.")
                fresh_job = (await asyncio.to_thread(db.get_job, job_id)) or job
                current_vids = list(fresh_job.get("video_ids") or [])
                if existing["id"] not in current_vids:
                    current_vids.append(existing["id"])
                
                total_target = fresh_job.get("progress_total") or 1
                new_progress = (fresh_job.get("progress_current") or 0) + 1
                is_done = new_progress >= total_target

                sub_jobs = list(fresh_job.get("sub_jobs") or [])
                for sj in sub_jobs:
                    if sj.get("video_id") in [youtube_id, entry.get("youtube_id")]:
                        sj["status"] = "done"
                        sj["progress"] = 100
                
                await asyncio.to_thread(db.update_job, job_id, {
                    "video_ids": current_vids,
                    "progress_current": total_target if (fresh_job.get("type") == "video" or is_done) else new_progress,
                    "progress_total": total_target,
                    "status": "done" if is_done else "processing",
                    "stage": None if is_done else "indexing",
                    "sub_jobs": sub_jobs if sub_jobs else None,
                    "error_message": None,
                })
                return

        # Create or update video record as downloading (reusing existing UUID if previously failed)
        existing_record = (await asyncio.to_thread(db.get_video_by_youtube_id, youtube_id)) if youtube_id else None
        video_id = existing_record["id"] if existing_record else str(uuid.uuid4())
        await asyncio.to_thread(db.create_video, {
            "id": video_id,
            "youtube_video_id": youtube_id or f"vid_{video_id[:8]}",
            "title": title,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": duration_seconds,
            "status": "downloading",
            "error_message": None,
            "added_at": existing_record.get("added_at") if existing_record else datetime.now(timezone.utc).isoformat(),
            "channel_name": channel_name,
            "description": description,
            "tags": existing_record.get("tags") if existing_record else ["Lecture", "Transcript"],
        })

        fresh_job = await asyncio.to_thread(db.get_job, job_id)
        if fresh_job:
            current_vids = list(fresh_job.get("video_ids") or [])
            if video_id not in current_vids:
                current_vids.append(video_id)
                await asyncio.to_thread(db.update_job, job_id, {"video_ids": current_vids})

        await set_job_stage_async("downloading")

        temp_dir = tempfile.mkdtemp(prefix=f"study_carrel_{job_id[:8]}_")

        try:
            # Check cancellation before download
            if await is_cancelled_async():
                logger.info(f"Job {job_id} cancelled before download. Halting.")
                await asyncio.to_thread(db.update_video, video_id, {"status": "cancelled", "error_message": "Ingestion cancelled by user"})
                return

            # 2. Download audio and split if long (offloaded to thread pool to not block asyncio event loop)
            audio_chunks = await asyncio.to_thread(download_audio_and_chunk, entry.get("url", ""), temp_dir)

            # Check cancellation after download
            if await is_cancelled_async():
                logger.info(f"Job {job_id} cancelled after download. Halting.")
                await asyncio.to_thread(db.update_video, video_id, {"status": "cancelled", "error_message": "Ingestion cancelled by user"})
                return

            # 3. Transcribe each audio chunk with Groq Whisper & offset timestamps
            await asyncio.to_thread(db.update_video, video_id, {"status": "transcribing"})
            await set_job_stage_async("transcribing")

            all_segments = []
            for chunk_path, offset_sec in audio_chunks:
                if await is_cancelled_async():
                    logger.info(f"Job {job_id} cancelled during transcription. Halting.")
                    await asyncio.to_thread(db.update_video, video_id, {"status": "cancelled", "error_message": "Ingestion cancelled by user"})
                    return

                segments = await transcribe_with_backoff(chunk_path, status_callback=set_job_stage_sync, cancel_check=is_cancelled_sync)
                for seg in segments:
                    seg_start = seg.get("start", 0.0) + offset_sec
                    seg_end = seg.get("end", 0.0) + offset_sec
                    all_segments.append({
                        "start": seg_start,
                        "end": seg_end,
                        "text": seg.get("text", "").strip()
                    })

            # Check cancellation before chunking & embedding
            if await is_cancelled_async():
                logger.info(f"Job {job_id} cancelled before embedding. Halting.")
                await asyncio.to_thread(db.update_video, video_id, {"status": "cancelled", "error_message": "Ingestion cancelled by user"})
                return

            # 4. Semantic chunking
            chunks = merge_segments_to_chunks(all_segments, target_duration=45.0)
            if not chunks:
                chunks = [{
                    "text": f"Lecture transcript for {title}.",
                    "start_seconds": 0.0,
                    "end_seconds": float(duration_seconds or 60.0)
                }]

            # 5. Gemini Embeddings (offloaded to thread pool)
            await asyncio.to_thread(db.update_video, video_id, {"status": "indexing"})
            await set_job_stage_async("indexing")

            chunk_texts = [c["text"] for c in chunks]
            embeddings = await asyncio.to_thread(embed_texts, chunk_texts, status_callback=set_job_stage_sync, cancel_check=is_cancelled_sync)

            if await is_cancelled_async():
                logger.info(f"Job {job_id} cancelled after embedding. Halting.")
                await asyncio.to_thread(db.update_video, video_id, {"status": "cancelled", "error_message": "Ingestion cancelled by user"})
                return

            # 6. Persist Chunks (delete any stale/partial chunks from previous attempts first)
            chunks_to_insert = []
            for c, emb in zip(chunks, embeddings):
                chunks_to_insert.append({
                    "id": str(uuid.uuid4()),
                    "video_id": video_id,
                    "text": c["text"],
                    "start_seconds": c["start_seconds"],
                    "end_seconds": c["end_seconds"],
                    "embedding": emb,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

            await asyncio.to_thread(db.delete_chunks_for_video, video_id)
            await asyncio.to_thread(db.insert_chunks, chunks_to_insert)

            # 7. Update Video and Job state to ready
            await asyncio.to_thread(db.update_video, video_id, {
                "status": "ready",
                "error_message": None,
            })

            fresh_job = (await asyncio.to_thread(db.get_job, job_id)) or job
            current_vids = list(fresh_job.get("video_ids") or [])
            if video_id not in current_vids:
                current_vids.append(video_id)

            total_target = fresh_job.get("progress_total") or 1
            new_progress = (fresh_job.get("progress_current") or 0) + 1
            is_done = new_progress >= total_target

            # Update sub-job if present
            sub_jobs = list(fresh_job.get("sub_jobs") or [])
            for sj in sub_jobs:
                if sj.get("video_id") in [youtube_id, entry.get("youtube_id")]:
                    sj["status"] = "done"
                    sj["progress"] = 100

            await asyncio.to_thread(db.update_job, job_id, {
                "video_ids": current_vids,
                "progress_current": total_target if (fresh_job.get("type") == "video" or is_done) else new_progress,
                "progress_total": total_target,
                "status": "done" if is_done else "processing",
                "stage": None if is_done else "downloading",
                "sub_jobs": sub_jobs if sub_jobs else None,
                "error_message": None,
            })

        finally:
            # Clean up temporary audio files
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    except asyncio.CancelledError:
        logger.info(f"Job {job_id} task was cancelled. Cleaned up.")
        if "video_id" in locals():
            await asyncio.to_thread(db.update_video, video_id, {
                "status": "cancelled",
                "error_message": "Ingestion cancelled by user",
            })
        fresh_job = (await asyncio.to_thread(db.get_job, job_id)) or job
        sub_jobs = list(fresh_job.get("sub_jobs") or [])
        for sj in sub_jobs:
            if sj.get("video_id") in [youtube_id, entry.get("youtube_id")] and sj.get("status") != "done":
                sj["status"] = "cancelled"
                sj["error_message"] = "Ingestion cancelled by user"
        await asyncio.to_thread(db.update_job, job_id, {
            "status": "cancelled",
            "stage": None,
            "sub_jobs": sub_jobs if sub_jobs else None,
            "error_message": "Ingestion cancelled by user",
        })
    except Exception as e:
        logger.error(f"Pipeline error for video {entry.get('title')}: {e}", exc_info=True)
        if "video_id" in locals():
            await asyncio.to_thread(db.update_video, video_id, {
                "status": "failed",
                "error_message": str(e),
            })
        fresh_job = (await asyncio.to_thread(db.get_job, job_id)) or job
        sub_jobs = list(fresh_job.get("sub_jobs") or [])
        for sj in sub_jobs:
            if sj.get("video_id") in [youtube_id, entry.get("youtube_id")] and sj.get("status") != "done":
                sj["status"] = "failed"
                sj["error_message"] = str(e)
        await asyncio.to_thread(db.update_job, job_id, {
            "status": "failed",
            "stage": None,
            "sub_jobs": sub_jobs if sub_jobs else None,
            "error_message": str(e),
        })
# =============================================================================
# API ROUTES
# =============================================================================

def find_active_job_for_video(vid_id: str) -> Optional[str]:
    """Finds an active in-progress job associated with a given video ID."""
    for j in db.list_jobs():
        if j.get("status") in ["queued", "processing"] and vid_id in (j.get("video_ids") or []):
            return j["id"]
    return None


@app.post("/api/videos", response_model=VideoIngestResponse, status_code=200)
async def ingest_video(req: VideoIngestRequest, background_tasks: BackgroundTasks):
    """
    Submits a video or playlist URL for ingestion.
    Blocks duplicate submissions:
    - If video is already ready: returns status="already_exists" with no new job.
    - If video is actively processing: returns status="already_processing" with no new job.
    - If video is failed/cancelled or new: starts new job.
    """
    if not req.url or "youtu" not in req.url:
        raise HTTPException(status_code=400, detail="Please enter a valid YouTube video or playlist URL.")

    # 1. Fast duplicate check before network operations
    fast_vid_id, fast_plist_id = extract_youtube_id(req.url)
    if fast_vid_id and not fast_plist_id:
        existing = db.get_video_by_youtube_id(fast_vid_id)
        if existing:
            v_status = existing.get("status")
            if v_status == "ready":
                return VideoIngestResponse(
                    job_id=None,
                    type="video",
                    status="already_exists",
                    message="This video is already in your library.",
                    video_id=existing["id"]
                )
            elif v_status in ["queued", "downloading", "transcribing", "indexing", "waiting_on_rate_limit"]:
                active_job_id = find_active_job_for_video(existing["id"])
                return VideoIngestResponse(
                    job_id=active_job_id,
                    type="video",
                    status="already_processing",
                    message="This video is already being processed — check Current Jobs for its status.",
                    video_id=existing["id"]
                )

    try:
        media_type, entries = await asyncio.to_thread(extract_metadata_and_expand_urls, req.url)
        if not entries:
            raise HTTPException(status_code=400, detail="No playable videos found at the provided URL.")

        # Post-extraction duplicate check for single video
        if media_type == "video" and len(entries) == 1:
            y_id = entries[0].get("youtube_id")
            if y_id:
                existing = db.get_video_by_youtube_id(y_id)
                if existing:
                    v_status = existing.get("status")
                    if v_status == "ready":
                        return VideoIngestResponse(
                            job_id=None,
                            type="video",
                            status="already_exists",
                            message="This video is already in your library.",
                            video_id=existing["id"]
                        )
                    elif v_status in ["queued", "downloading", "transcribing", "indexing", "waiting_on_rate_limit"]:
                        active_job_id = find_active_job_for_video(existing["id"])
                        return VideoIngestResponse(
                            job_id=active_job_id,
                            type="video",
                            status="already_processing",
                            message="This video is already being processed — check Current Jobs for its status.",
                            video_id=existing["id"]
                        )

        job_id = str(uuid.uuid4())
        job_title = (
            f"Playlist ({len(entries)} videos)"
            if media_type == "playlist"
            else entries[0].get("title", "YouTube Ingest Video")
        )

        sub_jobs = [
            SubJobInfo(
                video_id=e.get("youtube_id") or str(idx),
                title=e.get("title", f"Video {idx+1}"),
                status="queued",
                progress=0
            ).model_dump()
            for idx, e in enumerate(entries)
        ]

        await asyncio.to_thread(db.create_job, {
            "id": job_id,
            "type": media_type,
            "title": job_title,
            "status": "queued",
            "stage": "downloading",
            "video_ids": [],
            "progress_current": 0,
            "progress_total": len(entries),
            "sub_jobs": sub_jobs,
            "error_message": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "url": req.url,
        })

        for entry in entries:
            background_tasks.add_task(process_video_pipeline, job_id, entry)

        return VideoIngestResponse(job_id=job_id, type=media_type, status="queued")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve URL {req.url}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to resolve URL: {str(e)}")


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Returns the status and stage of an ingestion job."""
    job = await asyncio.to_thread(db.get_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")
    return JobResponse(
        id=job["id"],
        type=job.get("type", "video"),
        title=job.get("title"),
        status=job.get("status", "queued"),
        stage=job.get("stage"),
        video_ids=job.get("video_ids") or [],
        progress_current=job.get("progress_current", 0),
        progress_total=job.get("progress_total", 100),
        sub_jobs=job.get("sub_jobs"),
        error_message=job.get("error_message"),
        created_at=job.get("created_at"),
        url=job.get("url"),
    )


@app.get("/api/jobs", response_model=List[JobResponse])
async def list_jobs():
    """Lists all recent background ingestion jobs."""
    jobs = await asyncio.to_thread(db.list_jobs)
    return [
        JobResponse(
            id=j["id"],
            type=j.get("type", "video"),
            title=j.get("title"),
            status=j.get("status", "queued"),
            stage=j.get("stage"),
            video_ids=j.get("video_ids") or [],
            progress_current=j.get("progress_current", 0),
            progress_total=j.get("progress_total", 100),
            sub_jobs=j.get("sub_jobs"),
            error_message=j.get("error_message"),
            created_at=j.get("created_at"),
            url=j.get("url"),
        )
        for j in jobs
    ]


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancels an in-progress background ingestion job cooperatively."""
    job = await asyncio.to_thread(db.get_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")

    if job.get("status") in ["done", "failed", "cancelled"]:
        return {"status": "already_terminal", "job": job}

    sub_jobs = list(job.get("sub_jobs") or [])
    for sj in sub_jobs:
        if sj.get("status") not in ["done", "failed"]:
            sj["status"] = "cancelled"
            sj["error_message"] = "Ingestion cancelled by user"

    try:
        await asyncio.to_thread(db.update_job, job_id, {
            "status": "cancelled",
            "stage": None,
            "sub_jobs": sub_jobs if sub_jobs else None,
            "error_message": "Ingestion cancelled by user",
        })
    except Exception as e_job:
        logger.error(f"Failed to update job {job_id} status to cancelled: {e_job}")
        raise HTTPException(status_code=500, detail=f"Database error while cancelling job: {str(e_job)}")

    # Update any associated videos that are not yet ready
    for vid_id in job.get("video_ids") or []:
        try:
            vid = await asyncio.to_thread(db.get_video, vid_id)
            if vid and vid.get("status") != "ready":
                await asyncio.to_thread(db.update_video, vid_id, {
                    "status": "cancelled",
                    "error_message": "Ingestion cancelled by user",
                })
        except Exception as e_vid:
            logger.error(f"Failed to update video {vid_id} status to cancelled: {e_vid}")

    fresh_job = await asyncio.to_thread(db.get_job, job_id) or job
    return {"status": "cancelled", "job": fresh_job}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Removes a job history entry from the database."""
    job = await asyncio.to_thread(db.get_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")

    # If job is actively in-progress, cancel it first to halt background work
    if job.get("status") in ["queued", "processing"]:
        try:
            await asyncio.to_thread(db.update_job, job_id, {
                "status": "cancelled",
                "stage": None,
                "error_message": "Cancelled and removed by user",
            })
        except Exception as ce:
            logger.warning(f"Could not mark job {job_id} as cancelled before deleting: {ce}")

    try:
        await asyncio.to_thread(db.delete_job, job_id)
        return {"status": "deleted", "job_id": job_id}
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error while deleting job: {str(e)}")


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, background_tasks: BackgroundTasks):
    """
    Retries a failed or cancelled ingestion job.
    Enforces idempotency and active status checks:
    - If the video is already 'ready' in the library, marks the job as done and notifies the user.
    - If the video is actively processing under another task, returns an already_processing status.
    - Otherwise, re-launches the ingestion pipeline for the job.
    """
    job = await asyncio.to_thread(db.get_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    url = job.get("url")
    if not url and job.get("video_ids"):
        # Reconstruct URL from associated video if available
        for vid_id in job["video_ids"]:
            v = await asyncio.to_thread(db.get_video, vid_id)
            if v and v.get("youtube_video_id"):
                url = f"https://www.youtube.com/watch?v={v['youtube_video_id']}"
                break

    if not url:
        raise HTTPException(status_code=400, detail="Cannot retry job: No video URL is associated with this job.")

    # 1. Fast pre-extraction check for single video URL
    fast_vid_id, _ = extract_youtube_id(url)
    existing_video = (await asyncio.to_thread(db.get_video_by_youtube_id, fast_vid_id)) if fast_vid_id else None
    if not existing_video and job.get("video_ids"):
        existing_video = await asyncio.to_thread(db.get_video, job["video_ids"][0])

    if existing_video:
        if existing_video.get("status") == "ready":
            # Video is already indexed and ready in the library!
            await asyncio.to_thread(db.update_job, job_id, {
                "status": "done",
                "stage": None,
                "error_message": None,
                "progress_current": 1,
                "progress_total": 1,
                "video_ids": [existing_video["id"]],
            })
            return {
                "status": "already_exists",
                "message": "This video is already in your library.",
                "job": await asyncio.to_thread(db.get_job, job_id),
            }
        elif existing_video.get("status") in ["queued", "downloading", "transcribing", "indexing", "waiting_on_rate_limit"]:
            return {
                "status": "already_processing",
                "message": "This video is already being processed — check Current Jobs for its status.",
                "job": db.get_job(job_id),
            }

    try:
        media_type, entries = await asyncio.to_thread(extract_metadata_and_expand_urls, url)
        if not entries:
            raise HTTPException(status_code=400, detail="Could not retrieve any video metadata for this URL.")

        # Post-extraction duplicate check for single video
        if len(entries) == 1:
            entry_yt_id = entries[0].get("youtube_id")
            if entry_yt_id:
                post_existing = await asyncio.to_thread(db.get_video_by_youtube_id, entry_yt_id)
                if post_existing and post_existing.get("status") == "ready":
                    await asyncio.to_thread(db.update_job, job_id, {
                        "status": "done",
                        "stage": None,
                        "error_message": None,
                        "progress_current": 1,
                        "progress_total": 1,
                        "video_ids": [post_existing["id"]],
                    })
                    return {
                        "status": "already_exists",
                        "message": "This video is already in your library.",
                        "job": await asyncio.to_thread(db.get_job, job_id),
                    }

        # Reset any failed/cancelled video rows so they re-process cleanly
        for entry in entries:
            ex = await asyncio.to_thread(db.get_video_by_youtube_id, entry["youtube_id"])
            if ex and ex.get("status") in ["failed", "cancelled"]:
                await asyncio.to_thread(db.update_video, ex["id"], {
                    "status": "downloading",
                    "error_message": None,
                })

        sub_jobs = [
            SubJobInfo(
                video_id=e.get("youtube_id") or str(idx),
                title=e.get("title", f"Video {idx+1}"),
                status="queued",
                progress=0
            ).model_dump()
            for idx, e in enumerate(entries)
        ]

        await asyncio.to_thread(db.update_job, job_id, {
            "status": "processing",
            "stage": "downloading",
            "error_message": None,
            "progress_current": 0,
            "progress_total": len(entries),
            "sub_jobs": sub_jobs,
            "url": url,
        })

        for entry in entries:
            background_tasks.add_task(process_video_pipeline, job_id, entry)

        return {
            "status": "restarted",
            "message": "Ingestion job restarted.",
            "job": await asyncio.to_thread(db.get_job, job_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying job {job_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to restart job: {str(e)}")


@app.post("/api/videos/{video_id}/cancel")
async def cancel_video(video_id: str):
    """
    Cancels an in-progress video ingestion cooperatively from the Library grid.
    If the video is associated with a single-video job or playlist job, cancels the parent job or sub_job entry.
    """
    video = await asyncio.to_thread(db.get_video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=f"Video with ID '{video_id}' not found")

    if video.get("status") in ["ready", "failed", "cancelled"]:
        return {"status": "already_terminal", "video": video}

    try:
        await asyncio.to_thread(db.update_video, video_id, {
            "status": "cancelled",
            "error_message": "Ingestion cancelled by user",
        })

        # Find and cancel active parent job if present
        active_job_id = find_active_job_for_video(video_id)
        if active_job_id:
            job = await asyncio.to_thread(db.get_job, active_job_id)
            if job and job.get("status") in ["queued", "processing"]:
                # If it's a single video job, cancel parent job
                if job.get("type") == "video" or len(job.get("video_ids") or []) <= 1:
                    await asyncio.to_thread(db.update_job, active_job_id, {
                        "status": "cancelled",
                        "stage": None,
                        "error_message": "Ingestion cancelled by user",
                    })
                else:
                    # Update sub_jobs for playlist
                    sub_jobs = list(job.get("sub_jobs") or [])
                    updated = False
                    for sj in sub_jobs:
                        if sj.get("video_id") == video_id and sj.get("status") not in ["done", "failed", "cancelled"]:
                            sj["status"] = "cancelled"
                            sj["error_message"] = "Ingestion cancelled by user"
                            updated = True
                    if updated:
                        await asyncio.to_thread(db.update_job, active_job_id, {"sub_jobs": sub_jobs})

        fresh_video = await asyncio.to_thread(db.get_video, video_id) or video
        return {"status": "cancelled", "video": fresh_video}
    except Exception as e:
        logger.error(f"Failed to cancel video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error while cancelling video: {str(e)}")


@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    """
    Cascading delete: removes a video, its associated chunks, and cleans up references.
    If the video is mid-processing, cancels it first.
    """
    video = await asyncio.to_thread(db.get_video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=f"Video with ID '{video_id}' not found")

    try:
        if video.get("status") in ["queued", "downloading", "transcribing", "indexing", "waiting_on_rate_limit"]:
            try:
                await asyncio.to_thread(db.update_video, video_id, {
                    "status": "cancelled",
                    "error_message": "Deleted by user"
                })
            except Exception as ce:
                logger.warning(f"Could not mark video {video_id} as cancelled before deleting: {ce}")

        await asyncio.to_thread(db.delete_video, video_id)
        return {"status": "deleted", "video_id": video_id}
    except Exception as e:
        logger.error(f"Failed to delete video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error while deleting video: {str(e)}")


@app.get("/api/videos", response_model=List[VideoListItem])
async def list_videos():
    """Lists all videos in the study carrel library."""
    videos = await asyncio.to_thread(db.list_videos)
    return [
        VideoListItem(
            id=v["id"],
            youtube_video_id=v.get("youtube_video_id", ""),
            title=v.get("title", "Lecture Video"),
            thumbnail_url=v.get("thumbnail_url"),
            duration_seconds=v.get("duration_seconds", 0),
            status=v.get("status", "ready"),
            error_message=v.get("error_message"),
            added_at=v.get("added_at") or datetime.now(timezone.utc).isoformat(),
            tags=v.get("tags") or [],
            description=v.get("description"),
            channel_name=v.get("channel_name"),
        )
        for v in videos
    ]


@app.get("/api/videos/{video_id}", response_model=VideoDetailResponse)
async def get_video_detail(video_id: str):
    """Returns video details with full sorted transcript chunks."""
    video = await asyncio.to_thread(db.get_video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail=f"Video with ID '{video_id}' not found")

    chunks_data = await asyncio.to_thread(db.get_chunks_for_video, video_id)
    chunk_items = [
        ChunkItem(
            id=c.get("id"),
            text=c["text"],
            start_seconds=c["start_seconds"],
            end_seconds=c["end_seconds"],
            time_formatted=format_seconds(c["start_seconds"])
        )
        for c in chunks_data
    ]

    return VideoDetailResponse(
        id=video["id"],
        youtube_video_id=video.get("youtube_video_id", ""),
        title=video.get("title", "Lecture Video"),
        thumbnail_url=video.get("thumbnail_url"),
        duration_seconds=video.get("duration_seconds", 0),
        status=video.get("status", "ready"),
        error_message=video.get("error_message"),
        added_at=video.get("added_at"),
        tags=video.get("tags") or [],
        description=video.get("description"),
        channel_name=video.get("channel_name"),
        chunks=chunk_items
    )


# Configurable Generation Model for RAG answer synthesis
DEFAULT_GENERATION_MODEL = os.getenv("GEMINI_GENERATION_MODEL", "gemini-3.6-flash")


@app.post("/api/search", response_model=SearchResponse)
async def search_rag(req: SearchRequest):
    """
    Executes synchronous RAG query:
    1. Embeds user query using Gemini gemini-embedding-001 with task_type=RETRIEVAL_QUERY.
    2. Retrieves top 8 chunks by cosine similarity from pgvector.
    3. Injects retrieved chunks with timestamps and title labels into Gemini prompt.
    4. Generates cited research answer via gemini-3.6-flash.
    """
    global gemini_client
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    query_str = req.query.strip()

    # 1. Embed query with RETRIEVAL_QUERY task_type and 768-dim L2 normalization
    query_emb = await asyncio.to_thread(embed_query, query_str)

    # 2. Vector search in database
    retrieved_chunks = await asyncio.to_thread(
        db.search_chunks,
        query_embedding=query_emb,
        video_id=req.video_id,
        limit=8
    )

    top_results: List[SearchResultItem] = [
        SearchResultItem(
            video_id=r["video_id"],
            youtube_video_id=r.get("youtube_video_id"),
            title=r.get("title", "Lecture Video"),
            thumbnail_url=r.get("thumbnail_url"),
            text=r["text"],
            start_seconds=r["start_seconds"],
            end_seconds=r["end_seconds"],
            score=r["score"],
            duration_seconds=r.get("duration_seconds"),
            channel_name=r.get("channel_name"),
        )
        for r in retrieved_chunks
    ]

    # 3. Format Context for Gemini
    context_lines = [
        f'[Source {i + 1}] Video: "{r.title}" at timestamp {format_seconds(r.start_seconds)} - {format_seconds(r.end_seconds)}:\n"{r.text}"'
        for i, r in enumerate(top_results)
    ]
    context_prompt = "\n\n".join(context_lines)

    # 4. Generate Answer with Gemini
    generated_answer = ""
    client = get_gemini_client()

    if client and top_results:
        try:
            full_prompt = (
                f"You are the AI research assistant for the Digital Study Carrel personal video RAG system.\n"
                f"Answer the user's research question strictly using the provided video transcript excerpts below.\n"
                f"Cite the exact source video title and timestamp (e.g. [03:45] or [00:32]) for every substantive claim.\n"
                f"If the transcript excerpts do not contain enough information to answer the question, clearly state that the knowledge base does not cover it rather than speculating.\n\n"
                f"Question: {query_str}\n\n"
                f"Provided Video Transcript Chunks:\n{context_prompt}"
            )
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=DEFAULT_GENERATION_MODEL,
                contents=full_prompt,
            )
            generated_answer = response.text or ""
        except Exception as ai_err:
            logger.warning(f"Gemini generation failed, using heuristic fallback: {ai_err}")

    # Fallback heuristic synthesis if Gemini call not available
    if not generated_answer:
        if top_results and top_results[0].score > 0.2:
            top = top_results[0]
            generated_answer = f"Based on **\"{top.title}\"** at [{format_seconds(top.start_seconds)}], {top.text}"
            if len(top_results) > 1 and top_results[1].score > 0.25:
                second = top_results[1]
                generated_answer += f"\n\nFurthermore, in **\"{second.title}\"** at [{format_seconds(second.start_seconds)}]: \"{second.text}\""
        else:
            generated_answer = (
                f"No strong semantic matches were found in your library transcripts for \"{query_str}\". "
                "Try ingesting more related lecture materials or rephrasing your search query."
            )

    return SearchResponse(
        query=query_str,
        answer=generated_answer,
        results=top_results
    )


@app.get("/api/status", response_model=StatusResponse)
async def get_system_status():
    """Returns system configuration, active runtime models, and database counts."""
    stats = await asyncio.to_thread(db.get_system_stats)
    db_mode = "Supabase (PostgreSQL + pgvector)" if isinstance(db, SupabaseDatabase) else "In-Memory (Ephemeral)"
    return StatusResponse(
        status="ok",
        gemini_configured=bool(os.getenv("GEMINI_API_KEY")),
        groq_configured=bool(os.getenv("GROQ_API_KEY")),
        supabase_configured=bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        generation_model=DEFAULT_GENERATION_MODEL,
        transcription_model="whisper-large-v3-turbo",
        database_mode=db_mode,
        total_videos=stats["total_videos"],
        total_chunks=stats["total_chunks"],
        active_jobs=stats["active_jobs"],
    )


# =============================================================================
# STATIC SPA MOUNTING (Production Single-Process Container)
# =============================================================================
dist_path = os.path.join(os.getcwd(), "dist")
if os.path.exists(dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't hijack /api paths
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        target_file = os.path.join(dist_path, full_path)
        if os.path.isfile(target_file):
            return FileResponse(target_file)
        return FileResponse(os.path.join(dist_path, "index.html"))
