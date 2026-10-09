# Anticipating upcoming TCG releases: research and pipeline design

Researched 2026-10-09. Where a claim comes from the live YGOProDeck API it was checked that day (DB version 147.23, last_update 2026-10-08). Items marked **[unverified]** come from memory or a single secondary source.

## 1. How OCG releases relate to TCG releases

**Core boosters (the 4-per-year main sets).** Each TCG core booster is the OCG core booster (80 cards) plus about 16-20 TCG-only cards, for roughly 100-101 cards in total. The added cards sit at the end of the set list (for BETB, EN081-EN096), and a few more slots go to OCG cards from other products (BETB EN097-EN100). The YGOProDeck data shows this split for every recent core set:

| TCG set | TCG date | Main OCG date | Lag | Cards with no OCG date (TCG-first) |
|---|---|---|---|---|
| DUNE | 2023-07-27 | 2023-04-22 | ~14 wk | 11 |
| AGOV | 2023-10-19 | 2023-07-22 | ~13 wk | 12 |
| PHNI | 2024-02-08 | 2023-10-28 | ~15 wk | 16 |
| LEDE | 2024-04-25 | 2024-01-27 | ~13 wk | 16 |
| INFO | 2024-07-18 | 2024-04-27 | ~12 wk | 19 |
| SUDA | 2025-01-23 | 2024-10-26 | ~13 wk | 15 |
| ALIN | 2025-05-01 | 2025-01-25 | ~14 wk | 16 (got OCG date 2025-09-27 later) |
| DOOD | 2025-09-25 | 2025-07-26 | ~9 wk | 16 |
| BPRO | 2026-02-05 | 2025-10-25 | ~15 wk | 16 |
| BLZD | 2026-05-07 | 2026-01-24 | ~15 wk | 16 |
| CORI | 2026-07-02 | 2026-04-25 | ~10 wk | 16 |
| BETB | 2026-10-08 | 2026-07-18 | ~12 wk | 16 |

Rule of thumb: **the TCG core set arrives 9-15 weeks (median about 13) after the OCG set.** The TCG-only cards usually reach the OCG later, either in a following OCG set or as a batch. ALIN's 16 TCG-only cards, for example, got OCG date 2025-09-27.

**Other products.**
- The TCG 60-card sets map to OCG "Deck-Build Packs". *Glorious Victors* (GLVI, TCG 2026-12-04) is the TCG version of OCG *Deck-Build Pack: Glorious Victors* (DBGV, OCG 2026-09-05), a lag of about 13 weeks.
- Side products such as Magnificent Maestros (MAMS, TCG 2026-11-12) bundle OCG cards from varied, older dates. MAMS mostly contains cards with OCG date 2026-03-20, a lag of about 8 months.
- Battles of Legend sets, Rarity Collections and Legendary Decks are mostly reprints mixed with a small number of new or OCG-sourced cards.
- The lag for non-core products is irregular, so don't apply the 13-week rule to them.

**Skips, delays and exceptions.**
- Some OCG cards first arrive in a different TCG product than the one that matches their OCG set. Example: Clown Crew Cappello (OCG 2026-07-03) and Verre (OCG 2026-01-05) were added as BETB EN098/EN099.
- Some OCG cards don't come to the TCG for a long time. YGOProDeck lists about 380 cards whose formats include "OCG" but not "TCG".
- Some cards are TCG-first or TCG-only and have no OCG date at all, which means there is no OCG performance data for them.
- Cards can be renamed when localized, and the TCG has its own errata and policies **[unverified in detail]**.

## 2. Official sources

- **TCG product pages**, at `yugioh-card.com/en/products/<setcode>/` (e.g. `/en/products/glvi/`) and the `/eu/` equivalent, give the release date and a product description. Konami announces products about 3-5 months ahead. ICv2 reported GLVI (Dec 2026) and IMPH (Jan 2027) in advance.
- **Official card database** (`db.yugioh-card.com`). **[unverified]** From memory, it adds a set's cards around release, not at announcement, which makes it a confirmation source rather than a way to see cards in advance. It also has no public API. It is still the canonical source for Konami IDs; YGOProDeck exposes `konami_id`.
- **Full set lists.** The full TCG set list is generally known before release. The OCG part is known once the Japanese set is out. The TCG-only cards are revealed in the weeks before TCG release through Konami/YGOrganization reveal articles, previews and Premiere events. The complete list is usually finished about 1-3 weeks before street date **[unverified, typical community experience]**. Japan reveals OCG cards through V Jump, Jump and yu-gi-oh.jp roughly 1-3 months before OCG release.
- **TCG Forbidden & Limited lists.** The table below comes from Yugipedia list pages and their announcement citations.

