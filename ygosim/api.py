"""Thin HTTP layer over YGOProDeck with on-disk caching and polite rate limiting."""
import json
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CARDINFO_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
CARDSETS_URL = "https://db.ygoprodeck.com/api/v7/cardsets.php"
DECKS_URL = "https://ygoprodeck.com/api/decks/getDecks.php"
IGNIS_TCG_LFLIST_URL = "https://raw.githubusercontent.com/ProjectIgnis/LFLists/master/0TCG.lflist.conf"

_session = requests.Session()
_session.headers["User-Agent"] = "ygosim/0.1 (personal research project)"
_last_request = 0.0


def _get(url: str, params: dict | None = None) -> requests.Response:
    # YGOProDeck rate-limits at 20 req/s; stay far under it.
    global _last_request
    wait = 0.25 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = _session.get(url, params=params, timeout=60)
    _last_request = time.monotonic()
    resp.raise_for_status()
    return resp


def get_json(url: str, params: dict | None = None):
    return _get(url, params).json()


def get_text(url: str) -> str:
    return _get(url).text


def cached(name: str, max_age_hours: float, fetch):
    """Return JSON from data/<name>, refetching when missing or stale."""
    path = DATA_DIR / name
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data
