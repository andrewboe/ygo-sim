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
