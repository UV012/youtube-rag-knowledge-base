import React from 'react';

interface SidebarProps {
  currentTab: 'search' | 'add' | 'library' | 'detail';
  onTabChange: (tab: 'search' | 'add' | 'library') => void;
  onOpenAssistant: () => void;
  onOpenSettings: () => void;
  isDark?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onTabChange,
  onOpenAssistant,
  onOpenSettings,
}) => {
  return (
    <nav
      id="side-navigation-bar"
      className="hidden md:flex bg-[#fff7fa] dark:bg-[#1a1a24] text-[#0d0c25] dark:text-[#e2dfff] fixed left-0 top-0 h-full w-64 border-r border-[#c8c5ce] dark:border-[#78767e] flex-col py-8 px-4 z-50 transition-all duration-200 ease-in-out select-none"
    >
      {/* Workspace Brand / Header */}
      <div className="mb-8 px-4 flex items-center space-x-3">
        <div className="w-10 h-10 rounded-full bg-[#eedeeb] dark:bg-[#282421] flex-shrink-0 overflow-hidden border border-[#c8c5ce] dark:border-[#78767e]">
          <img
            alt="Research Desk Avatar"
            className="w-full h-full object-cover"
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuBFLpHbP2n14XqAT7Qetbz1RqW-i-0BVXakw7whhozuJGYFPaEALvM-KCEFWpW_E4U8_IIMMK4WdzVFrUYET_r3q2kjycXYnBdS8hE0-C0bHCcbR1d_aals9UN-KidkkaPyGCdTLNhqyYcR-phWlEIUOjx9Usr0OpfIEI1cwNSCnNRpQssvSnk-kOaAYRYAAFnPSqkaHTcNKHyuCVRyMs2Tz_POIu44aJFEjyprbeey9kDFe5iY0uiJ"
          />
        </div>
        <div>
          <h1 className="font-['Newsreader'] text-[20px] font-semibold text-[#0d0c25] dark:text-[#e2dfff] leading-tight">
            Research Desk
          </h1>
          <p className="font-['JetBrains_Mono'] text-[10px] text-[#47464d] dark:text-[#918b86] uppercase tracking-wider">
            Solo Learner Mode
          </p>
        </div>
      </div>

      {/* Main Navigation Links */}
      <div className="flex-1 space-y-1.5">
        {/* Search Link */}
        <button
          id="nav-search-btn"
          onClick={() => onTabChange('search')}
          className={`w-full flex items-center space-x-3 px-4 py-2.5 rounded-lg text-left transition-all duration-150 font-['JetBrains_Mono'] text-[12px] font-bold tracking-wider uppercase ${
            currentTab === 'search'
              ? 'bg-[#dbdeff] dark:bg-[#22223b] text-[#0d0c25] dark:text-[#e2dfff]'
              : 'text-[#47464d] dark:text-[#918b86] hover:bg-[#f4e3f1] dark:hover:bg-[#282421] hover:text-[#0d0c25] dark:hover:text-[#e2dfff]'
          }`}
        >
          <span
            className="material-symbols-outlined text-[20px]"
            style={{ fontVariationSettings: currentTab === 'search' ? "'FILL' 1" : "'FILL' 0" }}
          >
            search
          </span>
          <span>Search</span>
        </button>

        {/* Add Video Link */}
        <button
          id="nav-add-btn"
          onClick={() => onTabChange('add')}
          className={`w-full flex items-center space-x-3 px-4 py-2.5 rounded-lg text-left transition-all duration-150 font-['JetBrains_Mono'] text-[12px] font-bold tracking-wider uppercase ${
            currentTab === 'add'
              ? 'bg-[#dbdeff] dark:bg-[#22223b] text-[#0d0c25] dark:text-[#e2dfff]'
              : 'text-[#47464d] dark:text-[#918b86] hover:bg-[#f4e3f1] dark:hover:bg-[#282421] hover:text-[#0d0c25] dark:hover:text-[#e2dfff]'
          }`}
        >
          <span
            className="material-symbols-outlined text-[20px]"
            style={{ fontVariationSettings: currentTab === 'add' ? "'FILL' 1" : "'FILL' 0" }}
          >
            add_box
          </span>
          <span>Add Video</span>
        </button>

        {/* Library Link */}
        <button
          id="nav-library-btn"
          onClick={() => onTabChange('library')}
          className={`w-full flex items-center space-x-3 px-4 py-2.5 rounded-lg text-left transition-all duration-150 font-['JetBrains_Mono'] text-[12px] font-bold tracking-wider uppercase ${
            currentTab === 'library' || currentTab === 'detail'
              ? 'bg-[#dbdeff] dark:bg-[#22223b] text-[#0d0c25] dark:text-[#e2dfff]'
              : 'text-[#47464d] dark:text-[#918b86] hover:bg-[#f4e3f1] dark:hover:bg-[#282421] hover:text-[#0d0c25] dark:hover:text-[#e2dfff]'
          }`}
        >
          <span
            className="material-symbols-outlined text-[20px]"
            style={{ fontVariationSettings: currentTab === 'library' || currentTab === 'detail' ? "'FILL' 1" : "'FILL' 0" }}
          >
            auto_stories
          </span>
          <span>Library</span>
        </button>
      </div>

      {/* Footer Actions */}
      <div className="space-y-1 pt-4 border-t border-[#c8c5ce] dark:border-[#78767e]">
        <button
          id="nav-ask-assistant-btn"
          onClick={onOpenAssistant}
          className="w-full mb-4 px-4 py-2.5 bg-[#0d0c25] text-white dark:bg-[#e2dfff] dark:text-[#191932] rounded-lg font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider hover:opacity-90 transition-opacity flex items-center justify-center space-x-2 shadow-sm"
        >
          <span className="material-symbols-outlined text-[18px]">smart_toy</span>
          <span>Ask Assistant</span>
        </button>

        <button
          id="nav-settings-btn"
          onClick={onOpenSettings}
          className="w-full flex items-center space-x-3 px-4 py-2 rounded-lg text-[#47464d] dark:text-[#918b86] hover:bg-[#f4e3f1] dark:hover:bg-[#282421] hover:text-[#0d0c25] dark:hover:text-[#e2dfff] font-['JetBrains_Mono'] text-[12px] font-bold uppercase tracking-wider"
        >
          <span className="material-symbols-outlined text-[20px]">settings</span>
          <span>Settings</span>
        </button>

        {/* Archivist Profile */}
        <div className="mt-4 pt-3 flex items-center space-x-3 px-2">
          <div className="w-8 h-8 rounded-full bg-[#eedeeb] overflow-hidden border border-[#c8c5ce]">
            <img
              alt="Archivist User"
              className="w-full h-full object-cover"
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuDXd_JpbJb6hACsJ0hK5MolgDUBv0x0_TXC0w4V5ASfq8obxMIUhGnsgGtIroFcCkAim4SSjnhZ_AEOX-rk8mZaSPbhMHrlZZWZTZHmHR75IuaXjpQCvIYbc8i80s_dlsx8_RfZ4FXRsOJCKU069Ex4owalbtcgRPpWk0xWvVJCaQNXWIbEu_C8BWZHPbsR-ozjodSXllwV4feCSxP8N233_BkbKSLFsO1wmG2QtKsQUFZYuYMh2fMa"
            />
          </div>
          <span className="font-['JetBrains_Mono'] text-[13px] text-[#47464d] dark:text-[#918b86]">
            Archivist
          </span>
        </div>
      </div>
    </nav>
  );
};
