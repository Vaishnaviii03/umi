import logging
import os
from pathlib import Path

logger = logging.getLogger("umi.soul")

# Potential locations for Soul.md in order of priority:
# 1. Explicit environment variable SOUL_PATH
# 2. Workspace root: launcher/Soul.md
# 3. Bundled copy: backend/app/orchestrator/Soul.md
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]  # backend/app/orchestrator -> backend/app -> backend -> Umi

_SOUL_CANDIDATE_PATHS = [
    Path(os.environ["SOUL_PATH"]) if os.environ.get("SOUL_PATH") else None,
    _REPO_ROOT / "launcher" / "Soul.md",
    _HERE / "Soul.md",
]

_CACHED_SOUL_TEXT: str | None = None
_CACHED_SOUL_MTIME: float | None = None
_RESOLVED_SOUL_PATH: Path | None = None


def resolve_soul_path() -> Path | None:
    """Find the first existing Soul.md from candidate paths."""
    for candidate in _SOUL_CANDIDATE_PATHS:
        if candidate and candidate.is_file():
            return candidate
    return None


def get_soul_prompt() -> str:
    """Load and cache Umi's Soul prompt from Soul.md with automatic mtime reload."""
    global _CACHED_SOUL_TEXT, _CACHED_SOUL_MTIME, _RESOLVED_SOUL_PATH

    path = resolve_soul_path()
    if path is not None:
        try:
            mtime = path.stat().st_mtime
            if _CACHED_SOUL_TEXT is None or _CACHED_SOUL_MTIME != mtime or _RESOLVED_SOUL_PATH != path:
                logger.info("Loading Umi's nature from %s (mtime=%s)", path, mtime)
                _CACHED_SOUL_TEXT = path.read_text(encoding="utf-8").strip()
                _CACHED_SOUL_MTIME = mtime
                _RESOLVED_SOUL_PATH = path
            return _CACHED_SOUL_TEXT
        except Exception as exc:
            logger.warning("Failed to read Soul.md from %s: %s", path, exc)
            if _CACHED_SOUL_TEXT:
                return _CACHED_SOUL_TEXT

    # Fallback if Soul.md is missing
    return (
        "You are Umi, a personal AI assistant, companion, intelligent operating system, "
        "and trusted thinking partner for Boss. Be warm, intelligent, curious, and honest. "
        "Always address the user as Boss. Be direct, practical, and helpful."
    )
