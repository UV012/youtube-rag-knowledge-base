# Architecture

## Overview

Digital Study Carrel is a single-process FastAPI application that ingests YouTube videos, transcribes and indexes them, and answers natural-language questions against the indexed content using retrieval-augmented generation (RAG).

Ingestion is asynchronous and can take minutes; querying is synchronous and fast. These two workloads are deliberately kept separate so neither blocks the other.

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│   Browser   │◄────►│  FastAPI (single  │◄────►│  Supabase            │
│  (React SPA)│      │  process, serves  │      │  Postgres + pgvector │
└─────────────┘      │  API + static     │      └─────────────────────┘
                      │  frontend files)  │
                      └─────────┬─────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
         ┌─────────┐      ┌──────────┐      ┌──────────────┐
         │ yt-dlp/ │      │   Groq    │      │    Gemini     │
         │ ffmpeg  │      │  Whisper  │      │  embeddings + │
         │(download│      │(transcribe│      │  generation   │
         │ & split)│      │  audio)   │      │               │
         └─────────┘      └──────────┘      └──────────────┘
```

## Deployment shape

A single Docker image builds the React frontend to static assets (Node stage) and serves both those assets and the API from one Python/FastAPI process (`StaticFiles` mount + API routes in the same app). There's no separate frontend server or reverse proxy in production — one container, one process, one port. Locally, a lightweight Express dev server (`server.ts`) proxies `/api/*` to FastAPI so Vite's dev server and the backend can run side by side during development; this proxy plays no role in production.

## Ingestion pipeline

Triggered by `POST /api/videos`, run as a FastAPI background task (`process_video_pipeline` in `backend/main.py`), so the HTTP response returns immediately while processing continues.

1. **Resolve the URL.** A playlist URL is expanded into individual video entries; a single video URL is used directly. Metadata (title, thumbnail, duration, channel) is fetched via `yt-dlp` without downloading full audio yet.
2. **Idempotency check.** If the video's `youtube_video_id` already exists with status `ready`, processing is skipped and the existing video is returned — no duplicate work, no duplicate job.
3. **Download audio** (`download_audio_and_chunk` in `backend/pipeline.py`). Downloads the best audio stream via `yt-dlp`. To work around YouTube's bot detection on automated requests, this tries a sequence of spoofed player clients (`DEFAULT_YTDLP_PLAYER_CLIENTS`: `tv_embedded`, `android_creator`, `android_embedded`, `tv`, `web_safari`, `android`, `mweb`) until one succeeds, logging which one worked.
4. **Split long audio.** If the downloaded audio exceeds Groq's per-request limits, it's split into sequential chunks via `ffmpeg` before transcription, each retaining its position offset so timestamps can be corrected after merging.
5. **Transcribe** (`transcribe_with_backoff`). Each audio chunk is sent to Groq's `whisper-large-v3-turbo`, returning segment-level timestamps. Each chunk's segments are offset-corrected by that chunk's start position in the full audio. Includes exponential backoff on rate limits.
6. **Merge into semantic chunks** (`merge_segments_to_chunks`). Raw Whisper segments (often just a few seconds each) are merged into ~30–60 second chunks aligned to sentence boundaries — meaningful units for embedding and retrieval, not too granular to be useful, not so large that a search result loses precision about *where* in the video the answer is.
7. **Embed** (`_embed_batch_adaptive`). Each chunk's text is embedded via Gemini's `gemini-embedding-001` with `task_type=RETRIEVAL_DOCUMENT`, at a fixed `output_dimensionality=768` (matching the `pgvector` column), with the resulting vector L2-normalized before storage (required for `gemini-embedding-001` when the output dimension is reduced from its 3072 default — unlike some other embedding models, it doesn't auto-normalize in that case). Batches that get rejected as too large are adaptively halved and retried rather than failing outright; a genuine rate limit triggers backoff instead.
8. **Persist.** Any existing chunks for this video are deleted first (so a retry after a partial failure can't leave stale/duplicate chunks alongside fresh ones), then the new chunks are inserted, and the video's status is set to `ready`.

Throughout, the job's `status`/`stage` fields are updated so the frontend can poll `GET /api/jobs` and show live progress (`queued` → `downloading` → `transcribing` → `indexing` → `ready`, or `failed`/`cancelled`).

## Query pipeline

Triggered by `POST /api/search`, synchronous:

1. The question is embedded via `gemini-embedding-001` with `task_type=RETRIEVAL_QUERY` (asymmetric to the document-side embedding, which improves retrieval quality for this kind of question-vs-passage matching) — same `output_dimensionality`/normalization as ingestion, since the two vector spaces have to match to be comparable.
2. The embedding is passed to Supabase's `match_chunks` Postgres function, which ranks chunks by cosine similarity (`pgvector`'s `<=>` operator, converted from distance to a `0–1` similarity score) and returns the top matches across the whole library (not scoped to one video, unless the caller requests that).
3. The retrieved chunks — each with its source video title and timestamp range — are formatted into a citation-labeled context block and sent to `gemini-3.6-flash`, instructed to answer only from the provided context and cite which source each part of the answer comes from, or say it doesn't know if the context doesn't cover the question.
4. The response includes both the generated answer and the raw ranked chunk list, so the frontend can show multiple clickable timestamp results, not just a single prose answer.

## Data model (Supabase / Postgres)

- **`videos`** — one row per ingested video: metadata, current `status`, error message if failed.
- **`jobs`** — one row per ingestion request (a single video or a whole playlist). For playlists, tracks a `sub_jobs` array with per-video status within that playlist. Tracks overall progress and status/stage for polling.
- **`chunks`** — one row per semantic chunk: source video, text, start/end timestamps, and its embedding vector (`pgvector`).

## Concurrency and reliability notes

- **Duplicate-submission guard**: resubmitting a URL that's already `ready` or already mid-processing doesn't spawn a second concurrent job for the same video — this specifically avoids two pipelines racing on the same temp files and API rate limits.
- **Job-scoped temp directories**: each job's working directory is uniquely named (including the job ID), so concurrent jobs never collide on shared filenames.
- **Explicit timeouts** on both the Groq and Gemini clients (via shared factory functions `get_groq_client()`/`get_gemini_client()` in `backend/pipeline.py`), so a hung network call can't wedge a job indefinitely.
- **Stale-job watchdog**: a job with no progress for 15+ minutes is automatically transitioned to `failed` with a clear "stalled" message, rather than sitting in an ambiguous in-progress state forever.
- **Loud startup validation**: the app refuses to start against non-persistent storage unless `LOCAL_DEV=true` is explicitly set — there's no silent fallback to an in-memory store that could look like it's working while nothing actually persists.
