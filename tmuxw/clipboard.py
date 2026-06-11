"""Portapapeles de Windows vía ctypes (CF_UNICODETEXT)."""
import ctypes
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]


def set_clipboard_text(text: str) -> bool:
    """Copia `text` al portapapeles de Windows. Devuelve True si tuvo éxito."""
    data = text.encode("utf-16-le") + b"\x00\x00"
    if not _user32.OpenClipboard(None):
        return False
    try:
        _user32.EmptyClipboard()
        handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            return False
        ctypes.memmove(ptr, data, len(data))
        _kernel32.GlobalUnlock(handle)
        if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False
        return True
    finally:
        _user32.CloseClipboard()


def get_clipboard_text() -> str | None:
    """Lee texto (CF_UNICODETEXT) del portapapeles de Windows. Devuelve None si vacío."""
    if not _user32.OpenClipboard(None):
        return None
    try:
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        size = _kernel32.GlobalSize(handle)
        if size <= 0:
            return None
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            data = ctypes.string_at(ptr, size)
            text = data.decode("utf-16-le").rstrip("\x00")
            return text
        finally:
            _kernel32.GlobalUnlock(handle)
    except Exception:
        return None
    finally:
        _user32.CloseClipboard()
