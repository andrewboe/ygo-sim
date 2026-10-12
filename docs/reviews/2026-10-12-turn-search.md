# Turn-1 search: shaped evaluation and budget (2026-10-12)

## Deceptive landscape (Elfnote 203621: Regina, Medius, Purulia, Ghost Ogre, Ash)
A per-generation log showed searches from the root top out around 2.0-3.35, with "end the turn" at 2.7.
Re-plans from mid-combo positions reach 6.15. Holding an empty-field hand trap (Purulia) made every
partial combo score below doing nothing, so the search ended the turn (0 on 2 of 3 seeds).
Fix: search_turn adapts on a shaped score without the empty-field hand-trap value, and tracks the true
score; the final line is the best by true score, so ending the turn holding a Mulcharmy still wins
when it really is best. Seeds 0/1/2 without the breaker: 2.75 / 2.25 / 2.25 (was 0.75 / 3.25 / 1.50
with halving, 4.25 / 0 / 0 with one run). Hands without such traps are unaffected (identical boards).

## Budget, 30 vs 60 gens on turns 1-2 (S1, 4 decks x 3 deals, live without the breaker)
| Deck | 30 gens | 60 gens |
|---|---|---|
| Elfnote | 3.50 / 2.75 / 0.00 | 2.50 / 1.00 / 2.50 |
| Mitsurugi Yummy | 1.75 / 2.25 / 1.00 | 1.75 / 3.00 / 2.25 |
| Branded | 1.25 / 2.50 / 1.75 | 1.00 / 2.25 / 3.25 |
| Maliss | 0.50 / 2.50 / 2.25 | 2.75 / 2.50 / 1.50 |
Mean 1.83 vs 2.19 (+19%); 6 better, 4 worse, 2 tied (about 1 SE). Adopted: OPENING_BOOST 6.
Elfnote 203622 (Ghost Belle, Power Patron, Harmonia, Fuwalos, Vidolium) was called a brick on
2026-10-09. At 60 gens it builds Strelitzia + Accel Synchro Stardust + Vidolium (2.50), so that
verdict was wrong.

Still open: per-deal variance is about 1 interruption, so board comparisons need several deals.

## Full suite after the changes (2026-10-12; 60 gens, shaped search, dead-trap value)
S1, 3 deals per deck, mean live interruptions without the breaker (2026-10-09 baseline in brackets;
same per-deck deal seeds, though the old pilot may have drawn the same hands differently):
Branded 2.33 (1.67), Maliss 2.25 (1.75), Invoked 2.17 (1.00), Elfnote 2.00 (1.17), DM Chaos Ritual
1.83 (1.92), Chaos Ritual 1.75 (0.50), Lunalight 1.67 (1.00), Mitsurugi Yummy 1.58 (3.17),
Sky Striker 1.50 (1.67), Mitsurugi 1.42 (0.33), Magistus 1.00 (0.83), Blitzclique 0.92 (1.00).
Field mean 1.69 (1.33). Empty boards: Blitzclique 288942 and Magistus 240051 (not yet checked as bricks).
S2 into Ash (95000 / 95001, no breaker): Elfnote 1.00 / 3.75 (was 3.25 / 2.75), DM 0.00 / 1.25
(was 0.00 / 2.00), Mitsurugi Yummy 1.25 / 3.00 (unchanged). Ash was used only in DM 95000, which
still ends on Relinquished Anima alone after Ash.

Open:
- DM into Ash, deal 95000: no recovery line (0 both times).
- Mitsurugi Yummy S1 dropped (3.17 to 1.58). Check whether the 2026-10-09 hands match today's.
- Check the two empty boards for real bricks (203622 was not one).

## Follow-ups (2026-10-12)
- Like-for-like on the 2026-10-09 deals (94000-94002): field mean 1.85 vs 1.33 (+39%). Mitsurugi Yummy
  3.08 vs 3.17: the earlier "drop" was different hands. Magistus 0.83 to 2.50, Sky Striker 1.67 to 2.92;
  no deck worse beyond noise.
- Empty boards: Blitzclique 288942 is a true brick (Surge needs a monster to target, Whisker needs a
  destruction, Dominus Purge needs an opponent's card). Magistus 240051 was an evaluation bug: two
  different Mulcharmys counted as two interruptions, but only one can be activated per turn. Now
  Mulcharmys count once; that hand builds 7 cards (1.50). Other Mulcharmy hands are unchanged.
- DM into Ash 95000 (Black Chaos, WANTED, Magicians' Souls, Fuwalos, Hallowed Azamina; Ash on
  WANTED): ends on Relinquished Anima. Possible lines via Souls (send DM, revive it) are unclear
  to me; needs a human check.
