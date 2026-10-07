import argparse
from datetime import date

from .api import DATA_DIR
from .banlist import tcg_banlist
from .field import build_field, export_field
from .meta import build_meta, export_meta
from .project import export_projections, project_meta
from .refresh import refresh
from .sources import inbox_decks, pull_all


def _as_of(args) -> date:
    return date.fromisoformat(args.as_of) if getattr(args, "as_of", None) else date.today()


def _print_banlist():
    bl = tcg_banlist()
    print(f"TCG banlist: {bl.title} ({len(bl.limits)} cards restricted)")
    for c in bl.conflicts:
        print(f"  banlist sources disagree, stricter applied: {c}")


def _print_field(f, total_note=""):
    print(f"{'weight':>6}  {'tcg':>5}  deck  [lists to test]")
    for e in f.entries:
        tcg_share = "new" if e.source == "new" else f"{e.tcg_share:.1%}"
        print(f"{e.weight:6.1%}  {tcg_share:>5}  {e.name}  [{', '.join(e.lists)}]")
        if len(e.variants) > 1:
            print(f"               merged: {', '.join(e.variants[1:])}")
    print(f"\n{f.other_share:.0%} of weighted TCG share is below the cutoff ('other')")
    print("\nProjections and community lists:")
    for n in f.notes:
        print(f"  {n}")


def cmd_meta(args):
    pull_all(args.days)
    _print_banlist()
    archetypes, total = build_meta(args.days, args.min_lists, args.include_illegal)
    export_meta(archetypes, total, args.include_illegal)
    legality = "" if args.include_illegal else " legal under the current TCG banlist"
    print(f"{total} topping lists{legality} in the last {args.days} days -> {len(archetypes)} archetypes\n")
    print(f"{'lists':>5}  archetype")
    for a in archetypes:
        print(f"{len(a.lists):5}  {a.name}")
    print(f"\nWrote .ydk files and inclusion tables to {DATA_DIR / 'meta'}")


def cmd_project(args):
    pull_all(max(args.days, args.tcg_days))
    _print_banlist()
    as_of = _as_of(args)
    tcg, _ = build_meta(args.tcg_days, 1)
    projections = project_meta(args.days, args.min_lists, as_of, tcg)
    export_projections(projections, as_of)
    print(f"Projected {len(projections)} OCG archetypes to TCG as of {as_of}\n")
    print(f"{'lists':>5}  {'lost':>5}  {'conf':>4}  archetype  (closest TCG deck)")
    for p in projections:
        status = "REJECTED" if p.error else p.confidence
        print(f"{p.ocg_lists:5}  {p.main_lost:5.0%}  {status:>4}  {p.archetype}  ({p.tcg_match or '-'})")
        if p.error:
            print(f"         {p.error}")
    print(f"\nWrote legal .ydk files and provenance reports to {DATA_DIR / 'projected'}")


def cmd_field(args):
    pull_all(max(args.days, args.ocg_days))
    _print_banlist()
    as_of = _as_of(args)
    tcg, _ = build_meta(args.days, 1)
    projections = project_meta(args.ocg_days, 2, as_of, tcg)
    f = build_field(tcg, projections, inbox_decks(), args.min_share, args.new_share, as_of,
                    min_ocg_share=args.min_ocg_share)
    export_field(f, as_of)
    print(f"Field as of {as_of}\n")
    _print_field(f)
    print(f"\nWrote {DATA_DIR / 'field' / 'field.json'}")


def cmd_refresh(args):
    r = refresh(args.days, args.ocg_days, args.min_share, args.new_share, _as_of(args), args.force,
                args.min_ocg_share)
    print(f"Banlist: {r['banlist']}")
    print(f"Pulled: {r['pulled']['new'] or 'no new lists'} ({r['pulled']['stored']} lists stored)")
    if r["pulled"]["unknown_names"]:
        print(f"Skipped lists with unmatched card names: {r['pulled']['unknown_names']}")
    if not r["triggers"]:
        print("Nothing changed; field not rebuilt.")
        return
    print(f"Triggers: {'; '.join(r['triggers'])}\n")
    for c in r["changes"]:
        print(f"  {c}")
    print(f"\nSnapshot and changelog written under {DATA_DIR}")


