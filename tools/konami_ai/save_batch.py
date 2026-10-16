"""Step 3 helper: store one REA batch_decompile result (the JSON file the tool saves) as WORK_DIR/dec/<fn>.c.

  python save_batch.py RESULT_JSON WORK_DIR"""
import json
import os
import sys


def main():
    result, work = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(work, "dec"), exist_ok=True)
    items = json.load(open(result, encoding="utf-8"))["normalized_result"]["items"]
    ok = 0
    for it in items:
        name = (it.get("procedure") or {}).get("name") or it["address"]
        pc = (it.get("pseudocode") or "").replace("\r", "")
        if pc:
            open(os.path.join(work, "dec", f"{name}.c"), "w", encoding="utf-8").write(pc)
            ok += 1
        else:
            print("FAILED", it["address"])
    print(f"saved {ok}/{len(items)}")


if __name__ == "__main__":
    main()
