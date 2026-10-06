"""Patches ygo-agent's ygoenv for GCC 13 and the current edo9300 ygopro-core API.
Each run resets the patched files to git HEAD, then applies every patch once."""
import os
import re
import subprocess
import sys

ROOT = os.path.expanduser("~/ygo/ygo-agent/ygoenv/ygoenv")

# (file, old, new) literal replacements
PATCHES = [
    # GCC 13: brace-init bounds are ambiguous between Spec's tuple<D,D> and tuple<vector,vector> ctors.
    ("core/env_spec.h", "Spec<float>({-1}, {0.0, 1.0})",
     "Spec<float>({-1}, std::make_tuple(0.0f, 1.0f))"),
    # ygopro-core API: these now take pointers to their option/info structs.
    ("edopro/edopro.h", "OCG_CreateDuel(&pduel_, opts)", "OCG_CreateDuel(&pduel_, &opts)"),
    ("edopro/edopro.h", "OCG_DuelNewCard(pduel, info)", "OCG_DuelNewCard(pduel, &info)"),
    ("edopro/edopro.h", "OCG_DuelQuery(pduel, &length, info)", "OCG_DuelQuery(pduel, &length, &info)"),
    ("edopro/edopro.h", "OCG_DuelQueryLocation(pduel, &length, info)",
     "OCG_DuelQueryLocation(pduel, &length, &info)"),
    # Diagnostics: name the message that left callback_ empty instead of dying in std::function.
    ("edopro/edopro.h", "    int idx = action[\"action\"_];\n    callback_(idx);",
     "    int idx = action[\"action\"_];\n    check_callback();\n    callback_(idx);"),
    ("edopro/edopro.h", "          if (options_.size() == 1) {\n            callback_(0);",
     "          if (options_.size() == 1) {\n            check_callback();\n            callback_(0);"),
    ("edopro/edopro.h", "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {",
     "  int ygosim_last_msg_ = 0;\n"
     "  std::string ygosim_last_options_, ygosim_last_resp_;\n\n"
     "  void check_callback() {\n"
     "    if (!callback_) {\n"
     "      fmt::println(stderr, \"[ygosim] no callback for msg {} with {} options: {}\", msg_,\n"
     "                   options_.size(), fmt::join(options_, \" | \"));\n"
     "      std::fflush(stderr);\n"
     "      std::abort();\n"
     "    }\n"
     "    ygosim_last_msg_ = msg_;\n"
     "    ygosim_last_options_ = fmt::format(\"{}\", fmt::join(options_, \" | \"));\n"
     "  }\n\n"
     "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {"),
    ("edopro/edopro.h", "    uint32_t len = sizeof(value);\n    memcpy(resp_buf_, &value, len);\n",
     "    uint32_t len = sizeof(value);\n    memcpy(resp_buf_, &value, len);\n"
     "    ygosim_last_resp_ = fmt::format(\"msg {} -> int {}\", msg_, value);\n"),
    ("edopro/edopro.h", "    if (len == 0) {\n      len = buf[0];\n      OCG_DuelSetResponse(pduel, buf + 1, len);",
     "    {\n"
     "      uint32_t n = len == 0 ? buf[0] : len;\n"
     "      const uint8_t *b = len == 0 ? buf + 1 : buf;\n"
     "      ygosim_last_resp_ = fmt::format(\"msg {} -> bytes [{:02x}]\", msg_,\n"
     "                                      fmt::join(std::vector<uint8_t>(b, b + n), \" \"));\n"
     "    }\n"
     "    if (len == 0) {\n      len = buf[0];\n      OCG_DuelSetResponse(pduel, buf + 1, len);"),
    ("edopro/edopro.h", "      throw std::runtime_error(\"Retry\");",
     "      fmt::println(stderr, \"[ygosim] MSG_RETRY; last agent decision: msg {} options [{}]; \"\n"
     "                   \"last response sent: {}\", ygosim_last_msg_, ygosim_last_options_, ygosim_last_resp_);\n"
     "      std::fflush(stderr);\n"
     "      throw std::runtime_error(\"Retry\");"),
    # Card/tribute responses: the type-3 bitset branch packs indices into one uint8, silently
    # dropping any index >= 8. Always use type 2 (u8 index list), valid below 256 cards.
    ("edopro/edopro.h", "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {\n",
     "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {\n"
     "    if (maxseq < 256) {\n      return 2;  // ygosim\n    }\n"),
    # Select-sum: respect the min/max selected-card count the core enforces (mode 0), ...
    ("edopro/edopro.h",
     "      std::vector<std::vector<int>> combs =\n"
     "          combinations_with_weight2(card_levels, expected, true);\n",
     "      std::vector<std::vector<int>> combs =\n"
     "          combinations_with_weight2(card_levels, expected, true);\n"
     + open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "select_sum_filter.inc")).read()),
    # ... which also makes ygo-agent's restrictions on select-sum shapes unnecessary ...
    ("edopro/edopro.h",
     "      if (mode == 0) {\n"
     "        if (must_select_size != 1) {\n",
     "      if (false) {  // ygosim: validated against the core's rules below instead\n"
     "        if (must_select_size != 1) {\n"),
    ("edopro/edopro.h",
     "      } else {\n"
     "        if (min != 0 || max != 0 || must_select_size != 0) {\n",
     "      } else if (false) {\n"
     "        if (min != 0 || max != 0 || must_select_size != 0) {\n"),
    # ... (every must-select card counts toward the target, not just the first) ...
    ("edopro/edopro.h",
     "        if (must_select_size > 0) {\n"
     "          expected -= must_select_params[0] & 0xff;\n"
     "        }\n"
     "      }\n\n"
     "      uint8_t select_size",
     "        for (int p : must_select_params) {  // ygosim: all must-select cards, not just the first\n"
     "          expected -= p & 0xffff;\n"
     "        }\n"
     "      }\n\n"
     "      uint8_t select_size"),
    # ... and answer with a u8 index list instead of a one-byte bitset.
    ("edopro/edopro.h",
     "          int32_t ret = 3;\n"
     "          memcpy(resp_buf_, &ret, sizeof(ret));\n"
     "          uint8_t v = 0;\n"
     "          const auto &comb = combs[idx];\n"
     "          // TODO: support more than 8 cards\n"
     "          if (must_select_size + comb.size() > 8) {\n"
     "            throw std::runtime_error(\"must_select_size + comb.size() > 8\");\n"
     "          }\n"
     "          // for (int i = 0; i < must_select_size; ++i) {\n"
     "          //   v |= (1 << i);\n"
     "          // }\n"
     "          for (int i = 0; i < comb.size(); ++i) {\n"
     "            v |= (1 << (comb[i]));\n"
     "          }\n"
     "          memcpy(resp_buf_ + 4, &v, sizeof(v));\n"
     "          YGO_SetResponseb(pduel_, resp_buf_, 5);",
     "          const auto &comb = combs[idx];\n"
     "          int32_t ret = 2;  // ygosim: u8 index list\n"
     "          uint32_t n = comb.size();\n"
     "          memcpy(resp_buf_, &ret, sizeof(ret));\n"
     "          memcpy(resp_buf_ + 4, &n, sizeof(n));\n"
     "          for (uint32_t i = 0; i < n; ++i) {\n"
     "            resp_buf_[8 + i] = static_cast<uint8_t>(comb[i]);\n"
     "          }\n"
     "          YGO_SetResponseb(pduel_, resp_buf_, 8 + n);"),
    # Selections of more than max_multi_select cards were only handled for hand-limit discards;
    # pick randomly for any of them (rare, and the option space is combinatorial).
    ("edopro/edopro.h", "        if (discard_hand_) {\n          // random discard",
     "        if (true) {  // ygosim: was discard_hand_ only\n          // random discard"),
    # Route messages the 2024 env never handled (see extra_messages.inc) before its own dispatch.
    ("edopro/edopro.h", "    msg_ = int(data_[dp_++]);\n    options_ = {};\n",
     "    msg_ = int(data_[dp_++]);\n    options_ = {};\n"
     "    if (ygosim_handle_extra()) {\n      return;\n    }\n"),
    # Random hand-limit discard used the old length-prefixed response; the core wants
    # {int32 type=2, u32 count, u8 indices...}.
    ("edopro/edopro.h",
     "          resp_buf_[0] = min;\n"
     "          for (int i = 0; i < min; ++i) {\n"
     "            resp_buf_[i + 1] = comb[i];\n"
     "          }\n"
     "          YGO_SetResponseb(pduel_, resp_buf_);",
     "          int32_t ret = 2;\n"
     "          uint32_t n = min;\n"
     "          memcpy(resp_buf_, &ret, sizeof(ret));\n"
     "          memcpy(resp_buf_ + 4, &n, sizeof(n));\n"
     "          for (int i = 0; i < min; ++i) {\n"
     "            resp_buf_[8 + i] = static_cast<uint8_t>(comb[i]);\n"
     "          }\n"
     "          YGO_SetResponseb(pduel_, resp_buf_, 8 + n);"),
    # Diagnostics: name the unknown card code instead of a bare map::at() failure.
    ("edopro/edopro.h", "inline const Card &c_get_card(CardCode code) { return cards_.at(code); }",
     "inline const Card &c_get_card(CardCode code) {\n"
     "  auto it = cards_.find(code);\n"
     "  if (it == cards_.end()) {\n"
     "    fmt::println(stderr, \"[ygosim] c_get_card: unknown code {} ({:#x})\", code, code);\n"
     "    std::fflush(stderr);\n"
     "    throw std::runtime_error(\"unknown card code \" + std::to_string(code));\n"
     "  }\n"
     "  return it->second;\n"
     "}"),
    # A message that neither offers options nor sends a response leaves the core awaiting forever;
    # next() then spins on empty process calls. Fail loudly with the culprit instead.
    ("edopro/edopro.h",
     "        duel_status_ = YGO_Process(pduel_);\n"
     "        fdl_ = YGO_GetMessage(pduel_, data_);\n"
     "        if (fdl_ == 0) {\n"
     "          continue;\n"
     "        }\n",
     "        duel_status_ = YGO_Process(pduel_);\n"
     "        fdl_ = YGO_GetMessage(pduel_, data_);\n"
     "        if (fdl_ == 0) {\n"
     "          if (duel_status_ == OCG_DUEL_STATUS_AWAITING && ++ygosim_idle_spins_ > 1000) {\n"
     "            throw std::runtime_error(fmt::format(\n"
     "                \"[ygosim] core awaiting a response nobody sent; last message {}\", msg_));\n"
     "          }\n"
     "          continue;\n"
     "        }\n"
     "        ygosim_idle_spins_ = 0;\n"),
    # Script cache self-deadlock: the shared lock was held through OCG_LoadScript, and a script that
    # loads a not-yet-cached helper (Duel.LoadScript) re-enters and waits on the exclusive lock
    # forever. Copy the entry under the lock, then call the core unlocked.
    ("edopro/edopro.h",
     "  std::string path(name);\n"
     "  std::shared_lock<std::shared_timed_mutex> lock(scripts_mtx);\n"
     "  auto it = cards_script_.find(path);\n"
     "  if (it == cards_script_.end()) {\n"
     "    lock.unlock();\n"
     "    int len;\n"
     "    const char *buf = read_card_script(path, &len);\n"
     "    std::unique_lock<std::shared_timed_mutex> ulock(scripts_mtx);\n"
     "    cards_script_[path] = {buf, len};\n"
     "    it = cards_script_.find(path);\n"
     "  }\n"
     "  int len = it->second.len;\n"
     "  auto res = len && OCG_LoadScript(duel, it->second.buf, static_cast<uint32_t>(len), name);",
     "  std::string path(name);\n"
     "  const char *buf = nullptr;\n"
     "  int len = 0;\n"
     "  {\n"
     "    std::shared_lock<std::shared_timed_mutex> lock(scripts_mtx);\n"
     "    auto it = cards_script_.find(path);\n"
     "    if (it != cards_script_.end()) {\n"
     "      buf = it->second.buf;\n"
     "      len = it->second.len;\n"
     "    }\n"
     "  }\n"
     "  if (buf == nullptr && len == 0) {\n"
     "    const char *fresh = read_card_script(path, &len);\n"
     "    std::unique_lock<std::shared_timed_mutex> ulock(scripts_mtx);\n"
     "    auto [it, inserted] = cards_script_.try_emplace(path, card_script{fresh, len});\n"
     "    if (!inserted) {\n"
     "      delete[] fresh;  // another thread cached it first\n"
     "    }\n"
     "    buf = it->second.buf;\n"
     "    len = it->second.len;\n"
     "  }\n"
     "  auto res = len && OCG_LoadScript(duel, buf, static_cast<uint32_t>(len), name);"),
    # Quiet a known ygo-agent TODO (option spec missing from the obs index; it falls back to idx 1)
    # that otherwise dumps the whole index to stdout. Set YGOSIM_TRACE_SPEC=1 to see it.
    ("edopro/edopro.h",
     "        fmt::println(\"Spec2index:\");\n"
     "        for (auto &[k, v] : spec2index) {\n"
     "          fmt::println(\"{}: {}\", k, v);\n"
     "        }\n",
     "        if (std::getenv(\"YGOSIM_TRACE_SPEC\")) {\n"
     "          fmt::println(stderr, \"[ygosim] option spec {} not in obs index ({} entries)\", spec,\n"
     "                       spec2index.size());\n"
     "        }\n"),
    # Goldfish/search support: config, info specs, deterministic resets, lite mode.
    ("edopro/edopro.h",
     "                    \"max_multi_select\"_.Bind(5), \"record\"_.Bind(false));",
     "                    \"max_multi_select\"_.Bind(5), \"record\"_.Bind(false),\n"
     "                    \"lite\"_.Bind(false), \"duel_seed\"_.Bind(int64_t(-1)),\n"
     "                    \"shuffle2\"_.Bind(true));"),
    ("edopro/edopro.h", "      load_deck(i);\n",
     "      load_deck(i, i != 1 || shuffle2_);  // ygosim: stacked opponent deck for controlled hands\n"),
    ("edopro/edopro.h",
     "        \"info:win_reason\"_.Bind(Spec<int>({}, {-1, 1})));",
     "        \"info:win_reason\"_.Bind(Spec<int>({}, {-1, 1})),\n"
     "        \"info:turn\"_.Bind(Spec<int>({})),\n"
     "        \"info:msg\"_.Bind(Spec<int>({})),\n"
     "        \"info:board_\"_.Bind(Spec<int>({2, 7})),\n"
     "        \"info:field_codes_\"_.Bind(Spec<int>({2, 13})),\n"
     "        \"info:hand_codes_\"_.Bind(Spec<int>({2, 15})),\n"
     "        \"info:option_kinds_\"_.Bind(Spec<uint8_t>({conf[\"max_options\"_]})),\n"
     "        \"info:option_hash_\"_.Bind(Spec<int>({conf[\"max_options\"_]})),\n"
     "        \"info:option_card_\"_.Bind(Spec<int>({conf[\"max_options\"_]})));"),
    ("edopro/edopro.h",
     "        verbose_(spec.config[\"verbose\"_]), record_(spec.config[\"record\"_]),",
     "        verbose_(spec.config[\"verbose\"_]), record_(spec.config[\"record\"_]),\n"
     "        lite_(spec.config[\"lite\"_]), duel_seed_(spec.config[\"duel_seed\"_]),\n"
     "        shuffle2_(spec.config[\"shuffle2\"_]),"),
    ("edopro/edopro.h",
     "  void Reset() override {\n",
     "  void Reset() override {\n"
     "    if (duel_started_) {  // ygosim: resetting mid-duel leaked the old duel (and its Lua state)\n"
     "      std::unique_lock<std::shared_timed_mutex> end_lock(duel_mtx);\n"
     "      YGO_EndDuel(pduel_);\n"
     "      end_lock.unlock();\n"
     "      duel_started_ = false;\n"
     "    }\n"
     "    if (duel_seed_ >= 0) {  // ygosim: every env deals opening (duel_seed + set_opening(n))\n"
     "      gen_.seed(static_cast<uint64_t>(duel_seed_ + g_ygosim_opening.load()));\n"
     "    }\n"),
    ("edopro/edopro.h", "#include <shared_mutex>\n", "#include <shared_mutex>\n#include <atomic>\n"),
    ("edopro/edopro.h",
     "static void init_module(const std::string &db_path,",
     "// ygosim: which opening deterministic (duel_seed >= 0) envs deal on their next reset.\n"
     "static std::atomic<int64_t> g_ygosim_opening{0};\n"
     "static void set_opening(int64_t n) { g_ygosim_opening.store(n); }\n\n"
     "static void init_module(const std::string &db_path,"),
    ("edopro/edopro.cpp",
     "  m.def(\"init_module\", &edopro::init_module);",
     "  m.def(\"init_module\", &edopro::init_module);\n"
     "  m.def(\"set_opening\", &edopro::set_opening);"),
    ("edopro/edopro.h",
     "    state[\"info:win_reason\"_] = win_reason;\n",
     "    state[\"info:win_reason\"_] = win_reason;\n"
     "    ygosim_write_info(state);\n"),
    ("edopro/edopro.h",
     "    SpecIndex spec2index;\n    _set_obs_cards(state[\"obs:cards_\"_], spec2index, to_play_);",
     "    if (lite_) {\n"
     "      if (n_options > max_options()) {\n"
     "        options_.resize(max_options());\n"
     "      }\n"
     "      state[\"info:num_options\"_] = static_cast<int>(options_.size());\n"
     "      return;\n"
     "    }\n"
     "    SpecIndex spec2index;\n    _set_obs_cards(state[\"obs:cards_\"_], spec2index, to_play_);"),
    ("edopro/edopro.h",
     "            callback_(0);\n"
     "            update_h_card_ids(to_play_, 0);\n"
     "            update_history_actions(to_play_, 0);",
     "            callback_(0);\n"
     "            if (!lite_) {\n"
     "              update_h_card_ids(to_play_, 0);\n"
     "              update_history_actions(to_play_, 0);\n"
     "            }"),
    # Diagnostics: log every duel result (env var YGOSIM_TRACE_WIN=1).
    ("edopro/edopro.h", "      auto reason = read_u8();\n      auto winner = players_[player];",
     "      auto reason = read_u8();\n"
     "      if (std::getenv(\"YGOSIM_TRACE_WIN\")) {\n"
     "        fmt::println(stderr, \"[ygosim] MSG_WIN player {} reason {:#x} turn {} lp {}/{}\", player, reason,\n"
     "                     turn_count_, lp_[0], lp_[1]);\n"
     "      }\n"
     "      auto winner = players_[player];"),
    # Diagnostics: print a native stack trace on SIGSEGV/SIGABRT (no gdb in WSL without sudo).
    ("edopro/edopro.h", "#include <fmt/core.h>\n",
     "#include <fmt/core.h>\n#include <glog/logging.h>\n"),
    ("edopro/edopro.h", "                        const std::map<std::string, std::string> &decks) {\n",
     "                        const std::map<std::string, std::string> &decks) {\n"
     "  google::InstallFailureSignalHandler();\n"),
]

