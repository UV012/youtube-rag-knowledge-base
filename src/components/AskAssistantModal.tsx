import React, { useState } from 'react';

interface AskAssistantModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectVideoTimestamp: (videoId: string, startSeconds: number) => void;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{
    title: string;
    videoId: string;
    seconds: number;
  }>;
}

export const AskAssistantModal: React.FC<AskAssistantModalProps> = ({
  isOpen,
  onClose,
  onSelectVideoTimestamp,
}) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        'Hello Archivist. I have indexed your library transcripts. Ask me any conceptual question or ask me to cross-reference multiple lectures across your knowledge base.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userQ = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userQ }]);
    setLoading(true);

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQ }),
      });

      if (res.ok) {
        const data = await res.json();
        const sources = data.results.slice(0, 3).map((r: any) => ({
          title: r.title,
          videoId: r.video_id,
          seconds: r.start_seconds,
        }));

        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.answer,
            sources,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'I encountered an error querying your study transcripts. Please try again.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const formatSeconds = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0d0c25]/60 backdrop-blur-xs">
      <div className="bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-2xl w-full max-w-2xl h-[650px] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#c8c5ce] dark:border-[#78767e] flex items-center justify-between bg-[#fff7fa] dark:bg-[#1a1a24]">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-full bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] flex items-center justify-center">
              <span className="material-symbols-outlined text-[18px]">smart_toy</span>
            </div>
            <div>
              <h3 className="font-['Newsreader'] text-[20px] font-semibold text-[#0d0c25] dark:text-[#ffffff] leading-tight">
                Study Carrel Assistant
              </h3>
              <p className="font-['JetBrains_Mono'] text-[11px] text-[#47464d] dark:text-[#cdc5c0]">
                Gemini 2.0 Flash / 3.7 Flash RAG Engine
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[#eedeeb] dark:hover:bg-[#282421] text-[#47464d] dark:text-[#cdc5c0] cursor-pointer"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Conversation Stream */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 font-['Hanken_Grotesk'] text-[15px]">
          {messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl p-4 leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-br-xs'
                    : 'bg-[#fff7fa] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] text-[#221922] dark:text-[#fdecf9] rounded-bl-xs shadow-xs'
                }`}
              >
                <div className="whitespace-pre-line">{m.content}</div>

                {/* Sources chips */}
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-[#c8c5ce]/40 dark:border-[#78767e]/40 flex flex-wrap gap-2">
                    {m.sources.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          onSelectVideoTimestamp(s.videoId, s.seconds);
                          onClose();
                        }}
                        className="px-2.5 py-1 bg-[#dbdeff] hover:bg-[#c5c3e4] dark:bg-[#22223b] text-[#0d0c25] dark:text-[#e2dfff] rounded font-['JetBrains_Mono'] text-[11px] font-bold flex items-center gap-1 cursor-pointer transition-colors"
                      >
                        <span className="material-symbols-outlined text-[13px]">play_circle</span>
                        <span>
                          {s.title.slice(0, 15)}... [{formatSeconds(s.seconds)}]
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-[#fff7fa] dark:bg-[#1a1a24] border border-[#c8c5ce] dark:border-[#78767e] rounded-2xl p-4 flex items-center space-x-2 text-[#595d78] dark:text-[#e2dfff]">
                <span className="w-2 h-2 rounded-full bg-[#595d78] animate-ping" />
                <span className="font-['JetBrains_Mono'] text-[12px]">
                  Synthesizing cited transcript answer...
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Input Footer */}
        <form
          onSubmit={handleSend}
          className="p-4 border-t border-[#c8c5ce] dark:border-[#78767e] bg-[#fff7fa] dark:bg-[#1a1a24] flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question across all your lecture transcripts..."
            className="flex-1 px-4 py-3 bg-[#ffffff] dark:bg-[#222230] border border-[#c8c5ce] dark:border-[#78767e] rounded-xl font-['Hanken_Grotesk'] text-[15px] text-[#221922] dark:text-[#ffffff] placeholder:text-[#78767e] outline-none focus:border-[#0d0c25] dark:focus:border-[#e2dfff]"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-5 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-xl font-['JetBrains_Mono'] text-[12px] font-bold uppercase hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">send</span>
          </button>
        </form>
      </div>
    </div>
  );
};
