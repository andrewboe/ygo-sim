# Roadmap (agreed 2026-10-17)

## End goals
1. **Best new decks in a format:** when a format changes (new set, banlist), rank the decks by expected
   tournament conversion before real results exist.
2. **Tuning for a new format:** hand traps, non-engine cards and side decks for a chosen deck against
   the expected field.

Simulation only earns its place where data doesn't exist yet. For "which deck is best right now", real data
(YGOData matchups, tournament results) beats any simulator. So every output is scored against a data-only
baseline, and against what actually happens once results arrive.

## Lessons from prior work (docs/research/ml_methods.md)
- Hearthstone deck search with AI pilots produced decks tuned to the bot's weaknesses, never validated
  against human play. Our main risk.
- Search beats learning at our compute. Evaluate with fixed seeds and mirrored seats.
- ygo-agent-scale RL (about 100M games) is out of reach and was never validated on deck rankings.

## Phases (each has a budget and a written result before the next starts)
| Phase | What | Baseline to beat / pass rule | Budget |
|---|---|---|---|
| A. Baselines | Deck ranking: YGOData matchup matrix + field shares -> tournament simulator. Tuning: consensus counts from tournament lists (inclusion tables). | Exists and is reproducible | days |
| B. Simulator validity | Reproduce known pre-BETB facts: going-first rate 50-60% (G1), matchup directions (G2); reference end boards (G3) and hand-trap puzzles (G4) for the field decks | G1 in band, G2 ≥75%. **Stop rule:** if G2 is still under 60% after about 2 weeks, drop full-game simulation; keep only combo/interaction checks for tuning | ~2 weeks |
| C1. New-format test: decks | Predict BETB (and Toon, 2026-11-12) deck strength from information available beforehand (OCG results, new cards, simulation); score against post-release YGOData and YCS top cuts | Better rank agreement than the data-only / OCG-projection baseline | per set |
| C2. New-format test: tuning | Recommend the hand-trap / non-engine / side package for 2-3 decks; compare with what top lists converge on 4-8 weeks later | Matches or anticipates the consensus | per set |
| D. Improve | ML (docs/ml_design.md), more executors, list search, only where C shows the simulator is the bottleneck | Gates G1-G5 | later |

## Current state (2026-10-17)
- G1 fails: going first wins 31-38% (TCG 53.5%). Main cause: Elfnote's turn-1 boards are softer than real ones.
- The deck-executor A/B (other session) runs until about 2026-10-19 and reports Elfnote going first and its
  Extra Deck reach. The engine and runtime are frozen during it.
- ML stage on hold until phase C shows the simulator adds value.

## Phase A result (2026-10-17)
- **Deck baseline:** `python -m ygosim.baseline` (YGOData matchups -> Bo3 -> 200 events of 263 players).
  - Pre-BETB conversion: Blitzclique 1.44, Fairy Tail 1.27, Maliss/Elfnote/Invoked/L&D variants about 1.0-1.1,
    Mitsurugi 0.73, Branded 0.58, Sky Striker 0.47.
  - Decks with no YGOData row (Power Patron, Lunalight, Toon, other) play 50%.
- **Tuning baseline:** the existing inclusion tables (`ygosim meta`, data/meta/*.inclusion.json: play rate and
  average copies per card and zone), with dated lists in data/store.json (`ygosim refresh`). Phase C2 compares
  them at release time and 4-8 weeks after.
- **Next:** re-read YGOData once post-BETB data appears (its next update), which is the first phase C1 check.
