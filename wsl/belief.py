"""Opponent belief for hidden-information sampling (AUDIT.md item 2; deck prediction as in Hearthstone AI).

Search must not know cards its player can't see. Before each rollout, the deciding player's hidden
information is re-dealt from a belief, and the env swaps those card identities in place
(wsl/patch_core.py YGOSIM_SetCardCode via the re-deal action):

  - Which deck is the opponent on? Game 1: the field's TCG archetypes, weighted by field share, times
    the likelihood of every public card the opponent has shown (field, graveyard, face-up banished):
    a card the archetype's list doesn't run counts EPS. Games 2-3: the opponent's known list.
  - Given the archetype: its main deck minus the opponent's public cards is shuffled into their
    face-down field cards (spells/traps into S/T zones, monsters into monster zones), hand and deck;
    its Extra Deck minus public Extra Deck cards fills theirs.
  - The decider's own deck order is permuted too (its own future draws are unknown as well).

Known gaps: cards the opponent searched or revealed are public in real play but resampled here; set
cards and the hand are sampled independently of what the opponent did with them.
"""
import json
import os
import re
import sqlite3
from collections import Counter

import numpy as np

RUN = os.path.expanduser("~/ygo/run")
FIELD = "/mnt/c/Users/andre/Desktop/ygo-sim/data/field/field.json"
EPS = 0.02          # likelihood of a shown card the archetype's list doesn't run (tech, side, variant)
REDEAL = 3_000_000  # env action: apply the staged identities, same decision

LOC_DECK, LOC_HAND, LOC_EXTRA, FACEDOWN, DECK_PERMUTE = 0x01, 0x02, 0x40, 0x100, 0x200
TYPE_MONSTER, TYPE_SPELL, TYPE_TRAP = 0x1, 0x2, 0x4
TYPE_EXTRA = 0x40 | 0x2000 | 0x800000 | 0x4000000  # fusion, synchro, xyz, link


def read_ydk(path: str) -> tuple[Counter, Counter]:
    main, extra, zone = Counter(), Counter(), None
    for line in open(path):
        line = line.strip()
        if line in ("#main", "#extra", "!side"):
            zone = line
        elif line.isdigit() and zone in ("#main", "#extra"):
            (main if zone == "#main" else extra)[int(line)] += 1
    return main, extra


class Belief:
    def __init__(self, known: dict[int, str] | None = None):
        """known: player -> runtime deck name whose list that player's opponent knows (games 2-3)."""
        field = json.load(open(FIELD))
        slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        self.archetypes = []  # (name, weight, main Counter, extra Counter)
        for e in field["entries"]:
            path = f"{RUN}/decks/{slug(e['deck'])}__tcg.ydk"
            if e["source"] == "tcg" and os.path.exists(path):
                self.archetypes.append((e["deck"], e["weight"], *read_ydk(path)))
        self.prior = np.array([a[1] for a in self.archetypes])
        self.prior /= self.prior.sum()
        self.known = {p: read_ydk(f"{RUN}/decks/{d}.ydk") for p, d in (known or {}).items()}
        db = sqlite3.connect(f"{RUN}/cards.cdb")
        self.types = dict(db.execute("select id, type from datas"))
        self.alias = {i: a for i, a in db.execute("select id, alias from datas") if a}

    def base(self, code: int) -> int:
        return self.alias.get(code, code)

    def posterior(self, shown: list[int]) -> np.ndarray:
        like = np.ones(len(self.archetypes))
        for i, (_, _, main, extra) in enumerate(self.archetypes):
            seen = Counter(self.base(c) for c in shown)
            for c, n in seen.items():
                runs = main.get(c, 0) + extra.get(c, 0)
                like[i] *= EPS ** max(0, n - runs) if runs else EPS ** n
        post = self.prior * like
        return post / post.sum()

    def sample(self, rng, decider: int, info, i: int) -> list[int]:
        """Flat staged entries (player, location, index, code) re-dealing what `decider` can't see."""
        opp = 1 - decider
        field = [int(c) for c in info["field_codes_"][i][opp] if c]
        board = [int(x) for x in info["board_"][i][opp]]  # mzone, szone, hand, grave, removed, deck, extra
        public = [int(c) for c in info["public_codes_"][i][opp] if c]
        shown = [c for c in field if c > 0] + public
        if opp in self.known:
            main, extra = self.known[opp]
        else:
            a = rng.choice(len(self.archetypes), p=self.posterior(shown))
            main, extra = self.archetypes[a][2], self.archetypes[a][3]
        pool = main.copy()
        for c in shown:
            if pool.get(self.base(c), 0) > 0:
                pool[self.base(c)] -= 1
        pool = [c for c, n in pool.items() for _ in range(n)]
        rng.shuffle(pool)
        everything = [c for c, n in main.items() for _ in range(n)]

        def take(pred):
            for j, c in enumerate(pool):
                if pred(c):
                    return pool.pop(j)
            cands = [c for c in everything if pred(c)] or everything
            return int(rng.choice(cands))

        entries = []
        # Face-down cards: field_codes_ lists monster zones first (board[0] cards), then S/T zones;
        # the env enumerates face-down S/T cards first, then face-down monsters.
        n_m = min(board[0], len(field))
        down_st = [c for c in field[n_m:] if c < 0]
        down_m = [c for c in field[:n_m] if c < 0]
        k = 0
        for _ in down_st:
            entries += [opp, FACEDOWN, k, take(lambda c: self.types.get(c, 0) & (TYPE_SPELL | TYPE_TRAP))]
            k += 1
        for _ in down_m:
            entries += [opp, FACEDOWN, k, take(lambda c: self.types.get(c, 0) & TYPE_MONSTER)]
            k += 1
        for j in range(board[2]):
            entries += [opp, LOC_HAND, j, take(lambda c: True)]
        for j in range(board[5]):
            entries += [opp, LOC_DECK, j, take(lambda c: True)]
        xpool = extra.copy()
        for c in shown:
            if xpool.get(self.base(c), 0) > 0:
                xpool[self.base(c)] -= 1
        xs = [c for c, n in xpool.items() for _ in range(n)]
        rng.shuffle(xs)
        xall = [c for c, n in extra.items() for _ in range(n)]
        for j in range(board[6]):
            code = xs.pop() if xs else (int(rng.choice(xall)) if xall else 0)
            if code:
                entries += [opp, LOC_EXTRA, j, code]
        entries += [decider, DECK_PERMUTE, int(rng.integers(1, 2**31 - 1)), 0]
        return [int(x) for x in entries]
