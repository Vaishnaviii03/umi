from pathlib import Path
from app.orchestrator.soul import get_soul_prompt, resolve_soul_path
from app.orchestrator.core import _build_context


def test_resolve_soul_path():
    path = resolve_soul_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "Soul.md"


def test_soul_prompt_content():
    prompt = get_soul_prompt()
    assert "You are **Umi**" in prompt
    assert "Boss" in prompt
    assert "Be useful. Be intelligent. Be warm. Be honest. Help Boss move forward." in prompt


def test_build_context_contains_soul_nature():
    system, time_block, history, conv, created = _build_context(
        db=None,
        message="Hello",
        platform_context=None,
    )
    assert "You are **Umi**" in system
    assert "Boss" in system
    assert "The user's current local date and time is" in time_block
