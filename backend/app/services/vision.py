"""Phase 9 — Computer Vision Service.

Processes image frames captured by the client camera or snapshot feed.
Constructs multimodal messages for vision-capable models (via OpenRouter or OpenAI API)
and generates descriptive analysis and object detection summaries.
"""

from __future__ import annotations

import logging
import base64
import re
import time
from typing import Any

from openai import OpenAI
from app.config import settings

logger = logging.getLogger("umi.vision")

VISION_DEFAULT_PROMPT = "Describe what you see in this image in detail. Mention objects, environment, people, text, or activities visible."


class VisionService:
    def __init__(self) -> None:
        self._last_snapshot: str | None = None
        self._last_analysis: dict[str, Any] | None = None
        self._primary_exhausted_until: float = 0.0

    @property
    def is_available(self) -> bool:
        return bool(settings.llm_api_key or settings.gemini_api_key)

    def store_latest_snapshot(self, base64_image: str) -> None:
        """Cache the most recent frame received from client."""
        self._last_snapshot = base64_image

    def get_latest_snapshot(self) -> str | None:
        return self._last_snapshot

    def get_latest_analysis(self) -> dict[str, Any] | None:
        return self._last_analysis

    def _call_gemini_vision(self, clean_base64: str, prompt: str) -> dict[str, Any]:
        gemini_client = OpenAI(
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key,
            timeout=30.0,
        )
        image_url = f"data:image/jpeg;base64,{clean_base64}"
        candidate_models = [
            settings.gemini_model,
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
        ]
        seen: set[str] = set()
        models = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

        last_exc: Exception | None = None
        for model in models:
            try:
                response = gemini_client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                    max_tokens=250,
                )
                content = response.choices[0].message.content or "No visual description generated."
                words = set(re.findall(r"\b[a-z]{3,15}\b", content.lower()))
                common_objects = [
                    "person", "laptop", "cup", "book", "desk", "phone", "screen",
                    "keyboard", "chair", "wall", "window", "door", "light", "bottle"
                ]
                detected = [obj for obj in common_objects if obj in words]
                result = {
                    "description": content,
                    "objects": detected,
                    "prompt": prompt,
                }
                self._last_analysis = result
                return result
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                    logger.warning("Gemini vision model %s quota exceeded; trying next model in pool", model)
                    continue
                raise
        if last_exc:
            raise last_exc

    def analyze_image(
        self,
        base64_image: str,
        prompt: str = VISION_DEFAULT_PROMPT,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Analyze an image using a vision-capable multimodal LLM."""
        if not base64_image or not base64_image.strip():
            raise ValueError("No image data provided")

        clean_base64 = base64_image.strip()
        if clean_base64.startswith("data:"):
            try:
                clean_base64 = clean_base64.split(",", 1)[1].strip()
            except IndexError:
                pass

        try:
            base64.b64decode(clean_base64, validate=True)
        except Exception as exc:
            raise ValueError(f"Invalid base64 image data: {exc}") from exc

        self.store_latest_snapshot(clean_base64)

        if not self.is_available:
            simulated = {
                "description": "Camera image captured. Vision provider API key not configured.",
                "objects": ["camera_feed"],
                "prompt": prompt,
            }
            self._last_analysis = simulated
            return simulated

        now = time.time()
        # If OpenRouter was recently exhausted and Gemini fallback is ready, route to Gemini directly
        if settings.gemini_api_key and now < self._primary_exhausted_until:
            return self._call_gemini_vision(clean_base64, prompt)

        if settings.llm_api_key:
            client = OpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=30.0,
            )

            vision_model = model or "openai/gpt-4o-mini"
            image_url = f"data:image/jpeg;base64,{clean_base64}"

            try:
                response = client.chat.completions.create(
                    model=vision_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                    max_tokens=250,
                )
                content = response.choices[0].message.content or "No visual description generated."

                words = set(re.findall(r"\b[a-z]{3,15}\b", content.lower()))
                common_objects = [
                    "person", "laptop", "cup", "book", "desk", "phone", "screen",
                    "keyboard", "chair", "wall", "window", "door", "light", "bottle"
                ]
                detected = [obj for obj in common_objects if obj in words]

                result = {
                    "description": content,
                    "objects": detected,
                    "prompt": prompt,
                }
                self._last_analysis = result
                self._primary_exhausted_until = 0.0
                return result
            except Exception as exc:
                err_str = str(exc)
                is_exhaustion = any(
                    h in err_str.lower()
                    for h in ("402", "429", "credit", "quota", "rate limit", "purchased", "payment required")
                )
                if settings.gemini_api_key and is_exhaustion:
                    self._primary_exhausted_until = now + 1800
                    logger.warning(
                        "Primary vision model quota exhausted (%s). Seamlessly falling back to Google Gemini (%s).",
                        exc,
                        settings.gemini_model,
                    )
                    return self._call_gemini_vision(clean_base64, prompt)

                logger.error("Vision model analysis failed: %s", exc)
                if "402" in err_str or "credits" in err_str.lower() or "purchased" in err_str.lower():
                    user_msg = (
                        "Camera snapshot captured successfully! However, your OpenRouter account has run out of credits (Error 402). "
                        "To enable AI visual scene understanding, please add credits at https://openrouter.ai/settings/credits."
                    )
                    detected = ["camera_active", "snapshot_saved"]
                elif "429" in err_str or "rate limit" in err_str.lower():
                    user_msg = (
                        "Camera snapshot captured! OpenRouter free daily rate limit has been reached (Error 429). "
                        "Please wait for the daily reset or add credits at https://openrouter.ai/settings/credits."
                    )
                    detected = ["camera_active", "snapshot_saved"]
                else:
                    user_msg = f"Visual frame received, but analysis encountered an error: {exc}"
                    detected = []

                fallback = {
                    "description": user_msg,
                    "objects": detected,
                    "prompt": prompt,
                    "error": err_str,
                }
                self._last_analysis = fallback
                return fallback

        # If no OpenRouter key is set, fall directly to Gemini
        if settings.gemini_api_key:
            return self._call_gemini_vision(clean_base64, prompt)

        return {
            "description": "Camera image captured. No vision provider configured.",
            "objects": ["camera_feed"],
            "prompt": prompt,
        }


vision_service = VisionService()
