"""Start-with-Windows: the Run-key command, without touching the real registry."""

import sys

import pytest

from cfb_ticker import startup


def test_launch_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Tools\CFBTicker.exe")
    assert startup.launch_command() == r'"C:\Tools\CFBTicker.exe"'


def test_launch_command_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = startup.launch_command()
    assert "-m cfb_ticker" in cmd
    assert cmd.startswith('"')
    assert "python" in cmd.lower()
    assert "--cwd" not in cmd


@pytest.mark.skipif(sys.platform != "win32", reason="registry")
def test_set_enabled_round_trip(monkeypatch):
    """Use a throwaway value name so the test never touches the app's real Run entry."""
    monkeypatch.setattr(startup, "VALUE_NAME", "CFBTickerTest")
    try:
        startup.set_enabled(True, command='"x.exe"')
        assert startup.is_enabled()
        startup.set_enabled(False)
        assert not startup.is_enabled()
        startup.set_enabled(False)  # idempotent
    finally:
        startup.set_enabled(False)
