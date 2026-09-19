/**
 * Phase 10 — Client-side gesture detector for UMI.
 *
 * Analyzes video frames via downscaled offscreen canvas to detect:
 * - `swipe_left`: cycle panels backward / left
 * - `swipe_right`: cycle panels forward / right
 * - `open_palm`: mute speech / pause voice session
 * - `pinch_or_point`: activate voice input or camera snapshot
 *
 * Operates in 64x48 resolution for real-time evaluation with zero heavy dependencies.
 */

export type GestureType = "swipe_left" | "swipe_right" | "open_palm" | "pinch_or_point";

export interface GestureDetection {
  type: GestureType;
  confidence: number;
  label: string;
  timestamp: number;
}

export interface MotionPoint {
  x: number; // 0..1 (flipped if mirrored so x increases to user's right)
  y: number; // 0..1
  mass: number;
  timestamp: number;
}

export class GestureDetector {
  private prevFrameData: Uint8ClampedArray | null = null;
  private motionHistory: MotionPoint[] = [];
  private lastTriggerTime = 0;
  private cooldownMs = 700; // Prevent spamming triggers
  public mirrored = true; // Webcams in selfie view are mirrored
  public currentEnergy = 0; // 0..100 motion energy for HUD visualizer

  constructor(cooldownMs = 700, mirrored = true) {
    this.cooldownMs = cooldownMs;
    this.mirrored = mirrored;
  }

  public reset(): void {
    this.prevFrameData = null;
    this.motionHistory = [];
    this.lastTriggerTime = 0;
    this.currentEnergy = 0;
  }

  /**
   * Process a single ImageData frame (64x48 or 128x96).
   * Returns a detected gesture if threshold and cooldown conditions are met.
   */
  public processFrame(imageData: ImageData, now = Date.now()): GestureDetection | null {
    const { width, height, data } = imageData;
    const totalPixels = width * height;

    if (!this.prevFrameData || this.prevFrameData.length !== data.length) {
      this.prevFrameData = new Uint8ClampedArray(data);
      this.currentEnergy = 0;
      return null;
    }

    let diffPixels = 0;
    let sumX = 0;
    let sumY = 0;
    const threshold = 30; // Filter out webcam sensor noise and auto-exposure grain

    for (let i = 0; i < data.length; i += 4) {
      // Calculate grayscale brightness difference
      const rDiff = Math.abs(data[i] - this.prevFrameData[i]);
      const gDiff = Math.abs(data[i + 1] - this.prevFrameData[i + 1]);
      const bDiff = Math.abs(data[i + 2] - this.prevFrameData[i + 2]);
      const diff = (rDiff + gDiff + bDiff) / 3;

      if (diff > threshold) {
        const pixelIdx = i / 4;
        const x = pixelIdx % width;
        const y = Math.floor(pixelIdx / width);
        sumX += x;
        sumY += y;
        diffPixels++;
      }
    }

    // Save current frame for next comparison
    this.prevFrameData.set(data);

    const motionFraction = diffPixels / totalPixels;
    this.currentEnergy = Math.min(100, Math.round(motionFraction * 350));

    // Filter out sensor noise (< 40 px / < 1.5% mass) or massive full-frame shift (> 75%)
    if (diffPixels < 40 || motionFraction < 0.025 || motionFraction > 0.75) {
      return null;
    }

    const rawCentroidX = sumX / diffPixels;
    const rawCentroidY = sumY / diffPixels;

    // Invert X if mirrored so user moving hand right always yields positive deltaX
    const normX = this.mirrored ? 1 - rawCentroidX / width : rawCentroidX / width;
    const normY = rawCentroidY / height;

    const currentPoint: MotionPoint = {
      x: normX,
      y: normY,
      mass: motionFraction,
      timestamp: now,
    };

    this.motionHistory.push(currentPoint);

    // Keep recent motion points (~500ms sliding window)
    while (
      this.motionHistory.length > 12 ||
      (this.motionHistory.length > 1 && now - this.motionHistory[0].timestamp > 600)
    ) {
      this.motionHistory.shift();
    }

    // Enforce cooldown
    if (now - this.lastTriggerTime < this.cooldownMs) {
      return null;
    }

    // Evaluate gestures
    const gesture = this.evaluateMotion(this.motionHistory, now);
    if (gesture) {
      this.lastTriggerTime = now;
      this.motionHistory = []; // clear window after trigger
    }
    return gesture;
  }

  private evaluateMotion(history: MotionPoint[], now: number): GestureDetection | null {
    if (history.length < 3) return null;

    const first = history[0];
    const latest = history[history.length - 1];
    const duration = latest.timestamp - first.timestamp;

    if (duration > 850 || duration < 60) {
      return null;
    }

    const deltaX = latest.x - first.x;
    const deltaY = latest.y - first.y;
    const absDeltaX = Math.abs(deltaX);
    const absDeltaY = Math.abs(deltaY);

    // 1. Horizontal Swipes: deliberate horizontal motion across screen (> 20% frame width)
    if (absDeltaX > 0.20 && absDeltaX > absDeltaY * 1.2) {
      if (deltaX > 0) {
        return {
          type: "swipe_right",
          confidence: Math.min(1.0, 0.7 + absDeltaX),
          label: "Swipe Right (Next Tab)",
          timestamp: now,
        };
      } else {
        return {
          type: "swipe_left",
          confidence: Math.min(1.0, 0.7 + absDeltaX),
          label: "Swipe Left (Previous Tab)",
          timestamp: now,
        };
      }
    }

    // 2. Open Palm: Sustained, prominent centered hand mass (> 15% frame) held steady
    const avgMass = history.reduce((acc, p) => acc + p.mass, 0) / history.length;
    const avgDistFromCenter =
      history.reduce((acc, p) => acc + Math.hypot(p.x - 0.5, p.y - 0.5), 0) / history.length;

    if (avgMass > 0.15 && avgDistFromCenter < 0.38 && absDeltaX < 0.12 && absDeltaY < 0.12) {
      return {
        type: "open_palm",
        confidence: Math.min(1.0, avgMass * 4),
        label: "Open Palm (Mute/Pause)",
        timestamp: now,
      };
    }

    return null;
  }
}
