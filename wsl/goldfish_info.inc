  // ygosim: extra per-step info for search/goldfishing, plus a lite mode that skips the neural-net
  // observations (cards/actions/history), which dominate step cost and aren't needed for search.
  bool lite_ = false;
  int64_t duel_seed_ = -1;
  bool ygosim_replay_ = false;  // set per step by the replay flag (action + 1000)
  bool shuffle1_ = true;  // false: player 0's deck is stacked in file order (last main-deck line on top)
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
    uint32_t desc = 0;     // effect description (32 bits, see ygosim_desc_)
    uint8_t player = 0;    // activating player (WindBot's ActivatePlayer)
  };
  std::vector<YgosimLink> ygosim_chain_;               // the chain being built or resolved, link 1 first
  std::vector<YgosimLink> ygosim_resolved_;            // links resolved this turn, in order
  std::vector<uint32_t> ygosim_chain_targets_;         // targets of the latest chain link
  std::vector<std::pair<uint32_t, uint8_t>> ygosim_summoned_;  // last summon group: (code, controller)
  bool ygosim_summon_done_ = true;
  uint8_t ygosim_solving_ = 0;  // chain link resolving now (MSG_CHAIN_SOLVING), 0 when none
  // WindBot's message callbacks (OnMove, OnChaining, OnNewPhase...): the messages since the last decisions,
  // as a ring of [sequence number, message, code, a..e]; each executor replays the ones it hasn't seen.
  static constexpr int kYgosimEvents = 256;
  int ygosim_events_[kYgosimEvents][8] = {};
  int ygosim_event_seq_ = 0;
  // The pending selection prompt: [hint, min, max, cancelable or finishable, sum value, sum mode] and its
  // candidates [code, controller, location, sequence, position, param, mandatory] with their option specs.
  uint32_t ygosim_hint_ = 0;  // last HINT_SELECTMSG
  int ygosim_select_[6] = {};
  std::vector<std::array<int, 7>> ygosim_cands_;
  std::vector<std::string> ygosim_cand_specs_;
  uint32_t ygosim_prompt_desc_ = 0;              // MSG_SELECT_YESNO / EFFECTYN description
  std::vector<uint32_t> ygosim_prompt_options_;  // MSG_SELECT_OPTION descriptions

  void ygosim_event(int a, int b = 0, int c = 0, int d = 0, int e = 0, int f = 0) {
    int *ev = ygosim_events_[ygosim_event_seq_ % kYgosimEvents];
    ev[0] = ++ygosim_event_seq_;
    ev[1] = msg_;
    ev[2] = a, ev[3] = b, ev[4] = c, ev[5] = d, ev[6] = e, ev[7] = f;
  }

  void ygosim_add_candidate(PlayerId player, uint32_t code, uint8_t ctl, uint8_t loc, uint32_t seq, uint32_t pos,
                            uint32_t param, bool mandatory) {
    ygosim_cands_.push_back({static_cast<int>(code), ctl, loc, static_cast<int>(seq), static_cast<int>(pos),
                             static_cast<int>(param), mandatory});
    ygosim_cand_specs_.push_back(ls_to_spec(loc, seq, (loc & LOCATION_OVERLAY) ? pos : 0, player != ctl));
  }

  void ygosim_new_prompt(int hint, int min, int max, int cancel, int sum = 0, int mode = 0) {
    ygosim_select_[0] = hint, ygosim_select_[1] = min, ygosim_select_[2] = max;
    ygosim_select_[3] = cancel, ygosim_select_[4] = sum, ygosim_select_[5] = mode;
    ygosim_cands_.clear();
    ygosim_cand_specs_.clear();
  }
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
        ygosim_solving_ = 0;
        ygosim_hint_ = 0;
        ygosim_resolved_.clear();
        ygosim_chain_.clear();
        ygosim_chain_targets_.clear();
        ygosim_summoned_.clear();
        ygosim_summon_done_ = true;
        break;
      case MSG_CHAINING: {
        uint32_t code = read_u32();
        auto li = read_loc_info();
        uint8_t tc = read_u8();
        read_u8();
        compat_read<uint8_t, uint32_t>();
        uint32_t desc = compat_read<uint32_t, uint64_t>();
        YgosimLink link{code, li.controler, li.location, li.sequence};
        link.desc = desc;
        link.player = tc;
        ygosim_chain_.push_back(link);
        ygosim_chain_targets_.clear();
        ygosim_event(code, li.controler, li.location, li.sequence, tc, static_cast<int>(desc));
        break;
      }
      case MSG_CHAIN_END:
        ygosim_chain_.clear();
        ygosim_chain_targets_.clear();
        ygosim_solving_ = 0;
        ygosim_event(0);
        break;
      case MSG_NEW_TURN:
        ygosim_resolved_.clear();
        ygosim_event(0, read_u8());
        break;
      case MSG_NEW_PHASE:
        ygosim_hint_ = 0;
        ygosim_event(0, read_u16());
        break;
      case MSG_CHAIN_SOLVING:
        ygosim_solving_ = read_u8();
        ygosim_event(0, ygosim_solving_);
        break;
      case MSG_CHAIN_NEGATED: case MSG_CHAIN_DISABLED: {
        uint8_t ct = read_u8();
        if (ct >= 1 && ct <= ygosim_chain_.size()) {
          ygosim_chain_[ct - 1].negated = true;
        }
        ygosim_event(0, ct);
        break;
      }
      case MSG_MOVE: {
        uint32_t code = read_u32();
        auto from = read_loc_info();
        auto to = read_loc_info();
        ygosim_event(code, from.controler, from.location, to.controler, to.location,
                     static_cast<int>(to.sequence | (to.position << 16)));
        break;
      }
      case MSG_POS_CHANGE: {
        uint32_t code = read_u32();
        uint8_t ctl = read_u8(), loc = read_u8(), seq = read_u8(), prev = read_u8(), cur = read_u8();
        ygosim_event(code, ctl, loc, seq, prev, cur);
        break;
      }
      case MSG_HINT: {
        uint8_t type = read_u8();
        read_u8();
        uint32_t value = compat_read<uint32_t, uint64_t>();
        if (type == HINT_SELECTMSG) {
          ygosim_hint_ = value;
        }
        break;
      }
      case MSG_SELECT_CARD: {
        auto player = read_u8();
        int cancelable = read_u8();
        int min = compat_read<uint8_t, uint32_t>();
        int max = compat_read<uint8_t, uint32_t>();
        ygosim_new_prompt(ygosim_hint_, min, max, cancelable);
        ygosim_hint_ = 0;
        uint32_t size = compat_read<uint8_t, uint32_t>();
        for (uint32_t k = 0; k < size; ++k) {
          uint32_t code = read_u32();
          auto li = read_loc_info();
          ygosim_add_candidate(player, code, li.controler, li.location, li.sequence, li.position, 0, false);
        }
        break;
      }
      case MSG_SELECT_UNSELECT_CARD: {  // the hint stays: Lua helpers reuse it for each pick
        auto player = read_u8();
        int finishable = read_u8();
        int cancelable = read_u8();
        int min = compat_read<uint8_t, uint32_t>();
        int max = compat_read<uint8_t, uint32_t>();
        ygosim_new_prompt(ygosim_hint_, min, max, finishable | (cancelable << 1));
        uint32_t size = compat_read<uint8_t, uint32_t>();
        for (uint32_t k = 0; k < size; ++k) {
          uint32_t code = read_u32();
          auto li = read_loc_info();
          ygosim_add_candidate(player, code, li.controler, li.location, li.sequence, li.position, 0, false);
        }
        break;
      }
      case MSG_SELECT_TRIBUTE: {
        auto player = read_u8();
        int cancelable = read_u8();
        int min = compat_read<uint8_t, uint32_t>();
        int max = compat_read<uint8_t, uint32_t>();
        ygosim_new_prompt(ygosim_hint_, min, max, cancelable);
        ygosim_hint_ = 0;
        uint32_t size = compat_read<uint8_t, uint32_t>();
        for (uint32_t k = 0; k < size; ++k) {
          uint32_t code = read_u32();
          uint8_t ctl = read_u8();
          uint8_t loc = read_u8();
          uint32_t seq = compat_read<uint8_t, uint32_t>();
          uint8_t param = read_u8();
          ygosim_add_candidate(player, code, ctl, loc, seq, 0, param, false);
        }
        break;
      }
      case MSG_SELECT_SUM: {
        uint8_t player, mode;
        if (compat_mode_) {
          mode = read_u8();
          player = read_u8();
        } else {
          player = read_u8();
          mode = read_u8();
        }
        int val = read_u32();
        int min = compat_read<uint8_t, uint32_t>();
        int max = compat_read<uint8_t, uint32_t>();
        ygosim_new_prompt(ygosim_hint_, min, max, 0, val, mode);
        ygosim_hint_ = 0;
        for (int group = 0; group < 2; ++group) {
          uint32_t size = compat_read<uint8_t, uint32_t>();
          for (uint32_t k = 0; k < size; ++k) {
            uint32_t code = read_u32();
            uint8_t ctl = read_u8();
            uint8_t loc = read_u8();
            uint32_t seq = 0;
            if (compat_mode_) {
              seq = read_u8();
            } else {
              seq = read_u32();
              read_u32();
            }
            uint32_t param = read_u32();
            ygosim_add_candidate(player, code, ctl, loc, seq, 0, param, group == 0);
          }
        }
        break;
      }
      case MSG_SELECT_PLACE: case MSG_SELECT_DISFIELD: {  // WindBot passes the hint as the card id
        read_u8();
        int count = read_u8();
        uint32_t flag = read_u32();
        ygosim_new_prompt(ygosim_hint_, static_cast<int>(~flag), count, 0);
        ygosim_hint_ = 0;
        break;
      }
      case MSG_SELECT_YESNO:
        read_u8();
        ygosim_prompt_desc_ = compat_read<uint32_t, uint64_t>();
        break;
      case MSG_SELECT_EFFECTYN:
        read_u8();
        read_u32();
        read_loc_info();
        ygosim_prompt_desc_ = compat_read<uint32_t, uint64_t>();
        break;
      case MSG_SELECT_OPTION: {
        read_u8();
        uint8_t size = read_u8();
        ygosim_prompt_options_.clear();
        for (int k = 0; k < size; ++k) {
          ygosim_prompt_options_.push_back(compat_read<uint32_t, uint64_t>());
        }
        break;
      }
      case MSG_CHAIN_SOLVED: {
        uint8_t ct = read_u8();
        ygosim_event(0, ct);
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
          ygosim_event(static_cast<int>(ygosim_chain_targets_.back()), li.controler, li.location, li.sequence);
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
        ygosim_event(code, li.controler, li.location, li.sequence, li.position);
        break;
      }
      case MSG_SUMMONED: case MSG_SPSUMMONED: case MSG_FLIPSUMMONED:
        ygosim_summon_done_ = true;
        ygosim_event(0);
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
      state["info:chain_"_](k, 4) = static_cast<int>(ygosim_chain_[k].desc);
      state["info:chain_"_](k, 5) = ygosim_chain_[k].negated;
      state["info:chain_"_](k, 6) = static_cast<int>(ygosim_chain_[k].sequence);
      state["info:chain_"_](k, 7) = ygosim_chain_[k].player;
    }
    state["info:solving_"_] = ygosim_solving_;
    if (ygosim_full_context_) {  // WindBot executors only
      for (int k = 0; k < kYgosimEvents; ++k) {
        for (int j = 0; j < 8; ++j) {
          state["info:events_"_](k, j) = ygosim_events_[k][j];
        }
      }
      bool select = msg_ == MSG_SELECT_CARD || msg_ == MSG_SELECT_UNSELECT_CARD || msg_ == MSG_SELECT_TRIBUTE ||
                    msg_ == MSG_SELECT_SUM || msg_ == MSG_SELECT_PLACE || msg_ == MSG_SELECT_DISFIELD;
      if (select) {
        for (int j = 0; j < 6; ++j) {
          state["info:select_"_][j] = ygosim_select_[j];
        }
        for (int k = 0; k < std::min<int>(ygosim_cands_.size(), 64); ++k) {
          for (int j = 0; j < 7; ++j) {
            state["info:select_cards_"_](k, j) = ygosim_cands_[k][j];
          }
        }
        // each option's candidates (index + 1), from its space-separated specs ("f" finish has none)
        int n = std::min<int>(options_.size(), max_options());
        for (int i = 0; i < n; ++i) {
          size_t start = 0;
          int j = 0;
          while (j < 5) {
            size_t end = options_[i].find(' ', start);
            std::string tok = options_[i].substr(start, end == std::string::npos ? std::string::npos : end - start);
            for (int k = 0; k < std::min<int>(ygosim_cand_specs_.size(), 64); ++k) {
              if (ygosim_cand_specs_[k] == tok) {
                state["info:option_combo_"_](i, j++) = k + 1;
                break;
              }
            }
            if (end == std::string::npos) {
              break;
            }
            start = end + 1;
          }
        }
      }
      state["info:prompt_desc_"_] = static_cast<int>(ygosim_prompt_desc_);
      for (int k = 0; k < std::min<int>(ygosim_prompt_options_.size(), 8); ++k) {
        state["info:prompt_options_"_][k] = static_cast<int>(ygosim_prompt_options_[k]);
      }
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

