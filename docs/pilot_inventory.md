# Pilot inventory (2026-10-09): what the game pilot does today

The "what's there" half of the gap analysis. Code: `wsl/game.py` (full games), `wsl/goldfish.py` (stage 1
turn-1 search), `wsl/belief.py` (hidden information), `wsl/card_tags.py` (card values).

## Decision making
- **Turn player**: NRPA search per turn. 32 parallel rollouts x 10 generations (turns 1-2: x3), each rollout
  replays the game so far and plays the rest of the turn with a softmax policy over options, keyed by a
  stable option hash (action + card codes). The policy adapts toward the best rollout found.
- **Real turn**: follows the best rollout's own moves while they're available; otherwise the learned
  policy greedily; re-plans (smaller search) when the real game reaches a choice the search never saw.
- **Non-turn player (responder)**:
  - At windows where it holds a tagged interruption: plays out the rest of the turn after each option
    (pass + up to 2 interruptions) and takes the one after which the turn player's best continuation
    is worst (minimax over sampled rollouts). Up to 10 such comparisons per turn; identical "hold"
    windows reuse the verdict.
  - Otherwise a heuristic: after the turn player activates/summons, respond with the highest-tagged
    interruption; draw-on-summon hand traps (Mulcharmy, Maxx "C") at the first window of the turn;
    own optional triggers: yes; forced choices: first option.
  - Inside rollouts the responder co-evolves: its policy adapts toward the turn player's worst rollouts.
- **Card hints (Forge-style)**: don't set/normal summon monster hand traps; on your own turn, hand traps
  in chain windows default to hold.

## Hidden information
- Every rollout re-deals what the decider can't see (belief.py): the opponent's archetype is sampled from
  the field (weighted by share x likelihood of cards shown so far), then their hand, deck order, Extra Deck
  and face-down cards from that archetype's list; the decider's own deck order is permuted.
- Not modeled: what the opponent revealed or searched (resampled anyway); inference from the opponent's
  behavior; game 2-3 knowledge (supported by the code, not wired into matches).

## Evaluation (end of each searched turn)
- Logistic score over: LP difference (per 1,000), live interruptions on own board (search rollouts: probed
  by a scripted opponent summon + spell, as stage 1; real/greedy: static tags), opponent's tagged board,
  cards in hand and on field (0.3 each), held hand traps (1.0 each, once per name).
- Designed weights; a refitter exists (anchored to them, constrained) but needs v3 games.
- Not modeled: what a board does beyond interruptions (follow-ups, recursion, protection, floodgates'
  breadth, battle threat/ATK), grave/banish resources, deck thinning, the opponent's outs.

## Game structure
- Single games to a 12-turn cap (LP leader wins at the cap). Bo3 and side decks exist in the funnel code
  (`match.py`, `sideplan.py`) but games 2-3 aren't played with knowledge of game 1.
- Going first/second is assigned, not chosen.

## Known weak points (from audits, 2026-10-08/09)
- Long combo turns are found only with extra search (turn 1 boost); unclear how well it plays *into* hand
  traps (end boards shrink a lot vs interruption; cautious or correct is unknown).
- Probe measurement inside games gives some implausible values (a set Rhapsodia board scored 0) - being
  validated.
- Hand traps sometimes summoned as bodies when not urgent.
- Engine: some fusion checks blow up (CPU watchdog cuts them at 1 s); Lunalight stalls, Solfachord crashes.
