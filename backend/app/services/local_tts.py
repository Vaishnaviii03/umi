import logging
import os
import subprocess
import tempfile
import threading
import time

from app.config import settings

logger = logging.getLogger("umi.tts")

# macOS speech engine used by pyttsx3 ("nsss" = NSSpeechSynthesizer).
_ENGINE_NAME = "nsss"
# Output is synthesized to AIFF by NSSpeechSynthesizer, then converted to WAV so
# the audio plays in any Chromium/Electron/browser <audio> element.
_DEFAULT_AIFF_RATE_BPS = 22050

# Development-only categorization so backend logs explain WHY TTS failed.
TTS_UNAVAILABLE = "TTS_UNAVAILABLE_ERROR"
TTS_SYNTH_ERROR = "TTS_SYNTH_ERROR"
TTS_RENDER_ERROR = "TTS_RENDER_ERROR"
TTS_AUDIO_ERROR = "TTS_AUDIO_ERROR"

# Preferred default; falls back to the first available English-female voice,
# then the engine's system default.
DEFAULT_VOICE_ID = "com.apple.voice.compact.en-US.Samantha"

# Rate bounds for the pyttsx3 words-per-minute setting.
MIN_RATE = 60
MAX_RATE = 400


class TTSError(Exception):
    """Raised when the local TTS engine fails to produce audio."""


