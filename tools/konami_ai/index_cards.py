"""Step 4: per-card evidence. Finds every pool card's Master Duel ID in the decompiled AI functions
(switch cases, comparisons, helper-call arguments) and writes the enclosing block per hit.

  python index_cards.py WORK_DIR
Reads WORK_DIR/pool.json and WORK_DIR/dec/*.c; writes WORK_DIR/evidence/<passcode>.txt, index.json,
no_ai_refs.txt (pool cards Konami handles only generically) and batch<k>.txt (passcodes split for review)."""
import collections
import glob
import json
import os
import re
import sys

REF = re.compile(r"(case 0x([0-9a-f]+):)|([!=]= 0x([0-9a-f]+)\b)|([(,] ?0x([0-9a-f]+)[,)])")
MAX_BLOCK = 80


def block(lines, n, kind):
    """(start, end) of the case body or of the statement block around line n."""
    line = lines[n]
    if kind == "case":  # until the next case/default/closing brace at the same indentation
        ind = len(line) - len(line.lstrip())
        end = n + 1
        while end < len(lines) and end - n < MAX_BLOCK:
            l2 = lines[end]
            if l2.strip() and len(l2) - len(l2.lstrip()) <= ind and l2.strip().startswith(("case", "default", "}")):
                break
            end += 1
        return n, end
    start, depth, end = max(0, n - 2), 0, n  # until the braces opened from here balance
    while end < len(lines) and end - n < MAX_BLOCK:
        depth += lines[end].count("{") - lines[end].count("}")
        end += 1
        if depth <= 0 and end > n + 1 and ("}" in lines[end - 1] or ";" in lines[end - 1]):
            break
    return start, end


def main():
    work = sys.argv[1]
    pool = json.load(open(os.path.join(work, "pool.json"), encoding="utf-8"))
    md2code = {v["md"]: int(c) for c, v in pool.items()}
    out = os.path.join(work, "evidence")
    os.makedirs(out, exist_ok=True)
    index = collections.defaultdict(lambda: collections.Counter())
    snips, spans = collections.defaultdict(list), collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(work, "dec", "*.c"))):
        fn = os.path.basename(path)[:-2]
        lines = open(path, encoding="utf-8").read().splitlines()
        for n, line in enumerate(lines):
            for m in REF.finditer(line):
                kind, val = ("case", m.group(2)) if m.group(1) else ("cmp", m.group(4)) if m.group(3) else ("arg", m.group(6))
                code = md2code.get(int(val, 16))
                if code is None:
                    continue
                index[code][fn] += 1
                start, end = block(lines, n, kind)
                if any(f == fn and start < e and s < end for f, s, e in spans[code]):
                    continue
                spans[code].append((fn, start, end))
                snips[code].append(f"--- {fn}:{n + 1} ({kind})\n" + "\n".join(lines[start:end]))
    summary = {}
    for code in sorted(index):
        card = pool[str(code)]
        summary[code] = {"name": card["name"], "md": card["md"], "decks": card["decks"], "functions": dict(index[code])}
        with open(os.path.join(out, f"{code}.txt"), "w", encoding="utf-8") as f:
            f.write(f"# {card['name']} ({code}, MD {card['md']}) decks: {', '.join(card['decks'])}\n")
            f.write(f"# text: {card['text']}\n\n" + "\n\n".join(snips[code]))
    json.dump(summary, open(os.path.join(out, "index.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    generic = sorted(v["name"] for c, v in pool.items() if int(c) not in summary)
    open(os.path.join(out, "no_ai_refs.txt"), "w", encoding="utf-8").write("\n".join(generic))
    order = sorted(summary, key=lambda c: -sum(summary[c]["functions"].values()))
    for k in range(4):
        open(os.path.join(out, f"batch{k}.txt"), "w").write("\n".join(map(str, order[k::4])))
    print(f"{len(summary)} / {len(pool)} pool cards have card-specific AI blocks; "
          f"{len(generic)} only get Konami's generic handling")


if __name__ == "__main__":
    main()
