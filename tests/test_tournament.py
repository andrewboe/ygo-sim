import numpy as np
import pytest

from ygosim.tournament import EventFormat, check_matrix, run_event, simulate


def test_default_format_matches_ycs_guayaquil():
    # 263 players -> 9 Swiss rounds, top 32 (YCS Guayaquil 2026 ran a top 32).
    fmt = EventFormat(263).resolved()
    assert (fmt.rounds, fmt.top_cut) == (9, 32)


def test_even_field_converts_evenly():
    names = ["A", "B", "C"]
    matrix = np.full((3, 3), 0.5)
    stats = simulate(names, [0.5, 0.3, 0.2], matrix, EventFormat(128), events=300, seed=1)
    for row in stats.table():
        assert row["conversion"] == pytest.approx(1.0, abs=0.15)


def test_favorable_spread_converts_better():
    names = ["Strong", "Field"]
    matrix = np.array([[0.5, 0.6], [0.4, 0.5]])
    rows = {r["deck"]: r for r in simulate(names, [0.2, 0.8], matrix, EventFormat(128), 300, 2).table()}
    assert rows["Strong"]["conversion"] > 1.2 > 1.0 > rows["Field"]["conversion"]


def test_swiss_records_are_consistent():
    rng = np.random.default_rng(3)
    matrix = np.full((1, 1), 0.5)
    fmt = EventFormat(64).resolved()
    standings, winner = run_event([0] * 64, matrix, fmt, rng)
    assert sorted(standings) == list(range(64))
    assert winner in standings[:fmt.top_cut]


def test_odd_field_gets_byes():
    rng = np.random.default_rng(4)
    standings, _ = run_event([0] * 33, np.full((1, 1), 0.5), EventFormat(33).resolved(), rng)
    assert len(standings) == 33


def test_matrix_must_be_complementary():
    check_matrix(np.array([[0.5, 0.6], [0.4, 0.5]]))
    with pytest.raises(ValueError):
        check_matrix(np.array([[0.5, 0.6], [0.6, 0.5]]))
