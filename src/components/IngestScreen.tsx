import React, { useState } from 'react';
import { JobItem } from '../types';
import { useDataContext } from '../context/DataContext';

interface IngestScreenProps {
  onVideoAdded?: () => void;
}

export const IngestScreen: React.FC<IngestScreenProps> = ({ onVideoAdded }) => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const { jobs, setJobs, fetchJobs, fetchVideos } = useDataContext();
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const res = await fetch('/api/videos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || 'Failed to submit YouTube link');
      }

      if (data.status === 'already_exists') {
        setSuccessMsg(data.message || 'This video is already in your library.');
        setUrl('');
        return;
      }

      if (data.status === 'already_processing') {
        setSuccessMsg(data.message || 'This video is already being processed — check Current Jobs for its status.');
        setUrl('');
        if (data.job_id) {
          setExpandedJobId(data.job_id);
          setTimeout(() => {
            const el = document.getElementById(`job-card-${data.job_id}`);
            if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }, 100);
        }
        return;
      }

      setSuccessMsg(
        data.message ||
          `Ingestion task started (${data.type === 'playlist' ? 'Playlist' : 'Video'}). Tracking progress in Current Jobs.`
      );
      setUrl('');
      await fetchJobs();
      if (onVideoAdded) onVideoAdded();
    } catch (err: any) {
      setError(err.message || 'An error occurred while submitting video.');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (jobId: string) => {
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || 'Failed to retry job');
      }
      if (data.message) {
        setSuccessMsg(data.message);
      }
      await fetchJobs();
      if (onVideoAdded) onVideoAdded();
    } catch (err: any) {
      console.error('Failed to retry job:', err);
      setError(err.message || 'Failed to retry job');
    }
  };

  const handleCancel = async (jobId: string) => {
    // Optimistically update UI immediately so displayed state is instantaneous
    setJobs((prev) =>
      prev.map((j) =>
        j.id === jobId
          ? {
              ...j,
              status: 'cancelled',
              stage: undefined,
              error_message: 'Ingestion cancelled by user',
            }
          : j
      )
    );

    try {
      const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      if (res.ok) {
        await fetchJobs();
      }
    } catch (err) {
      console.error('Failed to cancel job:', err);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
      if (res.ok) {
        setJobs((prev) => prev.filter((j) => j.id !== jobId));
      }
    } catch (err) {
      console.error('Failed to delete job:', err);
    }
  };

  const getJobProgress = (job: JobItem): number => {
    if (job.status === 'done') return 100;
    if (job.status === 'failed' || job.status === 'cancelled') return 0;
    if (job.type === 'playlist') {
      const total = job.progress_total || 1;
      const current = job.progress_current || 0;
      return Math.min(100, Math.round((current / total) * 100));
    }
    switch (job.stage) {
      case 'downloading':
        return 25;
      case 'transcribing':
        return 60;
      case 'indexing':
        return 90;
      case 'waiting_on_rate_limit':
        return 75;
      default:
        return job.status === 'queued' ? 10 : 50;
    }
  };

  return (
    <div className="max-w-[1100px] mx-auto px-4 md:px-12 py-10 flex flex-col min-h-full selection:bg-[#dbdeff] selection:text-[#0d0c25]">
      {/* Header */}
      <header className="mb-10">
        <h2
          id="ingest-title"
          className="font-['Newsreader'] text-[42px] md:text-[48px] font-semibold text-[#0d0c25] dark:text-[#ffffff] tracking-[-0.02em] leading-[1.1] mb-2"
        >
          Ingest Material
        </h2>
        <p className="font-['Hanken_Grotesk'] text-[17px] md:text-[18px] text-[#47464d] dark:text-[#cdc5c0] max-w-2xl leading-[1.6]">
          Add YouTube links to your archive. The system will download transcripts, extract metadata, and index the content for structured semantic search.
        </p>
      </header>

      {/* Input Form Section (The "Desk") */}
      <section
        id="ingest-desk-card"
        className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl p-6 md:p-8 mb-12 shadow-sm relative overflow-hidden"
      >
        {/* Subtle background grid texture */}
        <div
          className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05] pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(var(--text-main, #0d0c25) 1px, transparent 1px)`,
            backgroundSize: '24px 24px',
          }}
        />

        <div className="relative z-10">
          <label
            htmlFor="youtube-url-input"
            className="block font-['Newsreader'] text-[24px] font-medium text-[#0d0c25] dark:text-[#ffffff] mb-2"
          >
            Add YouTube URL
          </label>
          <p className="font-['Hanken_Grotesk'] text-[15px] text-[#47464d] dark:text-[#cdc5c0] mb-6">
            Paste a link to any lecture, academic seminar, or playlist.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <span className="material-symbols-outlined absolute left-4 top-3.5 text-[#78767e] dark:text-[#918b86]">
                  link
                </span>
                <input
                  id="youtube-url-input"
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="w-full pl-12 pr-4 py-3.5 bg-[#fbf9f9] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg font-['JetBrains_Mono'] text-[14px] text-[#221922] dark:text-[#ffffff] placeholder:text-[#78767e] focus:outline-none focus:ring-2 focus:ring-[#0d0c25] dark:focus:ring-[#e2dfff] transition-all"
                  required
                />
              </div>
              <button
                id="ingest-submit-btn"
                type="submit"
                disabled={loading}
                className="px-8 py-3.5 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-lg font-['JetBrains_Mono'] text-[13px] font-bold uppercase tracking-wider hover:opacity-90 disabled:opacity-50 transition-all flex items-center justify-center space-x-2 cursor-pointer shadow-sm shrink-0"
              >
                {loading ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[18px]">
                      sync
                    </span>
                    <span>Queuing...</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[18px]">add_circle</span>
                    <span>Ingest Video</span>
                  </>
                )}
              </button>
            </div>

            {error && (
              <div className="p-3 bg-[#ffdad6] dark:bg-[#3b1212] border border-[#ffb4ab] dark:border-[#93000a] text-[#ba1a1a] dark:text-[#ffb4ab] text-sm rounded-lg flex items-center space-x-2 font-['Hanken_Grotesk']">
                <span className="material-symbols-outlined text-[18px]">error</span>
                <span>{error}</span>
              </div>
            )}

            {successMsg && (
              <div className="p-3 bg-[#dbdeff] dark:bg-[#22223b] border border-[#c1c4e5] dark:border-[#78767e] text-[#0d0c25] dark:text-[#e2dfff] text-sm rounded-lg flex items-center space-x-2 font-['Hanken_Grotesk']">
                <span className="material-symbols-outlined text-[18px]">check_circle</span>
                <span>{successMsg}</span>
              </div>
            )}
          </form>
        </div>
      </section>

      {/* Current Jobs Section (The "Active Tasks") */}
      <section id="current-jobs-section">
        <div className="flex items-center justify-between mb-6">
          <h3
            id="current-jobs-header"
            className="font-['Newsreader'] text-[28px] md:text-[32px] font-medium text-[#0d0c25] dark:text-[#ffffff]"
          >
            Current Jobs
          </h3>
          <div className="font-['JetBrains_Mono'] text-[13px] font-medium text-[#47464d] dark:text-[#918b86] bg-[#eedeeb] dark:bg-[#282421] px-3 py-1 rounded-full border border-[#c8c5ce] dark:border-[#78767e]">
            {jobs.length} Tasks
          </div>
        </div>

        <div className="space-y-4">
          {jobs.length === 0 && (
            <div className="text-center py-12 border border-dashed border-[#c8c5ce] dark:border-[#78767e] rounded-xl text-[#78767e] dark:text-[#918b86] font-['Hanken_Grotesk'] text-[15px]">
              No active or recent ingestion jobs. Submit a YouTube link above to start processing.
            </div>
          )}

          {jobs.map((job) => {
            const isTerminal = job.status === 'done' || job.status === 'failed' || job.status === 'cancelled';
            const progress = getJobProgress(job);

            // Render Playlist Card with accordion
            if (job.type === 'playlist') {
              const isExpanded = expandedJobId === job.id;
              return (
                <article
                  key={job.id}
                  id={`job-card-${job.id}`}
                  className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg p-5 transition-all shadow-xs"
                >
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-start space-x-4">
                      <div className="mt-1 w-10 h-10 rounded bg-[#e6d5e2] dark:bg-[#282421] flex items-center justify-center shrink-0 border border-[#c8c5ce] dark:border-[#78767e] text-[#47464d] dark:text-[#918b86]">
                        <span className="material-symbols-outlined">playlist_play</span>
                      </div>
                      <div>
                        <h4 className="font-['Newsreader'] text-[20px] font-medium text-[#221922] dark:text-[#ffffff] leading-tight mb-1">
                          {job.title}
                        </h4>
                        <div className="flex items-center space-x-3 font-['JetBrains_Mono'] text-[13px] text-[#47464d] dark:text-[#918b86]">
                          <span className="text-xs uppercase tracking-wider text-[#595d78] dark:text-[#e2dfff]">
                            Playlist
                          </span>
                          <span>•</span>
                          <span>{job.progress_current}/{job.progress_total} videos</span>
                        </div>
                      </div>
                    </div>

                    <div className="w-full sm:w-auto shrink-0 flex items-center justify-between sm:justify-end space-x-3">
                      <div className="font-['JetBrains_Mono'] text-[14px] text-[#78767e] dark:text-[#c8c5ce]">
                        [{job.stage || (job.status === 'done' ? 'done' : job.status)}{' '}
                        <span className="text-[#221922] dark:text-[#ffffff] font-bold">
                          {progress}%
                        </span>
                        ]
                      </div>

                      {!isTerminal && (
                        <button
                          onClick={() => handleCancel(job.id)}
                          className="px-3 py-1 text-xs border border-[#ba1a1a] dark:border-[#ffb4ab] text-[#ba1a1a] dark:text-[#ffb4ab] rounded font-['JetBrains_Mono'] font-semibold hover:bg-[#ffdad6] dark:hover:bg-[#3b1212] transition-colors cursor-pointer"
                        >
                          Cancel
                        </button>
                      )}

                      {isTerminal && (
                        <button
                          onClick={() => handleDeleteJob(job.id)}
                          className="p-1.5 rounded-md hover:bg-[#eedeeb] dark:hover:bg-[#282421] text-[#78767e] hover:text-[#ba1a1a] transition-colors cursor-pointer"
                          title="Dismiss job from history"
                        >
                          <span className="material-symbols-outlined text-[18px]">close</span>
                        </button>
                      )}

                      <button
                        onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                        className="p-1.5 rounded-md hover:bg-[#eedeeb] dark:hover:bg-[#282421] text-[#47464d] dark:text-[#918b86] transition-colors cursor-pointer"
                        title={isExpanded ? 'Collapse sub-videos' : 'Expand sub-videos'}
                      >
                        <span className="material-symbols-outlined">
                          {isExpanded ? 'expand_less' : 'expand_more'}
                        </span>
                      </button>
                    </div>
                  </div>

                  {/* Expandable Details */}
                  {isExpanded && (
                    <div className="playlist-details mt-4 pt-4 border-t border-[#c8c5ce] dark:border-[#78767e] border-dashed">
                      <ul className="space-y-2.5 pl-4 sm:pl-14 font-['JetBrains_Mono'] text-[13px]">
                        {job.sub_jobs?.slice(0, 4).map((sub) => (
                          <li
                            key={sub.video_id}
                            className={`flex items-center justify-between ${
                              sub.status === 'done'
                                ? 'text-[#47464d] dark:text-[#918b86]'
                                : sub.status === 'transcribing' || sub.status === 'indexing'
                                ? 'text-[#221922] dark:text-[#ffffff]'
                                : 'text-[#78767e]'
                            }`}
                          >
                            <div className="flex items-center space-x-2 truncate">
                              {sub.status === 'done' ? (
                                <span className="material-symbols-outlined text-[16px] text-[#0d0c25] dark:text-[#e2dfff]">
                                  check_circle
                                </span>
                              ) : sub.status === 'transcribing' || sub.status === 'indexing' ? (
                                <span className="w-1.5 h-1.5 rounded-full bg-[#595d78] dark:bg-[#e2dfff] animate-pulse ml-1 mr-[2px]" />
                              ) : (
                                <span className="material-symbols-outlined text-[16px]">pending</span>
                              )}
                              <span className="truncate">{sub.title}</span>
                            </div>
                            <span
                              className={`shrink-0 ml-4 ${
                                sub.status === 'transcribing'
                                  ? 'text-[#595d78] dark:text-[#e2dfff]'
                                  : ''
                              }`}
                            >
                              [{sub.status}]
                            </span>
                          </li>
                        ))}
                        {(job.sub_jobs?.length || 0) > 4 && (
                          <li className="pt-2 text-xs text-[#78767e] italic">
                            ... {(job.sub_jobs?.length || 0) - 4} more videos
                          </li>
                        )}
                      </ul>
                    </div>
                  )}
                </article>
              );
            }

            // Render Failed Card
            if (job.status === 'failed') {
              return (
                <article
                  key={job.id}
                  id={`job-failed-${job.id}`}
                  className="bg-[#ffffff] dark:bg-[#222230] border border-[#ffdad6] dark:border-[#5a1b1b] rounded-lg p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-xs"
                >
                  <div className="flex items-start space-x-4">
                    <div className="mt-1 w-10 h-10 rounded bg-[#ffdad6] dark:bg-[#3b1212] flex items-center justify-center shrink-0 border border-[#ffb4ab] dark:border-[#93000a] text-[#ba1a1a] dark:text-[#ffb4ab]">
                      <span className="material-symbols-outlined">error</span>
                    </div>
                    <div>
                      <h4 className="font-['Newsreader'] text-[20px] font-medium text-[#221922] dark:text-[#ffffff] leading-tight mb-1 line-through decoration-[#ba1a1a] dark:decoration-[#ffb4ab] decoration-2 opacity-80">
                        {job.title}
                      </h4>
                      <p className="font-['Hanken_Grotesk'] text-[14px] text-[#ba1a1a] dark:text-[#ffb4ab] mt-1 max-w-lg leading-relaxed">
                        {job.error_message ||
                          "Processing failed. Please check the logs or retry with another video."}
                      </p>
                    </div>
                  </div>

                  <div className="w-full sm:w-auto shrink-0 flex items-center space-x-3">
                    <div className="font-['JetBrains_Mono'] text-[14px] text-[#ba1a1a] dark:text-[#ffb4ab] font-bold tracking-wide">
                      [failed]
                    </div>
                    <button
                      onClick={() => handleRetry(job.id)}
                      className="px-3 py-1.5 border border-[#ba1a1a] dark:border-[#ffb4ab] text-[#ba1a1a] dark:text-[#ffb4ab] rounded font-['JetBrains_Mono'] text-[12px] font-bold uppercase hover:bg-[#ffdad6] dark:hover:bg-[#3b1212] transition-colors cursor-pointer"
                    >
                      Retry
                    </button>
                    <button
                      onClick={() => handleDeleteJob(job.id)}
                      className="p-1.5 rounded-md hover:bg-[#ffdad6] dark:hover:bg-[#3b1212] text-[#ba1a1a] dark:text-[#ffb4ab] transition-colors cursor-pointer"
                      title="Dismiss job from history"
                    >
                      <span className="material-symbols-outlined text-[18px]">close</span>
                    </button>
                  </div>
                </article>
              );
            }

            // Render Cancelled Card
            if (job.status === 'cancelled') {
              return (
                <article
                  key={job.id}
                  id={`job-cancelled-${job.id}`}
                  className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-xs opacity-80"
                >
                  <div className="flex items-start space-x-4">
                    <div className="mt-1 w-10 h-10 rounded bg-[#eedeeb] dark:bg-[#282421] flex items-center justify-center shrink-0 border border-[#c8c5ce] dark:border-[#78767e] text-[#78767e] dark:text-[#918b86]">
                      <span className="material-symbols-outlined">cancel</span>
                    </div>
                    <div>
                      <h4 className="font-['Newsreader'] text-[20px] font-medium text-[#221922] dark:text-[#ffffff] leading-tight mb-1">
                        {job.title}
                      </h4>
                      <p className="font-['Hanken_Grotesk'] text-[14px] text-[#78767e] dark:text-[#918b86] mt-1 max-w-lg leading-relaxed">
                        {job.error_message || "Ingestion was cancelled."}
                      </p>
                    </div>
                  </div>

                  <div className="w-full sm:w-auto shrink-0 flex items-center space-x-3">
                    <div className="font-['JetBrains_Mono'] text-[14px] text-[#78767e] dark:text-[#918b86] font-bold tracking-wide">
                      [cancelled]
                    </div>
                    <button
                      onClick={() => handleRetry(job.id)}
                      className="px-3 py-1.5 border border-[#78767e] text-[#47464d] dark:text-[#cdc5c0] rounded font-['JetBrains_Mono'] text-[12px] font-bold uppercase hover:bg-[#eedeeb] dark:hover:bg-[#282421] transition-colors cursor-pointer"
                    >
                      Retry
                    </button>
                    <button
                      onClick={() => handleDeleteJob(job.id)}
                      className="p-1.5 rounded-md hover:bg-[#eedeeb] dark:hover:bg-[#282421] text-[#78767e] transition-colors cursor-pointer"
                      title="Dismiss job from history"
                    >
                      <span className="material-symbols-outlined text-[18px]">close</span>
                    </button>
                  </div>
                </article>
              );
            }

            // Render Processing or Done Single Video Card
            const isDone = job.status === 'done';
            return (
              <article
                key={job.id}
                id={`job-active-${job.id}`}
                className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-xs"
              >
                <div className="flex items-start space-x-4">
                  <div className="mt-1 w-10 h-10 rounded bg-[#dbdeff] dark:bg-[#22223b] flex items-center justify-center shrink-0 border border-[#c1c4e5] dark:border-[#78767e] text-[#595d78] dark:text-[#e2dfff]">
                    <span className="material-symbols-outlined">
                      {isDone ? 'check_circle' : 'play_circle'}
                    </span>
                  </div>
                  <div>
                    <h4 className="font-['Newsreader'] text-[20px] font-medium text-[#221922] dark:text-[#ffffff] leading-tight mb-1">
                      {job.title}
                    </h4>
                    <div className="flex items-center space-x-3 font-['JetBrains_Mono'] text-[13px] text-[#47464d] dark:text-[#918b86]">
                      <span className="text-xs uppercase tracking-wider text-[#595d78] dark:text-[#e2dfff]">
                        Video
                      </span>
                      <span>•</span>
                      <span>{isDone ? 'Indexed & Ready' : 'Processing'}</span>
                    </div>
                  </div>
                </div>

                <div className="w-full sm:w-64 shrink-0 flex flex-col items-end">
                  <div className="flex items-center space-x-2 mb-2 font-['JetBrains_Mono'] text-[14px]">
                    {!isDone && (
                      <span className="w-2 h-2 rounded-full bg-[#595d78] dark:bg-[#e2dfff] animate-pulse" />
                    )}
                    <span className="text-[#595d78] dark:text-[#e2dfff]">
                      [{job.stage || (isDone ? 'ready' : 'transcribing')}]
                    </span>
                    <span className="text-[#47464d] dark:text-[#918b86]">{progress}%</span>
                    {isDone ? (
                      <button
                        onClick={() => handleDeleteJob(job.id)}
                        className="ml-2 p-1 rounded hover:bg-[#eedeeb] dark:hover:bg-[#282421] text-[#78767e] hover:text-[#ba1a1a] transition-colors cursor-pointer"
                        title="Dismiss job from history"
                      >
                        <span className="material-symbols-outlined text-[16px]">close</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleCancel(job.id)}
                        className="ml-2 px-2 py-0.5 text-xs border border-[#ba1a1a] dark:border-[#ffb4ab] text-[#ba1a1a] dark:text-[#ffb4ab] rounded font-['JetBrains_Mono'] hover:bg-[#ffdad6] dark:hover:bg-[#3b1212] transition-colors cursor-pointer"
                        title="Cancel job"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                  <div className="w-full h-1.5 bg-[#eedeeb] dark:bg-[#1a1a24] rounded-full overflow-hidden border border-[#c8c5ce] dark:border-[#78767e] border-opacity-50">
                    <div
                      className="h-full bg-[#595d78] dark:bg-[#e2dfff] transition-all duration-500 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
};
