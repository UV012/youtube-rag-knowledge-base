export type VideoStatus = 'queued' | 'downloading' | 'transcribing' | 'indexing' | 'waiting_on_rate_limit' | 'ready' | 'failed' | 'cancelled';
export type JobType = 'video' | 'playlist';
export type JobStatus = 'queued' | 'processing' | 'done' | 'failed' | 'cancelled';
export type JobStage = 'downloading' | 'transcribing' | 'indexing' | 'waiting_on_rate_limit';

export interface VideoChunk {
  id: string;
  video_id: string;
  text: string;
  start_seconds: number;
  end_seconds: number;
  embedding?: number[];
  created_at?: string;
}

export interface VideoItem {
  id: string;
  youtube_video_id: string;
  title: string;
  thumbnail_url: string;
  duration_seconds: number;
  status: VideoStatus;
  error_message?: string | null;
  added_at: string;
  tags?: string[];
  description?: string;
  chunks?: VideoChunk[];
  channel_name?: string;
}

export interface SubJob {
  video_id: string;
  title: string;
  status: 'queued' | 'downloading' | 'transcribing' | 'indexing' | 'waiting_on_rate_limit' | 'done' | 'failed' | 'cancelled';
  progress?: number;
  error_message?: string;
}

export interface JobItem {
  id: string;
  type: JobType;
  title: string;
  status: JobStatus;
  stage?: JobStage;
  video_ids: string[];
  progress_current: number;
  progress_total: number;
  error_message?: string | null;
  created_at: string;
  sub_jobs?: SubJob[];
  url?: string;
}

export interface SearchResultItem {
  video_id: string;
  youtube_video_id?: string;
  title: string;
  thumbnail_url: string;
  text: string;
  start_seconds: number;
  end_seconds: number;
  score: number;
  duration_seconds?: number;
  channel_name?: string;
}

export interface SearchResponse {
  answer: string;
  results: SearchResultItem[];
  query: string;
}