| Effective | Announced (approx.) |
|---|---|
| 2025-04-07 | 2025-04-06 |
| 2025-09-15 | 2025-09-12 |
| 2025-10-27 | 2025-10-24 |
| 2026-02-02 | ~2026-01-21 (Konami EU on X) |
| 2026-05-18 | 2026-05-11 |
| 2026-09-21 | 2026-09-20 |

  - That is 3-5 TCG lists per year with irregular spacing, announced **1-7 days** before taking effect, often close to a core set or major event.
  - The OCG list is quarterly and takes effect on Jan 1, Apr 1, Jul 1 and Oct 1 (Yugipedia has OCG lists for every quarter of 2024-2026).
  - Because the TCG list gives so little notice, a pipeline should poll for it rather than schedule around it.

## 3. Community and programmatic sources

**YGOProDeck API** (`db.ygoprodeck.com/api/v7/`, free, rate-limited, cache locally). This is the best single source.
- `cardsets.php` returns all TCG sets as `set_name, set_code, num_of_cards, tcg_date, set_image`.
  - **It does include future sets once announced.** On 2026-10-09 MAMS appeared with tcg_date 2026-11-12. GLVI (Dec 4) and IMPH (Jan 29) did not appear yet, probably because their set lists haven't been posted.
  - It lists TCG sets only, with no OCG sets.
  - `set_code` is not unique, and `tcg_date` can be missing (e.g. 26LP).
- `cardinfo.php?misc=yes` adds `misc_info[0]` with `tcg_date`, `ocg_date`, `formats` (e.g. `["TCG","OCG","Master Duel"]`), `konami_id`, `beta_id`, `beta_name`, `treated_as`, `md_rarity` and `staple`.
  - **Unreleased cards do appear.** There were 20 cards with tcg_date after today (the MAMS cards on 2026-11-12, and "Hope for the Future" on 2027-02-16).
  - It also has 53 cards with an ocg_date after today, mostly IMPH (2026-10-31), with `formats: ["OCG"]` and no `card_sets`.
  - OCG-only cards have no `card_sets` because OCG set prints aren't tracked. A card typically gains a `tcg_date` and a TCG `card_sets` entry once the TCG set list is published.
- **Date filtering works.** `cardinfo.php?startdate=2026-10-10&enddate=2027-12-31&dateregion=ocg&misc=yes` returned 53 cards. Other useful queries are `cardset=<name>` and `cardsetsinfo.php?setcode=BETB-EN081`.
- `checkDBVer.php` returns `{database_version, last_update}`. It is cheap to poll and tells you whether a full refetch is needed.
- Ban status comes from `banlist_info.ban_tcg` / `ban_ocg` on each card, plus `banlist=tcg|ocg` filters.
- **Data-quality issues seen in the data:**
  - ROTA's tcg and ocg dates look swapped (tcg 2024-07-27, ocg 2024-10-10).
  - "Red-Eyes Black Dragon Exceed" is printed in BETB but has no tcg_date and formats `["OCG"]`.
  - `cardsetsinfo` for BETB-EN081 still returns prerelease ID 101402101 the day after release.
  - Validate these fields; don't trust them blindly.

**Yugipedia** (MediaWiki API, `yugipedia.com/api.php`; WebFetch gets HTTP 403, but `curl` with a descriptive User-Agent works).
- Set pages have `{{Infobox set}}` with `jp_release_date`, `sc_release_date`, `na_release_date`, `eu_release_date`, `oc_release_date`, `prefix`, `size` (e.g. "80 (JP) / 100 (TCG)"), and `prev`/`next` links.
- **Following `next` from the newest core set finds the upcoming OCG sets before YGOProDeck lists them.**
- `Category:TCG Advanced Format Forbidden & Limited Lists` and `Category:OCG Forbidden & Limited Lists` give `start_date`/`end_date`.
- Set list pages ("Set Card Lists:...") give the per-region card lists.

**YGOrganization** (ygorganization.com) has translations of OCG reveals, TCG product announcements and F&L posts. It's useful as a human-readable feed or RSS; there's no structured API.

