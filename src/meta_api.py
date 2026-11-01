#!/usr/bin/env python3
"""Real cached model calls. Cache: data/api_cache/<sha256-of-canonical-request>.json — repeat clicks are free.
Meta Model API: OpenAI-compatible https://api.meta.ai/v1/chat/completions, Bearer META_MODEL_API_KEY (or MODEL_API_KEY).
Open weights: any OpenAI-compatible host. Default Baseten (BASETEN_API_KEY, model meta-models/muse-spark-open);
OPEN_BASE_URL, OPEN_API_KEY and OPEN_MODEL point the same code at Modal, Fireworks or your own server.
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
OPEN_URL = os.environ.get("OPEN_BASE_URL", "").rstrip("/")
if OPEN_URL: BASETEN_URL = OPEN_URL + "/chat/completions"

def _open_key():
    return os.environ.get("OPEN_API_KEY") or os.environ.get("BASETEN_API_KEY")

def _open_extra():
    effort = os.environ.get("OPEN_REASONING_EFFORT")  # reasoning tokens bill as output; Baseten defaults to xhigh
    return {"reasoning_effort": effort} if effort else {}

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

def open_weight_only():
    return os.environ.get("OPEN_WEIGHT_ONLY") == "1"

def _open_blocked(what="meta"):
    return {"status": "BLOCKED_OPEN_ONLY",
            "detail": f"OPEN_WEIGHT_ONLY=1: {what} (Meta) call refused before the network; Meta spend stays $0.00",
            "_cache": "miss", "_new_calls": 0}

def chat_cached(base_url, api_key, model, messages, extra=""):
    if open_weight_only() and ("api.meta.ai" in str(base_url) or str(base_url).rstrip("/") == META_BASE.rstrip("/")):
        return _open_blocked("chat")
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
        body = {"model": model, "messages": messages}
        if "api.meta.ai" not in str(base_url): body |= _open_extra()
        resp = _post(base_url.rstrip("/") + "/chat/completions", api_key, body)
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
    if open_weight_only(): return _open_blocked("SAM")
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    img_hash = hashlib.sha256(png_bytes).hexdigest()
    if png_bytes[:8] == b"\x89PNG\r\n\x1a\n":  # true media size (crops are 200x48, not 200x40)
        wh = (int.from_bytes(png_bytes[16:20], "big"), int.from_bytes(png_bytes[20:24], "big"))
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key("sam-3.1", [{"img": img_hash, "author": author_poly}], extra="responses-v2")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text())
        _attach_iou(out, author_poly, wh)
        out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    if not key: return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    try:
        out = _sam_run(key, png_bytes, author_poly, wh)
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    _attach_iou(out, author_poly, wh)
    return out | {"_cache": "miss"}

def _attach_iou(out, author_poly, wh):
    """IoU vs author contour via geometry.py, computed after cache retrieval (never stored)."""
    if out.get("status") != "OK" or not author_poly: return
    import geometry
    w, h = wh
    sam_mask = (geometry.mask_from_rows(out["mask_rows"], h, w) if out.get("mask_rows")
                else geometry.mask_from_rowspans(out.get("polygon") or [], h, w))
    out["iou_vs_author"] = round(geometry.iou(sam_mask, geometry.fill_contour(author_poly, h, w)), 3)
    out["sam_area"] = geometry.area(sam_mask)
    out["author_area"] = geometry.area(geometry.fill_contour(author_poly, h, w))

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
        # PromptBox is half-open: right/bottom are one past the last pixel (builder writes x2=right-1).
        prompt = build_object_prompt(size=(w, h), objects=[PromptObject(id="1", prompts=[
            FramePrompt(frame=0, box=PromptBox(left=int(min(xs)), top=int(min(ys)), right=int(max(xs)) + 1, bottom=int(max(ys)) + 1))])])
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
    # Store the decoded mask as row spans in the cache entry; IoU is computed OUTSIDE the
    # cache (geometry.py) by callers, never stored. Raster is cropped to the box, pasted at (left, top).
    import numpy as np
    sub = np.frombuffer(rec["raster"], dtype=np.uint8).reshape(mh, mw)
    rows = []
    for yy in range(mh):
        xs_on = np.flatnonzero(sub[yy])
        if len(xs_on): rows.append([int(yy + rec["top"]), int(xs_on[0] + rec["left"]), int(xs_on[-1] + rec["left"])])
    return {"status": "OK", "model": "sam-3.1", "prompt_mode": mode, "polygon": poly, "mask_rows": rows,
            "box": [rec["left"], rec["top"], rec["right"], rec["bottom"]], "records": len(recs)}

RATER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "spiculated": {"type": "string", "enum": ["yes", "no", "cannot_tell"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "spicule_points": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"frame": {"type": "integer"}, "x": {"type": "integer", "minimum": 0, "maximum": 1000},
                           "y": {"type": "integer", "minimum": 0, "maximum": 1000}},
            "required": ["frame", "x", "y"]}},
        "image_quality": {"type": "string", "enum": ["ok", "poor"]},
        "reason": {"type": "string"}},
    "required": ["spiculated", "confidence", "spicule_points", "image_quality", "reason"]}

RATER_PROMPT = ("You are a second rater for research microscopy. You are shown frames of the same red blood cell "
    "in a microfluidic channel, each preceded by a short text id such as 'frame 1 of 3' and upscaled for "
    "visibility. Judge ONLY visible morphology. A spiculated cell has distinct pointed protrusions (spicules) "
    "on its outline. Set spiculated to yes if clear spicules are visible in any frame, no if the outline is "
    "smooth in all frames, and cannot_tell if the images do not allow a judgement. confidence is your "
    "probability that the spiculated judgement is correct. spicule_points lists the clearest spicule tips, "
    "each with its frame number and x and y on a 0-1000 grid with 0,0 at the top-left of that frame image. "
    "image_quality is poor if blur, darkness or artefacts prevent judgement. reason is at most 20 words, "
    "morphology only. Reply with the JSON object only.")

def spark_rater(png_list, repeat=0):
    """Structured second-rater call: muse-spark-1.3, reasoning_effort=low, enforced json_schema.
    Cached by image hashes + repeat index (repeats are distinct cache entries by design).
    Returns the parsed rater dict, or BLOCKED/CACHE_ONLY — never a fabricated judgement."""
    if open_weight_only(): return _open_blocked("rater")
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    hashes = [hashlib.sha256(p).hexdigest() for p in png_list]
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key("muse-spark-1.3-rater", [{"imgs": hashes, "repeat": repeat, "prompt": RATER_PROMPT}], extra="rater-v1")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    if not key:
        return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    content = [{"type": "text", "text": RATER_PROMPT}]
    for i, png in enumerate(png_list):
        content.append({"type": "text", "text": f"frame {i + 1} of {len(png_list)}"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
    body = {"model": "muse-spark-1.3", "reasoning_effort": "low",
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "rbc_second_rater", "strict": True, "schema": RATER_SCHEMA}}}
    try:
        resp = _post(META_BASE.rstrip("/") + "/chat/completions", key, body, timeout=180)
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(text)
        if set(parsed) != set(RATER_SCHEMA["required"]) or parsed["spiculated"] not in ("yes", "no", "cannot_tell"):
            raise ValueError("schema-violating rater reply")
        parsed["spicule_points"] = [{"frame": int(p["frame"]), "x": max(0, min(1000, int(p["x"]))),
                                     "y": max(0, min(1000, int(p["y"])))} for p in parsed["spicule_points"]]
        out = {"status": "OK", "model": "muse-spark-1.3", "rater": parsed, "raw_id": resp.get("id")}
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

def _validate_rater(parsed):
    if not isinstance(parsed, dict) or set(parsed) != set(RATER_SCHEMA["required"]):
        raise ValueError("schema-violating rater reply")
    if parsed["spiculated"] not in ("yes", "no", "cannot_tell"): raise ValueError("bad spiculated value")
    if not (0 <= float(parsed["confidence"]) <= 1): raise ValueError("bad confidence")
    if parsed["image_quality"] not in ("ok", "poor"): raise ValueError("bad image_quality")
    if not isinstance(parsed["spicule_points"], list) or not isinstance(parsed["reason"], str):
        raise ValueError("bad spicule_points/reason")
    parsed["spicule_points"] = [{"frame": int(p["frame"]), "x": max(0, min(1000, int(p["x"]))),
                                 "y": max(0, min(1000, int(p["y"])))} for p in parsed["spicule_points"]]
    return parsed

def baseten_rater(png_list, repeat=0):
    """Open-weight second rater: meta-models/muse-spark-open on Baseten, same prompt/schema/images
    as spark_rater. Parses message.content only (reasoning_content ignored), validates the JSON
    in Python, retries once on invalid JSON, then falls back to null (BLOCKED) — never fabricates.
    Cached by image hashes + repeat in data/api_cache/ like every paid call."""
    load_env()
    key = _open_key()
    hashes = [hashlib.sha256(p).hexdigest() for p in png_list]
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key("muse-spark-open-rater", [{"imgs": hashes, "repeat": repeat, "prompt": RATER_PROMPT}], extra="rater-open-v1")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; out["_new_calls"] = 0; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss", "_new_calls": 0}
    if not key:
        return {"status": "BLOCKED", "detail": "BASETEN_API_KEY not set", "_new_calls": 0}
    content = [{"type": "text", "text": RATER_PROMPT}]
    for i, png in enumerate(png_list):
        content.append({"type": "text", "text": f"frame {i + 1} of {len(png_list)}"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
    body = {"model": "meta-models/muse-spark-open",
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "rbc_second_rater", "strict": True, "schema": RATER_SCHEMA}}}
    last_err = None
    for attempt in range(2):  # initial call + at most one retry on invalid JSON
        try:
            resp = _post(BASETEN_URL, key, body, timeout=180)
            msg = resp.get("choices", [{}])[0].get("message", {})
            text = msg.get("content", "")  # reasoning_content deliberately ignored
            if isinstance(text, list):
                text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
            parsed = _validate_rater(json.loads(text))
            out = {"status": "OK", "model": "meta-models/muse-spark-open", "rater": parsed,
                   "raw_id": resp.get("id"), "_new_calls": attempt + 1}
            hit.write_text(json.dumps(out, indent=1))
            return out | {"_cache": "miss"}
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    return {"status": "BLOCKED", "detail": last_err, "rater": None, "_cache": "miss", "_new_calls": 2}

BASETEN_MODEL = os.environ.get("OPEN_MODEL", "meta-models/muse-spark-open")


def baseten_models():
    """GET /v1/models on the Baseten endpoint (cached in data/api_cache). Returns served ids."""
    load_env()
    key = _open_key()
    CACHE.mkdir(parents=True, exist_ok=True)
    hit = CACHE / ("baseten_models.json" if not OPEN_URL else f"models_{hashlib.sha256(OPEN_URL.encode()).hexdigest()[:12]}.json")
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if not key:
        return {"status": "BLOCKED", "detail": "BASETEN_API_KEY not set", "models": [], "_cache": "miss"}
    try:
        req = urllib.request.Request(BASETEN_URL.rsplit("/chat/completions", 1)[0] + "/models",
                                     headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
        out = {"status": "OK", "models": [m.get("id") for m in data.get("data", [])]}
    except Exception as e:
        return {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}", "models": [], "_cache": "miss"}
    hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}


def baseten_chat(messages, model=None, extra="baseten-chat-v1"):
    """One cached Baseten chat completion. Returns {status, model, text, _cache}."""
    model = model or BASETEN_MODEL
    return chat_cached(BASETEN_URL.rsplit("/chat/completions", 1)[0], _open_key(),
                       model, messages, extra=extra)


def baseten_narrative(payload):
    """Open-weight narrative (Baseten), same rules as spark_narrative."""
    prompt = ("Write ONE short narrative sentence for a research audit report about a visit-to-visit change "
              "that was assessed against a combined measurement-and-protocol noise band. "
              "Rules: no digits, no numbers spelled out, no diagnosis, no disease-progression claim, "
              "no treatment advice. Decision category: " + str(payload.get("decision")) +
              ". Treatment context: " + str(payload.get("treatment")) + ".")
    return baseten_chat([{"role": "user", "content": prompt}], extra="narrative:" + json.dumps(payload, sort_keys=True))


def baseten_agent_chat(messages, tools, model=None):
    """Agent chat via Baseten native tool calling (the endpoint returns
    message.tool_calls, verified 2026-11-01). Cached by messages+tools.
    Invalid message (no content and no tool_calls): one retry, then a
    refusal message. Returns the assistant message dict."""
    load_env()
    model = model or BASETEN_MODEL
    key = _open_key()
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key(model + "-agent-baseten", [{"messages": messages, "tools": tools}], extra="agent-open-v1")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); return out["message"]
    if not key:
        raise RuntimeError("BLOCKED: BASETEN_API_KEY not set")
    body = {"model": model, "messages": messages, "tools": tools,
            "tool_choice": "auto", "parallel_tool_calls": False} | _open_extra()
    last = None
    for _attempt in range(2):
        resp = _post(BASETEN_URL, key, body, timeout=180)
        msg = resp.get("choices", [{}])[0].get("message", {})
        if isinstance(msg, dict) and (msg.get("tool_calls") or msg.get("content")):
            hit.write_text(json.dumps({"message": msg, "model": resp.get("model", model),
                                       "usage": resp.get("usage")}, indent=1))
            return msg
        last = msg
    return {"role": "assistant", "content": "REFUSED: open-weight endpoint returned no usable message "
                                            "(no content and no tool calls) after one retry."}


def _run_coro(coro):
    import asyncio
    loop = asyncio.SelectorEventLoop()  # Proactor self-pipe is sandbox-blocked (P-03)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def sam_prompt_mask(png_bytes, prompt_text, repeat=0, tag="prompt-v1"):
    """One SAM 3.1 Responses call with an explicit prompt (box string or concept text).
    Requests metadata.include_confidence="true". Returns decoded masks as row spans in
    image coords + per-mask confidence (None if the server did not emit it). Cached by
    image+prompt+repeat. No IoU here — callers compute it with geometry.py."""
    if open_weight_only(): return _open_blocked("SAM")
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    img_hash = hashlib.sha256(png_bytes).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key("sam-3.1-prompt", [{"img": img_hash, "prompt": prompt_text, "repeat": repeat}], extra=tag)
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    if not key:
        return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    try:
        out = _sam_prompt_run(key, png_bytes, prompt_text)
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

def _sam_prompt_run(key, png_bytes, prompt_text):
    import base64 as _b64
    from meta_sam_parser import parse_responses_stream, image_segmentation_format, decode_mask_to_raster
    data_url = "data:image/png;base64," + _b64.b64encode(png_bytes).decode()
    body = json.dumps({"model": "sam-3.1", "stream": True, "metadata": {"include_confidence": "true"}, "input": [
        {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt_text},
            {"type": "input_image", "image_url": data_url}]}]}).encode()
    req = urllib.request.Request(META_BASE.rstrip("/") + "/responses", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    events, completed = [], set()
    with urllib.request.urlopen(req, timeout=120) as r:
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
    async def agen():
        for e in events: yield e
    async def _get():
        return await parse_responses_stream(agen(), image_segmentation_format()).final_result()
    result = _run_coro(_get())
    masks = []
    import numpy as np
    for rec in getattr(result, "records", []) or []:
        try:
            raster = decode_mask_to_raster(rec.mask)
            b = rec.bounds; mw, mh = int(rec.mask.width), int(rec.mask.height)
            sub = np.frombuffer(raster, dtype=np.uint8).reshape(mh, mw)
            rows = []
            for yy in range(mh):
                xs_on = np.flatnonzero(sub[yy])
                if len(xs_on): rows.append([int(yy + int(b.top)), int(xs_on[0] + int(b.left)), int(xs_on[-1] + int(b.left))])
            masks.append({"rows": rows, "box": [int(b.left), int(b.top), int(b.right), int(b.bottom)],
                          "confidence": (float(rec.confidence) if getattr(rec, "confidence", None) is not None else None)})
        except Exception:
            continue
    if not masks:
        return {"status": "BLOCKED", "detail": "sam-3.1 returned zero masks", "masks": []}
    return {"status": "OK", "model": "sam-3.1", "masks": masks, "records": len(masks)}

def sam_upload_video(mp4_bytes, filename="clip.mp4"):
    """Files API upload (purpose=user_data) for SAM video. File id cached by content hash
    in data/api_cache/video_uploads.json (upload is not a model call; tracking is)."""
    if open_weight_only(): return _open_blocked("SAM video upload")
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not key: return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    CACHE.mkdir(parents=True, exist_ok=True)
    reg_path = CACHE / "video_uploads.json"
    reg = json.loads(reg_path.read_text()) if reg_path.exists() else {}
    digest = hashlib.sha256(mp4_bytes).hexdigest()
    if digest in reg: return {"status": "OK", "file_id": reg[digest], "_cache": "hit"}
    boundary = "----helpchoreai-video-boundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nuser_data\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: video/mp4\r\n\r\n").encode() + mp4_bytes + f"\r\n--{boundary}--\r\n".encode()
    try:
        resp = _post_multipart(META_BASE.rstrip("/") + "/files", key, body, f"multipart/form-data; boundary={boundary}", timeout=300)
        file_id = resp.get("id")
        if not (isinstance(file_id, str) and file_id.startswith("file-")):
            return {"status": "BLOCKED", "detail": f"Files API returned no file id: {str(resp)[:200]}"}
    except Exception as e:
        return {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    reg[digest] = file_id; reg_path.write_text(json.dumps(reg, indent=1))
    return {"status": "OK", "file_id": file_id, "_cache": "miss"}

def sam_track_video(file_id, mp4_bytes, prompt_text):
    """SAM 3.1 video tracking over a Responses stream (video_segmentation_format).
    Prompt text carries object prompts (frame = clip frame index); metadata requests
    confidence + forward propagation. Returns per-frame mask row spans keyed by
    (frame, object_id) + usage (incl. video_frames_processed). Cached by clip+prompt."""
    if open_weight_only(): return _open_blocked("SAM video")
    load_env()
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = _key("sam-3.1-video", [{"clip": hashlib.sha256(mp4_bytes).hexdigest(), "prompt": prompt_text}], extra="video-v1")
    hit = CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); out["_cache"] = "hit"; return out
    if _public():
        return {"status": "CACHE_ONLY", "detail": "PUBLIC_MODE: live calls disabled and no cached result", "_cache": "miss"}
    if not key:
        return {"status": "BLOCKED", "detail": "META_MODEL_API_KEY not set"}
    try:
        out = _sam_video_run(key, file_id, prompt_text)
    except Exception as e:
        out = {"status": "BLOCKED", "detail": f"{type(e).__name__}: {e}"}
    if out.get("status") == "OK":
        hit.write_text(json.dumps(out, indent=1))
    return out | {"_cache": "miss"}

def _sam_video_run(key, file_id, prompt_text):
    from meta_sam_parser import parse_responses_stream, video_segmentation_format, decode_mask_to_raster
    body = json.dumps({"model": "sam-3.1", "stream": True,
                       "metadata": {"include_confidence": "true", "propagation_direction": "forward"},
                       "input": [{"type": "message", "role": "user", "content": [
                           {"type": "input_text", "text": prompt_text},
                           {"type": "input_video", "file_id": file_id}]}]}).encode()
    req = urllib.request.Request(META_BASE.rstrip("/") + "/responses", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    events, completed, usage = [], set(), {}
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"): continue
            payload = line[5:].strip()
            if payload == "[DONE]": break
            try: data = json.loads(payload)
            except Exception: continue
            if isinstance(data.get("response"), dict) and isinstance(data["response"].get("usage"), dict):
                usage = data["response"]["usage"]
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
    async def agen():
        for e in events: yield e
    async def _get():
        return await parse_responses_stream(agen(), video_segmentation_format()).final_result()
    result = _run_coro(_get())
    import numpy as np
    records = []
    for rec in getattr(result, "records", []) or []:
        if getattr(rec, "kind", "mask") != "mask" or getattr(rec, "mask", None) is None: continue
        try:
            raster = decode_mask_to_raster(rec.mask)
            b = rec.bounds; mw, mh = int(rec.mask.width), int(rec.mask.height)
            sub = np.frombuffer(raster, dtype=np.uint8).reshape(mh, mw)
            rows = []
            for yy in range(mh):
                xs_on = np.flatnonzero(sub[yy])
                if len(xs_on): rows.append([int(yy + int(b.top)), int(xs_on[0] + int(b.left)), int(xs_on[-1] + int(b.left))])
            frame = getattr(rec, "frame", None)
            records.append({"frame": (int(frame.frame_index) if frame is not None else None),
                            "object_id": str(getattr(rec, "object_id", "")),
                            "rows": rows, "box": [int(b.left), int(b.top), int(b.right), int(b.bottom)],
                            "confidence": (float(rec.confidence) if getattr(rec, "confidence", None) is not None else None)})
        except Exception:
            continue
    records.sort(key=lambda r: (r["frame"] if r["frame"] is not None else -1, r["object_id"]))
    if not records:
        return {"status": "BLOCKED", "detail": "sam-3.1 video returned zero mask records", "records": []}
    return {"status": "OK", "model": "sam-3.1", "records": records, "usage": usage,
            "video_frames_processed": usage.get("video_frames_processed")}

def spark_visual_check(png_bytes):
    key = os.environ.get("META_MODEL_API_KEY")
    prompt = ("You are a research QC assistant. Look at this grayscale microfluidic red-blood-cell crop. "
              "Describe ONLY visible morphology (spicules, shape, image quality) in 2 short sentences. "
              "No numbers, no diagnosis, no treatment advice.")
    return chat_cached(META_BASE, key, "muse-spark-1.3", img_msg(prompt, png_bytes), extra=hashlib.sha256(png_bytes).hexdigest())

def spark_narrative(payload):
    if open_weight_only(): return baseten_narrative(payload)
    key = os.environ.get("META_MODEL_API_KEY")
    prompt = ("Write ONE short narrative sentence for a research audit report about a visit-to-visit change "
              "that was assessed against a combined measurement-and-protocol noise band. "
              "Rules: no digits, no numbers spelled out, no diagnosis, no disease-progression claim, "
              "no treatment advice. Decision category: " + str(payload.get("decision")) +
              ". Treatment context: " + str(payload.get("treatment")) + ".")
    return chat_cached(META_BASE, key, "muse-spark-1.3", [{"role": "user", "content": prompt}],
                       extra=json.dumps(payload, sort_keys=True))

def _parse_baseten_verdict(text):
    """Strict JSON verdict parse. Fail-closed: only an explicit PASS verdict passes."""
    try:
        obj = json.loads(str(text).strip())
    except Exception:
        return "BLOCK", ["unparseable auditor reply"]
    if not isinstance(obj, dict) or obj.get("verdict") not in ("PASS", "BLOCK"):
        return "BLOCK", ["auditor reply is not a strict PASS/BLOCK verdict"]
    reasons = obj.get("reasons")
    if not isinstance(reasons, list):
        return "BLOCK", ["auditor reasons missing or not a list"]
    return obj["verdict"], [str(r) for r in reasons]

def baseten_audit(report, payload):
    key = _open_key()
    prompt = ("You are a compliance auditor. Check this research report against its payload. "
              "Never flag these fixed template items: the pseudonymous patient code P1 to P5, week labels such as 8w, "
              "the dataset citation and its year, the licence name and version, the DOI, the disclaimer text, "
              "and any number that appears in the payload. "
              "Flag clinical advice, claims about disease state, disease progression or treatment effect, "
              "real patient identifiers such as names, hospital numbers or doctors, and any other number, "
              "including spelled-out numbers. "
              'Reply with strict JSON only: {"verdict": "PASS"|"BLOCK", "reasons": [...]}. '
              'Use "PASS" only if there are no flags; otherwise use "BLOCK".\nPAYLOAD: '
              + json.dumps(payload) + "\nREPORT:\n" + report)
    # Baseten serves meta-models/muse-spark-open; the -1026 ID 404s. Served model first. Other hosts: OPEN_MODEL only.
    r = {"status": "BLOCKED", "detail": "API key not set", "_cache": "miss"}
    for model in ([BASETEN_MODEL] if os.environ.get("OPEN_MODEL") else ["meta-models/muse-spark-open", "meta-models/muse-spark-open-1026"]):
        r = chat_cached(BASETEN_URL.rsplit("/chat/completions", 1)[0], key, model,
                        [{"role": "user", "content": prompt}])
        if r.get("status") == "OK":
            verdict, reasons = _parse_baseten_verdict(r.get("text", ""))
            return {"status": verdict, "verdict": verdict, "reasons": reasons,
                    "model": model, "detail": (r.get("text", "") or "")[:300], "_cache": r.get("_cache")}
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
    if open_weight_only(): return _open_blocked("voice")
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
    """Raster IoU on a w x h grid via geometry.fill_contour (the old ray caster over-filled)."""
    import geometry
    return geometry.iou(geometry.fill_contour(poly_a, h, w), geometry.fill_contour(poly_b, h, w))

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
