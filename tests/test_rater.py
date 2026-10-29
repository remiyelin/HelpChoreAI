"""Structured-rater durable tests (no network, no keys): schema contract, repeat cache keys,
cannot_tell pass-through, clamping, BLOCKED honesty on malformed replies."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import meta_api

GOOD = {"spiculated": "cannot_tell", "confidence": 0.4, "spicule_points": [{"frame": 1, "x": 1200, "y": -5}],
        "image_quality": "poor", "reason": "too dark to judge outline"}


def _fake_ok(monkeypatch, tmp_path, payload):
    monkeypatch.setenv("META_MODEL_API_KEY", "test-key")
    monkeypatch.setattr(meta_api, "CACHE", tmp_path)
    monkeypatch.setattr(meta_api, "_post", lambda url, key, body, timeout=60: {
        "id": "x", "choices": [{"message": {"content": json.dumps(payload)}}]})


def test_rater_parses_clamps_and_cannot_tell_stays_distinct(monkeypatch, tmp_path):
    _fake_ok(monkeypatch, tmp_path, GOOD)
    r = meta_api.spark_rater([b"png-a"], repeat=0)
    assert r["status"] == "OK" and r["rater"]["spiculated"] == "cannot_tell"  # never mapped to a label
    assert r["rater"]["spicule_points"] == [{"frame": 1, "x": 1000, "y": 0}]  # overshoots clamped
    r2 = meta_api.spark_rater([b"png-a"], repeat=0)
    assert r2["_cache"] == "hit"


def test_repeat_index_is_a_distinct_cache_entry(monkeypatch, tmp_path):
    _fake_ok(monkeypatch, tmp_path, GOOD)
    a = meta_api.spark_rater([b"png-a"], repeat=0)
    b = meta_api.spark_rater([b"png-a"], repeat=1)
    assert a["_cache"] == "miss" and b["_cache"] == "miss"  # repeat deliberately re-asks


def test_schema_violating_reply_is_blocked_not_fabricated(monkeypatch, tmp_path):
    _fake_ok(monkeypatch, tmp_path, {"spiculated": "maybe", "confidence": 2})
    r = meta_api.spark_rater([b"png-b"], repeat=0)
    assert r["status"] == "BLOCKED" and "detail" in r


def test_rater_blocked_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setattr(meta_api, "CACHE", tmp_path)
    assert meta_api.spark_rater([b"png-" + b"z" * 32], repeat=0)["status"] == "BLOCKED"
