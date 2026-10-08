"""Stage 1 report (ygosim report): one self-contained HTML page from the screen summary.

Shows each candidate's going-first board and going-second break score with standard errors, what the
board-breaker packages did relative to their base list, and the stage 2 entrants: per field deck, the
candidates no other candidate of that deck beats on both seats (at most MAX_PICKS, best combined first).
"""
import html
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

from .api import DATA_DIR
from .cards import name
from .deck import Deck
from .meta import slugify
from .screen import summarize

MAX_PICKS = 3
PACKAGES = {"light": "Light breakers", "heavy": "Heavy breakers", "backrow": "Backrow removal",
            "albaz": "Fallen & Virtuous"}
# Categorical deck colors, readable on both themes.
PALETTE = ["#3f7cc4", "#d0682c", "#2f9e6e", "#c2417a", "#8a63c9", "#b8962e", "#1f9fb0", "#c74a3c",
           "#6b8f2a", "#7b6f9e", "#d48aa8", "#4f6b8a", "#a0662a", "#3aa58c", "#9a4fb0"]


def _mean_se(xs: list[float]) -> tuple[float | None, float | None]:
    if not xs:
        return None, None
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, None
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(var / len(xs))


def collect() -> dict:
    field = json.loads((DATA_DIR / "field" / "field.json").read_text(encoding="utf-8"))
    variants = json.loads((DATA_DIR / "variants" / "variants.json").read_text(encoding="utf-8"))
    cands = {r["candidate"]: r for r in json.loads(
        (DATA_DIR / "candidates" / "candidates.json").read_text(encoding="utf-8")) if "skipped" not in r}
    opp_names = {f"{slugify(e['deck'])}__tcg": e["deck"] for e in field["entries"]}

    rows = []
    for r in summarize():
        meta = cands.get(r["candidate"])
        if meta is None:
            continue
        first, first_se = _mean_se(r["first_lines"])
        w = r["second_weights"]
        wsum = sum(w.values())
        opp = {}
        for o, games in r["second_games"].items():
            m, se = _mean_se(games)
            opp[o] = {"name": opp_names.get(o, o), "mean": m, "se": se, "n": len(games)}
        second_se = (math.sqrt(sum((w[o] * (opp[o]["se"] or 0)) ** 2 for o in opp)) / wsum) if wsum else None
        v = next((x for x in variants.get(meta["deck"], {}).get("variants", [])
                  if x["variant"] == meta["variant"]), {})
        rows.append({"candidate": r["candidate"], "deck": meta["deck"], "variant": meta["variant"],
                     "package": meta.get("package"), "first": first, "first_se": first_se,
                     "first_n": r["first_n"],
                     "p3": sum(x >= 3 for x in r["first_lines"]) / len(r["first_lines"]) if r["first_lines"] else None,
                     "second": r["second"], "second_se": second_se, "opponents": opp,
                     "share": v.get("share_of_deck"), "lists": v.get("lists"),
                     "signature": v.get("signature", [])})

    by_cand = {r["candidate"]: r for r in rows}
    for r in rows:  # what each package changed, relative to its base list
        if not r["package"]:
            continue
        base_name = r["candidate"].removesuffix(f"__{r['package']}")
        base = by_cand.get(base_name)
        r["base"] = base_name
        if base and base["first"] is not None and r["first"] is not None:
            r["d_first"] = r["first"] - base["first"]
        if base and base["second"] is not None and r["second"] is not None:
            r["d_second"] = r["second"] - base["second"]
        try:
            a = Deck.from_ydk(DATA_DIR / "candidates" / f"{r['candidate']}.ydk").canonical_ids().main
            b = Deck.from_ydk(DATA_DIR / "candidates" / f"{base_name}.ydk").canonical_ids().main
            r["added"] = [(name(c), n) for c, n in (a - b).items()]
            r["cut"] = [(name(c), n) for c, n in (b - a).items()]
        except FileNotFoundError:
            pass

    complete = [r for r in rows if r["first"] is not None and r["second"] is not None]
    if complete:  # z-scores across all candidates put the two seats on one scale
        for key in ("first", "second"):
            m = sum(r[key] for r in complete) / len(complete)
            sd = math.sqrt(sum((r[key] - m) ** 2 for r in complete) / max(1, len(complete) - 1)) or 1
            for r in complete:
                r[f"z_{key}"] = (r[key] - m) / sd
        for r in complete:
            r["z"] = r["z_first"] + r["z_second"]
    by_deck = defaultdict(list)
    for r in complete:
        by_deck[r["deck"]].append(r)
    for deck, group in by_deck.items():
        front = [r for r in group if not any(o["first"] >= r["first"] and o["second"] >= r["second"]
                                             and (o["first"] > r["first"] or o["second"] > r["second"])
                                             for o in group)]
        for r in front:
            r["front"] = True
        for r in sorted(front, key=lambda r: -r["z"])[:MAX_PICKS]:
            r["pick"] = True

    packages = {}
    for p in PACKAGES:
        ds = [r for r in rows if r["package"] == p and "d_first" in r and "d_second" in r]
        if ds:
            packages[p] = {"n": len(ds), "d_first": sum(r["d_first"] for r in ds) / len(ds),
                           "d_second": sum(r["d_second"] for r in ds) / len(ds),
                           "better_second": sum(r["d_second"] > 0 for r in ds)}
    return {"date": date.today().isoformat(), "field": field["entries"], "other_share": field.get("other_share"),
            "rows": rows, "packages": packages, "total_candidates": len(cands),
            "opponents": sorted({o for r in rows for o in r["opponents"]},
                                key=lambda o: -next((e["weight"] for e in field["entries"]
                                                     if f"{slugify(e['deck'])}__tcg" == o), 0))}


