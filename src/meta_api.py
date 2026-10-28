#!/usr/bin/env python3
"""Real cached model calls. Cache: data/api_cache/<sha256-of-canonical-request>.json — repeat clicks are free.
Meta Model API: OpenAI-compatible https://api.meta.ai/v1/chat/completions, Bearer META_MODEL_API_KEY (or MODEL_API_KEY).
Baseten: https://inference.baseten.co/v1/chat/completions, Bearer BASETEN_API_KEY, model meta-models/muse-spark-open-1026.
Every failure returns BLOCKED with the real error — never a fabricated PASS.
"""
import base64, hashlib, json, os, re, urllib.request, urllib.error
from pathlib import Path
from env import load_env

load_env()
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "api_cache"
META_BASE = os.environ.get("META_API_BASE", "https://api.meta.ai/v1")
BASETEN_URL = os.environ.get("BASETEN_API_URL", "https://inference.baseten.co/v1/chat/completions")

def _key(model, messages, extra=""):
    canon = json.dumps({"model": model, "messages": messages, "extra": extra}, sort_keys=True).encode()
    return hashlib.sha256(canon).hexdigest()

def _post(url, key, body, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def chat_cached(base_url, api_key, model, messages, extra=""):
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key(model, messages, extra)
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if not api_key:
        return {"status": "BLOCKED", "detail": "API key not set", "_cache": "miss"}
    try:
        resp = _post(base_url.rstrip("/") + "/chat/completions", api_key,
                     {"model": model, "messages": messages})
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        out = {"status": "OK", "model": model, "text": text, "raw_id": resp.get("id")}
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

def img_msg(text, png_bytes):
    b64 = base64.b64encode(png_bytes).decode()
    return [{"role": "user", "content": [{"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]

def sam_segment(png_bytes):
    """SAM 3.1 segmentation via Meta Model API. Returns polygon points in image coords if parseable."""
    key = os.environ.get("META_MODEL_API_KEY")
    prompt = ("Segment the single red blood cell in the center of this grayscale microfluidic channel crop. "
              "Reply ONLY with JSON: {\"polygon\": [[x,y],...]} using pixel coordinates of the input image. No other text.")
    r = chat_cached(META_BASE, key, "sam-3.1", img_msg(prompt, png_bytes), extra=hashlib.sha256(png_bytes).hexdigest())
    if r.get("status") != "OK": return r
    m = re.search(r"\{.*\}", r.get("text", ""), re.S)
    if not m: return {"status": "BLOCKED", "detail": "sam-3.1 reply contained no JSON polygon", "text_head": r.get("text", "")[:200], "_cache": r["_cache"]}
    try:
        poly = json.loads(m.group(0)).get("polygon")
    except Exception as e:
        return {"status": "BLOCKED", "detail": f"polygon parse failed: {e}", "_cache": r["_cache"]}
    if not poly or len(poly) < 3: return {"status": "BLOCKED", "detail": "empty polygon", "_cache": r["_cache"]}
    return {"status": "OK", "model": "sam-3.1", "polygon": poly, "_cache": r["_cache"]}

def spark_visual_check(png_bytes):
    key = os.environ.get("META_MODEL_API_KEY")
    prompt = ("You are a research QC assistant. Look at this grayscale microfluidic red-blood-cell crop. "
              "Describe ONLY visible morphology (spicules, shape, image quality) in 2 short sentences. "
              "No numbers, no diagnosis, no treatment advice.")
    return chat_cached(META_BASE, key, "muse-spark-1.3", img_msg(prompt, png_bytes), extra=hashlib.sha256(png_bytes).hexdigest())

def spark_narrative(payload):
    key = os.environ.get("META_MODEL_API_KEY")
    prompt = ("Write ONE short narrative sentence for a research audit report about a visit-to-visit change "
              "that was assessed against a combined measurement-and-protocol noise band. "
              "Rules: no digits, no numbers spelled out, no diagnosis, no disease-progression claim, "
              "no treatment advice. Decision category: " + str(payload.get("decision")) +
              ". Treatment context: " + str(payload.get("treatment")) + ".")
    return chat_cached(META_BASE, key, "muse-spark-1.3", [{"role": "user", "content": prompt}],
                       extra=json.dumps(payload, sort_keys=True))

def baseten_audit(report, payload):
    key = os.environ.get("BASETEN_API_KEY")
    prompt = ("You are a compliance auditor. Check this research report against its payload. "
              "Flag clinical-advice language, disease-progression claims, patient identifiers, or any number "
              "not present in the payload. Reply starting with BLOCK or PASS, then one short reason.\nPAYLOAD: "
              + json.dumps(payload) + "\nREPORT:\n" + report)
    r = chat_cached(BASETEN_URL.rsplit("/chat/completions", 1)[0], key, "meta-models/muse-spark-open-1026",
                    [{"role": "user", "content": prompt}])
    if r.get("status") != "OK": return r
    txt = r.get("text", "")
    return {"status": "BLOCK" if txt.strip().upper().startswith("BLOCK") else "PASS",
            "model": "meta-models/muse-spark-open-1026", "detail": txt[:300], "_cache": r["_cache"]}

def polygon_iou(poly_a, poly_b, w, h):
    """Raster IoU on a w x h grid (numpy, point-in-polygon via ray casting on pixel centers)."""
    import numpy as np
    def mask(poly):
        pts = np.asarray(poly, dtype=float)
        yy, xx = np.mgrid[0:h, 0:w]
        inside = np.zeros((h, w), dtype=bool)
        x, y = pts[:, 0], pts[:, 1]
        j = len(pts) - 1
        for i in range(len(pts)):
            cond = ((y[i] > yy) != (y[j] > yy)) & (xx < (x[j] - x[i]) * (yy - y[i]) / max(y[j] - y[i], 1e-9) + x[i])
            inside ^= cond; j = i
        return inside
    a, b = mask(poly_a), mask(poly_b)
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else 0.0
