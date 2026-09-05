"""Game picker: favorite teams on the left, today's slate on the right, check up to two games."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..data.models import GameState, TeamInfo
from ..settings import MAX_GAMES
from .game_row import clock_text

_STATUS_ORDER = {"in": 0, "pre": 1, "final": 2}
_SECTION_TITLES = {"favorites": "Favorites", "in": "Live", "pre": "Upcoming", "final": "Final"}


# ---- pure helpers (tested without a QApplication) -------------------------


def teams_on_board(games: list[GameState]) -> list[TeamInfo]:
    seen: dict[str, TeamInfo] = {}
    for g in games:
        for t in (g.home, g.away):
            seen.setdefault(t.team_id, t)
    return sorted(seen.values(), key=lambda t: t.name.lower())


def involves_favorite(game: GameState, favorite_ids: set[str]) -> bool:
    return game.home.team_id in favorite_ids or game.away.team_id in favorite_ids


def group_games(games: list[GameState], favorite_ids: set[str]) -> list[tuple[str, list[GameState]]]:
    """Sections in display order. A favorite's game appears only in Favorites.

    Within a section: live first (by kickoff), then upcoming by kickoff, then finals newest first.
    """
    favorites = [g for g in games if involves_favorite(g, favorite_ids)]
    rest = [g for g in games if not involves_favorite(g, favorite_ids)]

    def live_or_upcoming_key(g: GameState):
        return (_STATUS_ORDER[g.status], g.start_time)

    sections: list[tuple[str, list[GameState]]] = []
    if favorites:
        fav_sorted = sorted(
            favorites, key=lambda g: (_STATUS_ORDER[g.status], -g.start_time.timestamp() if g.status == "final" else g.start_time.timestamp())
        )
        sections.append((_SECTION_TITLES["favorites"], fav_sorted))
    for status in ("in", "pre", "final"):
        bucket = [g for g in rest if g.status == status]
        if not bucket:
            continue
        bucket.sort(key=lambda g: g.start_time, reverse=(status == "final"))
        sections.append((_SECTION_TITLES[status], bucket))
    return sections


def game_label(game: GameState) -> str:
    score = f"{game.away.abbreviation} {game.away_score} @ {game.home.abbreviation} {game.home_score}"
    if game.status == "pre":
        score = f"{game.away.abbreviation} @ {game.home.abbreviation}"
    return f"{score}    {clock_text(game)}"


# ---- the dialog ------------------------------------------------------------


class PickerDialog(QDialog):
    def __init__(
        self,
        games: list[GameState],
        selected_ids: list[str],
        favorite_ids: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("CFB Ticker: pick games")
        self.setMinimumSize(640, 480)
        self._games = {g.game_id: g for g in games}
        self._favorites: list[str] = list(favorite_ids)
        self._checked: list[str] = [gid for gid in selected_ids if gid in self._games]

        root = QHBoxLayout(self)

        # Favorites column
        fav_col = QVBoxLayout()
        fav_col.addWidget(QLabel("Favorite teams"))
        self.fav_list = QListWidget()
        fav_col.addWidget(self.fav_list, 1)
        add_row = QHBoxLayout()
        self.team_combo = QComboBox()
        self.team_combo.setEditable(True)
        self.team_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for t in teams_on_board(games):
            self.team_combo.addItem(f"{t.name} ({t.abbreviation})", t.team_id)
        self.team_combo.setCurrentIndex(-1)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_favorite)
        add_row.addWidget(self.team_combo, 1)
        add_row.addWidget(add_btn)
        fav_col.addLayout(add_row)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_favorite)
        fav_col.addWidget(remove_btn)
        root.addLayout(fav_col, 2)

        # Games column
        game_col = QVBoxLayout()
        self.hint = QLabel(f"Today's games: check up to {MAX_GAMES}. First checked is the top row.")
        game_col.addWidget(self.hint)
        self.game_list = QListWidget()
        self.game_list.itemChanged.connect(self._on_item_changed)
        game_col.addWidget(self.game_list, 1)
        root.addLayout(game_col, 3)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        game_col.addWidget(buttons)

        self._team_names = {t.team_id: t for t in teams_on_board(games)}
        self._rebuild_favorites()
        self._rebuild_games()

    # ---- results ------------------------------------------------------------

    def selected_game_ids(self) -> list[str]:
        return list(self._checked)

    def favorite_team_ids(self) -> list[str]:
        return list(self._favorites)

    # ---- favorites ------------------------------------------------------------

    def _rebuild_favorites(self) -> None:
        self.fav_list.clear()
        for tid in self._favorites:
            t = self._team_names.get(tid)
            label = f"{t.name} ({t.abbreviation})" if t else f"team {tid} (not on today's board)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tid)
            self.fav_list.addItem(item)

    def _add_favorite(self) -> None:
        idx = self.team_combo.currentIndex()
        if idx < 0:
            # Typed text without picking from the list: match on the visible label.
            idx = self.team_combo.findText(self.team_combo.currentText(), Qt.MatchFlag.MatchFixedString)
        if idx < 0:
            return
        tid = str(self.team_combo.itemData(idx))
        if tid not in self._favorites:
            self._favorites.append(tid)
            self._favorites.sort(key=lambda i: self._team_names[i].name.lower() if i in self._team_names else i)
            self._rebuild_favorites()
            self._rebuild_games()
        self.team_combo.setCurrentIndex(-1)

    def _remove_favorite(self) -> None:
        for item in self.fav_list.selectedItems():
            tid = str(item.data(Qt.ItemDataRole.UserRole))
            if tid in self._favorites:
                self._favorites.remove(tid)
        self._rebuild_favorites()
        self._rebuild_games()

    # ---- games ------------------------------------------------------------

    def _rebuild_games(self) -> None:
        self.game_list.blockSignals(True)
        self.game_list.clear()
        for title, bucket in group_games(list(self._games.values()), set(self._favorites)):
            header = QListWidgetItem(title)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self.game_list.addItem(header)
            for g in bucket:
                item = QListWidgetItem(game_label(g))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, g.game_id)
                item.setCheckState(
                    Qt.CheckState.Checked if g.game_id in self._checked else Qt.CheckState.Unchecked
                )
                self.game_list.addItem(item)
        self.game_list.blockSignals(False)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        gid = item.data(Qt.ItemDataRole.UserRole)
        if gid is None:
            return
        gid = str(gid)
        if item.checkState() == Qt.CheckState.Checked:
            if gid not in self._checked:
                self._checked.append(gid)
            if len(self._checked) > MAX_GAMES:
                dropped = self._checked.pop(0)
                self._set_checked(dropped, False)
        else:
            if gid in self._checked:
                self._checked.remove(gid)

    def _set_checked(self, gid: str, checked: bool) -> None:
        self.game_list.blockSignals(True)
        for i in range(self.game_list.count()):
            it = self.game_list.item(i)
            if str(it.data(Qt.ItemDataRole.UserRole)) == gid:
                it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.game_list.blockSignals(False)
