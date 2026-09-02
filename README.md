# Digital Study Carrel

A personal YouTube study-video RAG search tool. Paste a video or playlist link, and it downloads the audio, transcribes it with word-level timestamps, indexes it for semantic search, and lets you ask questions about anything you've watched — getting back an answer with the exact video and timestamp it came from.

Built for solo learners who watch a lot of lecture/tutorial content on YouTube and later struggle to find the specific moment a concept was explained.

## Features

- **Ingest single videos or full playlists** — paste a link, processing happens asynchronously in the background
- **Accurate transcription** — audio-based transcription (not YouTube's auto-captions) via Groq's Whisper API, with segment-level timestamps
- **Semantic search across your whole library** — ask a question in plain language, get an answer synthesized from the actual video content, with citations back to the source video and timestamp
- **Timestamp-accurate playback** — click a result and jump straight to that moment in the embedded player
- **Runs entirely on free-tier services** — no infrastructure cost to self-host at personal scale (see [Known Limitations](#known-limitations) for what that means in practice)

## Tech Stack

- **Backend**: FastAPI (Python), single-process, serving both the API and the built frontend
- **Audio**: `yt-dlp` for download/metadata, `ffmpeg` for audio extraction and chunking
- **Transcription**: Groq API, `whisper-large-v3-turbo`
- **Embeddings & Answer Generation**: Google Gemini API — `gemini-embedding-001` for vector embeddings, `gemini-3.6-flash` for RAG answer synthesis
- **Storage**: Supabase (Postgres + `pgvector`) — a single database for videos, jobs, and vector embeddings
- **Frontend**: React + Vite, Tailwind CSS

See [ARCHITECTURE.md](./ARCHITECTURE.md) for how the pieces fit together.

## Prerequisites

- Python 3.11+
- Node.js 20+
- `ffmpeg` installed and available on your system `PATH` ([download](https://ffmpeg.org/download.html)) — required locally even though Docker installs it automatically
- API keys (all have usable free tiers, see [Known Limitations](#known-limitations)):
  - [Google Gemini API key](https://aistudio.google.com/apikey)
  - [Groq API key](https://console.groq.com/keys)
  - [Supabase project](https://supabase.com) (free tier) with its URL and API key

## Setup

1. **Clone the repo**
   ```bash
   git clone <your-repo-url>
   cd digital-study-carrel
   ```

2. **Install backend dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   (Use `requirements-dev.txt` instead if you want to run the test suite.)

3. **Install frontend dependencies**
   ```bash
   npm install
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Fill in `GEMINI_API_KEY`, `GROQ_API_KEY`, `SUPABASE_URL`, and `SUPABASE_KEY` in `.env`.

5. **Set up the database**
   In your Supabase project's SQL Editor, run the entire contents of `supabase_schema.sql`. This creates the `vector` extension, the `videos`/`jobs`/`chunks` tables, and the `match_chunks` similarity-search function. This is a one-time step — it won't run automatically just by filling in `.env`.

6. **Start the backend**
   ```bash
   npm run dev:backend
   ```
   Watch the startup log — it should confirm a successful Supabase connection. If `SUPABASE_URL`/`SUPABASE_KEY` are missing or invalid, it will fail loudly on purpose rather than silently falling back to non-persistent storage.

7. **Start the frontend** (in a separate terminal)
   ```bash
   npm run dev:frontend
   ```
   Or `npm run dev` to run everything through the single Express dev server.

8. Open the app and paste a YouTube link to try it.

## Local Development Notes

- `LOCAL_DEV=true` in `.env` switches the backend to an in-memory store instead of Supabase — useful for quick local testing, but nothing persists across restarts. Leave it `false`/unset for normal use.
- The backend's `--reload` is scoped to the `backend/` directory only (`--reload-dir backend`), so editing frontend files or tests won't restart it.

## Deployment

See [DEPLOY.md](./DEPLOY.md) for deploying the included Docker image (single-process, serves both API and frontend) to Cloud Run or any other container host.

## Known Limitations

- **Single-user, no authentication.** There's no login system or per-user data isolation — every video and search result is global to whoever's running the instance. This is designed to be self-hosted by one person, not shared publicly among multiple users as-is.
- **Free-tier rate limits are real constraints, not just a cost-saving choice.** Groq's free Whisper tier caps out at roughly 8 hours of audio transcribed per day — plenty for one person's personal use, but the limiting factor if you're thinking about hosting this for a group.
- **YouTube's bot detection.** Downloads use a rotating set of spoofed player clients (`tv`, `web_safari`, `android`, `mweb`) to work around YouTube flagging automated download requests. This is inherently a moving target — YouTube's detection changes periodically, and occasional download failures on specific videos are expected behavior, not necessarily a bug.

## License

MIT — see [LICENSE](./LICENSE).
