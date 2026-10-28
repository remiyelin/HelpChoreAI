#!/usr/bin/env python3
"""Step 5: chained raw-to-report Checker (SHA-256 + Ed25519), templated report, auditor gate.
Chain: fetch-manifest hash -> canonical table hashes -> payload hash -> Ed25519 signature.
Report numbers are rendered ONLY from the signed payload; narrative slots may not contain digits.
Run demo/tests: uv run python src/checker.py --demo   |   uv run pytest tests/ -q
"""
import hashlib, json, os, re, sys
from pathlib import Path
try:
    from env import load_env
    load_env()
except Exception:
    pass
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "data" / "tables"
MANIFEST = ROOT / "data" / "fetch_manifest"
KEYS = ROOT / "data" / "checker"
DATASET_DOI = "10.6084/m9.figshare.c.5793482"
DISCLAIMER = ("Research use only. RBC morphology is a peripheral target-engagement marker, "
              "not a measure of central nervous system progression. Every result must be reviewed "
              "by a qualified researcher using the per-cell visual overlay.")
BANNED = ["diagnos", "progression of disease", "disease progression", "recommend treatment",
          "start dasatinib", "stop dasatinib", "start lithium", "stop lithium", "patient should",
          "clinical advice", "prognos"]

def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: Path) -> str: return sha_bytes(p.read_bytes())

def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def chain_hashes() -> dict:
    manifest_files = sorted(MANIFEST.glob("fetch_log*.json")) + sorted(MANIFEST.glob("holdout_*_manifest.json"))
    raw = sha_bytes(b"".join(p.read_bytes() for p in manifest_files))
    tables = {name: sha_file(TABLES / name) for name in
              ["per_run.csv", "per_visit_adjusted_v2.csv", "visit_pairs_decisions_v2.csv"]}
    return {"raw_manifest_sha256": raw, "tables_sha256": tables}

def build_payload(patient: str, from_visit: str, to_visit: str) -> dict:
    import pandas as pd
    dec = pd.read_csv(TABLES / "visit_pairs_decisions_v2.csv")
    row = dec[(dec.patient == patient) & (dec["from"] == from_visit) & (dec.to == to_visit)]
    if len(row) != 1: raise ValueError(f"pair not found {patient} {from_visit}->{to_visit}")
    r = row.iloc[0]
    payload = {"dataset_doi": DATASET_DOI, "patient": patient, "from_visit": from_visit, "to_visit": to_visit,
               "treatment": str(r.treatment), "delta_raw": float(r.delta_raw), "delta_adj": float(r.delta_adj),
               "rcv95": float(r.RCV95), "decision": str(r.decision), "ref_flow_ul_s": 0.016,
               "measurand": "health==1 fraction among shape!=0, flow-standardized",
               "disclaimer": DISCLAIMER, "chain": chain_hashes()}
    payload["payload_sha256"] = sha_bytes(canonical({k: v for k, v in payload.items()}))
    return payload

def get_key() -> Ed25519PrivateKey:
    KEYS.mkdir(parents=True, exist_ok=True)
    kp = KEYS / "private_key.pem"
    if kp.exists():
        return serialization.load_pem_private_key(kp.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    kp.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    return key

def sign_payload(payload: dict) -> dict:
    key = get_key()
    sig = key.sign(canonical(payload))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return {"payload": payload, "signature_hex": sig.hex(), "public_key_hex": pub}

def verify_envelope(env: dict, check_tables: bool = True) -> tuple[bool, list[str]]:
    errs = []
    payload = env.get("payload", {})
    body = {k: v for k, v in payload.items() if k != "payload_sha256"}
    if payload.get("payload_sha256") != sha_bytes(canonical(body)): errs.append("payload hash mismatch")
    if check_tables:
        now = chain_hashes()
        if payload.get("chain", {}).get("raw_manifest_sha256") != now["raw_manifest_sha256"]:
            errs.append("raw manifest chain mismatch (fetch log changed)")
        if payload.get("chain", {}).get("tables_sha256") != now["tables_sha256"]:
            errs.append("table chain mismatch (canonical tables changed since signing)")
    # decision consistency recomputed from payload numbers alone
    d, rcv = abs(float(payload.get("delta_adj", 0))), float(payload.get("rcv95", 0))
    expect = "exceeds_RCV" if d > rcv else "within_RCV"
    if payload.get("decision") not in ("indeterminate_QC", expect):
        errs.append(f"decision inconsistent: payload decision={payload.get('decision')} recomputed={expect}")
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(env["public_key_hex"]))
        pub.verify(bytes.fromhex(env["signature_hex"]), canonical(payload))
    except Exception as e:
        errs.append(f"signature invalid: {type(e).__name__}")
    return (not errs), errs