class LocalTTSProvider:
    """Local, zero-network TTS via pyttsx3 → macOS system speech voices.

    Synthesis is serialized under a lock: a single `NSSpeechSynthesizer` instance
    backs all requests (it is not safe for concurrent speaks, and the frontend
    prefetches several sentences in parallel during a voice turn). `synthesize`
    renders the speech to an AIFF temp file, converts it to WAV, and returns the
    bytes — so the existing `/tts` → frontend-blob → playback contract is
    preserved. On macOS, the synthesizer's completion is delivered to the main
    run loop, so we poll `isSpeaking()` instead of relying on `runAndWait()` —
    which otherwise returns early on non-main worker threads and truncates the
    audio (see `_render`).
    """

    def __init__(
        self,
        *,
        voice_id: str | None = None,
        rate: float | None = None,
        volume: float | None = None,
        renderer: object | None = None,
        converter: object | None = None,
    ) -> None:
        self._voice_id = voice_id if voice_id is not None else settings.local_tts_voice
        self._rate = self._clamp_rate(rate if rate is not None else settings.local_tts_rate)
        self._volume = max(0.0, min(1.0, volume if volume is not None else settings.local_tts_volume))
        # Injectable seams for tests: renderer(text, path) → pyttsx3 engine call
        # that writes an audio file; converter(path) → bytes of a playable file.
        self._renderer = renderer
        self._converter = converter if converter is not None else self._aiff_to_wav_bytes
        self._lock = threading.Lock()
        self._engine = None

    @staticmethod
    def _clamp_rate(rate: float) -> int:
        return int(max(MIN_RATE, min(MAX_RATE, float(rate))))

    def _engine_ref(self):
        """Lazily build the pyttsx3 engine and apply voice/rate/volume."""
        if self._engine is None:
            import pyttsx3

            try:
                engine = pyttsx3.init(_ENGINE_NAME)
            except Exception as exc:  # pragma: no cover - OS-specific
                logger.error("%s: pyttsx3 init failed: %s", TTS_UNAVAILABLE, exc)
                raise TTSError("Local TTS unavailable") from exc
            voice_id = self._select_voice(engine)
            try:
                if voice_id:
                    engine.setProperty("voice", voice_id)
                engine.setProperty("rate", self._rate)
                engine.setProperty("volume", self._volume)
            except Exception as exc:  # pragma: no cover - OS-specific
                logger.error("%s: failed to configure speech engine: %s", TTS_UNAVAILABLE, exc)
                raise TTSError("Local TTS unavailable") from exc
            logger.info(
                "Local TTS ready (voice=%s rate=%s volume=%s)",
                voice_id or "system-default",
                self._rate,
                self._volume,
            )
            self._engine = (engine, voice_id)
        return self._engine

    def _select_voice(self, engine) -> str | None:
        """Resolve the configured voice, falling back to an available
        English-female voice, then the engine default. Never crashes."""
        if self._voice_id:
            try:
                configured = engine.getProperty("voice")
                available = {v.id: v for v in engine.getProperty("voices")}
            except Exception:  # pragma: no cover - OS-specific
                return None
            if self._voice_id in available:
                return self._voice_id
            # Fall back to the most natural English-female voice we have.
            preferred = [v.id for v in available.values() if self._is_en_female(v)]
            if preferred:
                logger.warning(
                    "Configured voice %r unavailable; falling back to %r",
                    self._voice_id,
                    preferred[0],
                )
                return preferred[0]
            logger.warning(
                "Configured voice %r unavailable; using system default voice",
                self._voice_id,
            )
            return None
        return None

    @staticmethod
    def _is_en_female(voice) -> bool:
        gender = getattr(voice, "gender", None)
        langs = [str(x) for x in (getattr(voice, "languages", None) or [])]
        en = any(lang.replace("_", "-").lower().startswith("en") for lang in langs)
        female = "female" in str(gender or "").lower()
        return en and female

    def list_voices(self) -> list[dict]:
        """Safe diagnostic listing — IDs/names/languages only, no secrets."""
        try:
            engine, _ = self._engine_ref()
            out = []
            for v in engine.getProperty("voices"):
                out.append(
                    {
                        "id": getattr(v, "id", ""),
                        "name": getattr(v, "name", ""),
                        "language": (getattr(v, "languages", None) or [None])[0],
                        "gender": str(getattr(v, "gender", "")),
                    }
                )
            return out
        except Exception as exc:
            logger.error("%s: cannot list voices: %s", TTS_UNAVAILABLE, exc)
            raise TTSError("Local TTS unavailable") from exc

    def current_voice(self) -> str | None:
        try:
            _, voice_id = self._engine_ref()
            return voice_id
        except TTSError:
            return None

    def is_available(self) -> bool:
        try:
            self._engine_ref()
            return True
        except TTSError:
            return False

    # Kept for provider compatibility (routes gate on it).
    def is_configured(self) -> bool:
        return True

    def synthesize(
        self,
        text: str,
        *,
        metrics: dict | None = None,
    ) -> bytes:
        """Synthesize `text` locally and return playable WAV bytes."""
        text = (text or "").strip()
        if not text:
            logger.error("%s: no text to synthesize", TTS_SYNTH_ERROR)
            raise TTSError("No text to synthesize")

        metrics = {} if metrics is None else metrics
        started = time.perf_counter()
        with self._lock:
            try:
                engine, voice_id = self._engine_ref()
            except TTSError:
                raise
            tmp_aiff = None
            tmp_wav = None
            try:
                fd, tmp_aiff = tempfile.mkstemp(suffix=".aiff")
                os.close(fd)
                self._render(engine, text, tmp_aiff)
                audio = self._converter(tmp_aiff)
                metrics["tts_first_audio_ms"] = round((time.perf_counter() - started) * 1000)
            except TTSError:
                logger.exception("%s: synthesis failed", TTS_RENDER_ERROR)
                raise
            finally:
                for path in (tmp_aiff, tmp_wav):
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass

        if not audio:
            logger.error("%s: local TTS returned empty audio", TTS_AUDIO_ERROR)
            raise TTSError("Local TTS returned empty audio")

        logger.info(
            "Local TTS ok (%s chars, voice=%s, tts_first_audio_ms=%s)",
            len(text),
            voice_id or "system-default",
            metrics.get("tts_first_audio_ms"),
        )
        return audio

    def _render(self, engine, text: str, path: str) -> None:
        """Render `text` to an audio file at `path`.

        On macOS, `NSSpeechSynthesizer` posts completion to the main run loop,
        so pyttsx3's `runAndWait()` returns before synthesis finishes when the
        backend worker threads run on a non-main thread — producing truncated
        audio. We therefore drive the driver directly and poll the
        synthesizer's `isSpeaking()` state instead, which completes reliably
        from any thread.
        """
        if self._renderer is not None:
            self._renderer(engine, text, path)
            return
        driver = getattr(getattr(engine, "proxy", None), "_driver", None)
        tts = getattr(driver, "_tts", None) if driver is not None else None
        if tts is not None:
            driver.save_to_file(text, path)
            deadline = time.time() + 60.0
            while tts.isSpeaking() and time.time() < deadline:
                time.sleep(0.02)
            if tts.isSpeaking():
                raise TTSError("Local TTS timed out")
            # Give the file writer a moment to finish flushing before reading.
            time.sleep(0.15)
        else:  # pragma: no cover - test engines only
            engine.save_to_file(text, path)
            engine.runAndWait()
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise TTSError("Local TTS produced no audio")

    @staticmethod
    def _aiff_to_wav_bytes(aiff_path: str) -> bytes:
        """Convert the AIFF produced by NSSpeechSynthesizer to WAV bytes via the
        built-in macOS `afconvert` tool."""
        from tempfile import NamedTemporaryFile

        tmp_wav = NamedTemporaryFile(suffix=".wav", delete=False)
        wav_path = tmp_wav.name
        tmp_wav.close()
        try:
            result = subprocess.run(
                [
                    "/usr/bin/afconvert",
                    "-f", "WAVE",
                    "-d", f"LEI16@{_DEFAULT_AIFF_RATE_BPS}",
                    aiff_path,
                    wav_path,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not os.path.exists(wav_path):
                logger.error("%s: afconvert failed: %s", TTS_RENDER_ERROR, result.stderr.strip()[:200])
                raise TTSError("Local TTS render failed")
            with open(wav_path, "rb") as fh:
                return fh.read()
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def speak(self, text: str) -> None:
        """Speak `text` directly through system audio (blocks until done)."""
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            engine, _ = self._engine_ref()
            driver = getattr(getattr(engine, "proxy", None), "_driver", None)
            tts = getattr(driver, "_tts", None) if driver is not None else None
            if tts is not None:
                driver.say(text)
                deadline = time.time() + 60.0
                while tts.isSpeaking() and time.time() < deadline:
                    time.sleep(0.02)
            else:  # pragma: no cover - test engines only
                engine.say(text)
                engine.runAndWait()

    def stop(self) -> None:
        """Interrupt any in-flight speech/rendering, if supported."""
        try:
            engine, _ = self._engine_ref()
            engine.stop()
        except Exception:  # pragma: no cover - OS-specific
            pass

    def close(self) -> None:
        self._engine = None


tts_service = LocalTTSProvider()