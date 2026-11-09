"""HTTPS certificates for the packaged app.

A packaged app (PyInstaller) carries its own Python, whose OpenSSL looks for CA certificates in the folder of the machine
it was built on. On another computer that folder doesn't exist, every HTTPS request fails with "certificate verify failed",
and SeekSync said "Can't reach GitHub" or lost covers and Spotify. The bundle of the certifi package ships with the app, so
point OpenSSL at it. A file the user chose themselves (SSL_CERT_FILE) is respected when it exists."""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def use_bundled_certificates() -> str:
    """Make every HTTPS client in this process (aiohttp, urllib, ssl) trust the certifi bundle. Returns the file used
    ('' when nothing was changed)."""
    current = os.environ.get("SSL_CERT_FILE", "")
    if current and os.path.isfile(current):
        return ""
    try:
        import certifi
        path = certifi.where()
    except Exception:                                    # certifi missing: leave the system defaults alone
        log.debug("certifi isn't available", exc_info=True)
        return ""
    if not os.path.isfile(path):
        return ""
    os.environ["SSL_CERT_FILE"] = path
    return path
