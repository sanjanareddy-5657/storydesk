"""Turns verified moments into viewer-specific text (analyst/casual x English/Telugu/Hindi)
and into timed overlay JSON. Every number in the output comes from the verified moment
metrics, and the verifier's number check is re-run on the final localized text."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analytics"))
sys.path.insert(0, str(ROOT / "agents"))
import analytics as an  # noqa: E402
import story as st  # noqa: E402

T = {
    "en": {
        "high_press": {
            "analyst": ("{T} press high from minute {a}",
                        "{n} pressure actions in {O}'s half between {a}' and {b}': {rate} per minute vs a match average of {base}."),
            "casual": ("{T} are pressing {O} hard",
                       "From minute {a}, {T} pushed up and pressed {O} {n} times in their own half."),
        },
        "momentum_swing": {
            "analyst": ("Momentum swing to {T}",
                        "{T} had {pct}% of all events between {a}' and {b}', with {shots} shots worth {xg} xG."),
            "casual": ("{T} take control",
                       "From minute {a}, {T} had most of the ball and fired in {shots} shots."),
        },
        "big_chance": {
            "analyst": ("Big chance: {player}, {minute}'",
                        "{player} ({T}): a {xg} xG chance, {res}."),
            "casual": ("Huge chance for {T}!",
                       "{player} gets a great chance in minute {minute} and {res}."),
        },
        "res": {"goal": "scored", "no_goal": "missed"},
    },
    "te": {
        "high_press": {
            "analyst": ("{a}వ నిమిషం నుండి {T} హై ప్రెస్",
                        "{O} హాఫ్‌లో {a}–{b} నిమిషాల మధ్య {n} ప్రెషర్ యాక్షన్లు: నిమిషానికి {rate}, మ్యాచ్ సగటు {base}."),
            "casual": ("{T} తీవ్రంగా ప్రెస్ చేస్తోంది",
                       "{a}వ నిమిషం నుండి {T} {O} హాఫ్‌లో {n} సార్లు ప్రెస్ చేసింది."),
        },
        "momentum_swing": {
            "analyst": ("{T} వైపు మొమెంటమ్ మారింది",
                        "{a}–{b} నిమిషాల మధ్య {T} కి {pct}% ఈవెంట్లు ఉన్నాయి, {shots} షాట్లు ({xg} xG)."),
            "casual": ("{T} ఆటను నియంత్రిస్తోంది",
                       "{a}వ నిమిషం నుండి {T} ఎక్కువసేపు బంతిని తమ దగ్గరే ఉంచి {shots} షాట్లు కొట్టింది."),
        },
        "big_chance": {
            "analyst": ("పెద్ద అవకాశం: {player}, {minute}వ నిమిషం",
                        "{player} ({T}): {xg} xG అవకాశం, {res}."),
            "casual": ("{T} కి పెద్ద అవకాశం!",
                       "{minute}వ నిమిషంలో {player} కి మంచి అవకాశం వచ్చింది, {res}."),
        },
        "res": {"goal": "గోల్ అయ్యింది", "no_goal": "మిస్ అయ్యింది"},
    },
    "hi": {
        "high_press": {
            "analyst": ("{a}वें मिनट से {T} का हाई प्रेस",
                        "{O} के हाफ में {a}–{b} मिनट के बीच {n} प्रेशर एक्शन: प्रति मिनट {rate}, मैच औसत {base}."),
            "casual": ("{T} जोरदार प्रेस कर रही है",
                       "{a}वें मिनट से {T} ने {O} के हाफ में {n} बार प्रेस किया."),
        },
        "momentum_swing": {
            "analyst": ("{T} की ओर मोमेंटम बदला",
                        "{a}–{b} मिनट के बीच {T} के पास {pct}% इवेंट्स रहे, {shots} शॉट ({xg} xG)."),
            "casual": ("{T} खेल पर हावी",
                       "{a}वें मिनट से {T} ने ज्यादातर गेंद अपने पास रखी और {shots} शॉट मारे."),
        },
        "big_chance": {
            "analyst": ("बड़ा मौका: {player}, {minute}वां मिनट",
                        "{player} ({T}): {xg} xG का मौका, {res}."),
            "casual": ("{T} को बड़ा मौका!",
                       "{minute}वें मिनट में {player} को शानदार मौका मिला, {res}."),
        },
        "res": {"goal": "गोल हुआ", "no_goal": "चूक गया"},
    },
}


def facts(m):
    mt = m["metric"]
    team, opp = an.TEAM_NAMES[m["team"]], an.TEAM_NAMES[an.OPP[m["team"]]]
    f = {"T": team, "O": opp, "n": len(m["evidence"]),
         "a": m.get("start_minute"), "b": m.get("end_minute"), "minute": m.get("minute")}
    if m["type"] == "high_press":
        f.update(rate=mt["deep_pressures_per_min"], base=mt["match_baseline_per_min"])
    elif m["type"] == "momentum_swing":
        f.update(pct=round(mt["avg_event_share"] * 100), shots=mt["shots"], xg=mt["xg"])
    elif m["type"] == "big_chance":
        f.update(player=mt["player"], xg=mt["xg"], outcome=mt["outcome"])
    return f


def render(m, mode="analyst", lang="en"):
    lang = lang if lang in T else "en"
    mode = mode if mode in ("analyst", "casual") else "analyst"
    tpl = T[lang][m["type"]][mode]
    f = facts(m)
    if "outcome" in f:
        f["res"] = T[lang]["res"][f["outcome"]]
    return tpl[0].format(**f), tpl[1].format(**f)


def numbers_ok(text, m, events):
    """Re-run the verifier's number check on rendered (possibly translated) text."""
    by_id = {e["id"]: e for e in events}
    ok = st.allowed_numbers(m, by_id)
    for n in st.NUM.findall(st.IDS.sub("", text)):
        if not any(abs(float(n) - a) < 0.011 for a in ok):
            return False
    return True


