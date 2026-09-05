"""Team color helpers. ESPN hands back bare hex like 'ff8200' or '002244'."""

from __future__ import annotations

MIN_LUMINANCE = 0.30  # relative luminance floor: navy and forest green get lifted, Tennessee orange (0.37) does not


def parse_hex(raw: str | None) -> tuple[int, int, int] | None:
    if not raw:
        return None
    s = raw.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_on_dark(raw: str | None, fallback: str = "#e8e8e8") -> str:
    """Lighten a team color toward white until it clears the luminance floor. Returns '#rrggbb'."""
    rgb = parse_hex(raw)
    if rgb is None:
        return fallback
    r, g, b = rgb
    for _ in range(12):
        if luminance((r, g, b)) >= MIN_LUMINANCE:
            break
        r, g, b = (int(c + (255 - c) * 0.25) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"
