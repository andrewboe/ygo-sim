"""WindBot deck executors (docs/windbot_porting.md), by the ygo-sim deck names they play."""
import importlib

# deck name -> (module, executor class)
DECKS = {
    "elfnote__tcg": ("elfnote", "ElfnoteExecutor"),
    "elfnote__projected-elfnote": ("elfnote", "ElfnoteExecutor"),
    "chaos-ritual__tcg": ("chaos_ritual", "ChaosRitualExecutor"),
    "chaos-ritual__projected": ("chaos_ritual", "ChaosRitualExecutor"),
    "chaos-ritual-ocg__projected": ("chaos_ritual", "ChaosRitualExecutor"),
}


def executors(decks) -> dict:
    """deck name -> executor class, for the given decks that have a ported executor."""
    out = {}
    for deck in decks:
        if deck in DECKS:
            module, cls = DECKS[deck]
            try:
                out[deck] = getattr(importlib.import_module(f"windbot_decks.{module}"), cls)
            except ModuleNotFoundError:
                pass
    return out
