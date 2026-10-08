import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analytics"))
sys.path.insert(0, str(ROOT / "agents"))
import analytics as an  # noqa: E402
import story as st  # noqa: E402

N = 20
det = {"high_press": 0, "momentum_swing": 0, "big_chance": 0}
fp = 0
tot = {"claims_written": 0, "fake_claims": 0, "fake_caught": 0,
       "claims_published": 0, "claims_rejected": 0}

for n in range(1, N + 1):
    res = an.analyse(n)
    hits, f = an.evaluate(res, an.load_answer(n))
    for k, v in hits.items():
        det[k] += int(v)
    fp += f
    s = st.build_story(n, inject=True)
    for k in tot:
        tot[k] += s["totals"][k]

genuine = tot["claims_written"] - tot["fake_claims"]
wrongly_rejected = tot["claims_rejected"] - tot["fake_caught"]
fake_published = tot["fake_claims"] - tot["fake_caught"]

print(f"=== StoryDesk evaluation over {N} synthetic matches ===\n")
print("1) Detection of planted tactical events (ground truth known)")
for k, v in det.items():
    print(f"   {k:15s} {v}/{N}  ({100 * v / N:.0f}%)")
print(f"   false positives: {fp}\n")
print("2) Claim faithfulness (fake claims injected to simulate AI hallucination)")
print(f"   fake claims injected:            {tot['fake_claims']}")
print(f"   published WITHOUT verifier:      {tot['fake_claims']}  (hallucination rate {100 * tot['fake_claims'] / tot['claims_written']:.1f}% of all claims)")
print(f"   published WITH verifier:         {fake_published}  (hallucination rate {100 * fake_published / max(1, tot['claims_published']):.1f}% of published claims)")
print(f"   genuine claims written:          {genuine}")
print(f"   genuine claims wrongly rejected: {wrongly_rejected}")

(ROOT / "data" / "eval_results.json").write_text(json.dumps(
    {"matches": N, "detection": det, "false_positives": fp, "claims": tot,
     "fake_published_with_verifier": fake_published,
     "genuine_wrongly_rejected": wrongly_rejected}, indent=2))
