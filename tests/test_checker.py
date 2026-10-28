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

def test_open_weight_auditor_blocked_without_credentials(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    result, errs = checker.audit_with_open_weights("x", _env())
    assert result is None and "BLOCKED" in errs[0]
