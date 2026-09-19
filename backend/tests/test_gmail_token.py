"""Phase 5 — Gmail token store tests (local file, 0600, atomic save)."""

import json
import os
import stat

import pytest

from app.services.gmail.token_store import TokenStore


@pytest.fixture()
def store_path(tmp_path):
    return str(tmp_path / "gmail_token.json")


def test_missing_file_loads_none(store_path):
    store = TokenStore(store_path)
    assert store.load() is None
    assert store.exists is False


def test_save_then_load_roundtrip(store_path):
    store = TokenStore(store_path)
    token = {"token": "abc", "refresh_token": "r", "expiry": "2026-12-01T00:00:00Z"}
    store.save(token)
    assert store.exists is True
    assert store.load() == token


def test_save_sets_owner_only_permissions(store_path):
    store = TokenStore(store_path)
    store.save({"token": "x"})
    mode = stat.S_IMODE(os.stat(store_path).st_mode)
    assert mode == 0o600


def test_load_ignores_garbage_file(store_path):
    with open(store_path, "w") as fh:
        fh.write("{not json")
    assert TokenStore(store_path).load() is None


def test_load_rejects_file_without_token(store_path):
    with open(store_path, "w") as fh:
        json.dump({"other": 1}, fh)
    assert TokenStore(store_path).load() is None


def test_clear_removes_file(store_path):
    store = TokenStore(store_path)
    store.save({"token": "x"})
    store.clear()
    assert store.exists is False
    assert store.load() is None