def _e(s) -> str:
    return html.escape(str(s))


def _num(v, fmt=".2f", sign=False) -> str:
    if v is None:
        return "<span class=muted>–</span>"
    return f"{v:+{fmt}}" if sign else f"{v:{fmt}}"


def _scatter(rows, colors) -> str:
    pts = [r for r in rows if r["first"] is not None and r["second"] is not None]
    if not pts:
        return ""
    W, H, L, R, T, B = 760, 460, 56, 20, 16, 48
    xs, ys = [r["second"] for r in pts], [r["first"] for r in pts]
    x0, x1 = math.floor(min(xs) * 20) / 20, math.ceil(max(xs) * 20) / 20
    y0, y1 = math.floor(min(ys) * 4) / 4, math.ceil(max(ys) * 4) / 4
    x1, y1 = max(x1, x0 + 0.05), max(y1, y0 + 0.25)
    sx = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R)
    sy = lambda v: H - B - (v - y0) / (y1 - y0) * (H - T - B)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Going first versus going second, per candidate">']
    x = x0
    while x <= x1 + 1e-9:
        out.append(f'<line class=grid x1="{sx(x):.1f}" x2="{sx(x):.1f}" y1="{T}" y2="{H - B}"/>'
                   f'<text class=tick x="{sx(x):.1f}" y="{H - B + 18}" text-anchor=middle>{x:.2f}</text>')
        x += 0.05
    y = y0
    while y <= y1 + 1e-9:
        out.append(f'<line class=grid x1="{L}" x2="{W - R}" y1="{sy(y):.1f}" y2="{sy(y):.1f}"/>'
                   f'<text class=tick x="{L - 8}" y="{sy(y) + 4:.1f}" text-anchor=end>{y:.2f}</text>')
        y += 0.25
    out.append(f'<text class=axis x="{(L + W - R) / 2}" y="{H - 8}" text-anchor=middle>'
               f'Going second: break-the-board score (field-weighted) →</text>')
    out.append(f'<text class=axis transform="translate(14 {(T + H - B) / 2}) rotate(-90)" text-anchor=middle>'
               f'Going first: live interruptions →</text>')
    for r in sorted(pts, key=lambda r: bool(r.get("pick"))):
        c = colors[r["deck"]]
        pkg = f" + {PACKAGES[r['package']]}" if r["package"] else ""
        tip = (f"{r['deck']}: {r['variant']}{pkg}\nfirst {r['first']:.2f}, second {r['second']:.2f}"
               + ("\nstage 2 entrant" if r.get("pick") else ""))
        shape = (f'<rect x="{sx(r["second"]) - 4:.1f}" y="{sy(r["first"]) - 4:.1f}" width=8 height=8 '
                 f'transform="rotate(45 {sx(r["second"]):.1f} {sy(r["first"]):.1f})" fill="{c}"' if r["package"]
                 else f'<circle cx="{sx(r["second"]):.1f}" cy="{sy(r["first"]):.1f}" r=5 fill="{c}"')
        ring = " class=pick" if r.get("pick") else " class=dot"
        out.append(f'<g{ring}>{shape}><title>{_e(tip)}</title></{"rect" if r["package"] else "circle"}></g>')
    out.append("</svg>")
    return "".join(out)


