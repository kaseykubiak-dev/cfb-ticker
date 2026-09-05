"""Team color legibility, appbar rect math, dock-screen setting, tray placement menu."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from cfb_ticker.placement.appbar import bottom_strip
from cfb_ticker.settings import Settings
from cfb_ticker.ui.colors import MIN_LUMINANCE, luminance, parse_hex, readable_on_dark
from cfb_ticker.ui.tray import TrayIcon


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_parse_hex():
    assert parse_hex("ff8200") == (255, 130, 0)
    assert parse_hex("#002244") == (0, 34, 68)
    assert parse_hex(None) is None
    assert parse_hex("zzz") is None
    assert parse_hex("abc") is None


def test_readable_on_dark_keeps_bright_colors():
    assert readable_on_dark("ff8200") == "#ff8200"  # Tennessee orange already clears the floor
    assert readable_on_dark("ffffff") == "#ffffff"


def test_readable_on_dark_lightens_dark_colors():
    out = readable_on_dark("002244")  # a navy
    assert out != "#002244"
    assert luminance(parse_hex(out)) >= MIN_LUMINANCE
    assert readable_on_dark("000000") != "#000000"


def test_readable_on_dark_fallback():
    assert readable_on_dark(None) == "#e8e8e8"
    assert readable_on_dark("nope", fallback="#123456") == "#123456"


def test_bottom_strip():
    assert bottom_strip((0, 0, 1920, 1200), 60) == (0, 1140, 1920, 1200)
    assert bottom_strip((1920, 0, 3840, 1080), 48) == (1920, 1032, 3840, 1080)
    assert bottom_strip((0, 0, 100, 30), 60) == (0, 0, 100, 30)  # never taller than the monitor


def test_appbar_screen_setting(tmp_path):
    s = Settings(QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat))
    assert s.appbar_screen is None
    s.appbar_screen = r"\\.\DISPLAY2"
    assert s.appbar_screen == r"\\.\DISPLAY2"
    s.appbar_screen = None
    assert s.appbar_screen is None
    s.placement = "appbar"
    assert s.placement == "appbar"


def test_tray_placement_menu(qapp):
    tray = TrayIcon()
    got = []
    tray.placement_requested.connect(got.append)
    tray.set_placement("appbar")
    checked = [a.data() for a in tray.placement_menu.actions() if a.isChecked()]
    assert checked == ["appbar"]
    assert tray.screen_menu.isEnabled()
    tray.set_placement("floating")
    assert not tray.screen_menu.isEnabled()
    tray.set_screens(None)
    # offscreen platform has one screen, so the submenu hides itself
    assert tray.screen_menu.menuAction().isVisible() is False
    assert len(tray.screen_menu.actions()) == 1
    tray.placement_menu.actions()[1].trigger()
    assert got == ["appbar"]
