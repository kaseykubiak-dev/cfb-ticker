"""Interval and backoff policy, tested without a running QApplication."""

from datetime import UTC, datetime

from cfb_ticker.data.models import GameState, TeamInfo
from cfb_ticker.poller import (
    BACKOFF_CAP_MS,
    IDLE_MS,
    LIVE_MS,
    PREGAME_MS,
    next_backoff_ms,
    next_interval_ms,
)
from cfb_ticker.ui.game_row import clock_text, period_label

_T = TeamInfo("1", "AAA", "Aaa", None)
_NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)


def _game(status: str, period: int = 1, clock: str = "12:00", detail: str = "") -> GameState:
    return GameState(
        game_id="x", home=_T, away=_T, home_score=0, away_score=0, status=status,
        period=period, clock=clock, detail=detail, down_distance=None, possession=None,
        red_zone=False, start_time=_NOW, fetched_at=_NOW,
    )


def test_interval_nothing_selected():
    assert next_interval_ms([]) == IDLE_MS
    assert next_interval_ms([None, None]) == IDLE_MS


def test_interval_live_wins():
    assert next_interval_ms([_game("final"), _game("in")]) == LIVE_MS
    assert next_interval_ms([_game("pre"), _game("in")]) == LIVE_MS


def test_interval_pregame_then_idle():
    assert next_interval_ms([_game("pre"), _game("final")]) == PREGAME_MS
    assert next_interval_ms([_game("final")]) == IDLE_MS
    assert next_interval_ms([None, _game("final")]) == IDLE_MS


def test_backoff_doubles_and_caps():
    seq = []
    prev = None
    for _ in range(5):
        prev = next_backoff_ms(prev)
        seq.append(prev)
    assert seq == [10_000, 20_000, 40_000, BACKOFF_CAP_MS, BACKOFF_CAP_MS]


def test_period_labels():
    assert [period_label(p) for p in (0, 1, 2, 3, 4, 5, 6)] == ["", "1st", "2nd", "3rd", "4th", "OT", "2OT"]


def test_clock_text_variants():
    assert clock_text(_game("in", 2, "0:41", "0:41 - 2nd")) == "0:41 2nd"
    assert clock_text(_game("in", 2, "0:00", "Halftime")) == "Halftime"
    assert clock_text(_game("in", 0, "0:00", "Delayed")) == "Delayed"
    assert clock_text(_game("final", 4, "0:00", "Final")) == "FINAL"
    assert clock_text(_game("final", 6, "0:00", "Final/2OT")) == "FINAL/2OT"
    assert clock_text(_game("pre", 0, "0:00", "9/5 - 7:30 PM EDT")).startswith("Sat ")
