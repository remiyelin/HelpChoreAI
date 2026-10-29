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

def _public():
    return os.environ.get("PUBLIC_MODE") == "1"

def chat_cached(base_url, api_key, model, messages, extra=""):
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key(model, messages, extra)
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    if not api_key:
        return {"status": "BLOCKED", "detail": "API key not set", "_cache": "miss"}
    try:
        resp = _post(base_url.rstrip("/") + "/chat/completions", api_key,
                     {"model": model, "messages": messages})
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        out = {"status": "OK", "model": model, "text": text, "raw_id": resp.get("id")}
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

def img_msg(text, png_bytes):
    b64 = base64.b64encode(png_bytes).decode()
    return [{"role": "user", "content": [{"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]

def _mask_outline(raster: bytes, mw: int, mh: int, ox: int, oy: int):
    """Row-span outline polygon (image coords) from a binary raster placed at (ox,oy)."""
    import numpy as np
    m = np.frombuffer(raster, dtype=np.uint8).reshape(mh, mw)
    top, bot = [], []
    for y in range(mh):
        xs = np.flatnonzero(m[y])
        if len(xs): top.append([int(xs[0]) + ox, y + oy]); bot.append([int(xs[-1]) + ox, y + oy])
    if not top: return [], m
    return top + bot[::-1], m

def sam_segment(png_bytes, author_poly=None, wh=(200, 40)):
    """REAL SAM 3.1 via Responses API (streaming) + official meta_sam_parser. Cached by image+prompt hash.
    Concept prompt 'red blood cell' first; box-prompt (author box) fallback is labelled honestly.
    Returns mask polygon in crop coords + raster IoU vs author polygon when provided."""
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    img_hash = hashlib.sha256(png_bytes).hexdigest()
    if png_bytes[:8] == b"\x89PNG\r\n\x1a\n":  # true media size (crops are 200x48, not 200x40)
        wh = (int.from_bytes(png_bytes[16:20], "big"), int.from_bytes(png_bytes[20:24], "big"))
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key("sam-3.1", [{"img": img_hash, "author": author_poly}], extra="responses-v2")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    if not key: return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    try:
        out = _sam_run(key, png_bytes, author_poly, wh)
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

def _sam_run(key, png_bytes, author_poly, wh):
    import asyncio, base64
    from meta_sam_parser import (parse_responses_stream, image_segmentation_format,
                                 decode_mask_to_raster, build_object_prompt, PromptObject, PromptBox, FramePrompt)
    w, h = wh
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    async def events_of(stream):
        completed = set()
        async for event in stream:
            data = event.model_dump() if hasattr(event, "model_dump") else dict(event)
            lane = (data.get("item_id"), data.get("output_index"), data.get("content_index"))
            if data.get("type") == "response.output_text.done":
                if lane not in completed: completed.add(lane); yield data
                continue
            yield data
            part = data.get("part")
            if (data.get("type") == "response.content_part.done" and lane not in completed
                    and isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str)):
                completed.add(lane)
                yield {"type": "response.output_text.done", "item_id": data.get("item_id"),
                       "output_index": data.get("output_index"), "content_index": data.get("content_index"),
                       "text": part["text"]}
    def fetch_events(prompt_text):
        """urllib SSE transport (httpx/OpenAI SDK sockets are blocked in some sandboxes; urllib works)."""
        import urllib.request as _u
        body = json.dumps({"model": "sam-3.1", "stream": True, "input": [
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt_text},
                {"type": "input_image", "image_url": data_url}]}]}).encode()
        req = _u.Request(META_BASE.rstrip("/") + "/responses", data=body,
                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        events, completed = [], set()
        with _u.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"): continue
                payload = line[5:].strip()
                if payload == "[DONE]": break
                try: data = json.loads(payload)
                except Exception: continue
                lane = (data.get("item_id"), data.get("output_index"), data.get("content_index"))
                if data.get("type") == "response.output_text.done":
                    if lane not in completed: completed.add(lane); events.append(data)
                    continue
                events.append(data)
                part = data.get("part")
                if (data.get("type") == "response.content_part.done" and lane not in completed
                        and isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str)):
                    completed.add(lane)
                    events.append({"type": "response.output_text.done", "item_id": data.get("item_id"),
                                   "output_index": data.get("output_index"), "content_index": data.get("content_index"),
                                   "text": part["text"]})
        return events
    def run_sync(prompt_text):
        # Selector loop: Proactor's self-pipe socketpair is blocked in sandboxes (WinError 10013).
        loop = asyncio.SelectorEventLoop()
        try:
            return loop.run_until_complete(run(prompt_text))
        finally:
            loop.close()
    async def run(prompt_text):
        events = fetch_events(prompt_text)
        async def agen():
            for e in events: yield e
        return await parse_responses_stream(agen(), image_segmentation_format()).final_result()
    def records_of(result):
        recs = []
        for rec in getattr(result, "records", []) or []:
            try:
                raster = decode_mask_to_raster(rec.mask)
                b = rec.bounds
                left, top, right, bottom = int(b.left), int(b.top), int(b.right), int(b.bottom)
                recs.append({"raster": raster, "mw": int(rec.mask.width), "mh": int(rec.mask.height),
                             "left": left, "top": top, "right": right, "bottom": bottom})
            except Exception:
                continue
        return recs
    result = run_sync("red blood cell")
    recs, mode = records_of(result), "concept:red blood cell"
    if not recs and author_poly:
        xs = [p[0] for p in author_poly]; ys = [p[1] for p in author_poly]
        prompt = build_object_prompt(size=(w, h), objects=[PromptObject(id="1", prompts=[
            FramePrompt(frame=0, box=PromptBox(left=int(min(xs)), top=int(min(ys)), right=int(max(xs)), bottom=int(max(ys))))])])
        result = run_sync(prompt)
        recs, mode = records_of(result), "box-prompt(author box)"
    if not recs:
        return {"status": "BLOCKED", "detail": f"sam-3.1 returned zero masks ({mode})", "prompt_mode": mode}
    # pick record whose box center is closest to author box center (or crop center)
    cx = (sum(p[0] for p in author_poly) / len(author_poly)) if author_poly else w / 2
    cy = (sum(p[1] for p in author_poly) / len(author_poly)) if author_poly else h / 2
    rec = min(recs, key=lambda r: ((r["left"] + r["right"]) / 2 - cx) ** 2 + ((r["top"] + r["bottom"]) / 2 - cy) ** 2)
    mw, mh = rec["mw"] or (rec["right"] - rec["left"] + 1), rec["mh"] or (rec["bottom"] - rec["top"] + 1)
    poly, raster = _mask_outline(rec["raster"], mw, mh, rec["left"], rec["top"])
    out = {"status": "OK", "model": "sam-3.1", "prompt_mode": mode, "polygon": poly,
           "box": [rec["left"], rec["top"], rec["right"], rec["bottom"]], "records": len(recs)}
    if author_poly:
        import numpy as np
        author_raster = np.zeros((h, w), dtype=np.uint8)
        # rasterize author polygon via polygon_iou helper mask logic
        yy, xx = np.mgrid[0:h, 0:w]; pts = np.asarray(author_poly, dtype=float)
        inside = np.zeros((h, w), dtype=bool); x, y = pts[:, 0], pts[:, 1]; j = len(pts) - 1
        for i in range(len(pts)):
            cond = ((y[i] > yy) != (y[j] > yy)) & (xx < (x[j] - x[i]) * (yy - y[i]) / max(y[j] - y[i], 1e-9) + x[i])
            inside ^= cond; j = i
        sam_full = np.zeros((h, w), dtype=np.uint8)
        sub = np.frombuffer(rec["raster"], dtype=np.uint8).reshape(mh, mw)
        y0, y1, x0, x1 = rec["top"], min(h, rec["top"] + mh), rec["left"], min(w, rec["left"] + mw)
        if y1 > y0 and x1 > x0: sam_full[y0:y1, x0:x1] = sub[:y1 - y0, :x1 - x0]
        union = ((inside > 0) | (sam_full > 0)).sum()
        out["iou_vs_author"] = round(float(((inside > 0) & (sam_full > 0)).sum() / union), 3) if union else 0.0
    return out

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
    # Hackathon ID per guide; Baseten public changelog lists meta-models/muse-spark-open. Try in order, report served model.
    for model in ["meta-models/muse-spark-open-1026", "meta-models/muse-spark-open"]:
        r = chat_cached(BASETEN_URL.rsplit("/chat/completions", 1)[0], key, model,
                        [{"role": "user", "content": prompt}])
        if r.get("status") == "OK":
            txt = r.get("text", "")
            return {"status": "BLOCK" if txt.strip().upper().startswith("BLOCK") else "PASS",
                    "model": model, "detail": txt[:300], "_cache": r["_cache"]}
    return r

