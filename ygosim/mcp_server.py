"""stdio MCP server: deck validation, card search and format meta. Run: python -m ygosim.mcp_server

Register (user scope): claude mcp add --scope user ygo-format -- <venv python> -m ygosim.mcp_server
"""
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import carddata, cardtools, decksave, formatmeta, linkfind, rulings
from .formats import DeckInputError, validate_deck as _validate

Format = Literal["tcg_advanced", "genesys"]
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

server = MCPServer(
    "ygo-format",
    instructions=(
        "Format-aware Yu-Gi-Oh! card data (YGOProDeck, cached locally) for TCG Advanced and Genesys. "
        "Never state card text, ban status, Genesys points or what a card searches from memory: use "
        "card_lookup / search_cards / archetype. Ground 'current meta' claims in meta_snapshot and "
        "meta_inclusion. Run validate_deck before presenting any decklist, and quote the 'data as of' "
        "date with points or ban status. For rulings (cost vs. effect, timing, once-per-turn, whether "
        "two cards interact) call card_rulings, ideally with with_card, and quote the official answer; "
        "if no Q&A covers the case, say the ruling is unverified rather than guessing."
    ),
)


def _call(fn, *args, **kwargs) -> dict:
    """Open the index, refresh it if due, run fn, and attach the freshness block."""
    con = carddata.connect()
    try:
        refresh = carddata.ensure_fresh(con)
        result = fn(con, *args, **kwargs)
        result.setdefault("data", carddata.freshness(con))
        if refresh != "fresh":
            result["data"]["refresh"] = refresh
        return result
    except DeckInputError as e:
        return {"error": str(e), "data": carddata.freshness(con)}
    finally:
        con.close()


def _with_meta(fn):
    def run(con, *args, **kwargs):
        meta = formatmeta.ensure_meta(con)
        out = fn(con, *args, **kwargs)
        out["lists_as_of"] = meta
        return out
    return run


@server.tool(annotations=READ_ONLY)
def search_cards(
    format: Format,
    text: str | None = None,
    pattern: str | None = None,
    name: str | None = None,
    archetype: str | None = None,
    mentions: str | None = None,
    kind: str | None = None,
    attribute: str | None = None,
    race: str | None = None,
    level_min: int | None = None,
    level_max: int | None = None,
    atk_max: int | None = None,
    def_max: int | None = None,
    max_points: int | None = None,
    include_illegal: bool = False,
    limit: int = 20,
    full_text: bool = False,
) -> dict:
    """Search the card pool. Only cards legal in `format` are returned unless include_illegal.

    text: words that must all appear in the card text (or FTS5 syntax: "special summon" AND deck NOT banish)
    pattern: Python regex over card text, e.g. "Level 4 or lower .*Warrior"
    name: substring of the name; archetype: name contains it (case-sensitive game rule, e.g. "Destiny HERO")
    mentions: cards whose text names this in quotes, e.g. "HERO" or "Destiny HERO - Malicious"
    kind: monster, extra, main, tuner, fusion, synchro, xyz, link, ritual, pendulum, effect, normal, flip,
      spell, trap, quick-play, continuous spell, field, equip, ritual spell, normal trap, continuous trap, counter
    attribute: DARK, LIGHT, ...; race: Warrior, Spellcaster, ...; level_min/max: Level, Rank or Link rating
    max_points: Genesys points per copy at most this
    Card text is cut to 400 characters unless full_text.
    """
    return _call(cardtools.search_cards, format, text=text, pattern=pattern, name=name, archetype=archetype,
                 mentions=mentions, kind=kind, attribute=attribute, race=race, level_min=level_min,
                 level_max=level_max, atk_max=atk_max, def_max=def_max, max_points=max_points,
                 include_illegal=include_illegal, limit=limit, full_text=full_text)


@server.tool(annotations=READ_ONLY)
def card_lookup(query: str) -> dict:
    """One card by name or passcode: full text, stats, status in every format (limit, Genesys points,
    legality and why not), alt passcodes, quoted names in its text, and rulings links.
    Unknown or ambiguous names return candidates instead of a guess."""
    return _call(cardtools.card_lookup, query)


@server.tool(annotations=READ_ONLY)
def archetype(name: str, format: Format, include_text: bool | None = None) -> dict:
    """An archetype's members (name contains `name`, case-sensitive) with status in `format`, plus
    support: cards YGOProDeck tags with it or whose text names it in quotes. Card text is included when
    the answer is small (<= 60 cards) unless include_text is set."""
    return _call(cardtools.archetype, name, format, include_text=include_text)


@server.tool(annotations=READ_ONLY)
def meta_snapshot(format: Format, days: int = 60, top: int = 15) -> dict:
    """Recent tournament tops (Yugioh Meta) for the format: deck-type shares, top-8s and wins, how many
    lists are still legal under today's list or points (average points for Genesys), and the most-played
    cards. Genesys = Genesys events; Advanced = TCG lists outside Genesys and OCG."""
    return _call(_with_meta(formatmeta.meta_snapshot), format, days=days, top=top)