def render_report(env: dict, narrative: str = "") -> str:
    p = env["payload"]
    if re.search(r"\d", narrative or ""):
        raise ValueError("narrative slots may not contain digits (numbers are templated from payload)")
    lines = ["# HelpChoreAI Audit Report (research use)",
             f"Dataset: Figshare Collection doi:{p['dataset_doi']} (CC BY 4.0, Reichel et al. 2022)",
             f"Patient code: {p['patient']} | Visits: {p['from_visit']} -> {p['to_visit']} | Treatment context: {p['treatment']}",
             f"Measurand: {p['measurand']} at reference flow {p['ref_flow_ul_s']} uL/s",
             f"Change (raw): {p['delta_raw']:+.4f} | Change (flow-adjusted): {p['delta_adj']:+.4f} | RCV95 band: {p['rcv95']:.4f}",
             f"Decision: {p['decision']}",
             f"Checker payload SHA-256: {p['payload_sha256']}",
             f"Disclaimer: {p['disclaimer']}"]
    if narrative: lines.append(f"Narrative: {narrative}")
    return "\n".join(lines)

def audit_report(report: str, env: dict) -> tuple[bool, list[str]]:
    """Local rule auditor — stand-in implementing the open-weight auditor contract (see audit_with_open_weights)."""
    errs, low = [], report.lower()
    for phrase in BANNED:
        if phrase in low: errs.append(f"banned clinical-advice phrase: {phrase!r}")
    if DISCLAIMER not in report: errs.append("disclaimer missing")
    p = env["payload"]
    for token in [f"{p['delta_raw']:+.4f}", f"{p['delta_adj']:+.4f}", f"{p['rcv95']:.4f}", p["payload_sha256"]]:
        if token not in report: errs.append(f"payload number/token missing or altered: {token}")
    if re.search(r"\b[A-Z]{2}\b\s*\(?\d+w\)", report) and p["patient"] not in report:
        errs.append("possible non-P-code patient identifier")
    return (not errs), errs

def audit_with_open_weights(report: str, env: dict):
    """$10K prize path: meta-models/muse-spark-open-1026 on Baseten as secondary privacy/compliance auditor.
    Blocked without credentials by design — never silently falls back to 'approved'."""
    if not os.environ.get("BASETEN_API_KEY"):
        return None, ["BLOCKED: BASETEN_API_KEY not set; open-weight auditor (meta-models/muse-spark-open-1026) not run"]
    raise NotImplementedError("POST report+payload to Baseten muse-spark-open-1026 with the auditor prompt; block on any flagged item.")

if __name__ == "__main__":
    env = sign_payload(build_payload("P1", "0w", "2w"))
    out = ROOT / "data" / "checker" / "example_report_P1_0w_2w.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(env, indent=1))
    report = render_report(env, "Flow standardized change assessed against the combined noise band.")
    (ROOT / "data" / "checker" / "example_report_P1_0w_2w.md").write_text(report)
    ok, errs = verify_envelope(env)
    ok2, errs2 = audit_report(report, env)
    ow, errs3 = audit_with_open_weights(report, env)
    print("verify:", ok, errs); print("audit:", ok2, errs2); print("open-weight auditor:", ow, errs3)
    print(report)
