import os
import logging
import math
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("backend.db")

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class BaseDatabase:
    def get_video_by_youtube_id(self, youtube_video_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def create_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def update_video(self, video_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def create_or_update_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def list_videos(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_jobs(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def insert_chunks(self, chunks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def delete_chunks_for_video(self, video_id: str) -> None:
        raise NotImplementedError

    def get_chunks_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def search_chunks(
        self,
        query_embedding: List[float],
        video_id: Optional[str] = None,
        limit: int = 8
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def delete_video(self, video_id: str) -> bool:
        raise NotImplementedError

    def delete_job(self, job_id: str) -> bool:
        raise NotImplementedError

    def get_system_stats(self) -> Dict[str, int]:
        raise NotImplementedError


def _is_stale_job(job: Dict[str, Any], threshold_seconds: float = 900.0) -> bool:
    """Checks whether a non-terminal job has had no activity for longer than threshold_seconds (default 15 mins)."""
    if not job or job.get("status") not in ["queued", "processing"]:
        return False
    ts_str = job.get("updated_at") or job.get("created_at")
    if not ts_str:
        return False
    try:
        if isinstance(ts_str, str):
            clean_ts = ts_str[:-1] + "+00:00" if ts_str.endswith("Z") else ts_str
            dt = datetime.fromisoformat(clean_ts)
        elif isinstance(ts_str, datetime):
            dt = ts_str
        else:
            return False

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() > threshold_seconds
    except Exception:
        return False


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    similarity = dot_product / (norm_a * norm_b)
    return max(0.0, min(1.0, float(similarity)))


class InMemoryDatabase(BaseDatabase):
    """Explicit in-memory store used ONLY when LOCAL_DEV=true."""

    def __init__(self):
        logger.warning(
            "[WARN] Initializing InMemoryDatabase because LOCAL_DEV=true is set. "
            "Data will not persist across restarts."
        )
        self.videos: Dict[str, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.chunks: List[Dict[str, Any]] = []

    def get_video_by_youtube_id(self, youtube_video_id: str) -> Optional[Dict[str, Any]]:
        for v in self.videos.values():
            if v.get("youtube_video_id") == youtube_video_id:
                return dict(v)
        return None

    def create_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        vid_id = video_data.get("id") or str(uuid.uuid4())
        existing = self.videos.get(vid_id, {})
        record = {
            "id": vid_id,
            "youtube_video_id": video_data.get("youtube_video_id") or existing.get("youtube_video_id", ""),
            "title": video_data.get("title") or existing.get("title", "Untitled Lecture"),
            "thumbnail_url": video_data.get("thumbnail_url") or existing.get("thumbnail_url"),
            "duration_seconds": int(video_data.get("duration_seconds") if video_data.get("duration_seconds") is not None else existing.get("duration_seconds", 0)),
            "status": video_data.get("status") or existing.get("status", "queued"),
            "error_message": video_data.get("error_message") if "error_message" in video_data else existing.get("error_message"),
            "added_at": video_data.get("added_at") or existing.get("added_at") or _utc_now_iso(),
            "tags": video_data.get("tags") or existing.get("tags", []),
            "description": video_data.get("description") or existing.get("description"),
            "channel_name": video_data.get("channel_name") or existing.get("channel_name"),
        }
        self.videos[vid_id] = record
        return dict(record)

    def update_video(self, video_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if video_id not in self.videos:
            return None
        payload = {k: v for k, v in updates.items() if k != "id"}
        self.videos[video_id].update(payload)
        return dict(self.videos[video_id])

    def create_or_update_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        vid_id = video_data.get("id")
        if vid_id and vid_id in self.videos and "youtube_video_id" not in video_data:
            updated = self.update_video(vid_id, {k: v for k, v in video_data.items() if k != "id"})
            return updated or video_data
        return self.create_video(video_data)

    def list_videos(self) -> List[Dict[str, Any]]:
        v_list = list(self.videos.values())
        v_list.sort(key=lambda x: str(x.get("added_at", "")), reverse=True)
        return [dict(v) for v in v_list]

    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        v = self.videos.get(video_id)
        return dict(v) if v else None

    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        job_id = job_data.get("id") or str(uuid.uuid4())
        now_str = _utc_now_iso()
        record = {
            "id": job_id,
            "type": job_data.get("type", "video"),
            "title": job_data.get("title"),
            "status": job_data.get("status", "queued"),
            "stage": job_data.get("stage", "downloading"),
            "video_ids": list(job_data.get("video_ids") or []),
            "progress_current": int(job_data.get("progress_current") or 0),
            "progress_total": int(job_data.get("progress_total") or 100),
            "sub_jobs": list(job_data.get("sub_jobs") or []),
            "error_message": job_data.get("error_message"),
            "created_at": job_data.get("created_at") or now_str,
            "updated_at": job_data.get("updated_at") or now_str,
            "url": job_data.get("url"),
        }
        self.jobs[job_id] = record
        return dict(record)

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(job_id)
        if not job:
            return None
        payload = dict(updates)
        payload["updated_at"] = _utc_now_iso()
        job.update(payload)
        return dict(job)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        j = self.jobs.get(job_id)
        if not j:
            return None
        if _is_stale_job(j):
            j.update({
                "status": "failed",
                "stage": None,
                "error_message": "Stalled — no progress in 15 minutes. You can retry this job.",
                "updated_at": _utc_now_iso(),
            })
            for vid_id in j.get("video_ids") or []:
                if vid_id in self.videos and self.videos[vid_id].get("status") not in ["ready", "failed", "cancelled"]:
                    self.videos[vid_id].update({
                        "status": "failed",
                        "error_message": "Processing stalled — please retry.",
                    })
        return dict(j)

    def list_jobs(self) -> List[Dict[str, Any]]:
        for j in self.jobs.values():
            if _is_stale_job(j):
                j.update({
                    "status": "failed",
                    "stage": None,
                    "error_message": "Stalled — no progress in 15 minutes. You can retry this job.",
                    "updated_at": _utc_now_iso(),
                })
                for vid_id in j.get("video_ids") or []:
                    if vid_id in self.videos and self.videos[vid_id].get("status") not in ["ready", "failed", "cancelled"]:
                        self.videos[vid_id].update({
                            "status": "failed",
                            "error_message": "Processing stalled — please retry.",
                        })
        j_list = list(self.jobs.values())
        j_list.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return [dict(j) for j in j_list]

    def insert_chunks(self, chunks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        inserted = []
        for c in chunks_data:
            chunk_record = {
                "id": c.get("id") or str(uuid.uuid4()),
                "video_id": c["video_id"],
                "text": c["text"],
                "start_seconds": float(c["start_seconds"]),
                "end_seconds": float(c["end_seconds"]),
                "embedding": c.get("embedding"),
                "created_at": c.get("created_at") or _utc_now_iso(),
            }
            self.chunks.append(chunk_record)
            inserted.append(chunk_record)
        return inserted

    def delete_chunks_for_video(self, video_id: str) -> None:
        self.chunks = [c for c in self.chunks if c["video_id"] != video_id]

    def get_chunks_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        matched = [c for c in self.chunks if c["video_id"] == video_id]
        matched.sort(key=lambda x: x["start_seconds"])
        return [dict(c) for c in matched]

    def search_chunks(
        self,
        query_embedding: List[float],
        video_id: Optional[str] = None,
        limit: int = 8
    ) -> List[Dict[str, Any]]:
        candidates = self.chunks
        if video_id:
            candidates = [c for c in candidates if c["video_id"] == video_id]

        scored = []
        for c in candidates:
            emb = c.get("embedding")
            if not emb:
                continue
            sim = _cosine_similarity(query_embedding, emb)
            video = self.videos.get(c["video_id"], {})
            scored.append({
                "id": c["id"],
                "video_id": c["video_id"],
                "youtube_video_id": video.get("youtube_video_id", ""),
                "title": video.get("title", "Lecture Video"),
                "thumbnail_url": video.get("thumbnail_url"),
                "duration_seconds": video.get("duration_seconds", 0),
                "channel_name": video.get("channel_name"),
                "text": c["text"],
                "start_seconds": c["start_seconds"],
                "end_seconds": c["end_seconds"],
                "score": sim,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def delete_video(self, video_id: str) -> bool:
        # 1. Remove associated chunks
        self.chunks = [c for c in self.chunks if c.get("video_id") != video_id]
        # 2. Update any jobs referencing this video_id
        for job in self.jobs.values():
            if "video_ids" in job and video_id in job["video_ids"]:
                job["video_ids"] = [vid for vid in job["video_ids"] if vid != video_id]
        # 3. Remove video
        if video_id in self.videos:
            del self.videos[video_id]
            return True
        return False

    def delete_job(self, job_id: str) -> bool:
        if job_id in self.jobs:
            del self.jobs[job_id]
            return True
        return False

    def get_system_stats(self) -> Dict[str, int]:
        active_jobs = sum(1 for j in self.jobs.values() if j.get("status") == "processing")
        return {
            "total_videos": len(self.videos),
            "total_chunks": len(self.chunks),
            "active_jobs": active_jobs,
        }


class SupabaseDatabase(BaseDatabase):
    """Production Supabase client wrapping PostgreSQL + pgvector."""

    def __init__(self, supabase_url: str, supabase_key: str):
        from supabase import create_client, Client
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        try:
            self.client: Client = create_client(supabase_url, supabase_key)
            logger.info("Successfully connected to Supabase.")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Supabase client: {str(e)}") from e

    def get_video_by_youtube_id(self, youtube_video_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = (
                self.client.table("videos")
                .select("*")
                .eq("youtube_video_id", youtube_video_id)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error querying video by youtube ID {youtube_video_id}: {e}")
            return None

    def create_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        vid_id = video_data.get("id") or str(uuid.uuid4())
        record = {
            "id": vid_id,
            "youtube_video_id": video_data.get("youtube_video_id", ""),
            "title": video_data.get("title", "Untitled Lecture"),
            "thumbnail_url": video_data.get("thumbnail_url"),
            "duration_seconds": int(video_data.get("duration_seconds") or 0),
            "status": video_data.get("status", "queued"),
            "error_message": video_data.get("error_message"),
            "added_at": video_data.get("added_at") or _utc_now_iso(),
            "tags": video_data.get("tags", []),
            "description": video_data.get("description"),
            "channel_name": video_data.get("channel_name"),
        }
        payload = {k: v for k, v in record.items() if v is not None}
        try:
            res = self.client.table("videos").upsert(payload).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return payload
        except Exception as e:
            logger.error(f"Error creating/upserting full video: {e}")
            raise e

    def update_video(self, video_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = {k: v for k, v in updates.items() if k != "id"}
        try:
            res = self.client.table("videos").update(payload).eq("id", video_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error updating video {video_id}: {e}")
            raise e

    def create_or_update_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        vid_id = video_data.get("id")
        if vid_id and "youtube_video_id" not in video_data:
            # Defensive routing for partial status updates
            updates = {k: v for k, v in video_data.items() if k != "id"}
            updated = self.update_video(vid_id, updates)
            return updated or video_data
        return self.create_video(video_data)

    def list_videos(self) -> List[Dict[str, Any]]:
        try:
            res = self.client.table("videos").select("*").order("added_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error listing videos: {e}")
            return []

    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = self.client.table("videos").select("*").eq("id", video_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting video {video_id}: {e}")
            return None

    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: v for k, v in job_data.items() if v is not None}
        if "id" not in payload:
            payload["id"] = str(uuid.uuid4())
        try:
            res = self.client.table("jobs").insert(payload).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return payload
        except Exception as e:
            logger.error(f"Error creating job: {e}")
            raise e

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            res = self.client.table("jobs").update(updates).eq("id", job_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return None

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = self.client.table("jobs").select("*").eq("id", job_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                j = res.data[0]
                if _is_stale_job(j):
                    self.update_job(j["id"], {
                        "status": "failed",
                        "stage": None,
                        "error_message": "Stalled — no progress in 15 minutes. You can retry this job.",
                    })
                    j["status"] = "failed"
                    j["stage"] = None
                    j["error_message"] = "Stalled — no progress in 15 minutes. You can retry this job."
                    for vid_id in j.get("video_ids") or []:
                        vid = self.get_video(vid_id)
                        if vid and vid.get("status") not in ["ready", "failed", "cancelled"]:
                            self.update_video(vid_id, {
                                "status": "failed",
                                "error_message": "Processing stalled — please retry.",
                            })
                return j
            return None
        except Exception as e:
            logger.error(f"Error getting job {job_id}: {e}")
            return None

    def list_jobs(self) -> List[Dict[str, Any]]:
        try:
            res = self.client.table("jobs").select("*").order("created_at", desc=True).execute()
            jobs = res.data or []
            for j in jobs:
                if _is_stale_job(j):
                    self.update_job(j["id"], {
                        "status": "failed",
                        "stage": None,
                        "error_message": "Stalled — no progress in 15 minutes. You can retry this job.",
                    })
                    j["status"] = "failed"
                    j["stage"] = None
                    j["error_message"] = "Stalled — no progress in 15 minutes. You can retry this job."
                    for vid_id in j.get("video_ids") or []:
                        vid = self.get_video(vid_id)
                        if vid and vid.get("status") not in ["ready", "failed", "cancelled"]:
                            self.update_video(vid_id, {
                                "status": "failed",
                                "error_message": "Processing stalled — please retry.",
                            })
            return jobs
        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            return []

    def insert_chunks(self, chunks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not chunks_data:
            return []
        try:
            res = self.client.table("chunks").insert(chunks_data).execute()
            return res.data or chunks_data
        except Exception as e:
            logger.error(f"Error inserting chunks: {e}")
            raise e

    def delete_chunks_for_video(self, video_id: str) -> None:
        try:
            self.client.table("chunks").delete().eq("video_id", video_id).execute()
        except Exception as e:
            logger.error(f"Error deleting chunks for video {video_id}: {e}")
            raise e

    def get_chunks_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        try:
            res = (
                self.client.table("chunks")
                .select("id, video_id, text, start_seconds, end_seconds")
                .eq("video_id", video_id)
                .order("start_seconds", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Error getting chunks for video {video_id}: {e}")
            return []

    def search_chunks(
        self,
        query_embedding: List[float],
        video_id: Optional[str] = None,
        limit: int = 8
    ) -> List[Dict[str, Any]]:
        try:
            params = {
                "query_embedding": query_embedding,
                "match_count": limit,
                "filter_video_id": video_id,
            }
            res = self.client.rpc("match_chunks", params).execute()
            if res.data:
                results = []
                for item in res.data:
                    score = float(item.get("score", 0.0))
                    # Clamp score to [0.0, 1.0]
                    score = max(0.0, min(1.0, score))
                    item["score"] = score
                    results.append(item)
                return results
            return []
        except Exception as e:
            logger.error(f"Error during Supabase vector search: {e}")
            return []

    def delete_video(self, video_id: str) -> bool:
        try:
            # 1. Delete chunks for video
            self.delete_chunks_for_video(video_id)
            # 2. Delete the video row
            self.client.table("videos").delete().eq("id", video_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting video {video_id}: {e}")
            raise e

    def delete_job(self, job_id: str) -> bool:
        try:
            self.client.table("jobs").delete().eq("id", job_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {e}")
            raise e

    def get_system_stats(self) -> Dict[str, int]:
        try:
            v_res = self.client.table("videos").select("id", count="exact").execute()
            total_videos = v_res.count if v_res.count is not None else len(v_res.data or [])
        except Exception:
            total_videos = 0

        try:
            c_res = self.client.table("chunks").select("id", count="exact").execute()
            total_chunks = c_res.count if c_res.count is not None else len(c_res.data or [])
        except Exception:
            total_chunks = 0

        try:
            j_res = self.client.table("jobs").select("id").eq("status", "processing").execute()
            active_jobs = len(j_res.data or [])
        except Exception:
            active_jobs = 0

        return {
            "total_videos": total_videos,
            "total_chunks": total_chunks,
            "active_jobs": active_jobs,
        }


def init_database() -> BaseDatabase:
    """
    Initializes the application database.
    
    Loud startup rule:
    - If LOCAL_DEV=true is explicitly set, ALWAYS uses InMemoryDatabase (for local offline dev and isolated test suites).
    - If LOCAL_DEV != 'true': requires valid SUPABASE_URL and SUPABASE_KEY to connect to Supabase.
    - If missing or connection fails and LOCAL_DEV != 'true', raises a loud RuntimeError.
    """
    local_dev = os.getenv("LOCAL_DEV", "").strip().lower() == "true"
    if local_dev:
        return InMemoryDatabase()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if supabase_url and supabase_key:
        return SupabaseDatabase(supabase_url=supabase_url, supabase_key=supabase_key)

    raise RuntimeError(
        "Supabase configuration missing (SUPABASE_URL and SUPABASE_KEY are not set). "
        "To run locally with in-memory storage for testing, set LOCAL_DEV=true in your environment. "
        "For production, please configure Supabase credentials."
    )
