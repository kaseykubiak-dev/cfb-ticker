"""The whole data model: one GameState per game, provider-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Status = Literal["pre", "in", "final"]
Side = Literal["home", "away"]


@dataclass(frozen=True, slots=True)
class TeamInfo:
    team_id: str
    abbreviation: str  # "TENN"
    name: str  # "Tennessee"
    color: str | None  # hex without '#', e.g. "ff8200"
    rank: int | None = None  # AP poll rank 1-25; None when unranked


@dataclass(frozen=True, slots=True)
class GameState:
    game_id: str
    home: TeamInfo
    away: TeamInfo
    home_score: int
    away_score: int
    status: Status
    period: int  # 0 pregame, 1-4, 5+ = OT
    clock: str  # "12:34"
    detail: str  # ESPN's shortDetail: "0:41 - 2nd", "Halftime", "Final", "9/5 - 7:30 PM EDT"
    down_distance: str | None  # "3rd & 6 at FUR 24"; None between plays or when not in progress
    possession: Side | None
    red_zone: bool
    start_time: datetime
    fetched_at: datetime
    home_timeouts: int | None = None  # only meaningful while live
    away_timeouts: int | None = None
    last_play: str | None = None  # play-by-play text of the most recent play
    broadcast: str | None = None  # "SECN+", "ABC"

    @property
    def is_live(self) -> bool:
        return self.status == "in"
