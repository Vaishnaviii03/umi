import os

import pytest

from app.services.local_tts import (
    DEFAULT_VOICE_ID,
    MAX_RATE,
    MIN_RATE,
    LocalTTSProvider,
    TTSError,
)

SAMANTHA = "com.apple.voice.compact.en-US.Samantha"


class FakeVoice:
    def __init__(self, id, name, languages, gender):
        self.id = id
        self.name = name
        self.languages = [languages]
        self.gender = gender


class FakeEngine:
    def __init__(self, voices):
        self.calls = []
        self.props = {}
        self._voices = voices

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        if key == "voices":
            return self._voices
        return self.props.get(key)

    def save_to_file(self, text, path):
        self.calls.append(("save", text, path))
        with open(path, "wb") as fh:
            fh.write(b"\x00" * 256)  # pretend rendered audio

    def runAndWait(self):
        self.calls.append(("wait",))

    def say(self, text):
        self.calls.append(("say", text))

    def stop(self):
        self.calls.append(("stop",))


def voices_for(*ids):
    mapping = {
        SAMANTHA: FakeVoice(SAMANTHA, "Samantha", "en_US", "VoiceGenderFemale"),
        "com.apple.voice.compact.en-AU.Karen": FakeVoice(
            "com.apple.voice.compact.en-AU.Karen", "Karen", "en_AU", "VoiceGenderFemale"
        ),
        "com.apple.voice.compact.en-GB.Daniel": FakeVoice(
            "com.apple.voice.compact.en-GB.Daniel", "Daniel", "en_GB", "VoiceGenderMale"
        ),
        "com.apple.speech.synthesis.voice.Albert": FakeVoice(
            "com.apple.speech.synthesis.voice.Albert", "Albert", "en_US", "VoiceGenderNeuter"
        ),
    }
    return [mapping[i] for i in ids]


def make_provider(monkeypatch, engine=None, **kwargs):
    used = {"engine": engine or FakeEngine([])}
    monkeypatch.setattr("pyttsx3.init", lambda name: used["engine"])
    return LocalTTSProvider(**kwargs), used["engine"]


def test_synthesize_renders_locally_no_network(monkeypatch):
    engine = FakeEngine(voices_for(SAMANTHA))
    provider = LocalTTSProvider(
        voice_id=SAMANTHA,
        converter=lambda path: b"RIFFFAKEWAVE",
    )
    monkeypatch.setattr("pyttsx3.init", lambda name: engine)
    metrics = {}
    audio = provider.synthesize("  hello there  ", metrics=metrics)
    assert audio == b"RIFFFAKEWAVE"
    assert any(c[0] == "save" and c[1] == "hello there" for c in engine.calls)
    assert ("wait",) in engine.calls
    assert engine.props["voice"] == SAMANTHA
    assert metrics.get("tts_first_audio_ms") is not None


def test_empty_text_raises(monkeypatch):
    provider, engine = make_provider(monkeypatch, engine=FakeEngine([]))
    with pytest.raises(TTSError):
        provider.synthesize("   ")


def test_render_failure_raises(monkeypatch):
    def renderer(engine, text, path):
        raise TTSError("renderer exploded")

    provider, engine = make_provider(monkeypatch, renderer=renderer)
    with pytest.raises(TTSError):
        provider.synthesize("hello")


def test_empty_audio_raises(monkeypatch):
    provider, engine = make_provider(monkeypatch, converter=lambda path: b"")
    with pytest.raises(TTSError):
        provider.synthesize("hello")


def test_configured_voice_used_when_present(monkeypatch):
    provider, engine = make_provider(
        monkeypatch, engine=FakeEngine(voices_for(SAMANTHA)), voice_id=SAMANTHA
    )
    provider._engine_ref()
    assert engine.props["voice"] == SAMANTHA
    assert provider.current_voice() == SAMANTHA


def test_missing_voice_falls_back_to_en_female(monkeypatch):
    engine = FakeEngine(voices_for("com.apple.voice.compact.en-AU.Karen", "com.apple.voice.compact.en-GB.Daniel"))
    provider, engine = make_provider(monkeypatch, engine=engine, voice_id=SAMANTHA)
    provider._engine_ref()
    assert engine.props["voice"] == "com.apple.voice.compact.en-AU.Karen"


def test_no_female_voice_uses_engine_default(monkeypatch):
    engine = FakeEngine(voices_for("com.apple.speech.synthesis.voice.Albert"))
    provider, engine = make_provider(monkeypatch, engine=engine, voice_id=SAMANTHA)
    provider._engine_ref()
    assert engine.props.get("voice") is None
    assert provider.current_voice() is None


def test_rate_clamped_and_volume_bounded(monkeypatch):
    provider, engine = make_provider(monkeypatch, rate=99999, volume=99)
    provider._engine_ref()
    assert engine.props["rate"] == MAX_RATE
    assert engine.props["volume"] == 1.0

    provider, engine = make_provider(monkeypatch, rate=-5, volume=-1)
    provider._engine_ref()
    assert engine.props["rate"] == MIN_RATE
    assert engine.props["volume"] == 0.0


def test_list_voices_safe_fields_only(monkeypatch):
    provider, engine = make_provider(
        monkeypatch, engine=FakeEngine(voices_for(SAMANTHA, "com.apple.voice.compact.en-GB.Daniel"))
    )
    voices = provider.list_voices()
    assert len(voices) == 2
    first = voices[0]
    assert set(first) == {"id", "name", "language", "gender"}
    assert first["language"] == "en_US"


def test_pyttsx3_unavailable_marks_unavailable(monkeypatch):
    def boom(name):
        raise RuntimeError("no speech framework")

    monkeypatch.setattr("pyttsx3.init", boom)
    provider = LocalTTSProvider()
    assert provider.is_available() is False
    with pytest.raises(TTSError):
        provider.list_voices()
    with pytest.raises(TTSError):
        provider.synthesize("hello")


def test_speak_and_stop_paths(monkeypatch):
    engine = FakeEngine(voices_for(SAMANTHA))
    provider, engine = make_provider(monkeypatch, engine=engine)
    provider.speak("  hi  ")
    assert ("say", "hi") in engine.calls
    assert ("wait",) in engine.calls
    provider.stop()
    assert ("stop",) in engine.calls


def test_aiff_to_wav_bytes_via_afconvert(tmp_path, monkeypatch):
    import subprocess

    aiff = tmp_path / "in.aiff"
    aiff.write_bytes(b"\x00\x10" * 16)

    import app.services.local_tts as local_tts

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "/usr/bin/afconvert"
        wav = cmd[-1]
        with open(wav, "wb") as fh:
            fh.write(b"RIFFtestWAVE")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(local_tts.subprocess, "run", fake_run)
    assert local_tts.LocalTTSProvider._aiff_to_wav_bytes(str(aiff)) == b"RIFFtestWAVE"


def test_aiff_to_wav_failure_raises(tmp_path, monkeypatch):
    import subprocess

    import app.services.local_tts as local_tts

    aiff = tmp_path / "in.aiff"
    aiff.write_bytes(b"\x00" * 8)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stderr="afconvert: couldn't parse")

    monkeypatch.setattr(local_tts.subprocess, "run", fake_run)
    with pytest.raises(TTSError):
        local_tts.LocalTTSProvider._aiff_to_wav_bytes(str(aiff))