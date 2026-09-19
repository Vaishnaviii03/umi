"""Phase 9 — Vision API endpoints.

Provides endpoints for the frontend to submit camera frames,
receive real-time visual scene descriptions, and inspect vision status.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.vision import vision_service

router = APIRouter(prefix="/vision", tags=["vision"])


class VisionAnalyzeRequest(BaseModel):
    image: str = Field(..., description="Base64 encoded JPEG/PNG image")
    prompt: str = Field(
        default="Describe what you see in this image in detail.",
        description="Optional guiding question or instruction for the vision model",
    )


class VisionAnalyzeResponse(BaseModel):
    description: str
    objects: list[str]
    prompt: str


class VisionStatusResponse(BaseModel):
    enabled: bool
    has_recent_snapshot: bool
    last_analysis: dict[str, Any] | None


@router.get("/status", response_model=VisionStatusResponse)
def get_vision_status() -> VisionStatusResponse:
    return VisionStatusResponse(
        enabled=vision_service.is_available,
        has_recent_snapshot=vision_service.get_latest_snapshot() is not None,
        last_analysis=vision_service.get_latest_analysis(),
    )


@router.post("/analyze", response_model=VisionAnalyzeResponse)
def analyze_vision_frame(payload: VisionAnalyzeRequest) -> VisionAnalyzeResponse:
    try:
        result = vision_service.analyze_image(payload.image, prompt=payload.prompt)
        return VisionAnalyzeResponse(
            description=result.get("description", ""),
            objects=result.get("objects", []),
            prompt=result.get("prompt", payload.prompt),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vision analysis failed: {exc}") from exc
