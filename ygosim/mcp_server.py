"""stdio MCP server exposing validate_deck. Run: python -m ygosim.mcp_server

Register (user scope): claude mcp add --scope user ygo-format -- <venv python> -m ygosim.mcp_server
"""
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import carddata
from .formats import DeckInputError, validate_deck as _validate

server = MCPServer(
    "ygo-format",
    instructions=(
        "Format-aware Yu-Gi-Oh! deck legality from YGOProDeck data cached locally. Use validate_deck "
        "before stating that a deck, card count, ban status or Genesys point total is legal, and quote "
        "its 'data as of' date with any points or ban status you report. It checks deck construction "
        "only; it does not answer rulings questions."
    ),
)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def validate_deck(
    format: Literal["tcg_advanced", "genesys"],
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
    con = carddata.connect()
    try:
        refresh = carddata.ensure_fresh(con)
        result = _validate(con, format, ydk_path=ydk_path, ydk_text=ydk_text, decklist=decklist,
                           point_cap=point_cap, as_of=as_of)
        if refresh not in ("fresh",):
            result["data"]["refresh"] = refresh
        return result
    except DeckInputError as e:
        return {"legal": None, "summary": f"NOT VALIDATED: {e}", "data": carddata.freshness(con)}
    finally:
        con.close()


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
