"""Step 2: find the CPU think functions in duel.dll and write the decompile batches.

AI functions = functions that reference a CPU-specific debug string ("CPU..." Shift-JIS asserts from
cpu_think.c) or read the per-player CPU setting, plus the functions only they call. Usage:
  python ai_functions.py DUEL_DLL WORK_DIR
Writes WORK_DIR/ai_funcs.json (function start addresses, image-base VAs) and WORK_DIR/batches.json
(lists of ~23 addresses, one REA batch_decompile call each)."""
import json
import os
import re
import struct
import sys

from pe import PE


def main():
    dll, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)
    pe = PE(dll)
    rva0, rdata = pe.section(".rdata")
    # 1. CPU debug strings (Shift-JIS) and the functions that reference them.
    strings = {}
    for m in re.finditer(rb"[^\0]{4,}", rdata):
        try:
            s = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if "CPU" in s:
            strings[rva0 + m.start()] = s
    refs = pe.rip_refs(strings)
    ai = {pe.function_at(a) for at in refs.values() for a in at} - {None}
    n_assert = len(ai)
    # 2. Readers of the CPU setting: DLL_DuelSetCpuParam stores it through a global pointer (mov rax, [rip+X]).
    setter = pe.exports()["DLL_DuelSetCpuParam"]
    code = pe.b[pe.off(setter):pe.off(setter) + 7]
    assert code[:3] == b"\x48\x8b\x05", "DLL_DuelSetCpuParam no longer starts with mov rax, [rip+X]"
    holder = setter + 7 + struct.unpack_from("<i", code, 3)[0]
    for at in pe.rip_refs([holder]).get(holder, []):
        window = pe.b[pe.off(at):pe.off(at) + 40]  # the access that follows: [reg + idx*4 + 0x18]
        if re.search(rb"[\x40-\x7f][\x44\x4c\x54\x5c\x64\x6c\x74\x7c].\x18|\x8b[\x44\x4c\x54\x5c].\x18|"
                     rb"\xf7\x44.\x18|\x0f\xba..\x18", window, re.S):
            f = pe.function_at(at)
            if f is not None:
                ai.add(f)
    n_param = len(ai) - n_assert
    # 3. Functions called only from AI functions (per-card helpers of the think code).
    callers, callees = {}, {}
    for s, t in pe.calls():
        callers.setdefault(t, set()).add(s)
        callees.setdefault(s, set()).add(t)
    while True:
        new = {t for s in ai for t in callees.get(s, ()) if t not in ai and callers.get(t) and callers[t] <= ai}
        if not new:
            break
        ai |= new
    vas = sorted(hex(pe.base + f) for f in ai)
    json.dump(vas, open(os.path.join(work, "ai_funcs.json"), "w"))
    json.dump([vas[k:k + 23] for k in range(0, len(vas), 23)], open(os.path.join(work, "batches.json"), "w"))
    print(f"{len(vas)} AI functions ({n_assert} with CPU asserts, {n_param} more reading the CPU setting, "
          f"{len(vas) - n_assert - n_param} AI-only callees); {-(-len(vas) // 23)} decompile batches")


if __name__ == "__main__":
    main()
