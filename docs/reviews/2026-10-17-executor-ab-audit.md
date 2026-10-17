# Executor A/B audit (2026-10-17)

Before a long paired full-game A/B of the deck executors (docs/windbot_plan.md, phase 5), this audit checks that
the test can answer its question: does running a deck's executor (WindBot port or our own) win more full games?

## Design under audit

`wsl/ab_executors.sh`: each executor deck X plays a fixed opponent Y (a deck without an executor) on the same
deals in both seats. Arm 0: no handlers. Arm 1: handlers / executor for X's seat only (`YGOSIM_HANDLER_SEATS`),
so the opponent plays identically in both arms. The earlier handlers A/B ran handlers for both players, which
cannot show a win-rate effect. `wsl/ab_report.py` pairs the deals and reports win rates, a sign test over the
deals whose result changed, and the going-first rate per arm.

## Checks

| Check | Method | Result |
|---|---|---|
| Isolation | one game, handlers for seat 0 only; count non-zero offsets per seat | seat 0: 10,527 of 10,632 decisions with an offset; seat 1: 0 of 20,588; only the seat-0 executor was created |
| Determinism | same deal, same arm, twice | identical games (226 of 226 actions): deals pair exactly |
| Influence | replay played games; at each executor-seat decision, compare the played move with the executor's pick (arm 0: pick computed, not applied) | played = executor's row pick: 44% (off) -> 80% (on); idle 46 -> 73%, selections 39 -> 81%, battle 61 -> 100%. The executor changes real play at the default budget |
| Turn cap | audit games | none of 12 ended by the turn cap |

## Findings

1. **GameAI fallbacks acted as strong priors.** Deck executors (DECK_EXECUTOR) turned WindBot's last-resort
   defaults (first cards, Attack Position, centre zone, pass, end the turn) into PICK offsets. The Mitsurugi
   executor had an opinion at 99% of its decisions; about half were fallbacks, and real play followed them 89% of
   the time (zones: 25% -> 82%). These defaults are arbitrary (WindBot only falls back when it has no rule).
   **Fixed:** fallbacks are off by default (`YGOSIM_EXECUTOR_FALLBACKS=1` restores them); the base executor's
   default "yes" also counts as a fallback. Goldfish A/B with rows only (30 openings, 16x5, best turn-1 board):
   Mitsurugi 3.02 -> 4.02 (was 4.46 with fallbacks), Branded 3.08 -> 4.54 (4.68), Maliss 3.81 -> 5.04 (5.26):
   the rows carry most of the gain.
2. **Where executors act in the game loop.** Turn player: priors in the search (and the greedy choice where play
   leaves the searched line). Non-turn player: chain responses inside rollouts get the executor's pick as a +1
   prior to the adaptive responder; real interruption windows are decided by `choose_window` (a search comparing
   use vs hold), which never consults the executor; every other prompt (selections, yes/no, positions) follows
   the executor's pick outright via `respond()`. So executors shape the opponent's-turn play mainly through
   targets and triggers, not interruption timing.
3. **A regression from the executor in a full game.** Mitsurugi going first, same deal: off, turn-1 board
   Murakumo + set Saji + two Prayers + Great Purification (Ash kept), lost turn 8; on (fallbacks on), Dyna Mondo +
   two sets, empty hand, OTK'd on turn 2. The priors led the default-budget search to a worse turn-1 board than
   it finds alone, against a live opponent (Mulcharmy Fuwalos, Dominus Spark) that goldfish doesn't model.
4. **Pairing degrades after the first differing move.** Once the executor changes a move, the opponent's
   searches consume randomness differently, so later turns differ by chance (the Branded deal: the opponent found
   turn-2 lethal in one arm, not the other). Paired tests still help (same deal, same opening hands), but the
   result is noisier than an exact pairing; use the sign test over changed deals, not per-game pairing claims.
5. Audit games (6 deals x 2 arms). Fallbacks on: the executor arm was worse in 2 deals, better in 0. Fallbacks
   off (arm 1 re-run): better in 2, worse in 2; the Mitsurugi regression is gone (turn-1 board Murakumo + set
   Kusanagi + Great Purification + Prayers, Ash held; won turn 3). Executor decks won 3 of 3 going first (1 of 3
   without) and 1 of 3 going second (3 of 3 without): too few to judge, but the executors are mostly turn-1 combo
   rules, so the full test should report seats separately. Influence with fallbacks off: played = row pick 75%.

## Proposed full A/B (to agree before launching)

- Executors as they are now (fallbacks off), default search settings (32 rollouts x 10 generations, x6 on turns
  1-2, `YGOSIM_LATE_BOOST` 1 unless the going-first work changes it; recorded in `settings.txt`).
- Six executor decks (Elfnote, Chaos Ritual, Maliss, Branded, Sky Striker, Mitsurugi) each against a fixed
  non-executor opponent, 30 deals per seat (60 games per arm per deck, 720 games). Roughly 2 days.
- Primary result: pooled win rate of the executor decks, arm 1 vs arm 0, two-sided sign test over the deals
  whose result changed. Success: +5 points or more with p < 0.05. Harm: -5 points or worse with p < 0.05.
- Per deck and per seat (going first / second): win rates and changed deals, descriptive (60 games per arm only
  resolves ~15-point effects per deck).
- Secondary: going-first win rate per arm (target band 50-60%, YGOData TCG), turn-1 board (tagged
  interruptions on the executor deck's field at the end of its first turn, from replays), turn of each loss.
- Interim look at half (30 games per arm per deck): stop early only for clear harm (pooled -10 points, p < 0.05).
