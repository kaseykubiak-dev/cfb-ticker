"""The strip: frameless, always on top, hidden from the taskbar. Floating (draggable) or docked."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QHideEvent, QMouseEvent, QScreen, QShowEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..data.models import GameState
from ..placement import appbar as appbar_mod
from .game_row import GameRow

log = logging.getLogger(__name__)

STALE_AFTER_S = 60
EMPTY_MESSAGE = "no game picked: right-click here or the tray icon"

STYLESHEET = """
#ticker { background: #111418; border: 1px solid #2a2f36; border-radius: 6px; }
#ticker[docked="true"] { border: none; border-top: 1px solid #2a2f36; border-radius: 0; }
QLabel { color: #e8e8e8; font-family: "Segoe UI", sans-serif; font-size: 13px; }
#teamName { font-weight: 600; letter-spacing: 0.5px; }
#score { font-size: 15px; font-weight: 700; min-width: 20px; }
#possession { color: #ffb347; font-size: 9px; }
#possession[redZone="true"] { color: #ff6b6b; }
#at, #separator { color: #5c6470; }
#clock { color: #c9d1d9; }
#situation { color: #9aa4b1; }
#situation[redZone="true"] { color: #ff6b6b; font-weight: 600; }
#stale { color: #f0a020; font-size: 11px; font-style: italic; }
"""


def point_on_a_screen(pos: QPoint) -> bool:
    """A saved position from an unplugged monitor must not strand the strip off-screen."""
    return any(s.availableGeometry().contains(pos) for s in QGuiApplication.screens())


def screen_by_name(name: str | None) -> QScreen:
    for s in QGuiApplication.screens():
        if s.name() == name:
            return s
    return QGuiApplication.primaryScreen()


class TickerWindow(QWidget):
    moved = Signal(QPoint)  # emitted when a drag ends (floating mode only)
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

        self.placement = "floating"
        self.dock_screen: str | None = None
        self._appbar: appbar_mod.AppBar | None = None
        self._appbar_notifier = appbar_mod.AppBarNotifier(self)

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
        self._fit()

    # ---- data in ---------------------------------------------------------

    def on_games(self, games: list[GameState]) -> None:
        self._games = {g.game_id: g for g in games}
        self._last_ok = datetime.now(UTC)
        self._last_error = ""
        self._render()
        self._fit()
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

    def _fit(self) -> None:
        """Floating: shrink-wrap the rows. Docked: keep full width, re-reserve the height."""
        if self.placement == "appbar" and self._appbar is not None and self._appbar.registered:
            self._dock()
        else:
            self.adjustSize()

    # ---- placement ---------------------------------------------------------

    def restore_position(self, pos: QPoint | None) -> None:
        if self.placement != "floating":
            return
        if pos is not None and point_on_a_screen(pos):
            self.move(pos)
        else:
            self.move(self.default_position())

    def default_position(self) -> QPoint:
        """Bottom-right of the primary screen's work area, just above the taskbar."""
        avail = QGuiApplication.primaryScreen().availableGeometry()
        margin = 12
        size = self.sizeHint()
        return QPoint(avail.right() - size.width() - margin, avail.bottom() - size.height() - margin)

    def set_placement(self, mode: str, screen_name: str | None = None, floating_pos: QPoint | None = None) -> None:
        self.dock_screen = screen_name
        if mode == "appbar":
            self.placement = "appbar"
            self.setProperty("docked", True)
            self._repolish()
            if self.isVisible():
                self._dock()
        else:
            self.placement = "floating"
            self._undock()
            self.setProperty("docked", False)
            self._repolish()
            self._layout.activate()
            self.resize(self.sizeHint())
            self.restore_position(floating_pos)

    def _dock(self) -> None:
        if self._appbar is None:
            self._appbar = appbar_mod.AppBar(int(self.winId()), self._appbar_notifier)
        screen = screen_by_name(self.dock_screen)
        dpr = screen.devicePixelRatio()
        # Freshly added rows have no geometry until the layout activates; read the hint after.
        self._layout.activate()
        natural = self._layout.sizeHint().height()
        if natural <= 0:
            natural = sum(r.sizeHint().height() for r in self.rows.values()) or self.sizeHint().height()
        natural_px = math.ceil(natural * dpr)
        edge, tb = appbar_mod.taskbar_rect()
        taskbar_px = (tb.bottom - tb.top) if edge in (1, 3) else 0
        # One row matches the taskbar's height so it reads as part of the shell; two rows take what they need.
        height_px = max(natural_px, taskbar_px) if len(self.rows) <= 1 else max(natural_px, taskbar_px)
        mon = appbar_mod.monitor_rect_by_name(screen.name())
        point = ((mon.left + mon.right) // 2, (mon.top + mon.bottom) // 2) if mon else (0, 0)
        rc = self._appbar.dock(height_px, point)
        if rc is None:
            log.error("dock failed; falling back to floating")
            self.set_placement("floating")

    def _undock(self) -> None:
        if self._appbar is not None:
            self._appbar.undock()

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.placement == "appbar":
            self._dock()

    def hideEvent(self, event: QHideEvent) -> None:
        # Hidden bar must not keep its screen reservation.
        self._undock()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._undock()
        super().closeEvent(event)

    # ---- mouse: drag to move (floating only), right-click for menu ---------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.placement == "floating":
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
