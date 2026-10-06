# Theory and design

This is the reference for what ygosim computes and why. Code cites sections as `THEORY §n`.
References in §9 are from memory and are marked for verification.

## 1. Levels of the problem

| Level | Question | Status |
|---|---|---|
| Decision | Which legal option at this prompt? | Engine prompts (ygoenv on ygopro-core) |
| Turn 1 | Best line from an opening hand, through interruptions | §2–3, goldfish + chokepoint search |
| Game | Win probability, going first or second | §5 pilot |
| Match | Bo3 with siding | §6, `ygosim/match.py` |
| Event | YCS-style Swiss + top cut | §6, `ygosim/tournament.py` |
| Meta | Which deck and list to bring | §7 |

We build bottom up: get one game right, then Bo3, then events.

## 2. Turn-1 subgame: the chokepoint game

Modern Yu-Gi-Oh turns are long combos with few chances to interrupt. Interruptions are only legal at
specific *windows*: points where the engine offers the non-turn player a chain (`MSG_SELECT_CHAIN`
with that card among the options). Each hand trap has its own trigger: Ash Blossom on a search,
special summon from the deck, or send from the deck; Infinite Impermanence on a face-up effect monster;
Nibiru after the fifth summon. The engine enforces this, so legality is exact, not modeled.

**Players.** P1 (going first) holds opening hand H. P2 holds interruption set I (hand traps), unseen by P1.

**Lines.** A line ℓ is P1's sequence of choices. Replays are deterministic given the duel seed and the
choice sequence, so any prefix of ℓ can be reproduced exactly.

**Windows.** W(ℓ) = the (step, card) pairs where some c ∈ I is legal to chain while ℓ is played.

**Payoff.** S(board) = P1's end-of-turn board score (§3). P2 wants to minimize it.

**Adaptation.** After an interruption at window w, P1 re-plans: the value is
V(ℓ, w, c) = max over continuations of ℓ after w of S. Computed with the same search as goldfishing.

**Objectives, in order of strength:**

1. *Goldfish:* max_ℓ S(ℓ) with P2 passing. (Implemented.)
2. *Chokepoint map:* for P1's goldfish line, the best timing for P2 is argmin_(w,c) V(ℓ, w, c).
   Output per deck: which windows matter and how much each hand trap costs P1.
3. *Robust line (max-min):* max_ℓ min_(w,c) V(ℓ, w, c). P1 plays around interruptions: baits a
   weaker effect into Ash, sequences around Impermanence, keeps an extender.
4. *Equilibrium:* P2 can't see P1's hand or line, and P1 can't see I, so optimal play may mix (e.g.
   chain Ash to the first search with some probability, hold it otherwise). The subgame is small enough
   to solve approximately with PSRO: alternate best responses (P1 lines by search; P2 timing policies by
   chokepoint search) over growing populations, solving the population payoff matrix for a Nash
   mixture each round.

Multiple interruptions (e.g. Ash + Impermanence) extend W to sequences of windows; the same
definitions apply with nested min/max.

## 3. Board score S

Interruptions on board plus hand traps kept, with small tiebreaks (`wsl/card_tags.py`):
face-up quick/negate effects 0.75–1, set traps 0.75–1, floodgates 0.5, hand traps in hand 1,
+0.1 per card in hand, +0.02 per card on field. Monster hand traps are worth 0 on the field.

Known biases, to fix: effects already used this turn still count (once-per-turn tracking);
keyword tags mislabel some cards (corrected via `card_tag_overrides.json`). S is a proxy for
"how likely P2 loses next turn"; the pilot's game value (§5) eventually replaces it.

## 4. Search methods

- **NRPA** (nested rollout policy adaptation): single-player search for P1's line; a softmax policy
  over option identities (decision type + action + card codes) is adapted toward the best rollout.
  Works because replays are exact and turn 1 is effectively single-player when P2 passes.
- **Chokepoint search:** replay to each window, apply the interruption, re-run NRPA for P1's continuation.
- **Max-min / PSRO:** §2 objectives 3–4, built from the two searches above as best-response oracles.

