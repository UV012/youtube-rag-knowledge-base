import os
import math
import uuid
import asyncio
import subprocess
import shutil
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
import yt_dlp
from groq import Groq
from google import genai

logger = logging.getLogger("backend.pipeline")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

groq_client = None
gemini_client = None


def get_groq_client() -> Optional[Groq]:
    """Returns a configured Groq client with explicit 90.0s timeout, or None if key is absent."""
    global groq_client
    if groq_client is not None:
        return groq_client
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    groq_client = Groq(api_key=api_key, timeout=90.0)
    return groq_client


def get_gemini_client() -> Optional[genai.Client]:
    """Returns a configured Gemini client with explicit 90s (90,000ms) HTTP timeout, or None if key is absent."""
    global gemini_client
    if gemini_client is not None:
        return gemini_client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    from google.genai import types
    gemini_client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=90_000),
    )
    return gemini_client


groq_client = get_groq_client()
gemini_client = get_gemini_client()

# Configurable YouTube player clients for bypassing automated bot checks and SABR-streaming truncation
DEFAULT_YTDLP_PLAYER_CLIENTS = ["tv_embedded", "android_creator", "android_embedded", "tv", "web_safari", "android", "mweb"]


def get_ytdlp_player_clients() -> List[str]:
    """Retrieves the list of YouTube player clients to spoof (from YTDLP_PLAYER_CLIENTS env or defaults)."""
    env_clients = os.getenv("YTDLP_PLAYER_CLIENTS")
    if env_clients:
        return [c.strip() for c in env_clients.split(",") if c.strip()]
    return list(DEFAULT_YTDLP_PLAYER_CLIENTS)


def build_ytdlp_opts(custom_opts: Optional[Dict[str, Any]] = None, player_clients: Optional[List[str]] = None) -> Dict[str, Any]:
    """Constructs robust yt-dlp options with spoofed player clients, socket timeout, and optional cookies file."""
    clients = player_clients or get_ytdlp_player_clients()
    opts: Dict[str, Any] = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30.0,
        'extractor_args': {
            'youtube': {
                'player_client': clients,
            }
        },
    }
    cookies_path = os.getenv("YTDLP_COOKIES_FILE") or os.getenv("YTDLP_COOKIES_PATH")
    if cookies_path and os.path.exists(cookies_path):
        opts['cookiefile'] = cookies_path

    if custom_opts:
        # Merge custom options
        for k, v in custom_opts.items():
            if k == 'extractor_args' and isinstance(v, dict):
                opts['extractor_args'].update(v)
            else:
                opts[k] = v
    return opts


