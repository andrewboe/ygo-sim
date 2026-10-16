# ML methods research (2026-10-16)

Research subagent report, condensed. Sources linked inline.

## ygo-agent (github.com/sbl1996/ygo-agent)
- **Training:** PPO with dual clipping, GAE (lambda 0.95, gamma 1.0) and UPGO, run by a cleanba-style JAX actor-learner (`scripts/cleanba.py`).
- **Reward and self-play:** the game result is the reward. Self-play uses a single network; there's no league.
- **Network:** an LSTM over 160 card slots × 41 features, 23 global features, 24 legal actions and 32 recent actions.
- **Compute:** the released model trained on over 100M games, roughly 32 × 4090 GPUs for 5 days. A 50-iteration model wins 98% against random but only 3% against the released one.
- **Evaluation:** win rate against random and checkpoint head-to-heads by seat. No Elo, no WindBot comparison.
- **Limitations:** a fixed card list, no search, unseen cards disable it, development has stalled since 2024.
- The author notes combo and puzzle solving needs search, not RL (issue #2).

## Imperfect-information search + learning
- **ReBeL, Student of Games, Pluribus:** impractical here, since they need a tractable public-belief state and large compute.
- **Determinized search (PIMC/ISMCTS):** has known flaws (strategy fusion), but it's practical when hidden information is revealed quickly. That's our current approach, re-dealing hidden cards from a belief model.
- **AlphaZe\*\* (Blüml et al. 2023):** AlphaZero with determinization is competitive in Stratego and DarkHex at modest compute, so expert iteration over determinized search is a sound baseline.
- **DouZero, PerfectDou, Suphx:** the privileged critic (a value net trained on true hidden information) is cheap and effective.

## Hearthstone and Magic
- **Legends of Code and Magic competitions:** search won 2019–2021, and an RL agent won in 2022 only once card sets were randomized.
  - Biggest gains came from move ordering, pruning and lethal detection; hand prediction hurt.
  - Evaluation used shared seeds, mirrored seats and repeated matches.
- **Hearthstone AI Competition:** some decks were held out until the final to test generalization.
- **Hearthstone MCTS:** a learned value net, trained on bot self-play, guided MCTS and improved win rate while cutting compute.
- **Magic (Cowling, Ward & Powley 2012):** ensemble determinization with move pruning.
- **Pitfalls:**
  - Deck ratings from an AI pilot are biased toward the pilot's weaknesses.
  - Pure self-play learns to exploit itself.
  - Outcome labels are noisy.

## Yu-Gi-Oh specific
- WindBot (IceYGO) is the standard scripted bot, with hand-written per-deck executors, and is a natural external anchor.
- No peer-reviewed Yu-Gi-Oh AI papers turned up.

## Recommendations
- **Policy target:** the search's distribution (final NRPA policy softmax, or action frequency across the top lines), not only the chosen action.
- **Value target:** a blend of outcome and probe, shifting toward outcome as games accumulate. Use the privileged critic.
- **Volume:** expect 2–5k games/day, which gives roughly 50–200k turn-1/2 policy labels per day.
  - That's enough to distill the search into a small network.
  - There's only one outcome label per game, so lean on probe labels until there are 10k+ games.
  - Expert iteration usually shows gains within 3–10 iterations.
- **Evaluation:**
  - A fixed seed bank, with both seats and paired comparisons.
  - Roughly 800+ games to detect a 5-point gain at p≈0.5 (SE about 2.5 points at n=400), or SPRT / confidence intervals.
  - A Bradley–Terry/Elo ladder of frozen versions.
  - External anchors: WindBot, a ygo-agent checkpoint, and the non-ML pilot frozen as v0.
  - Held-out decks.
- **No self-grading:**
  - Strength is game outcome against frozen or external opponents only, never probe or search value.
  - Evaluation seeds are separate from training seeds.
  - Train against past versions too.
  - Run periodic audits against a higher-budget search.
