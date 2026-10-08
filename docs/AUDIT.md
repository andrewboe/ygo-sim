# Design audit and game review (2026-10-08)

Stage 2 results (finalists: Chaos Ritual Dogmatika/Stardust variants, Blitzclique Swordsoul, Branded
Springans) are **not trusted** until items 1–3 are fixed and the sanity checks in item 4 pass.

## Evidence
- Game review (wsl/review.py, 12 sampled stage 2 games): monster hand traps played as monsters 12 times
  (Ash ×5, Droll ×3, Fuwalos ×3, Purulia ×1); a responder used Ash on its own Mulcharmy Fuwalos; turn-1
  combos themselves are coherent, lethal is taken.
- Stage 2 data (1,404 games): going first wins only 43% (43% in the Elfnote mirror too); field lists
  going first win 9–37%; candidates going second win 82–90%; 15% of games end on turn 2.
- Fitted evaluation (data/games/eval_weights.json): 180 Elfnote-mirror games; held hand traps −0.10,
  card on field +0.32, card in hand +0.37.

## Findings (ranked)
1. **High — the turn player picks its opponent's real moves.** game.py commits the best rollout's
   full action list, including the responder's sampled actions, so the defender plays whatever was
   worst for itself in that rollout. Fix: real games advance decision by decision; each player plays
   its own learned policy greedily; nothing is copied from rollouts.
2. **High — information leakage.** Every rollout replays the same duel: own deck order, opponent hand,
   deck order, set cards and Extra Deck are all known. Fix: belief-based determinization per rollout
   (game 1: field-weighted archetype prior updated by revealed cards; within archetype, meta inclusion
   rates; games 2–3: the known deck), resampling own deck order and set-card identities too.
3. **High — evaluation is narrow and self-reinforcing.** Fit on one mirror, under the flaws above,
   never refit. Fix: refit after 1–2 on all decks with constraints/priors, leave-one-matchup-out
   validation, per-deck calibration; sensitivity test of rankings vs default weights.
4. **High — pilot-skill bias, no external validation.** Fixed search budget regardless of turn
   complexity; mirror not ≈50/50 per seat. Fix: budget-elasticity test (1× vs 3×); compare simulated
   first-player win rate and field-deck strength with real tournament data; goldfish end boards vs
   known human end boards.
5. **Med-high — statistics.** Winner's curse on finalists; variants indistinguishable; round-0 cut is a
   fraction cut, not CI-based; pooled results across configs; common random numbers unverified.
   Fix: fresh independent games for finalists, paired comparisons on shared deals, config-hash
   filtering, CI-only elimination.
6. **Medium — match-end rules.** Turn cap = LP leader wins; Konami Tournament Policy v2.5 (Sep 2025)
   scores an unfinished match as a double loss. Fix: model match time; unfinished = 0 points each.
7. **Medium — fixed field, best response only.** Field = topping shares, not entry shares; one medoid
   per archetype; Nash/α-Rank (THEORY §7) not implemented. Fix: matchup matrix → Nash mixture and
   α-Rank; report vs field, vs Nash, vs a field shifted toward the winner.
8. **Medium — side decking.** Seat-only side plans; opponent never sides; Bo3 falls back to pre-side.
   Fix: matchup-specific side templates chosen by simulation, both players side.
9. **Low-med — stage 1 probe** only tests responses to a normal summon and a spell. Fix: re-admit
   boundary decks into the corrected stage 2.
10. **Low — chokepoint p_trap** superseded by the belief model.

Checked and fine: no deck plays unscripted cards (only Normal Monsters lack scripts); Bo3 seat rule in
match.py is correct.

## Sources
Cowling, Powley & Whitehouse 2012 (ISMCTS); Long et al. 2010 (AAAI, when PIMC works); García-Sánchez et
al. 2016 and Fontaine et al. 2019 (deck search depends on the bot); Maron & Moore / Birattari 2002
(racing); Omidshafiei et al. 2019 (α-Rank); Lanctot et al. 2017 (PSRO); Konami TCG Tournament Policy v2.5.
