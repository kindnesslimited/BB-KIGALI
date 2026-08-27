import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { Platform } from "react-native";
import { createAudioPlayer, setAudioModeAsync, AudioPlayer } from "expo-audio";
import { api } from "../api";

export type NowPlaying = {
  streamUrl: string;
  streamUrlHttps?: string;
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

/**
 * Return the best-available stream URL for the current platform.
 * - On web: ALWAYS prefer the HTTPS mirror if configured (avoids mixed-content
 *   blocks on HTTPS pages and works fine on HTTP pages too).
 * - On native (iOS/Android): the HTTP URL works fine — iOS needs an ATS
 *   exception (already added for radio.bbkigali.com in app.json). We still
 *   prefer HTTPS when available for better security.
 */
function pickStreamUrl(np: NowPlaying): string {
  if (!np) return "";
  if (Platform.OS === "web" && np.streamUrlHttps) return np.streamUrlHttps;
  return np.streamUrlHttps || np.streamUrl;
}

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [isPlaying, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const playerRef = useRef<AudioPlayer | null>(null);

  const refreshNowPlaying = useCallback(async () => {
    try {
      const data = await api<NowPlaying>("/radio/now-playing");
      setNowPlaying(data);
    } catch (e) { console.log("[radio] fetch now-playing failed", e); }
  }, []);

  useEffect(() => { void refreshNowPlaying(); }, [refreshNowPlaying]);

  // Configure audio to keep playing when the app is backgrounded / screen is locked.
  useEffect(() => {
    void setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: true,
      interruptionMode: "duckOthers",
    }).catch(() => {});
    return () => { try { playerRef.current?.remove(); } catch { /* noop */ } };
  }, []);

  const play = useCallback(async () => {
    if (!nowPlaying) return;
    const uri = pickStreamUrl(nowPlaying);
    if (!uri) return;
    setLoading(true);
    try {
      if (!playerRef.current) {
        playerRef.current = createAudioPlayer({ uri });
      } else {
        // Reset source if it changed (e.g. admin swapped streamUrl live)
        try { playerRef.current.replace({ uri }); } catch { /* noop */ }
      }
      await playerRef.current.play();
      setPlaying(true);
    } catch (e) {
      console.log("[radio] play failed", e);
      setPlaying(false);
    } finally { setLoading(false); }
  }, [nowPlaying]);

  const pause = useCallback(() => {
    try { playerRef.current?.pause(); } catch { /* noop */ }
    setPlaying(false);
  }, []);

  const toggle = useCallback(async () => {
    if (isPlaying) pause(); else await play();
  }, [isPlaying, play, pause]);

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
