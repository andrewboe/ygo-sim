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

**Probed (default).** After P1's turn, P2 plays a scripted probe turn from its stacked hand: normal
summon a vanilla monster, activate Upstart Goblin, end turn. P1 passes throughout, but every response
the engine offers P1 right after those two actions is a *live* interruption. Effects already used on
turn 1, and effects with no legal target or trigger, aren't offered. Responses offered at phase changes
don't count (a freely usable quick effect isn't an interruption). Card copies still in hand don't get
field credit.

S = Σ over live field cards of max(0.5, tag value) + hand traps kept (tag `hand`, 1 each)
    + 0.1 per card in hand + 0.02 per card on field.

**Tag-only (`--no-probe`).** Every tagged card on the field counts, whether or not its effect was
used: face-up quick/negate 0.75–1, set traps 0.75–1, floodgates 0.5.

Limits: the probe only exercises responses to a summon and to a spell activation. It misses effects
that only answer special summons, monster effects or attacks. Tags (`wsl/card_tags.py`, corrected via
`card_tag_overrides.json`) still weight live cards and value hand traps. S is a proxy for "how likely
P2 loses next turn"; fitted weights (§5.1) and eventually the pilot's value head (§5) replace it.

**As implemented (`wsl/chokepoint.py`):**
- *Objective 2:* for each window on P1's line (deduped by game state, capped at 12) and each legal
  response plus its first follow-up, replay, interrupt, and re-search P1's continuation.
- *Objective 3, max-min:* iterated best response (`--robust ROUNDS`). P2's best timing on the newest
  line becomes a rule, "use the trap right after P1 uses card X". P1 re-searches with that rule live in
  its rollouts, and the learned strategy's uninterrupted (greedy) line becomes the next candidate.
  Every candidate gets the exact map, and the pick is the max over candidates of
  min(goldfish board, boards after each interruption).
- First result (TCG Elfnote vs Ash, 4 openings): worst case 2.04 → 2.90 for a goldfish cost of
  3.51 → 3.04. The new lines include one that gives Ash no window at all.
- **Expected value, not pure max-min.** Pure max-min assumes P2 always holds the trap, and it once traded
  2 points of board for 0.03 of worst case. Selection now maximizes p·worst + (1−p)·goldfish, where p is
  the chance P2 holds the trap (`--p-trap`, default 0.6; later from field hand-trap counts and the
  hypergeometric). p = 1 recovers max-min.
- 10-opening results (max-min, before the EV switch), board through the best-timed trap:
  TCG Elfnote 2.70 ± 0.27 (Ash), 2.85 ± 0.31 (Imperm); projected Ars Magna Elfnote 2.75 ± 0.31,
  3.03 ± 0.33. Ars Magna is ahead everywhere but within noise.

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

### 5.1 Rewards and objectives

- **Game reward:** win +1, loss −1, in-game draw (both players at 0 LP together) 0. No bonus for fast
  wins: Swiss scores a slow win the same as a fast one. ygo-agent's turn-scaled reward is dropped.
- **No clock in training.** Pilot games are untimed, so there is no time-draw to aim for and nothing to
  gain by padding turns with legal but pointless actions. The clock exists only at the match layer (§6).
- **The learned value replaces hand-made per-turn goals.** The value head predicts P(win), P(loss) and
  P(draw) from any state, which captures what a good turn is worth (interruptions, LP, card advantage).
  Eventually S (§3) becomes "P2's predicted win chance against this board".
- **Shaping, early only:** potential-based shaping with Φ = fitted S, adding Φ(s′) − Φ(s) per step
  (Ng, Harada & Russell 1999). This leaves the optimal policy unchanged. Fade it out as the value head matures.
- **Auxiliary heads, predicted but not rewarded:** interruptions at end of turn, damage next turn, cards in
  hand, whether the opponent's combo is stopped. They improve learning and serve as diagnostics.
- **Fit S from outcomes:** once full games are simulated, regress the turn-1 player's result on end-board
  features to get S's weights, per matchup if needed, in place of the hand-picked 1.0/0.75/0.1.

### 5.2 Clean wins

Win quality matters only through match and event effects, which are modeled where they occur:
- **Time:** slow games risk time-draws (§6).
- **Reliability:** P(win) over many games, and max-min lines (§2).
- **Information revealed:** this affects the opponent's siding (§6, Bo3).
- **Event situation:** utility comes from match points, intentional draws and top cut.

LP margin doesn't affect tiebreakers, but it decides unfinished games at time (§6).
Reported per deck but not rewarded: turns to win, wins through 1/2/3 interruptions, LP margin,
time-draw rate, and cards revealed.

**Pilot quality, measured per deck** so a deck isn't judged by a bad pilot:
- Turn-1 gap: the pilot's board vs the search's board from the same hand.
- Chokepoint agreement: the pilot's interruption timing vs the solver's.
- Mirror balance: about 50% in mirrors, going first and going second.
- Elo vs the search bot.

## 6. Match and event

- **Bo3** (`match.py`): from per-game rates (pre/post side × first/second), with a coin flip for game 1 and
  the loser choosing turn order. Closed form, tested against simulation.
- **Clock (to implement; details to verify against Konami's current TCG policy):** timed rounds
  (about 40 min). Game time is simulated from decisions, turns and chains. At time, the current turn
  plus a few extra turns are played; then the LP leader wins an unfinished game, and equal LP is a draw.
  The match goes to whoever won more games; equal games make a match draw (1 point each in Swiss).
  Game outcomes therefore carry duration and LP at time, and the Bo3 closed form gains a
  "game unfinished" outcome.
- **Draw incentives:** a time-draw is worth 1 Swiss point against 3 for a win, so playing for one is
  rational only when P(win) < ~1/3. The pilot never sees the clock (§5.1), so it can't learn to stall.
- **Event** (`tournament.py`): Swiss by score groups (no rematches, byes, OMW tiebreak) then a
  single-elim top cut, players drawn from field shares. Reports conversion = top-cut share / field share.
  To add: intentional draws in the final Swiss rounds, when both players make the cut with a draw.

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
- Ng, Harada & Russell 1999, *Policy Invariance Under Reward Transformations* (potential-based shaping, ICML).
- Konami, *Yu-Gi-Oh! TCG Tournament Policy*: end-of-match procedure, round time, tiebreakers (current version).
