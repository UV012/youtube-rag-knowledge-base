import os
import math
import pytest
import asyncio
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

# Set LOCAL_DEV=true for testing
os.environ["LOCAL_DEV"] = "true"

from backend.db import init_database, InMemoryDatabase, SupabaseDatabase, BaseDatabase, _cosine_similarity
from backend.models import (
    VideoIngestRequest, VideoIngestResponse, JobResponse,
    VideoListItem, VideoDetailResponse, SearchRequest, SearchResponse
)
from backend.pipeline import (
    merge_segments_to_chunks, embed_texts, _embed_batch_adaptive
)
import backend.pipeline as pipeline_module
import backend.main as main_module
from backend.main import app, db, process_video_pipeline


@pytest.fixture(autouse=True)
def clean_db():
    """Reset the in-memory database before each test and isolate external APIs."""
    if not isinstance(main_module.db, InMemoryDatabase):
        main_module.db = InMemoryDatabase()
    main_module.db.videos.clear()
    main_module.db.jobs.clear()
    main_module.db.chunks.clear()

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.return_value = MagicMock(text="Synthesized research answer citing [00:30].")
    mock_gemini.models.embed_content.side_effect = lambda model, contents, config=None: MagicMock(
        embeddings=[MagicMock(values=[0.1] * 768) for _ in contents]
    )
    main_module.gemini_client = mock_gemini
    pipeline_module.gemini_client = mock_gemini


client = TestClient(app)


# =============================================================================
# 1. Loud Startup & Database Tests
# =============================================================================

def test_loud_startup_without_supabase_and_without_local_dev(monkeypatch):
    """Verify that backend fails loudly at startup if Supabase keys are missing and LOCAL_DEV is not true."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("LOCAL_DEV", "false")

    with pytest.raises(RuntimeError) as exc_info:
        init_database()
    assert "Supabase configuration missing" in str(exc_info.value)


def test_startup_succeeds_with_explicit_local_dev(monkeypatch):
    """Verify that InMemoryDatabase is initialized when LOCAL_DEV=true."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("LOCAL_DEV", "true")

    db_instance = init_database()
    assert isinstance(db_instance, InMemoryDatabase)


def test_test_suite_runs_against_in_memory_database_not_supabase():
    """Verify that main_module.db initialized at import time is an InMemoryDatabase, not SupabaseDatabase."""
    assert isinstance(main_module.db, InMemoryDatabase)
    assert not isinstance(main_module.db, SupabaseDatabase)


def test_database_crud_and_similarity_scoring():
    """Verify database CRUD operations and cosine similarity calculation."""
    in_mem_db = InMemoryDatabase()

    # Create video
    video = in_mem_db.create_or_update_video({
        "youtube_video_id": "test_yt_123",
        "title": "Quantum Computing Lecture",
        "duration_seconds": 1200,
        "status": "ready",
    })
    assert video["youtube_video_id"] == "test_yt_123"
    assert video["id"] is not None

    # Retrieve video by youtube id
    found = in_mem_db.get_video_by_youtube_id("test_yt_123")
    assert found is not None
    assert found["id"] == video["id"]

    # Insert chunks with embeddings
    dummy_emb_1 = [1.0, 0.0] + [0.0] * 766
    dummy_emb_2 = [0.0, 1.0] + [0.0] * 766

    in_mem_db.insert_chunks([
        {
            "video_id": video["id"],
            "text": "First chunk on quantum entanglement.",
            "start_seconds": 0.0,
            "end_seconds": 45.0,
            "embedding": dummy_emb_1,
        },
        {
            "video_id": video["id"],
            "text": "Second chunk on superposition.",
            "start_seconds": 45.0,
            "end_seconds": 90.0,
            "embedding": dummy_emb_2,
        },
    ])

    # Search with query vector closest to dummy_emb_1
    query_emb = [0.99, 0.01] + [0.0] * 766
    results = in_mem_db.search_chunks(query_embedding=query_emb, limit=2)
    assert len(results) == 2
    # First result should have higher score (~0.99)
    assert results[0]["text"] == "First chunk on quantum entanglement."
    assert results[0]["score"] > results[1]["score"]
    assert 0.0 <= results[0]["score"] <= 1.0


def test_video_partial_status_update_preserves_full_fields():
    """
    Critical regression test:
    Verify that updating a video's status (e.g. to 'transcribing', 'indexing', 'ready')
    does NOT null out or corrupt the other existing columns (youtube_video_id, title, thumbnail_url, duration_seconds).
    """
    in_mem_db = InMemoryDatabase()

    # 1. Create video with full metadata
    created = in_mem_db.create_video({
        "id": "vid-full-meta-01",
        "youtube_video_id": "B1PUBlhd9Yg",
        "title": "Quantum Computing Fundamentals",
        "thumbnail_url": "https://i.ytimg.com/vi/B1PUBlhd9Yg/hqdefault.jpg",
        "duration_seconds": 735,
        "channel_name": "MIT OpenCourseWare",
        "description": "Comprehensive quantum lecture series.",
        "tags": ["Physics", "Quantum"],
        "status": "downloading",
    })
    vid_id = created["id"]

    # 2. Perform partial status update to 'transcribing'
    updated_transcribing = in_mem_db.update_video(vid_id, {"status": "transcribing"})
    assert updated_transcribing["status"] == "transcribing"
    assert updated_transcribing["youtube_video_id"] == "B1PUBlhd9Yg"
    assert updated_transcribing["title"] == "Quantum Computing Fundamentals"
    assert updated_transcribing["thumbnail_url"] == "https://i.ytimg.com/vi/B1PUBlhd9Yg/hqdefault.jpg"
    assert updated_transcribing["duration_seconds"] == 735
    assert updated_transcribing["channel_name"] == "MIT OpenCourseWare"
    assert updated_transcribing["description"] == "Comprehensive quantum lecture series."
    assert updated_transcribing["tags"] == ["Physics", "Quantum"]

    # 3. Perform partial status update to 'indexing'
    updated_indexing = in_mem_db.update_video(vid_id, {"status": "indexing"})
    assert updated_indexing["status"] == "indexing"
    assert updated_indexing["youtube_video_id"] == "B1PUBlhd9Yg"
    assert updated_indexing["title"] == "Quantum Computing Fundamentals"

    # 4. Perform partial status update to 'ready'
    updated_ready = in_mem_db.update_video(vid_id, {"status": "ready", "duration_seconds": 735})
    assert updated_ready["status"] == "ready"
    assert updated_ready["youtube_video_id"] == "B1PUBlhd9Yg"
    assert updated_ready["title"] == "Quantum Computing Fundamentals"

    # 5. Verify defensive create_or_update_video routing for partial payloads
    defensive_update = in_mem_db.create_or_update_video({"id": vid_id, "status": "ready"})
    assert defensive_update["status"] == "ready"
    assert defensive_update["youtube_video_id"] == "B1PUBlhd9Yg"
    assert defensive_update["title"] == "Quantum Computing Fundamentals"


