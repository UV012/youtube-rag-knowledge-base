import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { JobItem, VideoItem } from '../types';

export const ACTIVE_JOB_STATUSES = [
  'queued',
  'processing',
  'downloading',
  'transcribing',
  'indexing',
  'waiting_on_rate_limit',
];

export const ACTIVE_VIDEO_STATUSES = [
  'queued',
  'downloading',
  'transcribing',
  'indexing',
  'waiting_on_rate_limit',
];

export const isJobActive = (job: JobItem): boolean => {
  if (['done', 'failed', 'cancelled'].includes(job.status)) {
    return false;
  }
  if (ACTIVE_JOB_STATUSES.includes(job.status)) {
    return true;
  }
  if (job.stage && ACTIVE_JOB_STATUSES.includes(job.stage)) {
    return true;
  }
  if (job.sub_jobs && job.sub_jobs.some((sj) => !['done', 'failed', 'cancelled'].includes(sj.status))) {
    return true;
  }
  return false;
};

export const isVideoActive = (video: VideoItem): boolean => {
  return ACTIVE_VIDEO_STATUSES.includes(video.status);
};

interface DataContextType {
  jobs: JobItem[];
  videos: VideoItem[];
  isLoadingJobs: boolean;
  isLoadingVideos: boolean;
  currentTab: 'search' | 'add' | 'library' | 'detail';
  setCurrentTab: (tab: 'search' | 'add' | 'library' | 'detail') => void;
  fetchJobs: () => Promise<void>;
  fetchVideos: () => Promise<void>;
  setJobs: React.Dispatch<React.SetStateAction<JobItem[]>>;
  setVideos: React.Dispatch<React.SetStateAction<VideoItem[]>>;
}

const DataContext = createContext<DataContextType | undefined>(undefined);

export const DataProvider: React.FC<{
  currentTab: 'search' | 'add' | 'library' | 'detail';
  setCurrentTab: (tab: 'search' | 'add' | 'library' | 'detail') => void;
  children: React.ReactNode;
}> = ({ currentTab, setCurrentTab, children }) => {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [isLoadingJobs, setIsLoadingJobs] = useState(true);
  const [isLoadingVideos, setIsLoadingVideos] = useState(true);

  // In-flight request guards to prevent overlapping concurrent requests
  const isFetchingJobsRef = useRef(false);
  const isFetchingVideosRef = useRef(false);
  const lastJobsFetchTimeRef = useRef<number>(0);
  const lastVideosFetchTimeRef = useRef<number>(0);

  // Stable state refs to decouple the polling interval from state update re-renders
  const currentTabRef = useRef(currentTab);
  currentTabRef.current = currentTab;

  const jobsRef = useRef<JobItem[]>(jobs);
  jobsRef.current = jobs;

  const videosRef = useRef<VideoItem[]>(videos);
  videosRef.current = videos;

  // Single authoritative fetchJobs function
  const fetchJobs = useCallback(async () => {
    const now = Date.now();
    // Safety: if a request has been in-flight for >10s, release the lock
    if (isFetchingJobsRef.current && now - lastJobsFetchTimeRef.current < 10000) {
      return;
    }
    isFetchingJobsRef.current = true;
    lastJobsFetchTimeRef.current = now;

    try {
      const res = await fetch('/api/jobs');
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
    } finally {
      isFetchingJobsRef.current = false;
      setIsLoadingJobs(false);
    }
  }, []);

  // Single authoritative fetchVideos function
  const fetchVideos = useCallback(async () => {
    const now = Date.now();
    // Safety: if a request has been in-flight for >10s, release the lock
    if (isFetchingVideosRef.current && now - lastVideosFetchTimeRef.current < 10000) {
      return;
    }
    isFetchingVideosRef.current = true;
    lastVideosFetchTimeRef.current = now;

    try {
      const res = await fetch('/api/videos');
      if (res.ok) {
        const data = await res.json();
        setVideos(data);
      }
    } catch (err) {
      console.error('Failed to fetch videos:', err);
    } finally {
      isFetchingVideosRef.current = false;
      setIsLoadingVideos(false);
    }
  }, []);

  const fetchJobsRef = useRef(fetchJobs);
  fetchJobsRef.current = fetchJobs;

  const fetchVideosRef = useRef(fetchVideos);
  fetchVideosRef.current = fetchVideos;

  // Initial load
  useEffect(() => {
    fetchJobs();
    fetchVideos();
  }, [fetchJobs, fetchVideos]);

  // Tab switch instant refresh
  useEffect(() => {
    if (currentTab === 'add') {
      fetchJobs();
    } else if (currentTab === 'library') {
      fetchVideos();
    }
  }, [currentTab, fetchJobs, fetchVideos]);

  // Stable polling interval created once on mount
  useEffect(() => {
    const checkAndPoll = () => {
      const isVisible = typeof document === 'undefined' || document.visibilityState === 'visible';
      if (!isVisible) {
        return;
      }

      const activeTab = currentTabRef.current;
      const currentJobs = jobsRef.current;
      const currentVideos = videosRef.current;

      const hasActiveJobs = currentJobs.some(isJobActive);
      const hasActiveVideos = currentVideos.some(isVideoActive);

      let polledJobs = false;
      let polledVideos = false;

      // 1. Poll /api/jobs whenever on Add tab OR whenever background jobs are active
      if (activeTab === 'add' || hasActiveJobs) {
        polledJobs = true;
        fetchJobsRef.current();
      }

      // 2. Poll /api/videos when viewing Library AND videos are processing, OR if active jobs exist
      if ((activeTab === 'library' && hasActiveVideos) || hasActiveJobs) {
        polledVideos = true;
        fetchVideosRef.current();
      }

      // Instrumentation log to monitor polling ticks and state transitions
      console.debug('[DataContext Polling Tick]', {
        timestamp: new Date().toISOString(),
        activeTab,
        hasActiveJobs,
        activeJobCount: currentJobs.filter(isJobActive).length,
        hasActiveVideos,
        activeVideoCount: currentVideos.filter(isVideoActive).length,
        polledJobs,
        polledVideos,
        isFetchingJobs: isFetchingJobsRef.current,
        isFetchingVideos: isFetchingVideosRef.current,
      });
    };

    // Single rock-solid 3-second interval across the entire application
    const interval = setInterval(checkAndPoll, 3000);
    return () => clearInterval(interval);
  }, []); // Stable: runs on mount, never torn down by state updates

  return (
    <DataContext.Provider
      value={{
        jobs,
        videos,
        isLoadingJobs,
        isLoadingVideos,
        currentTab,
        setCurrentTab,
        fetchJobs,
        fetchVideos,
        setJobs,
        setVideos,
      }}
    >
      {children}
    </DataContext.Provider>
  );
};

export const useDataContext = () => {
  const context = useContext(DataContext);
  if (!context) {
    throw new Error('useDataContext must be used within a DataProvider');
  }
  return context;
};