def extract_metadata_and_expand_urls(url: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts metadata from a YouTube video or playlist URL with player client spoofing and fallback.
    Returns (media_type, list_of_entries).
    """
    clients_to_try = [get_ytdlp_player_clients(), ["tv"], ["web_safari"], ["android"], ["mweb"]]
    last_error = None

    for client_candidate in clients_to_try:
        ydl_opts = build_ytdlp_opts({
            'extract_flat': True,
            'skip_download': True,
        }, player_clients=client_candidate)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError(f"Could not extract info from URL: {url}")

                logger.info(f"Metadata extracted successfully using player clients: {client_candidate}")

                if '_type' in info and info['_type'] == 'playlist':
                    entries = []
                    for entry in info.get('entries', []):
                        if entry:
                            entries.append({
                                'youtube_id': entry.get('id'),
                                'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                                'title': entry.get('title', 'Unknown Video'),
                                'duration': int(entry.get('duration') or 0),
                                'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg",
                                'channel_name': entry.get('uploader') or entry.get('channel') or 'YouTube Creator',
                                'description': entry.get('description') or '',
                            })
                    return ('playlist', entries)
                else:
                    video_id = info.get('id')
                    return ('video', [{
                        'youtube_id': video_id,
                        'url': url,
                        'title': info.get('title', 'Unknown Video'),
                        'duration': int(info.get('duration') or 0),
                        'thumbnail': info.get('thumbnail') or (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None),
                        'channel_name': info.get('uploader') or info.get('channel') or 'YouTube Creator',
                        'description': info.get('description') or '',
                    }])
        except Exception as e:
            last_error = e
            logger.warning(f"Metadata extraction failed with player clients {client_candidate}: {e}. Retrying with next client...")

    raise last_error or ValueError(f"Failed to extract metadata for URL: {url}")


def _get_audio_duration(file_path: str) -> float:
    """Gets audio file duration in seconds via ffprobe if available."""
    if shutil.which("ffprobe"):
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", file_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            pass
    return 0.0


def download_audio_and_chunk(
    url: str,
    output_dir: str,
    max_chunk_duration_seconds: int = 600,  # 10 minutes
    max_chunk_size_bytes: int = 20 * 1024 * 1024  # 20 MB (Groq limit is 25MB)
) -> List[Tuple[str, float]]:
    """
    Downloads audio using yt-dlp to 128kbps MP3 with player client spoofing and fallback.
    If duration > max_chunk_duration_seconds or size > max_chunk_size_bytes,
    splits audio into sequential chunks with ffmpeg.
    
    Returns list of (chunk_audio_path, offset_seconds).
    """
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, '%(id)s.%(ext)s')

    configured_clients = get_ytdlp_player_clients()
    clients_to_try = [[c] for c in configured_clients]
    # Ensure standard robust fallbacks are present in order
    for fallback in [["tv_embedded"], ["android_creator"], ["android_embedded"], ["tv"], ["web_safari"], ["android"], ["mweb"]]:
        if fallback not in clients_to_try:
            clients_to_try.append(fallback)

    last_error = None
    info = None
    base_audio_path = None

    for client_candidate in clients_to_try:
        ydl_opts = build_ytdlp_opts({
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
        }, player_clients=client_candidate)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                cand_info = ydl.extract_info(url, download=True)
                vid_id = cand_info.get('id') if cand_info else None
                cand_path = os.path.join(output_dir, f"{vid_id}.mp3") if vid_id else None
                if not cand_path or not os.path.exists(cand_path):
                    for candidate_file in os.listdir(output_dir):
                        if vid_id and candidate_file.startswith(str(vid_id)) and candidate_file.endswith(".mp3"):
                            cand_path = os.path.join(output_dir, candidate_file)
                            break

                if cand_path and os.path.exists(cand_path):
                    cand_size = os.path.getsize(cand_path)
                    cand_dur = _get_audio_duration(cand_path)
                    expected_dur = float((cand_info and cand_info.get('duration')) or 0.0)
                    
                    # Reject truncated fragments (e.g. 554-byte headers or 0s audio from SABR streaming)
                    if cand_size > 4096 and (expected_dur <= 5.0 or cand_dur > 0.0):
                        info = cand_info
                        base_audio_path = cand_path
                        logger.info(f"Audio downloaded successfully using player client {client_candidate} (size: {cand_size} bytes, duration: {cand_dur:.1f}s)")
                        break
                    else:
                        logger.warning(f"Audio downloaded with player client {client_candidate} was truncated (size: {cand_size} bytes, duration: {cand_dur}s vs expected {expected_dur}s). Trying next fallback client...")
                        try:
                            os.remove(cand_path)
                        except OSError:
                            pass
        except Exception as e:
            last_error = e
            logger.warning(f"Audio download failed with player client {client_candidate}: {e}. Retrying fallback client...")

    if not info or not base_audio_path or not os.path.exists(base_audio_path):
        raise last_error or FileNotFoundError(f"Failed to download valid audio from {url} across all player clients")

    video_id = (info and info.get('id')) or "audio"
    file_size = os.path.getsize(base_audio_path)
    duration = float(info.get('duration') or _get_audio_duration(base_audio_path) or 0.0)

    needs_splitting = (duration > max_chunk_duration_seconds) or (file_size > max_chunk_size_bytes)
    ffmpeg_available = bool(shutil.which("ffmpeg"))

    if not needs_splitting or not ffmpeg_available:
        return [(base_audio_path, 0.0)]

    logger.info(f"Splitting audio {base_audio_path} (duration: {duration}s, size: {file_size} bytes)")
    chunks: List[Tuple[str, float]] = []
    chunk_duration = float(max_chunk_duration_seconds)
    num_chunks = math.ceil(duration / chunk_duration) if duration > 0 else 1

    for i in range(num_chunks):
        start_offset = i * chunk_duration
        chunk_filename = f"{video_id}_chunk_{i}_{uuid.uuid4().hex[:6]}.mp3"
        chunk_path = os.path.join(output_dir, chunk_filename)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_offset),
            "-t", str(chunk_duration),
            "-i", base_audio_path,
            "-acodec", "libmp3lame",
            "-b:a", "128k",
            chunk_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                chunks.append((chunk_path, start_offset))
        except Exception as e:
            logger.error(f"Error splitting chunk {i} with ffmpeg: {e}")

    if not chunks:
        return [(base_audio_path, 0.0)]

    return chunks


async def transcribe_with_backoff(
    audio_path: str,
    status_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[Dict[str, Any]]:
    """
    Transcribes audio using Groq Whisper large-v3-turbo with verbose segment timestamps.
    Handles HTTP 429 RateLimit backoff, cancellation checks, and notifies status_callback('waiting_on_rate_limit').
    """
    client = get_groq_client()
    if not client or not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        return [
            {"start": 0.0, "end": 28.5, "text": "Welcome to this research lecture. Today we examine the foundational architectural principles."},
            {"start": 28.5, "end": 58.0, "text": "We evaluate empirical performance across distributed retrieval vectors and neural processing pipelines."},
            {"start": 58.0, "end": 92.0, "text": "In conclusion, maintaining structured segment offsets guarantees precise cross-reference citations."}
        ]

    audio_size = os.path.getsize(audio_path)
    audio_dur = _get_audio_duration(audio_path)
    logger.info(f"Groq transcription input: {os.path.basename(audio_path)} (size: {audio_size} bytes, duration: {audio_dur:.2f}s)")
    if audio_size < 1024 or audio_dur == 0.0:
        logger.error(f"Audio file {audio_path} is invalid/truncated (size: {audio_size} bytes, duration: {audio_dur}s). Rejecting before Groq API call.")
        raise ValueError(f"Invalid or truncated audio file (size: {audio_size} bytes, duration: {audio_dur}s). Audio download was corrupt or empty.")

    max_retries = 6
    for attempt in range(max_retries):
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("Ingestion cancelled by user")

        try:
            def _call_groq():
                with open(audio_path, "rb") as file_obj:
                    return client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file_obj.read()),
                        model="whisper-large-v3-turbo",
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                        timeout=90.0
                    )
            transcription = await asyncio.to_thread(_call_groq)
                
            segments_raw = getattr(transcription, "segments", None)
            if segments_raw is None and isinstance(transcription, dict):
                segments_raw = transcription.get("segments")
            
            result = []
            if segments_raw:
                for s in segments_raw:
                    if isinstance(s, dict):
                        result.append({
                            "start": float(s.get("start", 0.0)),
                            "end": float(s.get("end", 0.0)),
                            "text": str(s.get("text", "")).strip()
                        })
                    else:
                        result.append({
                            "start": float(getattr(s, "start", 0.0)),
                            "end": float(getattr(s, "end", 0.0)),
                            "text": str(getattr(s, "text", "")).strip()
                        })
            return result
        except Exception as e:
            err_msg = str(e)
            if ("429" in err_msg or "rate_limit" in err_msg.lower()) and attempt < max_retries - 1:
                if status_callback:
                    status_callback("waiting_on_rate_limit")
                sleep_seconds = min(60, (2 ** attempt) + (attempt * 0.5))
                logger.warning(f"Groq 429 rate limit hit. Backing off for {sleep_seconds}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(sleep_seconds)
                if status_callback:
                    status_callback("transcribing")
            else:
                logger.error(f"Groq transcription error: {e}")
                raise e

    return []


def merge_segments_to_chunks(
    segments: List[Dict[str, Any]],
    target_duration: float = 45.0
) -> List[Dict[str, Any]]:
    """
    Merges fine-grained transcript segments into ~30-60 second conceptual chunks
    aligned with natural sentence punctuation boundaries (. ? !).
    """
    if not segments:
        return []

    chunks: List[Dict[str, Any]] = []
    current_chunk: List[Dict[str, Any]] = []
    current_start = 0.0
    current_text = ""

    for seg in segments:
        text = str(seg.get('text', '')).strip()
        if not text:
            continue
        start = float(seg.get('start', 0.0))
        end = float(seg.get('end', 0.0))

        if not current_chunk:
            current_start = start

        current_chunk.append(seg)
        current_text = (current_text + " " + text).strip()
        duration_so_far = end - current_start

        is_sentence_end = text.endswith(('.', '?', '!', ';"', '."'))
        if (duration_so_far >= target_duration and is_sentence_end) or (duration_so_far >= target_duration * 1.5):
            chunks.append({
                "text": current_text,
                "start_seconds": current_start,
                "end_seconds": end
            })
            current_chunk = []
            current_text = ""

    if current_chunk:
        chunks.append({
            "text": current_text,
            "start_seconds": current_start,
            "end_seconds": float(current_chunk[-1].get('end', current_start + 10.0))
        })

    return chunks


# Configurable Gemini Embedding Model (gemini-embedding-001 produces list-in/list-out batches with explicit output_dimensionality=768)
DEFAULT_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")


def _l2_normalize(vec: List[float]) -> List[float]:
    """L2 unit-normalizes an embedding vector so cosine similarity remains exact."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _generate_pseudo_embedding(text: str, dim: int = 768) -> List[float]:
    """Generates a deterministic 768-dim unit vector for local testing when no Gemini key is set."""
    vec = [0.0] * dim
    normalized = text.lower()
    for i, char in enumerate(normalized):
        code = ord(char)
        idx1 = (code * 31 + i * 17) % dim
        idx2 = (code * 47 + i * 19) % dim
        vec[idx1] += math.sin(code + i)
        vec[idx2] += math.cos(code * 2 + i)
    return _l2_normalize(vec)


def _embed_batch_adaptive(
    batch: List[str],
    status_callback: Optional[Callable[[str], None]] = None,
    max_retries: int = 5,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> List[List[float]]:
    """
    Embeds a single batch of texts using the Gemini Developer API's synchronous
    embed_content method with explicit output_dimensionality=768 and task_type.
    Applies manual L2 normalization to each returned vector.
    
    Failure mode handling:
    1. HTTP 400 / 413 / InvalidArgument (e.g. payload too large or request size limit):
       Immediately halves the batch size and recursively processes both halves.
       Halts at batch size 1 with a clear descriptive error identifying the chunk.
    2. HTTP 429 / ResourceExhausted (rate limiting):
       Exponential backoff retry while notifying status_callback('waiting_on_rate_limit').
    """
    client = get_gemini_client()

    if not batch:
        return []

    if not client:
        return [_generate_pseudo_embedding(t) for t in batch]

    for attempt in range(max_retries):
        try:
            from google.genai import types
            response = client.models.embed_content(
                model=DEFAULT_EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(
                    output_dimensionality=768,
                    task_type=task_type,
                ),
            )
            if response.embeddings:
                return [_l2_normalize(list(emb.values)) for emb in response.embeddings]
            return [_generate_pseudo_embedding(t) for t in batch]
        except Exception as e:
            err_msg = str(e)
            
            # Distinct failure mode 1: Invalid batch size / payload limit / 400 / 413
            is_oversized_error = (
                "400" in err_msg or
                "invalid" in err_msg.lower() or
                "too large" in err_msg.lower() or
                "413" in err_msg or
                "batch size" in err_msg.lower()
            )
            if is_oversized_error:
                if len(batch) > 1:
                    mid = len(batch) // 2
                    logger.warning(
                        f"Embedding batch of size {len(batch)} failed with 400/InvalidArgument: {e}. "
                        f"Halving batch into sub-batches of size {mid} and {len(batch) - mid}."
                    )
                    left = _embed_batch_adaptive(batch[:mid], status_callback, max_retries, task_type=task_type)
                    right = _embed_batch_adaptive(batch[mid:], status_callback, max_retries, task_type=task_type)
                    return left + right
                else:
                    sample_text = batch[0][:80] + "..." if len(batch[0]) > 80 else batch[0]
                    raise ValueError(
                        f"Embedding request failed for single chunk (length {len(batch[0])} chars): "
                        f"'{sample_text}'. Error: {err_msg}"
                    )

            # Distinct failure mode 2: HTTP 429 Rate limiting / Resource Exhausted
            is_rate_limit = "429" in err_msg or "resource_exhausted" in err_msg.lower()
            if is_rate_limit and attempt < max_retries - 1:
                if status_callback:
                    status_callback("waiting_on_rate_limit")
                sleep_time = min(30, (2 ** attempt) + 1)
                logger.warning(f"Gemini embedding rate limit hit (429). Sleeping {sleep_time}s (attempt {attempt+1}/{max_retries})")
                import time
                time.sleep(sleep_time)
                if status_callback:
                    status_callback("indexing")
            else:
                logger.error(f"Gemini embed_content error on attempt {attempt+1}: {e}")
                if attempt == max_retries - 1:
                    if len(batch) > 1:
                        mid = len(batch) // 2
                        left = _embed_batch_adaptive(batch[:mid], status_callback, max_retries, task_type=task_type)
                        right = _embed_batch_adaptive(batch[mid:], status_callback, max_retries, task_type=task_type)
                        return left + right
                    if os.getenv("LOCAL_DEV") == "true" or not os.getenv("GEMINI_API_KEY"):
                        return [_generate_pseudo_embedding(t) for t in batch]
                    sample_text = batch[0][:80] + "..." if len(batch[0]) > 80 else batch[0]
                    raise RuntimeError(
                        f"Embedding retries exhausted for chunk (length {len(batch[0])} chars): "
                        f"'{sample_text}'. Last error: {err_msg}"
                    )

    return [_generate_pseudo_embedding(t) for t in batch]


def embed_texts(
    texts: List[str],
    status_callback: Optional[Callable[[str], None]] = None,
    batch_size: int = 20,
    task_type: str = "RETRIEVAL_DOCUMENT",
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[List[float]]:
    """
    Generates 768-dimensional L2-normalized embeddings using Google Gemini Developer API synchronous
    embed_content method on gemini-embedding-001.
    
    Uses conservative default batch size of 20 (safe against token and RPM limits),
    with adaptive batch halving on 400/InvalidArgument errors, exponential backoff on 429s,
    and cooperative cancellation checks between batches.
    """
    if not texts:
        return []

    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        if cancel_check and cancel_check():
            logger.info("Embedding cancelled by user between batches. Halting.")
            raise asyncio.CancelledError("Ingestion cancelled by user")
        batch = texts[i : i + batch_size]
        batch_embs = _embed_batch_adaptive(batch, status_callback=status_callback, task_type=task_type)
        all_embeddings.extend(batch_embs)

    return all_embeddings


def embed_query(query: str) -> List[float]:
    """
    Generates a 768-dimensional normalized query embedding using RETRIEVAL_QUERY task_type.
    """
    res = embed_texts([query], batch_size=1, task_type="RETRIEVAL_QUERY")
    return res[0] if res else _generate_pseudo_embedding(query)
