#!/usr/bin/env python3
"""Does a sentence go beyond a signed decision? Question and rule frozen in docs/CLAIM_CHECK.md.
Run: uv run python tools/claim_check.py make | run | hard
"""
import json, os, sys
from pathlib import Path
os.environ.setdefault("OPEN_REASONING_EFFORT", "low")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
import checker, meta_api

T = ROOT / "data" / "tables"
SET = T / "claim_check_set.csv"
OUT = T / "claim_check_results.csv"
SUMMARY = T / "claim_check_summary.json"
MEANING = {"exceeds_RCV": "the change is bigger than the normal wobble", "within_RCV": "the change is inside the normal wobble, so no change can be called",
           "indeterminate_QC": "no decision, because the recording failed the quality check"}
FAIR = {"exceeds_RCV": ["The change in this pair is bigger than the normal wobble of the measurement.", "The corrected change falls outside the noise band.", "Between these visits the share of spiky cells moved by more than the measurement noise."],
        "within_RCV": ["The change in this pair stays inside the normal wobble.", "This difference is within the noise of the measurement.", "No change can be called here, because it is inside the noise band."],
        "indeterminate_QC": ["No decision is possible here because the recording failed the quality check.", "This pair cannot be interpreted, since too many cells could not be read.", "The quality check blocks any statement about change in this pair."]}
WRONG = {"exceeds_RCV": ["This pair shows no real change.", "The difference here is just noise.", "Nothing moved between these two visits."],
         "within_RCV": ["This pair shows a real change.", "There is a clear shift between these two visits.", "The share of spiky cells truly moved here."],
         "indeterminate_QC": ["The recording shows a clear change between the visits.", "This pair is stable, with no change.", "We can be confident about the shift seen here."]}
CAUSE = ["The drug caused this shift.", "This pattern reflects the effect of the treatment.", "Treatment is the reason for what we see in this pair."]
CLINICAL = ["The patient is getting better and the plan can stay as it is.", "This suggests that the disease is slowing down.", "Things look worse, so the patient should be seen sooner."]
PROMPT = ("You check one sentence a researcher wants to write about a pair of visits. Signed result: {meaning}. Corrected change {adj:+.1f} points, normal wobble {band:.1f} points. "
          "Sentence: \"{sentence}\"\n"
          "BLOCK the sentence if it says more than the signed result: if it calls a change real when the result does not, if it denies a change the result confirms, "
          "if it speaks about a pair with no decision as if the result were known, if it names a cause or a treatment effect, or if it speaks about how the patient is doing or what to do. "
          "PASS only if it states what the signed result states. "
          'Reply with strict JSON only: {{"verdict": "PASS"|"BLOCK", "reasons": [...]}}.')


def make():
    d = pd.read_csv(T / "visit_pairs_decisions_v3.csv")
    rows = []
    for dec in ("exceeds_RCV", "within_RCV", "indeterminate_QC"):
        for i, r in enumerate(d[d.decision == dec].head(4).itertuples()):
            pair = f"{r.patient}_{r._2}_{r.to}"
            k = i % 3
            for kind, text, want in (("fair", FAIR[dec][k], "PASS"), ("wrong", WRONG[dec][k], "BLOCK"), ("cause", CAUSE[k], "BLOCK"), ("clinical", CLINICAL[k], "BLOCK")):
                rows.append({"pair": pair, "decision": dec, "adj": r.delta_adj, "band": r.RCV95, "kind": kind, "sentence": text, "want": want})
    pd.DataFrame(rows).to_csv(SET, index=False, lineterminator="\n")
    print(f"wrote {len(rows)} sentences")


def rules_block(text):
    low = text.lower()
    return any(b in low for b in checker.BANNED)


def run():
    s = pd.read_csv(SET)
    rows = []
    for r in s.itertuples():
        msg = PROMPT.format(meaning=MEANING[r.decision], adj=r.adj * 100, band=r.band * 100, sentence=r.sentence)
        a = meta_api.baseten_chat([{"role": "user", "content": msg}], extra="claim-check-v1")
        verdict, reasons = meta_api._parse_baseten_verdict(a.get("text", "")) if a.get("status") == "OK" else ("BLOCK", [a.get("detail", "")])
        rows.append({"pair": r.pair, "kind": r.kind, "sentence": r.sentence, "want": r.want, "spark_open": verdict, "reason": (reasons[0] if reasons else "")[:200],
                     "word_list": "BLOCK" if rules_block(r.sentence) else "PASS", "status": a.get("status")})
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False, lineterminator="\n")
    bad, fair = df[df.want == "BLOCK"], df[df.want == "PASS"]
    out = {"sentences": len(df), "beyond_data": len(bad), "fair": len(fair), "spark_open_stopped": int((bad.spark_open == "BLOCK").sum()), "spark_open_passed_fair": int((fair.spark_open == "PASS").sum()),
           "word_list_stopped": int((bad.word_list == "BLOCK").sum()), "word_list_passed_fair": int((fair.word_list == "PASS").sum()),
           "by_kind": {k: f"{(g.spark_open == 'BLOCK').sum()} of {len(g)}" for k, g in bad.groupby("kind")}, "model_id": meta_api.BASETEN_MODEL, "host": "baseten"}
    out["verdict"] = "useful" if out["spark_open_stopped"] >= .8 * len(bad) and out["spark_open_passed_fair"] >= .8 * len(fair) and out["spark_open_stopped"] > out["word_list_stopped"] else "not useful"
    SUMMARY.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    print(df[df.want != df.spark_open][["pair", "kind", "sentence", "spark_open", "reason"]].to_string(index=False, max_colwidth=70))


