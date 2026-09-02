# =============================================================================
# Stage 1: Build React/Vite Frontend
# =============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY index.html vite.config.ts tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# =============================================================================
# Stage 2: Production Runtime (FastAPI Single-Process)
# =============================================================================
FROM python:3.11-slim AS runtime

# Install ffmpeg for audio extraction and chunking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy built frontend static assets from Stage 1
COPY --from=frontend-builder /app/dist ./dist

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Cloud Run single-process container entrypoint
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