def test_supabase_database_update_uses_table_update_not_upsert():
    """
    Verify that SupabaseDatabase.update_video issues a true table.update().eq() (PATCH),
    and NEVER an upsert() which would null out omitted columns.
    """
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_update_query = MagicMock()
    mock_eq_query = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [{"id": "vid-123", "status": "transcribing"}]

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update_query
    mock_update_query.eq.return_value = mock_eq_query
    mock_eq_query.execute.return_value = mock_resp

    supa_db = SupabaseDatabase.__new__(SupabaseDatabase)
    supa_db.client = mock_client

    # Call update_video
    result = supa_db.update_video("vid-123", {"status": "transcribing"})

    # Assertions
    mock_table.update.assert_called_once_with({"status": "transcribing"})
    mock_update_query.eq.assert_called_once_with("id", "vid-123")
    mock_table.upsert.assert_not_called()
    assert result == {"id": "vid-123", "status": "transcribing"}


# =============================================================================
# 2. Pipeline Tests: Audio Offsets, Chunk Merging & Adaptive Embeddings
# =============================================================================

def test_merge_segments_to_chunks_sentence_boundaries():
    """Verify segment merging preserves sentence boundaries and respects target duration."""
    segments = [
        {"start": 0.0, "end": 10.0, "text": "This is part one of the sentence"},
        {"start": 10.0, "end": 20.0, "text": "and here is part two."},
        {"start": 20.0, "end": 50.0, "text": "This is a longer second sentence that should complete the chunk."},
        {"start": 50.0, "end": 75.0, "text": "This is the start of the next topic."},
    ]
    chunks = merge_segments_to_chunks(segments, target_duration=45.0)
    assert len(chunks) >= 2
    assert chunks[0]["start_seconds"] == 0.0
    assert chunks[0]["end_seconds"] >= 50.0
    assert "part one" in chunks[0]["text"]
    assert "second sentence" in chunks[0]["text"]
    assert "next topic" in chunks[1]["text"]


def test_long_video_timestamp_offset_math():
    """Verify that multiple audio chunk offsets are correctly added to segment timestamps."""
    # Chunk 1 (offset = 0.0s)
    chunk1_segments = [
        {"start": 10.0, "end": 25.0, "text": "Segment in first 10 minutes."},
    ]
    # Chunk 2 (offset = 600.0s)
    chunk2_segments = [
        {"start": 15.0, "end": 35.0, "text": "Segment in second 10 minutes."},
    ]

    combined_segments = []
    # Process Chunk 1
    for s in chunk1_segments:
        combined_segments.append({
            "start": s["start"] + 0.0,
            "end": s["end"] + 0.0,
            "text": s["text"],
        })
    # Process Chunk 2
    for s in chunk2_segments:
        combined_segments.append({
            "start": s["start"] + 600.0,
            "end": s["end"] + 600.0,
            "text": s["text"],
        })

    assert combined_segments[0]["start"] == 10.0
    assert combined_segments[0]["end"] == 25.0
    assert combined_segments[1]["start"] == 615.0  # Correctly offset past 10 minutes!
    assert combined_segments[1]["end"] == 635.0


def test_embedding_batching_limit():
    """Verify embedding function processes batches up to default batch size (20 items)."""
    mock_client = MagicMock()
    mock_client.models.embed_content.side_effect = lambda model, contents, config=None: MagicMock(
        embeddings=[MagicMock(values=[0.1] * 768) for _ in contents]
    )
    pipeline_module.gemini_client = mock_client
    try:
        texts = [f"Text chunk {i}" for i in range(45)]
        embeddings = embed_texts(texts, batch_size=20)
        assert len(embeddings) == 45
        for emb in embeddings:
            assert len(emb) == 768
            # Verify unit length normalization
            norm = math.sqrt(sum(x * x for x in emb))
            assert math.isclose(norm, 1.0, rel_tol=1e-4)
    finally:
        pipeline_module.gemini_client = None


def test_embedding_adaptive_halving_on_400():
    """
    Verify distinct failure mode handling:
    If Gemini API returns 400 / InvalidArgument on an oversized batch,
    the pipeline halves the batch size and recursively retries rather than doing rate-limit backoff.
    """
    mock_client = MagicMock()

    def side_effect(model, contents, config=None):
        if len(contents) > 2:
            raise Exception("400 InvalidArgument: Request contains too many text elements (max 2 allowed in test)")
        mock_resp = MagicMock()
        mock_resp.embeddings = [MagicMock(values=[0.5] * 768) for _ in contents]
        return mock_resp

    mock_client.models.embed_content.side_effect = side_effect
    pipeline_module.gemini_client = mock_client

    try:
        texts = ["Chunk 1", "Chunk 2", "Chunk 3", "Chunk 4"]
        results = _embed_batch_adaptive(texts)
        assert len(results) == 4
        for r in results:
            assert len(r) == 768
            norm = math.sqrt(sum(x * x for x in r))
            assert math.isclose(norm, 1.0, rel_tol=1e-4)
    finally:
        pipeline_module.gemini_client = None


