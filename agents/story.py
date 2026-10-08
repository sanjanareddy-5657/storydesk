import json
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analytics"))
import analytics as an  # noqa: E402

DATA = Path("data")
NAME = an.TEAM_NAMES
OPP = an.OPP


# ---------------------------------------------------------------- evidence pack
def evidence_pack(events, moment, stats):
    by_id = {e["id"]: e for e in events}
    sample = [by_id[i] for i in moment["evidence"][:8] if i in by_id]
    return {"moment": moment, "sample_events": sample, "match_stats": stats}


# ---------------------------------------------------------------- narrator
def template_narrate(pack):
    """Offline narrator. Same output format as the AI narrator, so the pipeline always runs."""
    m = pack["moment"]
    team, opp = NAME[m["team"]], NAME[OPP[m["team"]]]
    ev = m["evidence"]
    t = m["type"]
    if t == "high_press":
        a, b, mt = m["start_minute"], m["end_minute"], m["metric"]
        return {
            "headline": f"{team} turn up the pressure from minute {a}",
            "claims": [
                {"text": f"{team} made {len(ev)} pressure actions deep in {opp}'s half between minute {a} and {b}.",
                 "evidence_ids": ev},
                {"text": f"That is {mt['deep_pressures_per_min']} deep pressures per minute, against a match average of {mt['match_baseline_per_min']}.",
                 "evidence_ids": ev[:3]},
            ]}
    if t == "momentum_swing":
        a, b, mt = m["start_minute"], m["end_minute"], m["metric"]
        pct = round(mt["avg_event_share"] * 100)
        return {
            "headline": f"Momentum swings to {team}",
            "claims": [
                {"text": f"{team} had {pct}% of all match events between minute {a} and {b}.",
                 "evidence_ids": ev},
                {"text": f"They created {mt['shots']} shots worth {mt['xg']} xG in that spell.",
                 "evidence_ids": ev},
            ]}
    if t == "big_chance":
        mt = m["metric"]
        res = "scored" if mt["outcome"] == "goal" else "missed"
        return {
            "headline": f"Big chance for {team} in minute {m['minute']}",
            "claims": [
                {"text": f"{mt['player']} had a {mt['xg']} xG chance in minute {m['minute']} and {res}.",
                 "evidence_ids": ev},
            ]}
    return {"headline": f"{team} goal in minute {m['minute']}",
            "claims": [{"text": f"{m['metric']['player']} scored in minute {m['minute']} from a {m['metric']['xg']} xG chance.",
                        "evidence_ids": ev}]}


SYSTEM_PROMPT = (
    "You are a football match analyst writing for a broadcast studio. "
    "You get ONE key moment with its evidence. Explain why it matters in 1-3 short claims. "
    "Use ONLY numbers, minutes, teams and players that appear in the input. "
    "Every claim must list evidence_ids taken from moment.evidence. "
    'Reply with JSON only: {"headline": str, "claims": [{"text": str, "evidence_ids": [str]}]}'
)


def ai_available():
    return all(os.getenv(k) for k in ("AZURE_OAI_ENDPOINT", "AZURE_OAI_KEY", "AZURE_OAI_DEPLOYMENT"))


