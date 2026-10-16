# ML stage design (draft for review, 2026-10-16)

Research behind this: docs/research/ml_methods.md and docs/research/validation_sources.md.

## Principle
Strength is measured only against things the training can't touch: external data, fixed reference
tests, and frozen opponents. Probe scores and search values are training signals, never results.
Pass thresholds are fixed here, before any training run.

## Gates (run on the current non-ML pilot first; ML must pass them too)
| Gate | Test | Pass | Current |
|---|---|---|---|
| G1 Seat balance | Going-first win rate, meta-vs-meta games (paired seeds, n≥400) | 58-72% (fail outside 55-75%); hand traps measurably shrink it | 37% (n=60) and mirror 50% (n=12): **fail** |
| G2 Matchup direction | Sign of matchups that have YGOData cells with n≥200 (re-pulled after BETB) | ≥75% of signs agree; none wrong by >15 pts | not run |
| G3 Reference boards | 3-5 curated hands per deck from guides, verified in EDOPro: reach the documented end board | ≥80% matched or beaten | not built |
| G4 Interruption puzzles | Curated positions with a known best response (chokepoint vs bait, Standby Mulcharmy, Evenly timing) | ≥85% correct | partial (S2/S4 suite) |
| G5 Strength ladder | Paired fixed-seed games vs frozen v0 (today's pilot), a WindBot-only anchor, and previous versions; SPRT or 95% CIs | Beats v0 and the anchors with significance | not built |

G1 failing is the first problem. Real play has going first win about 65% in Master Duel WCS2026, and our
pilot is well below that, so either going-first boards or defence on the opponent's turn are still too weak.
ML trained on this pilot would learn the same bias. **Step 1 is to diagnose G1, not to train.**

## ML plan (once G1 is in range and G3-G5 exist)
1. **Data:** self-play games with full provenance in each result row (a new CONFIG, the commit, and the
   card_tag_overrides hash). At each searched decision, log the search's final policy distribution, not
   only the chosen move. Evaluation seeds are kept separate from training seeds.
2. **Network:** the existing transformer (wsl/pilot.py) with policy and value heads, on the RTX 5080
   (PyTorch with CUDA 12.8 works). The value head is a privileged critic: it trains on the true hidden
   cards, while play uses the belief.
3. **Targets:**
   - Policy: cross-entropy against the search distribution.
   - Value: a blend `a*outcome + (1-a)*probe`, with `a` rising from 0.2 to 1 as games accumulate.
4. **Use:** the network becomes NRPA's prior and replaces the hand-built evaluation. Success means the
   G5 ladder improves at the same budget, or holds at half the budget.
5. **Expert iteration:** search with the network, play new games, retrain, repeat for 3-10 iterations.
   Every iteration must pass G1-G5 before the next. Training mixes in games against past versions.
   Periodic audits against a higher-budget search catch exploits the network learns against itself.

## Volume and cost
- Current speed is about 2-5 minutes per game. Expect a few thousand games per day.
- That gives tens to hundreds of thousands of turn 1-2 policy labels per day: enough to distil the search.
- Outcome labels come one per game, so the value target leans on the probe until there are more than 10k games.

## Open questions for the user
- **YGOData** needs a browser, and it has no terms page. Is it OK to read the matchup cells manually,
  through the browser, a few times? Bulk scraping of DuelingBook stays out.
- **WindBot as an anchor:** check its license, and confirm WindBot-only play as an opponent.
- **Held-out decks** for evaluation, for example Lunalight and Magistus, kept out of training and tuning.
