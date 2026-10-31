"""Durable Step 5 tests: Checker gate + templated numbers + auditor. Run: uv run pytest tests/ -q"""
import copy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import checker

def _env():
    return checker.sign_payload(checker.build_payload("P1", "0w", "2w"))

def test_untampered_verifies_and_roundtrips(tmp_path):
    env = _env()
    ok, errs = checker.verify_envelope(env)
    assert ok, errs
    p = tmp_path / "env.json"
    import json
    p.write_text(json.dumps(env))
    ok2, errs2 = checker.verify_envelope(json.loads(p.read_text()))
    assert ok2, errs2

def test_tampered_number_fails():
    env = _env()
    env["payload"]["delta_adj"] = env["payload"]["delta_adj"] + 0.05
    ok, errs = checker.verify_envelope(env, check_tables=False)
    assert not ok and errs

def test_tampered_decision_fails():
    env = _env()
    env["payload"]["decision"] = "within_RCV" if env["payload"]["decision"] == "exceeds_RCV" else "exceeds_RCV"
    ok, errs = checker.verify_envelope(env, check_tables=False)
    assert not ok

def test_narrative_with_digits_rejected():
    env = _env()
    try:
        checker.render_report(env, "The fraction rose by 12 percent.")
        assert False, "digits in narrative must be rejected"
    except ValueError:
        pass

def test_auditor_blocks_clinical_advice_and_missing_disclaimer():
    env = _env()
    bad = "We recommend treatment: start dasatinib. Disease progression confirmed. " + checker.render_report(env)
    bad = bad.replace(checker.DISCLAIMER, "")
    ok, errs = checker.audit_report(bad, env)
    assert not ok and len(errs) >= 2

def test_forged_key_envelope_rejected():
    import copy
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    env = _env()
    forged = copy.deepcopy(env)
    forged["payload"]["delta_adj"] = 0.25
    forged["payload"]["decision"] = "exceeds_RCV"
    forged["payload"]["payload_sha256"] = checker._payload_hash(forged["payload"])
    forged["payload"]["report_sha256"] = checker.sha_bytes(checker.render_report(forged).encode())
    attacker = Ed25519PrivateKey.generate()
    forged["signature_hex"] = attacker.sign(checker.canonical(forged["payload"])).hex()
    forged["public_key_hex"] = attacker.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    ok, errs = checker.verify_envelope(forged, check_tables=False)
    assert not ok and any("pinned" in e or "signature" in e for e in errs), errs

def test_committed_example_verifies_from_tracked_files_only():
    import hashlib, json
    root = Path(__file__).parent.parent
    env = json.loads((root / "data" / "checker" / "example_report_P1_0w_2w.json").read_text())
    assert env["public_key_hex"] == (root / "data" / "checker" / "public_key.hex").read_text().strip()
    hashed = env["payload"]["chain"]["hashed_files"]
    assert hashed and "data/fetch_manifest/fetch_log_step1.json" not in hashed
    assert "data/tables/visit_pairs_decisions_v3.csv" in hashed
    assert env["payload"]["report_sha256"] == hashlib.sha256(
        (root / "data" / "checker" / "example_report_P1_0w_2w.md").read_bytes()).hexdigest()
    ok, errs = checker.verify_envelope(env)
    assert ok, errs

def test_unparseable_baseten_reply_returns_block(monkeypatch):
    import meta_api
    monkeypatch.setattr(meta_api, "chat_cached",
                        lambda *a, **k: {"status": "OK", "text": "not json at all", "_cache": "miss"})
    out = meta_api.baseten_audit("any report", {})
    assert out["status"] == "BLOCK" and out["verdict"] == "BLOCK"

def test_spelled_out_number_narrative_rejected():
    env = _env()
    for bad in ["The fraction rose by twelve percent.", "A change of thirty units was seen."]:
        try:
            checker.render_report(env, bad)
            assert False, f"spelled-out narrative must be rejected: {bad}"
        except ValueError:
            pass
