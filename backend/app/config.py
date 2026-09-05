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

    # Phase 2.5 — ElevenLabs text-to-speech (voice output). The API key is a
    # server-side secret; leave empty to disable voice (text still works).
    elevenlabs_api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
    # Umi's voice is "Ash". Voice IDs are not secrets.
    elevenlabs_voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", "m3yAHyFEFKtbCIM5n7GF")
    # Current-API model. eleven_turbo_v2_5 is deprecated; eleven_flash_v2_5 is
    # its officially recommended functional replacement (same languages, lower
    # latency).
    elevenlabs_model: str = os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5")

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


settings = Settings()
