"""Phase 9 — Computer Vision Unit & Integration Tests.

Tests:
1. VisionService base64 validation and frame normalization
2. VisionService multimodal completion payload construction
3. Vision API endpoints (/vision/status, /vision/analyze)
4. DescribeVisualSceneTool tool registry and orchestrator tool call execution
"""

import base64
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.services.vision import vision_service
from app.tools import tool_manager, ToolContext

client = TestClient(app)

# 1x1 transparent PNG as sample base64
SAMPLE_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_vision_service_rejects_empty_image():
    try:
        vision_service.analyze_image("")
        assert False, "Should raise ValueError for empty image"
    except ValueError as exc:
        assert "No image data" in str(exc)


def test_vision_service_rejects_invalid_base64():
    try:
        vision_service.analyze_image("not-a-base64-string!@#$")
        assert False, "Should raise ValueError for invalid base64"
    except ValueError as exc:
        assert "Invalid base64" in str(exc)


def test_vision_service_caches_latest_snapshot():
    vision_service.store_latest_snapshot(SAMPLE_PNG_BASE64)
    assert vision_service.get_latest_snapshot() == SAMPLE_PNG_BASE64


def test_vision_status_endpoint():
    response = client.get("/vision/status")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "has_recent_snapshot" in data


def test_vision_analyze_endpoint_mock_success():
    fake_reply = MagicMock()
    fake_reply.choices = [
        MagicMock(message=MagicMock(content="I see a laptop and a coffee cup on a wooden desk."))
    ]

    with patch("openai.resources.chat.completions.Completions.create", return_value=fake_reply):
        response = client.post(
            "/vision/analyze",
            json={
                "image": f"data:image/png;base64,{SAMPLE_PNG_BASE64}",
                "prompt": "What do you see?",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "laptop" in data["description"]
    assert "laptop" in data["objects"]
    assert "cup" in data["objects"]
    assert data["prompt"] == "What do you see?"


def test_describe_visual_scene_tool_execution():
    from app.tools import tool_registry
    assert "describe_visual_scene" in tool_registry.names()

    # When snapshot is available
    vision_service.store_latest_snapshot(SAMPLE_PNG_BASE64)

    fake_reply = MagicMock()
    fake_reply.choices = [
        MagicMock(message=MagicMock(content="A person sitting at a desk with a keyboard."))
    ]

    with patch("openai.resources.chat.completions.Completions.create", return_value=fake_reply):
        from app.config import settings
        result = tool_manager.execute_tool(
            "describe_visual_scene",
            {"query": "Describe the scene"},
            ToolContext(user_id=str(settings.owner_id)),
        )
    assert result.status == "success"
    assert "keyboard" in result.data["description"]
