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
        combs.erase(std::remove_if(combs.begin(), combs.end(),
                                   [&](const std::vector<int> &c) { return !valid(c); }),
                    combs.end());
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
