"""Phase 9 — Vision Tools for UMI Orchestrator.

Enables the LLM to inspect recent visual context or camera snapshots.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from app.services.vision import vision_service
from app.tools.base import Tool, ToolContext, ToolResult


class DescribeVisualSceneInput(BaseModel):
    query: str = Field(
        default="What do you see?",
        description="The specific question about what is currently visible.",
    )


class DescribeVisualSceneTool(Tool):
    name = "describe_visual_scene"
    description = (
        "Inspect what Umi sees through the camera. Use when the user asks questions like "
        "'What am I looking at?', 'What do you see?', or asks to identify objects in front of the camera."
    )
    permission_level = 1  # Read-only perceptual inspection
    args_model = DescribeVisualSceneInput

    def run(self, ctx: ToolContext, query: str = "What do you see?", **kwargs: Any) -> ToolResult:
        snapshot = vision_service.get_latest_snapshot()
        if not snapshot:
            last_analysis = vision_service.get_latest_analysis()
            if last_analysis:
                return ToolResult.success(last_analysis)
            return ToolResult.failure(
                "No camera frame is currently available. Please turn on the camera in the Vision HUD or provide a snapshot."
            )

        try:
            analysis = vision_service.analyze_image(snapshot, prompt=query)
            return ToolResult.success(analysis)
        except Exception as exc:
            return ToolResult.failure(f"Failed to analyze visual scene: {exc}")

