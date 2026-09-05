"""Settings round-trips through an INI backend; picker grouping against the fixture."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QSettings

from cfb_ticker.data.espn import parse_scoreboard
from cfb_ticker.settings import Settings
from cfb_ticker.ui.picker_dialog import game_label, group_games, involves_favorite, teams_on_board

FIXTURE = Path(__file__).parent / "fixtures" / "scoreboard_live.json"
TENN = "2633"
FUR = "231"


@pytest.fixture
def settings(tmp_path):
    backend = QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    return Settings(backend)


@pytest.fixture(scope="module")
def games():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return parse_scoreboard(payload, now=datetime(2026, 9, 5, 20, 0, tzinfo=UTC))


def test_settings_defaults(settings):
    assert settings.game_ids == []
    assert settings.favorite_team_ids == []
    assert settings.window_pos is None
    assert settings.placement == "floating"


def test_settings_game_ids_round_trip_and_cap(settings):
    settings.game_ids = ["1", "2", "3"]
    assert settings.game_ids == ["1", "2"]
    settings.game_ids = ["9"]
    assert settings.game_ids == ["9"]  # single value comes back as a list, not a str
    settings.game_ids = []
    assert settings.game_ids == []


def test_settings_favorites_toggle(settings):
    assert settings.toggle_favorite(TENN) is True
    assert settings.toggle_favorite(FUR) is True
    assert settings.favorite_team_ids == [FUR, TENN]
    assert settings.toggle_favorite(TENN) is False
    assert settings.favorite_team_ids == [FUR]


def test_settings_window_pos(settings):
    settings.window_pos = QPoint(40, 900)
    assert settings.window_pos == QPoint(40, 900)


def test_teams_on_board_unique_and_sorted(games):
    teams = teams_on_board(games)
    ids = [t.team_id for t in teams]
    assert len(ids) == len(set(ids))
    assert [t.name for t in teams] == sorted((t.name for t in teams), key=str.lower)
    assert TENN in ids


def test_group_games_sections(games):
    sections = group_games(games, {TENN})
    titles = [t for t, _ in sections]
    assert titles == ["Favorites", "Live", "Upcoming", "Final"]
    fav = sections[0][1]
    assert [g.game_id for g in fav] == ["401856666"]
    # favorite's game is not repeated in Live
    assert all(g.game_id != "401856666" for g in sections[1][1])
    # Live and Upcoming sort by kickoff ascending; Final newest first
    live, upcoming, final = sections[1][1], sections[2][1], sections[3][1]
    assert [g.start_time for g in live] == sorted(g.start_time for g in live)
    assert [g.start_time for g in upcoming] == sorted(g.start_time for g in upcoming)
    assert [g.start_time for g in final] == sorted((g.start_time for g in final), reverse=True)
    assert len(live) + len(upcoming) + len(final) + len(fav) == 99


def test_group_games_no_favorites_has_no_favorites_section(games):
    assert [t for t, _ in group_games(games, set())] == ["Live", "Upcoming", "Final"]


def test_involves_favorite(games):
    g = next(x for x in games if x.game_id == "401856666")
    assert involves_favorite(g, {FUR})
    assert not involves_favorite(g, {"1"})


def test_game_label(games):
    by_id = {g.game_id: g for g in games}
    assert game_label(by_id["401856666"]) == "FUR 0 @ TENN 21    0:41 2nd"
    assert game_label(by_id["401856634"]) == "ECU 10 @ ALA 48    FINAL"
    assert game_label(by_id["401856660"]).startswith("CLEM @ LSU    Sat ")
