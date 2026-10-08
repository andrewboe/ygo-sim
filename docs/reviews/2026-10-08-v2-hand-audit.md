# Hand audit: pilot v2 (policy commit, designed eval, hand-trap hints, re-planning)

Games: Chaos Ritual Dogmatika/Stardust + backrow (P0, first) vs Elfnote (P1), deals 90000 and 90001.
Logs: data/review/cand__chaos-ritual__dogmatika-stardust__backrow__elfnote__tcg__9000{0,1}.txt

## Game 90000 (Elfnote wins, turn 6)
- T1 P0 (brick: 2 Evenly Matched, Droll, Blazing Cartesia, Purulia): normal summons Cartesia, passes.
  **Wrong.** Evenly Matched is either set (live at the end of P1's turn-2 Battle Phase) or held with an
  empty field (it can be activated from the hand only if you control no cards). Summoning Cartesia and
  holding both made them dead on turn 2 until Cartesia died.
- T2 P1 combo. P0 Droll in response to Power Patron's search: **right.** P0 held Purulia through the
  whole combo: **wrong** (it should go at the start of the turn against a deck that summons from hand
  this often). After Cartesia died, P0 controlled no cards at the end of P1's Battle Phase and passed
  with Evenly Matched in hand: **big miss** (it would have banished Strelitzia, Dawn Dragster, Rhapsodia).
- T3 P0 sets both Evenly Matched: right. P1 chains Strelitzia then its own Ghost Ogre: probably a
  wasted Ghost Ogre (can't tell the target from the log).
- T4 P1 makes a 4-card board and **skips the Battle Phase against an open board** with 7,400 LP to take.
  Consistent with knowing the two face-down cards are Evenly Matched (information leak).
- T5 P0 Celtic Mystic -> Griffoh -> Ragged Records -> Black Chaos, attacks: reasonable. Evenly Matched
  was live at the end of P0's own Battle Phase (4 vs 3 cards): small miss.
- T6 P1 attacks for lethal; P0 Droll on a search: right.

## Game 90001 (Chaos Ritual wins, turn 5)
- T1 P0 brick (3 Mulcharmy, Fydraulis, Evenly Matched): holds everything: **right.** P1 activates
  Purulia at the start of P0's turn and P0 never summons: wasted, minor.
- T2 P0 two Fuwalos at the start of P1's turn, Ash on Theorealize's search, Fydraulis Harmonia on
  Junoldo, Fuwalos end-phase check: **all right.** P1 ends on Junora + Welcome Home and holds Ghost
  Belle instead of summoning it: right.
- T3 P0 Fallen of Albaz fuses with P1's Junora into Titaniklad, attacks for 6,400: **strong play.**
- T4 P1 Welcome Home search, Ash'd by P0: right. T5 P0 lethal.

## Verdict
The v2 fixes hold: hand traps are kept and used on real targets (Ash on searches, Fydraulis on
effects), combos and lethal are found. Remaining systemic problems, in priority order:
1. **Non-turn-player timing outside "respond to an activation".** The responder heuristic only acts
   right after an activation or summon, so Evenly Matched (end of Battle Phase) is never used and
   Mulcharmy timing is inconsistent. Fix: at windows where the non-turn player holds a live
   interruption, compare use-now vs hold by playing out the rest of the turn both ways.
2. **Evaluation has no opponent-hand term.** Draws from Mulcharmy are worth nothing to the responder
   under the turn player's evaluation. Fix: opp_hand -0.3 (mirror of own_hand). Applied.
3. **Information leak**: battle skipped into known face-down Evenly Matched. Fix: belief model with
   set-card identities sampled too.
4. Conditional hand traps (Evenly Matched from hand needs an empty field) are valued unconditionally.
   Low priority.

Large runs stay on hold until 1 and 3 are fixed and a new audit passes.
