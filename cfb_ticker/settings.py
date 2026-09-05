"""QSettings wrapper. On Windows this lives in HKCU\\Software\\KaseyKubiak\\CFBTicker."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSettings

ORG = "KaseyKubiak"
APP = "CFBTicker"
MAX_GAMES = 2


class Settings:
    def __init__(self, backend: QSettings | None = None) -> None:
        self._s = backend or QSettings(ORG, APP)

    # ---- selected games --------------------------------------------------

    @property
    def game_ids(self) -> list[str]:
        return _str_list(self._s.value("games/selected", []))[:MAX_GAMES]

    @game_ids.setter
    def game_ids(self, ids: list[str]) -> None:
        self._s.setValue("games/selected", [str(i) for i in ids][:MAX_GAMES])
        self._s.sync()

    # ---- favorite teams (ESPN team ids) ----------------------------------

    @property
    def favorite_team_ids(self) -> list[str]:
        return _str_list(self._s.value("favorites/teams", []))

    @favorite_team_ids.setter
    def favorite_team_ids(self, ids: list[str]) -> None:
        self._s.setValue("favorites/teams", sorted({str(i) for i in ids}))
        self._s.sync()

    def toggle_favorite(self, team_id: str) -> bool:
        """Add or remove a team. Returns True if it is a favorite afterwards."""
        favs = set(self.favorite_team_ids)
        if team_id in favs:
            favs.remove(team_id)
            result = False
        else:
            favs.add(team_id)
            result = True
        self.favorite_team_ids = sorted(favs)
        return result

    @property
    def auto_follow(self) -> bool:
        """Fill empty slots with favorites' live games and drop finals after a grace period."""
        v = self._s.value("games/auto_follow", True)
        return v in (True, "true", "True", 1, "1")

    @auto_follow.setter
    def auto_follow(self, enabled: bool) -> None:
        self._s.setValue("games/auto_follow", bool(enabled))
        self._s.sync()

    # ---- window ------------------------------------------------------------

    @property
    def window_pos(self) -> QPoint | None:
        v = self._s.value("window/pos")
        return v if isinstance(v, QPoint) else None

    @window_pos.setter
    def window_pos(self, pos: QPoint) -> None:
        self._s.setValue("window/pos", pos)
        self._s.sync()

    @property
    def placement(self) -> str:
        """'floating' or 'appbar'. AppBar arrives in Phase 3; stored now so nothing migrates later."""
        return str(self._s.value("window/placement", "floating"))

    @placement.setter
    def placement(self, mode: str) -> None:
        self._s.setValue("window/placement", mode)
        self._s.sync()

    @property
    def appbar_screen(self) -> str | None:
        """QScreen.name() of the monitor the bar docks to; None means the primary screen."""
        v = self._s.value("window/appbar_screen")
        return str(v) if v else None

    @appbar_screen.setter
    def appbar_screen(self, name: str | None) -> None:
        if name:
            self._s.setValue("window/appbar_screen", name)
        else:
            self._s.remove("window/appbar_screen")
        self._s.sync()


def _str_list(raw: object) -> list[str]:
    """QSettings hands back a list, a single str, or None depending on how many were stored."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(x) for x in raw]
