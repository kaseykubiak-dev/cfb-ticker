"""ESPN scoreboard adapter.

Two hosts serve the same undocumented JSON. Observed 2026-09-05 from the UT network:
``site.api.espn.com`` sits behind Akamai bot detection that returns 403 to curl and to
a spoofed browser User-Agent, but passes Python's default one; ``site.web.api.espn.com``
answered every variant. So the adapter tries the web host first, falls back to the
other, and never pretends to be a browser.

Field mapping (verified against a live week 1 response, saved as
``tests/fixtures/scoreboard_live.json``):

- ``status.type.state`` is ``pre`` / ``in`` / ``post``; ``post`` maps to ``final``.
- ``competitions[0].situation`` carries ``downDistanceText``, ``possession`` (a team
  id, not a home/away flag), ``isRedZone``. Any of them can be absent mid-play.
- ``competitors[].score`` is a string; ``competitors[].curatedRank.current`` is 99 when unranked.
- ``competitions[0].broadcast`` is a plain network string ("SECN+"); ``situation.lastPlay.text`` is play-by-play.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import requests

from .models import GameState, Side, TeamInfo

log = logging.getLogger(__name__)

HOSTS = ("site.web.api.espn.com", "site.api.espn.com")
PATH = "/apis/site/v2/sports/football/college-football/scoreboard"
PARAMS = {"groups": "80", "limit": "200"}  # groups=80 is all of FBS
USER_AGENT = "cfb-ticker/0.1 (+https://github.com/kaseykubiak-dev/cfb-ticker)"
TIMEOUT_S = 8

_STATE_MAP = {"pre": "pre", "in": "in", "post": "final"}


class FetchError(RuntimeError):
    """Every host failed or returned something that was not a scoreboard."""


class EspnProvider:
    """ScoreProvider backed by the public scoreboard JSON."""

    name = "espn"

    def __init__(self) -> None:
        self._session = requests.Session()

    def fetch_scoreboard(self) -> list[GameState]:
        return fetch_scoreboard(self._session)


def fetch_scoreboard(session: requests.Session | None = None) -> list[GameState]:
    """Fetch today's FBS scoreboard and parse it. Raises FetchError on total failure."""
    sess = session or requests.Session()
    errors: list[str] = []
    for host in HOSTS:
        url = f"https://{host}{PATH}"
        try:
            resp = sess.get(
                url, params=PARAMS, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S
            )
            if resp.status_code != 200:
                errors.append(f"{host}: HTTP {resp.status_code}")
                continue
            return parse_scoreboard(resp.json())
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{host}: {exc.__class__.__name__}: {exc}")
    raise FetchError("; ".join(errors))


def parse_scoreboard(payload: dict[str, Any], now: datetime | None = None) -> list[GameState]:
    """Turn a scoreboard payload into GameStates. Skips events it cannot parse, with a log line."""
    fetched_at = now or datetime.now(UTC)
    games: list[GameState] = []
    for event in payload.get("events", []):
        try:
            games.append(_parse_event(event, fetched_at))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            log.warning("skipping event %s: %s", event.get("id"), exc)
    return games


def _parse_event(event: dict[str, Any], fetched_at: datetime) -> GameState:
    comp = event["competitions"][0]
    status = event.get("status") or comp["status"]
    stype = status["type"]

    sides: dict[str, dict[str, Any]] = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = sides["home"], sides["away"]

    situation = comp.get("situation") or {}
    possession = _possession(situation.get("possession"), home["id"], away["id"])

    return GameState(
        game_id=str(event["id"]),
        home=_team(home),
        away=_team(away),
        home_score=_score(home.get("score")),
        away_score=_score(away.get("score")),
        status=_STATE_MAP.get(stype.get("state"), "pre"),
        period=int(status.get("period") or 0),
        clock=str(status.get("displayClock") or "0:00"),
        detail=str(stype.get("shortDetail") or stype.get("description") or ""),
        down_distance=situation.get("downDistanceText") or None,
        possession=possession,
        red_zone=bool(situation.get("isRedZone", False)),
        start_time=_parse_date(event["date"]),
        fetched_at=fetched_at,
        home_timeouts=_int_or_none(situation.get("homeTimeouts")),
        away_timeouts=_int_or_none(situation.get("awayTimeouts")),
        last_play=((situation.get("lastPlay") or {}).get("text") or None),
        broadcast=(comp.get("broadcast") or None),
    )


def _team(competitor: dict[str, Any]) -> TeamInfo:
    team = competitor["team"]
    rank = _int_or_none((competitor.get("curatedRank") or {}).get("current"))
    return TeamInfo(
        team_id=str(team["id"]),
        abbreviation=str(team.get("abbreviation") or team.get("shortDisplayName") or "???"),
        name=str(team.get("shortDisplayName") or team.get("displayName") or ""),
        color=team.get("color") or None,
        rank=rank if rank is not None and 1 <= rank <= 25 else None,  # ESPN uses 99 for unranked
    )


def _int_or_none(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _score(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _possession(team_id: Any, home_id: str, away_id: str) -> Side | None:
    if team_id is None:
        return None
    tid = str(team_id)
    if tid == str(home_id):
        return "home"
    if tid == str(away_id):
        return "away"
    return None


def _parse_date(raw: str) -> datetime:
    # ESPN writes "2026-09-05T19:30Z"; fromisoformat wants an offset it recognizes.
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
