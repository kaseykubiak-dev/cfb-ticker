"""Entry point: ``python -m cfb_ticker [game_id ...]``.

Game ids on the command line override and replace the saved selection; with none, the
saved selection is used, and with nothing saved the strip says so and the tray picker
is the way in.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog

from .data.espn import EspnProvider
from .poller import ScorePoller
from .settings import MAX_GAMES, Settings
from .ui.picker_dialog import PickerDialog
from .ui.ticker_window import TickerWindow
from .ui.tray import TrayIcon


class App:
    """Wires settings, poller, window, tray and picker together. One instance per process."""

    def __init__(self, game_ids: list[str] | None) -> None:
        self.settings = Settings()
        if game_ids:
            self.settings.game_ids = game_ids
        ids = self.settings.game_ids

        self.poller = ScorePoller(EspnProvider(), ids)
        self.window = TickerWindow(ids)
        self.tray = TrayIcon()
        self._picker: PickerDialog | None = None

        self.poller.games_updated.connect(self._on_games)
        self.poller.fetch_failed.connect(self.window.on_fetch_failed)
        self.window.moved.connect(self._on_moved)
        self.window.menu_requested.connect(self._on_menu_requested)
        self.tray.pick_requested.connect(self.open_picker)
        self.tray.toggle_requested.connect(self.toggle_window)
        self.tray.refresh_requested.connect(self.poller.poll_now)
        self.tray.placement_requested.connect(self.set_placement)
        self.tray.screen_requested.connect(self.set_dock_screen)
        self.tray.quit_requested.connect(QApplication.instance().quit)

        qapp = QGuiApplication.instance()
        qapp.screenAdded.connect(lambda _s: self._refresh_screens())
        qapp.screenRemoved.connect(lambda _s: self._refresh_screens())

    def start(self) -> None:
        mode = self.settings.placement
        self.window.set_placement(mode, self.settings.appbar_screen, self.settings.window_pos)
        self.tray.set_placement(mode)
        self._refresh_screens()
        self.window.show()
        self.tray.show()
        self.tray.set_visible_state(True)
        self.poller.start()

    def stop(self) -> None:
        self.poller.stop()
        self.window.set_placement("floating")  # releases the AppBar reservation cleanly

    # ---- slots ---------------------------------------------------------

    def _on_games(self, games) -> None:
        self.window.on_games(games)
        self.tray.set_summary(self.window.summary())

    def _on_moved(self, pos: QPoint) -> None:
        self.settings.window_pos = pos

    def _on_menu_requested(self, global_pos: QPoint) -> None:
        self.tray.menu.popup(global_pos)

    def _refresh_screens(self) -> None:
        self.tray.set_screens(self.settings.appbar_screen)

    def toggle_window(self) -> None:
        visible = not self.window.isVisible()
        self.window.setVisible(visible)
        self.tray.set_visible_state(visible)

    def set_placement(self, mode: str) -> None:
        self.settings.placement = mode
        self.window.set_placement(mode, self.settings.appbar_screen, self.settings.window_pos)
        self.tray.set_placement(mode)

    def set_dock_screen(self, screen_name: str) -> None:
        self.settings.appbar_screen = screen_name
        self.tray.set_screens(screen_name)
        if self.settings.placement == "appbar":
            self.window.set_placement("appbar", screen_name)

    def open_picker(self) -> None:
        if self._picker is not None:
            self._picker.raise_()
            self._picker.activateWindow()
            return
        self._picker = PickerDialog(
            self.poller.all_games(), self.settings.game_ids, self.settings.favorite_team_ids
        )
        try:
            if self._picker.exec() == QDialog.DialogCode.Accepted:
                self._apply_selection(self._picker.selected_game_ids(), self._picker.favorite_team_ids())
        finally:
            self._picker = None

    def _apply_selection(self, game_ids: list[str], favorite_ids: list[str]) -> None:
        game_ids = game_ids[:MAX_GAMES]
        self.settings.game_ids = game_ids
        self.settings.favorite_team_ids = favorite_ids
        self.poller.set_game_ids(game_ids)
        self.window.set_game_ids(game_ids)
        if self.poller.latest:
            self._on_games(self.poller.all_games())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cfb-ticker", description="Always-on-top college football score strip.")
    parser.add_argument("game_ids", nargs="*", help="ESPN event id(s); replaces the saved selection")
    parser.add_argument("-v", "--verbose", action="store_true", help="log fetches to stderr")
    parser.add_argument("--placement", choices=["floating", "appbar"], help="override the saved placement mode")
    args = parser.parse_args(argv)
    if len(args.game_ids) > MAX_GAMES:
        parser.error(f"at most {MAX_GAMES} games")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Ctrl+C in the launching console ends the process at once, no traceback out of a Qt slot.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("CFB Ticker")
    qapp.setQuitOnLastWindowClosed(False)  # the tray keeps us alive when the strip is hidden

    app = App(args.game_ids or None)
    if args.placement:
        app.settings.placement = args.placement
    qapp.aboutToQuit.connect(app.stop)
    app.start()
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
