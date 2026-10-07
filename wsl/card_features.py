"""Fixed per-card features from card text, so the pilot understands cards it hasn't trained on (THEORY §5).

For every card in the runtime DB, indexed by code-list id (the id ygoenv puts in observations):
  - interruption tags (card_tags.py): field, set, hand values
  - keyword flags from the effect text (search, special summon, negate, quick effect, ...)
  - a sentence embedding of the effect text (all-MiniLM-L6-v2, 384 dims), computed on the GPU
Saved to data/card_features.npz as one matrix [n_ids + 1, D] (row 0 = no card). pilot.py loads it as a
frozen lookup table alongside the learned id embedding.

Run in the WSL venv:  python card_features.py
"""
import os
import re
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_tags import all_tags  # noqa: E402

RUN = os.path.expanduser("~/ygo/run")
OUT = "/mnt/c/Users/andre/Desktop/ygo-sim/data/card_features.npz"
KEYWORDS = {
    "search": r"add .{0,60}from your deck to your hand",
    "special_summon": r"special summon",
    "special_from_deck": r"special summon .{0,80}from your deck",
    "negate": r"\bnegate\b",
    "quick": r"\(quick effect\)|during either player's turn|during your opponent's turn",
    "from_hand": r"discard this card|from your hand",
    "once_per_turn": r"once per turn|only use .{0,40}once per turn",
    "destroy": r"\bdestroy\b",
    "banish": r"\bbanish\b",
    "send_gy": r"send .{0,60}to the gy",
    "draw": r"\bdraw\b",
    "target": r"\btarget\b",
    "floodgate": r"your opponent cannot|neither player can",
    "all_opponent": r"all (cards|monsters) your opponent controls|each card your opponent controls",
    "fusion": r"fusion summon",
    "synchro": r"synchro summon",
    "xyz": r"xyz summon",
    "link": r"link summon",
    "ritual": r"ritual summon",
    "recursion": r"from your gy",
    "lp_damage": r"inflict .{0,30}damage",
}


def main():
    con = sqlite3.connect(f"{RUN}/cards.cdb")
    texts = dict(con.execute("select id, desc from texts"))
    codes = [int(l) for l in open(f"{RUN}/code_list.txt") if l.strip()]
    tags = all_tags()
    n = len(codes) + 1
    kw = np.zeros((n, len(KEYWORDS)), dtype=np.float32)
    tg = np.zeros((n, 3), dtype=np.float32)
    docs = [""] * n
    for i, code in enumerate(codes, start=1):
        desc = (texts.get(code) or "").lower()
        docs[i] = texts.get(code) or ""
        kw[i] = [1.0 if re.search(p, desc) else 0.0 for p in KEYWORDS.values()]
        t = tags.get(code, {})
        tg[i] = [t.get("field", 0.0), t.get("set", 0.0), t.get("hand", 0.0)]

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cuda")
    emb = np.zeros((n, model.get_sentence_embedding_dimension()), dtype=np.float32)
    emb[1:] = model.encode(docs[1:], batch_size=256, show_progress_bar=False, normalize_embeddings=True)

    feats = np.concatenate([tg, kw, emb], axis=1)
    np.savez_compressed(OUT, features=feats, codes=np.array([0] + codes), keywords=np.array(list(KEYWORDS)))
    print(f"{n - 1} cards -> {feats.shape} features ({len(KEYWORDS)} keywords, 3 tags, {emb.shape[1]} text dims)")
    print("keyword coverage:", {k: int(kw[:, j].sum()) for j, k in enumerate(KEYWORDS)})


if __name__ == "__main__":
    main()
