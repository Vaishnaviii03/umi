import logging
import subprocess
import sys
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import LauncherConfig
from detector import detector_from_config

logger = logging.getLogger("umi.launcher")


def resolve_desktop_main(config: LauncherConfig) -> Path:
    """Determine how to launch the desktop app.

    During development we can run Electron against the real desktop directory.
    In production this may be replaced by the packaged app binary.
    """
    return config.desktop_dir


def run_detector_loop(config: LauncherConfig, dry_run: bool = False) -> None:
    detector = detector_from_config(config)
    block_len = int(config.sample_rate * config.block_ms / 1000.0)

    def on_double_clap():
        if dry_run:
            logger.info("DOUBLE_CLAP_DETECTED (dry run) — desktop NOT launched")
            return
        logger.info("DOUBLE_CLAP_DETECTED (count=%d)", detector.trigger_count)
        launch_desktop()

    def callback(indata, frames, time_info, status) -> None:
        if status:
            logger.warning("audio status: %s", status)
        block = np.array(indata[:, 0], dtype=np.float32)
        if detector.process_block(block):
            on_double_clap()

    logger.info(
        "listening (device=%s, rate=%d, sensitivity=%d, clap_thr=%.1f dB, %s)",
        config.device,
        config.sample_rate,
        config.sensitivity,
        config.clap_threshold_db,
        "dry run" if dry_run else "launch on clap",
    )
    try:
        with sd.InputStream(
            samplerate=config.sample_rate,
            blocksize=block_len,
            device=config.device,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            logger.info("microphone stream open — double clap to trigger")
            # Keep the process alive.
            while True:
                sd.sleep(1000)
    except KeyboardInterrupt:
        logger.info("stopping launcher")
    except Exception as exc:
        logger.error("audio stream error: %s", exc)
        raise


def launch_desktop() -> None:
    cfg = LauncherConfig()
    electron = str(cfg.electron_bin)
    if not Path(electron).exists():
        logger.error("electron binary not found: %s", electron)
        return
    main = str(resolve_desktop_main(cfg))
    logger.info("launching UMI desktop via %s %s", electron, main)
    try:
        subprocess.Popen([electron, main], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.error("failed to launch desktop: %s", exc)


def calibrate(config: LauncherConfig) -> None:
    """Print live peak levels so the user can choose a sensitivity and threshold."""
    block_len = int(config.sample_rate * config.block_ms / 1000.0)
    print(f"calibrating against clap threshold {config.clap_threshold_db:.1f} dB "
          f"(quiet {config.quiet_threshold_db:.1f} dB) — clap once, then clap twice")

    def callback(indata, frames, time_info, status) -> None:
        block = np.array(indata[:, 0], dtype=np.float32)
        peak = float(np.max(np.abs(block)))
        peak_db = 20.0 * np.log10(peak + 1e-9)
        bar = "#" * max(0, int((peak_db + 60) / 3))
        print(f"peak {peak_db:6.1f} dB |{bar}", flush=True)

    try:
        with sd.InputStream(
            samplerate=config.sample_rate,
            blocksize=block_len,
            device=config.device,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            sd.sleep(1000000)
    except KeyboardInterrupt:
        pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="umi-launcher", description="UMI background launcher — double clap to launch the UMI desktop app")
    parser.add_argument("--test", action="store_true", help="dry run: detect double claps without launching anything")
    parser.add_argument("--calibrate", action="store_true", help="print live mic peak levels to tune sensitivity")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = LauncherConfig()
    if args.calibrate:
        calibrate(cfg)
    else:
        run_detector_loop(cfg, dry_run=args.test)


if __name__ == "__main__":
    sys.exit(main())