## 5. The pilot (neural)

One deck-conditioned network for every deck, not one per deck. Edited lists and new cards must work
without retraining.

- **Inputs:** ygoenv's observation: cards in each zone with features from card ID embeddings plus
  card-text features, global state (LP, phase, turn), the legal options, and recent action history.
- **Architecture:** transformer over cards; options scored by attending to the cards they reference
  (from ygo-agent).
- **Heads:** policy over options; game value (win probability); end-board value (S, for turn 1);
  interruption value (payoff of each chain option vs pass at a window, §2).
- **Training:**
  1. *Imitation from search:* NRPA lines (P1) and chokepoint/equilibrium answers (P2) as labels.
  2. *Expert iteration:* pilot-guided search produces better labels, then retrain, repeat.
  3. *Self-play league:* full games across the field with PSRO-style populations and exploiters;
     an imperfect-information update (PPO first, then R-NaD as in DeepNash).
- **Play time:** network everywhere, plus search at high-stakes interruption windows (ReBeL-style).
- **Stack:** PyTorch on the RTX 5080. ygo-agent's JAX 0.4.28 predates Blackwell.

**Pilot quality, measured per deck** so a deck isn't judged by a bad pilot:
- Turn-1 gap: the pilot's board vs the search's board from the same hand.
- Chokepoint agreement: the pilot's interruption timing vs the solver's.
- Mirror balance: about 50% in mirrors, going first and going second.
- Elo vs the search bot.

## 6. Match and event

- **Bo3** (`match.py`): from per-game rates (pre/post side × first/second), with a coin flip for game 1 and
  the loser choosing turn order. Closed form, tested against simulation.
- **Event** (`tournament.py`): Swiss by score groups (no rematches, byes, OMW tiebreak) then a
  single-elim top cut, players drawn from field shares. Reports conversion = top-cut share / field share.

## 7. Meta and deck optimization

- **Ranking:** the matchup matrix is non-transitive; rank with Nash / α-Rank alongside tournament
  conversion, not average win rate.
- **Optimization:** PSRO at the deck level. Strategies are (decklist, side plan); the oracle is search
  over legal edits (inclusion tables from tournament data as the edit space, MAP-Elites for diversity)
  scored against the current meta mixture via the event simulator.

## 8. Roadmap

A1 log windows → A2 controlled P2 hand → A3 chokepoint map → A4 robust lines → A5 equilibrium →
B full single game (search pilot, then neural) → C Bo3 with siding → D events → meta optimization.

## 9. References (to verify)

- Rosin 2011, *Nested Rollout Policy Adaptation for Monte Carlo Tree Search* (IJCAI).
- Zinkevich et al. 2007, *Regret Minimization in Games with Incomplete Information* (CFR).
- Brown & Sandholm 2018/2019, Libratus / Pluribus (Science).
- Brown et al. 2020, *Combining Deep RL and Search for Imperfect-Information Games* (ReBeL, NeurIPS).
- Schmid et al. 2023, *Student of Games* (Science Advances).
- Perolat et al. 2022, *Mastering Stratego... with model-free MARL* (DeepNash, R-NaD; Science).
- Zha et al. 2021, *DouZero* (ICML).
- Cowling, Powley & Whitehouse 2012, *Information Set Monte Carlo Tree Search* (IEEE TCIAIG).
- Lanctot et al. 2017, *A Unified Game-Theoretic Approach to MARL* (PSRO, NeurIPS).
- Omidshafiei et al. 2019, *α-Rank* (Scientific Reports).
- Vinyals et al. 2019, AlphaStar league training (Nature).
- Fontaine et al. 2019, *Mapping Hearthstone Deck Spaces through MAP-Elites* (GECCO).
- Anthony et al. 2017, *Thinking Fast and Slow with Deep Learning and Tree Search* (expert iteration).
- sbl1996/ygo-agent (GitHub): ygoenv + RL agents for YGOPro.
