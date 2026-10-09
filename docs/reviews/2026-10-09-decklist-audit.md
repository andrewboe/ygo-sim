# Decklist audit (2026-10-09), against docs/research/meta.md

## Legality
All 251 field and candidate lists pass the 2026-09-21 TCG list as sourced independently by the research
(Kewl Tune Rotary, Dimension Shifter and the other new Forbidden cards absent; Elfnote Tinia and Terminus
at 1; Branded in High Spirits at <= 2; Maxx "C" absent). No violations.

## Field composition
- Weights match post-ban topping shares (LDR ~24% across DM / non-DM builds, Elfnote ~18%, then
  Blitzclique, Mitsurugi, Invoked, Branded, Power Patron, Sky Striker, Maliss/Magistus/Yummy, Lunalight).
- Kewl Tune correctly excluded (Rotary Forbidden).
- Power Patron is an OCG projection that already includes BETB's Ars Magna engine: right for post-BETB.
- Toon is projected but not in the field: correct until it is TCG-legal (Magnificent Maestros, 2026-11-12).
  Add it then (Track B).
- Watch: Ars Magna Elfnote (the top OCG Elfnote build) isn't a separate TCG field entry yet; BETB-legal
  TCG results will show whether it displaces the current Elfnote list.

## Field lists vs post-ban averages (key cards, deviation >= 1 copy)
| Deck | Result |
|---|---|
| Elfnote | matches (Lucina 3, Regina 3, Tinia 1, Welcome Home 2, Medius, Vidolium, hand traps) |
| Invoked, Mitsurugi, Lunalight, Maliss | match |
| Dark Magician Chaos Ritual (60) | DM-heavy build: Curtain 3 (avg 2), Dominus Impulse 3 (1.8), Kuriboh 3 (1.5), Magician of Dark Chaos 1 (2.4). A legitimate variant (Paris-winner style), but heavier on DM/Dominus than average. |
| Sky Striker | Pot of Desires 3 (avg 1.6) |
| Blitzclique | Ash 3 (avg 1.6) |
| Branded | Aluber 3, Branded Opening 3 (avg 1.9 each) |

Verdict: the field lists are real, legal, representative lists; deviations are list-to-list variance
around the averages, not errors. Each is one representative list (the medoid of its cluster), so
within-deck variants (stage 0) remain the place to compare builds.

## Follow-ups (Track B)
1. Add Toon on 2026-11-12; refresh the field as BETB-legal TCG results arrive.
2. Release pipeline (docs/research/release_pipeline.md): poll YGOProDeck's cardinfo (misc=yes) for upcoming
   cards with tcg/ocg dates, EDOPro prerelease databases for scripts, OCG results for those cards; F&L
   polling (TCG lists come with 1-7 days' notice).
3. Consider the DM-heavy LDR list vs an average-weighted one when the field is refreshed.
