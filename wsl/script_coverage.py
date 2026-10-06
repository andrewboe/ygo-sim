"""Check every card in the field's decklists has an Ignis script and database entry."""
import glob
import os
import sqlite3
import sys

HOME = os.path.expanduser("~/ygo")
FIELD = sys.argv[1] if len(sys.argv) > 1 else "/mnt/c/Users/andre/Desktop/ygo-sim/data/field"

scripts = set()
for sub in ("official", "pre-release"):
    for p in glob.glob(f"{HOME}/CardScripts/{sub}/c*.lua"):
        scripts.add(int(os.path.basename(p)[1:-4]))

db_ids, names, aliases = set(), {}, {}
for cdb in glob.glob(f"{HOME}/BabelCDB/*.cdb"):
    con = sqlite3.connect(cdb)
    for cid, alias in con.execute("select id, alias from datas"):
        db_ids.add(cid)
        aliases[cid] = alias
    names.update(dict(con.execute("select id, name from texts")))

missing_script, missing_db, total = {}, {}, set()
for ydk in glob.glob(f"{FIELD}/**/*.ydk", recursive=True):
    for line in open(ydk):
        line = line.strip()
        if not line.isdigit():
            continue
        cid = int(line)
        total.add(cid)
        if cid not in db_ids:
            missing_db.setdefault(cid, set()).add(os.path.relpath(ydk, FIELD))
        # Alt arts run their base card's script.
        elif cid not in scripts and aliases.get(cid, 0) not in scripts:
            missing_script.setdefault(cid, set()).add(os.path.relpath(ydk, FIELD))

print(f"{len(total)} distinct cards in field; {len(scripts)} scripts; {len(db_ids)} db entries")
for label, miss in (("not in Ignis DB", missing_db), ("no script", missing_script)):
    print(f"{label}: {len(miss)}")
    for cid, decks in sorted(miss.items()):
        print(f"  {cid} {names.get(cid, '?')}  <- {sorted(decks)[:3]}")
