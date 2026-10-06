  // ygosim: parser for the current ygopro-core query format, replacing the 2024 fixed-offset reads.
  // Each field is {u16 size, u32 flag, value}, `size` covering flag + value; a card ends with
  // QUERY_END; an empty zone slot in a location query is a bare u16 0.
  uint32_t q_u32_at(int32_t p) const {
    uint32_t v;
    std::memcpy(&v, query_buf_ + p, sizeof(v));
    return v;
  }

  uint16_t q_u16_at(int32_t p) const {
    uint16_t v;
    std::memcpy(&v, query_buf_ + p, sizeof(v));
    return v;
  }

  // Parse one card record starting at `p`; advances `p` past QUERY_END.
  // Overlay materials (if queried) are appended to `overlay` before the host card's return.
  Card parse_card_record(int32_t &p, int32_t bl, PlayerId player, uint8_t loc, uint32_t seq,
                         std::vector<Card> *overlay) {
    Card c;
    bool have_code = false;
    uint32_t position = 0, level = 0, rank = 0, link = 0, link_marker = 0;
    uint32_t lscale = 0, rscale = 0, counter = 0;
    int32_t attack = 0, defense = 0;
    std::vector<CardCode> materials;
    while (p + 6 <= bl) {
      uint16_t size = q_u16_at(p);
      uint32_t flag = q_u32_at(p + 2);
      int32_t v = p + 6;
      p += 2 + size;
      if (flag == QUERY_END) {
        break;
      }
      switch (flag) {
      case QUERY_CODE: c = c_get_card(q_u32_at(v)); have_code = true; break;
      case QUERY_POSITION: position = q_u32_at(v); break;
      case QUERY_LEVEL: level = q_u32_at(v); break;
      case QUERY_RANK: rank = q_u32_at(v); break;
      case QUERY_ATTACK: attack = static_cast<int32_t>(q_u32_at(v)); break;
      case QUERY_DEFENSE: defense = static_cast<int32_t>(q_u32_at(v)); break;
      case QUERY_LSCALE: lscale = q_u32_at(v); break;
      case QUERY_RSCALE: rscale = q_u32_at(v); break;
      case QUERY_LINK: link = q_u32_at(v); link_marker = q_u32_at(v + 4); break;
      case QUERY_OVERLAY_CARD:
        for (uint32_t i = 0, n = q_u32_at(v); i < n; ++i) {
          materials.push_back(q_u32_at(v + 4 + 4 * i));
        }
        break;
      case QUERY_COUNTERS:
        if (q_u32_at(v) > 0) {
          counter = q_u32_at(v + 4);
        }
        break;
      default: break;
      }
    }
    if (!have_code) {
      throw std::runtime_error(fmt::format(
          "[parse_card_record] no QUERY_CODE: player {}, loc {}, seq {}", player, loc, seq));
    }
    c.controler_ = player;
    c.location_ = loc;
    c.sequence_ = seq;
    c.position_ = position;
    // TODO (from ygo-agent): negative levels
    if ((level & 0xff) > 0) {
      c.level_ = level & 0xff;
    }
    if ((rank & 0xff) > 0) {
      c.level_ = rank & 0xff;
    }
    if ((link & 0xff) > 0) {
      c.level_ = link & 0xff;
    }
    c.attack_ = attack;
    c.defense_ = link_marker > 0 ? static_cast<int32_t>(link_marker) : defense;
    c.lscale_ = lscale;
    c.rscale_ = rscale;
    c.counter_ = counter;
    if (overlay) {
      for (size_t i = 0; i < materials.size(); ++i) {
        Card m = c_get_card(materials[i]);
        m.controler_ = player;
        m.location_ = loc | LOCATION_OVERLAY;
        m.sequence_ = seq;
        m.position_ = static_cast<uint32_t>(i);
        overlay->push_back(m);
      }
    }
    return c;
  }

  Card get_card(PlayerId player, uint8_t loc, uint8_t seq) {
    int32_t flags = QUERY_CODE | QUERY_POSITION | QUERY_LEVEL | QUERY_RANK |
                    QUERY_ATTACK | QUERY_DEFENSE | QUERY_LSCALE | QUERY_RSCALE |
                    QUERY_LINK;
    int32_t bl = YGO_QueryCard(pduel_, player, loc, seq, flags, query_buf_);
    if (bl <= 0) {
      std::string err = fmt::format("Player: {}, loc: {}, seq: {}, length: {}", player, loc, seq, bl);
      throw std::runtime_error("[get_card] Invalid card " + err);
    }
    int32_t p = 0;
    return parse_card_record(p, bl, player, loc, seq, nullptr);
  }

  std::vector<Card> get_cards_in_location(PlayerId player, uint8_t loc) {
    int32_t flags = QUERY_CODE | QUERY_POSITION | QUERY_LEVEL | QUERY_RANK |
                    QUERY_ATTACK | QUERY_DEFENSE | QUERY_OVERLAY_CARD |
                    QUERY_COUNTERS | QUERY_LSCALE | QUERY_RSCALE | QUERY_LINK;
    int32_t bl = OCG_QueryFieldCard(pduel_, player, loc, flags, query_buf_, 0);
    std::vector<Card> cards;
    int32_t p = 4;  // u32 total length
    uint32_t seq = 0;
    while (p + 2 <= bl) {
      if (q_u16_at(p) == 0) {  // empty zone slot
        p += 2;
        ++seq;
        continue;
      }
      // Overlay materials go before their host card, as in ygo-agent.
      Card c = parse_card_record(p, bl, player, loc, seq, &cards);
      cards.push_back(c);
      ++seq;
    }
    return cards;
  }

