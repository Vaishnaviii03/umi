import logging

import httpx

from app.config import settings

logger = logging.getLogger("umi.token")

SINGLE_USE_TOKEN_URL = "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe"


class ElevenLabsTokenError(Exception):
    """Raised when a single-use client token cannot be minted."""


class ElevenLabsTokenMinter:
    """Mints short-lived, single-use ElevenLabs tokens for client-side use.

    The real API key never leaves this backend — the frontend receives only a
    time-bound token (expires in ~15 minutes and is consumed on first use).
    """

    def __init__(self, *, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self._api_key = api_key if api_key is not None else settings.elevenlabs_api_key
        self._client = client

    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def mint(self) -> str:
        if not self.is_configured():
            raise ElevenLabsTokenError("ElevenLabs API key is not configured")

        headers = {"xi-api-key": self._api_key}
        try:
            response = self._http.post(SINGLE_USE_TOKEN_URL, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("ElevenLabs token mint failed: %s", exc)
            raise ElevenLabsTokenError("failed to mint single-use token") from exc

        if response.status_code != 200:
            logger.error(
                "ElevenLabs token mint returned %s: %.200s",
                response.status_code,
                response.text,
            )
            raise ElevenLabsTokenError(f"token endpoint returned HTTP {response.status_code}")

        data = response.json()
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            logger.error("ElevenLabs token mint returned no token")
            raise ElevenLabsTokenError("token endpoint returned no token")

        logger.info("ElevenLabs single-use token minted")
        return token

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


token_minter = ElevenLabsTokenMinter()