def render(d: dict) -> str:
    rows, opps = d["rows"], d["opponents"]
    decks = sorted({r["deck"] for r in rows}, key=lambda k: -next((e["weight"] for e in d["field"]
                                                                  if e["deck"] == k), 0))
    colors = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(decks)}
    complete = [r for r in rows if r["first"] is not None and r["second"] is not None]
    picks = [r for r in rows if r.get("pick")]
    opp_short = {o: next(iter(r["opponents"][o]["name"] for r in rows if o in r["opponents"])) for o in opps}

    best_first = max(complete, key=lambda r: r["first"], default=None)
    best_second = max(complete, key=lambda r: r["second"], default=None)
    label = lambda r: f"{r['deck']} {r['variant']}" + (f" + {PACKAGES[r['package']].lower()}" if r["package"] else "")
    findings = []
    if best_first:
        findings.append(f"Strongest first turn: <b>{_e(label(best_first))}</b>, "
                        f"{best_first['first']:.2f} live interruptions on average "
                        f"(P(≥3) {best_first['p3']:.0%}).")
    if best_second:
        findings.append(f"Best at breaking boards: <b>{_e(label(best_second))}</b>, "
                        f"score {best_second['second']:.2f} against the top field decks.")
    for p, s in d["packages"].items():
        findings.append(f"{PACKAGES[p]}: going second {s['d_second']:+.2f} on average "
                        f"({s['better_second']} of {s['n']} lists improved), going first {s['d_first']:+.2f}.")
    findings.append(f"{len(picks)} candidates from {len({r['deck'] for r in picks})} decks advance to stage 2.")

    legend = "".join(f'<span class=key><i style="background:{colors[k]}"></i>{_e(k)}</span>' for k in decks)

    pick_rows = []
    for deck in decks:
        for r in sorted((r for r in picks if r["deck"] == deck), key=lambda r: -r["z"]):
            pkg = PACKAGES[r["package"]] if r["package"] else "Base list"
            pick_rows.append(f'<li><span class=swatch style="background:{colors[deck]}"></span>'
                             f'<div><b>{_e(deck)}</b> · {_e(r["variant"])}<span class=pkg>{_e(pkg)}</span>'
                             f'<div class=sub>first {r["first"]:.2f} · second {r["second"]:.2f}</div></div></li>')

    table = []
    for deck in decks:
        group = sorted((r for r in rows if r["deck"] == deck),
                       key=lambda r: (r["variant"], r["package"] or ""))
        table.append(f'<tbody><tr class=deckrow><th colspan="{7 + len(opps)}">'
                     f'<span class=swatch style="background:{colors[deck]}"></span>{_e(deck)}</th></tr>')
        for r in group:
            pkg = PACKAGES[r["package"]] if r["package"] else "Base list"
            share = f'<span class=muted> · {r["share"]:.0%} of lists</span>' if r["share"] and not r["package"] else ""
            swap = ""
            if r.get("added"):
                swap = ('<div class=swap>+ ' + _e(", ".join(f"{n} {c}" for c, n in r["added"]))
                        + (" / − " + _e(", ".join(f"{n} {c}" for c, n in r["cut"])) if r.get("cut") else "")
                        + "</div>")
            status = ('<span class="chip go">Stage 2</span>' if r.get("pick") else
                      '<span class="chip front">Front</span>' if r.get("front") else "")
            opp_cells = "".join(
                f'<td class=num>{_num(r["opponents"][o]["mean"]) if o in r["opponents"] else _num(None)}</td>'
                for o in opps)
            fse = f'<span class=se>±{r["first_se"]:.2f}</span>' if r["first_se"] else ""
            sse = f'<span class=se>±{r["second_se"]:.2f}</span>' if r["second_se"] else ""
            table.append(
                f'<tr><td class=name><div>{_e(r["variant"])}{share}</div><div class=sub>{_e(pkg)}</div>{swap}</td>'
                f'<td class=num>{_num(r["first"])}{fse}</td>'
                f'<td class=num>{_num(r["p3"], ".0%")}</td>'
                f'<td class=num>{_num(r.get("d_first"), sign=True)}</td>'
                f'<td class=num>{_num(r["second"])}{sse}</td>'
                f'<td class=num>{_num(r.get("d_second"), sign=True)}</td>'
                f'{opp_cells}<td>{status}</td></tr>')
        table.append("</tbody>")

    field_max = max(e["weight"] for e in d["field"])
    field_rows = "".join(
        f'<div class=frow><span class=fname>{_e(e["deck"])}</span>'
        f'<span class=fbar><i style="width:{e["weight"] / field_max * 100:.1f}%;'
        f'background:{colors.get(e["deck"], "var(--muted)")}"></i></span>'
        f'<span class=fval>{e["weight"]:.1%}</span></div>' for e in d["field"])

    opp_heads = "".join(f'<th class=num>vs {_e(opp_short[o])}</th>' for o in opps)
    n_first = max((r["first_n"] for r in rows), default=0)
    n_second = max((v["n"] for r in rows for v in r["opponents"].values()), default=0)

    return TEMPLATE.format(
        date=d["date"], n=len(rows), total=d["total_candidates"], n_decks=len(decks), n_first=n_first,
        n_opp=len(opps), n_second=n_second,
        findings="".join(f"<li>{f}</li>" for f in findings), legend=legend, scatter=_scatter(rows, colors),
        picks="".join(pick_rows), table="".join(table), opp_heads=opp_heads, field=field_rows,
        other=f'{d["other_share"]:.0%}' if d.get("other_share") is not None else "–",
        opp_list=", ".join(_e(opp_short[o]) for o in opps), max_picks=MAX_PICKS)