@server.tool(annotations=READ_ONLY)
def meta_inclusion(format: Format, card: str | None = None, deck_type: str | None = None,
                   days: int = 60, limit: int = 40) -> dict:
    """How a card is played in recent tops (share of lists, average copies, by deck type), or a deck
    type's card inclusion table. Pass exactly one of card, deck_type (Yugioh Meta deck type name;
    near misses are suggested)."""
    return _call(_with_meta(formatmeta.meta_inclusion), format, card=card, deck_type=deck_type,
                 days=days, limit=limit)


@server.tool(annotations=READ_ONLY)
def card_rulings(card: str, with_card: str | None = None, query: str | None = None, limit: int = 8) -> dict:
    """Official FAQ and Q&A rulings for a card (Konami OCG database via YGOResources, cached locally).
    with_card: only Q&As that involve both cards (best for "does X work with Y" questions).
    query: only Q&As containing all these words, e.g. "cost banish" or "damage step".
    Each Q&A has title, question, answer, date and translation status. These are OCG rulings and TCG
    rulings can differ: quote them, don't extend them past what they cover. Requests are capped per call
    to respect YGOResources; the note says when more remain."""
    return _call(rulings.card_rulings, card, with_card=with_card, query=query, limit=limit)


@server.tool(annotations=READ_ONLY)
def find_links(
    format: Format,
    decklist: dict[str, list[str]] | None = None,
    ydk_path: str | None = None,
    ydk_text: str | None = None,
    cards: list[str] | None = None,
    archetypes: list[str] | None = None,
    max_points: int | None = None,
    point_cap: int | None = None,
    limit: int = 12,
) -> dict:
    """Bridges and support for a deck (or just a few cards), legal in `format` and within budget:
      into_your_deck      outside cards whose effects add/summon/send/banish/Set your cards (with evidence)
      your_deck_reaches   what your cards can already fetch outside the list, by archetype
      bridges             other engines tied to your deck through those cards
      extra_deck_options  Extra Deck monsters your monsters satisfy the materials of
      deck_locks          "cannot Special Summon except X" in your deck; suggestions that break one say so
    Genesys: suggestions are limited to the points left (point_cap minus the deck's points) unless
    max_points is given. Links are parsed from card text, not verified rulings: read each item's
    evidence and ruling_flags, and validate_deck any final list.
    """
    return _call(linkfind.find_links, format, ydk_path=ydk_path, ydk_text=ydk_text, decklist=decklist,
                 cards=cards, archetypes=archetypes, max_points=max_points, point_cap=point_cap, limit=limit)


@server.tool(annotations=READ_ONLY)
def validate_deck(
    format: Format,
    ydk_path: str | None = None,
    ydk_text: str | None = None,
    decklist: dict[str, list[str]] | None = None,
    point_cap: int | None = None,
    as_of: str | None = None,
) -> dict:
    """Check a deck against a format and list every card with its ban status or Genesys points.

    Give exactly one deck input:
      ydk_path  a .ydk file path readable from Windows (WSL files: \\\\wsl.localhost\\Ubuntu-24.04\\home\\...)
      ydk_text  .ydk contents, or a ydke:// URL
      decklist  {"main": [...], "extra": [...], "side": [...]} with entries like "3 Ash Blossom & Joyous Spring",
                "Called by the Grave x2", "Cupsy☆Yummy" or a passcode
    format: tcg_advanced (Forbidden & Limited list; stricter of YGOProDeck and Project Ignis) or genesys
      (no F&L; Link and Pendulum Monsters banned in every zone; Main+Extra+Side points must fit point_cap,
      default 100).
    as_of: YYYY-MM-DD for the release-date check (default today).

    legal is true/false, or null when the input had unknown passcodes, unknown or ambiguous names, or
    unreadable .ydk lines: nothing is dropped or guessed, so fix parse_errors and call again.
    resolved_names lists names that were matched after normalizing; check them.
    """
    result = _call(_validate, format, ydk_path=ydk_path, ydk_text=ydk_text, decklist=decklist,
                   point_cap=point_cap, as_of=as_of)
    if "error" in result:
        return {"legal": None, "summary": f"NOT VALIDATED: {result.pop('error')}", **result}
    return result


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                         openWorldHint=True))
def finalize_deck(
    format: Format,
    name: str,
    decklist: dict[str, list[str]] | None = None,
    ydk_path: str | None = None,
    ydk_text: str | None = None,
    point_cap: int | None = None,
    notes: str | None = None,
) -> dict:
    """Save a finished deck, but only if validate_deck says it is legal (otherwise nothing is written
    and the problems come back). Writes data/decks/<name>.<format>.ydk and a .json with the ydke:// URL,
    a text decklist, the points or ban breakdown and the data "as of" date. Saving the same name again
    keeps the previous .ydk in data/decks/history/. Follow-up questions can pass the returned ydk path to
    validate_deck or find_links."""
    return _call(decksave.finalize_deck, format, name, decklist=decklist, ydk_path=ydk_path,
                 ydk_text_in=ydk_text, point_cap=point_cap, notes=notes)


@server.tool(annotations=READ_ONLY)
def saved_decks(format: Format | None = None) -> dict:
    """Decks saved with finalize_deck, newest first: name, format, saved_at, summary, .ydk path, ydke URL."""
    return _call(decksave.saved_decks, format=format)


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
