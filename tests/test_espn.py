"""Parser tests against the live week 1 fixture captured 2026-09-05 (17 games in progress)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfb_ticker.data.espn import parse_scoreboard
from cfb_ticker.data.models import GameState

FIXTURE = Path(__file__).parent / "fixtures" / "scoreboard_live.json"
NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def games() -> dict[str, GameState]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = parse_scoreboard(payload, now=NOW)
    return {g.game_id: g for g in parsed}


def test_every_event_parses(games):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(games) == len(payload["events"]) == 99


def test_status_distribution(games):
    from collections import Counter
    counts = Counter(g.status for g in games.values())
    assert counts == {"final": 43, "pre": 39, "in": 17}


def test_live_game_fields(games):
    g = games["401856666"]  # Furman at Tennessee, 0:41 left in the 2nd
    assert (g.away.abbreviation, g.home.abbreviation) == ("FUR", "TENN")
    assert (g.away_score, g.home_score) == (0, 21)
    assert g.status == "in"
    assert g.period == 2
    assert g.clock == "0:41"
    assert g.detail == "0:41 - 2nd"
    assert g.down_distance == "3rd & 6 at FUR 24"
    assert g.possession == "home"  # ESPN gives team id 2633, which is Tennessee
    assert g.red_zone is False
    assert g.home.color == "ff8200"
    assert g.home.name == "Tennessee"
    assert g.start_time == datetime(2026, 9, 5, 19, 30, tzinfo=UTC)
    assert g.fetched_at == NOW


def test_possession_maps_to_away(games):
    g = games["401856636"]  # Baylor at Auburn, Baylor (239) has the ball
    assert g.away.team_id == "239"
    assert g.possession == "away"


def test_possession_maps_to_home(games):
    g = games["401858433"]  # Boise State at Oregon, Oregon (2483) has the ball
    assert g.home.team_id == "2483"
    assert g.possession == "home"


def test_red_zone_flag(games):
    assert games["401856658"].red_zone is True  # 1st & Goal at TNST 3


def test_missing_situation_pieces_do_not_crash(games):
    g = games["401858434"]  # Marshall at Penn State: situation present, possession and downDistance absent
    assert g.status == "in"
    assert g.down_distance is None
    assert g.possession is None


def test_halftime_detail_survives(games):
    g = games["401864499"]
    assert g.clock == "0:00"
    assert g.detail == "Halftime"


def test_final_game(games):
    g = games["401856634"]  # ECU at Alabama
    assert g.status == "final"
    assert (g.away_score, g.home_score) == (10, 48)
    assert g.down_distance is None
    assert g.possession is None


def test_pregame_game(games):
    g = games["401856660"]  # Clemson at LSU, 7:30 PM EDT
    assert g.status == "pre"
    assert g.period == 0
    assert (g.away_score, g.home_score) == (0, 0)
    assert g.start_time == datetime(2026, 9, 5, 23, 30, tzinfo=UTC)


def test_malformed_event_is_skipped_not_fatal():
    payload = {"events": [{"id": "bad", "competitions": []}]}
    assert parse_scoreboard(payload, now=NOW) == []
