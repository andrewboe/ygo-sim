# ygosim

Simulation-driven Yu-Gi-Oh! deck optimization, seeded from the current TCG meta.
The theory and design live in [docs/THEORY.md](docs/THEORY.md).

## Plan

| Phase | What | Runs on |
|---|---|---|
| 1 | Pull tournament-topping lists (YGOProDeck "Tournament Meta Decks"), build a representative list + card-inclusion table per archetype | Windows Python |
| 2 | Goldfish simulator on ygopro-core via [ygoenv](https://github.com/sbl1996/ygo-agent): opening/combo success rates | WSL2 (Ubuntu) |
| 3 | Pretrained ygo-agent pilots play meta decks against each other: first matchup matrix, checked against real tournament results | WSL2 + GPU |
| 4 | Outer loop: tune card counts and flex slots within each archetype using the inclusion tables as the edit space, with a surrogate win-rate model and MAP-Elites search. Optional cheap LLM (Haiku) proposes edits | WSL2 + GPU |
| 5 | Deck-conditioned league self-play so the pilot keeps up with edited lists | WSL2 + GPU |

LLM use stays optional and batched (one call proposes many edits). The simulation itself costs no tokens.

## Matches are best-of-3 with side decking

Competitive results are match results, so matchups are scored as Bo3 matches, not single games:

- Game 1 uses main decks, with a coin flip for who goes first.
- Games 2 and 3 use post-side lists: each deck's side plan for that opponent, built from its side deck. The loser of the previous game chooses turn order.

The simulator estimates four game win rates per matchup: pre-side going first, pre-side going second, post-side going first, and post-side going second. The match win rate then follows exactly from those numbers, so Bo3 costs no more simulation than single games. The side plan (which cards come in and out per matchup) becomes part of what the optimizer searches.

## Sharing the machine

- **Priority:** simulations run at the lowest priority (`nice 19`), so your own apps get the CPU first.
- **Pause:** `wsl bash wsl/pause_sims.sh` freezes every simulator and training process instantly, and
  `wsl bash wsl/resume_sims.sh` continues them. RAM and GPU memory stay allocated, and a pause doesn't
  survive a reboot.
- **Stop and resume later:** these runs pick up where they stopped:
  - `stage1.sh`, `matchups.sh` and `stage2.py` skip work whose results are already logged.
  - `train_pilot.py --resume` continues from the last completed epoch.
- **Stop everything now:** `wsl bash wsl/stop_sims.sh`.
- **Sleep:** long runs launch through `wsl/awake.ps1`, which keeps Windows awake only while the job runs.

## Tournaments

`ygosim tournament --matrix M.json` simulates YCS-style events over the current field:
- **Format:** Swiss rounds (3 points per win, pairings by record, no rematches, byes), then a single-elimination top cut.
- **Defaults:** `ceil(log2(players))` rounds and a top cut near players/8. 263 players gives 9 rounds and a top 32.
- **Tiebreak:** opponents' match-win percentage.
- **Matchups:** Bo3 match win rates from `match.py`.

It reports each deck's share of the field, its share of top cut, its conversion (top-cut share divided by field share), and its win rate. Until the matchup simulator exists, `M.json` has to be supplied.

## Setup (phase 1)

```
python -m venv .venv
.venv\Scripts\activate
pip install -e .
ygosim meta --days 60
```

Output goes to `data/meta/`: `<archetype>.ydk`, `<archetype>.inclusion.json`, and `summary.json`.

```
ygosim project --days 30 --as-of 2026-10-08
```

Converts recent OCG tournament lists into TCG-legal lists for a date. It drops unreleased cards, cuts to the TCG banlist, and refills slots from the OCG archetype, then the closest TCG archetype, then cross-archetype staples. Output goes to `data/projected/`: a `.ydk` plus a provenance report per deck.

```
ygosim field --as-of 2026-10-08
```

Builds the weighted field the simulator plays against: TCG decks (user labels merged by card overlap) weighted by topping share. Each OCG projection does one of three things:
- **Updates an existing deck:** it becomes an extra candidate list for that deck, at the same weight.
- **Enters as a new deck:** used when nothing in the TCG matches. It gets a prior share (`--new-share`).
- **Stays out:** used when its TCG counterpart is below `--min-share`, as with Sacred Beasts.

Matching ignores staples (cards in 15% or more of TCG lists). Output goes to `data/field/`.

```
ygosim refresh [--force]
```

Pulls every source into `data/store.json`, which keeps every list ever seen with its date. It rebuilds the field only when something changed: first run, a TCG banlist change, a set reaching its TCG date, new lists, or a change in `data/inbox/`. Each rebuild writes `data/snapshots/<date>/` and prepends a diff to `data/CHANGELOG.md`. Not scheduled yet: that waits until we know what the ML runs need.

## Sources

| Source | Used for |
|---|---|
| YGOProDeck tournament decks (TCG + OCG) | Meta share, projections |
| Yugioh Meta top decks (TCG + OCG) | Meta share, projections. Exact dates. Genesys events excluded. Cards matched by name; a list with any unmatched name is skipped. |
| `data/inbox/*.ydk` | Community lists (Reddit, YouTube, etc.). Enter as candidate lists, never as meta share. |
| YGOProDeck card DB + Project Ignis lflist | Card data, release dates, banlist |

Lists found on both sites are deduplicated by contents. Shares decay with a 21-day half-life. An OCG-only deck needs 4% or more of the OCG meta (`--min-ocg-share`) to enter the field as a new deck. AI is not used in refresh.

## Legality (fails closed)

- The banlist comes from YGOProDeck and Project Ignis `0TCG.lflist.conf`. Where they disagree, the stricter limit wins and the conflict is printed.
- Cards count by canonical id, so alt-art passcodes share one limit.
- Unknown cards and cards with no TCG release date on or before `--as-of` are illegal.
- `Deck.to_ydk` refuses to write an illegal deck.
- The projector rejects decks whose own core cards are forbidden in the TCG (e.g. Kewl Tune without Rotary).
- `pytest tests` covers these cases and re-validates every exported `.ydk`.

## Known risks

- ygo-agent pins `jax<=0.4.28`. That build predates RTX 50-series (Blackwell, sm_120) support, so GPU training will likely need a newer JAX/CUDA 12.8+ or a port to PyTorch.
- ygoenv uses Fluorohydride ygopro-core plus ygopro-scripts. Recent cards need up-to-date scripts.