def cmd_tournament(args):
    import json

    import numpy as np

    from .tournament import EventFormat, check_matrix, simulate

    from .meta import slugify

    field = json.loads((DATA_DIR / "field" / "field.json").read_text(encoding="utf-8"))
    m = json.loads(open(args.matrix, encoding="utf-8").read())
    # Matrix decks may be runtime names ("elfnote__tcg"); map them to field entries by slug.
    index = {}
    for i, d in enumerate(m["decks"]):
        slug = d.split("__")[0]
        name = next((e["deck"] for e in field["entries"] if slugify(e["deck"]) == slug), d)
        index.setdefault(name, i)
    names = [e["deck"] for e in field["entries"] if e["deck"] in index]
    missing = [e["deck"] for e in field["entries"] if e["deck"] not in index]
    if missing:
        print(f"no matchup data for {missing}; left out of the field")
    full = np.array(m["matrix"], dtype=float)
    idx = [index[d] for d in names]
    matrix = full[np.ix_(idx, idx)]
    check_matrix(matrix)
    shares = [next(e["weight"] for e in field["entries"] if e["deck"] == d) for d in names]
    fmt = EventFormat(args.players, args.rounds, args.top_cut, args.draw_rate)
    r = fmt.resolved()
    stats = simulate(names, shares, matrix, fmt, args.events, args.seed)
    print(f"{args.events} events of {r.players} players: {r.rounds} Swiss rounds, top {r.top_cut}\n")
    print(f"{'field':>6} {'top cut':>8} {'conv':>5} {'cut rate':>8} {'wins':>6}  deck")
    for row in stats.table():
        print(f"{row['field_share']:6.1%} {row['top_cut_share']:8.1%} {row['conversion']:5.2f} "
              f"{row['top_cut_rate']:8.1%} {row['win_rate']:6.1%}  {row['deck']}")


def cmd_fit_eval(args):
    from .evalfit import WEIGHTS, fit

    out = fit(args.l2)
    r = out["report"]
    print(f"{r['positions']} positions from {r['games']} games")
    print(f"held-out log loss {r['test_log_loss']:.3f} (base rate {r['test_log_loss_base_rate']:.3f}), "
          f"accuracy {r['test_accuracy']:.0%}")
    for k, v in sorted(out["weights"].items(), key=lambda kv: -abs(kv[1])):
        print(f"  {v:+.3f}  {k}")
    print(f"wrote {WEIGHTS}")


def cmd_matrix(args):
    from .matrix import MATRIX, build

    out = build(args.decks, args.eval)
    decks = out["decks"]
    width = max(len(d) for d in decks)
    print(f"Bo3 match win rate (row vs column), from {RESULTS_NOTE}:\n")
    print(" " * width + "  " + "  ".join(f"{i:>5}" for i in range(len(decks))))
    for i, (d, row) in enumerate(zip(decks, out["matrix"])):
        print(f"{d:>{width}}  " + "  ".join(f"{v:5.0%}" for v in row) + f"   [{i}]")
    print(f"\nwrote {MATRIX}  (use: ygosim tournament --matrix {MATRIX})")


RESULTS_NOTE = "data/games/results.jsonl"


def cmd_hand_traps(args):
    from .handtraps import field_hand_trap_odds

    import json

    odds = field_hand_trap_odds(args.cards, args.hand)
    print(f"P(opponent opens at least one), {args.hand}-card hand, weighted over the current field:")
    for name, p in sorted(odds.items(), key=lambda kv: -kv[1]):
        print(f"  {p:5.1%}  {name}")
    out = DATA_DIR / "field" / "hand_trap_odds.json"
    out.write_text(json.dumps({"hand": args.hand, "odds": odds}, indent=1), encoding="utf-8")
    print(f"wrote {out} (chokepoint.py --p-trap auto reads it)")


