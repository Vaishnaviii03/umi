import { test } from "node:test";
import assert from "node:assert/strict";
import { GestureDetector } from "../app/lib/gestures/detector.ts";

function createMockFrame(width, height, fillValue = 0) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = fillValue;     // R
    data[i + 1] = fillValue; // G
    data[i + 2] = fillValue; // B
    data[i + 3] = 255;       // A
  }
  return { width, height, data };
}

function drawMotionPatch(frame, startX, endX, startY, endY, brightness = 200) {
  const { width, data } = frame;
  for (let y = startY; y < endY; y++) {
    for (let x = startX; x < endX; x++) {
      const idx = (y * width + x) * 4;
      data[idx] = brightness;
      data[idx + 1] = brightness;
      data[idx + 2] = brightness;
      data[idx + 3] = 255;
    }
  }
}

test("GestureDetector initializes and returns null on first frame", () => {
  const detector = new GestureDetector(500);
  const frame = createMockFrame(64, 48, 10);
  const result = detector.processFrame(frame, 1000);
  assert.equal(result, null);
});

test("GestureDetector returns null when no significant motion occurs", () => {
  const detector = new GestureDetector(500);
  const frame1 = createMockFrame(64, 48, 10);
  detector.processFrame(frame1, 1000);

  const frame2 = createMockFrame(64, 48, 12); // subtle noise
  const result = detector.processFrame(frame2, 1050);
  assert.equal(result, null);
});

test("GestureDetector detects swipe right when motion vector shifts right", () => {
  const detector = new GestureDetector(500, false);
  const width = 64;
  const height = 48;

  detector.processFrame(createMockFrame(width, height, 0), 1000);

  let gesture = null;
  const patches = [
    [5, 20],
    [20, 35],
    [35, 50],
    [45, 60],
  ];
  for (let i = 0; i < patches.length; i++) {
    const f = createMockFrame(width, height, 0);
    drawMotionPatch(f, patches[i][0], patches[i][1], 15, 35, 220);
    const res = detector.processFrame(f, 1050 + i * 50);
    if (res) gesture = res;
  }

  assert.ok(gesture);
  assert.equal(gesture.type, "swipe_right");
  assert.ok(gesture.confidence > 0.5);
});

test("GestureDetector detects swipe left when motion vector shifts left", () => {
  const detector = new GestureDetector(500, false);
  const width = 64;
  const height = 48;

  detector.processFrame(createMockFrame(width, height, 0), 1000);

  let gesture = null;
  const patches = [
    [45, 60],
    [35, 50],
    [20, 35],
    [5, 20],
  ];
  for (let i = 0; i < patches.length; i++) {
    const f = createMockFrame(width, height, 0);
    drawMotionPatch(f, patches[i][0], patches[i][1], 15, 35, 220);
    const res = detector.processFrame(f, 1050 + i * 50);
    if (res) gesture = res;
  }

  assert.ok(gesture);
  assert.equal(gesture.type, "swipe_left");
  assert.ok(gesture.confidence > 0.5);
});

test("GestureDetector detects open palm when sustained centered mass is present", () => {
  const detector = new GestureDetector(500, false);
  const width = 64;
  const height = 48;

  detector.processFrame(createMockFrame(width, height, 0), 1000);

  let detectedGesture = null;
  for (let i = 1; i <= 6; i++) {
    const f = createMockFrame(width, height, 0);
    const brightness = 150 + (i % 2) * 80;
    drawMotionPatch(f, 18, 46, 12, 36, brightness);
    const res = detector.processFrame(f, 1000 + i * 50);
    if (res) {
      detectedGesture = res;
      break;
    }
  }
  assert.ok(detectedGesture);
  assert.equal(detectedGesture.type, "open_palm");
});

test("GestureDetector enforces cooldown period between detections", () => {
  const detector = new GestureDetector(800, false);
  const width = 64;
  const height = 48;

  detector.processFrame(createMockFrame(width, height, 0), 1000);

  let g1 = null;
  const patches = [
    [5, 20],
    [20, 35],
    [35, 50],
    [45, 60],
  ];
  for (let i = 0; i < patches.length; i++) {
    const f = createMockFrame(width, height, 0);
    drawMotionPatch(f, patches[i][0], patches[i][1], 15, 35, 220);
    const res = detector.processFrame(f, 1050 + i * 50);
    if (res) g1 = res;
  }

  assert.ok(g1);
  assert.equal(g1.type, "swipe_right");

  // Immediate subsequent motion within 400ms should be suppressed by cooldown
  const f6 = createMockFrame(width, height, 0);
  drawMotionPatch(f6, 45, 60, 15, 35, 220);
  const g2 = detector.processFrame(f6, 1300);
  assert.equal(g2, null);
});
