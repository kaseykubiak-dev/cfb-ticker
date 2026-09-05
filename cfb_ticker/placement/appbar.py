"""Dock the strip to the taskbar edge as a Windows AppBar, so the desktop reserves its space.

All geometry here is in physical pixels, because SHAppBarMessage and MoveWindow speak
physical pixels and Qt (per-monitor DPI aware) translates the resulting WM_WINDOWPOSCHANGED
back into its own logical coordinates on its own. Never mix the two in this file.

Protocol (docs.microsoft.com/windows/win32/shell/application-desktop-toolbars):
    ABM_NEW registers the HWND and a callback message id.
    ABM_QUERYPOS proposes a rect for an edge; the shell shrinks it around other appbars
    (the taskbar included). ABM_SETPOS commits it and reserves the work area.
    ABN_POSCHANGED arrives on the callback message whenever another appbar moves or the
    taskbar changes; re-query and re-set. ABM_REMOVE releases the reservation.
A crashed process never sends ABM_REMOVE, so the reservation is also released in an
atexit hook; Explorer clears it eventually anyway when the HWND dies.
"""

from __future__ import annotations

import atexit
import ctypes
import ctypes.wintypes as w
import logging

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

log = logging.getLogger(__name__)

ABM_NEW = 0x0
ABM_REMOVE = 0x1
ABM_QUERYPOS = 0x2
ABM_SETPOS = 0x3
ABM_GETSTATE = 0x4
ABM_GETTASKBARPOS = 0x5
ABN_POSCHANGED = 0x1
ABE_BOTTOM = 3
WM_DISPLAYCHANGE = 0x007E
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("hWnd", w.HWND),
        ("uCallbackMessage", w.UINT),
        ("uEdge", w.UINT),
        ("rc", w.RECT),
        ("lParam", w.LPARAM),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("rcMonitor", w.RECT),
        ("rcWork", w.RECT),
        ("dwFlags", w.DWORD),
        ("szDevice", w.WCHAR * 32),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HMONITOR, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)


_shell32 = ctypes.windll.shell32
_user32 = ctypes.windll.user32
_shell32.SHAppBarMessage.restype = ctypes.c_size_t
_shell32.SHAppBarMessage.argtypes = [w.DWORD, ctypes.POINTER(APPBARDATA)]
_user32.MonitorFromWindow.restype = w.HMONITOR
_user32.MonitorFromPoint.restype = w.HMONITOR


def taskbar_rect() -> tuple[int, w.RECT]:
    """(edge, rect) of the primary taskbar in physical pixels."""
    abd = APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA))
    _shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd))
    return abd.uEdge, abd.rc


def monitor_rect_at(x: int, y: int) -> w.RECT:
    """Full monitor rectangle (not work area) containing a physical point."""
    hmon = _user32.MonitorFromPoint(w.POINT(x, y), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFOEXW(cbSize=ctypes.sizeof(MONITORINFOEXW))
    _user32.GetMonitorInfoW(hmon, ctypes.byref(info))
    return info.rcMonitor


def monitor_rect_by_name(device_name: str) -> w.RECT | None:
    r"""Physical rect of the monitor whose device name matches QScreen.name() (e.g. '\\.\DISPLAY1')."""
    found: list[w.RECT] = []

    def _cb(hmon, _hdc, _rect, _lparam):
        info = MONITORINFOEXW(cbSize=ctypes.sizeof(MONITORINFOEXW))
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(info)) and info.szDevice == device_name:
            found.append(w.RECT(info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom))
        return True

    _user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return found[0] if found else None


def bottom_strip(monitor: tuple[int, int, int, int], height: int) -> tuple[int, int, int, int]:
    """Pure helper: the proposed rect for a strip of `height` along the monitor's bottom edge."""
    left, top, right, bottom = monitor
    return left, max(top, bottom - height), right, bottom


class AppBar(QAbstractNativeEventFilter):
    """Registers one HWND as a bottom-edge appbar on a chosen monitor and keeps it placed."""

    def __init__(self, hwnd: int, notifier: AppBarNotifier) -> None:
        super().__init__()
        self.hwnd = hwnd
        self._notifier = notifier
        self._callback_msg = _user32.RegisterWindowMessageW("CFBTickerAppBarCallback")
        self._registered = False
        self._height_px = 0
        self._monitor_point: tuple[int, int] = (0, 0)
        self._filter_installed = False
        self._granted: tuple[int, int, int, int] | None = None

    # ---- lifecycle ---------------------------------------------------------

    def dock(self, height_px: int, monitor_point: tuple[int, int]) -> w.RECT | None:
        """Register (first time) and place the bar. Returns the physical rect actually granted."""
        self._height_px = height_px
        self._monitor_point = monitor_point
        if not self._registered:
            abd = self._data()
            abd.uCallbackMessage = self._callback_msg
            if not _shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd)):
                log.error("ABM_NEW failed for hwnd %s", self.hwnd)
                return None
            self._registered = True
            atexit.register(self.undock)
            if not self._filter_installed:
                QCoreApplication.instance().installNativeEventFilter(self)
                self._filter_installed = True
        return self._place(force=True)

    def undock(self) -> None:
        if not self._registered:
            return
        self._granted = None
        abd = self._data()
        _shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        self._registered = False
        app = QCoreApplication.instance()
        if self._filter_installed and app is not None:
            app.removeNativeEventFilter(self)
            self._filter_installed = False
        log.debug("appbar removed")

    @property
    def registered(self) -> bool:
        return self._registered

    # ---- placement ---------------------------------------------------------

    def _place(self, force: bool = False) -> w.RECT | None:
        mon = monitor_rect_at(*self._monitor_point)
        left, top, right, bottom = bottom_strip((mon.left, mon.top, mon.right, mon.bottom), self._height_px)
        abd = self._data()
        abd.uEdge = ABE_BOTTOM
        abd.rc = w.RECT(left, top, right, bottom)
        _shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        # The shell moved rc.bottom up past the taskbar; keep our height from there.
        abd.rc.top = abd.rc.bottom - self._height_px
        wanted = (abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom)
        if wanted == self._granted and not force:
            # The shell echoes ABN_POSCHANGED after our own ABM_SETPOS; nothing moved, so do not
            # answer it with another SETPOS or two appbars can ping-pong forever.
            return abd.rc
        _shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        rc = abd.rc
        self._granted = (rc.left, rc.top, rc.right, rc.bottom)
        _user32.SetWindowPos(
            self.hwnd, 0, rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top, SWP_NOZORDER | SWP_NOACTIVATE
        )
        log.debug("appbar placed at (%d,%d)-(%d,%d)", rc.left, rc.top, rc.right, rc.bottom)
        return rc

    def _data(self) -> APPBARDATA:
        return APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA), hWnd=self.hwnd)

    # ---- native events ---------------------------------------------------------

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt override
        if not self._registered:
            return False, 0
        msg = w.MSG.from_address(int(message))
        if msg.hWnd != self.hwnd:
            return False, 0
        if msg.message == self._callback_msg and msg.wParam == ABN_POSCHANGED:
            self._place()
            self._notifier.repositioned.emit()
        elif msg.message == WM_DISPLAYCHANGE:
            self._place()
            self._notifier.repositioned.emit()
        return False, 0


class AppBarNotifier(QObject):
    """Signals cannot live on a QAbstractNativeEventFilter (not a QObject), so they live here."""

    repositioned = Signal()
