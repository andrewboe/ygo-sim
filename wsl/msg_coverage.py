"""List ygopro-core messages that ygoenv's EDOPro handle_message() doesn't handle."""
import os
import re

core = open(os.path.expanduser("~/ygo/edopro-core/ocgapi_constants.h")).read()
env = open(os.path.expanduser("~/ygo/ygo-agent/ygoenv/ygoenv/edopro/edopro.h")).read()

msgs = {name: int(num) for name, num in re.findall(r"#define (MSG_\w+)\s+(\d+)", core)}
handled = set(re.findall(r"msg_ == (MSG_\w+)", env))
# Also messages listed in skip/ignore sets, e.g. `MSG_X,` inside an initializer near "skip".
listed = set(re.findall(r"\b(MSG_\w+)\b", env))
for name, num in sorted(msgs.items(), key=lambda kv: kv[1]):
    status = "handled" if name in handled else ("mentioned" if name in listed else "MISSING")
    if status != "handled":
        print(f"{num:4} {name:28} {status}")
