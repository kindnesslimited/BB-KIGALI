import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { Platform } from "react-native";
import { createAudioPlayer, setAudioModeAsync, AudioPlayer } from "expo-audio";
import { api } from "../api";

export type NowPlaying = {
  streamUrl: string;
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
};

const PlayerCtx = createContext<Ctx | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [isPlaying, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const playerRef = useRef<AudioPlayer | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api<NowPlaying>("/radio/now-playing");
        setNowPlaying(data);
      } catch (e) { console.log("np", e); }
      try {
        await setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: true });
      } catch {}
    })();
    return () => { try { playerRef.current?.remove(); } catch {} };
  }, []);

  const play = useCallback(async () => {
    if (!nowPlaying) return;
    setLoading(true);
    try {
      if (!playerRef.current) {
        playerRef.current = createAudioPlayer({ uri: nowPlaying.streamUrl });
      }
      playerRef.current.play();
      setPlaying(true);
    } catch (e) {
      console.log("play err", e);
    } finally { setLoading(false); }
  }, [nowPlaying]);

  const pause = useCallback(() => {
    try { playerRef.current?.pause(); } catch {}
    setPlaying(false);
  }, []);

  const toggle = useCallback(async () => {
    if (isPlaying) pause(); else await play();
  }, [isPlaying, pause, play]);

  return (
    <PlayerCtx.Provider value={{ nowPlaying, isPlaying, loading, toggle, play, pause }}>
      {children}
    </PlayerCtx.Provider>
  );
}

export const usePlayer = () => {
  const v = useContext(PlayerCtx);
  if (!v) throw new Error("usePlayer outside provider");
  return v;
};
