from typing import List, Optional, Literal, Union
from datetime import datetime
from pydantic import BaseModel, Field

VideoStatus = Literal["queued", "downloading", "transcribing", "indexing", "waiting_on_rate_limit", "ready", "failed", "cancelled"]
JobType = Literal["video", "playlist"]
JobStatus = Literal["queued", "processing", "done", "failed", "cancelled"]
JobStage = Literal["downloading", "transcribing", "indexing", "waiting_on_rate_limit"]

class VideoIngestRequest(BaseModel):
    url: str

class VideoIngestResponse(BaseModel):
    job_id: Optional[str] = None
    type: Optional[JobType] = "video"
    status: Optional[str] = "queued"  # "queued", "already_exists", "already_processing"
    message: Optional[str] = None
    video_id: Optional[str] = None

class SubJobInfo(BaseModel):
    video_id: str
    title: str
    status: Literal["queued", "downloading", "transcribing", "indexing", "waiting_on_rate_limit", "done", "failed", "cancelled"] = "queued"
    progress: Optional[int] = None
    error_message: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    type: JobType
    title: Optional[str] = None
    status: JobStatus
    stage: Optional[JobStage] = None
    video_ids: List[str] = Field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 100
    sub_jobs: Optional[List[SubJobInfo]] = None
    error_message: Optional[str] = None
    created_at: Optional[Union[str, datetime]] = None
    updated_at: Optional[Union[str, datetime]] = None
    url: Optional[str] = None

class VideoListItem(BaseModel):
    id: str
    youtube_video_id: str
    title: str
    thumbnail_url: Optional[str] = None
    duration_seconds: int = 0
    status: VideoStatus
    error_message: Optional[str] = None
    added_at: Union[str, datetime]
    tags: Optional[List[str]] = Field(default_factory=list)
    description: Optional[str] = None
    channel_name: Optional[str] = None

class ChunkItem(BaseModel):
    id: Optional[str] = None
    text: str
    start_seconds: float
    end_seconds: float
    time_formatted: Optional[str] = None

class VideoDetailResponse(BaseModel):
    id: str
    youtube_video_id: str
    title: str
    thumbnail_url: Optional[str] = None
    duration_seconds: int = 0
    status: VideoStatus
    error_message: Optional[str] = None
    added_at: Optional[Union[str, datetime]] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    description: Optional[str] = None
    channel_name: Optional[str] = None
    chunks: List[ChunkItem] = Field(default_factory=list)

class SearchRequest(BaseModel):
    query: str
    video_id: Optional[str] = None

class SearchResultItem(BaseModel):
    video_id: str
    youtube_video_id: Optional[str] = None
    title: str
    thumbnail_url: Optional[str] = None
    text: str
    start_seconds: float
    end_seconds: float
    score: float
    duration_seconds: Optional[int] = None
    channel_name: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    answer: str
    results: List[SearchResultItem]

class StatusResponse(BaseModel):
    status: str = "ok"
    gemini_configured: bool
    groq_configured: bool
    supabase_configured: bool
    embedding_model: str = "gemini-embedding-001"
    generation_model: str = "gemini-3.6-flash"
    transcription_model: str = "whisper-large-v3-turbo"
    database_mode: str = "Supabase (PostgreSQL + pgvector)"
    total_videos: int
    total_chunks: int
    active_jobs: int