# Regex patches: Spec<int>({}, {a, b}) -> Spec<int>({}, std::make_tuple<int, int>(a, b))
REGEX_PATCHES = [
    ("edopro/edopro.h", re.compile(r"Spec<int>\(\{\}, \{([^{}]+?), ([^{}]+?)\}\)"),
     r"Spec<int>({}, std::make_tuple<int, int>(\1, \2))"),
]


# Region patches: replace everything from `start` up to (not including) `end` with a file's contents.
HERE = os.path.dirname(os.path.abspath(__file__))
REGION_PATCHES = [
    # Query buffers are now tagged records; the 2024 fixed-offset parsers misread every card.
    ("edopro/edopro.h", "  Card get_card(PlayerId player, uint8_t loc, uint8_t seq) {\n",
     "  std::vector<Card> read_cardlist(bool extra", os.path.join(HERE, "query_parser.inc")),
    ("edopro/edopro.h", "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {",
     "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {", os.path.join(HERE, "goldfish_info.inc")),
    # Zero-length region = insert the file before `end`.
    ("edopro/edopro.h", "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {",
     "  int GetSuitableReturn(uint32_t maxseq, uint32_t size) {", os.path.join(HERE, "extra_messages.inc")),
]


def main():
    files = sorted({rel for rel, *_ in PATCHES + REGEX_PATCHES + REGION_PATCHES})
    subprocess.run(["git", "checkout", "--", *files], cwd=ROOT, check=True)
    changed = 0
    for rel, old, new in PATCHES:
        path = os.path.join(ROOT, rel)
        src = open(path).read()
        if src.count(old) != 1:
            sys.exit(f"patch target in {rel} found {src.count(old)} times (expected 1): {old[:60]!r}")
        open(path, "w").write(src.replace(old, new))
        changed += 1
    for rel, pattern, repl in REGEX_PATCHES:
        path = os.path.join(ROOT, rel)
        src = open(path).read()
        out, n = pattern.subn(repl, src)
        open(path, "w").write(out)
        changed += n
    for rel, start, end, body_file in REGION_PATCHES:
        path = os.path.join(ROOT, rel)
        src = open(path).read()
        i, j = src.find(start), src.find(end)
        if i < 0 or j < i or src.count(start) != 1:
            sys.exit(f"region patch markers not found in {rel}: {start.strip()!r} .. {end!r}")
        open(path, "w").write(src[:i] + open(body_file).read() + src[j:])
        changed += 1
    print(f"{changed} patches applied to {files}")


if __name__ == "__main__":
    sys.exit(main())