def write(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(collect()), encoding="utf-8")
    return path


TEMPLATE = """<title>Stage 1 Deck Screen</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a tournament-report sheet. Summary and entrants first, the evidence (chart, full table, field) after. */
:root {{
  --bg: #f4f5f7; --surface: #ffffff; --fg: #18202b; --muted: #677285; --line: #dde1e8;
  --accent: #2c5fa8; --go: #1d7a52; --go-bg: #e3f3ea; --front-bg: #e8eef8;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "IBM Plex Sans", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #12161d; --surface: #1a2029; --fg: #e6eaf0; --muted: #94a0b3; --line: #2c3442;
  --accent: #7aa7e6; --go: #6fd3a2; --go-bg: #173327; --front-bg: #1e2a3d; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #12161d; --surface: #1a2029; --fg: #e6eaf0; --muted: #94a0b3; --line: #2c3442;
  --accent: #7aa7e6; --go: #6fd3a2; --go-bg: #173327; --front-bg: #1e2a3d; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.55 var(--body); }}
main {{ max-width: 1120px; margin: 0 auto; padding-inline: 20px; padding-block: 32px 64px;
  display: grid; gap: 40px; }}
h1, h2 {{ font-family: var(--display); font-weight: 600; letter-spacing: .01em; line-height: 1.1;
  text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(34px, 6vw, 52px); }}
h2 {{ font-size: 26px; }}
.eyebrow {{ font: 500 12px var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
header {{ display: grid; gap: 10px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 8px 24px; font: 13px var(--mono); color: var(--muted); }}
.stats b {{ color: var(--fg); font-weight: 500; }}
section {{ display: grid; gap: 14px; min-width: 0; }}
.lede {{ max-width: 68ch; color: var(--muted); margin: 0; }}
.findings {{ margin: 0; padding-left: 20px; display: grid; gap: 6px; max-width: 80ch; }}
.top {{ display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 32px; }}
@media (max-width: 820px) {{ .top {{ grid-template-columns: 1fr; }} }}
.picks {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 2px;
  border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }}
.picks li {{ display: flex; gap: 12px; align-items: flex-start; padding: 10px 14px; border-top: 1px solid var(--line); }}
.picks li:first-child {{ border-top: 0; }}
.swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-top: 6px; flex: none; }}
.deckrow .swatch {{ margin: 0 8px 0 0; }}
.pkg {{ margin-left: 8px; font: 12px var(--mono); color: var(--muted); }}
.sub {{ font-size: 13px; color: var(--muted); }}
.chart {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px; overflow-x: auto; }}
.chart svg {{ width: 100%; min-width: 560px; height: auto; display: block; }}
.grid {{ stroke: var(--line); stroke-width: 1; }}
.tick {{ fill: var(--muted); font: 11px var(--mono); }}
.axis {{ fill: var(--muted); font: 12px var(--body); }}
.dot > * {{ opacity: .55; }}
.pick > * {{ stroke: var(--fg); stroke-width: 2; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); }}
.key i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
.legend .shape {{ color: var(--fg); }}
.tablewrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ padding: 8px 12px; text-align: left; vertical-align: top; border-top: 1px solid var(--line); }}
thead th {{ font: 500 12px var(--mono); text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
  border-top: 0; white-space: nowrap; position: sticky; top: 0; background: var(--surface); }}
.deckrow th {{ font: 600 18px var(--display); padding-top: 16px; background: var(--bg); }}
.num {{ text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.se {{ display: block; font-size: 11px; color: var(--muted); }}
.name {{ min-width: 220px; }}
.swap {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
.muted {{ color: var(--muted); }}
.chip {{ font: 500 11px var(--mono); padding: 2px 8px; border-radius: 99px; white-space: nowrap; }}
.chip.go {{ background: var(--go-bg); color: var(--go); }}
.chip.front {{ background: var(--front-bg); color: var(--accent); }}
.field {{ display: grid; gap: 6px; max-width: 640px; }}
.frow {{ display: grid; grid-template-columns: minmax(0, 220px) 1fr 56px; gap: 12px; align-items: center; font-size: 14px; }}
.fbar {{ height: 10px; background: var(--line); border-radius: 2px; overflow: hidden; }}
.fbar i {{ display: block; height: 100%; }}
.fval {{ font-family: var(--mono); text-align: right; font-variant-numeric: tabular-nums; }}
.notes {{ max-width: 76ch; display: grid; gap: 10px; color: var(--muted); }}
.notes p {{ margin: 0; }}
.notes b {{ color: var(--fg); font-weight: 500; }}
</style>
<main>
<header>
  <div class=eyebrow>ygo-sim · funnel stage 1 · {date}</div>
  <h1>Stage 1 Deck Screen</h1>
  <div class=stats><span><b>{n}</b> of {total} candidates screened</span><span><b>{n_decks}</b> field decks</span>
  <span><b>{n_first}</b> openings searched going first</span><span><b>{n_opp}×{n_second}</b> games going second</span></div>
</header>

<div class=top>
<section>
  <h2>What stage 1 found</h2>
  <ul class=findings>{findings}</ul>
</section>
<section>
  <h2>Stage 2 entrants</h2>
  <p class=lede>Per deck, the lists no sibling beats on both seats (up to {max_picks}).</p>
  <ul class=picks>{picks}</ul>
</section>
</div>

<section>
  <h2>First turn versus breaking boards</h2>
  <p class=lede>Each mark is one candidate list. Up is a stronger going-first board, right is a better chance to
  break the top decks' boards going second. Circles are base lists, diamonds add a breaker package, outlined
  marks advance. Hover a mark for its name.</p>
  <div class=legend>{legend}</div>
  <div class=chart>{scatter}</div>
</section>

<section>
  <h2>Every candidate</h2>
  <p class=lede>Going first: live interruptions on the searched turn-1 board (mean ± standard error) and the
  share of openings reaching 3 or more. Going second: break-the-board score, overall and per opponent.
  Δ columns compare a package list with its base list.</p>
  <div class=tablewrap><table>
    <thead><tr><th>List</th><th class=num>First</th><th class=num>P(≥3)</th><th class=num>Δ first</th>
    <th class=num>Second</th><th class=num>Δ second</th>{opp_heads}<th>Status</th></tr></thead>
    {table}
  </table></div>
</section>

<section>
  <h2>The field</h2>
  <p class=lede>Share of the simulated TCG field per deck (other decks: {other}). Going-second scores are
  weighted by these shares across the opponents tested.</p>
  <div class=field>{field}</div>
</section>

<section class=notes>
  <h2>How to read this</h2>
  <p><b>Going first</b> is the best turn-1 line found by search (NRPA) for each opening, scored by a scripted
  opponent turn that counts which interruptions are actually live, plus hand traps held.</p>
  <p><b>Going second</b> plays the candidate against {opp_list} going first, with the co-evolved pilot. A win
  scores 1 and a loss 0; games that reach the turn cap are scored by the fitted position evaluation.</p>
  <p><b>Limits.</b> The two seats use different scales, so lists are compared within their deck, not across decks;
  stage 2 games put everything on one win-rate scale. Twelve games per opponent leaves standard errors near
  0.05–0.08, so close neighbors are not reliably different. The pilot plays every deck the same way and is not
  yet as strong as a good human player.</p>
</section>
</main>
"""