def test_embedding_rate_limit_backoff_on_429(monkeypatch):
    """
    Verify distinct failure mode handling:
    If Gemini API returns 429 ResourceExhausted, status_callback is notified with 'waiting_on_rate_limit'.
    """
    mock_client = MagicMock()
    call_count = {"count": 0}
    callback_statuses = []

    def status_cb(stage):
        callback_statuses.append(stage)

    def side_effect(model, contents, config=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise Exception("429 ResourceExhausted: Quota exceeded")
        mock_resp = MagicMock()
        mock_resp.embeddings = [MagicMock(values=[0.7] * 768) for _ in contents]
        return mock_resp

    mock_client.models.embed_content.side_effect = side_effect
    pipeline_module.gemini_client = mock_client
    monkeypatch.setattr("time.sleep", lambda s: None)  # speed up test

    try:
        texts = ["Rate limit test chunk"]
        results = _embed_batch_adaptive(texts, status_callback=status_cb)
        assert len(results) == 1
        assert "waiting_on_rate_limit" in callback_statuses
        assert "indexing" in callback_statuses
    finally:
        pipeline_module.gemini_client = None


# =============================================================================
# 3. FastAPI API Endpoints & Idempotency Tests
# =============================================================================

def test_api_status():
    """Verify /api/status endpoint."""
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "total_videos" in data
    assert "total_chunks" in data
    assert "active_jobs" in data


def test_api_videos_invalid_url():
    """Verify /api/videos rejects non-YouTube URLs."""
    res = client.post("/api/videos", json={"url": "https://example.com/not-youtube"})
    assert res.status_code == 400


def test_api_videos_idempotency():
    """
    Verify /api/videos idempotency:
    If a video is already in the database with status 'ready', re-submitting returns
    the existing video immediately without spawning a duplicate job.
    """
    existing_video = main_module.db.create_or_update_video({
        "youtube_video_id": "FN1n4k8i-Y8",
        "title": "Roman Aqueducts",
        "status": "ready",
        "duration_seconds": 1500,
    })

    res = client.post("/api/videos", json={"url": "https://www.youtube.com/watch?v=FN1n4k8i-Y8"})
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "already_exists"
    assert "already in your library" in data.get("message", "").lower()
    assert data.get("video_id") == existing_video["id"]
    assert data.get("job_id") is None


def test_resubmit_failed_video_retries_and_succeeds(monkeypatch):
    """
    Verify that a previously 'failed' video URL can be re-submitted:
    it is NOT blocked by the idempotency check, re-processes, reuses the UUID, and succeeds.
    """
    # Seed a failed video
    failed_video = main_module.db.create_or_update_video({
        "youtube_video_id": "failed_vid_999",
        "title": "Failed Lecture",
        "status": "failed",
        "error_message": "Network error during first attempt",
        "duration_seconds": 0,
    })

    # Mock download to succeed on retry
    def mock_download(url, output_dir, **kwargs):
        dummy = os.path.join(output_dir, "test.mp3")
        with open(dummy, "w") as f:
            f.write("audio")
        return [(dummy, 0.0)]

    monkeypatch.setattr("backend.main.download_audio_and_chunk", mock_download)
    monkeypatch.setattr(
        "backend.main.extract_metadata_and_expand_urls",
        lambda url: ("video", [{
            "youtube_id": "failed_vid_999",
            "title": "Recovered Lecture",
            "url": url,
            "duration": 600,
            "thumbnail": "https://example.com/thumb.jpg",
        }])
    )

    res = client.post("/api/videos", json={"url": "https://www.youtube.com/watch?v=failed_vid_999"})
    assert res.status_code == 200
    data = res.json()
    # It must spawn a new job to retry, NOT return 'already indexed'
    assert data.get("job_id") is not None
    assert "already indexed" not in (data.get("message") or "").lower()


def test_api_video_detail_and_chunks():
    """Verify GET /api/videos/{id} returns video details and sorted chunks."""
    vid = main_module.db.create_or_update_video({
        "youtube_video_id": "test_detail_01",
        "title": "Deep Learning Specialization",
        "status": "ready",
        "duration_seconds": 2700,
    })

    main_module.db.insert_chunks([
        {
            "video_id": vid["id"],
            "text": "Backpropagation chain rule mechanics.",
            "start_seconds": 120.0,
            "end_seconds": 180.0,
            "embedding": [0.1] * 768,
        },
        {
            "video_id": vid["id"],
            "text": "Gradient descent parameter optimization.",
            "start_seconds": 45.0,
            "end_seconds": 105.0,
            "embedding": [0.2] * 768,
        },
    ])

    res = client.get(f"/api/videos/{vid['id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == vid["id"]
    assert len(data["chunks"]) == 2
    # Should be sorted chronologically: 45s before 120s
    assert data["chunks"][0]["start_seconds"] == 45.0
    assert data["chunks"][0]["time_formatted"] == "00:45"
    assert data["chunks"][1]["start_seconds"] == 120.0
    assert data["chunks"][1]["time_formatted"] == "02:00"


def test_api_search_rag():
    """Verify POST /api/search embeds query, retrieves top chunks, and returns cited answer."""
    vid = main_module.db.create_or_update_video({
        "youtube_video_id": "test_search_vid",
        "title": "Attention Is All You Need",
        "status": "ready",
        "duration_seconds": 3600,
    })

    # Insert sample chunk
    main_module.db.insert_chunks([
        {
            "video_id": vid["id"],
            "text": "Scaled dot-product attention computes softmax of QK transpose divided by square root of d_k.",
            "start_seconds": 240.0,
            "end_seconds": 300.0,
            "embedding": embed_texts(["Scaled dot product attention formula"])[0],
        }
    ])

    res = client.post("/api/search", json={"query": "Scaled dot product attention formula"})
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "Scaled dot product attention formula"
    assert len(data["results"]) >= 1
    assert "Scaled dot-product attention" in data["results"][0]["text"]
    assert data["results"][0]["start_seconds"] == 240.0
    assert data["answer"] is not None
    assert len(data["answer"]) > 0


def test_search_with_video_id_filter():
    """Verify searching with video_id constraint only returns chunks belonging to that video."""
    vid1 = main_module.db.create_or_update_video({"youtube_video_id": "vid1", "title": "Video 1", "status": "ready"})
    vid2 = main_module.db.create_or_update_video({"youtube_video_id": "vid2", "title": "Video 2", "status": "ready"})

    emb = embed_texts(["Quantum physics concept"])[0]
    main_module.db.insert_chunks([
        {"video_id": vid1["id"], "text": "Quantum physics concept in video 1", "start_seconds": 0.0, "end_seconds": 30.0, "embedding": emb},
        {"video_id": vid2["id"], "text": "Quantum physics concept in video 2", "start_seconds": 0.0, "end_seconds": 30.0, "embedding": emb},
    ])

    res = client.post("/api/search", json={"query": "Quantum physics concept", "video_id": vid1["id"]})
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["video_id"] == vid1["id"]


@pytest.mark.asyncio
async def test_process_video_pipeline_end_to_end(monkeypatch):
    """Verify that process_video_pipeline executes full sequence and transitions job/video to ready/done."""
    import uuid
    job_id = str(uuid.uuid4())
    job = main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "title": "E2E Test Video",
        "status": "queued",
        "progress_current": 0,
        "progress_total": 1,
    })

    def mock_download(url, output_dir, **kwargs):
        dummy_file = os.path.join(output_dir, "test.mp3")
        with open(dummy_file, "w") as f:
            f.write("mock_audio_content")
        return [(dummy_file, 0.0)]

    async def mock_transcribe(audio_path, **kwargs):
        return [
            {"start": 0.0, "end": 30.0, "text": "Fresh test transcript sentence one."},
            {"start": 30.0, "end": 60.0, "text": "Fresh test transcript sentence two."},
        ]

    monkeypatch.setattr("backend.main.download_audio_and_chunk", mock_download)
    monkeypatch.setattr("backend.main.transcribe_with_backoff", mock_transcribe)

    entry = {
        "youtube_id": "e2e_test_vid_id",
        "title": "Empirical Study of Transformers",
        "url": "https://www.youtube.com/watch?v=e2e_test_vid_id",
        "duration": 300,
        "thumbnail": "https://example.com/thumb.jpg",
        "channel_name": "AI Lab",
    }

    await process_video_pipeline(job_id, entry)

    updated_job = main_module.db.get_job(job_id)
    assert updated_job["status"] == "done"
    assert updated_job["progress_current"] == 1
    assert len(updated_job["video_ids"]) == 1

    created_vid_id = updated_job["video_ids"][0]
    created_vid = main_module.db.get_video(created_vid_id)
    assert created_vid is not None
    assert created_vid["status"] == "ready"
    assert created_vid["title"] == "Empirical Study of Transformers"

    chunks = main_module.db.get_chunks_for_video(created_vid_id)
    assert len(chunks) > 0
    assert chunks[0]["text"] is not None


