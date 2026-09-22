"""Application identity and icon assets, independent of the working directory."""

import sys
import logging
from pathlib import Path

from PyQt6.QtGui import QIcon


APP_ID = "RemoteHosas.USBIPBridge"
APP_NAME = "USB/IP + Joystick Bridge"
ICON_PATH = Path(__file__).resolve().parent / "assets" / "remote-hosas.ico"


def register_notification_identity():
    """Register presentation metadata for this user, without administrator rights."""
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\AppUserModelId\{APP_ID}", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(ICON_PATH))


def application_icon() -> QIcon:
    return QIcon(str(ICON_PATH))


def set_windows_app_id() -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        try:
            register_notification_identity()
        except OSError:
            logging.getLogger(__name__).warning("Could not register Windows notification branding.", exc_info=True)
