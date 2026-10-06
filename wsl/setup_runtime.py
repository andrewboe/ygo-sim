"""Assemble ~/ygo/run: what the EDOPro env reads at runtime.

  edopro_script/  every Ignis script in one flat dir (official wins over pre-release)
  cards.cdb       BabelCDB cards.cdb + release/pre-release DBs (Advanced format only)
  code_list.txt   card codes the env may see
  decks/          field decklists, flattened to <deck>__<label>.ydk, plus _tokens.ydk
"""
import glob
import os
import shutil
import sqlite3

HOME = os.path.expanduser("~/ygo")
RUN = f"{HOME}/run"
FIELD = "/mnt/c/Users/andre/Desktop/ygo-sim/data/field"
TYPE_TOKEN = 0x4000
SKIP_DB = ("rush", "skill", "goat", "unofficial")


def link_scripts():
    out = f"{RUN}/edopro_script"
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    # Later entries win: utility scripts, then pre-release, then official.
    for src in (f"{HOME}/CardScripts/*.lua", f"{HOME}/CardScripts/pre-release/*.lua",
                f"{HOME}/CardScripts/official/*.lua"):
        for p in glob.glob(src):
            dst = f"{out}/{os.path.basename(p)}"
            if os.path.lexists(dst):
                os.remove(dst)
            os.symlink(p, dst)
    return len(os.listdir(out))


def merge_db():
    out = f"{RUN}/cards.cdb"
    shutil.copy(f"{HOME}/BabelCDB/cards.cdb", out)
    con = sqlite3.connect(out)
    extra = sorted(p for p in glob.glob(f"{HOME}/BabelCDB/*.cdb")
                   if not p.endswith("/cards.cdb") and not any(s in os.path.basename(p) for s in SKIP_DB))
    for p in extra:
        con.execute("attach ? as src", (p,))
        con.execute("insert or ignore into datas select * from src.datas")
        con.execute("insert or ignore into texts select * from src.texts")
        con.commit()
        con.execute("detach src")
    all_ids = [r[0] for r in con.execute("select id from datas")]
    con.close()
    return all_ids, [os.path.basename(p) for p in extra]


def copy_decks(all_ids):
    out = f"{RUN}/decks"
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    codes = set(all_ids)
    for p in glob.glob(f"{FIELD}/*/*.ydk"):
        deck, label = os.path.basename(os.path.dirname(p)), os.path.basename(p)[:-4]
        lines = [l.strip() for l in open(p)]
        # Normalize to LF: ygoenv's parser skips card lines ending in '\r'.
        with open(f"{out}/{deck}__{label}.ydk", "w", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        codes |= {int(l) for l in lines if l.isdigit()}
    # The env only knows cards it preloaded, and duels create cards that aren't in any deck
    # (tokens, cards whose code changes). '_'-prefixed decks are preloaded but never played.
    with open(f"{out}/_all.ydk", "w") as f:
        f.write("#main\n" + "\n".join(map(str, all_ids)) + "\n#extra\n!side\n")
    with open(f"{RUN}/code_list.txt", "w") as f:
        f.write("\n".join(map(str, sorted(codes))) + "\n")
    return len(glob.glob(f"{out}/*.ydk")) - 1, len(codes)


if __name__ == "__main__":
    os.makedirs(RUN, exist_ok=True)
    print("scripts:", link_scripts())
    all_ids, extra = merge_db()
    print(f"db: {len(all_ids)} cards (merged {extra})")
    decks, codes = copy_decks(all_ids)
    print(f"decks: {decks}, code list: {codes}")