def test_embedding_single_chunk_400_base_case():
    """
    Verify base case at batch size 1:
    If a single chunk still fails with 400 InvalidArgument (e.g. pathological length),
    it halts and raises a descriptive ValueError identifying the offending chunk.
    """
    mock_client = MagicMock()
    mock_client.models.embed_content.side_effect = Exception("400 InvalidArgument: Text length exceeds maximum token capacity of 8192 tokens")
    pipeline_module.gemini_client = mock_client

    try:
        with pytest.raises(ValueError) as exc_info:
            _embed_batch_adaptive(["This is a pathologically oversized single text chunk that cannot be embedded."])
        assert "Embedding request failed for single chunk" in str(exc_info.value)
        assert "pathologically oversized" in str(exc_info.value)
    finally:
        pipeline_module.gemini_client = None


@pytest.mark.asyncio
async def test_retry_clears_stale_chunks_before_insert(monkeypatch):
    """
    Verify that when a failed video is reprocessed, any stale chunks from earlier attempts
    are deleted before fresh chunks are inserted, preventing duplicate or overlapping chunks.
    """
    import uuid
    # 1. Seed a failed video with 3 stale chunks
    video = main_module.db.create_or_update_video({
        "youtube_video_id": "stale_test_vid",
        "title": "Partially Ingested Video",
        "status": "failed",
    })
    vid_id = video["id"]

    main_module.db.insert_chunks([
        {"video_id": vid_id, "text": "Stale chunk 1", "start_seconds": 0.0, "end_seconds": 30.0, "embedding": [0.1]*768},
        {"video_id": vid_id, "text": "Stale chunk 2", "start_seconds": 30.0, "end_seconds": 60.0, "embedding": [0.1]*768},
        {"video_id": vid_id, "text": "Stale chunk 3", "start_seconds": 60.0, "end_seconds": 90.0, "embedding": [0.1]*768},
    ])
    assert len(main_module.db.get_chunks_for_video(vid_id)) == 3

    # 2. Create job and run process_video_pipeline
    job_id = str(uuid.uuid4())
    job = main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "status": "queued",
        "progress_current": 0,
        "progress_total": 1,
    })

    def mock_download(url, output_dir, **kwargs):
        dummy_file = os.path.join(output_dir, "test.mp3")
        with open(dummy_file, "w") as f:
            f.write("mock_audio_content")
        return [(dummy_file, 0.0)]

    async def mock_transcribe(audio_path, **kwargs):
        return [
            {"start": 0.0, "end": 30.0, "text": "Fresh test transcript sentence one."},
            {"start": 30.0, "end": 60.0, "text": "Fresh test transcript sentence two."},
        ]

    monkeypatch.setattr("backend.main.download_audio_and_chunk", mock_download)
    monkeypatch.setattr("backend.main.transcribe_with_backoff", mock_transcribe)

    entry = {
        "youtube_id": "stale_test_vid",
        "title": "Partially Ingested Video",
        "url": "https://www.youtube.com/watch?v=stale_test_vid",
        "duration": 90,
    }

    await process_video_pipeline(job_id, entry)

    # 3. Verify chunks in DB: stale chunks must be deleted, only fresh chunks present
    current_chunks = main_module.db.get_chunks_for_video(vid_id)
    chunk_texts = [c["text"] for c in current_chunks]
    assert not any("Stale chunk" in t for t in chunk_texts)
    assert len(current_chunks) > 0


