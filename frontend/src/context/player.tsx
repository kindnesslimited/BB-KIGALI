import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "../api";

export type NowPlaying = {
  streamUrl: string;
  youtubeVideoId?: string;
  youtubeEmbedUrl?: string;
  youtubeWatchUrl?: string;
  showTitle: string;
  djName: string;
  description: string;
  coverImage: string;
  isLive: boolean;
};

type Ctx = {
  nowPlaying: NowPlaying | null;
  isPlaying: boolean;
  loading: boolean;
  toggle: () => Promise<void>;
  play: () => Promise<void>;
  pause: () => void;
  refreshNowPlaying: () => Promise<void>;
};

const PlayerCtx = createContext<Ctx | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [isPlaying, setPlaying] = useState(false);
  const [loading] = useState(false);

  const refreshNowPlaying = useCallback(async () => {
    try {
      const data = await api<NowPlaying>("/radio/now-playing");
      setNowPlaying(data);
    } catch (e) { console.log("np", e); }
  }, []);

  useEffect(() => { void refreshNowPlaying(); }, [refreshNowPlaying]);

  const play = useCallback(async () => { setPlaying(true); }, []);
  const pause = useCallback(() => { setPlaying(false); }, []);
  const toggle = useCallback(async () => { setPlaying((p) => !p); }, []);

  return (
    <PlayerCtx.Provider value={{ nowPlaying, isPlaying, loading, toggle, play, pause, refreshNowPlaying }}>
      {children}
    </PlayerCtx.Provider>
  );
}

export const usePlayer = () => {
  const v = useContext(PlayerCtx);
  if (!v) throw new Error("usePlayer outside provider");
  return v;
};
