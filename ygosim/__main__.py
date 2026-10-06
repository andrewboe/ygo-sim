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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