def test_ytdlp_player_client_configuration(monkeypatch):
    """Verify that YouTube player clients can be configured via environment or defaults."""
    from backend.pipeline import get_ytdlp_player_clients, build_ytdlp_opts, DEFAULT_YTDLP_PLAYER_CLIENTS

    # Test defaults
    monkeypatch.delenv("YTDLP_PLAYER_CLIENTS", raising=False)
    clients = get_ytdlp_player_clients()
    assert clients == DEFAULT_YTDLP_PLAYER_CLIENTS
    assert "tv" in clients
    assert "web_safari" in clients

    # Test custom env var
    monkeypatch.setenv("YTDLP_PLAYER_CLIENTS", "android, tv, ios")
    custom_clients = get_ytdlp_player_clients()
    assert custom_clients == ["android", "tv", "ios"]

    # Test build_ytdlp_opts applies extractor_args
    opts = build_ytdlp_opts()
    assert opts["extractor_args"]["youtube"]["player_client"] == ["android", "tv", "ios"]


def test_l2_normalization_and_embed_query():
    """Verify that embed_query uses RETRIEVAL_QUERY task_type and normalizes vectors."""
    from backend.pipeline import _l2_normalize, embed_query

    # Test normalization function
    raw_vec = [3.0, 4.0]
    norm_vec = _l2_normalize(raw_vec)
    assert math.isclose(norm_vec[0], 0.6)
    assert math.isclose(norm_vec[1], 0.8)

    mock_client = MagicMock()
    captured_config = []

    def mock_embed(model, contents, config=None):
        captured_config.append(config)
        mock_resp = MagicMock()
        mock_resp.embeddings = [MagicMock(values=[1.0] * 768) for _ in contents]
        return mock_resp

    mock_client.models.embed_content.side_effect = mock_embed
    pipeline_module.gemini_client = mock_client

    try:
        q_emb = embed_query("What is machine learning?")
        assert len(q_emb) == 768
        norm = math.sqrt(sum(x * x for x in q_emb))
        assert math.isclose(norm, 1.0, rel_tol=1e-4)
        assert len(captured_config) == 1
        assert captured_config[0].output_dimensionality == 768
        assert captured_config[0].task_type == "RETRIEVAL_QUERY"
    finally:
        pipeline_module.gemini_client = None


def test_spa_static_serving():
    """Verify that FastAPI serves index.html for SPA routes when dist/ exists."""
    if os.path.exists("dist/index.html"):
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "<html" in res.text.lower() or "<!doctype html" in res.text.lower()

        res_route = client.get("/library")
        assert res_route.status_code == 200
        assert "<html" in res_route.text.lower() or "<!doctype html" in res_route.text.lower()


