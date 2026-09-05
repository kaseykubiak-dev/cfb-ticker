"""CollegeFootballData.com fallback provider. Stub: documented, not wired.

CFBD needs a free API key (https://collegefootballdata.com/key), sent as
``Authorization: Bearer <key>``. Its ``/scoreboard`` endpoint returns score, period,
clock and possession for live games, but its situation data lags ESPN's and it has
no down-and-distance text, so it stays the fallback. The key would live in
QSettings under ``providers/cfbd_key`` and never in the repo.
"""

from __future__ import annotations

from .models import GameState


class CfbdProvider:
    name = "cfbd"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch_scoreboard(self) -> list[GameState]:
        raise NotImplementedError("CFBD provider is a Phase 2 stub; ESPN is the only live provider")