VOICE_MODEL = os.environ.get("META_VOICE_MODEL", "muse-voice-transcribe-1.0")  # alias: muse-voice-transcribe
VOICE_URL = META_BASE.rstrip("/") + "/asr/transcribe"
VOICE_MODES = ("PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION")

def make_sample_wav(path, seconds=1.6, rate=24000):
    """Synthesized sample review clip (formant-like sweep + pauses, no real speech). 24 kHz mono 16-bit WAV."""
    import math, wave as _wave
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        seg = 0.6 * math.sin(2 * math.pi * (180 + 90 * math.sin(2 * math.pi * 1.4 * t)) * t) \
            * (0.25 + 0.75 * abs(math.sin(math.pi * t / 0.4))) if (t % 0.5) < 0.38 else 0.0
        v = max(-32767, min(32767, int(seg * 9000)))
        frames += int(v).to_bytes(2, "little", signed=True)
    with _wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(bytes(frames))
    return path

def _post_multipart(url, key, body, ctype, timeout=120):
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def transcribe_audio(wav_bytes, mode="PUSH_TO_TALK", filename="review.wav"):
    """Muse Voice Transcribe (POST /v1/asr/transcribe, multipart request-JSON + audio). Cached by audio hash.
    Returns {status: OK, text, turns, audio_ms} or BLOCKED with the real error — never a fabricated transcript."""
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not key: return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    if mode not in VOICE_MODES: return {"status": "BLOCKED", "detail": f"unknown mode {mode!r} (server ignores bad modes)"}
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key(VOICE_MODEL, [{"audio": hashlib.sha256(wav_bytes).hexdigest(), "mode": mode}], extra="asr-v1")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    boundary = "----helpchoreai-voice-boundary"
    req_json = json.dumps({"mode": mode, "model": VOICE_MODEL, "audioEncoding": "WAV"})
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"request\"\r\nContent-Type: application/json\r\n\r\n{req_json}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{filename}\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode() + wav_bytes + f"\r\n--{boundary}--\r\n".encode()
    try:
        resp = _post_multipart(VOICE_URL, key, body, f"multipart/form-data; boundary={boundary}")
        text = resp.get("transcript") or " ".join(t.get("transcript", "") for t in resp.get("turns", [])).strip()
        out = {"status": "OK", "model": VOICE_MODEL, "text": text, "turns": resp.get("turns"),
               "audio_ms": resp.get("audioDurationMs"), "session_id": resp.get("sessionId")}
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

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

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "make-sample-wav":
        print(make_sample_wav(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "transcribe":
        wav = Path(sys.argv[2]).read_bytes()
        mode = sys.argv[3] if len(sys.argv) > 3 else "PUSH_TO_TALK"
        print(json.dumps(transcribe_audio(wav, mode=mode, filename=Path(sys.argv[2]).name), indent=1))
    else:
        print("usage: meta_api.py make-sample-wav <out.wav> | transcribe <in.wav> [MODE]")
