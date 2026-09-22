"""Native menu theme and alpha bitmap resources; no custom popup windows."""
import ctypes
from ctypes import wintypes as W
import sys
from PyQt6.QtGui import QImage, QIcon


class MenuItemInfo(ctypes.Structure):
    _fields_ = [("cbSize", W.UINT), ("fMask", W.UINT), ("fType", W.UINT),
        ("fState", W.UINT), ("wID", W.UINT), ("hSubMenu", W.HMENU),
        ("hbmpChecked", W.HBITMAP), ("hbmpUnchecked", W.HBITMAP),
        ("dwItemData", ctypes.c_size_t), ("dwTypeData", W.LPWSTR),
        ("cch", W.UINT), ("hbmpItem", W.HBITMAP)]


class BitmapInfo(ctypes.Structure):
    _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
        ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
        ("imageSize", W.DWORD), ("xppm", W.LONG), ("yppm", W.LONG),
        ("colors", W.DWORD), ("important", W.DWORD), ("color", W.DWORD)]


class MenuStyle:
    def __init__(self, user32):
        self.api = user32
        self.bitmaps = []
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.gdi.CreateDIBSection.argtypes = [W.HDC, ctypes.POINTER(BitmapInfo),
            W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]
        self.gdi.CreateDIBSection.restype = W.HBITMAP
        self.gdi.DeleteObject.argtypes = [W.HANDLE]
        self.gdi.DeleteObject.restype = W.BOOL
        self.api.SetMenuItemInfoW.argtypes = [W.HMENU, W.UINT, W.BOOL, ctypes.POINTER(MenuItemInfo)]
        self.api.SetMenuItemInfoW.restype = W.BOOL
        self.api.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.api.GetSystemMetrics.restype = ctypes.c_int
        self._theme = None

    def dark(self):
        # Same guarded ordinal exports used by Microsoft's PowerToys/ZoomIt.
        # Their signatures apply to Windows 10 1903 and later only.
        if sys.getwindowsversion().build < 18362:
            return False
        class HighContrast(ctypes.Structure):
            _fields_ = [("size", W.UINT), ("flags", W.DWORD), ("scheme", W.LPWSTR)]
        contrast = HighContrast()
        contrast.size = ctypes.sizeof(contrast)
        self.api.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, ctypes.c_void_p, W.UINT]
        self.api.SystemParametersInfoW.restype = W.BOOL
        if self.api.SystemParametersInfoW(0x42, contrast.size, ctypes.byref(contrast), 0) and contrast.flags & 1:
            return False
        try:
            self._theme = ctypes.WinDLL("uxtheme")
            preferred = self._theme[135]
            preferred.argtypes, preferred.restype = [ctypes.c_int], ctypes.c_int
            flush = self._theme[136]
            flush.argtypes, flush.restype = [], None
            preferred(2)  # ForceDark, scoped to this process, not Windows settings.
            flush()
            return True
        except (OSError, AttributeError):
            return False

    def attach_icon(self, menu, position, action):
        if action.icon().isNull():
            return
        size = max(16, self.api.GetSystemMetrics(71))  # SM_CXMENUCHECK, scales with system DPI.
        mode = QIcon.Mode.Normal if action.isEnabled() else QIcon.Mode.Disabled
        image = action.icon().pixmap(size, size, mode).toImage().scaled(size, size)
        image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        info = BitmapInfo()
        info.size, info.width, info.height = 40, size, -size
        info.planes, info.bits = 1, 32
        pixels = ctypes.c_void_p()
        bitmap = self.gdi.CreateDIBSection(None, ctypes.byref(info), 0, ctypes.byref(pixels), None, 0)
        if not bitmap:
            raise ctypes.WinError(ctypes.get_last_error())
        self.bitmaps.append(bitmap)
        ctypes.memmove(pixels, image.constBits().asstring(image.sizeInBytes()), image.sizeInBytes())
        item = MenuItemInfo()
        item.cbSize, item.fMask, item.hbmpItem = ctypes.sizeof(item), 0x80, bitmap
        if not self.api.SetMenuItemInfoW(menu, position, True, ctypes.byref(item)):
            raise ctypes.WinError(ctypes.get_last_error())

    def release(self):
        for bitmap in self.bitmaps:
            self.gdi.DeleteObject(bitmap)
        self.bitmaps.clear()
