import React, { useState, useEffect } from 'react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const [status, setStatus] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'status' | 'architecture' | 'docker'>('status');

  useEffect(() => {
    if (isOpen) {
      fetch('/api/status')
        .then((res) => res.json())
        .then((d) => setStatus(d))
        .catch((e) => console.error(e));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0d0c25]/60 backdrop-blur-xs">
      <div className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-2xl w-full max-w-3xl h-[650px] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#c8c5ce] dark:border-[#78767e] flex items-center justify-between bg-[#fff7fa] dark:bg-[#1a1a24]">
          <div className="flex items-center space-x-3">
            <span className="material-symbols-outlined text-[24px] text-[#0d0c25] dark:text-[#e2dfff]">
              settings
            </span>
            <h3 className="font-['Newsreader'] text-[22px] font-semibold text-[#0d0c25] dark:text-[#ffffff]">
              System Configuration & Architecture
            </h3>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[#eedeeb] dark:hover:bg-[#282421] text-[#47464d] dark:text-[#cdc5c0] cursor-pointer"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Tab Selection */}
        <div className="flex border-b border-[#c8c5ce] dark:border-[#78767e] px-6 bg-[#fff7fa]/50 dark:bg-[#1a1a24]/50 gap-4 font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider">
          <button
            onClick={() => setActiveTab('status')}
            className={`py-3 border-b-2 ${
              activeTab === 'status'
                ? 'border-[#0d0c25] dark:border-[#e2dfff] text-[#0d0c25] dark:text-[#e2dfff]'
                : 'border-transparent text-[#78767e] hover:text-[#0d0c25]'
            }`}
          >
            API & Pipeline Status
          </button>
          <button
            onClick={() => setActiveTab('architecture')}
            className={`py-3 border-b-2 ${
              activeTab === 'architecture'
                ? 'border-[#0d0c25] dark:border-[#e2dfff] text-[#0d0c25] dark:text-[#e2dfff]'
                : 'border-transparent text-[#78767e] hover:text-[#0d0c25]'
            }`}
          >
            RAG Pipeline Specs
          </button>
          <button
            onClick={() => setActiveTab('docker')}
            className={`py-3 border-b-2 ${
              activeTab === 'docker'
                ? 'border-[#0d0c25] dark:border-[#e2dfff] text-[#0d0c25] dark:text-[#e2dfff]'
                : 'border-transparent text-[#78767e] hover:text-[#0d0c25]'
            }`}
          >
            Cloud Run & Dockerfile
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === 'status' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 bg-[#fff7fa] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl">
                  <div className="font-['JetBrains_Mono'] text-[11px] text-[#78767e] uppercase mb-1">
                    Google Gemini API
                  </div>
                  <div className="font-['Newsreader'] text-[16px] font-semibold text-[#0d0c25] dark:text-[#ffffff] flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
                    <span className="truncate">
                      {status?.embedding_model || 'gemini-embedding-001'} / {status?.generation_model || 'gemini-3.6-flash'}
                    </span>
                  </div>
                  <p className="font-['Hanken_Grotesk'] text-[12px] text-[#47464d] dark:text-[#cdc5c0] mt-2">
                    Active client initialized for 768-dim vector embeddings & cited RAG answer synthesis.
                  </p>
                </div>

                <div className="p-4 bg-[#fff7fa] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl">
                  <div className="font-['JetBrains_Mono'] text-[11px] text-[#78767e] uppercase mb-1">
                    Groq Transcription
                  </div>
                  <div className="font-['Newsreader'] text-[16px] font-semibold text-[#0d0c25] dark:text-[#ffffff] flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
                    <span className="truncate">{status?.transcription_model || 'whisper-large-v3-turbo'}</span>
                  </div>
                  <p className="font-['Hanken_Grotesk'] text-[12px] text-[#47464d] dark:text-[#cdc5c0] mt-2">
                    Timestamp-accurate segment transcription with exponential backoff on 429.
                  </p>
                </div>

                <div className="p-4 bg-[#fff7fa] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl">
                  <div className="font-['JetBrains_Mono'] text-[11px] text-[#78767e] uppercase mb-1">
                    Database Storage
                  </div>
                  <div className="font-['Newsreader'] text-[16px] font-semibold text-[#0d0c25] dark:text-[#ffffff] flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
                    <span className="truncate">{status?.database_mode || 'Supabase (pgvector)'}</span>
                  </div>
                  <p className="font-['Hanken_Grotesk'] text-[12px] text-[#47464d] dark:text-[#cdc5c0] mt-2">
                    Durable store for videos, jobs, and 768-dim embeddings with HNSW cosine distance index.
                  </p>
                </div>
              </div>

              {/* Stats */}
              <div className="p-4 bg-[#eedeeb]/50 dark:bg-[#282421]/50 border border-[#c8c5ce] dark:border-[#78767e] rounded-xl font-['JetBrains_Mono'] text-[13px] flex items-center justify-between">
                <span>Total Indexed Videos: <strong>{status?.total_videos ?? 0}</strong></span>
                <span>Vector Chunks: <strong>{status?.total_chunks ?? 0}</strong></span>
                <span>Active Background Jobs: <strong>{status?.active_jobs ?? 0}</strong></span>
              </div>
            </div>
          )}

          {activeTab === 'architecture' && (
            <div className="space-y-4 font-['Hanken_Grotesk'] text-[14px] text-[#221922] dark:text-[#cdc5c0]">
              <h4 className="font-['Newsreader'] text-[18px] font-semibold text-[#0d0c25] dark:text-[#ffffff]">
                Core Architecture & Ingestion Flow
              </h4>
              <ol className="list-decimal pl-5 space-y-2 leading-relaxed">
                <li>
                  <strong>URL Ingestion & Idempotency:</strong> <code>POST /api/videos</code> checks whether the video ID has already been indexed before spawning asynchronous background worker tasks.
                </li>
                <li>
                  <strong>Audio Extraction:</strong> Downloads optimal audio stream using <code>yt-dlp</code> with configurable player client rotation and extracts to 128kbps MP3 via <code>ffmpeg</code>.
                </li>
                <li>
                  <strong>Groq Whisper Transcription:</strong> Transcribes with <code>whisper-large-v3-turbo</code> generating segment-level timestamps.
                </li>
                <li>
                  <strong>Semantic Chunking:</strong> Merges word segments into 30–60s conceptual chunks aligned on natural sentence boundaries.
                </li>
                <li>
                  <strong>Google Gemini Embeddings:</strong> Generates 768-dim normalized vectors via <code>{status?.embedding_model || 'gemini-embedding-001'}</code> and stores in Supabase <code>chunks</code> table.
                </li>
                <li>
                  <strong>Synchronous Search & RAG:</strong> <code>POST /api/search</code> embeds queries, executes cosine distance ranking, and passes top context to <code>{status?.generation_model || 'gemini-3.6-flash'}</code> to synthesize cited answers with timestamp jumps.
                </li>
              </ol>
            </div>
          )}

          {activeTab === 'docker' && (
            <div className="space-y-3 font-['JetBrains_Mono'] text-[12px]">
              <div className="text-[#0d0c25] dark:text-[#ffffff] font-bold">
                Dockerfile (Cloud Run Deployment Ready):
              </div>
              <pre className="p-4 bg-[#1a1a24] text-[#e2dfff] rounded-xl overflow-x-auto leading-relaxed border border-[#78767e]">
{`FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ffmpeg curl build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]`}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
