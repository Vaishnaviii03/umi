import os
from pathlib import Path
from typing import Optional

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


def list_audio_input_devices() -> list[dict]:
    """List available audio input devices with their indices and names."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        return [
            {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0
        ]
    except Exception as e:
        return [{"error": str(e)}]


class LauncherConfig:
    """Configuration for the UMI background launcher."""

    # Microphone
    device: int | None = int(os.environ["UMI_MIC_DEVICE"]) if os.environ.get("UMI_MIC_DEVICE") else None
    sample_rate: int = _int("UMI_SAMPLE_RATE", 44100)
    block_ms: int = _int("UMI_BLOCK_MS", 20)

    # Detection sensitivity (0-100). Higher = detects quieter claps.
    sensitivity: int = _int("UMI_SENSITIVITY", 60)

    # Timing (milliseconds)
    min_gap_ms: int = _int("UMI_MIN_GAP_MS", 60)
    max_interval_ms: int = _int("UMI_MAX_INTERVAL_MS", 500)
    post_trigger_cooldown_ms: int = _int("UMI_POST_TRIGGER_COOLDOWN_MS", 3000)

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

    def get_input_devices(self) -> list[dict]:
        """List available audio input devices."""
        return list_audio_input_devices()

    def select_device_interactive(self) -> Optional[int]:
        """Interactively select microphone device."""
        devices = self.get_input_devices()
        if not devices or "error" in devices[0]:
            print(f"Error listing devices: {devices}")
            return None
        print("Available input devices:")
        for d in devices:
            print(f"  [{d['index']}] {d['name']} ({d['channels']} ch)")
        try:
            choice = input("Select device index (Enter for default): ").strip()
            if not choice:
                return None
            return int(choice)
        except (ValueError, EOFError):
            return None