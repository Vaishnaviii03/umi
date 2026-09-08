import os
from dotenv import load_dotenv

load_dotenv()


def _cors_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class Settings:
    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    llm_model: str = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    # Fast conversational model for casual chat / voice turns. It must produce
    # first-content tokens quickly (no long hidden reasoning). Falls back to
    # llm_model when unset.
    llm_fast_model: str = os.environ.get("LLM_FAST_MODEL", "openai/gpt-5.4-mini")

    def model_for(self, fast: bool) -> str:
        return self.llm_fast_model or self.llm_model if fast else self.llm_model

    # Phase 2.5 — ElevenLabs Scribe realtime STT (voice input). The API key is
    # a server-side secret; the backend mints short-lived single-use tokens for
    # the browser. Keep in sync with app/services/elevenlabs_token.py.
    elevenlabs_api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
    # Local TTS (voice output) via pyttsx3 → macOS system speech. All synthesis
    # happens on this machine; no external TTS API, no key, no network call.
    local_tts_voice: str = os.environ.get(
        "TTS_VOICE", "com.apple.voice.compact.en-US.Samantha"
    )
    # Speech rate in words-per-minute (pyttsx3) and volume 0.0–1.0.
    local_tts_rate: float = float(os.environ.get("TTS_RATE", "180"))
    local_tts_volume: float = float(os.environ.get("TTS_VOLUME", "1.0"))

    # Database (Phase 2). Supabase/PostgreSQL connection string.
    # Leave empty to run without persistence (graceful degradation).
    database_url: str = os.environ.get("SUPABASE_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")

    # The local owner account (a real Supabase Auth user). Defaults to a
    # placeholder for standalone/test runs without Supabase.
    owner_id: str = os.environ.get(
        "UMI_OWNER_ID", "00000000-0000-0000-0000-000000000001"
    )

    @property
    def db_enabled(self) -> bool:
        return bool(self.database_url)

    # Explicit allowlist of exact origins (comma-separated). Used by the remote
    # browser (dev) frontend. Kept env-driven; never set to ["*"].
    cors_origins: list[str] = _cors_origins(
        os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    )

    # Regex for Umi's local development/desktop origins. The desktop shell serves
    # the UI on 127.0.0.1:3456 (port configurable via the UMI_FRONTEND_PORT env var), so the
    # origin port is not fixed. Restricted to localhost only — remote origins must
    # be listed explicitly in CORS_ORIGINS. Empty string disables the regex.
    cors_origin_regex: str = os.environ.get(
        "CORS_ORIGIN_REGEX", r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    )

    # Phase 3 — tool system. The backend is the boundary: the LLM proposes tool
    # calls, the ToolManager validates + permits + executes. `tools_enabled`
    # can hard-disable the whole capability framework; the maximum permission
    # level the backend will auto-run (1=read, 2=write, 3=sensitive, 4=destructive,
    # 5=high-risk) is enforced centrally so higher-risk tools stay inert until a
    # human raises the ceiling.
    tools_enabled: bool = os.environ.get("UMI_TOOLS_ENABLED", "1").strip().lower() not in ("0", "false", "no")
    tools_max_permission_level: int = int(os.environ.get("UMI_TOOLS_MAX_LEVEL", "2"))

    # Phase 5 — Gmail. OAuth 2.0 (Google Cloud project → Gmail API → OAuth
    # Desktop/Web client). The redirect URI below must be registered in the
    # Google client under "Authorized redirect URIs". Tokens are saved to a
    # local, owner-only file (see app/services/gmail/token_store.py) and never
    # touch the database or the client.
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/gmail/oauth/callback"
    )
    gmail_token_path: str = os.environ.get("GMAIL_TOKEN_PATH", "~/.umi/gmail_token.json")

    @property
    def gmail_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    # Phase 8 — Discord + Telegram integrations. The tokens are server-side
    # secrets; they are read from backend/.env and never exposed to the
    # browser. Owner ids pin which platform user may speak to Umi; every other
    # user receives a polite refusal with no LLM/tool/database access.
    discord_application_id: str = os.environ.get("DISCORD_APPLICATION_ID", "")
    discord_public_key: str = os.environ.get("DISCORD_PUBLIC_KEY", "")
    discord_bot_token: str = os.environ.get("DISCORD_BOT_TOKEN", "")
    discord_owner_id: str = os.environ.get("DISCORD_OWNER_ID", "")
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_owner_id: str = os.environ.get("TELEGRAM_OWNER_ID", "")

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_bot_token)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


settings = Settings()
