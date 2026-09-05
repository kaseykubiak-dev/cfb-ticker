"""Polling loop: a QTimer that runs each fetch on a worker thread and adapts its interval.

Interval policy (design doc, Phase 1):
    10 s when any selected game is in progress
    60 s when every selected game is pregame
    5 min when everything selected is final, or nothing is selected
On failure: keep the last state, back off 10 -> 20 -> 40 s, capped at 60 s.
The window decides when to show "stale"; the poller only reports when data last arrived.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .data.models import GameState
from .data.provider import ScoreProvider

log = logging.getLogger(__name__)

LIVE_MS = 10_000
PREGAME_MS = 60_000
IDLE_MS = 300_000
BACKOFF_START_MS = 10_000
BACKOFF_CAP_MS = 60_000


def next_interval_ms(selected: Iterable[GameState | None]) -> int:
    """Pure policy function so it can be unit-tested without Qt running."""
    states = [g for g in selected if g is not None]
    if not states:
        return IDLE_MS
    if any(g.status == "in" for g in states):
        return LIVE_MS
    if any(g.status == "pre" for g in states):
        return PREGAME_MS
    return IDLE_MS


def next_backoff_ms(previous_ms: int | None) -> int:
    if previous_ms is None:
        return BACKOFF_START_MS
    return min(previous_ms * 2, BACKOFF_CAP_MS)


class _FetchWorker(QThread):
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, provider: ScoreProvider, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._provider = provider

    def run(self) -> None:  # runs on the worker thread
        try:
            self.finished_ok.emit(self._provider.fetch_scoreboard())
        except Exception as exc:  # noqa: BLE001 - anything here must become a UI state, not a crash
            self.failed.emit(str(exc))


class ScorePoller(QObject):
    """Owns the timer and the in-flight worker. Emits parsed games or an error string."""

    games_updated = Signal(list)  # list[GameState], the full scoreboard
    fetch_failed = Signal(str)

    def __init__(self, provider: ScoreProvider, game_ids: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.game_ids = list(game_ids)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.poll_now)
        # One worker for the life of the poller; QThread.start() may be called again once
        # run() has returned. Creating a fresh one per poll and deleteLater-ing it left a
        # dead wrapper behind, and the next isRunning() call raised (found on first run).
        self._worker = _FetchWorker(provider, self)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_failed)
        self._backoff_ms: int | None = None
        self.latest: dict[str, GameState] = {}
        self.last_ok: datetime | None = None

    def start(self) -> None:
        self.poll_now()

    def stop(self) -> None:
        self._timer.stop()
        if self._worker.isRunning():
            self._worker.wait(2000)

    def poll_now(self) -> None:
        if self._worker.isRunning():
            log.debug("poll skipped: previous fetch still running")
            return
        self._timer.stop()
        self._worker.start()

    def set_game_ids(self, game_ids: list[str]) -> None:
        """Change the selection; the next interval follows the new games' status immediately."""
        self.game_ids = list(game_ids)
        if self.last_ok is not None and not self._worker.isRunning():
            self._schedule(next_interval_ms(self.selected()))

    def selected(self) -> list[GameState | None]:
        return [self.latest.get(gid) for gid in self.game_ids]

    def all_games(self) -> list[GameState]:
        return list(self.latest.values())

    def _on_ok(self, games: list[GameState]) -> None:
        self._backoff_ms = None
        self.latest = {g.game_id: g for g in games}
        self.last_ok = datetime.now(UTC)
        self.games_updated.emit(games)
        self._schedule(next_interval_ms(self.selected()))

    def _on_failed(self, message: str) -> None:
        self._backoff_ms = next_backoff_ms(self._backoff_ms)
        log.warning("fetch failed (%s); retrying in %d s", message, self._backoff_ms // 1000)
        self.fetch_failed.emit(message)
        self._schedule(self._backoff_ms)

    def _schedule(self, ms: int) -> None:
        self._timer.start(ms)
