  // ygosim: extra per-step info for search/goldfishing, plus a lite mode that skips the neural-net
  // observations (cards/actions/history), which dominate step cost and aren't needed for search.
  bool lite_ = false;
  int64_t duel_seed_ = -1;
  bool ygosim_replay_ = false;  // set per step by the replay flag (action + 1000)
  bool shuffle2_ = true;  // false: player 1's deck is stacked in file order (last main-deck line on top)
  int ygosim_idle_spins_ = 0;
  uint32_t ygosim_pos_code_ = 0;  // card of the pending MSG_SELECT_POSITION
  // Duel context the lite env never parses (WindBot's Duel.CurrentChain, ChainTargets, LastSummonedCards),
  // recorded by peeking messages in ygosim_track_message without consuming them.
  struct YgosimLink {
    uint32_t code;
    uint8_t controller;
    uint8_t location;
    uint32_t sequence;
    uint32_t target = 0;   // first card it targeted
    bool negated = false;  // activation negated or effect disabled
  };
  std::vector<YgosimLink> ygosim_chain_;               // the chain being built or resolved, link 1 first
  std::vector<YgosimLink> ygosim_resolved_;            // links resolved this turn, in order
  std::vector<uint32_t> ygosim_chain_targets_;         // targets of the latest chain link
  std::vector<std::pair<uint32_t, uint8_t>> ygosim_summoned_;  // last summon group: (code, controller)
  bool ygosim_summon_done_ = true;
  // Deck / Extra Deck contents cost a query per step: only when the card handlers ask (YGOSIM_CONTEXT set).
  const bool ygosim_full_context_ = std::getenv("YGOSIM_CONTEXT") != nullptr;

  // Effect description of each activation option of the pending decision, keyed by option string and
  // filled where the env builds the options. EDOPro's desc is code << 20 | string index (64 bits); the env
  // keeps 32: the index (low 20 bits) and the card code's low 12 bits. System strings have no code part.
  ankerl::unordered_dense::map<std::string, uint32_t> ygosim_desc_;

  void ygosim_track_message() {
    auto dp = dp_;
    ygosim_desc_.clear();
    try {
      switch (msg_) {
      case MSG_START:
        ygosim_resolved_.clear();
        ygosim_chain_.clear();
        ygosim_chain_targets_.clear();
        ygosim_summoned_.clear();
        ygosim_summon_done_ = true;
        break;
      case MSG_CHAINING: {
        uint32_t code = read_u32();
        auto li = read_loc_info();
        ygosim_chain_.push_back({code, li.controler, li.location, li.sequence});
        ygosim_chain_targets_.clear();
        break;
      }
      case MSG_CHAIN_END:
        ygosim_chain_.clear();
        ygosim_chain_targets_.clear();
        break;
      case MSG_NEW_TURN:
        ygosim_resolved_.clear();
        break;
      case MSG_CHAIN_NEGATED: case MSG_CHAIN_DISABLED: {
        uint8_t ct = read_u8();
        if (ct >= 1 && ct <= ygosim_chain_.size()) {
          ygosim_chain_[ct - 1].negated = true;
        }
        break;
      }
      case MSG_CHAIN_SOLVED: {
        uint8_t ct = read_u8();
        if (ct >= 1 && ct <= ygosim_chain_.size() && ygosim_resolved_.size() < 16) {
          ygosim_resolved_.push_back(ygosim_chain_[ct - 1]);
        }
        break;
      }
      case MSG_BECOME_TARGET: {
        auto count = compat_read<uint8_t, uint32_t>();
        for (uint32_t k = 0; k < count; ++k) {
          auto li = read_loc_info();
          ygosim_chain_targets_.push_back(get_card(li.controler, li.location, li.sequence).code_);
        }
        if (!ygosim_chain_.empty() && !ygosim_chain_.back().target && !ygosim_chain_targets_.empty()) {
          ygosim_chain_.back().target = ygosim_chain_targets_.front();
        }
        break;
      }
      case MSG_SUMMONING: case MSG_SPSUMMONING: case MSG_FLIPSUMMONING: {
        if (ygosim_summon_done_) {
          ygosim_summoned_.clear();
          ygosim_summon_done_ = false;
        }
        uint32_t code = read_u32();
        auto li = read_loc_info();
        ygosim_summoned_.push_back({code, li.controler});
        break;
      }
      case MSG_SUMMONED: case MSG_SPSUMMONED: case MSG_FLIPSUMMONED:
        ygosim_summon_done_ = true;
        break;
      default:
        break;
      }
    } catch (const std::exception &) {
    }
    dp_ = dp;
  }

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

  // Apply this env's staged hidden identities (stage_hidden): hand/deck/extra by index, face-down
  // field cards by order (S/T zones, then monster zones), or a permutation of the deck's codes.
  void ygosim_apply_staged() {
    std::vector<int> e;
    {
      std::lock_guard<std::mutex> lock(g_ygosim_stage_mtx);
      auto it = g_ygosim_stage.find(env_id_);
      if (it == g_ygosim_stage.end()) {
        return;
      }
      e.swap(it->second);
      g_ygosim_stage.erase(it);
    }
    for (size_t k = 0; k + 3 < e.size(); k += 4) {
      auto p = static_cast<PlayerId>(e[k]);
      int loc = e[k + 1], idx = e[k + 2];
      auto code = static_cast<uint32_t>(e[k + 3]);
      if (loc == 0x100) {
        int n = 0;
        for (uint8_t l : {uint8_t(LOCATION_SZONE), uint8_t(LOCATION_MZONE)}) {
          for (const auto &c : get_cards_in_location(p, l)) {
            if ((c.position_ & POS_FACEDOWN) && !(c.location_ & LOCATION_OVERLAY) && n++ == idx) {
              YGOSIM_SetCardCode(pduel_, p, l, c.sequence_, code);
            }
          }
        }
      } else if (loc == 0x200) {
        auto cards = get_cards_in_location(p, LOCATION_DECK);
        std::vector<uint32_t> codes;
        for (const auto &c : cards) {
          codes.push_back(c.code_);
        }
        std::mt19937 g(static_cast<uint32_t>(idx));
        std::shuffle(codes.begin(), codes.end(), g);
        for (size_t j = 0; j < cards.size(); ++j) {
          YGOSIM_SetCardCode(pduel_, p, LOCATION_DECK, cards[j].sequence_, codes[j]);
        }
      } else {
        YGOSIM_SetCardCode(pduel_, p, static_cast<uint32_t>(loc), static_cast<uint32_t>(idx), code);
      }
    }
  }

  void ygosim_write_info(State &state) {
    state["info:turn"_] = turn_count_;
    state["info:msg"_] = msg_;
    state["info:turn_player"_] = static_cast<int>(tp_);
    state["info:lp_"_][0] = lp_[0];
    state["info:lp_"_][1] = lp_[1];
    if (!duel_started_ || ygosim_replay_) {
      // Duel destroyed (_duel_end), or a replay step whose info nobody reads: skip the board,
      // hand and per-option queries (the bulk of per-step cost during replays).
      return;
    }
    static const uint32_t locs[7] = {LOCATION_MZONE, LOCATION_SZONE, LOCATION_HAND, LOCATION_GRAVE,
                                     LOCATION_REMOVED, LOCATION_DECK, LOCATION_EXTRA};
    for (int p = 0; p < 2; ++p) {
      for (int k = 0; k < 7; ++k) {
        state["info:board_"_](p, k) = static_cast<int>(YGO_QueryFieldCount(pduel_, p, locs[k]));
      }
      int n = 0;
      int overlays[7] = {0, 0, 0, 0, 0, 0, 0};
      for (uint8_t loc : {uint8_t(LOCATION_MZONE), uint8_t(LOCATION_SZONE)}) {
        for (const auto &c : get_cards_in_location(p, loc)) {
          if ((c.location_ & LOCATION_OVERLAY) && loc == LOCATION_MZONE && c.sequence_ < 7) {
            overlays[c.sequence_] += 1;  // Xyz materials attached
          }
          if (n < 13 && !(c.location_ & LOCATION_OVERLAY)) {
            // Face-down cards are flagged by a negative code (set traps count differently).
            bool face_down = c.position_ & POS_FACEDOWN;
            state["info:field_codes_"_](p, n++) = static_cast<int>(c.code_) * (face_down ? -1 : 1);
            // Every zone by slot: Monster Zones 0-6, Spell & Trap Zones 8-15 (field 13, Pendulum 14-15).
            int row = (loc == LOCATION_MZONE ? 0 : 8) + static_cast<int>(c.sequence_);
            if (row < 16) {
              state["info:zone_cards_"_](p, row, 0) = static_cast<int>(c.code_);
              state["info:zone_cards_"_](p, row, 1) = static_cast<int>(c.position_);
              state["info:zone_cards_"_](p, row, 2) = c.attack_;
              state["info:zone_cards_"_](p, row, 3) = c.defense_;
              state["info:zone_cards_"_](p, row, 4) = static_cast<int>(c.level_);
            }
            // Monster Zone stats by slot (0-4 main, 5-6 Extra): current ATK, DEF, position. Face-down
            // monsters keep their stats hidden. Link monsters have no DEF (the query returns markers).
            if (loc == LOCATION_MZONE && c.sequence_ < 7) {
              bool link = false;
              try {
                link = c_get_card(c.code_).type() & TYPE_LINK;
              } catch (const std::exception &) {
              }
              state["info:field_stats_"_](p, c.sequence_, 0) = face_down ? 0 : c.attack_;
              state["info:field_stats_"_](p, c.sequence_, 1) = face_down || link ? 0 : c.defense_;
              state["info:field_stats_"_](p, c.sequence_, 2) = static_cast<int>(c.position_);
            }
          }
        }
      }
      for (int z = 0; z < 7; ++z) {
        state["info:zone_cards_"_](p, z, 5) = overlays[z];
      }
      int h = 0;
      for (const auto &c : get_cards_in_location(p, LOCATION_HAND)) {
        if (h < 15) {
          state["info:hand_codes_"_](p, h++) = static_cast<int>(c.code_);
        }
      }
      // Public cards beyond the field: graveyard and face-up banished (belief.py's evidence).
      int u = 0, g = 0, r = 0;
      for (uint8_t loc : {uint8_t(LOCATION_GRAVE), uint8_t(LOCATION_REMOVED)}) {
        for (const auto &c : get_cards_in_location(p, loc)) {
          bool down = loc == LOCATION_REMOVED && (c.position_ & POS_FACEDOWN);
          if (u < 40 && !down) {
            state["info:public_codes_"_](p, u++) = static_cast<int>(c.code_);
          }
          if (loc == LOCATION_GRAVE && g < 40) {
            state["info:grave_codes_"_](p, g++) = static_cast<int>(c.code_);
          } else if (loc == LOCATION_REMOVED && r < 40) {
            state["info:banished_codes_"_](p, r++) = static_cast<int>(c.code_) * (down ? -1 : 1);
          }
        }
      }
      if (ygosim_full_context_) {  // Deck / Extra Deck (the handlers read only the deciding player's own)
        int d = 0, x = 0;
        for (const auto &c : get_cards_in_location(p, LOCATION_DECK)) {
          if (d < 60) {
            state["info:deck_codes_"_](p, d++) = static_cast<int>(c.code_);
          }
        }
        for (const auto &c : get_cards_in_location(p, LOCATION_EXTRA)) {
          if (x < 20) {
            state["info:extra_codes_"_](p, x++) = static_cast<int>(c.code_) * (c.position_ & POS_FACEUP ? -1 : 1);
          }
        }
      }
    }
    state["info:phase"_] = current_phase_;
    for (int k = 0; k < std::min<int>(ygosim_chain_.size(), 8); ++k) {
      state["info:chain_"_](k, 0) = static_cast<int>(ygosim_chain_[k].code);
      state["info:chain_"_](k, 1) = ygosim_chain_[k].controller;
      state["info:chain_"_](k, 2) = ygosim_chain_[k].location;
      state["info:chain_"_](k, 3) = static_cast<int>(ygosim_chain_[k].target);
    }
    for (int k = 0; k < std::min<int>(ygosim_resolved_.size(), 16); ++k) {
      state["info:resolved_"_](k, 0) = static_cast<int>(ygosim_resolved_[k].code);
      state["info:resolved_"_](k, 1) = ygosim_resolved_[k].controller;
      state["info:resolved_"_](k, 2) = ygosim_resolved_[k].negated;
      state["info:resolved_"_](k, 3) = static_cast<int>(ygosim_resolved_[k].target);
    }
    for (int k = 0; k < std::min<int>(ygosim_chain_targets_.size(), 4); ++k) {
      state["info:chain_targets_"_][k] = static_cast<int>(ygosim_chain_targets_[k]);
    }
    for (int k = 0; k < std::min<int>(ygosim_summoned_.size(), 5); ++k) {
      state["info:summoned_"_](k, 0) = static_cast<int>(ygosim_summoned_[k].first);
      state["info:summoned_"_](k, 1) = ygosim_summoned_[k].second;
    }
    int n_opt = std::min<int>(options_.size(), max_options());
    for (int i = 0; i < n_opt; ++i) {
      state["info:option_kinds_"_][i] = ygosim_option_kind(msg_, options_[i]);
      int32_t card = 0;
      state["info:option_hash_"_][i] = ygosim_option_hash(options_[i], to_play_, &card);
      if (msg_ == MSG_SELECT_POSITION && card_ids_.count(ygosim_pos_code_)) {
        card = c_get_card_id(ygosim_pos_code_);  // the card being positioned, not in the option string
      }
      state["info:option_card_"_][i] = card;
      // Action letter (idle: s summon, c special summon, r reposition, m set monster, t set, v activate).
      state["info:option_act_"_][i] = static_cast<uint8_t>(options_[i].empty() ? 0 : options_[i][0]);
      // Zone number in the option string ("m3", "os2", "h4" -> 3, 2, 4; 0 if none): place prompts and
      // card selections name their slot here, which option_card_ does not.
      int zone = 0;
      for (size_t k = 0; k < options_[i].size(); ++k) {
        if (std::isdigit(static_cast<unsigned char>(options_[i][k]))) {
          zone = std::atoi(options_[i].c_str() + k);
          break;
        }
      }
      state["info:option_zone_"_][i] = zone;
      auto d = ygosim_desc_.find(options_[i]);
      state["info:option_desc_"_][i] = static_cast<int>(d == ygosim_desc_.end() ? 0u : d->second);
    }
  }

