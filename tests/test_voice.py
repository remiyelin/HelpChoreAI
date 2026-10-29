"""Voice-transcribe durable tests (no network, no keys): WAV fixture, blocked honesty, multipart contract, cache."""
import sys, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import meta_api

FIXTURE = Path(__file__).parent / "fixtures" / "sample_review.wav"


def test_sample_wav_fixture_is_valid_24k_mono_16bit():
    assert FIXTURE.exists(), "generate with: uv run python src/meta_api.py make-sample-wav"
    with wave.open(str(FIXTURE), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() in (16000, 24000)
        assert w.getnframes() > w.getframerate() // 2  # at least half a second


def test_make_sample_wav_roundtrip(tmp_path):
    out = meta_api.make_sample_wav(tmp_path / "s.wav")
    with wave.open(str(out), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == 24000


def test_transcribe_blocked_without_key(monkeypatch):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert meta_api.transcribe_audio(b"RIFF-fake-" + b"x" * 64)["status"] == "BLOCKED"


def test_transcribe_multipart_contract_and_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("META_MODEL_API_KEY", "test-key")
    monkeypatch.setattr(meta_api, "CACHE", tmp_path)
    seen = {}
    def fake_post(url, key, body, ctype, timeout=120):
        seen.update(url=url, key=key, body=body, ctype=ctype)
        return {"transcript": "cell looks healthy, no spicules", "audioDurationMs": 1200, "sessionId": "s1"}
    monkeypatch.setattr(meta_api, "_post_multipart", fake_post)
    wav = meta_api.make_sample_wav(tmp_path / "a.wav").read_bytes()
    r1 = meta_api.transcribe_audio(wav)
    assert r1["status"] == "OK" and r1["text"] == "cell looks healthy, no spicules" and r1["_cache"] == "miss"
    assert seen["url"].endswith("/asr/transcribe") and "muse-voice-transcribe" in seen["body"].decode("latin1")
    r2 = meta_api.transcribe_audio(wav)
    assert r2["_cache"] == "hit" and r2["text"] == r1["text"]
