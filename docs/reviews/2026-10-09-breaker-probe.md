# Regression check, breaker-aware board value, search variance (2026-10-09)

## Regression after the S4 fixes (S2 into Ash, deals 95000-95001, live interruptions)
| Deck | Before | After |
|---|---|---|
| Elfnote | 1.00 / 2.75 | 3.25 / 2.75 |
| DM Chaos Ritual | 0.00 / 2.00 | 0.00 / 2.00 |
| Mitsurugi Yummy | 1.25 / 2.00 | 1.25 / 3.00 |
No regressions. Mitsurugi Yummy with belief on and no real interruption (`_p2__evenly`, dead on turn 1):
1.25 / 2.75 vs passive 1.25 / 3.25. The "belief-driven caution" gap is within search noise, closed.

## Breaker-aware board value (gap #1)
Built: the end-of-turn probe can open with a breaker (Dark Ruler No More or Harpie's Feather Duster,
picked against the side of the board holding more interruption value). Board value = half every live
interruption + half the better of answering the breaker with a negate or letting it resolve.
`suite_s1.py` now prints both (`live` with the breaker, `no breaker`).

Findings while building it:
- Alternating breakers by rollout made scores noisy, and NRPA chased lucky rollouts. Now deterministic per board.
- The breaker stage has to end when the breaker reaches the GY, or post-resolution windows count as answers.
- **Engine anomaly (open):** after Dark Ruler No More resolves, Elfnote Lucina / Fortuna / Tinia
  are still offered their opponent-turn Quick Effects. This happens with a natively drawn DRNM too
  (`_p2__drnm`, game 97001), not just a probe-staged one. The scripts and the core's disabled checks
  look correct; cause unknown. The probe drops face-up monsters from the after-DRNM responders as a
  workaround. Real games may let Elfnote boards ignore DRNM-style negation, which would overvalue them.

A/B (old probe vs breaker probe in search, same deals, boards scored with the breaker metric):
+0.25, -3.75, +0.12, 0, 0. The -3.75 was an empty board, and it turned out to be search variance,
not the probe. **Search rollouts keep the plain probe** (`PROBE_BREAKERS = ()`); the breaker metric
is measurement only.

## Search variance on turn 1 (new weak point)
The same deal (Elfnote 203621: Regina, Medius, Purulia, Ghost Ogre, Ash) across search seeds, value
without the breaker:
| Search | Seeds 0 / 1 / 2 | Mean |
|---|---|---|
| One NRPA run, 30 gens | 4.25 / 0 / 0 | 1.42 |
| 3 restarts x 10 gens | 1.75 / 0.75 / 0.75 | 1.08 |
| Successive halving (3 x 6 gens, best +12) | 0.75 / 3.25 / 1.50 | 1.83 |
The empty boards are a deceptive landscape: partial combos score below an empty field that keeps
Purulia live, so a single run locks onto "end the turn". Successive halving stays, as it removes the
collapses. On two other deals it was neutral (203620: 3.50 / 1.75 / 1.50; Mitsurugi Yummy 570031:
2.25 / 2.75 / 1.75, vs about 2.5 and 2.4 single-run). Variance is still about 1 interruption per deal.

Open, by priority:
1. Turn-1 search variance: more budget, or better rollout priors for combo depth. It dominates every
   board-quality comparison at this sample size.
2. The DRNM / Elfnote engine anomaly.
3. Mitsurugi Yummy seed 2 set Mulcharmy Fuwalos (a hand-trap monster) despite the hint.
