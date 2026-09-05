"""System tray icon and its menu. Owns no state; everything is a signal to __main__."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def make_icon(size: int = 64) -> QIcon:
    """A dark rounded tile with an orange football. Generated so Phase 1-3 need no asset file."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#111418")))
    p.drawRoundedRect(QRect(0, 0, size, size), size * 0.2, size * 0.2)
    # football: a rotated ellipse with a lace line
    p.save()
    p.translate(size / 2, size / 2)
    p.rotate(-35)
    p.setBrush(QBrush(QColor("#ffb347")))
    p.drawEllipse(-size * 0.36, -size * 0.2, size * 0.72, size * 0.4)
    p.setPen(QPen(QColor("#111418"), max(1, size // 16)))
    p.drawLine(-size * 0.12, 0, size * 0.12, 0)
    p.restore()
    p.end()
    return QIcon(pix)


class TrayIcon(QObject):
    pick_requested = Signal()
    toggle_requested = Signal()
    refresh_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.menu = QMenu()
        self.pick_action = QAction("Pick games...", self.menu)
        self.toggle_action = QAction("Hide ticker", self.menu)
        self.refresh_action = QAction("Refresh now", self.menu)
        self.quit_action = QAction("Quit", self.menu)
        self.pick_action.triggered.connect(self.pick_requested)
        self.toggle_action.triggered.connect(self.toggle_requested)
        self.refresh_action.triggered.connect(self.refresh_requested)
        self.quit_action.triggered.connect(self.quit_requested)
        self.menu.addAction(self.pick_action)
        self.menu.addAction(self.toggle_action)
        self.menu.addAction(self.refresh_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)

        self.icon = QSystemTrayIcon(make_icon(), self)
        self.icon.setToolTip("CFB Ticker")
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)

    def show(self) -> None:
        self.icon.show()

    def set_visible_state(self, ticker_visible: bool) -> None:
        self.toggle_action.setText("Hide ticker" if ticker_visible else "Show ticker")

    def set_summary(self, text: str) -> None:
        self.icon.setToolTip(f"CFB Ticker\n{text}" if text else "CFB Ticker")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.pick_requested.emit()
