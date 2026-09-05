"""The seam between the UI and whoever supplies scores."""

from __future__ import annotations

from typing import Protocol

from .models import GameState


class ScoreProvider(Protocol):
    name: str

    def fetch_scoreboard(self) -> list[GameState]:
        """Return every game on today's board. Raise on total failure; never return partial silently."""
        ...
