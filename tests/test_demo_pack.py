"""The public pack: signed reports verify from the pack alone, and nothing private ships in web/."""
import json
import re
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import checker
import server
from test_server_security import port, post  # noqa: F401  (shared local server fixture)

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DEMO = WEB / "demo"
pack = pytest.mark.skipif(not DEMO.exists(), reason="demo pack not built")


@pack
def test_reports_verify_from_the_pack_alone():
    pub = (DEMO / "public_key.hex").read_text().strip()
    assert pub == checker.pinned_public_key_hex()
    index = json.loads((DEMO / "reports" / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 21
    for rid in index:
        r = json.loads((DEMO / "reports" / f"{rid}.json").read_text(encoding="utf-8"))
        payload = json.loads(r["payload_canonical"])
        assert checker.canonical(payload).decode("ascii") == r["payload_canonical"], rid
        env = {"payload": payload, "signature_hex": r["signature_hex"], "public_key_hex": r["public_key_hex"]}
        assert checker.verify_envelope(env, report_text=r["report"], check_tables=False)[0], rid


@pack
def test_nothing_private_in_web():
    files = [p for p in WEB.rglob("*") if p.is_file()]
    assert sum(p.stat().st_size for p in files) < 30e6
    assert not [p for p in files if p.suffix in (".p", ".pem", ".env", ".raw") or p.name.startswith(".env")]
    tokens = []
    m = ROOT / "private" / "initials_map.json"
    if m.exists():
        d = json.loads(m.read_text(encoding="utf-8"))
        tokens = list(d) if all(str(v).startswith("P") for v in d.values()) else list(d.values())
    rx = [re.compile(rf"(?<![A-Za-z]){re.escape(t)}(?![a-z])") for t in tokens]
    for p in files:
        if p.suffix not in (".json", ".js", ".html", ".css", ".hex"): continue
        s = p.read_text(encoding="utf-8")
        assert not any(r.search(s) for r in rx), p.name
        if p.parent.name == "cells" or p.name in ("pairs.json", "visits.json"):
            assert not re.search(r"\b20[12]\d[01]\d[0-3]\d\b", s), f"recording date in {p.name}"


def test_modal_image_holds_web_only():
    s = (ROOT / "modal_app.py").read_text(encoding="utf-8")
    assert "--bind 0.0.0.0" in s and "modal.concurrent" in s
    assert not re.search(r"data[/\"' ]|Secret|\.env", s.split("One-time setup")[1].split('"""', 1)[1])


@pytest.mark.parametrize("path,ok", [("/demo/pairs.json", True), ("/demo/../../.env", False), ("/demo/", False),
                                     ("/fonts/../app.js", False), ("/data/tables/per_run.csv", False)])
def test_pack_paths(path, ok):
    if ok and not DEMO.exists(): pytest.skip("demo pack not built")
    assert (server.pack_file(path) is not None) is ok


def test_signoff_refuses_hashes_of_another_pair(port):  # noqa: F811
    env = json.loads((ROOT / "logs" / "agent_runs" / "P1_0w_2w" / "envelope.json").read_text(encoding="utf-8"))
    body = {"patient": "P1", "from": "2w", "to": "4w", "decision": "Approved",
            "payload_sha256": env["payload"]["payload_sha256"], "report_sha256": env["payload"]["report_sha256"]}
    code, text = post(port, "/api/signoff", json.dumps(body).encode())
    assert code == 409 and "not the signed report" in text
    body.update({"from": "../..", "to": "x"})
    assert post(port, "/api/signoff", json.dumps(body).encode())[0] == 409
