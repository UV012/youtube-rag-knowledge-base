# YouTube Study RAG Backend — Deployment & Migration Guide

## 1. Supabase Schema Migration (with pgvector)

Run the SQL in [`supabase_schema.sql`](supabase_schema.sql) in your Supabase SQL Editor:

```sql
-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Videos Table
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    youtube_video_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    thumbnail_url TEXT,
    duration_seconds INT DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('queued', 'downloading', 'transcribing', 'indexing', 'ready', 'failed', 'cancelled')),
    error_message TEXT,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tags TEXT[] DEFAULT '{}',
    description TEXT,
    channel_name TEXT
);

-- 3. Jobs Table
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL CHECK (type IN ('video', 'playlist')),
    title TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'done', 'failed', 'cancelled')),
    stage TEXT CHECK (stage IN ('downloading', 'transcribing', 'indexing', 'waiting_on_rate_limit')),
    video_ids UUID[] DEFAULT '{}',
    progress_current INT DEFAULT 0,
    progress_total INT DEFAULT 100,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sub_jobs JSONB DEFAULT '[]'::jsonb,
    url TEXT
);

-- 4. Chunks Table (768 dimensions for Gemini gemini-embedding-001)
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    start_seconds FLOAT NOT NULL,
    end_seconds FLOAT NOT NULL,
    embedding VECTOR(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. HNSW index for cosine similarity search
CREATE INDEX IF NOT EXISTS chunks_embedding_cosine_idx 
ON chunks USING hnsw (embedding vector_cosine_ops);

-- 6. RPC function for semantic similarity vector search
CREATE OR REPLACE FUNCTION match_chunks (
    query_embedding VECTOR(768),
    match_count INT DEFAULT 8,
    filter_video_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    video_id UUID,
    youtube_video_id TEXT,
    title TEXT,
    thumbnail_url TEXT,
    duration_seconds INT,
    channel_name TEXT,
    text TEXT,
    start_seconds FLOAT,
    end_seconds FLOAT,
    score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.video_id,
        v.youtube_video_id,
        v.title,
        v.thumbnail_url,
        v.duration_seconds,
        v.channel_name,
        c.text,
        c.start_seconds,
        c.end_seconds,
        (1 - (c.embedding <=> query_embedding))::FLOAT AS score
    FROM chunks c
    JOIN videos v ON c.video_id = v.id
    WHERE (filter_video_id IS NULL OR c.video_id = filter_video_id)
      AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> query_embedding ASC
    LIMIT match_count;
END;
$$;
```

---

## 2. Google Cloud Run Deployment (Single-Process Container)

The application uses a multi-stage Dockerfile where the React/Vite frontend is built into static assets and served directly by the single FastAPI container.

```bash
# 1. Authenticate with GCP
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID

# 2. Build and submit container image
gcloud builds submit --tag gcr.io/YOUR_GCP_PROJECT_ID/digital-study-carrel:latest

# 3. Deploy to Cloud Run
gcloud run deploy digital-study-carrel \
    --image gcr.io/YOUR_GCP_PROJECT_ID/digital-study-carrel:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 600 \
    --set-env-vars "GEMINI_API_KEY=YOUR_GEMINI_KEY,GROQ_API_KEY=YOUR_GROQ_KEY,SUPABASE_URL=YOUR_SUPABASE_URL,SUPABASE_KEY=YOUR_SUPABASE_KEY"
```

---

## 3. Required Environment Variables
- `GEMINI_API_KEY`: Google Gemini API key for `gemini-embedding-001` (768-dim embeddings) and `gemini-2.0-flash` (RAG answer synthesis).
- `GROQ_API_KEY`: Groq API key for `whisper-large-v3-turbo` audio transcription with timestamps.
- `SUPABASE_URL`: Supabase project URL (e.g. `https://xyz.supabase.co`).
- `SUPABASE_KEY`: Supabase API key.
- `LOCAL_DEV`: Set to `true` ONLY for local offline development without Supabase. When `false` (default), the backend will fail loudly at startup if Supabase credentials are missing.
- `YTDLP_PLAYER_CLIENTS`: (Optional) Comma-separated list of YouTube player clients to spoof (defaults to `tv,web_safari,android,mweb`).
- `YTDLP_COOKIES_FILE`: (Optional) Path to a `cookies.txt` file if deploying to datacenter environments requiring authenticated session fallback.

---

## 4. YouTube Bot Detection & Maintenance

YouTube actively employs automated bot checks on requests originating from datacenter IPs. The ingestion engine mitigates this via **player client spoofing**:
1. **Configurable Player Clients**: The pipeline automatically requests video streams spoofing `tv`, `web_safari`, `android`, and `mweb` client APIs, bypassing standard web JS bot challenges.
2. **Fallback Sequence**: If one client API is blocked or DRM-restricted on a particular video, the engine automatically attempts fallback clients in order and logs which client succeeded.
3. **Periodic yt-dlp Updates**: Because YouTube adjusts its player endpoints periodically, upgrade `yt-dlp` regularly:
   ```bash
   pip install --upgrade yt-dlp
   ```
4. **Cookie Fallback (Second-line option)**: If datacenter IP blocks occur on specific videos, export a `cookies.txt` file from a dedicated (non-personal) Google account and set `YTDLP_COOKIES_FILE=/path/to/cookies.txt`.
