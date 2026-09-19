import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import LauncherConfig
from detector import detector_from_config

logger = logging.getLogger("umi.launcher")

# IPC socket path for single-instance activation
IPC_SOCKET_PATH = "/tmp/umi_launcher_ipc.sock"

# Directory containing this launcher module
HERE = Path(__file__).resolve().parent


def resolve_desktop_main(config: LauncherConfig) -> Path:
    """Determine how to launch the desktop app.

    During development we can run Electron against the real desktop directory.
    In production this may be replaced by the packaged app binary.
    """
    return config.desktop_dir


def check_mic_permission() -> bool:
    """Check if microphone permission is granted on macOS."""
    if sys.platform != "darwin":
        return True
    try:
        import subprocess
        # Check TCC database for microphone permission
        result = subprocess.run(
            ["osascript", "-e", "tell application \"System Events\" to get microphone access"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "granted" in result.stdout.lower()
    except Exception:
        return False


def request_mic_permission() -> bool:
    """Request microphone permission on macOS."""
    if sys.platform != "darwin":
        return True
    try:
        import subprocess
        # Trigger permission prompt by attempting to access microphone
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get microphone access'],
            timeout=5
        )
        return True
    except Exception:
        return False


def send_activation_signal() -> bool:
    """Send activation signal to existing Umi desktop instance via Unix socket."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(IPC_SOCKET_PATH)
        sock.send(b"UMI_ACTIVATE\n")
        sock.close()
        logger.info("Activation signal sent to existing Umi instance")
        return True
    except (ConnectionRefusedError, FileNotFoundError, socket.timeout, OSError):
        return False
    except Exception as e:
        logger.debug("Failed to send activation signal: %s", e)
        return False


def start_ipc_server(config: LauncherConfig) -> socket.socket | None:
    """Start Unix socket server for receiving activation signals."""
    try:
        # Clean up any existing socket
        try:
            os.unlink(IPC_SOCKET_PATH)
        except FileNotFoundError:
            pass
        except OSError:
            pass

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(IPC_SOCKET_PATH)
        sock.listen(1)
        sock.settimeout(0.5)  # Non-blocking with short timeout
        logger.info("IPC server started at %s", IPC_SOCKET_PATH)
        return sock
    except Exception as e:
        logger.warning("Failed to start IPC server: %s", e)
        return None


def run_detector_loop(config: LauncherConfig, dry_run: bool = False) -> None:
    detector = detector_from_config(config)
    block_len = int(config.sample_rate * config.block_ms / 1000.0)

    def on_double_clap():
        if dry_run:
            logger.info("DOUBLE_CLAP_DETECTED (dry run) — desktop NOT launched")
            return
        logger.info("DOUBLE_CLAP_DETECTED (count=%d)", detector.trigger_count)
        # Try to activate existing instance first
        if not send_activation_signal():
            launch_desktop()

    def callback(indata, frames, time_info, status) -> None:
        if status:
            logger.warning("audio status: %s", status)
        block = np.array(indata[:, 0], dtype=np.float32)
        if detector.process_block(block):
            on_double_clap()

    # Check microphone permission
    if not check_mic_permission():
        logger.warning("Microphone permission not granted. Requesting...")
        request_mic_permission()
        time.sleep(1)

    # Validate audio device
    if config.device is not None:
        try:
            sd.check_input_settings(device=config.device, samplerate=config.sample_rate, channels=1)
        except Exception as e:
            logger.error("Invalid audio device %s: %s", config.device, e)
            # Try to find a working input device
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                for i, d in enumerate(devices):
                    if d["max_input_channels"] > 0:
                        logger.info("Falling back to device %d: %s", i, d["name"])
                        config.device = i
                        break
            except Exception:
                pass

    logger.info(
        "listening (device=%s, rate=%d, sensitivity=%d, clap_thr=%.1f dB, %s)",
        config.device,
        config.sample_rate,
        config.sensitivity,
        config.clap_threshold_db,
        "dry run" if dry_run else "launch on clap",
    )

    ipc_sock = None
    if not dry_run:
        ipc_sock = start_ipc_server(config)

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
                # Handle IPC connections
                if ipc_sock:
                    try:
                        conn, _ = ipc_sock.accept()
                        data = conn.recv(1024)
                        if data and b"UMI_ACTIVATE" in data:
                            logger.info("Activation signal received via IPC")
                        conn.close()
                    except socket.timeout:
                        pass
                    except Exception as e:
                        logger.debug("IPC error: %s", e)
                sd.sleep(100)
    except KeyboardInterrupt:
        logger.info("stopping launcher")
    except Exception as exc:
        logger.error("audio stream error: %s", exc)
        raise
    finally:
        if ipc_sock:
            ipc_sock.close()
        try:
            os.unlink(IPC_SOCKET_PATH)
        except Exception:
            pass


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
    parser.add_argument("--list-devices", action="store_true", help="list available audio input devices")
    parser.add_argument("--select-device", action="store_true", help="interactively select microphone device")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = LauncherConfig()
    if args.list_devices:
        devices = cfg.get_input_devices()
        if not devices or "error" in devices[0]:
            print(f"Error listing devices: {devices}")
        else:
            print("Available input devices:")
            for d in devices:
                print(f"  [{d['index']}] {d['name']} ({d['channels']} ch)")
        return

    if args.select_device:
        idx = cfg.select_device_interactive()
        if idx is not None:
            # Write to .env
            env_path = HERE / ".env"
            env_content = f"UMI_MIC_DEVICE={idx}\n"
            if env_path.exists():
                content = env_path.read_text()
                lines = [line for line in content.splitlines() if not line.startswith("UMI_MIC_DEVICE")]
                content = "\n".join(lines) + "\n"
            env_path.write_text(content + f"UMI_MIC_DEVICE={idx}\n")
            print(f"Selected device {idx} saved to .env")
        return

    if args.calibrate:
        calibrate(cfg)
    else:
        run_detector_loop(cfg, dry_run=args.test)


if __name__ == "__main__":
    sys.exit(main())