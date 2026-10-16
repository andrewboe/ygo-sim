# Card-specific rules from WindBot

Goal: card-specific behaviour for both players' decisions, as priors the search can overrule
(`wsl/card_handlers.py`), sourced from the open-source WindBot AI rather than guessed.

## Sources (2026-10-15 survey of the 303 field-deck cards)

| Source | License | Pool cards covered | Notes |
|---|---|---|---|
| IceYGO/windbot | MIT | 186 | 73 deck executors; Elfnote, ChaosRitual, Maliss, SkyStriker, DarkMagician, Ryzeal match field decks; DefaultExecutor covers staples |
| ProjectIgnis/windbot (EDOPro) | AGPL-3.0 | 154 (+3 not in IceYGO) | behaviour only |
| Master Duel CPU (Konami, decompiled) | proprietary | 111 (23 not in WindBot) | specs in `wsl/cpu_handler_specs.jsonl`, behaviour only (docs/cpu_handlers.md) |
| YGO Omega | closed | - | AI is WindBot-derived and not published |

Any source: 212 cards; neither WindBot nor Konami: 91 (left to the search and card_tags).
Per deck (any source / deck size): blitzclique 22/34, branded 35/42, chaos-ritual 41/43, dm-chaos-ritual 38/57,
elfnote 40/44, invoked 26/40, lunalight 29/39, magistus-fairy-tail 23/49, maliss 39/41, mitsurugi-yummy 47/58,
mitsurugi 29/42, sky-striker 30/37.

## Phases

1. **Context + WindBot layer** (done). Engine info: every zone's cards with position/ATK/DEF/level/Xyz
   materials (`zone_cards_`), GY and banished split, own Deck / Extra Deck (`YGOSIM_CONTEXT`), phase, the
   chain and its targets, the last summon, each option's zone and effect description (WindBot's
   ActivateDescription). `wsl/windbot.py`: Bot / Enemy / Duel / Util / AI / Card / ExecutorType with
   WindBot's names, hidden information masked; `card_handlers.py` runs one executor per (env, player),
   scores options by WindBot's first-passing-row rule, keeps side effects (flags, AI.SelectCard queues) only
   for the option actually chosen.
2. **DefaultExecutor port**: staples used across decks (Ash, Called by the Grave, Imperm, Nibiru, Maxx "C",
   Veiler, Droll, Ghost Belle, Solemns...) and default reposition / battle-phase rules.
3. **Deck executors**: one module per WindBot executor mapped to field decks (`DECK_EXECUTORS`), in coverage
   order: Elfnote, ChaosRitual, Maliss, SkyStriker, DarkMagician, Ryzeal (Blitzclique builds), then
   Albaz/Dogmatika rules for Branded. Ported rule by rule from IceYGO (MIT, keep attribution).
4. **Gaps**: Konami-only cards from the specs; cards neither covers stay with the search.
5. **Validation**: unit tests per executor on built boards, the live firing test, then paired A/Bs big
   enough to mean something (~60 games per arm, overnight), plus review.py flag deltas.

## Known limits of the layer

- `IsDisabled`, equips/targets relations, counters, which monsters already attacked: not exposed.
- Xyz material codes: only counts. Effect descriptions: only for the option's own card (another card's
  granted effect reads -1).
- Rollouts replay earlier turns without running executors, so per-game executor flags set before the
  searched turn are lost; per-turn flags (most of WindBot's) are unaffected.
- Executors run for the turn player's search priors and the other player's `respond()`; both players use
  the executor of their own deck.
