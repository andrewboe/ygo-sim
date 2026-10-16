"""Step 1: the card pool (cards in ygo-sim's field decks) with Master Duel internal IDs and card text.

  python pool.py DECKS_DIR YDK_IDS CARDS_CDB WORK_DIR [GLOB]
DECKS_DIR: ~/ygo/run/decks; YDK_IDS: YgoMaster's Data/YdkIds.txt (passcode -> Master Duel ID);
GLOB: which decks count as the pool (default *__tcg.ydk, the field decks).
Writes WORK_DIR/pool.json {passcode: {md, name, text, decks}}."""
import glob
import json
import os
import re
import sqlite3
import sys


def main():
    decks_dir, ydk_ids, cdb, work = sys.argv[1:5]
    pattern = sys.argv[5] if len(sys.argv) > 5 else "*__tcg.ydk"
    os.makedirs(work, exist_ok=True)
    md = {int(a): int(b) for a, b in (line.split() for line in open(ydk_ids) if line.strip())}
    texts = {c: (n, d) for c, n, d in sqlite3.connect(cdb).execute("select id, name, desc from texts")}
    decks = {}
    for path in sorted(glob.glob(os.path.join(decks_dir, pattern))):
        for line in open(path):
            if re.fullmatch(r"\d+\s*", line):
                decks.setdefault(int(line), set()).add(os.path.basename(path)[:-4])
    pool = {c: {"md": md[c], "name": texts.get(c, ("?", ""))[0], "text": texts.get(c, ("", ""))[1],
                "decks": sorted(d)} for c, d in sorted(decks.items()) if c in md}
    json.dump(pool, open(os.path.join(work, "pool.json"), "w"), indent=0, ensure_ascii=False)
    missing = [texts.get(c, ("?",))[0] for c in decks if c not in md]
    print(f"{len(decks)} cards in {pattern}; {len(pool)} have Master Duel IDs; not in Master Duel: {missing}")


if __name__ == "__main__":
    main()
