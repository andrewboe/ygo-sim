# External validation sources (2026-10-16)

Research subagent report, condensed.

## Going first vs second (the most rigorous figure available)
- **Master Duel WCS2026 replay stats (note.com/apkallone):** all 274 replayable matches.
  - Going first wins 65.3% (95% CI about 60–71%); WCS2025 was 69.7%. Mean game length 3.34 turns.
  - The advantage shrinks with hand traps: with 3+ hand traps, going first falls to 34.5% and going second rises to 52.3%.
- There's no equivalent for TCG paper play. Master Duel has a different card pool, so use it for direction and range only.

## Matchup data
- **YGOData (ygodata.com):** about 132k ranked DuelingBook matches with auto-classified decks and a row-vs-column matchup matrix. Last updated 2026-08-05, so pre-BETB.
  - Branded vs Mitsurugi 52.8% (n=248), vs Sky Striker 61.9% (n=299), vs L&D Ritual 41.4% (n=382), vs Blitzclique 46.4% (n=267).
  - Mitsurugi vs Elfnote 43.6% (n=259).
  - Access needs a real browser (HTTP 403 to scripts). No API or terms page found, and the site warns of classification errors.
- **Konami YCS coverage:** late-round pairings by player name only, no deck labels.
- **Master Duel Meta (MDM) in-game deck win rates:** compressed to 53–54%, with no matchup splits.

## Conversion rates
- No reliable published 2026 table.
- Conversion computed from posted decklists is inflated, because 0-X players rarely post lists.
- YCS Paris 2026 (2,588 players) top 8: 4 Elfnote, 3 L&D Ritual, 1 Kewl Tune; L&D Ritual won.

## Reference end boards
- No structured database. Sources:
  - Elfnote: MDM player write-ups and Road of the King OCG reports.
  - Mitsurugi: YGOrganization's FTK article.
  - Blitzclique: TCG Contender guide.
  - Branded: a paid Metafy class, not usable.
- Plan: hand-curate 3–5 canonical hands per deck, verify each in EDOPro, and use them as tests.

## Replays
- No bulk current-format dataset.
- `yugioh-benchmark` (MIT) converts DuelingBook replays into decision-agreement tests: a template, but with almost no data.
- DuelingBook's terms on scraping are unknown, so ask before any bulk collection.

## Usable as thresholds
- **Going-first rate:** band 58–72% for meta-vs-meta games; fail outside 55–75%. Hand traps must measurably reduce the edge.
- **Matchup direction:** YGOData cells with n≥200, testing sign or "outside 50±5%" only. Re-pull after BETB.
- **YCS top-cut ordering:** a weak ordinal check only.
