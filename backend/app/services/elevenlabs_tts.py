import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("umi.tts")

TTS_BASE_URL = "https://api.elevenlabs.io/v1"

# Development-only categorization so backend logs explain WHY TTS failed.
TTS_CONFIG_ERROR = "TTS_CONFIG_ERROR"
TTS_AUTH_ERROR = "TTS_AUTH_ERROR"
TTS_PERMISSION_ERROR = "TTS_PERMISSION_ERROR"
TTS_QUOTA_ERROR = "TTS_QUOTA_ERROR"
TTS_NETWORK_ERROR = "TTS_NETWORK_ERROR"
TTS_PROVIDER_ERROR = "TTS_PROVIDER_ERROR"
TTS_AUDIO_ERROR = "TTS_AUDIO_ERROR"

# Optional voice tuning. Keep the numbers conservative for a natural, calm
# tone; the ElevenLabs API accepts stability/similarity_boost/style directly.
DEFAULT_VOICE_SETTINGS: dict[str, Any] | None = None


class TTSError(Exception):
    """Raised when the TTS provider fails to produce audio."""


class ElevenLabsTTS:
    """Thin, provider-specific wrapper around the ElevenLabs TTS API.

    The rest of the backend talks to this interface only — never to the
    provider SDK directly — so the provider can be swapped later. The API key
    never leaves this service and is never echoed into logs or responses.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        voice_settings: dict[str, Any] | None = DEFAULT_VOICE_SETTINGS,
        client: httpx.Client | None = None,
        base_url: str = TTS_BASE_URL,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.elevenlabs_api_key
        self._voice_id = voice_id if voice_id is not None else settings.elevenlabs_voice_id
        self._model_id = model_id if model_id is not None else settings.elevenlabs_model
        self._voice_settings = voice_settings
        self._base_url = base_url.rstrip("/")
        self._client = client

    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        model_id: str | None = None,
        metrics: dict | None = None,
    ) -> bytes:
        """Synthesize speech for `text` and return the raw audio bytes.

        Raises TTSError on any failure — missing key, empty text, network or
        provider errors. The API key is never included in any message.
        `metrics` (optional) is filled with tts_first_audio_ms (time to the
        first audio byte) for development latency logging.
        """
        if not self.is_configured():
            logger.error("%s: ElevenLabs API key is not configured", TTS_CONFIG_ERROR)
            raise TTSError("ElevenLabs API key is not configured")

        text = (text or "").strip()
        if not text:
            logger.error("%s: no text to synthesize", TTS_PROVIDER_ERROR)
            raise TTSError("No text to synthesize")

        metrics = {} if metrics is None else metrics
        url = f"{self._base_url}/text-to-speech/{voice_id or self._voice_id}"
        payload: dict[str, Any] = {
            "text": text,
            "model_id": model_id or self._model_id,
        }
        if self._voice_settings:
            payload["voice_settings"] = self._voice_settings

        headers = {
            "xi-api-key": self._api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        request = self._http.build_request("POST", url, headers=headers, json=payload)
        response = None
        try:
            response = self._http.send(request, stream=True)
            if response.status_code != 200:
                _ = response.read()
                category, detail = self._classify_error(response)
                logger.error(
                    "%s: ElevenLabs returned %s for voice %s (request_id=%s): %.300s",
                    category,
                    response.status_code,
                    voice_id or self._voice_id,
                    detail.get("request_id") or response.headers.get("x-request-id", "none"),
                    detail.get("message") or response.text,
                )
                raise TTSError(f"TTS provider returned HTTP {response.status_code}")

            blocks = bytearray()
            first_seen = False
            for block in response.iter_bytes(chunk_size=8192):
                if not first_seen:
                    first_seen = True
                    metrics["tts_first_audio_ms"] = round(
                        (time.perf_counter() - started) * 1000
                    )
                blocks.extend(block)
        except httpx.HTTPError as exc:
            logger.error("%s: ElevenLabs request failed: %s", TTS_NETWORK_ERROR, exc)
            raise TTSError("TTS provider request failed") from exc
        finally:
            if response is not None:
                response.close()

        audio = bytes(blocks)
        if not audio:
            logger.error(
                "%s: ElevenLabs returned empty audio for voice %s",
                TTS_AUDIO_ERROR,
                voice_id or self._voice_id,
            )
            raise TTSError("TTS provider returned empty audio")

        logger.info(
            "ElevenLabs TTS ok (%s chars, voice=%s, tts_first_audio_ms=%s)",
            len(text),
            voice_id or self._voice_id,
            metrics.get("tts_first_audio_ms"),
        )
        return audio

    @staticmethod
    def _classify_error(response: httpx.Response) -> tuple[str, dict[str, str]]:
        """Map a non-200 ElevenLabs response to a dev-log category + safe detail.

        The category/detail are written to the backend log only. Nothing here
        is ever returned to the frontend.
        """
        detail: dict[str, str] = {}
        if response.headers.get("x-contains-content-quota-error") == "true":
            return TTS_QUOTA_ERROR, {"message": "content quota exceeded"}

        try:
            body = response.json()
        except ValueError:
            return TTS_PROVIDER_ERROR, {"message": (response.text or "")[:300]}

        err = body.get("detail")
        if isinstance(err, dict):
            detail = {k: str(v) for k, v in err.items()}
        elif isinstance(err, str):
            detail = {"message": err}

        code = detail.get("code", "")
        status = response.status_code

        if status == 400 and code in {"invalid_api_key", "missing_api_key"}:
            return TTS_CONFIG_ERROR, detail
        if status in (401, 403):
            if status == 403:
                return TTS_PERMISSION_ERROR, detail
            return TTS_AUTH_ERROR, detail
        if status in (429, 499):
            return TTS_QUOTA_ERROR, detail
        return TTS_PROVIDER_ERROR, detail

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


tts_service = ElevenLabsTTS()