def ai_narrate(pack):
    from openai import AzureOpenAI  # pip install openai
    client = AzureOpenAI(azure_endpoint=os.environ["AZURE_OAI_ENDPOINT"],
                         api_key=os.environ["AZURE_OAI_KEY"],
                         api_version=os.getenv("AZURE_OAI_API_VERSION", "2024-12-01-preview"))
    slim = {"moment": pack["moment"], "sample_events": pack["sample_events"]}
    resp = client.chat.completions.create(
        model=os.environ["AZURE_OAI_DEPLOYMENT"],
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": json.dumps(slim)}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def narrate(pack):
    if ai_available():
        try:
            return ai_narrate(pack)
        except Exception as ex:  # recovery: fall back so the pipeline never stops
            print("  [narrator] AI call failed, using template:", ex)
    return template_narrate(pack)


# ---------------------------------------------------------------- hallucination simulator (for eval)
def inject_fake_claim(story, moment, rnd):
    """Simulate an AI hallucination: wrong number and an evidence ID that does not exist."""
    team = NAME[moment["team"]]
    fake_n = rnd.randint(111, 199)
    # half the time cite a fake event ID, half the time cite a REAL one but with a wrong number
    ids = ["E99999"] if rnd.random() < 0.5 else moment["evidence"][:2]
    story["claims"].append({
        "text": f"{team} made {fake_n} dangerous touches in the box in this period.",
        "evidence_ids": ids, "_fake": True})
    return story


# ---------------------------------------------------------------- verifier
NUM = re.compile(r"\d+(?:\.\d+)?")
IDS = re.compile(r"\b(?:[A-Z]{3}_\d+|E\d{5})\b")  # player IDs / event IDs are names, not numbers


def allowed_numbers(moment, by_id):
    nums = set()

    def add(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.add(round(float(v), 2))

    for k in ("minute", "start_minute", "end_minute"):
        add(moment.get(k))
    add(len(moment["evidence"]))
    for v in moment["metric"].values():
        add(v)
    share = moment["metric"].get("avg_event_share")
    if share is not None:
        add(round(share * 100))
    for i in moment["evidence"]:
        e = by_id.get(i)
        if e:
            add(e["minute"])
            add(e.get("xg"))
    return nums


def verify(story, moment, events):
    by_id = {e["id"]: e for e in events}
    ok_nums = allowed_numbers(moment, by_id)
    good, bad = [], []
    for c in story["claims"]:
        reason = None
        ids = c.get("evidence_ids", [])
        if not ids:
            reason = "no evidence cited"
        elif any(i not in by_id for i in ids):
            reason = "cited event ID does not exist"
        elif any(i not in moment["evidence"] for i in ids):
            reason = "evidence not part of this moment"
        else:
            for n in NUM.findall(IDS.sub("", c["text"])):
                if not any(abs(float(n) - a) < 0.011 for a in ok_nums):
                    reason = f"number {n} not supported by evidence"
                    break
        (bad if reason else good).append({**c, "reason": reason} if reason else c)
    return good, bad


# ---------------------------------------------------------------- pipeline
def build_story(n, inject=False, seed=0, verbose=True):
    match = an.load_match(n)
    events = match["events"]
    res = an.analyse(n)
    rnd = random.Random(seed + n)
    moments = [m for m in res["moments"] if m["type"] != "goal"]
    moments.sort(key=lambda m: m["minute_sort"])
    out = {"match": n, "stats": res["stats"], "cards": [], "totals": {
        "claims_written": 0, "fake_claims": 0, "fake_caught": 0, "claims_published": 0,
        "claims_rejected": 0}}
    t = out["totals"]
    for m in moments:
        pack = evidence_pack(events, m, res["stats"])
        story = narrate(pack)
        if inject:
            story = inject_fake_claim(story, m, rnd)
        good, bad = verify(story, m, events)
        t["claims_written"] += len(story["claims"])
        t["fake_claims"] += sum(1 for c in story["claims"] if c.get("_fake"))
        t["fake_caught"] += sum(1 for c in bad if c.get("_fake"))
        t["claims_published"] += len(good)
        t["claims_rejected"] += len(bad)
        out["cards"].append({"type": m["type"], "team": m["team"],
                             "minute": m.get("minute", m.get("start_minute")),
                             "importance": m["importance"],
                             "headline": story["headline"], "claims": good, "rejected": bad})
    return out


if __name__ == "__main__":
    mode = "Azure OpenAI" if ai_available() else "offline template"
    print(f"Narrator mode: {mode}\n")
    story = build_story(1, inject=True)
    (DATA / "story_01.json").write_text(json.dumps(story, indent=2))
    for c in story["cards"]:
        print(f"[{c['type']}] minute {c['minute']}: {c['headline']}")
        for cl in c["claims"]:
            print(f"   OK       {cl['text']}  (evidence: {len(cl['evidence_ids'])} events)")
        for cl in c["rejected"]:
            print(f"   REJECTED {cl['text']}  -> {cl['reason']}")
    t = story["totals"]
    print(f"\nPublished {t['claims_published']} claims, rejected {t['claims_rejected']} "
          f"(fake claims injected: {t['fake_claims']}, caught: {t['fake_caught']})")
    