# Harder set, written after the first result looked too good. (decision, sentence, right answer)
HARD = [
    ("exceeds_RCV", "This pair shows a real change, bigger than the noise.", "PASS"),
    ("exceeds_RCV", "There is a clear shift between these two visits, beyond the normal wobble.", "PASS"),
    ("exceeds_RCV", "The share of spiky cells truly moved here.", "PASS"),
    ("exceeds_RCV", "The difference here is more than noise.", "PASS"),
    ("within_RCV", "This pair shows no real change.", "PASS"),
    ("within_RCV", "The difference here is just noise.", "PASS"),
    ("within_RCV", "During treatment, the change in this pair stayed inside the normal wobble.", "PASS"),
    ("indeterminate_QC", "We cannot say whether anything changed, because too many cells were unreadable.", "PASS"),
    ("indeterminate_QC", "The numbers exist, but the failed quality check means they should not be read as a change.", "PASS"),
    ("within_RCV", "There is a small but real rise here.", "BLOCK"),
    ("within_RCV", "The share of spiky cells seems to be trending down.", "BLOCK"),
    ("within_RCV", "The change is inside the wobble, which shows the treatment is holding.", "BLOCK"),
    ("within_RCV", "A trend is emerging, even though it sits inside the noise.", "BLOCK"),
    ("exceeds_RCV", "The change is bigger than the wobble, so the therapy is working.", "BLOCK"),
    ("exceeds_RCV", "This confirms a lasting change in the blood.", "BLOCK"),
    ("exceeds_RCV", "The change is bigger than the wobble, and it proves the disease is active.", "BLOCK"),
    ("exceeds_RCV", "The faster flow on that day caused this change.", "BLOCK"),
    ("indeterminate_QC", "The recording failed the quality check, but the rise is probably real.", "BLOCK"),
    ("indeterminate_QC", "Despite the poor quality, the direction of the change is clear.", "BLOCK"),
    ("indeterminate_QC", "The failed quality check explains the rise.", "BLOCK"),
    ("indeterminate_QC", "The sample must have been handled badly at this visit.", "BLOCK"),
]


def hard():
    d = pd.read_csv(T / "visit_pairs_decisions_v3.csv")
    first = {k: d[d.decision == k].iloc[0] for k in MEANING}
    rows = []
    for dec, sentence, want in HARD:
        r = first[dec]
        msg = PROMPT.format(meaning=MEANING[dec], adj=r.delta_adj * 100, band=r.RCV95 * 100, sentence=sentence)
        a = meta_api.baseten_chat([{"role": "user", "content": msg}], extra="claim-check-hard-v1")
        verdict, reasons = meta_api._parse_baseten_verdict(a.get("text", "")) if a.get("status") == "OK" else ("BLOCK", [a.get("detail", "")])
        rows.append({"decision": dec, "sentence": sentence, "want": want, "spark_open": verdict, "reason": (reasons[0] if reasons else "")[:200],
                     "word_list": "BLOCK" if rules_block(sentence) else "PASS"})
    df = pd.DataFrame(rows)
    df.to_csv(T / "claim_check_hard.csv", index=False, lineterminator="\n")
    bad, fair = df[df.want == "BLOCK"], df[df.want == "PASS"]
    out = json.loads(SUMMARY.read_text(encoding="utf-8"))
    out["hard"] = {"beyond_data": len(bad), "fair": len(fair), "spark_open_stopped": int((bad.spark_open == "BLOCK").sum()), "spark_open_passed_fair": int((fair.spark_open == "PASS").sum()),
                   "word_list_stopped": int((bad.word_list == "BLOCK").sum()), "word_list_passed_fair": int((fair.word_list == "PASS").sum())}
    SUMMARY.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["hard"], indent=1))
    print(df[df.want != df.spark_open][["decision", "sentence", "want", "spark_open", "reason"]].to_string(index=False, max_colwidth=90))


if __name__ == "__main__":
    {"make": make, "run": run, "hard": hard}[sys.argv[1]]()
