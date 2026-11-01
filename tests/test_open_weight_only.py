"""P-25: OPEN_WEIGHT_ONLY=1 blocks every Meta call before the network."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import meta_api


@pytest.fixture()
def open_only(monkeypatch):
    monkeypatch.setenv("OPEN_WEIGHT_ONLY", "1")

    def boom(*a, **k):
        raise AssertionError("network attempted in OPEN_WEIGHT_ONLY mode")

    monkeypatch.setattr(meta_api, "_post", boom)
    monkeypatch.setattr(meta_api.urllib.request, "urlopen", boom)
    return monkeypatch


def test_meta_chat_rater_voice_blocked_before_network(open_only):
    assert meta_api.chat_cached(meta_api.META_BASE, "k", "muse-spark-1.3",
                                [{"role": "user", "content": "hello-open-only-test"}])["status"] == "BLOCKED_OPEN_ONLY"
    assert meta_api.spark_rater([b"\x89PNG-fake"])["status"] == "BLOCKED_OPEN_ONLY"
    assert meta_api.spark_narrative({"decision": "within_RCV", "treatment": "x"})["status"] in (
        "BLOCKED", "BLOCKED_OPEN_ONLY", "OK")  # narrative is re-routed to Baseten, never Meta
    out = meta_api.transcribe_audio(b"fake-wav")
    assert out["status"] == "BLOCKED_OPEN_ONLY"
    assert meta_api.sam_prompt_mask(b"\x89PNG-fake", "box:1,2,3,4")["status"] == "BLOCKED_OPEN_ONLY"
    assert meta_api.sam_track_video("file-x", b"mp4", "prompt")["status"] == "BLOCKED_OPEN_ONLY"


def test_baseten_path_not_blocked(open_only, monkeypatch):
    monkeypatch.setenv("BASETEN_API_KEY", "test-key")
    monkeypatch.setattr(meta_api, "_post", lambda url, key, body, timeout=60: {
        "id": "x", "model": "meta-models/muse-spark-open",
        "choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    out = meta_api.baseten_chat([{"role": "user", "content": "open-only baseten test ping"}])
    assert out["status"] == "OK" and out["model"] == "meta-models/muse-spark-open"


def test_open_weight_only_default_off(monkeypatch):
    monkeypatch.delenv("OPEN_WEIGHT_ONLY", raising=False)
    assert meta_api.open_weight_only() is False
