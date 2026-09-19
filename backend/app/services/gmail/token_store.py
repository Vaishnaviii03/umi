"""Phase 5 — local OAuth token store.

Gmail tokens are credentials with wide reach, so they live in a single
owner-only file (``~/.umi/gmail_token.json``, mode 0600) — never in the
database, and never exposed through the REST API. The raw file is written
atomically (temp file + rename) so a crash can't leave a half-written token.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger("umi.gmail")


class TokenStore:
    def __init__(self, path: str | None = None) -> None:
        raw = path or settings.gmail_token_path
        self.path = Path(raw).expanduser()

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict | None:
        """Return stored token info, or None when nothing usable is present."""
        try:
            data = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict) or not data.get("token"):
            return None
        return data

    def save(self, token: dict) -> None:
        """Persist token info with owner-only permissions (0600)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(token, indent=2))
        tmp.chmod(0o600)
        os.replace(tmp, self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass  # best-effort on odd filesystems; temp rename already set it

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        logger.info("[gmail] OAuth token cleared")


token_store = TokenStore()