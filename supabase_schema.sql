-- =============================================================================
-- Supabase Schema Migration: Digital Study Carrel (PostgreSQL + pgvector)
-- =============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Videos Table
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    youtube_video_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    thumbnail_url TEXT,
    duration_seconds INT DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('queued', 'downloading', 'transcribing', 'indexing', 'waiting_on_rate_limit', 'ready', 'failed', 'cancelled')),
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

-- 5. Indexes for fast retrieval
CREATE INDEX IF NOT EXISTS idx_videos_youtube_video_id ON videos (youtube_video_id);
CREATE INDEX IF NOT EXISTS idx_chunks_video_id ON chunks (video_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);

-- 6. HNSW vector index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS chunks_embedding_cosine_idx 
ON chunks USING hnsw (embedding vector_cosine_ops);

-- 7. RPC function for semantic similarity vector search
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
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =============================================================================
-- MIGRATION FOR EXISTING DEPLOYMENTS:
-- Run this in Supabase SQL Editor if upgrading an already existing database:
-- =============================================================================
-- ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_status_check;
-- ALTER TABLE videos ADD CONSTRAINT videos_status_check
--   CHECK (status IN ('queued', 'downloading', 'transcribing', 'indexing', 'waiting_on_rate_limit', 'ready', 'failed', 'cancelled'));
--
-- ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
-- ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
--   CHECK (status IN ('queued', 'processing', 'done', 'failed', 'cancelled'));
--
-- ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_stage_check;
-- ALTER TABLE jobs ADD CONSTRAINT jobs_stage_check
--   CHECK (stage IN ('downloading', 'transcribing', 'indexing', 'waiting_on_rate_limit'));

