"""One game's rendering: AWAY 14  @  HOME 21 | 0:41 2nd | 3rd & 6 at FUR 24."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..data.models import GameState
from .colors import readable_on_dark

POSSESSION_MARK = "◀"  # black left-pointing triangle, points at the team with the ball
DASH = "–"

_PERIOD_NAMES = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def period_label(period: int) -> str:
    if period in _PERIOD_NAMES:
        return _PERIOD_NAMES[period]
    if period > 4:
        n = period - 4
        return "OT" if n == 1 else f"{n}OT"
    return ""


def clock_text(game: GameState) -> str:
    """What goes in the clock slot for each status."""
    if game.status == "final":
        return "FINAL" if game.period <= 4 else f"FINAL/{period_label(game.period)}"
    if game.status == "pre":
        return game.start_time.astimezone().strftime("%a %I:%M %p").replace(" 0", " ")
    if game.clock == "0:00" and game.detail:
        # "Halftime", "End of 2nd", "Delayed": ESPN's own words beat "0:00 2nd"
        return game.detail
    return f"{game.clock} {period_label(game.period)}".strip()


class GameRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gameRow")

        self.away_name = QLabel("---")
        self.away_score = QLabel("0")
        self.away_poss = QLabel("")
        self.at = QLabel("@")
        self.home_poss = QLabel("")
        self.home_name = QLabel("---")
        self.home_score = QLabel("0")
        self.clock = QLabel("waiting")
        self.situation = QLabel("")
        self.stale = QLabel("")

        for w in (self.away_name, self.home_name):
            w.setObjectName("teamName")
        for w in (self.away_score, self.home_score):
            w.setObjectName("score")
        for w in (self.away_poss, self.home_poss):
            w.setObjectName("possession")
            w.setFixedWidth(12)
        self.at.setObjectName("at")
        self.clock.setObjectName("clock")
        self.situation.setObjectName("situation")
        self.stale.setObjectName("stale")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)
        for w in (
            self.away_poss, self.away_name, self.away_score,
            self.at,
            self.home_name, self.home_score, self.home_poss,
        ):
            layout.addWidget(w)
        layout.addSpacing(8)
        layout.addWidget(self._separator())
        layout.addWidget(self.clock)
        layout.addWidget(self._separator())
        layout.addWidget(self.situation)
        layout.addStretch(1)
        layout.addWidget(self.stale)

    @staticmethod
    def _separator() -> QLabel:
        sep = QLabel("|")
        sep.setObjectName("separator")
        return sep

    def update_game(self, game: GameState) -> None:
        self.away_name.setText(game.away.abbreviation)
        self.home_name.setText(game.home.abbreviation)
        # Team color accent on the abbreviation, lightened so dark brands stay legible.
        self.away_name.setStyleSheet(f"color: {readable_on_dark(game.away.color)};")
        self.home_name.setStyleSheet(f"color: {readable_on_dark(game.home.color)};")
        self.away_score.setText(str(game.away_score))
        self.home_score.setText(str(game.home_score))
        self.clock.setText(clock_text(game))

        live = game.status == "in"
        # Between periods ESPN keeps the last play's down and distance on the wire
        # (seen at halftime: "2nd & 10 at FUR 23"), so only trust it while the clock runs.
        between_periods = game.clock == "0:00"
        show_situation = live and not between_periods
        self.away_poss.setText(POSSESSION_MARK if show_situation and game.possession == "away" else "")
        self.home_poss.setText(POSSESSION_MARK if show_situation and game.possession == "home" else "")
        self.situation.setText((game.down_distance or DASH) if show_situation else "")
        red = show_situation and game.red_zone
        self.situation.setProperty("redZone", red)
        self._repolish(self.situation)
        for marker in (self.away_poss, self.home_poss):
            marker.setProperty("redZone", red)
            self._repolish(marker)

    def set_stale(self, stale: bool, tooltip: str = "") -> None:
        self.stale.setText("stale" if stale else "")
        self.stale.setToolTip(tooltip)

    def show_message(self, text: str) -> None:
        """Before the first successful fetch, or when the game id is not on the board."""
        self.clock.setText(text)
        self.situation.setText("")

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        # Dynamic-property selectors in the stylesheet need an explicit re-polish.
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
