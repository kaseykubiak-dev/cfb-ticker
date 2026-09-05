"""Rank, timeouts, last play, broadcast parsing; row text helpers; auto-follow policy."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cfb_ticker.autofollow import FINAL_GRACE_S, plan_selection, track_finals
from cfb_ticker.data.espn import parse_scoreboard
from cfb_ticker.data.models import GameState, TeamInfo
from cfb_ticker.ui.game_row import situation_text, team_label_html, tooltip_text

FIXTURE = Path(__file__).parent / "fixtures" / "scoreboard_live.json"
NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def games():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {g.game_id: g for g in parse_scoreboard(payload, now=NOW)}


# ---- parsing --------------------------------------------------------------


def test_rank_parsed_and_99_means_unranked(games):
    g = games["401856666"]
    assert g.home.rank == 20  # Tennessee
    assert g.away.rank is None  # Furman, curatedRank.current == 99
    assert games["401856658"].home.rank == 3  # Georgia


def test_timeouts_and_last_play_live(games):
    g = games["401856666"]
    assert (g.home_timeouts, g.away_timeouts) == (2, 1)  # parsed but not rendered; ESPN does not maintain them
    assert g.last_play.startswith("(00:48) No Huddle-Shotgun")


def test_timeouts_none_when_not_live(games):
    g = games["401856634"]  # final
    assert g.home_timeouts is None and g.away_timeouts is None


def test_broadcast(games):
    assert games["401856666"].broadcast == "SECN+"
    assert games["401856660"].broadcast == "ABC"


# ---- row text helpers ---------------------------------------------------------




def test_team_label_html(games):
    g = games["401856666"]
    assert team_label_html(g.away) == "FUR"
    html = team_label_html(g.home)
    assert html.startswith("<span") and html.endswith("#20</span> TENN")


def test_situation_text_by_status(games):
    assert situation_text(games["401856666"]) == "3rd & 6 at FUR 24"
    assert situation_text(games["401856660"]) == "ABC"  # pregame shows the network
    assert situation_text(games["401864499"]) == ""  # halftime hides stale down and distance
    assert situation_text(games["401856634"]) == ""  # final


def test_tooltip_text(games):
    tip = tooltip_text(games["401856666"])
    assert tip.startswith("Furman at Tennessee (SECN+)")
    assert "Last play: (00:48)" in tip
    assert "Last play" not in tooltip_text(games["401856634"])


# ---- auto-follow ---------------------------------------------------------------

_T = {tid: TeamInfo(tid, tid.upper(), tid, None) for tid in ("fav", "fav2", "x", "y", "z")}


def _g(gid, status, home, away, kickoff_min=0):
    return GameState(
        game_id=gid, home=_T[home], away=_T[away], home_score=0, away_score=0, status=status,
        period=1, clock="10:00", detail="", down_distance=None, possession=None, red_zone=False,
        start_time=NOW + timedelta(minutes=kickoff_min), fetched_at=NOW,
    )


def test_fills_empty_slots_with_live_favorites_earliest_first():
    games = {
        "late": _g("late", "in", "fav", "x", kickoff_min=30),
        "early": _g("early", "in", "y", "fav2", kickoff_min=0),
        "other": _g("other", "in", "x", "y"),
        "pre": _g("pre", "pre", "fav", "z", kickoff_min=120),
    }
    assert plan_selection([], games, {"fav", "fav2"}, {}, NOW) == ["early", "late"]
    assert plan_selection([], games, {"x"}, {}, NOW) == ["other", "late"]  # both involve x, kickoff order
    assert plan_selection([], games, set(), {}, NOW) == []


def test_never_displaces_live_or_upcoming_selection():
    games = {
        "mine": _g("mine", "pre", "x", "y"),
        "favlive": _g("favlive", "in", "fav", "z"),
        "fav2live": _g("fav2live", "in", "fav2", "z"),
    }
    assert plan_selection(["mine"], games, {"fav", "fav2"}, {}, NOW) == ["mine", "favlive"]
    assert plan_selection(["mine", "favlive"], games, {"fav", "fav2"}, {}, NOW) == ["mine", "favlive"]


def test_final_dropped_only_after_grace():
    games = {"done": _g("done", "final", "x", "y"), "favlive": _g("favlive", "in", "fav", "z")}
    since = {"done": NOW}
    assert plan_selection(["done"], games, {"fav"}, since, NOW) == ["done", "favlive"]
    later = NOW + timedelta(seconds=FINAL_GRACE_S)
    assert plan_selection(["done"], games, {"fav"}, since, later) == ["favlive"]
    # a final with no recorded time (app just started) is kept
    assert plan_selection(["done"], games, set(), {}, later) == ["done"]


def test_vanished_game_is_dropped():
    games = {"a": _g("a", "in", "x", "y")}
    assert plan_selection(["gone", "a"], games, set(), {}, NOW) == ["a"]


def test_track_finals():
    since: dict[str, datetime] = {}
    games = {"a": _g("a", "final", "x", "y"), "b": _g("b", "in", "x", "z")}
    track_finals(games, since, NOW)
    assert since == {"a": NOW}
    track_finals(games, since, NOW + timedelta(seconds=30))
    assert since["a"] == NOW  # first-seen time is kept
    track_finals({"b": games["b"]}, since, NOW)
    assert since == {}  # vanished final forgotten
