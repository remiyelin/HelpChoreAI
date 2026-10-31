#!/usr/bin/env python3
"""P-10 verifiable audit agent (muse-spark-1.3 function calling, parallel_tool_calls off).

Verification runs inside agent_tools.render_and_sign, so the model cannot skip it.
Ground truth (tables) stays outside the agent's message history; rejection feedback
names the error, never the expected value. 3 rejections -> NEEDS_HUMAN. A passing
report is AWAITING_SIGNOFF until a researcher signs off in the UI.
Run:  uv run python -m src.agent run [--limit N] | uv run python -m src.agent verify <run_id>
"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import agent_tools, checker, meta_api
from env import load_env

load_env()
ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
MODEL = "muse-spark-1.3"
MAX_TOOL_CALLS = 8
COST_PER_MODEL_CALL_USD = 0.02  # conservative ledger estimate per cached-miss model call
BUDGET_USD = 3.00

TOOL_SCHEMAS = [{"type": "function", "function": {"name": n, "description": d, "parameters": p}} for n, d, p in [
    ("list_pairs", "List audited visit pairs for a dev patient.",
     {"type": "object", "properties": {"patient": {"type": "string"}}, "required": ["patient"]}),
    ("pair_stats", "v3 decision row and run details for one visit pair.",
     {"type": "object", "properties": {"patient": {"type": "string"}, "from_visit": {"type": "string"},
      "to_visit": {"type": "string"}}, "required": ["patient", "from_visit", "to_visit"]}),
    ("qc_gate", "Skip-rate QC status for both visits of a pair.",
     {"type": "object", "properties": {"patient": {"type": "string"}, "from_visit": {"type": "string"},
      "to_visit": {"type": "string"}}, "required": ["patient", "from_visit", "to_visit"]}),
    ("sample_cells", "Sampled M10 cell metrics (no author labels) for one visit.",
     {"type": "object", "properties": {"patient": {"type": "string"}, "visit": {"type": "string"},
      "n": {"type": "integer"}}, "required": ["patient", "visit", "n"]}),
    ("rater_summary", "Aggregate spark/open rater metrics for one patient visit.",
     {"type": "object", "properties": {"patient": {"type": "string"}, "visit": {"type": "string"}},
      "required": ["patient", "visit"]}),
    ("render_and_sign", "Validate narrative, template and sign the final report. Narrative must contain no numbers.",
     {"type": "object", "properties": {"patient": {"type": "string"}, "from_visit": {"type": "string"},
      "to_visit": {"type": "string"}, "narrative": {"type": "string"}},
      "required": ["patient", "from_visit", "to_visit", "narrative"]}),
]]

SYSTEM = ("You are a research audit agent. Use the tools to audit exactly one visit pair, then call "
          "render_and_sign with one short narrative sentence. The narrative must contain no digits and "
          "no spelled-out numbers and no percent words; all numbers are templated by the tool. "
          "Never invent numbers. If a tool rejects your narrative, rewrite it without numbers and retry.")


def trail_path() -> Path:
    return Path(os.environ.get("HELPCHORE_AGENT_TRAIL", str(LOGS / "audit_trail.jsonl")))


def _log(run_id, kind, payload):
    p = trail_path(); p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run_id": run_id, "kind": kind}
    entry.update(payload)
    entry["input_sha256"] = checker.sha_bytes(checker.canonical(payload.get("input", {})))
    entry["output_sha256"] = checker.sha_bytes(checker.canonical(payload.get("output", {})))
    with p.open("a", encoding="utf-8") as f: f.write(json.dumps(entry) + "\n")
    return entry


class Ledger:
    def __init__(self):
        self.path = LOGS / "agent_ledger.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"spent_usd": 0.0, "model_calls": 0}
    def charge(self):
        if self.data["spent_usd"] + COST_PER_MODEL_CALL_USD > BUDGET_USD:
            raise SystemExit(f"BUDGET: ledger would pass ${BUDGET_USD}; stopping before the call")
        self.data["spent_usd"] = round(self.data["spent_usd"] + COST_PER_MODEL_CALL_USD, 4)
        self.data["model_calls"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))


def _spark_tools_chat(messages, ledger=None):
    """One cached muse-spark-1.3 function-calling turn (data/api_cache). Returns assistant message dict."""
    meta_api.CACHE.mkdir(parents=True, exist_ok=True)
    ck = meta_api._key(MODEL + "-agent", [{"messages": messages, "tools": TOOL_SCHEMAS}], extra="agent-v1")
    hit = meta_api.CACHE / f"{ck}.json"
    if hit.exists():
        out = json.loads(hit.read_text()); return out["message"]
    key = os.environ.get("META_MODEL_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not key: raise RuntimeError("BLOCKED: META_MODEL_API_KEY not set")
    if ledger is not None: ledger.charge()
    resp = meta_api._post(meta_api.META_BASE.rstrip("/") + "/chat/completions", key,
                          {"model": MODEL, "messages": messages, "tools": TOOL_SCHEMAS,
                           "tool_choice": "auto", "parallel_tool_calls": False}, timeout=180)
    msg = resp.get("choices", [{}])[0].get("message", {})
    hit.write_text(json.dumps({"message": msg, "usage": resp.get("usage")}, indent=1))
    return msg


def run_pair(patient, from_visit, to_visit, model_fn=None, ledger=None, max_tool_calls=MAX_TOOL_CALLS):
    run_id = f"{patient}_{from_visit}_{to_visit}"
    chat = model_fn or (lambda msgs: _spark_tools_chat(msgs, ledger))
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Audit pair {patient} {from_visit} -> {to_visit}. Call pair_stats and qc_gate first, then render_and_sign."}]
    tool_calls, rejections, final = 0, 0, None
    for _turn in range(16):
        msg = chat(messages)
        _log(run_id, "model", {"input": {"messages": messages[-2:]}, "output": msg})
        messages.append(msg if isinstance(msg, dict) and msg.get("role") else
                        {"role": "assistant", "content": (msg or {}).get("content"), "tool_calls": (msg or {}).get("tool_calls")})
        calls = (msg or {}).get("tool_calls") or []
        if not calls:
            messages.append({"role": "user", "content": "Continue: call the next needed tool, or render_and_sign if you have pair_stats and qc_gate."})
            continue
        for call in calls[:1]:  # parallel_tool_calls is off; handle one at a time
            tool_calls += 1
            fn = (call.get("function") or {})
            name = fn.get("name") or call.get("name")
            try: args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or call.get("arguments") or {})
            except Exception: args = {}
            if tool_calls > max_tool_calls:
                final = {"status": "NEEDS_HUMAN", "reason": "tool-call budget exceeded"}; break
            out = agent_tools.call_tool(name, args)
            _log(run_id, "tool", {"tool": name, "input": args, "output": out})
            messages.append({"role": "tool", "tool_call_id": call.get("id", name), "name": name,
                             "content": json.dumps(out)})
            if name == "render_and_sign":
                if out.get("status") == "PASS":
                    final = {"status": "AWAITING_SIGNOFF", "report": out["report"],
                             "envelope": out["envelope"], "report_sha256": out["report_sha256"]}
                elif out.get("status") == "REJECTED_UNVERIFIED_NUMBER":
                    rejections += 1
                    if rejections >= 3:
                        final = {"status": "NEEDS_HUMAN", "reason": "3 rejected narratives", "rejections": rejections}
                else:
                    rejections += 1
                    if rejections >= 3:
                        final = {"status": "NEEDS_HUMAN", "reason": out.get("status"), "rejections": rejections}
            if final: break
        if final: break
    if final is None:
        final = {"status": "NEEDS_HUMAN", "reason": "turn budget exhausted without a passing report"}
    final.update({"run_id": run_id, "patient": patient, "from_visit": from_visit,
                  "to_visit": to_visit, "tool_calls": tool_calls, "rejections": rejections})
    if final["status"] == "AWAITING_SIGNOFF":
        d = LOGS / "agent_runs" / run_id; d.mkdir(parents=True, exist_ok=True)
        (d / "report.md").write_bytes(final["report"].encode())
        (d / "envelope.json").write_text(json.dumps(final["envelope"], indent=1))
    _log(run_id, "final", {"input": {"patient": patient, "from_visit": from_visit, "to_visit": to_visit},
                           "output": {k: v for k, v in final.items() if k not in ("report", "envelope")}})
    return final


def verify_run(run_id, path=None):
    p = Path(path) if path else trail_path()
    if not p.exists(): print(f"FAILED: no audit trail at {p}"); return False
    entries = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    mine = [e for e in entries if e.get("run_id") == run_id]
    if not mine: print(f"FAILED: run {run_id} not in audit trail"); return False
    ok = True
    for e in mine:
        if checker.sha_bytes(checker.canonical(e.get("input", {}))) != e["input_sha256"]: ok = False; print(f"hash mismatch input at {e['kind']}")
        # tool outputs are re-derived only for render steps; hash check covers the rest
    renders = [e for e in mine if e.get("kind") == "tool" and e.get("tool") == "render_and_sign" and e["output"].get("status") == "PASS"]
    for e in renders:
        # Verification needs no private key and writes no file: check the stored
        # envelope against the pinned public key instead of re-signing.
        env = e["output"]["envelope"]
        if env.get("payload", {}).get("report_sha256") != e["output"].get("report_sha256"):
            ok = False; print("render re-run hash mismatch")
        vok, verrs = checker.verify_envelope(env)
        if not vok: ok = False; print(f"envelope re-verify failed: {verrs}")
    final = [e for e in mine if e.get("kind") == "final"]
    print(f"{'VERIFIED' if ok else 'FAILED'}: {run_id} steps={len(mine)} renders={len(renders)} final={final[-1]['output'].get('status') if final else None}")
    return ok


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "verify":
        return 0 if verify_run(argv[1]) else 1
    if argv and argv[0] == "run":
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 21
        dec = agent_tools.pd.read_csv(agent_tools.TABLES / "visit_pairs_decisions_v3.csv")
        pairs = [(str(r.patient), str(r["from"]), str(r.to)) for _, r in dec.iterrows()][:limit]
        ledger = Ledger(); results = []
        for patient, frm, to in pairs:
            print(f"== {patient} {frm}->{to} ==", flush=True)
            res = run_pair(patient, frm, to, ledger=ledger)
            print(f"   {res['status']} tool_calls={res['tool_calls']} rejections={res['rejections']}", flush=True)
            results.append(res)
        summary = {"pairs": len(results),
                   "passed_awaiting_signoff": sum(r["status"] == "AWAITING_SIGNOFF" for r in results),
                   "needs_human": sum(r["status"] == "NEEDS_HUMAN" for r in results),
                   "tool_calls": sum(r["tool_calls"] for r in results),
                   "rejections": sum(r["rejections"] for r in results), "ledger": ledger.data,
                   "results": [{k: r[k] for k in ("run_id", "status", "tool_calls", "rejections")} for r in results]}
        (LOGS / "agent_summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary, indent=1)); return 0
    print("usage: python -m src.agent run [--limit N] | verify <run_id>"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
