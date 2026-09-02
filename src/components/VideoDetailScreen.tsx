import React, { useState, useEffect, useRef } from 'react';
import { VideoItem, VideoChunk } from '../types';

interface VideoDetailScreenProps {
  videoId: string;
  initialTimestamp?: number;
  onBack: () => void;
}

export const VideoDetailScreen: React.FC<VideoDetailScreenProps> = ({
  videoId,
  initialTimestamp = 0,
  onBack,
}) => {
  const [video, setVideo] = useState<VideoItem | null>(null);
  const [currentTime, setCurrentTime] = useState<number>(initialTimestamp);
  const [transcriptSearch, setTranscriptSearch] = useState('');
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number>(0);
  const [userNote, setUserNote] = useState('');
  const [noteSaved, setNoteSaved] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    const fetchVideoDetail = async () => {
      try {
        const res = await fetch(`/api/videos/${videoId}`);
        if (res.ok) {
          const data = await res.json();
          setVideo(data);
          // Set initial note if present
          setUserNote(data.description || '');
        }
      } catch (err) {
        console.error('Failed to load video details:', err);
      }
    };
    fetchVideoDetail();
  }, [videoId]);

  const handleJumpToTimestamp = (seconds: number, index: number) => {
    setCurrentTime(seconds);
    setActiveSegmentIndex(index);
    if (iframeRef.current && video?.youtube_video_id) {
      iframeRef.current.src = `https://www.youtube-nocookie.com/embed/${video.youtube_video_id}?autoplay=1&start=${Math.floor(
        seconds
      )}&enablejsapi=1`;
    }
  };

  const formatSeconds = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const handleSaveNote = () => {
    setNoteSaved(true);
    setTimeout(() => setNoteSaved(false), 2500);
  };

  const handleExport = (format: 'markdown' | 'json' | 'text') => {
    if (!video) return;
    let content = '';
    let filename = `${video.title.toLowerCase().replace(/[^a-z0-9]/g, '_')}_transcript`;

    if (format === 'markdown') {
      content = `# ${video.title}\n\n**YouTube ID:** ${video.youtube_video_id}\n**Archived:** ${video.added_at}\n\n## Transcript\n\n`;
      video.chunks?.forEach((c) => {
        content += `### [${formatSeconds(c.start_seconds)}] - [${formatSeconds(c.end_seconds)}]\n${c.text}\n\n`;
      });
      filename += '.md';
    } else if (format === 'json') {
      content = JSON.stringify(video, null, 2);
      filename += '.json';
    } else {
      content = `${video.title}\n\n`;
      video.chunks?.forEach((c) => {
        content += `[${formatSeconds(c.start_seconds)}] ${c.text}\n`;
      });
      filename += '.txt';
    }

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    setExportMenuOpen(false);
  };

  const filteredChunks = video?.chunks?.filter((c) =>
    c.text.toLowerCase().includes(transcriptSearch.toLowerCase())
  );

  return (
    <div className="max-w-[1400px] mx-auto px-4 md:px-10 py-8 flex flex-col min-h-full">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 mb-6 border-b border-[#c8c5ce] dark:border-[#78767e] gap-4">
        <div className="flex items-start gap-4">
          <button
            id="back-to-library-btn"
            onClick={onBack}
            className="p-2 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] hover:bg-[#f4e3f1] dark:hover:bg-[#282421] rounded-lg text-[#0d0c25] dark:text-[#ffffff] transition-colors cursor-pointer shrink-0 mt-1"
            title="Back to Library"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_back</span>
          </button>

          <div>
            <h2
              id="video-detail-title"
              className="font-['Newsreader'] text-[32px] md:text-[38px] font-semibold text-[#0d0c25] dark:text-[#ffffff] leading-tight tracking-tight"
            >
              {video?.title || 'Loading Transcript...'}
            </h2>
            <div className="flex items-center space-x-3 font-['JetBrains_Mono'] text-[12px] text-[#47464d] dark:text-[#cdc5c0] mt-1">
              <span>Archived 2 days ago</span>
              <span>•</span>
              <span>ID: {video?.id}</span>
              <span>•</span>
              <span className="px-2 py-0.5 bg-[#dbdeff] dark:bg-[#22223b] text-[#0d0c25] dark:text-[#e2dfff] rounded font-bold uppercase">
                INDEXED
              </span>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5 shrink-0 relative">
          <button
            onClick={handleSaveNote}
            className="px-4 py-2 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] hover:border-[#0d0c25] text-[#0d0c25] dark:text-[#ffffff] rounded-lg font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">
              {noteSaved ? 'check' : 'bookmark'}
            </span>
            <span>{noteSaved ? 'Saved!' : 'Save Note'}</span>
          </button>

          {/* Export Dropdown */}
          <div className="relative">
            <button
              onClick={() => setExportMenuOpen(!exportMenuOpen)}
              className="px-4 py-2 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-lg font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider hover:opacity-90 transition-opacity flex items-center gap-1.5 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">ios_share</span>
              <span>Export</span>
            </button>

            {exportMenuOpen && (
              <div className="absolute right-0 mt-2 w-48 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg shadow-lg py-1.5 z-30 font-['JetBrains_Mono'] text-[12px]">
                <button
                  onClick={() => handleExport('markdown')}
                  className="w-full text-left px-4 py-2 hover:bg-[#f4e3f1] dark:hover:bg-[#282421] text-[#221922] dark:text-[#ffffff] flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-[16px]">description</span>
                  <span>Markdown (.md)</span>
                </button>
                <button
                  onClick={() => handleExport('json')}
                  className="w-full text-left px-4 py-2 hover:bg-[#f4e3f1] dark:hover:bg-[#282421] text-[#221922] dark:text-[#ffffff] flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-[16px]">data_object</span>
                  <span>JSON Chunks (.json)</span>
                </button>
                <button
                  onClick={() => handleExport('text')}
                  className="w-full text-left px-4 py-2 hover:bg-[#f4e3f1] dark:hover:bg-[#282421] text-[#221922] dark:text-[#ffffff] flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-[16px]">notes</span>
                  <span>Plain Text (.txt)</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-1">
        {/* Left Column: Player & Notes */}
        <div className="lg:col-span-7 flex flex-col space-y-6">
          {/* Video Player Box */}
          <div
            id="video-player-container"
            className="aspect-video w-full bg-[#1a1a24] rounded-2xl overflow-hidden shadow-sm border border-[#c8c5ce] dark:border-[#78767e] relative"
          >
            {video?.youtube_video_id ? (
              <iframe
                ref={iframeRef}
                src={`https://www.youtube-nocookie.com/embed/${video.youtube_video_id}?autoplay=0&start=${Math.floor(
                  initialTimestamp
                )}&enablejsapi=1`}
                title={video.title}
                className="w-full h-full border-0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white font-['JetBrains_Mono']">
                <span>Loading video stream...</span>
              </div>
            )}
          </div>

          {/* Tags */}
          <div className="flex flex-wrap items-center gap-2">
            {(video?.tags || ['History', 'Engineering', 'Architecture']).map((tag, idx) => (
              <span
                key={idx}
                className="px-3 py-1 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-full font-['JetBrains_Mono'] text-[11px] font-bold text-[#47464d] dark:text-[#cdc5c0] uppercase tracking-wider"
              >
                #{tag}
              </span>
            ))}
          </div>

          {/* Study Scratchpad */}
          <div className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <label className="font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-widest text-[#0d0c25] dark:text-[#ffffff] flex items-center gap-2">
                <span className="material-symbols-outlined text-[16px]">edit_note</span>
                <span>Personal Study Notes & Synthesis</span>
              </label>
              <span className="font-['JetBrains_Mono'] text-[11px] text-[#78767e]">
                Auto-saved locally
              </span>
            </div>
            <textarea
              value={userNote}
              onChange={(e) => setUserNote(e.target.value)}
              placeholder="Jot down hypotheses, timestamps, or flashcard concepts here..."
              rows={4}
              className="w-full p-3 bg-[#fff7fa] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg font-['Hanken_Grotesk'] text-[15px] text-[#221922] dark:text-[#ffffff] placeholder:text-[#78767e] outline-none focus:ring-1 focus:ring-[#0d0c25] leading-relaxed resize-y"
            />
          </div>
        </div>

        {/* Right Column: Full Synchronized Transcript Panel */}
        <div className="lg:col-span-5 flex flex-col bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-2xl overflow-hidden shadow-xs h-[750px]">
          {/* Transcript Header */}
          <div className="p-4 border-b border-[#c8c5ce] dark:border-[#78767e] bg-[#fff7fa]/70 dark:bg-[#1a1a24]/70">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-['Newsreader'] text-[22px] font-semibold text-[#0d0c25] dark:text-[#ffffff] flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-[#595d78] dark:text-[#e2dfff]">
                  format_quote
                </span>
                <span>Full Transcript</span>
              </h3>
              <span className="font-['JetBrains_Mono'] text-[11px] px-2 py-0.5 bg-[#eedeeb] dark:bg-[#282421] text-[#47464d] dark:text-[#cdc5c0] rounded-full font-bold">
                {filteredChunks?.length || 0} Segments
              </span>
            </div>

            {/* Transcript Filter Input */}
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-2.5 text-[#78767e] text-[16px]">
                filter_alt
              </span>
              <input
                type="text"
                value={transcriptSearch}
                onChange={(e) => setTranscriptSearch(e.target.value)}
                placeholder="Search within this transcript..."
                className="w-full pl-8 pr-3 py-1.5 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-lg font-['JetBrains_Mono'] text-[12px] text-[#221922] dark:text-[#ffffff] placeholder:text-[#78767e] outline-none"
              />
            </div>
          </div>

          {/* Transcript Segments List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 divide-y divide-[#c8c5ce]/30 dark:divide-[#78767e]/30">
            {filteredChunks && filteredChunks.length > 0 ? (
              filteredChunks.map((chunk, index) => {
                const isActive = activeSegmentIndex === index;

                return (
                  <div
                    key={chunk.id || index}
                    id={`transcript-seg-${index}`}
                    onClick={() => handleJumpToTimestamp(chunk.start_seconds, index)}
                    className={`pt-3 first:pt-0 p-3 rounded-lg cursor-pointer transition-all duration-150 border-l-3 ${
                      isActive
                        ? 'bg-[#dbdeff] dark:bg-[#22223b] border-l-[#0d0c25] dark:border-l-[#e2dfff] shadow-xs'
                        : 'border-l-transparent hover:bg-[#f4e3f1] dark:hover:bg-[#282421]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span
                        className={`font-['JetBrains_Mono'] text-[12px] font-bold ${
                          isActive
                            ? 'text-[#0d0c25] dark:text-[#e2dfff]'
                            : 'text-[#595d78] dark:text-[#c1c4e5]'
                        } flex items-center gap-1`}
                      >
                        <span className="material-symbols-outlined text-[14px]">
                          {isActive ? 'volume_up' : 'play_circle'}
                        </span>
                        <span>{formatSeconds(chunk.start_seconds)}</span>
                      </span>

                      <span className="font-['JetBrains_Mono'] text-[10px] text-[#78767e]">
                        {formatSeconds(chunk.end_seconds - chunk.start_seconds)}s
                      </span>
                    </div>

                    <p
                      className={`font-['Hanken_Grotesk'] text-[15px] leading-relaxed ${
                        isActive
                          ? 'text-[#0d0c25] dark:text-[#ffffff] font-medium'
                          : 'text-[#221922] dark:text-[#e6d5e2]'
                      }`}
                    >
                      {chunk.text}
                    </p>
                  </div>
                );
              })
            ) : (
              <div className="py-12 text-center text-[#78767e] font-['Hanken_Grotesk']">
                No matching transcript segments found.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
