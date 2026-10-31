#!/usr/bin/env python3
"""Re-sign all 21 committed pairs with the existing key (P-21).

Reuses the narrative already in each report.md. For a narrative now refused
(new BANNED phrases), makes at most one Spark call per refused pair and at
most 3 new (cache-miss) Spark calls in total; if still refused, falls back
to the template narrative and records narrative_source=template in the new
chained trail. Asserts payload_sha256 is unchanged for 21 of 21 pairs.
Run: uv run python tools/resign_reports.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import agent, agent_tools, checker, meta_api

ROOT = Path(__file__).parent.parent
TEMPLATE = "Flow standardized change assessed against the combined noise band."
MAX_NEW_SPARK_CALLS = 3


def _narrative_of(report_text: str) -> str:
    for line in report_text.splitlines():
        if line.startswith("Narrative: "):
            return line[len("Narrative: "):].strip()
    return ""


def main() -> int:
    runs = ROOT / "logs" / "agent_runs"
    pairs = []
    for d in sorted(runs.iterdir()):
        env_f = d / "envelope.json"
        if env_f.exists():
            env = json.loads(env_f.read_text(encoding="utf-8"))
            p = env["payload"]
            pairs.append((p["patient"], p["from_visit"], p["to_visit"], env["payload"]["payload_sha256"]))
    assert len(pairs) == 21, f"expected 21 committed pairs, found {len(pairs)}"
    new_spark_calls = 0
    unchanged = 0
    for patient, frm, to, old_payload_sha in pairs:
        run_id = f"{patient}_{frm}_{to}"
        d = runs / run_id
        narrative = _narrative_of((d / "report.md").read_text(encoding="utf-8"))
        source = "cached"
        out = agent_tools.render_and_sign(patient, frm, to, narrative)
        if out.get("status") != "PASS":
            # Narrative now refused: at most one Spark attempt for this pair,
            # and at most MAX_NEW_SPARK_CALLS cache misses in total.
            payload = checker.build_payload(patient, frm, to)
            spark = meta_api.spark_narrative(payload)
            if spark.get("_cache") == "miss" and spark.get("status") == "OK":
                new_spark_calls += 1
            cand = (spark.get("text") or "").strip() if spark.get("status") == "OK" else ""
            if cand and new_spark_calls <= MAX_NEW_SPARK_CALLS:
                out2 = agent_tools.render_and_sign(patient, frm, to, cand)
                if out2.get("status") == "PASS":
                    out, narrative, source = out2, cand, f"muse-spark-1.3 ({spark.get('_cache')})"
            if out.get("status") != "PASS":
                out = agent_tools.render_and_sign(patient, frm, to, TEMPLATE)
                narrative, source = TEMPLATE, "template"
        assert out.get("status") == "PASS", (run_id, out)
        env = out["envelope"]
        assert env["payload"]["payload_sha256"] == old_payload_sha, f"payload changed for {run_id}"
        unchanged += 1
        (d / "report.md").write_bytes(out["report"].replace("\r\n", "\n").encode())
        (d / "envelope.json").write_bytes((json.dumps(env, indent=1) + "\n").encode())
        agent._log(run_id, "tool", {"tool": "render_and_sign",
                                    "input": {"patient": patient, "from_visit": frm, "to_visit": to,
                                              "narrative": narrative},
                                    "output": out})
        agent._log(run_id, "final", {"input": {"patient": patient, "from_visit": frm, "to_visit": to},
                                     "output": {"status": "AWAITING_SIGNOFF",
                                                "narrative_source": source,
                                                "report_sha256": out["report_sha256"]}})
        print(f"{run_id}: re-signed narrative_source={source}")
    # Committed checker example: no narrative, report text is the .md file.
    ex = checker.sign_payload(checker.build_payload("P1", "0w", "2w"), "")
    (ROOT / "data" / "checker" / "example_report_P1_0w_2w.json").write_bytes(
        (json.dumps(ex, indent=1) + "\n").encode())
    (ROOT / "data" / "checker" / "example_report_P1_0w_2w.md").write_bytes(
        checker.render_report(ex).replace("\r\n", "\n").encode())
    print(f"payload_sha256 unchanged: {unchanged}/21 pairs; new Spark calls: {new_spark_calls}")
    assert unchanged == 21
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