def build_payload(n, mode="analyst", lang="en", inject=False):
    match = an.load_match(n)
    events = match["events"]
    res = an.analyse(n)
    story = st.build_story(n, inject=inject)
    idx = {(m["type"], m["team"], m["minute_sort"]): m for m in res["moments"]}

    cards, overlay = [], []
    for c in story["cards"]:
        m = idx[(c["type"], c["team"], c["minute"])]
        head, line = render(m, mode, lang)
        verified = numbers_ok(head + " " + line, m, events)
        if not verified:
            continue
        end_min = m.get("end_minute", m.get("minute", 0) + 1)
        card = {"type": m["type"], "team": m["team"], "minute": c["minute"], "end_minute": end_min,
                "headline": head, "line": line, "verified": True, "importance": m["importance"],
                "evidence_ids": m["evidence"],
                "claims": c["claims"], "blocked": c["rejected"]}
        cards.append(card)
        overlay.append({"start_sec": c["minute"] * 60, "end_sec": end_min * 60 if m["type"] != "big_chance" else c["minute"] * 60 + 20,
                        "type": m["type"], "team": m["team"], "language": lang, "mode": mode,
                        "lower_third": {"headline": head, "body": line},
                        "evidence_ids": m["evidence"][:12], "verified": True})

    # momentum timeline: Eastvale share of events per minute, smoothed
    tot = [0] * 90
    eas = [0] * 90
    for e in events:
        tot[e["minute"]] += 1
        if e["team"] == "EAS":
            eas[e["minute"]] += 1
    share = an.rolling([eas[i] / max(1, tot[i]) for i in range(90)], 5)
    goals = [{"minute": m["minute"], "team": m["team"], "player": m["metric"]["player"]}
             for m in res["moments"] if m["type"] == "goal"]
    goals.sort(key=lambda g: g["minute"])
    return {"match": n, "teams": an.TEAM_NAMES, "stats": res["stats"], "cards": cards,
            "timeline": [round(v, 3) for v in share], "goals": goals,
            "totals": story["totals"], "overlay": overlay}


def get_events(n, ids):
    wanted = set(ids)
    return [e for e in an.load_match(n)["events"] if e["id"] in wanted]