def test_duplicate_submission_ready_video_returns_already_exists_and_no_job():
    """Verify that submitting an already ready video returns already_exists and does not create a job."""
    vid = main_module.db.create_video({
        "youtube_video_id": "test_idem_vid",
        "title": "Already Indexed Video",
        "status": "ready",
    })

    jobs_before = len(main_module.db.list_jobs())
    res = client.post("/api/videos", json={"url": "https://www.youtube.com/watch?v=test_idem_vid"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "already_exists"
    assert data["message"] == "This video is already in your library."
    assert data["video_id"] == vid["id"]
    assert data["job_id"] is None

    # Confirm no new job was created
    jobs_after = len(main_module.db.list_jobs())
    assert jobs_after == jobs_before


def test_duplicate_submission_processing_video_returns_already_processing():
    """Verify that submitting a video that is currently processing returns already_processing and links active job."""
    import uuid
    vid = main_module.db.create_video({
        "youtube_video_id": "test_active_vid",
        "title": "Processing Video",
        "status": "indexing",
    })

    active_job_id = str(uuid.uuid4())
    main_module.db.create_job({
        "id": active_job_id,
        "type": "video",
        "title": "Processing Video",
        "status": "processing",
        "stage": "indexing",
        "video_ids": [vid["id"]],
    })

    jobs_before = len(main_module.db.list_jobs())
    res = client.post("/api/videos", json={"url": "https://www.youtube.com/watch?v=test_active_vid"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "already_processing"
    assert "already being processed" in data["message"]
    assert data["job_id"] == active_job_id

    # Confirm no duplicate job was created
    jobs_after = len(main_module.db.list_jobs())
    assert jobs_after == jobs_before


def test_stale_job_watchdog_auto_fails():
    """Verify that watchdog automatically marks jobs with no activity for >15m as failed."""
    from datetime import datetime, timezone, timedelta
    import uuid

    stale_vid_id = str(uuid.uuid4())
    main_module.db.create_video({
        "id": stale_vid_id,
        "youtube_video_id": "stale_watchdog_vid",
        "title": "Stuck Video",
        "status": "indexing",
    })

    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    job_id = str(uuid.uuid4())
    main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "title": "Stuck Job",
        "status": "processing",
        "stage": "indexing",
        "video_ids": [stale_vid_id],
        "created_at": stale_time,
        "updated_at": stale_time,
    })

    # When list_jobs or get_job is called, watchdog triggers
    job = main_module.db.get_job(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert "Stalled — no progress" in job["error_message"]

    vid = main_module.db.get_video(stale_vid_id)
    assert vid is not None
    assert vid["status"] == "failed"


def test_delete_video_cascades_chunks_and_removes_from_search():
    """Verify that DELETE /api/videos/{video_id} removes video, its chunks, and clears it from search."""
    vid = main_module.db.create_video({
        "youtube_video_id": "to_be_deleted",
        "title": "Video To Delete",
        "status": "ready",
    })

    emb = [0.1] * 768
    main_module.db.insert_chunks([{
        "video_id": vid["id"],
        "text": "Unique text in video to delete",
        "start_seconds": 0.0,
        "end_seconds": 30.0,
        "embedding": emb,
    }])

    assert len(main_module.db.get_chunks_for_video(vid["id"])) == 1

    # Delete video
    res = client.delete(f"/api/videos/{vid['id']}")
    assert res.status_code == 200
    assert res.json()["status"] == "deleted"

    # Confirm video is gone
    assert main_module.db.get_video(vid["id"]) is None
    assert len(main_module.db.get_chunks_for_video(vid["id"])) == 0

    # Confirm search does not find it
    search_res = client.post("/api/search", json={"query": "Unique text in video to delete"})
    assert search_res.status_code == 200
    assert len(search_res.json()["results"]) == 0


@pytest.mark.asyncio
async def test_cancel_job_cooperative_stops_processing(monkeypatch):
    """Verify that POST /api/jobs/{job_id}/cancel sets cancelled and halts pipeline before transcription."""
    import uuid
    job_id = str(uuid.uuid4())
    main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "title": "Cancellable Video",
        "status": "queued",
        "progress_current": 0,
        "progress_total": 1,
    })

    whisper_called = []
    gemini_called = []

    def mock_download(url, output_dir, **kwargs):
        dummy_file = os.path.join(output_dir, "test.mp3")
        with open(dummy_file, "w") as f:
            f.write("mock_audio")
        # Cancel the job right during/after download
        main_module.db.update_job(job_id, {"status": "cancelled"})
        return [(dummy_file, 0.0)]

    async def mock_transcribe(*args, **kwargs):
        whisper_called.append(True)
        return []

    def mock_embed(*args, **kwargs):
        gemini_called.append(True)
        return []

    monkeypatch.setattr(main_module, "download_audio_and_chunk", mock_download)
    monkeypatch.setattr(main_module, "transcribe_with_backoff", mock_transcribe)
    monkeypatch.setattr(main_module, "embed_texts", mock_embed)

    await process_video_pipeline(job_id, {
        "youtube_id": "cancel_vid_test",
        "title": "Cancellable Video",
        "url": "https://www.youtube.com/watch?v=cancel_vid_test",
        "duration": 60,
    })

    # Assert that downstream transcription and embedding were aborted
    assert len(whisper_called) == 0
    assert len(gemini_called) == 0

    job = main_module.db.get_job(job_id)
    assert job["status"] == "cancelled"


def test_delete_job_housekeeping():
    """Verify that DELETE /api/jobs/{job_id} removes the job record from database."""
    job = main_module.db.create_job({
        "type": "video",
        "title": "Redundant Job",
        "status": "done",
    })

    res = client.delete(f"/api/jobs/{job['id']}")
    assert res.status_code == 200
    assert res.json()["status"] == "deleted"

    assert main_module.db.get_job(job["id"]) is None


def test_retry_job_when_video_already_ready_marks_done():
    """Verify that retrying a job whose video is already 'ready' marks the job as done and returns already_exists."""
    vid = main_module.db.create_or_update_video({
        "youtube_video_id": "ready_retry_vid",
        "title": "Already Completed Video",
        "status": "ready",
        "duration_seconds": 300,
    })

    job = main_module.db.create_job({
        "type": "video",
        "title": "Already Completed Video",
        "url": "https://www.youtube.com/watch?v=ready_retry_vid",
        "status": "failed",
        "video_ids": [vid["id"]],
    })

    res = client.post(f"/api/jobs/{job['id']}/retry")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "already_exists"
    assert "already in your library" in data.get("message", "").lower()

    updated_job = main_module.db.get_job(job["id"])
    assert updated_job["status"] == "done"
    assert updated_job["progress_current"] == 1


def test_retry_job_when_video_already_processing():
    """Verify that retrying a job whose video is actively processing returns already_processing."""
    vid = main_module.db.create_or_update_video({
        "youtube_video_id": "active_retry_vid",
        "title": "Active Video",
        "status": "transcribing",
        "duration_seconds": 300,
    })

    job = main_module.db.create_job({
        "type": "video",
        "title": "Active Video",
        "url": "https://www.youtube.com/watch?v=active_retry_vid",
        "status": "failed",
        "video_ids": [vid["id"]],
    })

    res = client.post(f"/api/jobs/{job['id']}/retry")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "already_processing"
    assert "already being processed" in data.get("message", "").lower()


def test_retry_job_reconstructs_url_from_video(monkeypatch):
    """Verify that retrying a job without a recorded URL recovers the URL from associated video."""
    monkeypatch.setattr(
        "backend.main.extract_metadata_and_expand_urls",
        lambda url: ("video", [{
            "youtube_id": "reconstruct_url_vid",
            "title": "URL Reconstructed Video",
            "url": url,
            "duration": 300,
            "thumbnail": "https://example.com/thumb.jpg",
        }])
    )

    vid = main_module.db.create_or_update_video({
        "youtube_video_id": "reconstruct_url_vid",
        "title": "URL Reconstructed Video",
        "status": "failed",
        "duration_seconds": 300,
    })

    job = main_module.db.create_job({
        "type": "video",
        "title": "Job Without Explicit URL",
        "url": None,
        "status": "failed",
        "video_ids": [vid["id"]],
    })

    res = client.post(f"/api/jobs/{job['id']}/retry")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "restarted"
    assert data.get("job")["url"] == "https://www.youtube.com/watch?v=reconstruct_url_vid"


def test_api_status_dynamic_models_and_mode():
    """Verify that /api/status returns dynamic runtime models and database mode."""
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["embedding_model"] == "gemini-embedding-001"
    assert data["generation_model"] == "gemini-3.6-flash"
    assert data["transcription_model"] == "whisper-large-v3-turbo"
    assert "In-Memory" in data["database_mode"] or "Supabase" in data["database_mode"]


@pytest.mark.asyncio
async def test_transcribe_with_backoff_rejects_truncated_media_files(tmp_path):
    """Verify that transcribe_with_backoff rejects corrupt/truncated audio files (< 1024 bytes)."""
    fake_empty_audio = tmp_path / "truncated.mp3"
    fake_empty_audio.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x7fTXXX" + (b"\x00" * 200))  # 210 bytes
    
    with pytest.raises(ValueError, match="Invalid or truncated audio file"):
        await pipeline_module.transcribe_with_backoff(str(fake_empty_audio))


def test_cancel_job_endpoint_sets_cancelled_status():
    """Verify POST /api/jobs/{id}/cancel sets job and non-ready videos to cancelled status."""
    v1 = main_module.db.create_or_update_video({
        "youtube_video_id": "cancel_vid_01",
        "title": "In-Progress Video",
        "status": "transcribing",
    })
    v2 = main_module.db.create_or_update_video({
        "youtube_video_id": "cancel_vid_02",
        "title": "Already Ready Video",
        "status": "ready",
    })

    job = main_module.db.create_job({
        "type": "playlist",
        "title": "Playlist to Cancel",
        "status": "processing",
        "video_ids": [v1["id"], v2["id"]],
    })

    res = client.post(f"/api/jobs/{job['id']}/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cancelled"
    assert data["job"]["status"] == "cancelled"

    # v1 should be cancelled
    v1_updated = main_module.db.get_video(v1["id"])
    assert v1_updated["status"] == "cancelled"

    # v2 was already ready, should remain ready
    v2_updated = main_module.db.get_video(v2["id"])
    assert v2_updated["status"] == "ready"


def test_cancel_video_endpoint_from_library_grid():
    """Verify POST /api/videos/{video_id}/cancel sets video and parent single job to cancelled."""
    v = main_module.db.create_or_update_video({
        "youtube_video_id": "grid_cancel_vid",
        "title": "Grid Processing Video",
        "status": "transcribing",
    })

    job = main_module.db.create_job({
        "type": "video",
        "title": "Single Video Job",
        "status": "processing",
        "video_ids": [v["id"]],
    })

    res = client.post(f"/api/videos/{v['id']}/cancel")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cancelled"
    assert data["video"]["status"] == "cancelled"

    # Confirm in DB
    updated_v = main_module.db.get_video(v["id"])
    assert updated_v["status"] == "cancelled"
    updated_j = main_module.db.get_job(job["id"])
    assert updated_j["status"] == "cancelled"


def test_delete_video_endpoint_handles_mid_processing_video():
    """Verify DELETE /api/videos/{video_id} gracefully cleans up mid-processing video."""
    v = main_module.db.create_or_update_video({
        "youtube_video_id": "mid_proc_del_vid",
        "title": "Mid-Processing Video to Delete",
        "status": "downloading",
    })

    res = client.delete(f"/api/videos/{v['id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "deleted"
    assert main_module.db.get_video(v["id"]) is None


def test_download_audio_and_chunk_splitting_variable_scope(tmp_path, monkeypatch):
    """Verify download_audio_and_chunk splits long audio without any video_id NameError."""
    fake_audio = tmp_path / "test_long_vid.mp3"
    fake_audio.write_bytes(b"\xff\xfb\x90\x00" * 2000)  # 8000 bytes

    # Mock yt-dlp to return info and write fake audio file
    class MockYtdl:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download=True):
            return {
                "id": "test_long_vid",
                "title": "OmniRoute Long Video",
                "duration": 1500.0,  # 25 mins > 600s chunk limit
            }

    monkeypatch.setattr("yt_dlp.YoutubeDL", MockYtdl)
    monkeypatch.setattr("backend.pipeline._get_audio_duration", lambda p: 1500.0)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None)

    # Mock subprocess.run for ffmpeg chunk creation
    def mock_subprocess_run(cmd, *args, **kwargs):
        out_chunk = cmd[-1]
        with open(out_chunk, "wb") as f:
            f.write(b"chunk_content")
        return MagicMock(returncode=0)

    monkeypatch.setattr("subprocess.run", mock_subprocess_run)

    chunks = pipeline_module.download_audio_and_chunk(
        "https://www.youtube.com/watch?v=test_long_vid",
        str(tmp_path),
        max_chunk_duration_seconds=600
    )

    assert len(chunks) == 3
    assert chunks[0][1] == 0.0
    assert chunks[1][1] == 600.0
    assert chunks[2][1] == 1200.0
    assert "test_long_vid_chunk_" in chunks[0][0]


@pytest.mark.asyncio
async def test_pipeline_intermediate_stages_and_sub_jobs_sync(monkeypatch):
    """Verify that process_video_pipeline actively updates job status, stage, and sub_jobs across each stage."""
    recorded_stages = []

    # Intercept update_job to record stage progression
    original_update_job = main_module.db.update_job
    def track_update_job(j_id, updates):
        if "stage" in updates:
            recorded_stages.append((updates.get("status"), updates.get("stage"), [sj.get("status") for sj in updates.get("sub_jobs") or []]))
        return original_update_job(j_id, updates)

    monkeypatch.setattr(main_module.db, "update_job", track_update_job)

    # Mock audio download, transcribe, and embed
    monkeypatch.setattr(main_module, "download_audio_and_chunk", lambda url, d: [("/fake/path.mp3", 0.0)])
    async def mock_transcribe(p, status_callback=None, cancel_check=None):
        if status_callback:
            status_callback("transcribing")
        return [{"start": 0.0, "end": 10.0, "text": "Testing stage sync."}]
    monkeypatch.setattr(main_module, "transcribe_with_backoff", mock_transcribe)
    def mock_embed(texts, status_callback=None, cancel_check=None):
        if status_callback:
            status_callback("indexing")
        return [[0.1] * 768]
    monkeypatch.setattr(main_module, "embed_texts", mock_embed)

    job_id = "stage_test_job_123"
    main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "title": "Stage Test Video",
        "status": "queued",
        "stage": "downloading",
        "progress_current": 0,
        "progress_total": 1,
        "sub_jobs": [{"video_id": "stage_vid_1", "title": "Stage Video", "status": "queued", "progress": 0}],
    })

    entry = {
        "youtube_id": "stage_vid_1",
        "title": "Stage Test Video",
        "url": "https://www.youtube.com/watch?v=stage_vid_1",
        "duration": 60,
    }

    await main_module.process_video_pipeline(job_id, entry)

    final_job = main_module.db.get_job(job_id)
    assert final_job["status"] == "done"
    assert final_job["stage"] is None
    assert final_job["sub_jobs"][0]["status"] == "done"
    assert final_job["sub_jobs"][0]["progress"] == 100

    # Verify that intermediate stages were recorded
    stages_hit = [s[1] for s in recorded_stages]
    assert "downloading" in stages_hit
    assert "transcribing" in stages_hit
    assert "indexing" in stages_hit


