import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { IngestScreen } from './components/IngestScreen';
import { LibraryScreen } from './components/LibraryScreen';
import { SearchScreen } from './components/SearchScreen';
import { VideoDetailScreen } from './components/VideoDetailScreen';
import { AskAssistantModal } from './components/AskAssistantModal';
import { SettingsModal } from './components/SettingsModal';
import { DataProvider } from './context/DataContext';

export function App() {
  const [currentTab, setCurrentTab] = useState<'search' | 'add' | 'library' | 'detail'>('add');
  const [selectedVideoId, setSelectedVideoId] = useState<string>('a7b9-f21');
  const [initialTimestamp, setInitialTimestamp] = useState<number>(0);
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const handleSelectVideo = (videoId: string, timestamp: number = 0) => {
    setSelectedVideoId(videoId);
    setInitialTimestamp(timestamp);
    setCurrentTab('detail');
  };

  return (
    <DataProvider currentTab={currentTab} setCurrentTab={setCurrentTab}>
      <div className="flex h-screen bg-[#fff7fa] dark:bg-[#1a1a24] text-[#221922] dark:text-[#fdecf9] overflow-hidden font-['Hanken_Grotesk']">
      {/* Sidebar Navigation */}
      <Sidebar
        currentTab={currentTab}
        onTabChange={(tab) => setCurrentTab(tab)}
        onOpenAssistant={() => setIsAssistantOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* Mobile Top Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-[#fff7fa] dark:bg-[#1a1a24] border-b border-[#c8c5ce] dark:border-[#78767e] flex items-center justify-between px-4 z-40">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-full bg-[#eedeeb] overflow-hidden">
            <img
              alt="Research Desk Avatar"
              className="w-full h-full object-cover"
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuBFLpHbP2n14XqAT7Qetbz1RqW-i-0BVXakw7whhozuJGYFPaEALvM-KCEFWpW_E4U8_IIMMK4WdzVFrUYET_r3q2kjycXYnBdS8hE0-C0bHCcbR1d_aals9UN-KidkkaPyGCdTLNhqyYcR-phWlEIUOjx9Usr0OpfIEI1cwNSCnNRpQssvSnk-kOaAYRYAAFnPSqkaHTcNKHyuCVRyMs2Tz_POIu44aJFEjyprbeey9kDFe5iY0uiJ"
            />
          </div>
          <span className="font-['Newsreader'] text-[18px] font-semibold text-[#0d0c25] dark:text-[#ffffff]">
            Research Desk
          </span>
        </div>

        <div className="flex items-center space-x-1">
          <button
            onClick={() => setIsAssistantOpen(true)}
            className="p-2 rounded-lg text-[#0d0c25] dark:text-[#ffffff]"
          >
            <span className="material-symbols-outlined text-[22px]">smart_toy</span>
          </button>
          <button
            onClick={() => setIsSettingsOpen(true)}
            className="p-2 rounded-lg text-[#0d0c25] dark:text-[#ffffff]"
          >
            <span className="material-symbols-outlined text-[22px]">settings</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <main
        id="main-viewport-content"
        className="flex-1 md:pl-64 h-full overflow-y-auto pt-16 md:pt-0 pb-16 md:pb-0"
      >
        {currentTab === 'add' && (
          <IngestScreen onVideoAdded={() => {}} />
        )}

        {currentTab === 'library' && (
          <LibraryScreen
            onSelectVideo={(id) => handleSelectVideo(id, 0)}
            onNavigateAdd={() => setCurrentTab('add')}
          />
        )}

        {currentTab === 'search' && (
          <SearchScreen
            onSelectVideoTimestamp={(videoId, timestamp) =>
              handleSelectVideo(videoId, timestamp)
            }
          />
        )}

        {currentTab === 'detail' && (
          <VideoDetailScreen
            videoId={selectedVideoId}
            initialTimestamp={initialTimestamp}
            onBack={() => setCurrentTab('library')}
          />
        )}
      </main>

      {/* Mobile Bottom Navigation Bar */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 h-16 bg-[#ffffff] dark:bg-[#222230] border-t border-[#c8c5ce] dark:border-[#78767e] flex items-center justify-around z-40">
        <button
          onClick={() => setCurrentTab('search')}
          className={`flex flex-col items-center justify-center w-full h-full ${
            currentTab === 'search'
              ? 'text-[#0d0c25] dark:text-[#e2dfff]'
              : 'text-[#78767e]'
          }`}
        >
          <span className="material-symbols-outlined text-[22px]">search</span>
          <span className="font-['JetBrains_Mono'] text-[10px] uppercase mt-0.5">Search</span>
        </button>

        <button
          onClick={() => setCurrentTab('add')}
          className={`flex flex-col items-center justify-center w-full h-full ${
            currentTab === 'add'
              ? 'text-[#0d0c25] dark:text-[#e2dfff]'
              : 'text-[#78767e]'
          }`}
        >
          <span className="material-symbols-outlined text-[22px]">add_box</span>
          <span className="font-['JetBrains_Mono'] text-[10px] uppercase mt-0.5">Add</span>
        </button>

        <button
          onClick={() => setCurrentTab('library')}
          className={`flex flex-col items-center justify-center w-full h-full ${
            currentTab === 'library' || currentTab === 'detail'
              ? 'text-[#0d0c25] dark:text-[#e2dfff]'
              : 'text-[#78767e]'
          }`}
        >
          <span className="material-symbols-outlined text-[22px]">auto_stories</span>
          <span className="font-['JetBrains_Mono'] text-[10px] uppercase mt-0.5">Library</span>
        </button>
      </div>

      {/* Modals */}
      <AskAssistantModal
        isOpen={isAssistantOpen}
        onClose={() => setIsAssistantOpen(false)}
        onSelectVideoTimestamp={(videoId, timestamp) =>
          handleSelectVideo(videoId, timestamp)
        }
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
      </div>
    </DataProvider>
  );
}

export default App;