**EDOPro / Project Ignis.**
- `ProjectIgnis/CardScripts` has a `pre-release/` folder (137 scripts on 2026-10-09, named like `c100200292.lua`).
- `ProjectIgnis/BabelCDB` has per-set prerelease databases: `prerelease-imph.cdb`, `prerelease-dbgv.cdb`, `prerelease-betb-en.cdb` (TCG-only cards), `prerelease-others.cdb`, plus `release-betb.cdb`.
- Unreleased cards get **placeholder IDs** in the 100xxxxxx/101xxxxxx range, which match YGOProDeck's `beta_id`. After official release they are re-keyed to the real passcode **[mechanism of migration unverified; likely an alias/rename in the CDB]**.
- This is the practical source of **simulatable** card scripts for unreleased cards, often weeks before the TCG release. It's the natural input for ygo-sim.

**OCG results**
- *Road of the King* (roadoftheking.com) publishes OCG metagame reports per format window, e.g. "OCG 2026.07". They aggregate top decks from Japanese, Chinese, Taiwanese and Korean events; one August 2026 report covered 193 decks from 32 tournaments. These are HTML articles, so they'd need scraping.
- *YGOProDeck tournaments* (`ygoprodeck.com/tournaments/`) has OCG, China OCG and Asian-English OCG format filters with decklists. The table loads dynamically, so check the site for a JSON endpoint **[unverified]**.
- *Konami JP* (`konami.com/yugioh/news/`) posts official results for YCSJ and the Japanese Championship, including deck distribution charts.
- Japanese CS ("championship series", store-run) decklists are spread across store blogs and X posts, with no reliable aggregator found. The appmedia.jp results turned out to cover Master Duel, not OCG.

## 4. Current and upcoming sets (as of 2026-10-09)

| TCG product | TCG date (NA / EU) | OCG counterpart | OCG date |
|---|---|---|---|
| Beyond the Brave (BETB, 100) | 2026-10-09 / 10-08 | Beyond the Brave (JP, 80) | 2026-07-18 |
| Magnificent Maestros (MAMS, 24) | 2026-11-12 | mixed OCG cards (mostly 2026-03-20) | various |
| Glorious Victors (GLVI, 60, 60-card set) | 2026-12-04 / 12-03 | Deck-Build Pack: Glorious Victors (DBGV) | 2026-09-05 |
| Immortal Phoenix (IMPH, 100) | 2027-01-29 / 01-28 | Immortal Phoenix (JP, 80) | 2026-10-31 |
| (next core, TCG name TBA) | expected ~Apr-May 2027 | Pride and Soul (OCG core) | 2027-01-23 |

- BETB's 16 TCG-only cards (EN081-EN096) have no OCG history, including the "Angelechy" support and "Audhumla, Progenitor of the Frozen Expanse".
- **IMPH** cards are revealed and in YGOProDeck with ocg_date 2026-10-31 (44 cards so far). Their OCG results will exist from November 2026, about 13 weeks before the TCG release.
- The TCG date for Pride and Soul's counterpart is an estimate from the 13-week rule, not an announcement.
- The OCG F&L for Oct 1, 2026 is already in effect. The next one is due Jan 1, 2027.

## 5. Recommended pipeline

**Step 1: Set calendar (daily).**
- Poll `checkDBVer.php`; if it changed, refetch `cardsets.php` and `cardinfo.php?misc=yes` (about 25 MB).
- Poll the Yugipedia infoboxes for the latest Core Booster / Deck-Build Pack and walk `next`.
- Build a `sets` table: `{tcg_code, tcg_name, tcg_date_na, tcg_date_eu, ocg_counterpart, ocg_date, product_type, source, confidence}`.
- Join TCG to OCG on the Yugipedia `prefix`, or on the `{{about}}` hatnote for 60-card sets.
- When a TCG date is missing, estimate it as OCG date + 13 weeks (± 3) for core sets and flag it as `estimated`.

**Step 2: Card roster per upcoming TCG set.**
- Before the TCG set list exists, the roster is the cards with `ocg_date == counterpart OCG date` (from the `startdate/enddate/dateregion=ocg` query), plus the matching prerelease CDB from BabelCDB (e.g. `prerelease-imph.cdb`).
- After the TCG set list is published, use `cardinfo.php?cardset=<name>`.
- Diff the two rosters to find TCG-only cards (no `ocg_date`) and cards that came in from other OCG sets.

**Step 3: "Coming in N weeks" detection.**
- `weeks_until = (tcg_date - today)/7` per set.
- Raise events at 12, 8, 4 and 1 weeks out, and when a set first appears in `cardsets.php` or a new `next` link appears on Yugipedia.

