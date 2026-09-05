"""The strip: frameless, always on top, hidden from the taskbar, draggable."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..data.models import GameState
from .game_row import GameRow

STALE_AFTER_S = 60

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


class TickerWindow(QWidget):
    def __init__(self, game_ids: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game_ids = list(game_ids)
        self.setObjectName("ticker")
        self.setWindowTitle("CFB Ticker")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(STYLESHEET)

        self.rows: dict[str, GameRow] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for gid in self.game_ids:
            row = GameRow(self)
            row.show_message("loading")
            self.rows[gid] = row
            layout.addWidget(row)

        self._drag_offset: QPoint | None = None
        self._last_ok: datetime | None = None
        self._last_error: str = ""

        # Stale check runs on its own clock so a stalled poller still gets flagged.
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(5_000)
        self._stale_timer.timeout.connect(self._refresh_stale)
        self._stale_timer.start()

    # ---- data in ---------------------------------------------------------

    def on_games(self, games: list[GameState]) -> None:
        by_id = {g.game_id: g for g in games}
        self._last_ok = datetime.now(UTC)
        self._last_error = ""
        for gid, row in self.rows.items():
            game = by_id.get(gid)
            if game is None:
                row.show_message(f"game {gid} not on today's board")
            else:
                row.update_game(game)
        self.adjustSize()
        self._refresh_stale()

    def on_fetch_failed(self, message: str) -> None:
        self._last_error = message
        self._refresh_stale()

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

    # ---- drag to move ----------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        event.accept()
