"""P-10 offline tests with a mock model (no network, no keys)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import agent, agent_tools


def _call(name, **args):
    return {"tool_calls": [{"id": f"c{name}", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _scripted(script):
    state = {"i": 0}
    def chat(messages):
        step = script[min(state["i"], len(script) - 1)]; state["i"] += 1
        return step(messages) if callable(step) else step
    return chat


def test_tools_sealed_and_no_labels_or_sealed_patients():
    out = agent_tools.pair_stats("P1", "0w", "2w")
    assert out["status"] == "OK" and len(out["sha256"]) == 64 and out["decision"]
    cells = agent_tools.sample_cells("P1", "0w", 3)
    assert cells["status"] == "OK" and all("health" not in c for c in cells["cells"])
    assert agent_tools.list_pairs("P3")["status"] == "ERROR"
    assert agent_tools.pair_stats("P5", "0w", "2w")["status"] == "ERROR"


def test_planted_unverified_number_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPCHORE_AGENT_TRAIL", str(tmp_path / "trail.jsonl"))
    mock = _scripted([
        _call("pair_stats", patient="P1", from_visit="0w", to_visit="2w"),
        _call("render_and_sign", patient="P1", from_visit="0w", to_visit="2w",
              narrative="The fraction rose by 42 percent since baseline."),
        _call("render_and_sign", patient="P1", from_visit="0w", to_visit="2w",
              narrative="Flow standardized change assessed against the combined noise band."),
    ])
    res = agent.run_pair("P1", "0w", "2w", model_fn=mock)
    assert res["status"] == "AWAITING_SIGNOFF" and res["rejections"] == 1 and res["tool_calls"] == 3
    direct = agent_tools.render_and_sign("P1", "0w", "2w", "An increase of ninety nine units was seen.")
    assert direct["status"] == "REJECTED_UNVERIFIED_NUMBER" and "42" not in direct["feedback"]


def test_three_rejections_need_human(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPCHORE_AGENT_TRAIL", str(tmp_path / "trail.jsonl"))
    bad = _call("render_and_sign", patient="P1", from_visit="0w", to_visit="2w",
                narrative="The fraction rose by 42 percent since baseline.")
    res = agent.run_pair("P1", "0w", "2w", model_fn=_scripted([bad]))
    assert res["status"] == "NEEDS_HUMAN" and res["rejections"] == 3


def test_verify_cli_reruns_checks(tmp_path, monkeypatch, capsys):
    trail = tmp_path / "trail.jsonl"
    monkeypatch.setenv("HELPCHORE_AGENT_TRAIL", str(trail))
    mock = _scripted([
        _call("pair_stats", patient="P1", from_visit="0w", to_visit="2w"),
        _call("render_and_sign", patient="P1", from_visit="0w", to_visit="2w",
              narrative="Flow standardized change assessed against the combined noise band."),
    ])
    res = agent.run_pair("P1", "0w", "2w", model_fn=mock)
    assert res["status"] == "AWAITING_SIGNOFF"
    assert agent.main(["verify", res["run_id"]]) == 0
    assert "VERIFIED" in capsys.readouterr().out