**Step 4: OCG performance.**
- For each roster card, take its OCG date and collect OCG decklists from that date onward: YGOProDeck tournaments (format=OCG) and Road of the King reports.
- Compute play rate, top-cut share and archetype share. Keep the OCG ban status in effect at each event so cards banned in the OCG aren't missed.
- There are usually 9-15 weeks of OCG data before the TCG release.

**Step 5: Legality on a date.**
- A card is legal in the TCG once its earliest TCG product's `tcg_date` has passed. Taking the minimum across `card_sets` is safer than relying on `misc_info.tcg_date` alone.
- Apply the TCG F&L list whose `start_date` is on or before that date. Poll YGOrganization/Yugipedia frequently in the weeks after each core set, because notice can be as short as one day.

**Step 6: Simulator hook.**
- Load the prerelease CDBs and scripts into ygo-sim, keyed by `beta_id`.
- Keep a `beta_id → passcode` map, filled from YGOProDeck `misc_info.beta_id` once a card is released.

**Pitfalls**
- **Card IDs.**
  - Prerelease placeholder IDs (`beta_id`, EDOPro 100/101xxxxxx) change to real passcodes at release, sometimes with a delay (BETB-EN081 was still on its beta ID the day after release).
  - Alt-art cards have several `card_images[].id` values under one card.
  - `konami_id` differs from the passcode.
- **Names.** Use `beta_name` to cover TCG names that change between reveal and release, and OCG-translated names that differ from the final TCG names. Join on ID, never on name.
- **Errata.** TCG and OCG card text and errata can differ. EDOPro also keeps a `pre-errata` folder.
- **Region.** NA/EU/OC release dates differ by a day; pick NA consistently. Asian-English OCG, Simplified Chinese OCG and Korean releases have their own dates and their own F&L lists. China in particular uses a separate list **[unverified for 2026]**.
- **Data errors.** Swapped dates (ROTA), missing tcg_date on reprinted OCG cards (Red-Eyes Black Dragon Exceed), and non-unique set codes.
- **Translating OCG results.** OCG results come from a different format with a different ban list and card pool. TCG-only support can change an archetype's strength, so treat OCG play rate as a prior, not ground truth.

## Sources

- YGOProDeck API: https://db.ygoprodeck.com/api/v7/cardsets.php, https://db.ygoprodeck.com/api/v7/cardinfo.php, https://db.ygoprodeck.com/api/v7/checkDBVer.php (queried 2026-10-09)
- YGOProDeck tournaments: https://ygoprodeck.com/tournaments/
- Yugipedia: https://yugipedia.com/wiki/Beyond_the_Brave, https://yugipedia.com/wiki/Immortal_Phoenix, https://yugipedia.com/wiki/Pride_and_Soul, https://yugipedia.com/wiki/Glorious_Victors, https://yugipedia.com/wiki/Deck-Build_Pack:_Glorious_Victors, F&L pages (e.g. https://yugipedia.com/wiki/September_2026_Lists_(TCG)) via https://yugipedia.com/api.php
- YugiohMeta, OCG Beyond the Brave announcement: https://www.yugiohmeta.com/articles/news/2026/mar/beyond-the-brave-announced
- YugiohMeta, Immortal Phoenix announcement: https://www.yugiohmeta.com/articles/news/2026/jun/immortal-phoenix-announced
- ICv2, Glorious Victors: https://icv2.com/articles/news/view/63153/new-yu-gi-oh-tcg-booster-set-revealed
- ICv2, Immortal Phoenix (Jan 29, 2027): https://icv2.com/articles/news/view/63433
- ICv2, 2026 calendar: https://icv2.com/articles/news/view/61069/yu-gi-oh-tcg-2026-product-release-calendar
- Konami product page (GLVI): https://www.yugioh-card.com/en/products/glvi/
- YGOrganization F&L posts: https://ygorganization.com/putinvokerbackpls, https://ygorganization.com/prematurekewltunenerfs/
- MasterDuelMeta TCG F&L Sept 2026: https://www.masterduelmeta.com/articles/news/september-2026/tcg-forbidden-list/
- Project Ignis: https://github.com/ProjectIgnis/CardScripts (pre-release/), https://github.com/ProjectIgnis/BabelCDB
- Road of the King OCG reports: https://roadoftheking.com/ocg-2026-07-metagame-report-6-7/
- Konami JP news (YCSJ results): https://www.konami.com/yugioh/news/
