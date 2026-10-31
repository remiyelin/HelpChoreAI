"""Durable Step 5 tests: Checker gate + templated numbers + auditor. Run: uv run pytest tests/ -q"""
import copy, json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import checker

ROOT = Path(__file__).parent.parent

def _env():
    # Committed envelope: these tests must pass with no private key present.
    return json.loads((ROOT / "data" / "checker" / "example_report_P1_0w_2w.json").read_text())

def _patch_keys(monkeypatch, keys_dir: Path, pin_hex: str):
    keys_dir.mkdir(parents=True, exist_ok=True)
    pin = keys_dir / "public_key.hex"
    pin.write_text(pin_hex + "\n")
    monkeypatch.setattr(checker, "KEYS", keys_dir)
    monkeypatch.setattr(checker, "PINNED_PUBLIC_KEY", pin)
    return pin

def _write_private(keys_dir: Path, key):
    from cryptography.hazmat.primitives import serialization
    (keys_dir / "private_key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

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
    forged["payload"]["report_sha256"] = checker.sha_report(checker.render_report(forged))
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
        (root / "data" / "checker" / "example_report_P1_0w_2w.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    report_text = (root / "data" / "checker" / "example_report_P1_0w_2w.md").read_text(encoding="utf-8")
    ok, errs = checker.verify_envelope(env, report_text=report_text)
    assert ok, errs

def test_unparseable_baseten_reply_returns_block(monkeypatch):
    import meta_api
    monkeypatch.setattr(meta_api, "chat_cached",
                        lambda *a, **k: {"status": "OK", "text": "not json at all", "_cache": "miss"})
    out = meta_api.baseten_audit("any report", {})
    assert out["status"] == "BLOCK" and out["verdict"] == "BLOCK"

def test_no_private_key_sign_raises_and_pin_unchanged(tmp_path, monkeypatch):
    pin = _patch_keys(monkeypatch, tmp_path / "keys", checker.pinned_public_key_hex())
    before = pin.read_bytes()
    with pytest.raises(checker.NoSigningKey):
        checker.load_signing_key()
    with pytest.raises(checker.NoSigningKey):
        checker.sign_payload(_env()["payload"])
    assert pin.read_bytes() == before
    assert not (tmp_path / "keys" / "private_key.pem").exists()

def test_fresh_key_envelope_rejected(tmp_path, monkeypatch):
    _patch_keys(monkeypatch, tmp_path / "keys", checker.pinned_public_key_hex())
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    forged = _env()
    attacker = Ed25519PrivateKey.generate()
    forged["signature_hex"] = attacker.sign(checker.canonical(forged["payload"])).hex()
    forged["public_key_hex"] = attacker.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    ok, errs = checker.verify_envelope(forged, check_tables=False)
    assert not ok and errs

def test_every_committed_envelope_verifies_with_no_private_key(tmp_path, monkeypatch):
    pin = _patch_keys(monkeypatch, tmp_path / "keys", checker.pinned_public_key_hex())
    before = pin.read_bytes()
    files = sorted((ROOT / "logs" / "agent_runs").glob("*/envelope.json")) + \
        sorted((ROOT / "data" / "checker").glob("*.json"))
    assert files
    for f in files:
        report = f.parent / "report.md"
        if not report.exists(): report = f.with_suffix(".md")
        report_text = report.read_text(encoding="utf-8") if report.exists() else None
        ok, errs = checker.verify_envelope(json.loads(f.read_text()), report_text=report_text)
        assert ok, (f.name, errs)
    assert pin.read_bytes() == before
    assert not (tmp_path / "keys" / "private_key.pem").exists()

def test_wrong_private_key_raises_key_mismatch(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    pin = _patch_keys(monkeypatch, keys_dir, checker.pinned_public_key_hex())
    before = pin.read_bytes()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    _write_private(keys_dir, Ed25519PrivateKey.generate())
    with pytest.raises(checker.KeyMismatch):
        checker.load_signing_key()
    with pytest.raises(checker.KeyMismatch):
        checker.sign_payload(_env()["payload"])
    assert pin.read_bytes() == before

def test_rotate_cli_only_writes_with_confirm(tmp_path, monkeypatch):
    import importlib.util
    keys_dir = tmp_path / "keys"
    pin = _patch_keys(monkeypatch, keys_dir, "00" * 32)
    spec = importlib.util.spec_from_file_location("rotate_key", ROOT / "tools" / "rotate_key.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    with pytest.raises(SystemExit):
        mod.main([])
    assert not (keys_dir / "private_key.pem").exists()
    assert pin.read_text().strip() == "00" * 32
    assert mod.main(["--confirm-rotate"]) == 0
    key = checker.load_signing_key()  # new private key matches the rewritten pin
    assert key is not None and pin.read_text().strip() != "00" * 32

def test_injected_narrative_fails_verification():
    env = _env()
    report = (ROOT / "data" / "checker" / "example_report_P1_0w_2w.md").read_text(encoding="utf-8")
    ok, errs = checker.verify_envelope(env, report_text=report)
    assert ok, errs
    injected = report.rstrip() + "\nNarrative: Patient improved on dasatinib; continue the dose."
    ok, errs = checker.verify_envelope(env, report_text=injected)
    assert not ok and any("report hash" in e for e in errs), errs

def test_banned_phrases_refused():
    env = _env()
    for phrase in ["treatment response", "response to treatment", "responded to",
                   "improved on", "worsened on", "drug effect", "continue the dose"]:
        text = checker.render_report(env) + f"\nNarrative: The {phrase} was noted."
        ok, errs = checker.audit_report(text, env)
        assert not ok and any(phrase in e for e in errs), (phrase, errs)
        with pytest.raises(ValueError):
            checker.render_report(env, f"The {phrase} was noted.")

def test_spelled_out_number_narrative_rejected():
    env = _env()
    for bad in ["The fraction rose by twelve percent.", "A change of thirty units was seen."]:
        try:
            checker.render_report(env, bad)
            assert False, f"spelled-out narrative must be rejected: {bad}"
        except ValueError:
            pass
