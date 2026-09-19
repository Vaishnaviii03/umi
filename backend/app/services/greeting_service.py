from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import pytz


@dataclass
class GreetingConfig:
    morning_start: int = 5
    morning_end: int = 11
    afternoon_start: int = 12
    afternoon_end: int = 16
    evening_start: int = 17
    evening_end: int = 20
    # night: 21-4


@dataclass
class GreetingVariants:
    morning: list[str] = (
        "Good morning, Boss.",
        "Good morning, Boss. Ready to get started?",
        "Good morning, Boss. What are we working on today?",
    )
    afternoon: list[str] = (
        "Good afternoon, Boss.",
        "Good afternoon, Boss. How's the day going?",
        "Afternoon, Boss. Ready when you are.",
    )
    evening: list[str] = (
        "Good evening, Boss.",
        "Good evening, Boss. What are we building tonight?",
        "Evening, Boss. What's on the agenda?",
    )
    night: list[str] = (
        "You're up late, Boss.",
        "Late night, Boss. What are we working on?",
        "Hey, Boss. Still building?",
    )


class GreetingService:
    def __init__(
        self,
        timezone: str = "Asia/Kolkata",
        config: Optional[GreetingConfig] = None,
        variants: Optional[GreetingVariants] = None,
    ):
        self.timezone = pytz.timezone(timezone)
        self.config = config or GreetingConfig()
        self.variants = variants or GreetingVariants()

    def get_current_hour(self, dt: Optional[datetime] = None) -> int:
        """Get current hour in the configured timezone."""
        if dt is None:
            dt = datetime.now(self.timezone)
        elif dt.tzinfo is None:
            dt = self.timezone.localize(dt)
        else:
            dt = dt.astimezone(self.timezone)
        return dt.hour

    def get_greeting_period(self, hour: Optional[int] = None) -> str:
        """Determine the greeting period based on hour."""
        if hour is None:
            hour = self.get_current_hour()

        c = self.config
        if c.morning_start <= hour <= c.morning_end:
            return "morning"
        elif c.afternoon_start <= hour <= c.afternoon_end:
            return "afternoon"
        elif c.evening_start <= hour <= c.evening_end:
            return "evening"
        else:
            return "night"

    def get_greeting(
        self,
        hour: Optional[int] = None,
        variant_index: Optional[int] = None,
        context: str = "startup",  # "startup", "text_chat", "voice_chat", "late_night_chat"
    ) -> str:
        """Get a contextual greeting."""
        if hour is None:
            hour = self.get_current_hour()

        period = self.get_greeting_period(hour)
        variants = getattr(self.variants, period)

        # Select variant - use minute-based selection for variety
        if variant_index is None:
            now = datetime.now(self.timezone)
            variant_index = (now.minute // 5) % len(variants)

        base_greeting = variants[variant_index % len(variants)]

        # Add context-aware variations for late night
        if period == "night" and context in ("text_chat", "voice_chat"):
            # If user is chatting late, acknowledge they're up late naturally
            if "late" not in base_greeting.lower() and "up late" not in base_greeting.lower():
                pass  # Use the default night variants which are already contextual

        return base_greeting

    def get_full_greeting(
        self,
        hour: Optional[int] = None,
        variant_index: Optional[int] = None,
        context: str = "startup",
    ) -> str:
        """Get greeting with optional follow-up."""
        greeting = self.get_greeting(hour, variant_index, context)

        # Add follow-up question based on time of day
        hour = hour or self.get_current_hour()
        period = self.get_greeting_period(hour)

        follow_ups = {
            "morning": [
                "Ready to build something?",
                "What are we working on today?",
                "How can I help?",
            ],
            "afternoon": [
                "How's the day going?",
                "Ready when you are.",
                "What's next?",
            ],
            "evening": [
                "What are we building tonight?",
                "What's on the agenda?",
                "How can I help?",
            ],
            "night": [
                "What are we working on?",
                "Still building?",
                "How can I help?",
            ],
        }

        if period == "night" and context in ("text_chat", "voice_chat"):
            # Late night chat - acknowledge naturally
            follow_up = "What are we working on?"
        else:
            follow_ups_list = follow_ups.get(period, ["How can I help?"])
            now = datetime.now(self.timezone)
            follow_up = follow_ups_list[(now.minute // 10) % len(follow_ups_list)]

        return f"{greeting} {follow_up}"


# Global instance
_greeting_service: Optional[GreetingService] = None


def get_greeting_service() -> GreetingService:
    global _greeting_service
    if _greeting_service is None:
        _greeting_service = GreetingService()
    return _greeting_service