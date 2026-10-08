"""Patches the edo9300 ygopro-core checkout (~/ygo/edopro-core) before build_core.sh builds it.
Each run resets the patched files to git HEAD, then applies every patch once.

Watchdog: some board states make the core's material checks (fusion_check -> check_matching, nested
per material) explode combinatorially; one OCG_DuelProcess call then runs for hours. A Lua count hook
checks the thread's CPU time and raises a Lua error once a process call has used STEP_LIMIT_S; the
core already catches script errors (it's built with C++ stack unwinding), so the slow check fails and
the duel continues as if that summon or effect weren't available.
"""
import os
import subprocess
import sys

ROOT = os.path.expanduser("~/ygo/edopro-core")
STEP_LIMIT_S = 1.0  # CPU seconds; normal calls take milliseconds, legit Branded Fusion checks exceeded 0.1

PATCHES = [
    ("interpreter.cpp", '#include "scriptlib.h"\n',
     '#include "scriptlib.h"\n'
     "#include <ctime>\n\n"
     "// ygosim watchdog (wsl/patch_core.py): CPU-time deadline for the current OCG_DuelProcess call.\n"
     "thread_local double ygosim_deadline = 0;  // 0 = no deadline\n"
     "double ygosim_thread_cpu() {\n"
     "\ttimespec ts;\n"
     "\tclock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);\n"
     "\treturn static_cast<double>(ts.tv_sec) + ts.tv_nsec * 1e-9;\n"
     "}\n"
     "static void ygosim_watchdog(lua_State* L, lua_Debug*) {\n"
     "\tif(ygosim_deadline > 0 && ygosim_thread_cpu() > ygosim_deadline)\n"
     "\t\tluaL_error(L, \"ygosim watchdog: process step over its CPU time limit\");\n"
     "}\n"),
    ("interpreter.cpp", "\tlua_state = luaL_newstate();\n",
     "\tlua_state = luaL_newstate();\n"
     "\tlua_sethook(lua_state, ygosim_watchdog, LUA_MASKCOUNT, 100000);  // inherited by coroutines\n"),
    ("ocgapi.cpp", '#include "ocgapi.h"\n',
     '#include "ocgapi.h"\n'
     "extern thread_local double ygosim_deadline;\n"
     "double ygosim_thread_cpu();\n"),
    ("ocgapi.cpp",
     "\tpduel->buff.clear();\n\tauto flag = OCG_DUEL_STATUS_END;\n\tdo {\n",
     "\tpduel->buff.clear();\n\tauto flag = OCG_DUEL_STATUS_END;\n"
     f"\tygosim_deadline = ygosim_thread_cpu() + {STEP_LIMIT_S};\n"
     "\tdo {\n"),
    ("ocgapi.cpp",
     "\t} while(pduel->buff.size() == 0 && flag == OCG_DUEL_STATUS_CONTINUE);\n\treturn flag;\n",
     "\t} while(pduel->buff.size() == 0 && flag == OCG_DUEL_STATUS_CONTINUE);\n"
     "\tygosim_deadline = 0;\n\treturn flag;\n}\n\n"
     # Hidden-information sampling (belief.py / game.py): give one hidden card a sampled identity. The
     # card object stays where it is (no move, no events); its card data and initial effects are
     # replaced as Card.Recreate with replace_effect does, minus the copy-effect status it leaves.
     "void YGOSIM_SetCardCode(OCG_Duel ocg_duel, uint8_t playerid, uint32_t location, uint32_t sequence,\n"
     "                        uint32_t code) {\n"
     "\tauto* pduel = static_cast<duel*>(ocg_duel);\n"
     "\tauto& pl = pduel->game_field->player[playerid];\n"
     "\tcard_vector* list = location == LOCATION_HAND ? &pl.list_hand : location == LOCATION_DECK ? &pl.list_main\n"
     "\t\t: location == LOCATION_EXTRA ? &pl.list_extra : location == LOCATION_MZONE ? &pl.list_mzone\n"
     "\t\t: location == LOCATION_SZONE ? &pl.list_szone : nullptr;\n"
     "\tif(!list || sequence >= list->size() || !code)\n"
     "\t\treturn;\n"
     "\tcard* pcard = (*list)[sequence];\n"
     "\tif(!pcard || pcard->data.code == code)\n"
     "\t\treturn;\n"
     "\tif((location & LOCATION_ONFIELD) && !(pcard->current.position & POS_FACEDOWN))\n"
     "\t\treturn;  // face-up field cards are public: never resampled\n"
     "\tfor(auto it = pcard->indexer.begin(); it != pcard->indexer.end();) {\n"
     "\t\tauto rm = it++;\n"
     "\t\tif(rm->first->is_flag(EFFECT_FLAG_INITIAL))\n"
     "\t\t\tpcard->remove_effect(rm->first, rm->second);\n"
     "\t}\n"
     "\tpcard->recreate(code);\n"
     "\t// Alt-art printings have no script of their own: effects come from the base card (alias).\n"
     "\tuint32_t al = pcard->data.alias;\n"
     "\tuint32_t script = (al && (al > code ? al - code : code - al) < 20) ? al : code;\n"
     "\tif(!(pcard->data.type & TYPE_NORMAL)) {\n"
     "\t\tpcard->replace_effect(script, 0, 0, true);\n"
     "\t\tpcard->set_status(STATUS_EFFECT_REPLACED, FALSE);\n"
     "\t}\n"),
    ("ocgapi.h", "OCGAPI int OCG_DuelProcess(OCG_Duel ocg_duel);\n",
     "OCGAPI int OCG_DuelProcess(OCG_Duel ocg_duel);\n"
     "OCGAPI void YGOSIM_SetCardCode(OCG_Duel ocg_duel, uint8_t playerid, uint32_t location, uint32_t sequence,\n"
     "                               uint32_t code);\n"),
]


def main():
    files = sorted({rel for rel, *_ in PATCHES})
    subprocess.run(["git", "checkout", "--", *files], cwd=ROOT, check=True)
    for rel, old, new in PATCHES:
        path = os.path.join(ROOT, rel)
        src = open(path).read()
        if src.count(old) != 1:
            sys.exit(f"core patch target in {rel} found {src.count(old)} times (expected 1): {old[:60]!r}")
        open(path, "w").write(src.replace(old, new))
    print(f"{len(PATCHES)} core patches applied to {files}")


if __name__ == "__main__":
    main()