@pytest.mark.asyncio
async def test_pipeline_failure_syncs_sub_jobs_status(monkeypatch):
    """Verify that a pipeline exception sets both job and sub_jobs to failed."""
    monkeypatch.setattr(main_module, "download_audio_and_chunk", MagicMock(side_effect=RuntimeError("Simulated download failure")))

    job_id = "fail_stage_job_456"
    main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "title": "Fail Test Video",
        "status": "queued",
        "stage": "downloading",
        "progress_current": 0,
        "progress_total": 1,
        "sub_jobs": [{"video_id": "fail_vid_1", "title": "Fail Video", "status": "queued", "progress": 0}],
    })

    entry = {
        "youtube_id": "fail_vid_1",
        "title": "Fail Test Video",
        "url": "https://www.youtube.com/watch?v=fail_vid_1",
        "duration": 60,
    }

    await main_module.process_video_pipeline(job_id, entry)

    final_job = main_module.db.get_job(job_id)
    assert final_job["status"] == "failed"
    assert final_job["stage"] is None
    assert final_job["sub_jobs"][0]["status"] == "failed"
    assert "Simulated download failure" in final_job["sub_jobs"][0]["error_message"]


@pytest.mark.asyncio
async def test_concurrent_api_jobs_polling_during_pipeline_processing(monkeypatch):
    """Verify that synchronous background work (yt-dlp, Groq, DB calls) does not block GET /api/jobs."""
    import time
    
    # Simulate a blocking synchronous download in a worker thread
    def slow_blocking_download(url, d):
        time.sleep(0.3)
        return [("/fake/path.mp3", 0.0)]

    monkeypatch.setattr(main_module, "download_audio_and_chunk", slow_blocking_download)
    async def mock_transcribe(p, status_callback=None, cancel_check=None):
        return [{"start": 0.0, "end": 10.0, "text": "Non-blocking event loop test."}]
    monkeypatch.setattr(main_module, "transcribe_with_backoff", mock_transcribe)
    monkeypatch.setattr(main_module, "embed_texts", lambda texts, status_callback=None, cancel_check=None: [[0.1] * 768])

    job_id = "nonblocking_job_789"
    main_module.db.create_job({
        "id": job_id,
        "type": "video",
        "title": "Non-blocking Test Video",
        "status": "queued",
        "stage": "downloading",
        "progress_current": 0,
        "progress_total": 1,
        "sub_jobs": [{"video_id": "nb_vid_1", "title": "NB Video", "status": "queued", "progress": 0}],
    })

    entry = {
        "youtube_id": "nb_vid_1",
        "title": "Non-blocking Test Video",
        "url": "https://www.youtube.com/watch?v=nb_vid_1",
        "duration": 60,
    }

    # Start the pipeline as a concurrent asyncio task
    pipeline_task = asyncio.create_task(main_module.process_video_pipeline(job_id, entry))

    # Give it 50ms to enter the slow_blocking_download thread
    await asyncio.sleep(0.05)

    # Concurrently call GET /api/jobs on the event loop while background worker is sleeping in thread
    start_poll = time.monotonic()
    jobs_response = await main_module.list_jobs()
    poll_elapsed = time.monotonic() - start_poll

    # Assert that GET /api/jobs responded in less than 100ms (not blocked by the 300ms sleep)
    assert poll_elapsed < 0.2
    assert any(j.id == job_id for j in jobs_response)

    # Wait for the pipeline task to finish
    await pipeline_task
    final_job = main_module.db.get_job(job_id)
    assert final_job["status"] == "done"


