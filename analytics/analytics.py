import json
import math
from pathlib import Path

DATA = Path("data")
TEAM_NAMES = {"NOR": "Northbridge", "EAS": "Eastvale"}
OPP = {"NOR": "EAS", "EAS": "NOR"}


def load_match(n):
    return json.loads((DATA / f"match_{n:02d}.json").read_text())


def load_answer(n):
    return json.loads((DATA / f"answer_{n:02d}.json").read_text())


def basic_stats(events):
    stats = {t: {"goals": 0, "shots": 0, "xg": 0.0, "passes": 0, "passes_ok": 0}
             for t in TEAM_NAMES}
    for e in events:
        s = stats[e["team"]]
        if e["type"] == "shot":
            s["shots"] += 1
            s["xg"] += e["xg"]
            if e["outcome"] == "goal":
                s["goals"] += 1
        elif e["type"] == "pass":
            s["passes"] += 1
            if e["outcome"] == "complete":
                s["passes_ok"] += 1
    for s in stats.values():
        s["xg"] = round(s["xg"], 2)
        s["pass_acc"] = round(100 * s["passes_ok"] / max(1, s["passes"]), 1)
    return stats


def per_minute(events, fn, team):
    """Count of events per minute (0..89) for a team where fn(e) is True."""
    series = [0] * 90
    for e in events:
        if e["team"] == team and fn(e):
            series[e["minute"]] += 1
    return series


def rolling(series, w=5):
    h = w // 2
    out = []
    for i in range(len(series)):
        lo, hi = max(0, i - h), min(len(series), i + h + 1)
        out.append(sum(series[lo:hi]) / (hi - lo))
    return out


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def segments(flags, min_len=4, max_gap=1):
    """Group flagged minutes into (start, end) segments."""
    segs, start, last = [], None, None
    for m, f in enumerate(flags):
        if f:
            if start is None:
                start = m
            elif m - last > max_gap + 1:
                segs.append((start, last))
                start = m
            last = m
    if start is not None:
        segs.append((start, last))
    return [(a, b) for a, b in segs if b - a + 1 >= min_len]


def trim(seg, raw, min_count):
    a, b = seg
    while a < b and raw[a] < min_count:
        a += 1
    while b > a and raw[b] < min_count:
        b -= 1
    return a, b


def detect_high_press(events):
    """A team presses high when it makes many pressure events deep in the opponent's half."""
    found = []
    for team in TEAM_NAMES:
        if team == "EAS":
            deep = lambda e: e["type"] == "pressure" and e["x"] < 35
        else:
            deep = lambda e: e["type"] == "pressure" and e["x"] > 65
        raw = per_minute(events, deep, team)
        sm = rolling(raw, 5)
        base = median(sm)
        thr = max(2.0, base * 2.5)
        flags = [v >= thr for v in sm]
        for seg in segments(flags, min_len=6):
            a, b = trim(seg, raw, 2)
            ids = [e["id"] for e in events
                   if e["team"] == team and deep(e) and a <= e["minute"] <= b]
            found.append({"type": "high_press", "team": team,
                          "start_minute": a, "end_minute": b + 1,
                          "evidence": ids,
                          "metric": {"deep_pressures_per_min": round(sum(raw[a:b + 1]) / (b - a + 1), 2),
                                     "match_baseline_per_min": round(sum(raw) / 90, 2)}})
    return found


def detect_momentum_swing(events):
    """A swing is a stretch where one team's share of all events jumps well above 50%."""
    found = []
    tot = [0] * 90
    for e in events:
        tot[e["minute"]] += 1
    for team in TEAM_NAMES:
        mine = per_minute(events, lambda e: True, team)
        share = [mine[m] / max(1, tot[m]) for m in range(90)]
        sm = rolling(share, 5)
        flags = [v >= 0.64 for v in sm]
        for seg in segments(flags, min_len=5):
            a, b = seg
            shots = [e for e in events if e["team"] == team and e["type"] == "shot"
                     and a <= e["minute"] <= b]
            xg = round(sum(e["xg"] for e in shots), 2)
            found.append({"type": "momentum_swing", "team": team,
                          "start_minute": a, "end_minute": b + 1,
                          "evidence": [e["id"] for e in shots],
                          "metric": {"avg_event_share": round(sum(share[a:b + 1]) / (b - a + 1), 2),
                                     "shots": len(shots), "xg": xg}})
    return found


