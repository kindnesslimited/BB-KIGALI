import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { Platform } from "react-native";
import { createAudioPlayer, setAudioModeAsync, AudioPlayer } from "expo-audio";
import { api } from "../api";

export type NowPlaying = {
  // NOTE: `streamUrl` and `streamUrlHttps` are ONLY returned by the backend for
  // authenticated paying subscribers. Guests / free tier receive
  // `requiresSubscription: true` with these fields absent.
  streamUrl?: string;
  streamUrlHttps?: string;
  proxyStreamUrl?: string; // preferred — subscription-authorised backend proxy
  youtubeVideoId?: string;
  youtubeEmbedUrl?: string;
  youtubeWatchUrl?: string;
  showTitle: string;
  djName: string;
  description: string;
  coverImage: string;
  isLive: boolean;
  requiresSubscription?: boolean;
};

type Ctx = {
  nowPlaying: NowPlaying | null;
  isPlaying: boolean;
  loading: boolean;
  requiresSubscription: boolean;
  toggle: () => Promise<void>;
  play: () => Promise<void>;
  pause: () => void;
  refreshNowPlaying: () => Promise<void>;
};

const PlayerCtx = createContext<Ctx | null>(null);

/** Returns the subscription-authorised proxy URL if the user is a paying
 *  subscriber, else null. Playing raw upstream URLs is NOT allowed anymore —
 *  the backend rewrites the paywall on `/radio/now-playing`. */
function pickStreamUrl(np: NowPlaying | null): string | null {
  if (!np) return null;
  if (np.proxyStreamUrl) return np.proxyStreamUrl;
  return null;
}

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [nowPlaying, setNowPlaying] = useState<NowPlaying | null>(null);
  const [isPlaying, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const playerRef = useRef<AudioPlayer | null>(null);

  const refreshNowPlaying = useCallback(async () => {
    try {
      // `auth: true` when a token is available — the backend returns richer data
      // (proxyStreamUrl) for paying subscribers.
      const data = await api<NowPlaying>("/radio/now-playing", { auth: true }).catch(() =>
        api<NowPlaying>("/radio/now-playing"),
      );
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
    if (nowPlaying.requiresSubscription) {
      // Caller should route to /paywall — the play button becomes a paywall CTA.
      return;
    }
    const uri = pickStreamUrl(nowPlaying);
    if (!uri) return;
    setLoading(true);
    try {
      if (!playerRef.current) {
        playerRef.current = createAudioPlayer({ uri });
      } else {
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

  const requiresSubscription = !!(nowPlaying?.requiresSubscription);

  return (
    <PlayerCtx.Provider value={{ nowPlaying, isPlaying, loading, requiresSubscription, toggle, play, pause, refreshNowPlaying }}>
      {children}
    </PlayerCtx.Provider>
  );
}

export const usePlayer = () => {
  const v = useContext(PlayerCtx);
  if (!v) throw new Error("usePlayer outside provider");
  return v;
};