def main():
    parser = argparse.ArgumentParser(prog="ygosim")
    sub = parser.add_subparsers(required=True)

    def field_args(p):
        p.add_argument("--days", type=int, default=60, help="TCG look-back window")
        p.add_argument("--ocg-days", type=int, default=30, help="OCG look-back window")
        p.add_argument("--as-of", help="TCG date, YYYY-MM-DD (default: today)")
        p.add_argument("--min-share", type=float, default=0.02, help="TCG share needed to be simulated")
        p.add_argument("--new-share", type=float, default=0.03,
                       help="assumed share for decks with no TCG presence yet")
        p.add_argument("--min-ocg-share", type=float, default=0.04,
                       help="OCG share an OCG-only deck needs to enter the field as new")

    meta = sub.add_parser("meta", help="build per-archetype TCG decks from recent tournament lists")
    meta.add_argument("--days", type=int, default=60, help="look-back window")
    meta.add_argument("--min-lists", type=int, default=2, help="drop archetypes with fewer lists")
    meta.add_argument("--include-illegal", action="store_true",
                      help="keep lists that break the current TCG banlist (e.g. pre-banlist events)")
    meta.set_defaults(func=cmd_meta)

    proj = sub.add_parser("project", help="convert recent OCG tournament lists into TCG-legal lists")
    proj.add_argument("--days", type=int, default=30, help="OCG look-back window")
    proj.add_argument("--tcg-days", type=int, default=60, help="TCG look-back window for refill data")
    proj.add_argument("--min-lists", type=int, default=2, help="drop OCG archetypes with fewer lists")
    proj.add_argument("--as-of", help="TCG date to project to, YYYY-MM-DD (default: today)")
    proj.set_defaults(func=cmd_project)

    fld = sub.add_parser("field", help="build the weighted field to simulate: TCG meta plus OCG projections")
    field_args(fld)
    fld.set_defaults(func=cmd_field)

    ref = sub.add_parser("refresh", help="pull all sources; rebuild, snapshot and log only if something changed")
    field_args(ref)
    ref.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    ref.set_defaults(func=cmd_refresh)

    tour = sub.add_parser("tournament", help="Monte Carlo YCS-style events over the current field")
    tour.add_argument("--matrix", required=True,
                      help='JSON {"decks": [...], "matrix": [[match win rate row vs col]]}')
    tour.add_argument("--players", type=int, default=263)
    tour.add_argument("--rounds", type=int, help="Swiss rounds (default: ceil(log2(players)))")
    tour.add_argument("--top-cut", type=int, help="default: power of two near players/8, 8-64")
    tour.add_argument("--draw-rate", type=float, default=0.0)
    tour.add_argument("--events", type=int, default=1000)
    tour.add_argument("--seed", type=int, default=0)
    tour.set_defaults(func=cmd_tournament)

    mx = sub.add_parser("matrix", help="Bo3 matchup matrix from simulated games (data/games/results.jsonl)")
    mx.add_argument("decks", nargs="+", help="runtime deck names, e.g. elfnote__tcg")
    mx.add_argument("--eval", choices=["fitted", "default"], help="only games played with this evaluation")
    mx.set_defaults(func=cmd_matrix)

    ht = sub.add_parser("hand-traps", help="how likely the field's opponent opens each hand trap")
    ht.add_argument("cards", nargs="*", default=["Ash Blossom & Joyous Spring", "Infinite Impermanence",
                                                 "Effect Veiler", "Nibiru, the Primal Being",
                                                 "Droll & Lock Bird", "Ghost Belle & Haunted Mansion",
                                                 "Mulcharmy Fuwalos", "Mulcharmy Purulia"])
    ht.add_argument("--hand", type=int, default=6, help="6 = facing the second player's first turn")
    ht.set_defaults(func=cmd_hand_traps)

    fe = sub.add_parser("fit-eval", help="fit the game position evaluation from logged game outcomes")
    fe.add_argument("--l2", type=float, default=1.0)
    fe.set_defaults(func=cmd_fit_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
