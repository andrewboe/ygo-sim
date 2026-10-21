import os
from pathlib import Path

# Card data, formats and the MCP server live in ygo-format; keep its cache in this repo's data/ so the
# simulator, its caches and saved decks share one folder.
os.environ.setdefault("YGO_FORMAT_DATA", str(Path(__file__).resolve().parent.parent / "data"))
