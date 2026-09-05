"""The strip: frameless, always on top, hidden from the taskbar, draggable."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..data.models import GameState
from .game_row import GameRow

STALE_AFTER_S = 60
EMPTY_MESSAGE = "no game picked: right-click here or the tray icon"

STYLESHEET = """
#ticker { background: #111418; border: 1px solid #2a2f36; border-radius: 6px; }
QLabel { color: #e8e8e8; font-family: "Segoe UI", sans-serif; font-size: 13px; }
#teamName { font-weight: 600; letter-spacing: 0.5px; }
#score { font-size: 15px; font-weight: 700; min-width: 20px; }
#possession { color: #ffb347; font-size: 9px; }
#at, #separator { color: #5c6470; }
#clock { color: #c9d1d9; font-variant-numeric: tabular-nums; }
#situation { color: #9aa4b1; }
#situation[redZone="true"] { color: #ff6b6b; font-weight: 600; }
#stale { color: #f0a020; font-size: 11px; font-style: italic; }
"""


def point_on_a_screen(pos: QPoint) -> bool:
    """A saved position from an unplugged monitor must not strand the strip off-screen."""
    return any(s.availableGeometry().contains(pos) for s in QGuiApplication.screens())


class TickerWindow(QWidget):
    moved = Signal(QPoint)  # emitted when a drag ends
    menu_requested = Signal(QPoint)  # global position of a right-click

    def __init__(self, game_ids: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ticker")
        self.setWindowTitle("CFB Ticker")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(STYLESHEET)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.rows: dict[str, GameRow] = {}
        self._placeholder: GameRow | None = None
        self._games: dict[str, GameState] = {}
        self._drag_offset: QPoint | None = None
        self._dragged = False
        self._last_ok: datetime | None = None
        self._last_error: str = ""

        self.set_game_ids(game_ids)

        # Stale check runs on its own clock so a stalled poller still gets flagged.
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(5_000)
        self._stale_timer.timeout.connect(self._refresh_stale)
        self._stale_timer.start()

    # ---- selection ------------------------------------------------------

    @property
    def game_ids(self) -> list[str]:
        return list(self.rows.keys())

    def set_game_ids(self, game_ids: list[str]) -> None:
        """Rebuild the rows for a new selection and render whatever data is already held."""
        old = list(self.rows.values())
        if self._placeholder is not None:
            old.append(self._placeholder)
            self._placeholder = None
        self.rows.clear()
        for row in old:
            # Unparent before deleteLater so the layout's size hint shrinks now, not next tick.
            self._layout.removeWidget(row)
            row.hide()
            row.setParent(None)
            row.deleteLater()

        if not game_ids:
            self._placeholder = GameRow(self)
            self._placeholder.show_message(EMPTY_MESSAGE)
            self._layout.addWidget(self._placeholder)
        for gid in game_ids:
            row = GameRow(self)
            row.show_message("loading" if self._last_ok is None else f"game {gid} not on today's board")
            self.rows[gid] = row
            self._layout.addWidget(row)
        self._render()
        self.adjustSize()

    # ---- data in ---------------------------------------------------------

    def on_games(self, games: list[GameState]) -> None:
        self._games = {g.game_id: g for g in games}
        self._last_ok = datetime.now(UTC)
        self._last_error = ""
        self._render()
        self.adjustSize()
        self._refresh_stale()

    def on_fetch_failed(self, message: str) -> None:
        self._last_error = message
        self._refresh_stale()

    def summary(self) -> str:
        """One line per row, for the tray tooltip."""
        lines = []
        for gid in self.rows:
            g = self._games.get(gid)
            if g:
                lines.append(f"{g.away.abbreviation} {g.away_score} @ {g.home.abbreviation} {g.home_score}, {g.detail}")
        return "\n".join(lines)

    def _render(self) -> None:
        for gid, row in self.rows.items():
            game = self._games.get(gid)
            if game is not None:
                row.update_game(game)
            elif self._last_ok is not None:
                row.show_message(f"game {gid} not on today's board")

    def _refresh_stale(self) -> None:
        if self._last_ok is None:
            stale = bool(self._last_error)
            tip = self._last_error
        else:
            age = (datetime.now(UTC) - self._last_ok).total_seconds()
            stale = age > STALE_AFTER_S
            tip = f"last update {int(age)} s ago" + (f"; {self._last_error}" if self._last_error else "")
        for row in self.rows.values():
            row.set_stale(stale, tip)

    # ---- placement ---------------------------------------------------------

    def restore_position(self, pos: QPoint | None) -> None:
        if pos is not None and point_on_a_screen(pos):
            self.move(pos)

    # ---- mouse: drag to move, right-click for menu ---------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._dragged = True
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and self._dragged:
            self.moved.emit(self.pos())
        self._drag_offset = None
        self._dragged = False
        event.accept()
