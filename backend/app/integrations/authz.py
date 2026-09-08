from app.config import settings

_UNKNOWN_REFUSAL = (
    "I only respond to my owner on this platform. "
    "If you're the owner, set {owner_env} in the backend environment and "
    "restart me."
)


def _owner_id_for(platform: str) -> str | None:
    if platform == "discord":
        return settings.discord_owner_id
    if platform == "telegram":
        return settings.telegram_owner_id
    return None


def _owner_env_for(platform: str) -> str:
    return "DISCORD_OWNER_ID" if platform == "discord" else "TELEGRAM_OWNER_ID"


def resolve_role(platform: str, platform_user_id: str | int) -> str:
    """Return ``"owner"`` when the platform user id matches the configured owner
    id for that platform, else ``"unknown"``. Missing owner id -> unknown."""
    owner_id = _owner_id_for(platform)
    if not owner_id:
        return "unknown"
    return "owner" if str(platform_user_id).strip() == owner_id.strip() else "unknown"


def refusal_text(platform: str, author_name: str | None = None) -> str:
    return _UNKNOWN_REFUSAL.format(owner_env=_owner_env_for(platform))