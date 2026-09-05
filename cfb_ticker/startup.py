"""Start with Windows, via the per-user Run key.

``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` is what the Settings app's
"Startup apps" page lists and what Task Manager's Startup tab toggles, so a user can
turn it off without us. It needs no COM shortcut plumbing, unlike a ``.lnk`` in the
Startup folder, which is why the design doc's shortcut plan was swapped for this.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CFBTicker"


def launch_command() -> str:
    """The command the Run key should hold for this install.

    Frozen (PyInstaller): the .exe itself. From source: the venv's pythonw so no console
    window appears, running the package as a module.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else python
    # No working directory needed: uv installs the project editable into the venv.
    return f'"{interpreter}" -m cfb_ticker'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool, command: str | None = None) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
