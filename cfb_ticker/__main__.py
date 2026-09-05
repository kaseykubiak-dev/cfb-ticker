"""Entry point: ``python -m cfb_ticker 401856666 [second_game_id]``."""

from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from .poller import ScorePoller
from .ui.ticker_window import TickerWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cfb-ticker", description="Always-on-top college football score strip.")
    parser.add_argument("game_ids", nargs="+", help="ESPN event id(s), one or two")
    parser.add_argument("-v", "--verbose", action="store_true", help="log fetches to stderr")
    args = parser.parse_args(argv)

    if len(args.game_ids) > 2:
        parser.error("at most two games")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)

    window = TickerWindow(args.game_ids)
    poller = ScorePoller(args.game_ids, parent=window)
    poller.games_updated.connect(window.on_games)
    poller.fetch_failed.connect(window.on_fetch_failed)
    app.aboutToQuit.connect(poller.stop)

    window.show()
    poller.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
