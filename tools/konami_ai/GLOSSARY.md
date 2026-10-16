# Reading Master Duel CPU AI snippets (Ghidra pseudocode of duel.dll)

Each evidence/<passcode>.txt holds every block of Konami's CPU think code that names that card,
found in 217 AI functions. Card IDs in the code are Master Duel internal IDs (the header gives the
card's MD ID; `0x353f` etc. in the code). Other hex IDs in the same block are other cards.

## Global state
- `DAT_1811f9c50` duel state. Per-player block = `(player & 1) * 0xddc`.
  - LP at block+0, XOR-masked: `*DAT_1811f9c48 & 0xffff ^ value` = real LP.
  - Field zones: 0x1c-byte slots at block + 0x5c + zone*0x1c, zone 0-4 Main Monster Zones, 5-6 Extra
    Monster Zones, 7-11 Spell/Trap, 12 field. Card id short at slot+0x5c, owner/unique bits slot+0x5e,
    position byte slot+0x62 (0 = attack position), face-up flag slot+0x63; flags word at
    block + (zone+4)*0x1c (bit 0x20 = "no card/being removed"), slot+0x6c more flags.
  - Hand: count at block+0xc, card list at block+0x1e4 (4 bytes each).
  - `+0x3c08` turn player, `+0x3c1c` phase (2 = Main 1, 3-5 battle steps, ...), `+0x3c14` turn count
    (0 = first turn), `+0x1bb8` battle flags.
- `DAT_1811f9c48 + 0x18 + p*4` CPU setting of player p (flags: 0x40000000 Fool, 0x20000000 Light,
  0x10000000 MyTurnOnly, 0x04000000 AttackOnly, 0x03000000 Simple).
- `DAT_1811f9c30` the current selection list (count short at +10, entries 4 bytes at +0x18,
  per-entry flags at +0x4c8; flag bits 0x7fc0 = not selectable).
- `DAT_1811f9c58 + 0xa98` the effect/chain link being evaluated; `+0xa8c` chain length.
- `*DAT_1811f9c08` low bit = player being thought for ("me"); `DAT_1811f9c08[1]` = acting player.

## Helpers (meaning inferred from their bodies)
- `FUN_180b048b0(p, zone)` zone bitmask bit: 1 << (zone + 16*p).
- `FUN_1807a4d80(p, zone)` card id in that field zone (alias-resolved).
- `FUN_1800319a0(p, zone, 1, 0)` raw card id in a zone.
- `FUN_180060640(p, card, p2, loc, ...)` how many of `card` player p has (face-up) in loc (0x12 = field);
  nonzero = "p controls card".
- `FUN_18063ae60 / FUN_18000c3c0(p, loc, card, ...)` count of card in a location (0xd = graveyard-ish
  location code; 1000+ ids are effect/category codes, not cards).
- `FUN_180066100(p)` number of monsters p controls.
- `FUN_180ea8190(a, b)` a and b are the same card (alt arts folded).
- `FUN_180ea8930(card)` card id is valid.  `FUN_180ea7f30(card)` printed ATK of card.
- `FUN_180c24ae0(uid)` card id from unique id.  `FUN_1807cefa0(p, zone)` cached monster stats
  (+8 current ATK, +0x10 current DEF in the cache record).
- `FUN_180aa8070(card) / FUN_180aa8280(p, card)` index of card in the current selection list (-1 none).
- `FUN_180c25100(n)` duel option flag n.  `FUN_180a95aa0(x, card)` card is in a per-turn usage list
  (already used/activated this turn).
- `FUN_180aeeed0(...)` CPU_GetChainWorkEx: starts simulating a chain (lookahead).
  `FUN_180bad020 / FUN_180bad140 / FUN_180bad2b0` save / restore the whole duel for lookahead.
- `FUN_18063c0b0(p, zone, kind, card, ...)` registers a planned action for that card (kind 2 = activate).
- `FUN_1809e3780` battle position choice; `FUN_1809f5bc0` max battle damage; `FUN_18067cff0` lethal check.
- `FUN_180eac800(file, line, msg)` debug assert (ignore).
- Return values: in "should I do X" handlers 0/1 = no/yes; in scoring handlers bigger = better;
  0xffffffff / -1 = not applicable.

## Spec format (one JSON object per line)
{"passcode": 12345678, "name": "...",
 "rules": [{"decision": "activate|chain_response|select_target|select_cost|select_material|summon|
                         position|attack|other",
            "when": "plain-language condition from the snippet (game terms, not code)",
            "prefer": "what the CPU does: activate / hold / pick the highest-ATK monster / avoid X ...",
            "strength": "always|usually|tiebreak"}],
 "generic": false,           # true when the snippets only list the card in a generic table
 "confidence": "high|medium|low",
 "evidence": ["FUN_...:line", ...],
 "notes": "anything unclear"}
Write behaviour in your own words in game terms. Never copy pseudocode into the spec.
