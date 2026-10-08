"""Funnel stage 1 summary: going-first and going-second scores per candidate (ygosim screen).

Going first: mean goldfish board (live interruptions, THEORY §3) over the openings searched.
Going second: mean break-the-board score (wsl/second_screen.py) per opponent, combined by the
opponents' field weights. The two scales differ (interruptions vs win probability), so candidates are
ranked on each within their deck; stage 2 (games vs the field) combines them into one win rate.
"""
import json
from collections import defaultdict

from .api import DATA_DIR


def _field_weight() -> dict[str, float]:
    from .meta import slugify
    field = json.loads((DATA_DIR / "field" / "field.json").read_text(encoding="utf-8"))
    return {f"{slugify(e['deck'])}__tcg": e["weight"] for e in field["entries"]}


def summarize() -> list[dict]:
    first = defaultdict(list)
    for p in (DATA_DIR / "search").glob("cand__*__goldfish.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            first[r["deck"]].append(r["line"])
    second = defaultdict(lambda: defaultdict(list))
    path = DATA_DIR / "screen" / "second.jsonl"
    if path.exists():
        # Interrupted or overlapping runs can repeat a game: keep one result per (game, seed).
        games = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            games[(r["candidate"], r["opponent"], r["game"], r["seed"])] = r["score"]
        for (cand, opp, _, _), score in games.items():
            second[cand][opp].append(score)
    weights = _field_weight()
    current = {f"cand__{r['candidate']}" for r in json.loads(
        (DATA_DIR / "candidates" / "candidates.json").read_text(encoding="utf-8")) if "skipped" not in r}
    rows = []
    for cand in sorted((set(first) | set(second)) & current):  # ignore results of removed candidates
        opp = {o: sum(v) / len(v) for o, v in second[cand].items()}
        w = {o: weights.get(o, 0.0) for o in opp}
        sec = sum(opp[o] * w[o] for o in opp) / sum(w.values()) if sum(w.values()) else None
        name = cand.removeprefix("cand__")
        deck, _, rest = name.partition("__")
        rows.append({"candidate": name, "deck": deck, "variant": rest,
                     "first": sum(first[cand]) / len(first[cand]) if first[cand] else None,
                     "first_n": len(first[cand]), "second": sec, "second_by_opponent": opp,
                     "first_lines": first[cand], "second_games": {o: list(v) for o, v in second[cand].items()},
                     "second_weights": w})
    return rows
