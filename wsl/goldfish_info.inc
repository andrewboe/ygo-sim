  // ygosim: extra per-step info for search/goldfishing, plus a lite mode that skips the neural-net
  // observations (cards/actions/history), which dominate step cost and aren't needed for search.
  bool lite_ = false;
  int64_t duel_seed_ = -1;
  int64_t ygosim_resets_ = 0;

  // Option kinds: 0 = action, 1 = pass/decline (c, f, n...), 2 = end turn (e), 3 = phase move (b, m).
  static uint8_t ygosim_option_kind(int msg, const std::string &opt) {
    if (opt == "c" || opt == "f" || opt == "n" || opt.rfind("n ", 0) == 0) {
      return 1;
    }
    if (msg == MSG_SELECT_IDLECMD || msg == MSG_SELECT_BATTLECMD) {
      if (opt == "e") {
        return 2;
      }
      if (opt == "b" || opt == "m") {
        return 3;
      }
    }
    return 0;
  }

  void ygosim_write_info(State &state) {
    state["info:turn"_] = turn_count_;
    state["info:msg"_] = msg_;
    static const uint32_t locs[7] = {LOCATION_MZONE, LOCATION_SZONE, LOCATION_HAND, LOCATION_GRAVE,
                                     LOCATION_REMOVED, LOCATION_DECK, LOCATION_EXTRA};
    for (int p = 0; p < 2; ++p) {
      for (int k = 0; k < 7; ++k) {
        state["info:board_"_](p, k) = static_cast<int>(YGO_QueryFieldCount(pduel_, p, locs[k]));
      }
      int n = 0;
      for (uint8_t loc : {uint8_t(LOCATION_MZONE), uint8_t(LOCATION_SZONE)}) {
        for (const auto &c : get_cards_in_location(p, loc)) {
          if (n < 13 && !(c.location_ & LOCATION_OVERLAY)) {
            state["info:field_codes_"_](p, n++) = static_cast<int>(c.code_);
          }
        }
      }
    }
    int n_opt = std::min<int>(options_.size(), max_options());
    for (int i = 0; i < n_opt; ++i) {
      state["info:option_kinds_"_][i] = ygosim_option_kind(msg_, options_[i]);
    }
  }

