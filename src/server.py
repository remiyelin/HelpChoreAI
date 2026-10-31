#!/usr/bin/env python3
"""HelpChoreAI Step 6 server (stdlib only). Run: uv run python src/server.py [--port 8765]
Views data APIs + per-cell contours (RestrictedUnpickler) + live kappa/AC1 + Checker + tamper sim.
Live AI activation: META_MODEL_API_KEY -> SAM 3.1 status; BASETEN_API_KEY -> open-weight auditor attempt.
Without keys everything runs on extracted dev data and live calls report BLOCKED (never fake-approved).
"""
import argparse, json, os, sys, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from env import load_env
load_env()
import checker
import meta_api
from step2_analysis import RestrictedUnpickler

ROOT = Path(__file__).resolve().parent.parent
WEB, TABLES, DEV = ROOT / "web", ROOT / "data" / "tables", ROOT / "data" / "dev"
REVIEWS = ROOT / "data" / "reviews.json"
_pickle_cache = {}

def kappa_ac1(a, b):
    a, b = np.asarray(a, dtype=int), np.asarray(b, dtype=int)
    n = len(a)
    if n == 0: return {"n": 0, "kappa": None, "ac1": None, "agreement": None}
    po = float((a == b).mean())
    pa = np.array([(a == 0).mean(), (a == 1).mean()]); pb = np.array([(b == 0).mean(), (b == 1).mean()])
    pe_k = float((pa * pb).sum())
    kappa = (po - pe_k) / (1 - pe_k) if pe_k < 1 else 1.0
    p_avg = (pa + pb) / 2; pe_a = float(2 * p_avg[0] * p_avg[1])
    ac1 = (po - pe_a) / (1 - pe_a) if pe_a < 1 else 1.0
    return {"n": n, "kappa": round(float(kappa), 3), "ac1": round(float(ac1), 3), "agreement": round(po, 3)}

def load_pickle(patient, date):
    key = (patient, str(date))
    if key in _pickle_cache: return _pickle_cache[key]
    hits = list((DEV / patient).glob(f"{patient}__{date}_*__Offline__M10_results.p"))
    if not hits: return None
    with open(hits[0], "rb") as fh: obj = RestrictedUnpickler(fh, encoding="latin1").load()
    _pickle_cache[key] = obj
    return obj

