import os
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _resolve_electron_bin(desktop_dir: Path) -> Path:
    bin_dir = desktop_dir / "node_modules" / ".bin"
    if os.name == "nt":
        for name in ("electron.cmd", "electron"):
            candidate = bin_dir / name
            if candidate.exists():
                return candidate
    else:
        candidate = bin_dir / "electron"
        if candidate.exists():
            return candidate
    return bin_dir / "electron"  # fallback; will fail loudly if missing


class LauncherConfig:
    """Configuration for the UMI background launcher."""

    # Microphone
    device: int | None = int(os.environ["UMI_MIC_DEVICE"]) if os.environ.get("UMI_MIC_DEVICE") else None
    sample_rate: int = _int("UMI_SAMPLE_RATE", 44100)
    block_ms: int = _int("UMI_BLOCK_MS", 20)

    # Detection sensitivity (0-100). Higher = detects quieter claps.
    sensitivity: int = _int("UMI_SENSITIVITY", 60)

    # Timing (milliseconds)
    min_gap_ms: int = _int("UMI_MIN_GAP_MS", 80)
    max_interval_ms: int = _int("UMI_MAX_INTERVAL_MS", 400)
    post_trigger_cooldown_ms: int = _int("UMI_POST_TRIGGER_COOLDOWN_MS", 8000)

    # Desktop app
    desktop_dir: Path = Path(os.environ.get("UMI_DESKTOP_DIR", str(HERE.parent / "desktop")))
    electron_bin: Path = Path(
        os.environ.get(
            "UMI_ELECTRON_BIN",
            str(_resolve_electron_bin(Path(os.environ.get("UMI_DESKTOP_DIR", str(HERE.parent / "desktop"))))),
        )
    )

    @property
    def clap_threshold_db(self) -> float:
        base = -10.0
        boost = (self.sensitivity / 100.0) * 8.0
        return base - boost

    @property
    def quiet_threshold_db(self) -> float:
        return self.clap_threshold_db - 24.0