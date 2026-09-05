from datetime import datetime


def local_time_description() -> str:
    """Human-readable local time in the owner's timezone.

    Provides a reliable, non-hardcoded time source that can later be promoted
    into Umi's tool system. No magic timestamps — always computed at call time.
    """
    now = datetime.now().astimezone()
    clock = now.strftime("%I:%M %p").lstrip("0")
    return f"{now.strftime('%A, %B')} {now.day}, {now.year} at {clock}"