def cell_contour(patient, date, cell):
    obj = load_pickle(patient, date)
    if obj is None or cell >= len(obj["Contours"]): return None
    contours = obj["Contours"][cell]
    if not contours: return None
    pts = np.asarray(contours[len(contours) // 2], dtype=float)
    if pts.ndim != 2 or len(pts) < 3: return None
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    norm = (pts - lo) / span * 100
    return {"points": [[round(float(x), 1), round(float(y), 1)] for x, y in norm],
            "n_frames": len(contours), "frame_mid": int(np.asarray(obj["Frames"][cell])[len(contours) // 2])}

import struct, zlib as _zlib
def png_gray(rows: np.ndarray) -> bytes:
    """Minimal 8-bit grayscale PNG encoder (stdlib). rows: uint8 array, already top-down."""
    h, w = rows.shape
    raw = b"".join(b"\x00" + rows[i].tobytes() for i in range(h))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", _zlib.crc32(tag + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", _zlib.compress(raw)) + chunk(b"IEND", b""))

def frame_png(patient, date, cell, crop=True):
    """Real grayscale frame for a cell: raw DIB (bottom-up) extracted from *_imaq.avi by tools/extract_imaq_frames.mjs."""
    obj = load_pickle(patient, date)
    if obj is None or cell >= len(obj["Frames"]): return None
    frames = np.asarray(obj["Frames"][cell]); mid = len(frames) // 2
    frame_no = int(frames[mid]); pos_x = float(np.asarray(obj["pos_x"][cell])[mid])
    fdir = ROOT / "data" / "frames" / f"{patient}_{date}_M10"
    raw_path, meta_path = fdir / f"frame_{frame_no}.raw", fdir / f"frame_{frame_no}.json"
    if not raw_path.exists(): return None
    meta = json.loads(meta_path.read_text()); w, h = int(meta["width"]), int(meta["height"])
    img = np.frombuffer(raw_path.read_bytes(), dtype=np.uint8)
    if img.size < w * h: return None
    img = img[:w * h].reshape(h, w)[::-1]  # DIB bottom-up -> top-down
    contour = np.asarray(obj["Contours"][cell][mid], dtype=float)
    if crop:
        x0 = int(max(0, min(w - 200, pos_x - 100)))
        img = img[:, x0:x0 + 200]
        pts = [[round(float(x - x0), 1), round(float(y), 1)] for x, y in contour[::3]]
        full = [[round(float(x), 1), round(float(y), 1)] for x, y in contour[::3]]
        fullres = [[round(float(x - x0), 1), round(float(y), 1)] for x, y in contour]
        return png_gray(img), {"frame": frame_no, "pos_x": round(pos_x, 1), "crop_x0": x0, "crop_w": 200, "frame_height": h, "frame_width": w, "contour_crop": pts, "contour_full": full, "contour_crop_fullres": fullres}
    pts = [[round(float(x), 1), round(float(y), 1)] for x, y in contour[::3]]
    return png_gray(img), {"frame": frame_no, "pos_x": round(pos_x, 1), "frame_height": h, "frame_width": w, "contour_full": pts}

def _committed_envelope(patient, frm, to):
    """Committed envelope for this pair, if one exists. Read-only; never signs."""
    candidates = [ROOT / "logs" / "agent_runs" / f"{patient}_{frm}_{to}" / "envelope.json",
                  ROOT / "data" / "checker" / f"example_report_{patient}_{frm}_{to}.json"]
    for cand in candidates:
        if not cand.exists(): continue
        try: env = json.loads(cand.read_text())
        except Exception: continue
        p = env.get("payload", {})
        if (p.get("patient"), p.get("from_visit"), p.get("to_visit")) == (patient, frm, to):
            return env
    return None

def _committed_report(patient, frm, to):
    for cand in [ROOT / "logs" / "agent_runs" / f"{patient}_{frm}_{to}" / "report.md",
                 ROOT / "data" / "checker" / f"example_report_{patient}_{frm}_{to}.md"]:
        if cand.exists(): return cand.read_text(encoding="utf-8")
    return None

def _envelope_for_pair(patient, frm, to, narrative=""):
    """(envelope, is_committed), or (None, False) when signing is disabled and
    no committed envelope exists. Never signs without a matching private key."""
    try:
        checker.load_signing_key()
    except (checker.NoSigningKey, checker.KeyMismatch):
        env = _committed_envelope(patient, frm, to)
        return (env, True) if env is not None else (None, False)
    return checker.sign_payload(checker.build_payload(patient, frm, to), narrative), False

def public_mode():
    return os.environ.get("PUBLIC_MODE") == "1"

STATIC_ALLOWLIST = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"),
                    "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}

def live_status():
    if public_mode():
        return {"sam_3_1": "CACHED DEMO", "muse_spark_cloud": "CACHED DEMO",
                "muse_voice_transcribe": "CACHED DEMO", "open_weight_auditor": "CACHED DEMO",
                "open_weight_model": "CACHED DEMO"}
    return {"sam_3_1": "LIVE" if os.environ.get("META_MODEL_API_KEY") else "OFFLINE (set META_MODEL_API_KEY)",
            "muse_spark_cloud": "LIVE" if os.environ.get("META_MODEL_API_KEY") else "OFFLINE (set META_MODEL_API_KEY)",
            "muse_voice_transcribe": "LIVE" if os.environ.get("META_MODEL_API_KEY") else "OFFLINE (set META_MODEL_API_KEY)",
            "open_weight_auditor": "LIVE" if os.environ.get("BASETEN_API_KEY") else "OFFLINE (set BASETEN_API_KEY)",
            "open_weight_model": "meta-models/muse-spark-open-1026 via Baseten"}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/meta": return self.send_json({"live": live_status(), "dataset": checker.DATASET_DOI})
            if path == "/api/benchmark":
                f = TABLES / "live_benchmark_summary.json"
                return self.send_json(json.loads(f.read_text()) if f.exists() else {"status": "NOT_RUN", "detail": "run: uv run python src/run_live_benchmark.py"})
            if path == "/api/visits": return self.send_json(pd.read_csv(TABLES / "per_visit_adjusted_v2.csv").to_dict("records"))
            if path == "/api/pairs": return self.send_json(pd.read_csv(TABLES / "visit_pairs_decisions_v2.csv").to_dict("records"))
            if path == "/api/queue":
                q = pd.read_csv(TABLES / "adjudication_queue.csv")
                targets = {}
                tf = ROOT / "data" / "frames" / "targets.json"
                if tf.exists():
                    for pp, dd in json.loads(tf.read_text()).items():
                        for dt, rows in dd.items():
                            for r in rows: targets[(pp, str(dt), int(r["cell"]))] = int(r["frame"])
                def has_frame(r):
                    fr = targets.get((r.patient, str(r.date), int(r.cell)))
                    return bool(fr is not None and (ROOT / "data" / "frames" / f"{r.patient}_{r.date}_M10" / f"frame_{fr}.raw").exists())
                q["has_frame"] = [has_frame(r) for r in q.itertuples()]
                q = q.sort_values(["has_frame", "confidence"], ascending=[False, True])
                return self.send_json(q.head(300).to_dict("records"))
            if path.startswith("/api/sam/"):
                seg = path.split("/"); patient, date, cell = seg[3], seg[4], int(seg[5])
                got = frame_png(patient, date, cell, crop=True)
                if got is None: return self.send_json({"status": "BLOCKED", "detail": "no real frame for this cell"}, 200)
                png, info = got
                sam = meta_api.sam_segment(png, author_poly=info.get("contour_crop_fullres") or info.get("contour_crop"), wh=(200, 40))
                out = {"sam": sam, "author_contour_crop": info.get("contour_crop"), "frame": info.get("frame"),
                       "iou_vs_author": sam.get("iou_vs_author")}
                return self.send_json(out)
            if path.startswith("/api/sparkcheck/"):
                seg = path.split("/"); patient, date, cell = seg[3], seg[4], int(seg[5])
                got = frame_png(patient, date, cell, crop=True)
                if got is None: return self.send_json({"status": "BLOCKED", "detail": "no real frame for this cell"}, 200)
                return self.send_json(meta_api.spark_visual_check(got[0]))
            if path == "/api/kappa":
                rev = json.loads(REVIEWS.read_text()) if REVIEWS.exists() else []
                f = pd.read_csv(TABLES / "cell_features_M10.csv")
                author = {(r.patient, str(r.date), int(r.cell)): int(r.health) for r in f.itertuples()}
                pairs = [(author[(r["patient"], str(r["date"]), int(r["cell"]))], int(r["rater"]))
                         for r in rev if (r["patient"], str(r["date"]), int(r["cell"])) in author]
                return self.send_json(kappa_ac1([p[0] for p in pairs], [p[1] for p in pairs]) | {"reviews": len(rev)})
            if path.startswith("/api/cell/"):
                _, _, _, patient, date, cell = path.split("/")
                c = cell_contour(patient, date, int(cell))
                return self.send_json(c or {"error": "contour unavailable"}, 200 if c else 404)
            if path.startswith("/api/longitudinal/"):
                patient = path.split("/")[-1]
                raw = pd.read_csv(TABLES / "per_visit.csv"); adj = pd.read_csv(TABLES / "per_visit_adjusted_v2.csv")
                dec = pd.read_csv(TABLES / "visit_pairs_decisions_v2.csv")
                m = adj[adj.patient == patient].copy()
                m["frac_raw"] = [float(raw[(raw.patient == patient) & (raw.date.astype(str) == str(d))].frac_health1.iloc[0]) for d in m.date]
                m["qc_blocked"] = m.skip_rate > 0.25
                return self.send_json({"visits": m.to_dict("records"),
                                       "pairs": dec[dec.patient == patient].to_dict("records")})
            if path.startswith("/api/frame/") or path.startswith("/api/frameinfo/"):
                # /api/frame/<patient>/<date>/<cell>/crop.png|strip.png ; /api/frameinfo/<patient>/<date>/<cell>
                seg = path.split("/")
                patient, date, cell = seg[3], seg[4], int(seg[5].split(".")[0])
                is_crop = "strip" not in path
                got = frame_png(patient, date, cell, crop=is_crop)
                if got is None: return self.send_json({"error": "frame not extracted for this cell (sample: P1 0w M10 cells 4, 11, 19)"}, 404)
                png, info = got
                if "frameinfo" in path: return self.send_json(info)
                self.send_response(200); self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png))); self.end_headers(); self.wfile.write(png); return
            if path.startswith("/api/report/"):
                _, _, _, patient, frm, to = path.split("/")
                # Peek at committed envelope first: with no key we serve it as-is.
                try: checker.load_signing_key(); has_key = True
                except (checker.NoSigningKey, checker.KeyMismatch): has_key = False
                narrative, nsrc = "Flow standardized change assessed against the combined noise band.", "template"
                if not has_key:
                    env = _committed_envelope(patient, frm, to)
                    if env is None: return self.send_json({"status": "SIGNING_DISABLED"}, 409)
                    committed = True
                    report = _committed_report(patient, frm, to) or checker.render_report(env, narrative)
                    ow = {"status": "SIGNING_DISABLED", "detail": "committed envelope served; no signing key present"}
                else:
                    committed = False
                    payload0 = checker.build_payload(patient, frm, to)
                    spark = meta_api.spark_narrative(payload0)
                    if spark.get("status") == "OK" and spark.get("text") and not any(ch.isdigit() for ch in spark["text"]):
                        cand = spark["text"].strip()
                        try: checker.render_report({"payload": payload0}, cand); narrative, nsrc = cand, f"muse-spark-1.3 ({spark.get('_cache')})"
                        except ValueError: pass
                    env = checker.sign_payload(payload0, narrative)
                    report = checker.render_report(env, narrative)
                    ow = None
                ok, errs = checker.verify_envelope(env, report_text=report)
                aok, aerrs = checker.audit_report(report, env)
                if ow is None: ow = meta_api.baseten_audit(report, env["payload"])
                return self.send_json({"envelope": env, "report": report, "verified": ok, "verify_errors": errs,
                                       "audit_ok": aok, "audit_errors": aerrs, "narrative_source": nsrc,
                                       "cloud": {"model": "muse-spark-1.3", "narrative_source": nsrc, "checker_verified": ok},
                                       "open_weight": ow})
            if path in STATIC_ALLOWLIST:
                name, ct = STATIC_ALLOWLIST[path]
                b = (WEB / name).read_bytes(); self.send_response(200)
                self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
                self.end_headers(); self.wfile.write(b); return
            return self.send_json({"error": "not found"}, 404)
        except Exception as e:
            return self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict): raise ValueError("JSON body must be an object")
        except Exception as e:
            return self.send_json({"error": f"malformed request body: {type(e).__name__}: {e}"}, 400)
        try:
            return self._post(body)
        except KeyError as e:
            return self.send_json({"error": f"missing field: {e}"}, 400)
        except (ValueError, TypeError) as e:
            return self.send_json({"error": f"invalid field: {type(e).__name__}: {e}"}, 400)
        except Exception as e:
            return self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)
    def _post(self, body):
        if public_mode() and self.path in ("/api/review", "/api/signoff", "/api/transcribe"):
            return self.send_json({"error": "PUBLIC_MODE: this endpoint is disabled in the read-only demo"}, 403)
        if self.path == "/api/transcribe":
            import base64 as _b64
            try:
                wav = _b64.b64decode(body.get("audio_b64", ""), validate=True)
            except Exception as e:
                return self.send_json({"status": "BLOCKED", "detail": f"invalid audio_b64: {e}"})
            if not wav: return self.send_json({"status": "BLOCKED", "detail": "empty audio"})
            return self.send_json(meta_api.transcribe_audio(wav, mode=body.get("mode", "PUSH_TO_TALK")))
        if self.path == "/api/signoff":
            payload_sha = str(body.get("payload_sha256") or "")
            report_sha = str(body.get("report_sha256") or "")
            import re as _re
            if not _re.fullmatch(r"[0-9a-f]{64}", payload_sha) or not _re.fullmatch(r"[0-9a-f]{64}", report_sha):
                return self.send_json({"error": "sign-off requires payload_sha256 and report_sha256 of the active report (generate a report first)"}, 400)
            import datetime as _dt
            entry = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "patient": body.get("patient"),
                     "from": body.get("from"), "to": body.get("to"), "decision": body.get("decision"),
                     "note": body.get("note", ""), "payload_sha256": payload_sha, "report_sha256": report_sha}
            f = ROOT / "data" / "signoffs.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            with f.open("a", encoding="utf-8") as fh: fh.write(json.dumps(entry) + "\n")
            return self.send_json({"saved": True, "ts": entry["ts"], "payload_sha256": payload_sha, "report_sha256": report_sha})
        if self.path == "/api/review":
            rev = json.loads(REVIEWS.read_text()) if REVIEWS.exists() else []
            rev = [r for r in rev if not (r["patient"] == body["patient"] and str(r["date"]) == str(body["date"]) and int(r["cell"]) == int(body["cell"]))]
            rev.append({"patient": body["patient"], "date": str(body["date"]), "cell": int(body["cell"]), "rater": int(body["rater"])})
            REVIEWS.write_text(json.dumps(rev, indent=1))
            return self.send_json({"saved": True, "reviews": len(rev)})
        if self.path == "/api/tamper":
            mode = body.get("mode")
            env, _committed = _envelope_for_pair(body["patient"], body["from"], body["to"])
            if env is None: return self.send_json({"status": "SIGNING_DISABLED"}, 409)
            report = checker.render_report(env, "Flow standardized change assessed against the combined noise band.")
            if mode == "number":
                report = report.replace(f"{env['payload']['delta_adj']:+.4f}", "+0.9999")
                ok, errs = checker.audit_report(report, env)
                vok, verrs = checker.verify_envelope(env)
                return self.send_json({"tampered": "number", "checker_verifies_envelope": vok,
                                       "auditor_blocks_report": not ok, "auditor_errors": errs, "report": report})
            if mode == "advice":
                report += "\nAssessment: disease progression confirmed. We recommend treatment: start dasatinib."
                ok, errs = checker.audit_report(report, env)
                return self.send_json({"tampered": "clinical_advice", "auditor_blocks_report": not ok, "auditor_errors": errs, "report": report})
            env["payload"]["delta_adj"] += 0.05
            ok, errs = checker.verify_envelope(env, check_tables=False)
            return self.send_json({"tampered": "payload", "checker_blocks": not ok, "verify_errors": errs})
        return self.send_json({"error": "unknown POST"}, 404)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    print(f"HelpChoreAI UI on http://127.0.0.1:{args.port}  live={live_status()}")
    ThreadingHTTPServer(("127.0.0.1", args.port), H).serve_forever()