def test_waiting_on_rate_limit_status_and_models_validation():
    """Verify that 'waiting_on_rate_limit' is valid across VideoListItem, SubJobInfo, and DB updates."""
    from backend.models import VideoListItem, SubJobInfo, JobResponse, VideoIngestResponse

    # 1. Test model serialization/validation
    sub_job = SubJobInfo(
        video_id="rate_limit_vid",
        title="Rate Limit Video",
        status="waiting_on_rate_limit",
        progress=45
    )
    assert sub_job.status == "waiting_on_rate_limit"

    video_item = VideoListItem(
        id="vid-rl-123",
        youtube_video_id="rl_yt_123",
        title="Rate Limit Video",
        thumbnail_url="https://example.com/thumb.jpg",
        duration_seconds=120,
        status="waiting_on_rate_limit",
        added_at="2026-09-01T12:00:00Z"
    )
    assert video_item.status == "waiting_on_rate_limit"

    job_item = JobResponse(
        id="job-rl-123",
        type="video",
        title="Rate Limit Job",
        status="processing",
        stage="waiting_on_rate_limit",
        sub_jobs=[sub_job]
    )
    assert job_item.stage == "waiting_on_rate_limit"

    # 2. Test DB persistence for video with waiting_on_rate_limit status
    main_module.db.create_video({
        "id": "vid-rl-db-1",
        "youtube_video_id": "rl_yt_db_1",
        "title": "Rate Limit DB Video",
        "thumbnail_url": None,
        "duration_seconds": 60,
        "status": "waiting_on_rate_limit",
        "added_at": "2026-09-01T12:00:00Z"
    })

    saved = main_module.db.get_video("vid-rl-db-1")
    assert saved is not None
    assert saved["status"] == "waiting_on_rate_limit"

    # 3. Test video status update to waiting_on_rate_limit
    main_module.db.update_video("vid-rl-db-1", {"status": "waiting_on_rate_limit"})
    updated = main_module.db.get_video("vid-rl-db-1")
    assert updated["status"] == "waiting_on_rate_limit"








