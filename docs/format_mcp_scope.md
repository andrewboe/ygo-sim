# Yu-Gi-Oh format MCP: scope (draft for approval)

Status: approved 2026-10-20. **Phase 0 and Phase 1 (`validate_deck`) are built**:
- `ygosim/carddata.py` builds `data/cards.sqlite`.
- `ygosim/formats.py` holds the format registry, the strict parser and the validator.
- `ygosim/mcp_server.py` is the stdio MCP server, registered at user scope as `ygo-format`.
- CLI: `ygosim validate`, `ygosim cards-refresh`.
- Tests: `tests/test_formats.py` (25 pass).

Differences from the plan below:
- `Deck.from_ydk` is not made strict yet; the strict parser lives in `formats.py`, so simulator code is untouched.
- Both Genesys point sets (TCG and OCG) are fetched now.
- The dump is cached as `data/cards_genesys.json`, alongside the simulator's `cards.json`.

## 1. Recommendation

Build a small stdio MCP server **inside ygo-sim** (`ygosim/formats.py` + `ygosim/mcp_server.py`). It reuses the card DB, two-source banlist and `.ydk` code that ygo-sim already has, and adds a format layer (Advanced, Genesys) on top. Ship `validate_deck` first and on its own. Add `card_lookup`, `points_delta` and a data-status tool only after `validate_deck` has caught real mistakes.

Most of the plumbing already exists. The new work is:
- Genesys points, which the current dump doesn't fetch.
- A format registry.
- A strict `.ydk` parser.
- Freshness metadata on every answer.
- The MCP wrapper.

## 2. What already exists

| Source | What it has | Gaps for this tool |
|---|---|---|
| `ygosim/api.py` | YGOPRODeck v7 client, 0.25 s rate limit, `cached()` JSON-on-disk with a max age | Age comes from the file mtime only. Doesn't record the DB version or the fetch date. |
| `ygosim/cards.py` → `card_db()` | `data/cards.json` (`misc=yes`, 14,599 cards, fetched 2026-10-09). Alt-art passcodes map to the canonical id. Has `tcg_date` (falls back to the earliest TCG set date) and `is_extra`. | **No Genesys points:** the fetch doesn't pass `format=genesys`. Doesn't keep level, attribute, race, ATK/DEF, `ban_ocg`/`ban_goat` or `ocg_date`. `by_name` is exact-match only. |
| `ygosim/banlist.py` → `tcg_banlist()` | TCG F&L from YGOPRODeck `ban_tcg` and Project Ignis `0TCG.lflist.conf`, **stricter wins**, conflicts listed. Ignis title gives the list name (currently `2026.09 TCG`). | TCG only |
| `ygosim/deck.py` → `Deck.legality_errors(as_of)` | Advanced legality: 40–60 main, ≤15 extra, ≤15 side, ≤3 copies by canonical id, F&L, TCG release by `as_of`, and extra-deck cards in the right zone. Already fails closed on unknown ids. | **`from_ydk` silently skips any non-digit line.** A trailing comment, `#side` instead of `!side`, or a stray character drops the card. That fits the "36-card file" incident. It also accepts zero-count edge cases quietly. Doesn't catch Tokens or Skill cards. |
| `tests/test_legality.py` | 5 tests (filler deck, 4 copies, Forbidden, alt-art dodge, alt-art counting) | No Genesys tests, no parser tests |
| `~/ygo/run/cards.cdb` (WSL, EDOPro) | What the simulator can actually play | Lags new sets (BETB). Use it only as an optional "sim-ready" flag, never as the source of truth. |
| YGO cart optimizer | Planned, not built: no YGO code in `andrewboe/andrew-portfolio` `main`, and `Desktop/tcgmizer` is the upstream clone | Nothing to reuse yet. It could read the same SQLite file later. |
| Claude Code MCP config | Only `rea` is registered (user scope). No YGO MCP, no Vizier. | — |

