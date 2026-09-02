import React, { useState } from 'react';
import { SearchResponse } from '../types';

interface SearchScreenProps {
  onSelectVideoTimestamp: (videoId: string, startSeconds: number) => void;
}

export const SearchScreen: React.FC<SearchScreenProps> = ({
  onSelectVideoTimestamp,
}) => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const suggestedQueries = [
    'How does backpropagation work?',
    'Quantum entanglement',
    'The Pont du Gard construction',
    'Scaled dot-product attention formula',
    'Roman aqueducts gravity gradient',
  ];

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setQuery(searchQuery);

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery.trim() }),
      });

      if (res.ok) {
        const data = await res.json();
        setSearchResponse(data);
      }
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const formatSeconds = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-[1100px] mx-auto px-4 md:px-12 py-10 flex flex-col min-h-full">
      {/* Oversized Search Input Bar */}
      <div className="relative mb-10">
        <div className="relative flex items-center shadow-sm">
          <span className="material-symbols-outlined absolute left-5 text-[#47464d] dark:text-[#cdc5c0] text-[26px] pointer-events-none">
            search
          </span>
          <input
            id="search-input-field"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSearch(query);
            }}
            placeholder="Search anything you've watched..."
            className="w-full pl-14 pr-28 py-5 bg-[#ffffff] dark:bg-[#222230] border-2 border-[#c8c5ce] dark:border-[#78767e] rounded-2xl font-['Hanken_Grotesk'] text-[20px] text-[#0d0c25] dark:text-[#ffffff] placeholder:text-[#78767e] focus:border-[#0d0c25] dark:focus:border-[#e2dfff] outline-none transition-all"
          />
          <button
            onClick={() => handleSearch(query)}
            disabled={loading || !query.trim()}
            className="absolute right-3 px-5 py-3 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-xl font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
          >
            {loading ? (
              <span className="material-symbols-outlined animate-spin text-[18px]">sync</span>
            ) : (
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            )}
            <span>Search</span>
          </button>
        </div>
      </div>

      {/* State 1: Initial State (No search performed yet) */}
      {!searchResponse && !loading && (
        <div className="my-auto py-12 text-center max-w-2xl mx-auto">
          <div className="w-16 h-16 rounded-2xl bg-[#dbdeff] dark:bg-[#22223b] flex items-center justify-center mx-auto mb-6 text-[#595d78] dark:text-[#e2dfff] border border-[#c8c5ce] dark:border-[#78767e]">
            <span className="material-symbols-outlined text-[36px]">travel_explore</span>
          </div>

          <h3
            id="study-carrel-heading"
            className="font-['Newsreader'] text-[36px] md:text-[42px] font-semibold text-[#0d0c25] dark:text-[#ffffff] tracking-tight mb-3"
          >
            Your Digital Study Carrel
          </h3>
          <p className="font-['Hanken_Grotesk'] text-[17px] text-[#47464d] dark:text-[#cdc5c0] leading-relaxed mb-10">
            Search across transcripts, visual text, and metadata from all videos in your library.
          </p>

          <div>
            <div className="font-['JetBrains_Mono'] text-[11px] font-bold text-[#78767e] dark:text-[#c8c5ce] uppercase tracking-widest mb-4">
              SUGGESTED QUERIES
            </div>
            <div className="flex flex-wrap justify-center gap-2.5">
              {suggestQueriesChips(suggestedQueries, handleSearch)}
            </div>
          </div>
        </div>
      )}

      {/* State 2: Results State */}
      {searchResponse && (
        <div className="space-y-10">
          {/* AI-Synthesized Answer Box */}
          <section
            id="ai-synthesis-box"
            className="bg-[#ffffff] dark:bg-[#222230] border-2 border-[#595d78] dark:border-[#e2dfff] rounded-2xl p-6 md:p-8 shadow-sm relative overflow-hidden"
          >
            <div className="flex items-center space-x-2.5 mb-4">
              <span className="w-2.5 h-2.5 rounded-full bg-[#595d78] dark:bg-[#e2dfff] animate-pulse" />
              <span className="font-['JetBrains_Mono'] text-[12px] font-bold tracking-widest text-[#595d78] dark:text-[#e2dfff] uppercase">
                AI SUMMARY • GEMINI RAG SYNTHESIS
              </span>
            </div>

            <div className="font-['Hanken_Grotesk'] text-[17px] md:text-[18px] text-[#221922] dark:text-[#fdecf9] leading-[1.7] space-y-4 whitespace-pre-line">
              {searchResponse.answer}
            </div>

            {searchResponse.results.length > 0 && (
              <div className="mt-6 pt-5 border-t border-[#c8c5ce]/60 dark:border-[#78767e]/60 flex flex-wrap items-center gap-2">
                <span className="font-['JetBrains_Mono'] text-[11px] text-[#47464d] dark:text-[#cdc5c0] uppercase tracking-wider mr-2">
                  Source Timestamps:
                </span>
                {searchResponse.results.slice(0, 4).map((r, i) => (
                  <button
                    key={i}
                    onClick={() => onSelectVideoTimestamp(r.video_id, r.start_seconds)}
                    className="px-3 py-1 bg-[#dbdeff] hover:bg-[#c5c3e4] dark:bg-[#22223b] dark:hover:bg-[#372d37] text-[#0d0c25] dark:text-[#e2dfff] rounded-full font-['JetBrains_Mono'] text-[12px] font-bold flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[14px]">play_circle</span>
                    <span>
                      {r.title.slice(0, 18)}... [{formatSeconds(r.start_seconds)}]
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* Individual Excerpt Matches */}
          <section className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#c8c5ce] dark:border-[#78767e]">
              <h4 className="font-['Newsreader'] text-[24px] font-semibold text-[#0d0c25] dark:text-[#ffffff]">
                Indexed Transcript Excerpts ({searchResponse.results.length})
              </h4>
              <span className="font-['JetBrains_Mono'] text-[11px] text-[#78767e] uppercase tracking-wider">
                Ranked by Cosine Similarity
              </span>
            </div>

            <div className="space-y-4">
              {searchResponse.results.map((res, idx) => (
                <article
                  key={idx}
                  className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl p-5 md:p-6 transition-all hover:border-[#0d0c25] dark:hover:border-[#e2dfff] flex flex-col md:flex-row gap-5"
                >
                  {/* Video Thumbnail */}
                  <div
                    onClick={() => onSelectVideoTimestamp(res.video_id, res.start_seconds)}
                    className="relative w-full md:w-56 aspect-video shrink-0 bg-[#1a1a24] rounded-lg overflow-hidden cursor-pointer group"
                  >
                    <img
                      src={res.thumbnail_url}
                      alt={res.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                    />
                    <div className="absolute inset-0 bg-[#0d0c25]/30 group-hover:bg-[#0d0c25]/10 flex items-center justify-center transition-colors">
                      <span className="material-symbols-outlined text-white text-[32px] opacity-80 group-hover:opacity-100 group-hover:scale-110 transition-all">
                        play_circle
                      </span>
                    </div>
                    <div className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 bg-[#0d0c25]/85 text-white rounded font-['JetBrains_Mono'] text-[10px]">
                      {formatSeconds(res.start_seconds)}
                    </div>
                  </div>

                  {/* Details */}
                  <div className="flex-1 flex flex-col justify-between">
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <h5
                          onClick={() => onSelectVideoTimestamp(res.video_id, res.start_seconds)}
                          className="font-['Newsreader'] text-[20px] font-semibold text-[#0d0c25] dark:text-[#ffffff] hover:text-[#595d78] cursor-pointer"
                        >
                          {res.title}
                        </h5>
                        <span className="font-['JetBrains_Mono'] text-[11px] px-2 py-0.5 bg-[#eedeeb] dark:bg-[#282421] text-[#47464d] dark:text-[#cdc5c0] rounded-full shrink-0">
                          {Math.round((res.score || 0.85) * 100)}% match
                        </span>
                      </div>

                      <p className="font-['Hanken_Grotesk'] text-[15px] text-[#221922] dark:text-[#fdecf9] leading-relaxed mb-4">
                        "{res.text}"
                      </p>
                    </div>

                    <div className="flex items-center justify-between pt-3 border-t border-[#c8c5ce]/40 dark:border-[#78767e]/40">
                      <button
                        onClick={() => onSelectVideoTimestamp(res.video_id, res.start_seconds)}
                        className="font-['JetBrains_Mono'] text-[12px] text-[#595d78] dark:text-[#e2dfff] font-bold flex items-center gap-1 hover:underline cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[16px]">play_arrow</span>
                        <span>Jump to [{formatSeconds(res.start_seconds)}]</span>
                      </button>

                      <button
                        onClick={() => handleCopy(res.text, `chunk-${idx}`)}
                        className="font-['JetBrains_Mono'] text-[11px] text-[#47464d] dark:text-[#cdc5c0] hover:text-[#0d0c25] flex items-center gap-1 cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[14px]">
                          {copiedId === `chunk-${idx}` ? 'check' : 'content_copy'}
                        </span>
                        <span>{copiedId === `chunk-${idx}` ? 'Copied' : 'Copy excerpt'}</span>
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
};

function suggestQueriesChips(
  queries: string[],
  onSelect: (q: string) => void
) {
  return queries.map((q, i) => (
    <button
      key={i}
      onClick={() => onSelect(q)}
      className="px-4 py-2 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] hover:border-[#0d0c25] dark:hover:border-[#e2dfff] rounded-full font-['Hanken_Grotesk'] text-[14px] text-[#221922] dark:text-[#ffffff] transition-all hover:bg-[#f4e3f1] dark:hover:bg-[#282421] cursor-pointer"
    >
      "{q}"
    </button>
  ));
}
