# Master Duel CPU behaviour in the pilot

The pilot borrows behaviour (not code) from Master Duel's CPU opponent, which lives in the game's
`masterduel_Data/Plugins/x86_64/duel.dll` (`YUGI_PC/src/duelsys/think/cpu_think.c`). Two layers:

1. **Battle rules** (`wsl/board.py`, used by `hint_priors` and `respond`; `YGOSIM_CPU_RULES=0` turns them off):
   lethal check (enter the Battle Phase and keep attacking when the board's damage reaches the
   opponent's LP), no attacks with 0-ATK monsters, and the CPU's summon-position rule.
2. **Per-card handlers** (`wsl/card_handlers.py`; `YGOSIM_CARD_HANDLERS=1` turns them on): Konami
   keeps its card knowledge in switches on card ID inside the think code. Each handler restates one
   card's branch as prior offsets, like `card_tags` hints, for both players' decisions.

Engine side, `goldfish_info.inc` adds `info:field_stats_` (per Monster Zone slot: current ATK, DEF,
position) and names the card at position prompts (`option_card_` at MSG_SELECT_POSITION).

## Refreshing the per-card handlers

Run after adding decks, or after a Master Duel update (IDs and addresses move). Steps 1, 2, 4 are
stdlib Python; step 3 needs Ghidra through REA (`rea-agents`, `GHIDRA_INSTALL_DIR`,
`REA_GHIDRA_STARTUP_TIMEOUT_MS=7200000`: the first analysis of duel.dll takes ~10-20 minutes).
Keep WORK outside the repo: it holds decompiled Konami code, which must not be committed.

1. Pool: `python tools/konami_ai/pool.py ~/ygo/run/decks ".../YgoMaster/Data/YdkIds.txt" ~/ygo/run/cards.cdb WORK`
   maps the field decks' passcodes to Master Duel IDs (YgoMaster's table). Cards Master Duel doesn't
   have yet are listed and skipped.
2. AI functions: `python tools/konami_ai/ai_functions.py DUEL_DLL WORK` finds the think functions
   (CPU debug-string references, readers of the CPU setting, and their AI-only callees) and splits
   them into decompile batches (`WORK/batches.json`).
3. Decompile: open duel.dll with REA's Ghidra provider and run `batch_decompile` on each batch; save
   each result with `python tools/konami_ai/save_batch.py RESULT.json WORK`.
4. Evidence: `python tools/konami_ai/index_cards.py WORK` writes `WORK/evidence/<passcode>.txt`:
   every block of think code that names the card, with the card text. Cards with no blocks
   (`no_ai_refs.txt`) get Konami's generic handling only, which the battle rules cover.
5. Specs: read each evidence file with `tools/konami_ai/GLOSSARY.md` (state layout, helper meanings)
   and write one line per card to `wsl/cpu_handler_specs.jsonl`: decision (activate, chain_response,
   select_target, select_cost, select_material, summon, position, attack), when, prefer, strength
   (always / usually / tiebreak), confidence, evidence (function:line). Plain game terms only:
   never paste pseudocode into specs or handlers.
6. Handlers: implement the high/medium-confidence rules in `wsl/card_handlers.py` with
   `@on_option` (options naming the card) or `@on_select` (candidates while the card's effect is
   choosing), offsets `ALWAYS` / `USUALLY` / `TIEBREAK`. Cite the spec in a comment.
7. Check: paired A/B on shared deals (`YGOSIM_LOG_DIR` keeps experiment logs out of the fit data),
   handlers on vs off.

First run (2026-10-15, duel.dll SHA-256 97bd4d13...): 303 field-deck cards, 295 in Master Duel,
622 AI functions, 111 cards with card-specific blocks, 184 generic. Specs: 2 high, 41 medium, 68 low
confidence (low = the branch depends on helpers we couldn't identify). Most medium rules restate Konami's
own lookahead ("simulate the effect, activate if the board scores better"), which the rollout search
already does; the handlers cover the rest: Engage!'s search, Lava Golem, Triple Tactics Talent, Albion,
Roze's Extra Monster Zone removal, Stardust / Accel Synchro Stardust, Chaos Angel's materials,
Fraktall -> Kitt, GY fodder (Druiswurm, Malong, Witch), Called by the Grave, Heavy Polymerization,
S:P Little Knight, Shark Cannon / Widow Anchor. Not yet expressible: Crossout Designator (needs our
Deck list and the declared name; MSG_ANNOUNCE_CARD is auto-answered), zone choices (Raye's Link to the
Extra Monster Zone, Firewall / Relinquished Anima arrows; place prompts don't name zones), and threat
awareness of the opponent's Exciton Knight / Mirrorjade (evaluation features, not hints).
