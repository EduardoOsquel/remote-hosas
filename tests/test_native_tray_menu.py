import sys
from unittest.mock import MagicMock
import pytest
from PyQt6.QtWidgets import QApplication, QMenu

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 menu")


def test_native_menu_maps_submenu_and_frees_handles():
    from native_tray_menu import WindowsMenu
    application = QApplication.instance() or QApplication([])
    menu = QMenu()
    menu.addAction("Show application")
    submenu = menu.addMenu("Share device")
    chosen = submenu.addAction("2-3 - Controller")
    submenu.addAction("Unavailable").setEnabled(False)
    native = WindowsMenu()
    api = MagicMock()
    api.CreatePopupMenu.side_effect = [100, 101]
    api.CreateWindowExW.return_value = 200
    api.TrackPopupMenu.return_value = 2
    native.api = api
    assert native.show(menu) is chosen
    api.DestroyMenu.assert_called_once_with(100)
    api.DestroyWindow.assert_called_once_with(200)
    api.PostMessageW.assert_called_once_with(200, 0, 0, 0)
    assert any(call.args[1] == 3 for call in api.AppendMenuW.call_args_list)


def test_native_menu_failure_releases_allocated_menu():
    from native_tray_menu import WindowsMenu
    application = QApplication.instance() or QApplication([])
    menu = QMenu()
    menu.addAction("Show application")
    native = WindowsMenu()
    api = MagicMock()
    api.CreatePopupMenu.return_value = 100
    api.AppendMenuW.return_value = False
    native.api = api
    with pytest.raises(OSError):
        native.show(menu)
    api.DestroyMenu.assert_called_once_with(100)



@pytest.mark.parametrize("name,kind", [
    ("Logitech Gaming Mouse", "mouse"), ("USB Keyboard", "keyboard"),
    ("VKB Gladiator Joystick", "gaming"), ("Xbox Wireless Controller", "gaming"),
    ("HP True Vision HD Camera", "camera"), ("USB Headset", "audio"),
    ("Realtek USB GbE Family Controller", "network"),
    ("Logitech USB Input Device", "usb"), ("unknown product", "usb")])
def test_device_icons_are_conservative(name, kind):
    from ui_icons import device_icon_kind
    assert device_icon_kind(name) == kind


def test_native_menu_attaches_and_releases_real_bitmap():
    import ctypes
    from native_tray_menu import WindowsMenu
    from native_menu_style import MenuStyle, MenuItemInfo
    from ui_icons import line_icon
    application = QApplication.instance() or QApplication([])
    menu = QMenu()
    action = menu.addAction("1-1 - Joystick")
    action.setIcon(line_icon("gaming"))
    native = WindowsMenu()
    style = MenuStyle(native.api)
    native._style = style
    handle = native.build(menu, {})
    try:
        info = MenuItemInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = 0x80
        native.api.GetMenuItemInfoW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
            ctypes.c_int, ctypes.POINTER(MenuItemInfo)]
        assert native.api.GetMenuItemInfoW(handle, 0, True, ctypes.byref(info))
        assert info.hbmpItem in style.bitmaps
    finally:
        native.api.DestroyMenu(handle)
        style.release()
    assert style.bitmaps == []