Verified live against the API today (DB version 147.37, last update 2026-10-16 16:01):
- `format=genesys&misc=yes` returns the full pool in one request: 14,618 cards, 25 MB, 0.5 s. Every card has `misc_info[0].genesys_points`. 750 cards have points above zero, and the highest is 100 (Zaborg, Vanity's Fiend/Ruler/Emptiness, XX-Saber Gottoms).
- `format=genesys ocg` (with a space; `genesys_ocg` is rejected) returns `genesys_ocg_points` instead.
- Every card carries `banlist_info` with `ban_tcg`, `ban_ocg` and `ban_goat`. There's no Master Duel ban field.
- `checkDBVer.php` returns `{database_version, last_update}` and is a cheap staleness probe.
- Neither the API nor Konami's Genesys page gives a "points list effective date". The only "as of" available is our fetch time plus the YGOPRODeck DB version.

## 3. Where it lives and how it runs

- **Code:** new files in ygo-sim. `ygosim/formats.py` holds the format registry and validator. `ygosim/carddata.py` handles the SQLite build, or extends `cards.py`. `ygosim/mcp_server.py` is the FastMCP wrapper. `mcp` goes in as an optional extra in `pyproject.toml` (`pip install -e .[mcp]`).
  - Existing modules change only slightly: `cards.py` gains fields, and `Deck.from_ydk` becomes strict.
  - This avoids the other session's files (pilots, executors, `wsl/`, the `ygo-sim-ab` worktree).
- **Runtime:** Windows Python 3.12, the same interpreter ygo-sim already uses. Data stays in `ygo-sim/data/`. It doesn't depend on WSL.
- **Registration (user scope)**, so every conversation gets it:
  `claude mcp add --scope user ygo-format -- python -m ygosim.mcp_server`
  The working directory comes from the package path, so `DATA_DIR` resolves without a cwd.
- **CLI twin:** `ygosim validate deck.ydk --format genesys`, the same core function, for use outside Claude.
- **Alternative considered:** a separate repo with its own cache. Rejected: it duplicates the banlist logic, which is exactly the part that drifts. It's worth revisiting only if the cart optimizer (TypeScript) needs the code rather than just the SQLite file.

## 4. Data and caching

- **Raw cache** (as today, in `data/`):
  - `cards_genesys.json` (`format=genesys&misc=yes`). This replaces `cards.json` because it's a superset with the same fields plus points.
  - `cards_genesys_ocg.json` (phase 3).
  - `cardsets.json`.
  - Ignis `0TCG.lflist.conf`.
- **Derived index `data/cards.sqlite`**, rebuilt on every refresh in about 2 s:
  - `cards(id PK, canonical_id, name, name_norm, type, frame_type, race, attribute, level, atk, def, linkval, desc, archetype, tcg_date, ocg_date, beta_name, konami_id)`. Alt-art passcodes are rows that point to `canonical_id`.
  - `limits(format, canonical_id, limit, source)`, where `source` is `ygoprodeck`, `ignis` or `min`.
  - `points(format, canonical_id, points)`.
  - `points_history(fetch_id, format, canonical_id, points)`. Rows are written only when points change, so "Illusion Gate went 7 → 10 on <date>" is answerable.
  - `fetches(fetch_id, fetched_at, ygoprodeck_db_version, ygoprodeck_last_update, ignis_list_title, sha256)`.
- **Why SQLite** rather than the in-memory dict: points history and as-of queries, fast MCP startup (no 25 MB JSON parse per launch) and normalized-name search. The TS cart optimizer can also read it later.
- **Refresh:**
  - Run it with `refresh_data` (a tool and a CLI command). It fetches 2–4 requests in total, far below the 20 req/s limit.
  - On server start: if the last fetch is older than 24 h, call `checkDBVer`, and refetch only if the version changed.
  - An optional Windows scheduled task (`ygosim refresh-cards`, daily) is phase 3. ygo-sim's existing `refresh` doesn't get scheduled; your earlier decision stands.

## 5. Format model

One `FormatSpec` per format. Rules are data, so a rule change from Konami is a one-line edit.

```python
@dataclass(frozen=True)
class FormatSpec:
    key: str                    # "tcg_advanced", "genesys"
    region: str                 # "tcg" | "ocg"  -> which release date gates the pool
    main: tuple[int, int] = (40, 60)
    extra_max: int = 15
    side_max: int = 15
    max_copies: int = 3
    limits: str | None          # limits table key, or None if no F&L applies
    points: str | None          # points table key, or None
    default_cap: int | None     # 100 for Genesys; overridable per call
    banned_frames: frozenset[str] = frozenset()   # e.g. {"link", "pendulum"}
    banned_types: frozenset[str] = frozenset({"Token", "Skill Card"})
```

| Rule | TCG Advanced | Genesys (TCG) |
|---|---|---|
| Deck sizes | 40–60 / ≤15 / ≤15 | Same |
| Copies | ≤3 per canonical id, summed across main, extra and side | Same |
| Card pool | `tcg_date ≤ as_of` | Same |
| F&L | `min(ygoprodeck ban_tcg, Ignis 0TCG)`, conflicts reported | **Not used.** Konami: "The standard Forbidden & Limited Cards list is not used." |
| Points | — | Main + Extra + **Side** total ≤ cap. Cap defaults to 100 and is a per-call parameter (stores run 0, 50, 200 events). |
| Banned frames | — | Any Link or Pendulum Monster, in any zone including Side (match on `frameType`: `link`, `*_pendulum`) |
| Zones | Extra types (Fusion/Synchro/XYZ/Link) only in Extra | Same |

Later formats (each about half a day; data source in brackets):
- **OCG Advanced:** `region=ocg`, `ban_ocg` + Ignis `0OCG.lflist.conf`.
- **Genesys OCG:** `region=ocg`, `genesys_ocg_points`, launched 2026-03-10.
- **GOAT:** `ban_goat` + Ignis GOAT list, pool cut off by date.
- **Master Duel:** YGOPRODeck has a `master duel` pool filter but **no MD ban field**. Needs another list (Ignis if it has one, or MDM). This is the only one with an unsolved source.

## 6. Tools

Every response carries the same freshness block:

```json
"data": {"fetched_at": "2026-10-20T14:02Z", "ygoprodeck_db": "147.37 (2026-10-16 16:01)",
         "tcg_list": "2026.09 TCG", "stale": false,
         "note": "Genesys points as published on YGOPRODeck at fetch time; Konami publishes no effective date."}
```

`stale` is true if the fetch is older than 7 days or `checkDBVer` reports a newer version. The tool descriptions tell Claude to quote the `as of` date whenever it states points or ban status.

### Phase 1 (on its own): `validate_deck`

```
validate_deck(
  format: "tcg_advanced" | "genesys",
  ydk_path: str | None = None,       # one of these three
  ydk_text: str | None = None,       #   .ydk contents or ydke:// URL
  decklist: {main: [str], extra: [str], side: [str]} | None = None,  # "3 Ash Blossom & Joyous Spring" / passcodes
  point_cap: int | None = None,      # Genesys only; default 100
  as_of: "YYYY-MM-DD" | None = None, # release-date gate; default today
) -> {
  "legal": false,
  "summary": "ILLEGAL in Genesys (cap 100): 2 problems. Points 104/100 (Main 82, Extra 0, Side 22). Main 40, Extra 15, Side 15.",
  "problems": [
    "Paleozoic Cambroraster (36346532, Extra): Link Monster, not allowed in Genesys",
    "Points 104 > cap 100"
  ],
  "cards": [  // one row per distinct canonical card, grouped by zone
    {"zone": "main", "count": 1, "passcode": 33017964, "name": "Illusion Gate",
     "type": "Spell Card", "limit": 3, "points": 10, "points_total": 10, "flags": []}
  ],
  "totals": {"main": {"cards": 40, "points": 82}, "extra": {...}, "side": {...}, "deck_points": 104},
  "data": {...freshness...}
}
```

Behaviour:
- **Fails loudly and doesn't validate** if any input is unresolved. It returns `"legal": null` with `parse_errors` listing line numbers. Covered cases:
  - Unknown passcodes.
  - Unknown or ambiguous names. Candidates are listed, never auto-picked.
  - Unrecognized `.ydk` lines and duplicate section headers.
  - A file whose card count doesn't match the lines read.
- Alt-art passcodes are normalized and shown with the canonical id.
- `limit` in each row is the format's effective limit, so Genesys shows 3 for Herald of the Arc Light.
- Rows are kept compact: no card text in this tool. An optional `sim_ready` flag is phase 3; it means "passcode present in EDOPro cards.cdb".

### Phase 2

```
card_lookup(query: str | int, formats: [str] = ["tcg_advanced","genesys"], include_text: bool = true)
  -> {"match": "exact" | "normalized" | "ambiguous" | "none",
      "cards": [{"passcode", "alt_passcodes", "name", "type", "frame", "attribute", "race",
                 "level|rank|link", "atk", "def", "text", "archetype", "tcg_date",
                 "status": {"tcg_advanced": {"limit": 1, "label": "Limited", "sources": {...}},
                            "genesys": {"legal": true, "points": 0}}}],
      "candidates": [...], "data": {...}}
```

- **Name resolution:** exact first, then normalized (case-folded, punctuation and whitespace collapsed, ☆/★ kept distinct but searchable), then `beta_name` aliases, then fuzzy candidates only.
- ☆ and ★ must stay distinct: Cupsy☆Yummy (Limited) and Cupsy★Yummy Way (Forbidden) are different cards.

```
points_delta(remove: [str|int], add: [str|int], current_points: int | None = None, point_cap: int = 100)
  -> {"removed": [{"name", "points"}], "added": [...], "delta": +8,
      "new_total": 98, "within_cap": true, "data": {...}}

data_status() -> freshness block + counts + last 5 points changes
refresh_data(force: bool = false) -> what changed (DB version, list title, points changes)
```

- `points_delta` takes lists, so swaps like 2-for-1 work.
- `refresh_data` is behind the normal MCP tool-approval prompt.

### Phase 3+ (only if needed)

- `search_cards(filters)`, such as "Genesys 0-point Level 4 LIGHT Spellcasters".
- `points_changes(since)`.
- `diff_formats(ydk)`: one deck checked against every registered format.

**Out of scope: rulings.** The tools never answer rulings questions. The descriptions say so explicitly, to stop Claude laundering a guess through a tool call. YGOrganization and the Konami DB are scrape-only. Revisit as a separate project if you want it.

## 7. Phases and effort

| Phase | Contents | Effort (Claude session time) |
|---|---|---|
| 0. Data | Genesys fetch, SQLite build, `fetches` metadata, `FormatSpec` registry, strict `.ydk`/`ydke`/name-list parser | ~0.5 day |
| 1. `validate_deck` | Core validator (Advanced + Genesys), MCP wrapper, CLI twin, registration, tests below | ~1 day |
| *Use it for a week or two of deck work* | | |
| 2. Lookups | `card_lookup`, `points_delta`, `data_status`, `refresh_data` | ~0.5 day |
| 3. Freshness/extras | Points history diffs, optional scheduled refresh, `sim_ready` flag, Genesys OCG | ~0.5 day |
| 4. More formats | OCG Advanced, GOAT (~0.5 day each); Master Duel once a ban-list source is chosen | 1–1.5 days |

## 8. Tests from the known mistakes

Tests run against a pinned fixture: a ~40-card subset of the dump plus an lflist snapshot under `tests/fixtures/`, so Konami point changes don't break CI. A separate `-m live` test re-checks the same facts against current data and reports drift instead of failing.

| Mistake | Card (passcode) | Expected |
|---|---|---|
| Cambroraster is a Link | Paleozoic Cambroraster (36346532), `Link Monster` | Genesys: illegal ("Link Monster"), including when it's only in the Side Deck. Advanced: legal. |
| Herald was banned | Herald of the Arc Light (79606837), `ban_tcg` Forbidden | Advanced: illegal at 1 copy. Genesys: legal, 0 pts (F&L not used). |
| Eclipse is pointed | Eclipse Wyvern (51858306): Forbidden TCG, 11 pts | Advanced: illegal. Genesys: legal and contributes 11. *Confirm this is the "Eclipse" you meant.* |
| D.D. Ground is pointed | Different Dimension Ground (31849106), 10 pts | Shorthand "D.D. Ground" fails as ambiguous or not found with candidates, and is **not** silently resolved. The full name gives 10 pts. |
| Illusion Gate is pointed | Illusion Gate (33017964), 10 pts | 10 per copy |
| Cupsy is limited | Cupsy☆Yummy (31425736), Limited | Advanced: 2 copies illegal. "Cupsy★Yummy Way" (31603289, Forbidden) resolves to a different card. |
| Dreadnought Servant passcode wrong | Destiny HERO - Dreadnought Servant (98931282), BETB, TCG 2026-10-08 | A wrong passcode means `legal: null` with "unknown passcode" and no partial result. `as_of=2026-10-07` gives "not TCG-released". |
| 36-card file lost cards | Synthetic `.ydk` | Trailing comments, garbage lines and the `#side` typo each give a parse error with a line number. CRLF and BOM are accepted (EDOPro reads them), but CRLF gives a warning because ygoenv's parser drops `
`-terminated card lines. A 36-card main gives "main deck has 36 cards". |

Plus:
- Points cap edges: exactly 100 passes, 101 fails, Side Deck points count, `point_cap=50`.
- Alt-art counting, already covered by the existing tests.
- Extra card in Main.
- Token or Skill card rejected.
- Freshness: `stale` flips when `fetched_at` is older than 7 days.

## 9. Risks

- **YGOPRODeck points can lag or be wrong after a Konami points update**, and there's no effective date to check against.
  - Mitigation: record the DB version and fetch time on every answer; keep points history; and in phase 3, optionally cross-check against Konami's official Genesys list.
  - Vizier could be a second source, but it has the same staleness concern.
- **Name resolution** is where conversational mistakes come from: ☆/★, TCG vs OCG names, shorthand.
  - Mitigation: never auto-pick a fuzzy match inside `validate_deck`.
- **Event-specific caps and future rule changes**, such as Konami allowing Pendulums. Handled by `point_cap` and by keeping the format rules as data.
- **Shared repo:** ygo-sim is under active AI work in another session.
  - Mitigation: new files only, plus a small, tested change to `cards.py` and `Deck.from_ydk`.
  - Making `from_ydk` strict could surface existing malformed `.ydk` files in `data/` or WSL decks. That's desired, but run it over the existing decks once before merging.
- **Data volume:** switching the cache to the Genesys dump adds about 0 requests and roughly the same 25 MB. The ~1 s first-load cost goes away with SQLite.
- **Master Duel ban source** is unresolved (see §5).

## 10. Decisions

1. Build inside ygo-sim: **approved** (2026-10-20).
2. This doc lives at `docs/format_mcp_scope.md`.
3. Open: replace `data/cards.json` with the Genesys dump everywhere, or keep both. For now the format layer uses its own `data/cards.sqlite` built from the Genesys dump, and the existing simulator code is untouched.
4. Open: confirm which "Eclipse" card the mistake referred to (the tests use Eclipse Wyvern).
