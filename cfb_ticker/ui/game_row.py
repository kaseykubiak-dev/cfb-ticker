"""One game's rendering: #20 TENN 21 ◀  @  FUR 0 | 0:41 2nd | 3rd & 6 at FUR 24."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..data.models import GameState, TeamInfo
from .colors import readable_on_dark

POSSESSION_MARK = "◀"  # black left-pointing triangle, points at the team with the ball
DASH = "–"
FLASH_MS = 1500
FINAL_TEXT_COLOR = "#7d8590"
RANK_COLOR = "#8b949e"

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


def situation_text(game: GameState) -> str:
    """The third slot: down and distance while the clock runs, the network before kickoff."""
    if game.status == "pre":
        return game.broadcast or ""
    if game.status == "in" and game.clock != "0:00":
        return game.down_distance or DASH
    return ""


def tooltip_text(game: GameState) -> str:
    parts = [f"{game.away.name} at {game.home.name}"]
    if game.broadcast:
        parts[0] += f" ({game.broadcast})"
    if game.status == "in" and game.last_play:
        parts.append(f"Last play: {game.last_play}")
    return "\n".join(parts)


def team_label_html(team: TeamInfo) -> str:
    """Rank inline with the abbreviation so both sit on one baseline: '#20 TENN'."""
    if team.rank:
        return f'<span style="font-size:10px; color:{RANK_COLOR};">#{team.rank}</span> {team.abbreviation}'
    return team.abbreviation


class _TeamCell:
    """Abbreviation with inline rank for one side.

    Timeout dots lived here for an evening (2026-09-05) and were removed: ESPN's scoreboard
    timeout fields are not maintained (0/0 with both teams holding two, no reset at the half)
    and the summary endpoint only has whole-game totals. The model still parses the fields.
    """

    def __init__(self) -> None:
        self.name = QLabel("---")
        self.name.setObjectName("teamName")

    def widgets(self) -> list[QLabel]:
        return [self.name]

    def update(self, team: TeamInfo, final: bool) -> None:
        self.name.setText(team_label_html(team))
        color = FINAL_TEXT_COLOR if final else readable_on_dark(team.color)
        self.name.setStyleSheet(f"color: {color};")


class GameRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gameRow")

        self.away = _TeamCell()
        self.home = _TeamCell()
        self.away_score = QLabel("0")
        self.home_score = QLabel("0")
        self.away_poss = QLabel("")
        self.home_poss = QLabel("")
        self.at = QLabel("@")
        self.clock = QLabel("waiting")
        self.situation = QLabel("")
        self.stale = QLabel("")

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
        for w in (self.away_poss, *self.away.widgets(), self.away_score, self.at,
                  *self.home.widgets(), self.home_score, self.home_poss):
            layout.addWidget(w)
        layout.addSpacing(8)
        layout.addWidget(self._separator())
        layout.addWidget(self.clock)
        layout.addWidget(self._separator())
        layout.addWidget(self.situation)
        layout.addStretch(1)
        layout.addWidget(self.stale)

        self._last_scores: tuple[int, int] | None = None
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(FLASH_MS)
        self._flash_timer.timeout.connect(self._clear_flash)

    @staticmethod
    def _separator() -> QLabel:
        sep = QLabel("|")
        sep.setObjectName("separator")
        return sep

    def update_game(self, game: GameState) -> None:
        live = game.status == "in"
        final = game.status == "final"
        # Between periods ESPN keeps the last play's down and distance on the wire
        # (seen at halftime: "2nd & 10 at FUR 23"), so only trust it while the clock runs.
        show_situation = live and game.clock != "0:00"

        self.away.update(game.away, final)
        self.home.update(game.home, final)
        self.away_score.setText(str(game.away_score))
        self.home_score.setText(str(game.home_score))
        self.clock.setText(clock_text(game))
        self.situation.setText(situation_text(game))
        self.setToolTip(tooltip_text(game))

        self.away_poss.setText(POSSESSION_MARK if show_situation and game.possession == "away" else "")
        self.home_poss.setText(POSSESSION_MARK if show_situation and game.possession == "home" else "")
        red = show_situation and game.red_zone
        for w in (self.situation, self.away_poss, self.home_poss):
            w.setProperty("redZone", red)
            self._repolish(w)

        self.setProperty("final", final)
        self._repolish(self)

        scores = (game.away_score, game.home_score)
        if self._last_scores is not None and scores != self._last_scores:
            self._flash(self.away_score, scores[0] != self._last_scores[0])
            self._flash(self.home_score, scores[1] != self._last_scores[1])
        self._last_scores = scores

    def set_stale(self, stale: bool, tooltip: str = "") -> None:
        self.stale.setText("stale" if stale else "")
        self.stale.setToolTip(tooltip)

    def show_message(self, text: str) -> None:
        """Before the first successful fetch, or when the game id is not on the board."""
        self.clock.setText(text)
        self.situation.setText("")
        self._last_scores = None

    # ---- score flash -------------------------------------------------------

    def _flash(self, label: QLabel, changed: bool) -> None:
        if not changed:
            return
        label.setProperty("flash", True)
        self._repolish(label)
        self._flash_timer.start()

    def _clear_flash(self) -> None:
        for label in (self.away_score, self.home_score):
            label.setProperty("flash", False)
            self._repolish(label)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        # Dynamic-property selectors in the stylesheet need an explicit re-polish.
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
