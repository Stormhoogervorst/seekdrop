"""Keeping the Soulseek password and the Nicotine+ key out of plain sight in settings.json.

On macOS and Linux settings.json can only be read by the user (chmod 600), so the values stay as they are. Windows
has no such file mode, so there they are encrypted with the Windows Data Protection API (DPAPI, `CryptProtectData`):
only the same Windows user on the same computer can read them back. No extra package is needed; it is part of
Windows. A value that can't be read back (settings copied from another computer) comes out empty, and the user is
asked for the password again, like on a fresh install."""
from __future__ import annotations

import base64
import logging
import sys

log = logging.getLogger(__name__)

PREFIX = "dpapi:"
IS_WINDOWS = sys.platform.startswith("win")
_UI_FORBIDDEN = 0x01         # never show a dialog


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    dst = Blob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, _UI_FORBIDDEN, ctypes.byref(dst)):
        raise OSError(ctypes.get_last_error() or ctypes.GetLastError(), "DPAPI failed")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(dst.pbData, ctypes.c_void_p))


def protect(value: str) -> str:
    """What goes into settings.json for a secret. Unchanged off Windows, and when encrypting fails."""
    if not value or not IS_WINDOWS:
        return value
    try:
        return PREFIX + base64.b64encode(_dpapi(value.encode("utf-8"), True)).decode("ascii")
    except Exception:
        log.warning("couldn't encrypt a setting, it is stored as it is", exc_info=True)
        return value


def unprotect(stored: str) -> str:
    """The secret from what settings.json holds. A plain value (older versions, macOS) is returned as it is."""
    if not isinstance(stored, str) or not stored.startswith(PREFIX):
        return stored
    if not IS_WINDOWS:
        log.warning("a setting was encrypted on Windows and can't be read here; it has to be entered again")
        return ""
    try:
        return _dpapi(base64.b64decode(stored[len(PREFIX):]), False).decode("utf-8")
    except Exception:
        log.warning("couldn't decrypt a setting (made by another Windows user or computer?); it has to be entered again",
                    exc_info=True)
        return ""
