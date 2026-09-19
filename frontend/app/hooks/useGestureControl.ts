"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GestureDetector, GestureType, GestureDetection } from "../lib/gestures/detector";

export interface UseGestureControlOptions {
  onGesture?: (gesture: GestureDetection) => void;
  enabled?: boolean;
}

export function useGestureControl({ onGesture, enabled = true }: UseGestureControlOptions = {}) {
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastGesture, setLastGesture] = useState<GestureDetection | null>(null);
  const [motionEnergy, setMotionEnergy] = useState<number>(0);
  const [stream, setStream] = useState<MediaStream | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<GestureDetector | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const onGestureRef = useRef(onGesture);
  const lastSampleTimeRef = useRef<number>(0);

  useEffect(() => {
    onGestureRef.current = onGesture;
  }, [onGesture]);

  if (!detectorRef.current) {
    detectorRef.current = new GestureDetector(700, true);
  }

  const stopCamera = useCallback(() => {
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    if (detectorRef.current) {
      detectorRef.current.reset();
    }
    setStream(null);
    setMotionEnergy(0);
    setIsCameraOn(false);
  }, []);

  const attachStreamToVideo = useCallback((videoEl: HTMLVideoElement | null, mediaStream: MediaStream | null) => {
    if (!videoEl || !mediaStream) return;
    if (videoEl.srcObject !== mediaStream) {
      videoEl.srcObject = mediaStream;
    }
    videoEl.play().catch((err) => {
      console.warn("Video play error (will retry on user interaction):", err);
    });
  }, []);

  // Callback ref passed to <video> so it attaches the exact instant the element mounts
  const setVideoElement = useCallback((node: HTMLVideoElement | null) => {
    videoRef.current = node;
    if (node && streamRef.current) {
      attachStreamToVideo(node, streamRef.current);
    }
  }, [attachStreamToVideo]);

  const startCamera = useCallback(async () => {
    setError(null);
    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("Camera is not supported on this browser/environment.");
      }

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: "user",
        },
        audio: false,
      });

      streamRef.current = mediaStream;
      setStream(mediaStream);
      setIsCameraOn(true);

      // Attach immediately if video is already mounted
      if (videoRef.current) {
        attachStreamToVideo(videoRef.current, mediaStream);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error && err.name === "NotAllowedError"
          ? "Camera permission denied. Please allow camera access in your browser address bar."
          : err instanceof Error
          ? err.message
          : "Failed to access camera";
      console.error("[useGestureControl] Camera error:", err);
      setError(msg);
      stopCamera();
    }
  }, [attachStreamToVideo, stopCamera]);

  const toggleCamera = useCallback(() => {
    if (isCameraOn) {
      stopCamera();
    } else {
      startCamera();
    }
  }, [isCameraOn, startCamera, stopCamera]);

  // Ensure stream stays attached whenever isCameraOn or stream updates
  useEffect(() => {
    if (isCameraOn && stream && videoRef.current) {
      attachStreamToVideo(videoRef.current, stream);
    }
  }, [isCameraOn, stream, attachStreamToVideo]);

  // Capture current frame from video as base64 JPEG
  const captureSnapshot = useCallback((): string | null => {
    const video = videoRef.current;
    if (!video || !streamRef.current) {
      console.warn("[useGestureControl] captureSnapshot: video or stream not available");
      return null;
    }

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;

    if (width === 0 || height === 0) {
      console.warn("[useGestureControl] captureSnapshot: video dimensions 0");
      return null;
    }

    const snapCanvas = document.createElement("canvas");
    snapCanvas.width = width;
    snapCanvas.height = height;
    const ctx = snapCanvas.getContext("2d");
    if (!ctx) return null;

    try {
      ctx.drawImage(video, 0, 0, width, height);
      return snapCanvas.toDataURL("image/jpeg", 0.85);
    } catch (err) {
      console.error("[useGestureControl] Error drawing video to canvas:", err);
      return null;
    }
  }, []);

  // Manual gesture simulator for testing / instant fallback
  const triggerManualGesture = useCallback((type: GestureType) => {
    const labels: Record<GestureType, string> = {
      swipe_right: "Swipe Right (Next Tab)",
      swipe_left: "Swipe Left (Previous Tab)",
      open_palm: "Open Palm (Mute/Pause)",
      pinch_or_point: "Pinch/Point (Voice Trigger)",
    };
    const detection: GestureDetection = {
      type,
      confidence: 1.0,
      label: labels[type],
      timestamp: Date.now(),
    };
    setLastGesture(detection);
    if (onGestureRef.current) {
      onGestureRef.current(detection);
    }
  }, []);

  // Continuous frame analysis loop sampled every ~45ms
  useEffect(() => {
    if (!isCameraOn || !enabled) return;

    if (!canvasRef.current && typeof document !== "undefined") {
      const c = document.createElement("canvas");
      c.width = 64;
      c.height = 48;
      canvasRef.current = c;
    }

    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d", { willReadFrequently: true });
    let isProcessing = true;

    const loop = (timestamp: number) => {
      if (!isProcessing) return;

      if (timestamp - lastSampleTimeRef.current >= 45) {
        lastSampleTimeRef.current = timestamp;

        const video = videoRef.current;
        if (
          video &&
          video.videoWidth > 0 &&
          video.videoHeight > 0 &&
          ctx &&
          canvas &&
          detectorRef.current
        ) {
          try {
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const gesture = detectorRef.current.processFrame(imgData, Date.now());

            setMotionEnergy(detectorRef.current.currentEnergy);

            if (gesture) {
              setLastGesture(gesture);
              if (onGestureRef.current) {
                onGestureRef.current(gesture);
              }
            }
          } catch (e) {
            console.debug("[useGestureControl] Frame draw skipped:", e);
          }
        }
      }

      animFrameRef.current = requestAnimationFrame(loop);
    };

    animFrameRef.current = requestAnimationFrame(loop);

    return () => {
      isProcessing = false;
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [isCameraOn, enabled]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  return {
    isCameraOn,
    toggleCamera,
    captureSnapshot,
    lastGesture,
    motionEnergy,
    triggerManualGesture,
    setVideoElement,
    videoRef,
    error,
  };
}
