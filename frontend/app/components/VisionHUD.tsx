"use client";

import { useState } from "react";
import type { RefObject } from "react";
import type { GestureDetection, GestureType } from "../lib/gestures/detector";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface VisionHUDProps {
  isCameraOn: boolean;
  onToggleCamera: () => void;
  gesturesEnabled?: boolean;
  onToggleGestures?: () => void;
  videoRef?: RefObject<HTMLVideoElement | null>;
  setVideoElement?: (el: HTMLVideoElement | null) => void;
  lastGesture: GestureDetection | null;
  motionEnergy?: number;
  onCaptureSnapshot: () => string | null;
  onAskUmiAboutScene?: (description: string) => void;
  onTriggerManualGesture?: (type: GestureType) => void;
  error?: string | null;
}

export default function VisionHUD({
  isCameraOn,
  onToggleCamera,
  gesturesEnabled = false,
  onToggleGestures,
  videoRef,
  setVideoElement,
  lastGesture,
  motionEnergy = 0,
  onCaptureSnapshot,
  onAskUmiAboutScene,
  onTriggerManualGesture,
  error,
}: VisionHUDProps) {
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<{
    description: string;
    objects: string[];
  } | null>(null);
  const [hudCollapsed, setHudCollapsed] = useState(false);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    const snapshot = onCaptureSnapshot();
    if (!snapshot) {
      setAnalyzing(false);
      setAnalysisResult({
        description: "Camera is still starting up or frame not captured yet. Please ensure camera permission is allowed and try again.",
        objects: [],
      });
      return;
    }

    try {
      const res = await fetch(`${BACKEND_URL}/vision/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: snapshot,
          prompt: "Describe what you see in front of the camera, noting key objects and activities.",
        }),
      });

      if (!res.ok) {
        throw new Error(`Vision API error: ${res.statusText}`);
      }

      const data = await res.json();
      setAnalysisResult({
        description: data.description,
        objects: data.objects || [],
      });

      if (onAskUmiAboutScene && data.description) {
        onAskUmiAboutScene(data.description);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Vision inspection failed";
      setAnalysisResult({
        description: `Error analyzing frame: ${msg}`,
        objects: [],
      });
    } finally {
      setAnalyzing(false);
    }
  };

  if (!isCameraOn) {
    return null;
  }

  return (
    <div
      className={`fixed right-6 top-20 z-50 transition-all duration-300 ${
        hudCollapsed ? "w-64" : "w-88 max-w-sm"
      } rounded-2xl border border-holo-border-strong bg-holo-panel/95 p-4 shadow-[0_16px_48px_rgba(0,0,0,0.7)] backdrop-blur-2xl`}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between border-b border-holo-border/60 pb-2.5">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
          </span>
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-holo-cyan">
            Vision HUD & Gestures
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setHudCollapsed((v) => !v)}
            className="rounded p-1 text-holo-muted hover:bg-white/5 hover:text-white transition-colors"
            title={hudCollapsed ? "Expand HUD" : "Collapse HUD"}
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              {hudCollapsed ? <path d="M6 9l6 6 6-6" /> : <path d="M18 15l-6-6-6 6" />}
            </svg>
          </button>
          <button
            type="button"
            onClick={onToggleCamera}
            className="rounded p-1 text-holo-muted hover:bg-white/5 hover:text-holo-magenta transition-colors"
            title="Turn camera off"
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Gesture Control Toggle */}
      <div className="mb-3 flex items-center justify-between rounded-xl bg-black/40 px-3 py-2 border border-holo-border/40">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${gesturesEnabled ? "bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]" : "bg-zinc-600"}`} />
          <span className="font-mono text-[11px] text-holo-muted">Gestures:</span>
          <span className={`font-mono text-[11px] font-bold ${gesturesEnabled ? "text-emerald-400" : "text-zinc-500"}`}>
            {gesturesEnabled ? "ACTIVE" : "MUTED"}
          </span>
        </div>
        {onToggleGestures && (
          <button
            type="button"
            onClick={onToggleGestures}
            className={`rounded-lg px-2.5 py-1 font-mono text-[10px] uppercase font-semibold tracking-wider transition-all ${
              gesturesEnabled
                ? "border border-emerald-500/50 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                : "border border-holo-border bg-white/5 text-holo-muted hover:text-white hover:bg-white/10"
            }`}
          >
            {gesturesEnabled ? "Disable" : "Enable"}
          </button>
        )}
      </div>

      {/* Video Viewport */}
      <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-holo-border bg-black/90">
        <video
          ref={setVideoElement || (videoRef as any)}
          autoPlay
          playsInline
          muted
          className="h-full w-full object-cover transform -scale-x-100"
        />

        {/* HUD reticle overlay lines */}
        <div className="pointer-events-none absolute inset-0 border border-holo-cyan/20">
          <div className="absolute left-2 top-2 h-3 w-3 border-l-2 border-t-2 border-holo-cyan/70" />
          <div className="absolute right-2 top-2 h-3 w-3 border-r-2 border-t-2 border-holo-cyan/70" />
          <div className="absolute bottom-2 left-2 h-3 w-3 border-b-2 border-l-2 border-holo-cyan/70" />
          <div className="absolute bottom-2 right-2 h-3 w-3 border-b-2 border-r-2 border-holo-cyan/70" />
        </div>

        {/* Active Gesture Banner */}
        {lastGesture && (
          <div className="absolute top-2 left-2 right-2 animate-bounce flex items-center justify-between rounded-lg bg-holo-cyan/20 border border-holo-cyan/50 px-2.5 py-1.5 backdrop-blur-md">
            <span className="font-mono text-xs font-bold text-holo-cyan">
              {lastGesture.label}
            </span>
            <span className="font-mono text-[10px] text-white/80">
              {Math.round(lastGesture.confidence * 100)}%
            </span>
          </div>
        )}

        {/* Live Motion Energy Meter */}
        <div className="absolute bottom-2 left-2 right-2 flex flex-col gap-1 rounded bg-black/75 px-2 py-1 backdrop-blur-md">
          <div className="flex items-center justify-between font-mono text-[9px] text-holo-muted">
            <span>Motion Tracker</span>
            <span className={motionEnergy > 20 ? "text-holo-cyan font-bold" : "text-holo-muted"}>
              {motionEnergy}%
            </span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className={`h-full transition-all duration-150 ${
                motionEnergy > 30 ? "bg-holo-cyan" : "bg-holo-cyan/50"
              }`}
              style={{ width: `${Math.min(100, motionEnergy * 2)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Controls & Gesture Testing */}
      {!hudCollapsed && (
        <div className="mt-3 space-y-3">
          <button
            type="button"
            disabled={analyzing}
            onClick={handleAnalyze}
            className="w-full rounded-lg border border-holo-cyan/40 bg-holo-cyan/10 px-3 py-2 font-mono text-xs font-medium text-holo-cyan transition-all hover:bg-holo-cyan/20 hover:border-holo-cyan active:scale-95 disabled:opacity-50"
          >
            {analyzing ? "Analyzing scene..." : "Ask Umi What She Sees"}
          </button>

          {error && (
            <p className="text-[11px] font-mono text-holo-magenta">{error}</p>
          )}

          {analysisResult && (
            <div className="rounded-lg border border-holo-border bg-black/40 p-2.5 text-xs">
              <p className="text-holo-text leading-relaxed">{analysisResult.description}</p>
              {analysisResult.objects.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {analysisResult.objects.map((obj) => (
                    <span
                      key={obj}
                      className="rounded bg-holo-cyan/10 px-1.5 py-0.5 font-mono text-[10px] text-holo-cyan"
                    >
                      #{obj}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Quick manual gesture tester */}
          <div className="border-t border-holo-border/40 pt-2.5">
            <div className="mb-1.5 flex items-center justify-between font-mono text-[10px] text-holo-muted">
              <span>Gestures (Wave hand or Click to test)</span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                onClick={() => onTriggerManualGesture?.("swipe_right")}
                className="rounded border border-holo-border/60 bg-white/5 px-2 py-1 font-mono text-[10px] text-holo-text hover:bg-holo-cyan/15 hover:text-holo-cyan hover:border-holo-cyan/40 transition-colors text-left"
                title="Wave hand right to switch to next panel"
              >
                👋 Swipe Right →
              </button>
              <button
                type="button"
                onClick={() => onTriggerManualGesture?.("swipe_left")}
                className="rounded border border-holo-border/60 bg-white/5 px-2 py-1 font-mono text-[10px] text-holo-text hover:bg-holo-cyan/15 hover:text-holo-cyan hover:border-holo-cyan/40 transition-colors text-left"
                title="Wave hand left to switch to previous panel"
              >
                ← Swipe Left 👋
              </button>
              <button
                type="button"
                onClick={() => onTriggerManualGesture?.("open_palm")}
                className="rounded border border-holo-border/60 bg-white/5 px-2 py-1 font-mono text-[10px] text-holo-text hover:bg-holo-cyan/15 hover:text-holo-cyan hover:border-holo-cyan/40 transition-colors text-left"
                title="Hold open palm in center to mute speech"
              >
                ✋ Open Palm (Mute)
              </button>
              <button
                type="button"
                onClick={() => onTriggerManualGesture?.("pinch_or_point")}
                className="rounded border border-holo-border/60 bg-white/5 px-2 py-1 font-mono text-[10px] text-holo-text hover:bg-holo-cyan/15 hover:text-holo-cyan hover:border-holo-cyan/40 transition-colors text-left"
                title="Pinch or point to trigger voice input"
              >
                🤏 Pinch (Voice)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
