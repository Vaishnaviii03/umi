"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { normalizeTtsText, VOICE_UNAVAILABLE_MESSAGE } from "../lib/speech";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type VoiceStatus = "unknown" | "available" | "unavailable";

type TtsApi = {
  /**
   * Enqueue `text` to be synthesized and played. Resolves when that item's
   * playback ends (or is interrupted/stopped). Items play in order while
   * later items are synthesized ahead of time so audio is ready when needed.
   */
  speak: (text: string) => Promise<void>;
  /** Immediately stop any in-flight synthesis/playback and clear the queue. */
  stop: () => void;
  voiceStatus: VoiceStatus;
};

type SpeechItem = {
  text: string;
  audio?: Blob;
  token: number;
  resolve: () => void;
  reject: (error: Error) => void;
};

/**
 * Text-to-speech client for the Umi frontend. Fetches synthesized audio from
 * POST /tts and plays it through a single Audio element at a time.
 *
 * A prefetching queue lets the caller hand over complete sentences as the LLM
 * streams them: sentence N is already being synthesized while sentence N-1 is
 * playing, so Umi starts speaking from the first sentence instead of waiting
 * for the whole reply. `speak` still resolves per-item when its playback ends,
 * preserving the "busy while talking" contract. On any failure the item is
 * rejected with VOICE_UNAVAILABLE_MESSAGE and `voiceStatus` flips, while the
 * text pipeline stays intact.
 */
export function useTts(options?: { onAudioStart?: () => void }): TtsApi {
  const onAudioStartRef = useRef(options?.onAudioStart);
  useEffect(() => {
    onAudioStartRef.current = options?.onAudioStart;
  }, [options]);

  const queueRef = useRef<SpeechItem[]>([]);
  const inFlightRef = useRef<Map<SpeechItem, Promise<Blob>>>(new Map());
  const drainingRef = useRef(false);
  const stopTokenRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const stopSignalRef = useRef<() => void>(() => {});
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("unknown");

  const releaseAudio = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    stopTokenRef.current += 1;
    const signal = stopSignalRef.current;
    stopSignalRef.current = () => {};
    signal();
    releaseAudio();
    const pending = queueRef.current;
    queueRef.current = [];
    for (const item of pending) {
      item.resolve();
    }
  }, [releaseAudio]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  const synth = useCallback(async (text: string): Promise<Blob> => {
    const res = await fetch(`${BACKEND_URL}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "audio/mpeg" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(VOICE_UNAVAILABLE_MESSAGE);
    const blob = await res.blob();
    if (!blob.size) throw new Error(VOICE_UNAVAILABLE_MESSAGE);
    return blob;
  }, []);

  const ensureAudio = useCallback(
    (item: SpeechItem): Promise<Blob> => {
      if (item.audio) return Promise.resolve(item.audio);
      const existing = inFlightRef.current.get(item);
      if (existing) return existing;
      const promise = synth(item.text)
        .then((blob) => {
          item.audio = blob;
          inFlightRef.current.delete(item);
          return blob;
        })
        .catch((error: unknown) => {
          inFlightRef.current.delete(item);
          throw error;
        });
      inFlightRef.current.set(item, promise);
      return promise;
    },
    [synth],
  );

  const playAudio = useCallback(async (blob: Blob, token: number): Promise<void> => {
    if (token !== stopTokenRef.current) return;
    const url = URL.createObjectURL(blob);
    objectUrlRef.current = url;
    const audio = new Audio();
    audioRef.current = audio;
    audio.src = url;
    setVoiceStatus("available");
    await audio.play();
    onAudioStartRef.current?.();
    await new Promise<void>((resolve) => {
      const finish = () => resolve();
      const fail = () => {
        setVoiceStatus("unavailable");
        resolve();
      };
      audio.addEventListener("ended", finish, { once: true });
      audio.addEventListener("error", fail, { once: true });
      stopSignalRef.current = () => {
        audio.removeEventListener("ended", finish);
        audio.removeEventListener("error", fail);
        resolve();
      };
    });
    stopSignalRef.current = () => {};
  }, [onAudioStartRef]);

  const drain = useCallback(async () => {
    if (drainingRef.current) return;
    drainingRef.current = true;
    try {
      while (queueRef.current.length > 0) {
        const token = stopTokenRef.current;
        const item = queueRef.current[0];
        if (item.token !== token) {
          queueRef.current = queueRef.current.slice(1);
          item.resolve();
          continue;
        }
        try {
          const blob = await ensureAudio(item);
          if (token !== stopTokenRef.current) break;
          await playAudio(blob, token);
          queueRef.current = queueRef.current.slice(1);
          item.resolve();
        } catch (error) {
          setVoiceStatus("unavailable");
          queueRef.current = queueRef.current.slice(1);
          const err = error instanceof Error ? error : new Error(VOICE_UNAVAILABLE_MESSAGE);
          item.reject(err);
        }
      }
    } finally {
      drainingRef.current = false;
      if (queueRef.current.length > 0) void drain();
    }
  }, [ensureAudio, playAudio]);

  const speak = useCallback(
    (text: string): Promise<void> => {
      const trimmed = normalizeTtsText(text);
      if (!trimmed) return Promise.resolve();
      const token = stopTokenRef.current;
      return new Promise<void>((resolve, reject) => {
        const item: SpeechItem = { text: trimmed, token, resolve, reject };
        queueRef.current = [...queueRef.current, item];
        // Fire-and-forget prefetch: synthesize this (and any other queued)
        // item now, so the next sentence's audio is ready while the current
        // one plays.
        void ensureAudio(item).catch(() => {});
        void drain();
      });
    },
    [ensureAudio, drain],
  );

  return { speak, stop, voiceStatus };
}