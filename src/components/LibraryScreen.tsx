import React, { useState } from 'react';
import { VideoItem } from '../types';
import { useDataContext } from '../context/DataContext';

interface LibraryScreenProps {
  onSelectVideo: (videoId: string) => void;
  onNavigateAdd: () => void;
}

export const LibraryScreen: React.FC<LibraryScreenProps> = ({
  onSelectVideo,
  onNavigateAdd,
}) => {
  const { videos, setVideos, fetchVideos, isLoadingVideos: loading } = useDataContext();
  const [searchFilter, setSearchFilter] = useState('');
  const [sortOption, setSortOption] = useState<'date' | 'title' | 'duration'>('date');
  
  // Deletion state
  const [videoToDelete, setVideoToDelete] = useState<VideoItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Cancellation state
  const [videoToCancel, setVideoToCancel] = useState<VideoItem | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const handleDeleteVideo = async (videoId: string) => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/videos/${videoId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to delete video');
      }
      setVideos((prev) => prev.filter((v) => v.id !== videoId));
      setVideoToDelete(null);
    } catch (err: any) {
      setDeleteError(err.message || 'Failed to delete video');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancelVideo = async (videoId: string) => {
    setIsCancelling(true);
    setCancelError(null);
    try {
      const res = await fetch(`/api/videos/${videoId}/cancel`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to cancel video ingestion');
      }
      // Update local state immediately
      setVideos((prev) =>
        prev.map((v) => (v.id === videoId ? { ...v, status: 'cancelled', error_message: 'Ingestion cancelled by user' } : v))
      );
      setVideoToCancel(null);
    } catch (err: any) {
      setCancelError(err.message || 'Failed to cancel video ingestion');
    } finally {
      setIsCancelling(false);
    }
  };

  // Helper to format duration in MM:SS or HH:MM:SS
  const formatDuration = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Helper to format date
  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (e) {
      return 'Recent';
    }
  };

  // Filter & Sort
  const filteredVideos = videos
    .filter((v) => {
      const q = searchFilter.toLowerCase();
      return (
        v.title.toLowerCase().includes(q) ||
        (v.tags && v.tags.some((t) => t.toLowerCase().includes(q))) ||
        (v.channel_name && v.channel_name.toLowerCase().includes(q))
      );
    })
    .sort((a, b) => {
      if (sortOption === 'title') return a.title.localeCompare(b.title);
      if (sortOption === 'duration') return b.duration_seconds - a.duration_seconds;
      return new Date(b.added_at).getTime() - new Date(a.added_at).getTime();
    });

  const isProcessing = (status: string) =>
    ['queued', 'downloading', 'transcribing', 'indexing', 'waiting_on_rate_limit'].includes(status);

  return (
    <div className="max-w-[1300px] mx-auto px-4 md:px-12 py-10 flex flex-col min-h-full">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 pb-6 border-b border-[#c8c5ce] dark:border-[#78767e] gap-4">
        <div>
          <h2
            id="library-title"
            className="font-['Newsreader'] text-[42px] md:text-[48px] font-semibold text-[#0d0c25] dark:text-[#ffffff] tracking-[-0.02em] leading-[1.1] mb-2"
          >
            My Library
          </h2>
          <p className="font-['Hanken_Grotesk'] text-[17px] text-[#47464d] dark:text-[#cdc5c0]">
            Your index of processed video transcripts and extracted study materials.
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <span className="material-symbols-outlined absolute left-3 top-2.5 text-[#78767e] text-[18px]">
              search
            </span>
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Filter library..."
              className="pl-9 pr-3 py-2 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg font-['JetBrains_Mono'] text-[13px] text-[#221922] dark:text-[#ffffff] placeholder:text-[#78767e] outline-none focus:ring-1 focus:ring-[#0d0c25]"
            />
          </div>

          <button
            onClick={onNavigateAdd}
            className="px-4 py-2 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-lg font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider hover:opacity-90 transition-opacity flex items-center space-x-1.5 cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            <span>Add Video</span>
          </button>
        </div>
      </div>

      {/* Library Grid */}
      {filteredVideos.length === 0 && !loading ? (
        <div
          id="library-empty-state"
          className="my-auto py-16 px-6 max-w-lg mx-auto text-center border border-dashed border-[#c8c5ce] dark:border-[#78767e] rounded-2xl bg-[#ffffff]/60 dark:bg-[#222230]/60"
        >
          <div className="w-16 h-16 rounded-full bg-[#dbdeff] dark:bg-[#22223b] flex items-center justify-center mx-auto mb-4 text-[#595d78] dark:text-[#e2dfff]">
            <span className="material-symbols-outlined text-[32px]">video_library</span>
          </div>
          <h3 className="font-['Newsreader'] text-[24px] font-semibold text-[#0d0c25] dark:text-[#ffffff] mb-2">
            No Videos in Library
          </h3>
          <p className="font-['Hanken_Grotesk'] text-[15px] text-[#47464d] dark:text-[#cdc5c0] mb-6">
            Ingest your first lecture or seminar video to generate synchronized transcripts and AI-powered study carrel queries.
          </p>
          <button
            onClick={onNavigateAdd}
            className="px-6 py-3 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-lg font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider hover:opacity-90 transition-opacity cursor-pointer inline-flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">add_box</span>
            <span>Add Video Link</span>
          </button>
        </div>
      ) : (
        <div
          id="library-videos-grid"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6"
        >
          {filteredVideos.map((video) => {
            const isReady = video.status === 'ready';
            const isFailed = video.status === 'failed';
            const isCancelled = video.status === 'cancelled';
            const activeProcessing = isProcessing(video.status);

            return (
              <article
                key={video.id}
                id={`video-card-${video.id}`}
                onClick={() => {
                  if (isReady) onSelectVideo(video.id);
                }}
                className={`group bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl overflow-hidden shadow-xs transition-all duration-200 ${
                  isReady
                    ? 'hover:shadow-md hover:border-[#0d0c25] dark:hover:border-[#e2dfff] cursor-pointer'
                    : isFailed
                    ? 'border-[#ba1a1a]/50 dark:border-[#ffb4ab]/40 bg-[#fff5f5]/60 dark:bg-[#2a1d20]/50'
                    : 'opacity-95'
                } flex flex-col`}
              >
                {/* Thumbnail Container */}
                <div className="relative aspect-video w-full bg-[#1a1a24] overflow-hidden">
                  <img
                    src={video.thumbnail_url || 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600&auto=format&fit=crop&q=80'}
                    alt={video.title}
                    className={`w-full h-full object-cover transition-transform duration-300 ${
                      isReady ? 'group-hover:scale-105' : 'grayscale-30'
                    }`}
                    loading="lazy"
                  />
                  {/* Duration Badge */}
                  {video.duration_seconds > 0 && (
                    <div className="absolute bottom-2 right-2 px-1.5 py-0.5 bg-[#0d0c25]/85 backdrop-blur-xs text-white rounded font-['JetBrains_Mono'] text-[11px] font-medium tracking-wide">
                      {formatDuration(video.duration_seconds)}
                    </div>
                  )}

                  {/* Top Action Buttons */}
                  <div className="absolute top-2 right-2 flex items-center space-x-1.5 z-10">
                    {/* Cancel Button (for in-progress videos) */}
                    {activeProcessing && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setVideoToCancel(video);
                        }}
                        className="px-2 py-1 rounded-md bg-[#ba1a1a]/90 hover:bg-[#ba1a1a] text-white font-['JetBrains_Mono'] text-[10px] font-bold uppercase tracking-wider flex items-center space-x-1 shadow-sm cursor-pointer transition-all"
                        title="Cancel this video ingestion"
                      >
                        <span className="material-symbols-outlined text-[14px]">cancel</span>
                        <span>Cancel</span>
                      </button>
                    )}

                    {/* Delete Button (accessible for all videos) */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setVideoToDelete(video);
                      }}
                      className="w-8 h-8 rounded-lg bg-[#0d0c25]/75 hover:bg-[#ba1a1a] text-white opacity-90 group-hover:opacity-100 transition-all flex items-center justify-center cursor-pointer shadow-sm"
                      title="Delete video from library"
                    >
                      <span className="material-symbols-outlined text-[18px]">delete</span>
                    </button>
                  </div>

                  {/* Processing Overlay */}
                  {activeProcessing && (
                    <div className="absolute inset-0 bg-[#0d0c25]/65 backdrop-blur-xs flex flex-col items-center justify-center p-2 text-center">
                      <div className="flex items-center space-x-2 text-white font-['JetBrains_Mono'] text-[12px] uppercase mb-1">
                        <span className="material-symbols-outlined animate-spin text-[20px]">
                          sync
                        </span>
                        <span className="font-semibold">
                          {video.status === 'downloading'
                            ? 'Downloading'
                            : video.status === 'transcribing'
                            ? 'Transcribing'
                            : video.status === 'indexing'
                            ? 'Indexing Chunks'
                            : video.status === 'waiting_on_rate_limit'
                            ? 'Rate Limit Wait'
                            : 'Queued'}
                        </span>
                      </div>
                      <p className="text-[11px] text-white/80 font-['Hanken_Grotesk']">
                        Processing audio & embeddings...
                      </p>
                    </div>
                  )}

                  {/* Failed Overlay */}
                  {isFailed && (
                    <div className="absolute inset-0 bg-[#ba1a1a]/40 backdrop-blur-xs flex items-center justify-center p-2">
                      <div className="px-2.5 py-1 rounded bg-[#ba1a1a]/90 text-white font-['JetBrains_Mono'] text-[11px] font-bold uppercase tracking-wider flex items-center space-x-1.5 shadow">
                        <span className="material-symbols-outlined text-[16px]">error</span>
                        <span>Ingestion Failed</span>
                      </div>
                    </div>
                  )}

                  {/* Cancelled Overlay */}
                  {isCancelled && (
                    <div className="absolute inset-0 bg-[#0d0c25]/50 backdrop-blur-xs flex items-center justify-center p-2">
                      <div className="px-2.5 py-1 rounded bg-[#78767e]/90 text-white font-['JetBrains_Mono'] text-[11px] font-bold uppercase tracking-wider flex items-center space-x-1.5 shadow">
                        <span className="material-symbols-outlined text-[16px]">block</span>
                        <span>Cancelled</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Content */}
                <div className="p-4 flex-1 flex flex-col justify-between">
                  <div>
                    <h3 className="font-['Newsreader'] text-[19px] font-semibold text-[#0d0c25] dark:text-[#ffffff] leading-snug line-clamp-2 mb-2 group-hover:text-[#595d78] dark:group-hover:text-[#dbdeff] transition-colors">
                      {video.title}
                    </h3>
                    {video.channel_name && (
                      <p className="font-['Hanken_Grotesk'] text-[13px] text-[#47464d] dark:text-[#cdc5c0] mb-2 truncate">
                        {video.channel_name}
                      </p>
                    )}
                    {isFailed && video.error_message && (
                      <p className="font-['JetBrains_Mono'] text-[11px] text-[#ba1a1a] dark:text-[#ffb4ab] line-clamp-2 mb-2 bg-[#ffdad6]/40 dark:bg-[#93000a]/20 p-1.5 rounded border border-[#ba1a1a]/20">
                        {video.error_message}
                      </p>
                    )}
                  </div>

                  <div className="pt-3 border-t border-[#c8c5ce]/40 dark:border-[#78767e]/40 flex items-center justify-between font-['JetBrains_Mono'] text-[11px]">
                    <span className="text-[#47464d] dark:text-[#cdc5c0]">
                      {formatDate(video.added_at)}
                    </span>

                    {/* Status Badge */}
                    {isReady ? (
                      <span className="px-2 py-0.5 bg-[#dbdeff] dark:bg-[#22223b] text-[#0d0c25] dark:text-[#e2dfff] rounded font-bold uppercase tracking-wider flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#0d0c25] dark:bg-[#e2dfff]" />
                        READY
                      </span>
                    ) : isFailed ? (
                      <span className="px-2 py-0.5 bg-[#ffdad6] dark:bg-[#93000a]/40 text-[#ba1a1a] dark:text-[#ffb4ab] rounded font-bold uppercase tracking-wider flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#ba1a1a] dark:bg-[#ffb4ab]" />
                        FAILED
                      </span>
                    ) : isCancelled ? (
                      <span className="px-2 py-0.5 bg-[#eedeeb] dark:bg-[#343038] text-[#78767e] dark:text-[#cdc5c0] rounded font-bold uppercase tracking-wider flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#78767e]" />
                        CANCELLED
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 bg-[#f4e3f1] dark:bg-[#282421] text-[#595d78] dark:text-[#cdc5c0] rounded font-bold uppercase tracking-wider flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#595d78] animate-ping" />
                        {video.status.toUpperCase()}...
                      </span>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Confirmation Modal for Video Deletion */}
      {videoToDelete && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl max-w-md w-full p-6 shadow-xl">
            <div className="flex items-center space-x-3 text-[#ba1a1a] dark:text-[#ffb4ab] mb-3">
              <span className="material-symbols-outlined text-[28px]">warning</span>
              <h3 className="font-['Newsreader'] text-[22px] font-semibold text-[#0d0c25] dark:text-[#ffffff]">
                Delete Video
              </h3>
            </div>
            <p className="font-['Hanken_Grotesk'] text-[15px] text-[#47464d] dark:text-[#cdc5c0] mb-4">
              Are you sure you want to remove <strong>"{videoToDelete.title}"</strong> from your library? This will permanently delete its transcripts, chunks, and index vectors.
            </p>
            {deleteError && (
              <p className="font-['Hanken_Grotesk'] text-[13px] text-[#ba1a1a] dark:text-[#ffb4ab] mb-4">
                {deleteError}
              </p>
            )}
            <div className="flex items-center justify-end space-x-3 font-['JetBrains_Mono'] text-[13px]">
              <button
                onClick={() => {
                  setVideoToDelete(null);
                  setDeleteError(null);
                }}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg border border-[#c8c5ce] dark:border-[#78767e] text-[#47464d] dark:text-[#cdc5c0] hover:bg-[#eedeeb] dark:hover:bg-[#282421] transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteVideo(videoToDelete.id)}
                disabled={isDeleting}
                className="px-4 py-2 bg-[#ba1a1a] text-white rounded-lg font-bold uppercase tracking-wider hover:bg-[#93000a] transition-colors cursor-pointer flex items-center space-x-1.5"
              >
                {isDeleting ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[16px]">sync</span>
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[16px]">delete</span>
                    <span>Delete Video</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal for Video Ingestion Cancellation */}
      {videoToCancel && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl max-w-md w-full p-6 shadow-xl">
            <div className="flex items-center space-x-3 text-[#ba1a1a] dark:text-[#ffb4ab] mb-3">
              <span className="material-symbols-outlined text-[28px]">cancel</span>
              <h3 className="font-['Newsreader'] text-[22px] font-semibold text-[#0d0c25] dark:text-[#ffffff]">
                Cancel Ingestion
              </h3>
            </div>
            <p className="font-['Hanken_Grotesk'] text-[15px] text-[#47464d] dark:text-[#cdc5c0] mb-4">
              Stop background processing for <strong>"{videoToCancel.title}"</strong>? Any unfinished transcription or indexing work will be halted immediately.
            </p>
            {cancelError && (
              <p className="font-['Hanken_Grotesk'] text-[13px] text-[#ba1a1a] dark:text-[#ffb4ab] mb-4">
                {cancelError}
              </p>
            )}
            <div className="flex items-center justify-end space-x-3 font-['JetBrains_Mono'] text-[13px]">
              <button
                onClick={() => {
                  setVideoToCancel(null);
                  setCancelError(null);
                }}
                disabled={isCancelling}
                className="px-4 py-2 rounded-lg border border-[#c8c5ce] dark:border-[#78767e] text-[#47464d] dark:text-[#cdc5c0] hover:bg-[#eedeeb] dark:hover:bg-[#282421] transition-colors cursor-pointer"
              >
                Keep Processing
              </button>
              <button
                onClick={() => handleCancelVideo(videoToCancel.id)}
                disabled={isCancelling}
                className="px-4 py-2 bg-[#ba1a1a] text-white rounded-lg font-bold uppercase tracking-wider hover:bg-[#93000a] transition-colors cursor-pointer flex items-center space-x-1.5"
              >
                {isCancelling ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[16px]">sync</span>
                    <span>Cancelling...</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[16px]">cancel</span>
                    <span>Stop Ingestion</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
