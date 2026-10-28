"""Live-integration durable tests (no network, no keys): env, cache determinism, IoU, blocked honesty."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import meta_api

def test_blocked_without_keys(monkeypatch):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    assert meta_api.sam_segment(b"png")["status"] == "BLOCKED"
    assert meta_api.baseten_audit("report", {})["status"] == "BLOCKED"

def test_cache_key_deterministic():
    a = meta_api._key("m", [{"role": "user", "content": "x"}])
    b = meta_api._key("m", [{"role": "user", "content": "x"}])
    assert a == b and len(a) == 64

def test_polygon_iou_identical_and_disjoint():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert meta_api.polygon_iou(sq, sq, 20, 20) == 1.0
    far = [[15, 15], [19, 15], [19, 19], [15, 19]]
    assert meta_api.polygon_iou(sq, far, 20, 20) == 0.0

def test_env_example_names():
    txt = (Path(__file__).parent.parent / ".env.example").read_text()
    assert "META_MODEL_API_KEY=" in txt and "BASETEN_API_KEY=" in txt
    gi = (Path(__file__).parent.parent / ".gitignore").read_text()
    assert ".env" in gi
