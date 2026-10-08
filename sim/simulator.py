import json
import random
from pathlib import Path

TEAMS = {
    "NOR": {"name": "Northbridge", "players": [f"NOR_{i}" for i in range(1, 12)]},
    "EAS": {"name": "Eastvale", "players": [f"EAS_{i}" for i in range(1, 12)]},
}


def make_match(seed):
    rnd = random.Random(seed)
    events = []

    # Planted events (ground truth). Timings vary per match.
    press_start = rnd.randint(45, 65)
    press_end = press_start + 15
    swing_start = press_end
    swing_end = swing_start + 10
    chance_minute = swing_start + 7

    def add(minute, team, player, etype, x, y, tag=None, **kw):
        events.append({
            "minute": minute, "second": rnd.randint(0, 59), "team": team,
            "player": player, "type": etype,
            "x": round(x, 1), "y": round(y, 1), "_tag": tag, **kw,
        })

    def shot(minute, team, tag=None, xg=None):
        goal_x = 100 if team == "NOR" else 0
        x = 100 - rnd.uniform(5, 30) if team == "NOR" else rnd.uniform(5, 30)
        dist = abs(goal_x - x)
        if xg is None:
            xg = round(max(0.02, 0.5 - dist * 0.015), 2)
        outcome = "goal" if rnd.random() < xg else "no_goal"
        add(minute, team, rnd.choice(TEAMS[team]["players"]), "shot",
            x, rnd.uniform(30, 70), tag, xg=xg, outcome=outcome)
        return outcome

    for m in range(90):
        p_nor = 0.5
        if press_start <= m < press_end:
            p_nor = 0.42
        if swing_start <= m < swing_end:
            p_nor = 0.30

        for _ in range(rnd.randint(24, 32)):
            team = "NOR" if rnd.random() < p_nor else "EAS"
            player = rnd.choice(TEAMS[team]["players"])
            x, y = rnd.uniform(5, 95), rnd.uniform(5, 95)
            r = rnd.random()
            if r < 0.80:
                add(m, team, player, "pass", x, y, outcome="complete" if rnd.random() < 0.8 else "incomplete")
            elif r < 0.89:
                add(m, team, player, "tackle", x, y)
            elif r < 0.96:
                add(m, team, player, "pressure", x, y)
            elif r < 0.99:
                add(m, team, player, "turnover", x, y)
            else:
                shot(m, team)

        # planted: Eastvale high press (pressure deep in Northbridge's half)
        if press_start <= m < press_end:
            for _ in range(3):
                add(m, "EAS", rnd.choice(TEAMS["EAS"]["players"]), "pressure",
                    rnd.uniform(5, 35), rnd.uniform(10, 90), "high_press")
            for _ in range(2):
                add(m, "NOR", rnd.choice(TEAMS["NOR"]["players"]), "turnover",
                    rnd.uniform(5, 35), rnd.uniform(10, 90), "high_press")

        # planted: momentum swing (extra Eastvale shots)
        if swing_start <= m < swing_end:
            shot(m, "EAS", "momentum_swing")

        # planted: big chance
        if m == chance_minute:
            add(m, "EAS", rnd.choice(TEAMS["EAS"]["players"]), "shot",
                rnd.uniform(6, 12), 50, "big_chance", xg=0.65, outcome="goal")

    # sort by time, assign IDs
    events.sort(key=lambda e: (e["minute"], e["second"]))
    tags = {}
    for i, e in enumerate(events, 1):
        e["id"] = f"E{i:05d}"
        t = e.pop("_tag")
        if t:
            tags.setdefault(t, []).append(e["id"])

    answer = {
        "seed": seed,
        "planted": [
            {"type": "high_press", "team": "EAS", "start_minute": press_start,
             "end_minute": press_end, "event_ids": tags.get("high_press", [])},
            {"type": "momentum_swing", "team": "EAS", "start_minute": swing_start,
             "end_minute": swing_end, "event_ids": tags.get("momentum_swing", [])},
            {"type": "big_chance", "team": "EAS", "minute": chance_minute,
             "event_ids": tags.get("big_chance", [])},
        ],
    }
    meta = {"seed": seed, "teams": {k: v["name"] for k, v in TEAMS.items()}}
    return {"meta": meta, "events": events}, answer


if __name__ == "__main__":
    out = Path("data")
    out.mkdir(exist_ok=True)
    for seed in range(1, 21):
        match, answer = make_match(seed)
        (out / f"match_{seed:02d}.json").write_text(json.dumps(match))
        (out / f"answer_{seed:02d}.json").write_text(json.dumps(answer, indent=2))

    m, a = make_match(1)
    ev = m["events"]
    shots = [e for e in ev if e["type"] == "shot"]
    print("Events:", len(ev), "| Shots:", len(shots))
    print("Planted:", [(p["type"], p.get("start_minute", p.get("minute"))) for p in a["planted"]])
    print("20 matches saved in data/")
    