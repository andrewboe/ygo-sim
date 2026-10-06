  // ygosim: extra per-step info for search/goldfishing, plus a lite mode that skips the neural-net
  // observations (cards/actions/history), which dominate step cost and aren't needed for search.
  bool lite_ = false;
  int64_t duel_seed_ = -1;
  bool shuffle2_ = true;  // false: player 1's deck is stacked in file order (last main-deck line on top)
  int ygosim_idle_spins_ = 0;

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

  // Stable identity of an option across replays and hand orderings: decision type, action letters,
  // and the codes of the cards it refers to (not their zone/slot). Search policies key on this.
  // `first_card` receives the code-list id of the first card the option refers to (0 if none).
  int32_t ygosim_option_hash(const std::string &opt, PlayerId player, int32_t *first_card) {
    uint32_t h = 2166136261u;
    auto mix = [&h](uint32_t v) { h = (h ^ v) * 16777619u; };
    mix(static_cast<uint32_t>(msg_));
    std::vector<CardId> ids;
    try {
      ids = parse_card_ids(opt, player);
    } catch (const std::exception &) {
      ids.clear();
    }
    *first_card = ids.empty() ? 0 : static_cast<int32_t>(ids[0]);
    if (ids.empty()) {
      for (char ch : opt) {
        mix(static_cast<uint8_t>(ch));
      }
    } else {
      if (msg_ == MSG_SELECT_IDLECMD || msg_ == MSG_SELECT_BATTLECMD) {
        mix(static_cast<uint8_t>(opt[0]));  // action: summon, set, activate...
      }
      if (std::isalpha(static_cast<unsigned char>(opt.back()))) {
        mix(static_cast<uint8_t>(opt.back()));  // which effect of the card
      }
      std::sort(ids.begin(), ids.end());
      for (CardId id : ids) {
        mix(id);
      }
    }
    return static_cast<int32_t>(h);
  }

  void ygosim_write_info(State &state) {
    state["info:turn"_] = turn_count_;
    state["info:msg"_] = msg_;
    state["info:turn_player"_] = static_cast<int>(tp_);
    state["info:lp_"_][0] = lp_[0];
    state["info:lp_"_][1] = lp_[1];
    if (!duel_started_) {
      return;  // duel ended and was destroyed (_duel_end); nothing left to query
    }
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
            // Face-down cards are flagged by a negative code (set traps count differently).
            bool face_down = c.position_ & POS_FACEDOWN;
            state["info:field_codes_"_](p, n++) = static_cast<int>(c.code_) * (face_down ? -1 : 1);
          }
        }
      }
      int h = 0;
      for (const auto &c : get_cards_in_location(p, LOCATION_HAND)) {
        if (h < 15) {
          state["info:hand_codes_"_](p, h++) = static_cast<int>(c.code_);
        }
      }
    }
    int n_opt = std::min<int>(options_.size(), max_options());
    for (int i = 0; i < n_opt; ++i) {
      state["info:option_kinds_"_][i] = ygosim_option_kind(msg_, options_[i]);
      int32_t card = 0;
      state["info:option_hash_"_][i] = ygosim_option_hash(options_[i], to_play_, &card);
      state["info:option_card_"_][i] = card;
      // Action letter (idle: s summon, c special summon, r reposition, m set monster, t set, v activate).
      state["info:option_act_"_][i] = static_cast<uint8_t>(options_[i].empty() ? 0 : options_[i][0]);
    }
  }

