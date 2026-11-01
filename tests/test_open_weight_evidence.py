"""An audit must be about the committed report, and open runs must verify from tracked files."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import agent, agent_tools, checker, meta_api

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "logs" / "agent_runs"
EVID = ROOT / "logs" / "open_weight_runs" / "agent_runs"


def test_audit_files_match_committed_reports():
    for f in RUNS.glob("*/open_weight_audit.json"):
        env = json.loads((f.parent / "envelope.json").read_text(encoding="utf-8"))
        assert json.loads(f.read_text(encoding="utf-8"))["report_sha256"] == env["payload"]["report_sha256"], f.parent.name


def test_open_runs_verify_and_match_cloud_numbers():
    for d in (EVID.iterdir() if EVID.exists() else []):
        env = json.loads((d / "envelope.json").read_text(encoding="utf-8"))
        cloud = json.loads((RUNS / d.name / "envelope.json").read_text(encoding="utf-8"))
        assert checker.verify_envelope(env, report_text=(d / "report.md").read_text(encoding="utf-8"))[0], d.name
        assert env["payload"]["payload_sha256"] == cloud["payload"]["payload_sha256"], d.name


@pytest.mark.parametrize("text", ["The later visit exceeds the predefined acceptance threshold, so no decision is made.",
                                  "Elevated skip rates exceeding the limit block the comparison."])
def test_skip_rate_wording_is_not_a_change_claim(text):
    assert agent_tools.re.search(agent_tools.DECISION_CLAIM, text.lower()) is None


@pytest.mark.parametrize("text", ["A real change exceeds the combined noise band.",
                                  "The change exceeds the threshold.",
                                  "The drop exceeded the reference change band."])
def test_change_claims_are_still_caught(text):
    assert agent_tools.re.search(agent_tools.DECISION_CLAIM, text.lower()) is not None


def _call(i, name, **args):
    return {"id": f"c{i}", "function": {"name": name, "arguments": json.dumps(args)}}


def test_every_tool_call_in_one_message_is_answered(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPCHORE_AGENT_TRAIL", str(tmp_path / "trail.jsonl"))
    monkeypatch.setattr(agent, "LOGS", tmp_path)
    seen = []

    def model(messages):
        seen.append([m for m in messages if m.get("role") == "tool"])
        if len(seen) == 1:
            return {"role": "assistant", "content": None, "tool_calls": [
                _call(1, "pair_stats", patient="P1", from_visit="0w", to_visit="2w"),
                _call(2, "qc_gate", patient="P1", from_visit="0w", to_visit="2w")]}
        return {"role": "assistant", "content": None, "tool_calls": [
            _call(3, "render_and_sign", patient="P1", from_visit="0w", to_visit="2w", narrative="x")]}

    agent.run_pair("P1", "0w", "2w", model_fn=model)
    assert [m["name"] for m in seen[1]] == ["pair_stats", "qc_gate"]
    assert "tool_budget_left" in json.loads(seen[1][0]["content"])


def test_repeat_inspection_is_answered_without_a_refusal():
    agent_tools.begin_run("t")
    first = agent_tools.call_tool("rater_summary", {"patient": "P1", "visit": "10w"})
    again = agent_tools.call_tool("rater_summary", {"patient": "P1", "visit": "10w"})
    assert first.get("status") != "ALREADY_INSPECTED"
    assert again["status"] == "ALREADY_INSPECTED"


def test_open_model_settings_reach_the_request(monkeypatch, tmp_path):
    sent = {}
    monkeypatch.setattr(meta_api, "CACHE", tmp_path)
    monkeypatch.setenv("BASETEN_API_KEY", "test-key")
    monkeypatch.setenv("OPEN_REASONING_EFFORT", "low")
    monkeypatch.setenv("OPEN_WEIGHT_ONLY", "1")

    def fake(url, key, body, timeout=60):
        sent.update(body)
        return {"id": "x", "choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(meta_api, "_post", fake)
    assert meta_api.baseten_chat([{"role": "user", "content": "effort test ping"}], extra="effort-test")["status"] in ("OK",)
    assert sent.get("reasoning_effort") == "low"
