"""Export WindBot's card lists (Game/AI/Enums/*.cs: floodgates, dangerous / invincible monsters, cards that
shouldn't be targeted...) to wsl/windbot_lists.json for wsl/windbot.py.

Source: IceYGO/windbot (MIT License, Copyright (c) 2015-2017 IceYGO; see THIRD_PARTY_NOTICES.md).
  python export_lists.py WINDBOT_CHECKOUT"""
import glob
import json
import os
import re
import subprocess
import sys

ENUM = re.compile(r"enum\s+(\w+)\s*\{(.*?)\}", re.S)
MEMBER = re.compile(r"(\w+)\s*=\s*(\d+)")


def main():
    root = sys.argv[1]
    lists = {}
    for path in sorted(glob.glob(os.path.join(root, "Game", "AI", "Enums", "*.cs"))):
        for name, body in ENUM.findall(open(path, encoding="utf-8").read()):
            lists[name] = sorted({int(v) for _, v in MEMBER.findall(body)})
    commit = subprocess.run(["git", "-C", root, "log", "-1", "--format=%H %cs"], capture_output=True, text=True).stdout.strip()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "wsl", "windbot_lists.json")
    json.dump({"source": f"IceYGO/windbot {commit} (MIT)", "lists": lists}, open(out, "w"), indent=0)
    print(", ".join(f"{k} {len(v)}" for k, v in lists.items()))


if __name__ == "__main__":
    main()
