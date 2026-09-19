"""Phase 11 — Integration tests for Notifications API routes."""

from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.services.proactive_scheduler import proactive_scheduler

client = TestClient(app)


def test_list_notifications_empty_or_populated():
    response = client.get("/notifications")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_and_dismiss_notification_endpoint():
    notif = proactive_scheduler.create_notification(
        notif_type="system",
        title="Test Notification",
        message="This is a test notification.",
    )

    # Verify present in list
    response = client.get("/notifications")
    assert response.status_code == 200
    items = response.json()
    assert any(item["id"] == notif.id for item in items)

    # Dismiss notification
    dismiss_res = client.post(f"/notifications/{notif.id}/dismiss")
    assert dismiss_res.status_code == 200
    data = dismiss_res.json()
    assert data["status"] == "success"
    assert data["id"] == notif.id

    # Dismissing unknown ID returns 404
    bad_res = client.post("/notifications/unknown-uuid-xyz/dismiss")
    assert bad_res.status_code == 404


def test_trigger_check_endpoint():
    with patch.object(proactive_scheduler, "scan_all", return_value=[]):
        res = client.post("/notifications/trigger-check")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["alerts_emitted"] == 0
