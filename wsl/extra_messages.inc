  // ygosim: messages from the current ygopro-core that the 2024 env never handled.
  // Informational messages are skipped (observations come from field queries, not message replay).
  // Decisions get a random legal response; they aren't exposed to the agent as options yet.
  template <typename T> T ygosim_rd() {
    T v;
    std::memcpy(&v, data_ + dp_, sizeof(T));
    dp_ += sizeof(T);
    return v;
  }

  template <typename T> void ygosim_respond(T v) {
    std::memcpy(resp_buf_, &v, sizeof(T));
    YGO_SetResponseb(pduel_, resp_buf_, sizeof(T));
  }

  // Port of ygopro-core's is_declarable (playerop.cpp): evaluates an announce-card opcode filter.
  static bool ygosim_is_declarable(const OCG_CardData &cd, const std::vector<uint64_t> &opcodes) {
    std::vector<int64_t> st;
    bool alias = false, token = false;
    auto pop = [&st]() { int64_t v = st.back(); st.pop_back(); return v; };
    for (uint64_t op : opcodes) {
      switch (op) {
#define YGOSIM_BIN(OPC, EXPR) case OPC: if (st.size() >= 2) { int64_t r = pop(), l = pop(); st.push_back(EXPR); } break;
#define YGOSIM_UN(OPC, EXPR) case OPC: if (!st.empty()) { int64_t v = pop(); st.push_back(EXPR); } break;
      YGOSIM_BIN(OPCODE_ADD, l + r)
      YGOSIM_BIN(OPCODE_SUB, l - r)
      YGOSIM_BIN(OPCODE_MUL, l * r)
      YGOSIM_BIN(OPCODE_DIV, r ? l / r : 0)
      YGOSIM_BIN(OPCODE_AND, l && r)
      YGOSIM_BIN(OPCODE_OR, l || r)
      YGOSIM_UN(OPCODE_NEG, -v)
      YGOSIM_UN(OPCODE_NOT, !v)
      YGOSIM_BIN(OPCODE_BAND, l & r)
      YGOSIM_BIN(OPCODE_BOR, l | r)
      YGOSIM_BIN(OPCODE_BXOR, l ^ r)
      YGOSIM_UN(OPCODE_BNOT, ~v)
      YGOSIM_BIN(OPCODE_LSHIFT, l << r)
      YGOSIM_BIN(OPCODE_RSHIFT, l >> r)
      YGOSIM_UN(OPCODE_ISCODE, cd.code == static_cast<uint32_t>(v))
      YGOSIM_UN(OPCODE_ISTYPE, cd.type & v)
      YGOSIM_UN(OPCODE_ISRACE, static_cast<int64_t>(cd.race & static_cast<uint64_t>(v)))
      YGOSIM_UN(OPCODE_ISATTRIBUTE, cd.attribute & v)
#undef YGOSIM_BIN
#undef YGOSIM_UN
      case OPCODE_GETCODE: st.push_back(cd.code); break;
      case OPCODE_GETTYPE: st.push_back(cd.type); break;
      case OPCODE_GETRACE: st.push_back(static_cast<int64_t>(cd.race)); break;
      case OPCODE_GETATTRIBUTE: st.push_back(cd.attribute); break;
      case OPCODE_ISSETCARD:
        if (!st.empty()) {
          int32_t set_code = static_cast<int32_t>(pop());
          uint16_t settype = set_code & 0xfff, setsubtype = set_code & 0xf000;
          bool res = false;
          for (const uint16_t *sc = cd.setcodes; sc && *sc; ++sc) {
            if ((*sc & 0xfff) == settype && (*sc & 0xf000 & setsubtype) == setsubtype) {
              res = true;
              break;
            }
          }
          st.push_back(res);
        }
        break;
      case OPCODE_ALLOW_ALIASES: alias = true; break;
      case OPCODE_ALLOW_TOKENS: token = true; break;
      default: st.push_back(static_cast<int64_t>(op)); break;
      }
    }
    if (st.size() != 1 || st.back() == 0) {
      return false;
    }
    return cd.code == CARD_MARINE_DOLPHIN || cd.code == CARD_TWINKLE_MOSS ||
           ((alias || !cd.alias) &&
            (token || ((cd.type & (TYPE_MONSTER + TYPE_TOKEN)) != (TYPE_MONSTER + TYPE_TOKEN))));
  }

  bool ygosim_handle_extra() {
    switch (msg_) {
    case MSG_WAITING: case MSG_START: case MSG_UPDATE_DATA: case MSG_UPDATE_CARD:
    case MSG_REQUEST_DECK: case MSG_REFRESH_DECK: case MSG_SWAP_GRAVE_DECK:
    case MSG_REVERSE_DECK: case MSG_DECK_TOP: case MSG_CONFIRM_EXTRATOP:
    case MSG_FIELD_DISABLED: case MSG_UNEQUIP: case MSG_CARD_TARGET: case MSG_CANCEL_TARGET:
    case MSG_BE_CHAIN_TARGET: case MSG_CREATE_RELATION: case MSG_RELEASE_RELATION:
    case MSG_TOSS_COIN: case MSG_TOSS_DICE: case MSG_HAND_RES: case MSG_TAG_SWAP:
    case MSG_RELOAD_FIELD: case MSG_AI_NAME: case MSG_SHOW_HINT: case MSG_MATCH_KILL:
    case MSG_CUSTOM_MSG: case MSG_REMOVE_CARDS:
      dp_ = dl_;
      return true;

    case MSG_SORT_CHAIN:  // keep the default order of simultaneous triggers
      dp_ = dl_;
      YGO_SetResponsei(pduel_, -1);
      return true;

    case MSG_ROCK_PAPER_SCISSORS:
      dp_ = dl_;
      YGO_SetResponsei(pduel_, std::uniform_int_distribution<int>(1, 3)(gen_));
      return true;

    case MSG_ANNOUNCE_RACE: {
      ygosim_rd<uint8_t>();  // player
      int count = ygosim_rd<uint8_t>();
      uint64_t available = ygosim_rd<uint64_t>();
      dp_ = dl_;
      std::vector<uint64_t> bits;
      for (int i = 0; i < 64; ++i) {
        if (available & (uint64_t(1) << i)) {
          bits.push_back(uint64_t(1) << i);
        }
      }
      std::shuffle(bits.begin(), bits.end(), gen_);
      uint64_t pick = 0;
      for (int i = 0; i < count && i < static_cast<int>(bits.size()); ++i) {
        pick |= bits[i];
      }
      ygosim_respond<uint64_t>(pick);
      return true;
    }

    case MSG_SELECT_COUNTER: {
      ygosim_rd<uint8_t>();  // player
      ygosim_rd<uint16_t>();  // counter type
      int need = ygosim_rd<uint16_t>();
      uint32_t size = ygosim_rd<uint32_t>();
      std::vector<int16_t> have(size), take(size, 0);
      for (uint32_t i = 0; i < size; ++i) {
        ygosim_rd<uint32_t>();  // code
        dp_ += 3;               // controller, location, sequence
        have[i] = ygosim_rd<uint16_t>();
      }
      dp_ = dl_;
      // Remove counters one at a time from random cards that still have some.
      while (need > 0) {
        std::vector<uint32_t> idx;
        for (uint32_t i = 0; i < size; ++i) {
          if (take[i] < have[i]) {
            idx.push_back(i);
          }
        }
        if (idx.empty()) {
          break;
        }
        ++take[idx[std::uniform_int_distribution<size_t>(0, idx.size() - 1)(gen_)]];
        --need;
      }
      std::memcpy(resp_buf_, take.data(), size * sizeof(int16_t));
      YGO_SetResponseb(pduel_, resp_buf_, size * sizeof(int16_t));
      return true;
    }

    case MSG_ANNOUNCE_CARD: {
      PlayerId player = ygosim_rd<uint8_t>();
      int n = ygosim_rd<uint8_t>();
      std::vector<uint64_t> opcodes(n);
      for (int i = 0; i < n; ++i) {
        opcodes[i] = ygosim_rd<uint64_t>();
      }
      dp_ = dl_;
      // Prefer naming a card in the opponent's deck; fall back to any declarable card.
      std::vector<uint32_t> cands;
      const std::string &opp = deck_name_[1 - player];
      for (const auto *deck : {&main_decks_[opp], &extra_decks_[opp]}) {
        for (CardCode code : *deck) {
          auto it = cards_data_.find(code);
          if (it != cards_data_.end() && ygosim_is_declarable(it->second, opcodes)) {
            cands.push_back(code);
          }
        }
      }
      if (cands.empty()) {
        for (const auto &[code, cd] : cards_data_) {
          if (ygosim_is_declarable(cd, opcodes)) {
            cands.push_back(code);
          }
        }
      }
      if (cands.empty()) {
        throw std::runtime_error("[ygosim] MSG_ANNOUNCE_CARD: no declarable card");
      }
      int32_t code = cands[std::uniform_int_distribution<size_t>(0, cands.size() - 1)(gen_)];
      YGO_SetResponsei(pduel_, code);
      return true;
    }

    default:
      return false;
    }
  }

