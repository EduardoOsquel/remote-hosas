"""Preserve redirected helper output without allocating a Windows console."""
import os
import sys


def redirected_stream(identifier):
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE,
        wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
        wintypes.BOOL, wintypes.DWORD]
    kernel.DuplicateHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.GetStdHandle(identifier & 0xffffffff)
    if handle in (None, 0, ctypes.c_void_p(-1).value):
        raise OSError("No redirected output handle")
    process = kernel.GetCurrentProcess()
    duplicate = wintypes.HANDLE()
    if not kernel.DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(duplicate.value, os.O_WRONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(duplicate)
        raise
    return os.fdopen(descriptor, "w", encoding="utf-8", errors="replace", buffering=1)


def prepare_output(helper=False):
    for name, identifier in (("stdout", -11), ("stderr", -12)):
        if getattr(sys, name) is not None:
            continue
        if helper and sys.platform == "win32":
            try:
                setattr(sys, name, redirected_stream(identifier))
                continue
            except OSError:
                pass
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
