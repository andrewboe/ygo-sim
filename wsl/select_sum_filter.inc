      {
        // ygosim: keep only selections the core accepts (port of playerop.cpp SelectSum step 1).
        // Mode 0 (max > 0): exact sum, selected count in [min, max]. Mode 1: sum reaches the target
        // with no surplus card. ygo-agent treated both as exact sums with no count limit.
        auto check1 = [](auto &&self, const std::vector<int32_t> &op, size_t i, int32_t acc) -> bool {
          if (acc == 0 || i == op.size()) {
            return false;
          }
          int32_t o1 = op[i] & 0xffff, o2 = op[i] >> 16;
          if (i == op.size() - 1) {
            return acc == o1 || acc == o2;
          }
          return (acc > o1 && self(self, op, i + 1, acc - o1)) ||
                 (o2 > 0 && acc > o2 && self(self, op, i + 1, acc - o2));
        };
        int32_t target = static_cast<int32_t>(val & 0xffff);
        auto valid = [&](const std::vector<int> &c) {
          std::vector<int32_t> op(must_select_params.begin(), must_select_params.end());
          for (int i : c) {
            op.push_back(select_params[i]);
          }
          if (mode == 0) {
            int n = static_cast<int>(c.size());
            return n >= min && n <= max && check1(check1, op, 0, target);
          }
          int32_t sum = 0, mx = 0, mn = 0x7fffffff;
          for (int32_t p : op) {
            int32_t o1 = p & 0xffff, o2 = p >> 16;
            int32_t ms = (o2 && o2 < o1) ? o2 : o1;
            sum += ms;
            mx += (o2 > o1) ? o2 : o1;
            mn = std::min(mn, ms);
          }
          return !c.empty() && mx >= target && sum - mn < target;
        };
        // ygo-agent built every subset of the candidates (combinations_with_weight2) before
        // filtering: 2^n vectors, a bad_alloc once a ritual offers ~28 tributes. Walk the subsets
        // in the same order (size, then lexicographic) with pruning and keep only the first
        // max_options valid ones, the most WriteState ever exposes.
        const size_t cap = static_cast<size_t>(std::max(max_options(), 2));
        int32_t lmax = 0, must_ms = 0, must_mx = 0, must_mn = 0x7fffffff;
        for (int p : select_params) {
          lmax = std::max<int32_t>(lmax, std::max<int32_t>(p & 0xffff, p >> 16));
        }
        for (int p : must_select_params) {
          int32_t o1 = p & 0xffff, o2 = p >> 16;
          int32_t ms = (o2 && o2 < o1) ? o2 : o1;
          must_ms += ms;
          must_mx += (o2 > o1) ? o2 : o1;
          must_mn = std::min(must_mn, ms);
        }
        int64_t budget = 1 << 22;  // subset nodes visited; bounds the walk if valid ones are rare
        std::vector<int> cur;
        // Extending a selection never lowers its minimum sum (mode 0: must stay <= target) or
        // its sum without the smallest card (mode 1: must stay < target), so prune on those.
        auto walk = [&](auto &&self, int start, int k, int32_t ms_sum, int32_t mx_sum,
                        int32_t mn) -> void {
          if (static_cast<int>(cur.size()) == k) {
            if (valid(cur) && sum_to2(card_levels, cur, expected, true)) {
              combs.push_back(cur);
            }
            return;
          }
          int left = k - static_cast<int>(cur.size());
          for (int i = start; i <= select_size - left; ++i) {
            if (combs.size() >= cap || --budget < 0) {
              return;
            }
            int32_t o1 = select_params[i] & 0xffff, o2 = select_params[i] >> 16;
            int32_t ms = (o2 && o2 < o1) ? o2 : o1;
            int32_t s = ms_sum + ms, x = mx_sum + ((o2 > o1) ? o2 : o1), m = std::min(mn, ms);
            if (mode == 0 ? s > target : s - m >= target) {
              continue;
            }
            if (x + static_cast<int64_t>(left - 1) * lmax < target) {
              continue;
            }
            cur.push_back(i);
            self(self, i + 1, k, s, x, m);
            cur.pop_back();
          }
        };
        int kmax = mode == 0 ? std::min<int>(max, select_size) : select_size;
        for (int k = 1; k <= kmax && combs.size() < cap && budget > 0; ++k) {
          walk(walk, 0, k, must_ms, must_mx, must_mn);
        }
        if (combs.empty() && select_size <= 16) {  // brute force small selections
          for (uint32_t mask = 1; mask < (1u << select_size); ++mask) {
            std::vector<int> c;
            for (int i = 0; i < select_size; ++i) {
              if (mask & (1u << i)) {
                c.push_back(i);
              }
            }
            if (valid(c)) {
              combs.push_back(c);
            }
          }
        }
        if (combs.empty()) {
          throw std::runtime_error(fmt::format(
              "[ygosim] MSG_SELECT_SUM: no valid selection (mode {}, target {}, {} cards)", mode,
              target, select_size));
        }
      }
