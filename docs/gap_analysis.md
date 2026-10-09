# Gap analysis: pilot vs expert play (2026-10-09)

Sources: docs/research/strategy.md (expert principles), docs/research/meta.md (decks, pending),
docs/pilot_inventory.md (what the pilot does). Status: FIXED (this session), PARTIAL, OPEN.
Priority is for Track A (short weak-point tests, then fix).

## Fixed tonight
1. **Probe was blind to monster-effect negates.** It summoned a vanilla and activated a spell, so
   Crystal Wing-style "when a monster effect is activated" negates (most omni-negates) never registered,
   in stage 1 and in game search. The filler is now Card Trooper: summon, activate its effect, then the
   spell. FIXED.
2. **Empty-field hand traps.** Mulcharmys, Evenly Matched and Impermanence from the hand need you to
   control no cards; the evaluation credited them regardless (summoning Cartesia while holding Evenly
   Matched). Now credited only with an empty field. Check: the Chaos Ritual brick hand now passes with an
   empty field instead of summoning Cartesia. FIXED.
3. **In-game probe measurement**: harness bugs gave zeros; with probe-from-position, boards now measure
   plausibly (Rhapsodia + interrupting monsters 1.75; Junora board 2.75; empty 0). FIXED.

## Open, by priority
1. **Board value = interruptions after the opponent's likely 1-2 hand traps/breakers** (strategy §3, §5).
   The probe counts interruptions against a summon + monster effect + spell, with no breakers. Next:
   probe variants that also apply a breaker (Droplet / Evenly Matched / Lightning Storm / DRNM-like) and
   score what survives; prefer diversity across response types. PARTIAL (probe exists).
2. **Hand traps: chokepoint vs bait** (§2). The timing comparison (use now vs hold, by the turn player's
   best continuation) is the right mechanism; its quality depends on rollout realism. Needs a scenario
   test per hand trap (Ash on starter vs extender, Imperm on the payoff). PARTIAL.
3. **Breaker conditions and sequencing** (§4): "control no cards / no face-up cards" breakers first;
   Droplet type lockout; DRNM no-damage clause; Talent needs a baited monster effect. The engine enforces
   legality; the pilot only orders them right if search finds it. Needs scenario tests. PARTIAL.
4. **Playing first into hand traps** (§3): non-committal plays first, bait with redundant starters, a
   negate before the 5th summon (Nibiru), stop extending while a Mulcharmy is live. Belief-sampled
   rollouts expose the search to these; the evaluation already charges opponent draws. Needs a scenario
   test (turn 1 vs a known Ash / Nibiru / Mulcharmy). PARTIAL.
5. **Battle phase** (§7): lethal over attack orders, Evenly Matched at the end of the Battle Phase,
   DRNM's no-damage clause. Search handles attacks as options; no dedicated lethal sub-search. OPEN
   (low cost: a lethal check before ending the Battle Phase).
6. **Evaluation beyond interruptions** (§5, §6): follow-ups/recursion, protection, floodgates, LP
   relative to the opponent's burst, usable resources over raw card count. OPEN (larger).
7. **Turn order as a decision; play/draw side plans; game 2-3 knowledge** (§1, §8). Match layer.
   OPEN (after single games are trusted).
8. **Mulcharmy End Phase hand cap** (+6), Nibiru counter awareness in evaluation. OPEN (small).

## Track A weak-point suite (each a few minutes; run after every change)
- S1 combo depth: each field deck's turn 1 vs a passive opponent, probe-scored (done for Elfnote: 1.5).
- S2 into hand traps: turn 1 vs a known Ash / Imperm / Nibiru / Mulcharmy (chokepoint tooling).
- S3 breaking: going second vs a fixed board; breakers used, lethal found when it exists.
- S4 interruption timing: Evenly Matched end of Battle Phase, Mulcharmy in Standby, Ash on the chokepoint.
- S5 regression: the 6-game audit set, read by hand.
