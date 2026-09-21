"""Application identity and icon assets, independent of the working directory."""

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon


def application_icon() -> QIcon:
    return QIcon(str(Path(__file__).resolve().parent / "assets" / "remote-hosas.ico"))


def set_windows_app_id() -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RemoteHosas.USBIPBridge")
