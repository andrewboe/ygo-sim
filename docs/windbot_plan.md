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
2. **DefaultExecutor port** (done). `wsl/windbot_default.py`: the Default* staple conditions, on-targeted and
   negation / search / draw checks, the message callbacks that track resolved hand traps (Called by the Grave,
   Lock Bird, Maxx "C" and the Mulcharmys, Mistaken Arrest, Dimension Shifter) and the battle rules
   (OnSelectAttackTarget, OnPreBattleBetween, 0-ATK monsters to Defense). `GenericExecutor` (staple rows,
   reposition, Spell/Trap sets) runs for decks without a deck executor.
3. **Deck executors** (in progress). Infrastructure (done): the engine's event ring (`events_`: MSG_MOVE,
   CHAINING, CHAIN_SOLVING/SOLVED/END, NEGATED, NEW_TURN/PHASE, POS_CHANGE, summons, BECOME_TARGET), select
   prompts (`select_`: hint, min/max, cancelable, sum; `select_cards_` candidates; `option_combo_` each
   option's candidates), yes/no and option descriptions, the resolving link and each link's description and
   activating player; `wsl/windbot_gameai.py` ports GameAI (row-major action choice, the AI.Select* stack,
   OnSelectCard / Sum / Tribute / Place / Position / Option / YesNo with WindBot's fallbacks) and replays the
   messages since each decision through the executor's callbacks. Porting guide: docs/windbot_porting.md;
   registry: `wsl/windbot_decks/__init__.py`. Ported (rule for rule): Elfnote, ChaosRitual, Maliss, SkyStriker
   and Albaz (for Branded). Not ported: Ryzeal, DarkMagician, Dogmatika (2-6 shared cards with our lists).
   WindBot's lists differ from ours (Sky Striker shares 10 of its 37 cards), and six field decks have no
   WindBot executor, so decks also get executors written from their current lines (docs/windbot_porting.md,
   "Writing an executor..."): Mitsurugi, Branded and Maliss so far. Goldfish A/B (best turn-1 board, 30
   openings, 16x5, interruptions): Mitsurugi 3.02 -> 4.46; Branded 3.08 (Albaz port 3.35) -> 4.68; Maliss
   3.81 (port 4.24) -> 5.26, and 3.69 (port 4.11) -> 5.43 on held-out openings. The registry runs our own
   executor where it beats the port.
4. **Gaps**: Konami-only cards from the specs; cards neither covers stay with the search.
5. **Validation**: unit tests per executor on built boards, the live firing test, then paired A/Bs big
   enough to mean something (~60 games per arm, overnight), plus review.py flag deltas.

## Known limits of the layer

- `IsDisabled`, equips/targets relations, counters, announces, link markers, which monsters already
  attacked, the battling monster: not exposed.
- Cards are rebuilt per decision; a card's identity is (Id, Controller, Location, Sequence), standing in for
  WindBot's object identity. Message callbacks see the chain state of their time but the current board.
- GameAI's last-resort defaults (first cards, pass, end turn) count only for deck executors; for the generic
  executor the search decides.
- Xyz material codes: only counts. Effect descriptions: only for the option's own card (another card's
  granted effect reads -1).
- Rollouts replay earlier turns without running executors, so per-game executor flags set before the
  searched turn are lost; per-turn flags (most of WindBot's) are unaffected.
- Executors run for the turn player's search priors and the other player's `respond()`; both players use
  the executor of their own deck.
