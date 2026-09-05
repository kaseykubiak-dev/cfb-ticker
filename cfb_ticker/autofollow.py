"""Auto-follow favorites: pure selection policy, applied by __main__ after every fetch.

Rules, in order:
  1. A selected game that has been final for FINAL_GRACE_S is dropped.
  2. A selected game that vanished from the board (yesterday's, or an id typo) is dropped.
  3. Empty slots fill with favorites' games that are live and not already selected,
     earliest kickoff first. Nothing ever displaces a game that is still live or upcoming.
The function is pure so it can be tested with hand-built states and clocks.
"""

from __future__ import annotations

from datetime import datetime

from .data.models import GameState
from .settings import MAX_GAMES

FINAL_GRACE_S = 600


def plan_selection(
    current: list[str],
    games: dict[str, GameState],
    favorite_team_ids: set[str],
    final_since: dict[str, datetime],
    now: datetime,
    max_games: int = MAX_GAMES,
) -> list[str]:
    keep: list[str] = []
    for gid in current:
        g = games.get(gid)
        if g is None:
            continue
        if g.status == "final":
            since = final_since.get(gid)
            if since is not None and (now - since).total_seconds() >= FINAL_GRACE_S:
                continue
        keep.append(gid)

    if len(keep) < max_games and favorite_team_ids:
        candidates = [
            g for g in games.values()
            if g.status == "in"
            and g.game_id not in keep
            and (g.home.team_id in favorite_team_ids or g.away.team_id in favorite_team_ids)
        ]
        candidates.sort(key=lambda g: g.start_time)
        for g in candidates:
            if len(keep) >= max_games:
                break
            keep.append(g.game_id)
    return keep


def track_finals(games: dict[str, GameState], final_since: dict[str, datetime], now: datetime) -> None:
    """Record when each game was first seen final; forget ones that are no longer final or gone."""
    for gid, g in games.items():
        if g.status == "final":
            final_since.setdefault(gid, now)
        else:
            final_since.pop(gid, None)
    for gid in list(final_since):
        if gid not in games:
            del final_since[gid]
