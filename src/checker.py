#!/usr/bin/env python3
"""Step 5: chained raw-to-report Checker (SHA-256 + Ed25519), templated report, auditor gate.
Chain: fetch-manifest hash -> canonical table hashes -> payload hash -> Ed25519 signature.
Report numbers are rendered ONLY from the signed payload; narrative slots may not contain digits.
Run demo/tests: uv run python src/checker.py --demo   |   uv run pytest tests/ -q
"""
import hashlib, json, re, subprocess, sys
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
PINNED_PUBLIC_KEY = KEYS / "public_key.hex"
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
                "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million"]
NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS + ["percent", "percentage"]) + r")\b",
                            re.IGNORECASE)

def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: Path) -> str: return sha_bytes(p.read_bytes())

def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def _tracked_files() -> set[str]:
    """Repo-relative POSIX paths of tracked files (git ls-files); empty set if git is unavailable."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        if out.returncode != 0: return set()
        return {line.strip() for line in out.stdout.splitlines() if line.strip()}
    except Exception:
        return set()

def chain_hashes() -> dict:
    tracked = _tracked_files()
    manifest_rels = sorted(r for r in tracked if r.startswith("data/fetch_manifest/") and r.endswith(".json")
                           and "holdout" not in Path(r).name.lower())
    table_names = ["per_run.csv", "per_visit_adjusted_v3.csv", "visit_pairs_decisions_v3.csv"]
    table_rels = [f"data/tables/{n}" for n in table_names if f"data/tables/{n}" in tracked]
    hashed = sorted(manifest_rels + table_rels)
    # Normalize CRLF->LF so hashes survive autocrlf checkouts on a fresh clone.
    def norm(rel: str) -> bytes: return (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
    raw = sha_bytes(b"".join(norm(r) for r in manifest_rels))
    tables = {Path(r).name: sha_bytes(norm(r)) for r in table_rels}
    return {"raw_manifest_sha256": raw, "tables_sha256": tables, "hashed_files": hashed}

def _payload_hash(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k not in ("payload_sha256", "report_sha256")}
    return sha_bytes(canonical(body))

def build_payload(patient: str, from_visit: str, to_visit: str) -> dict:
    import pandas as pd
    dec = pd.read_csv(TABLES / "visit_pairs_decisions_v3.csv")
    row = dec[(dec.patient == patient) & (dec["from"] == from_visit) & (dec.to == to_visit)]
    if len(row) != 1: raise ValueError(f"pair not found {patient} {from_visit}->{to_visit}")
    r = row.iloc[0]
    payload = {"dataset_doi": DATASET_DOI, "patient": patient, "from_visit": from_visit, "to_visit": to_visit,
               "treatment": str(r.treatment), "delta_raw": float(r.delta_raw), "delta_adj": float(r.delta_adj),
               "rcv95": float(r.RCV95), "decision": str(r.decision), "ref_flow_ul_s": 0.016,
               "measurand": "health==1 fraction among shape!=0, flow-standardized",
               "disclaimer": DISCLAIMER, "chain": chain_hashes()}
    payload["payload_sha256"] = _payload_hash(payload)
    payload["report_sha256"] = sha_bytes(render_report({"payload": payload}).encode())
    return payload

class NoSigningKey(Exception):
    """No private signing key is present; signing is disabled."""


class KeyMismatch(Exception):
    """The private key present does not match the pinned public key."""


def pinned_public_key_hex() -> str:
    return PINNED_PUBLIC_KEY.read_text().strip().lower()

def load_signing_key() -> Ed25519PrivateKey:
    """Read the private key only. Never generates a key and never writes any file."""
    kp = KEYS / "private_key.pem"
    if not kp.exists():
        raise NoSigningKey(f"no signing key at {kp}; signing is disabled")
    key = serialization.load_pem_private_key(kp.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyMismatch("signing key is not an Ed25519 key")
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    try:
        pinned = pinned_public_key_hex()
    except Exception as e:
        raise KeyMismatch("pinned public key missing") from e
    if pub != pinned:
        raise KeyMismatch("private key does not match pinned public key")
    return key

def sign_payload(payload: dict) -> dict:
    payload = dict(payload)
    if payload.get("payload_sha256") != _payload_hash(payload):
        payload["payload_sha256"] = _payload_hash(payload)
    if not payload.get("report_sha256"):
        payload["report_sha256"] = sha_bytes(render_report({"payload": payload}).encode())
    key = load_signing_key()
    sig = key.sign(canonical(payload))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return {"payload": payload, "signature_hex": sig.hex(), "public_key_hex": pub}

def verify_envelope(env: dict, check_tables: bool = True) -> tuple[bool, list[str]]:
    errs = []
    payload = env.get("payload", {})
    if payload.get("payload_sha256") != _payload_hash(payload): errs.append("payload hash mismatch")
    if payload.get("report_sha256"):
        try:
            if payload["report_sha256"] != sha_bytes(render_report(env).encode()):
                errs.append("report hash mismatch (rendered report changed since signing)")
        except Exception as e:
            errs.append(f"report hash mismatch: {type(e).__name__}")
    if check_tables:
        now = chain_hashes()
        if payload.get("chain", {}).get("raw_manifest_sha256") != now["raw_manifest_sha256"]:
            errs.append("raw manifest chain mismatch (fetch log changed)")
        if payload.get("chain", {}).get("tables_sha256") != now["tables_sha256"]:
            errs.append("table chain mismatch (canonical tables changed since signing)")
        if payload.get("chain", {}).get("hashed_files") != now["hashed_files"]:
            errs.append("hashed file list mismatch (tracked-file chain changed)")
    # decision consistency recomputed from payload numbers alone
    d, rcv = abs(float(payload.get("delta_adj", 0))), float(payload.get("rcv95", 0))
    expect = "exceeds_RCV" if d > rcv else "within_RCV"
    if payload.get("decision") not in ("indeterminate_QC", expect):
        errs.append(f"decision inconsistent: payload decision={payload.get('decision')} recomputed={expect}")
    try:
        pinned = pinned_public_key_hex()
    except Exception:
        pinned = ""
        errs.append("pinned public key missing")
    if pinned and str(env.get("public_key_hex", "")).lower() != pinned:
        errs.append("envelope public key does not match pinned public key")
    if pinned:
        try:
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pinned))
            pub.verify(bytes.fromhex(env["signature_hex"]), canonical(payload))
        except Exception as e:
            errs.append(f"signature invalid: {type(e).__name__}")
    return (not errs), errs

def render_report(env: dict, narrative: str = "") -> str:
    p = env["payload"]
    if re.search(r"\d", narrative or ""):
        raise ValueError("narrative slots may not contain digits (numbers are templated from payload)")
    m = NUMBER_WORD_RE.search(narrative or "")
    if m:
        raise ValueError(f"narrative slots may not contain spelled-out numbers or percent words: {m.group(0)!r}")
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
    """Local rule auditor implementing the open-weight auditor contract (see meta_api.baseten_audit)."""
    errs, low = [], report.lower()
    for phrase in BANNED:
        if phrase in low: errs.append(f"banned clinical-advice phrase: {phrase!r}")
    if DISCLAIMER not in report: errs.append("disclaimer missing")
    p = env["payload"]
    for token in [f"{p['delta_raw']:+.4f}", f"{p['delta_adj']:+.4f}", f"{p['rcv95']:.4f}", p["payload_sha256"]]:
        if token not in report: errs.append(f"payload number/token missing or altered: {token}")
    for m in re.finditer(r"\b[A-Z]{2}\b\s*\(?\d+w\)", report):
        errs.append(f"possible non-P-code patient identifier: {m.group(0)!r}")
    m = NUMBER_WORD_RE.search(report)
    if m: errs.append(f"spelled-out number or percent word in report: {m.group(0)!r}")
    return (not errs), errs

if __name__ == "__main__":
    env = sign_payload(build_payload("P1", "0w", "2w"))
    out = ROOT / "data" / "checker" / "example_report_P1_0w_2w.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(env, indent=1))
    report = render_report(env)
    (ROOT / "data" / "checker" / "example_report_P1_0w_2w.md").write_bytes(report.encode())
    ok, errs = verify_envelope(env)
    ok2, errs2 = audit_report(report, env)
    print("verify:", ok, errs); print("audit:", ok2, errs2)
    print(report)