def detect_big_chances(events, min_xg=0.4):
    out = []
    for e in events:
        if e["type"] == "shot" and e["xg"] >= min_xg:
            out.append({"type": "big_chance", "team": e["team"], "minute": e["minute"],
                        "evidence": [e["id"]],
                        "metric": {"xg": e["xg"], "outcome": e["outcome"], "player": e["player"]}})
    return out


def detect_goals(events):
    return [{"type": "goal", "team": e["team"], "minute": e["minute"],
             "evidence": [e["id"]],
             "metric": {"xg": e["xg"], "player": e["player"]}}
            for e in events if e["type"] == "shot" and e["outcome"] == "goal"]


IMPORTANCE = {"goal": 100, "big_chance": 70, "momentum_swing": 60, "high_press": 50}


def rank_moments(moments):
    for m in moments:
        base = IMPORTANCE[m["type"]]
        if m["type"] == "big_chance":
            base += 20 * m["metric"]["xg"]
        m["importance"] = round(base, 1)
        m["minute_sort"] = m.get("minute", m.get("start_minute"))
    return sorted(moments, key=lambda m: -m["importance"])


def analyse(n):
    match = load_match(n)
    ev = match["events"]
    moments = (detect_high_press(ev) + detect_momentum_swing(ev)
               + detect_big_chances(ev) + detect_goals(ev))
    return {"match": n, "stats": basic_stats(ev), "moments": rank_moments(moments)}


def overlaps(a_start, a_end, b_start, b_end, tol=3):
    return a_start <= b_end + tol and b_start <= a_end + tol


def evaluate(result, answer):
    """Compare detected moments with planted ground truth."""
    hits = {}
    for p in answer["planted"]:
        ok = False
        for m in result["moments"]:
            if m["type"] != p["type"] or m["team"] != p["team"]:
                continue
            if p["type"] == "big_chance":
                ok = ok or p["event_ids"][0] in m["evidence"]
            else:
                ms, me = m["start_minute"], m["end_minute"]
                ok = ok or overlaps(ms, me, p["start_minute"], p["end_minute"])
        hits[p["type"]] = ok
    false_pos = 0
    for m in result["moments"]:
        if m["type"] in ("goal",):
            continue
        matched = False
        for p in answer["planted"]:
            if m["type"] != p["type"] or m["team"] != p["team"]:
                continue
            if p["type"] == "big_chance":
                matched = matched or p["event_ids"][0] in m["evidence"]
            else:
                matched = matched or overlaps(m["start_minute"], m["end_minute"],
                                              p["start_minute"], p["end_minute"])
        if m["type"] == "big_chance" and not matched:
            continue  # other real big chances are valid moments, not errors
        if not matched:
            false_pos += 1
    return hits, false_pos


if __name__ == "__main__":
    total = {"high_press": 0, "momentum_swing": 0, "big_chance": 0}
    fp_total = 0
    N = 20
    for n in range(1, N + 1):
        res = analyse(n)
        (DATA / f"moments_{n:02d}.json").write_text(json.dumps(res, indent=2))
        hits, fp = evaluate(res, load_answer(n))
        for k, v in hits.items():
            total[k] += int(v)
        fp_total += fp

    r = analyse(1)
    s = r["stats"]
    print(f"Match 1: Northbridge {s['NOR']['goals']} - {s['EAS']['goals']} Eastvale | "
          f"xG {s['NOR']['xg']} - {s['EAS']['xg']}")
    print("Top moments:")
    for m in r["moments"][:5]:
        when = m.get("minute", f"{m.get('start_minute')}-{m.get('end_minute')}")
        print(f"  {m['type']:15s} {TEAM_NAMES[m['team']]:12s} min {when}  importance {m['importance']}")

    print(f"\nDetection over {N} matches (planted events found):")
    for k, v in total.items():
        print(f"  {k:15s} {v}/{N}  ({100 * v / N:.0f}%)")
    print(f"  false positives: {fp_total}")
    