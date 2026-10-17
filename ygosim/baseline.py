"""Data-only baseline (docs/roadmap.md, phase A): rank decks from real matchup data, no simulation.

Game win rates come from YGOData's TCG "Advanced" matrix (DuelingBook ranked, 2026-05-22 to 07-28; read
manually, docs/research/ygodata_advanced_2026-08-05.md). Field shares come from data/field/field.json. Each
deck pair's game rate becomes a Bo3 match rate (match.match_win_rate) with the measured going-first edge
(53.5% overall, so +-3.5 points by seat) and no side-deck change. Then tournament.simulate runs YCS-sized
events. Decks with no YGOData row (Power Patron, Lunalight, Toon, and the "other" share) play 50% games.

This is the number any simulator output has to beat for "which deck is best now". It is pre-BETB.

Run:  python -m ygosim.baseline [--events 200] [--players 263]
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .match import GameRates, match_win_rate
from .tournament import EventFormat, simulate

FIELD = Path(__file__).resolve().parent.parent / "data" / "field" / "field.json"
SEAT_EDGE = 0.035  # going first wins 53.5% of TCG games (YGOData, n=30,858)

# Row deck's game win % vs column deck (YGOData). Kewl Tune and Artmage are left out (Rotary is now
# Forbidden; Artmage isn't in our field).
YGODATA_DECKS = ["L&D Ritual", "Blitzclique", "Sky Striker", "Mitsurugi", "Invoked", "Branded", "Elfnote",
                 "Yummy", "Maliss", "Fairy Tail"]
YGODATA = {
    "L&D Ritual":  [None, 49.3, 56.9, 54.5, 54.1, 58.6, 47.1, 48.9, 55.7, 44.3],
    "Blitzclique": [50.7, None, 56.4, 44.4, 56.6, 53.6, 55.7, 57.1, 44.8, 57.7],
    "Sky Striker": [43.1, 43.6, None, 45.1, 46.2, 38.1, 41.4, 42.0, 50.0, 40.7],
    "Mitsurugi":   [45.5, 55.6, 54.9, None, 45.0, 47.2, 43.6, 49.1, 47.5, 33.3],
    "Invoked":     [45.9, 43.4, 53.8, 55.0, None, 56.4, 55.2, 51.6, 47.5, 51.9],
    "Branded":     [41.4, 46.4, 61.9, 52.8, 43.6, None, 44.6, 41.1, 42.7, 38.3],
    "Elfnote":     [52.9, 44.3, 58.6, 56.4, 44.8, 55.4, None, 50.0, 39.6, 50.9],
    "Yummy":       [51.1, 42.9, 58.0, 50.9, 48.4, 58.9, 50.0, None, 42.3, 52.6],
    "Maliss":      [44.3, 55.2, 50.0, 52.5, 52.5, 57.3, 60.4, 57.7, None, 55.0],
    "Fairy Tail":  [55.7, 42.3, 59.3, 66.7, 48.1, 61.7, 49.1, 47.4, 45.0, None],
}
# Our field deck -> YGOData archetype (None: no data, plays 50%).
FIELD_TO_YGODATA = {
    "Elfnote": "Elfnote", "Dark Magician Chaos Ritual": "L&D Ritual", "Chaos Ritual": "L&D Ritual",
    "Chaos Ritual (OCG)": "L&D Ritual", "Mitsurugi Chaos Ritual": "L&D Ritual", "Sky Striker": "Sky Striker",
    "Blitzclique": "Blitzclique", "Invoked": "Invoked", "Mitsurugi Yummy": "Yummy", "Branded": "Branded",
    "Magistus Invoked Fairy Tail": "Fairy Tail", "Mitsurugi": "Mitsurugi", "Maliss": "Maliss",
}


def game_rate(a: str | None, b: str | None) -> float:
    if a is None or b is None or a == b:
        return 0.5
    return YGODATA[a][YGODATA_DECKS.index(b)] / 100


def match_matrix(decks: list[str]) -> np.ndarray:
    m = np.full((len(decks), len(decks)), 0.5)
    for i, a in enumerate(decks):
        for j, b in enumerate(decks):
            if i != j:
                p = game_rate(FIELD_TO_YGODATA.get(a), FIELD_TO_YGODATA.get(b))
                m[i, j] = match_win_rate(GameRates(p + SEAT_EDGE, p - SEAT_EDGE, p + SEAT_EDGE, p - SEAT_EDGE))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=200)
    ap.add_argument("--players", type=int, default=263)
    args = ap.parse_args()
    field = json.loads(FIELD.read_text())
    decks = [e["deck"] for e in field["entries"]] + ["Other"]
    shares = [e["weight"] for e in field["entries"]] + [field["other_share"]]
    stats = simulate(decks, shares, match_matrix(decks), EventFormat(args.players), args.events)
    print(f"Data-only baseline: {args.events} events x {args.players} players, field as of {field['as_of']}, "
          f"YGOData matchups (pre-BETB)")
    print(f"{'deck':30s} {'field':>6s} {'top cut':>8s} {'conv':>5s}  data")
    for r in stats.table():
        src = FIELD_TO_YGODATA.get(r["deck"]) or "none (50%)"
        print(f"{r['deck']:30s} {r['field_share']:6.1%} {r['top_cut_share']:8.1%} {r['conversion']:5.2f}  {src}")


if __name__ == "__main__":
    main()
