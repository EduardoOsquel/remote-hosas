"""Win32 notification-area menus backed by the existing Qt actions."""
import ctypes
from ctypes import wintypes as W


class WindowsMenu:
    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self._style = None
        signatures = {
            "CreatePopupMenu": ([], W.HMENU),
            "DestroyMenu": ([W.HMENU], W.BOOL),
            "AppendMenuW": ([W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR], W.BOOL),
            "CreateWindowExW": ([W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                W.HWND, W.HMENU, W.HINSTANCE, ctypes.c_void_p], W.HWND),
            "DestroyWindow": ([W.HWND], W.BOOL),
            "GetCursorPos": ([ctypes.POINTER(W.POINT)], W.BOOL),
            "SetForegroundWindow": ([W.HWND], W.BOOL),
            "PostMessageW": ([W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL),
            "TrackPopupMenu": ([W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, W.HWND, ctypes.c_void_p], W.UINT),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

    def build(self, menu, actions):
        handle = self.api.CreatePopupMenu()
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            position = 0
            for action in menu.actions():
                if not action.isVisible():
                    continue
                flags = 0 if action.isEnabled() else 3  # MF_GRAYED | MF_DISABLED
                child = None
                if action.isSeparator():
                    flags, identifier, text = 0x800, 0, None
                elif action.menu() is not None:
                    child = self.build(action.menu(), actions)
                    flags, identifier, text = flags | 0x10, child, action.text()
                else:
                    identifier = len(actions) + 1
                    actions[identifier] = action
                    text = action.text()
                    if action.isChecked():
                        flags |= 8
                if not self.api.AppendMenuW(handle, flags, identifier, text):
                    if child:
                        self.api.DestroyMenu(child)
                    raise ctypes.WinError(ctypes.get_last_error())
                if self._style is not None and not action.isSeparator():
                    self._style.attach_icon(handle, position, action)
                position += 1
            return handle
        except Exception:
            self.api.DestroyMenu(handle)
            raise

    def show(self, menu):
        actions = {}
        from native_menu_style import MenuStyle
        self._style = MenuStyle(self.api)
        self._style.dark()
        handle = None
        owner = None
        try:
            handle = self.build(menu, actions)
            # Dedicated invisible owner; never activate or restore the main window.
            owner = self.api.CreateWindowExW(0, "STATIC", "RemoteHosas tray menu",
                0x80000000, 0, 0, 0, 0, None, None, None, None)
            if not owner:
                raise ctypes.WinError(ctypes.get_last_error())
            point = W.POINT()
            if not self.api.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.api.SetForegroundWindow(owner)
            identifier = self.api.TrackPopupMenu(handle, 0x100 | 0x2,
                point.x, point.y, 0, owner, None)  # TPM_RETURNCMD | TPM_RIGHTBUTTON
            self.api.PostMessageW(owner, 0, 0, 0)
            return actions.get(identifier)
        finally:
            if handle:
                self.api.DestroyMenu(handle)
            self._style.release()
            self._style = None
            if owner:
                self.api.DestroyWindow(owner)
