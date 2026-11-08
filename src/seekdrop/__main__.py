"""Entry point: `python -m seekdrop` or the packaged app."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import webbrowser

from . import __version__
from .app import Backend, acquire_instance_lock, setup_logging
from .config import APP_NAME, migrate_legacy_data

ALREADY_RUNNING_HTML = """<html><body style="font-family:system-ui;background:#111;color:#eee;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><h2>SeekDrop is already running</h2>
<p style="color:#999">Switch to the open SeekDrop window.</p></div></body></html>"""


class JsApi:
    """Functions the UI can call through pywebview (native dialogs)."""

    def __init__(self):
        self.window = None

    def pick_folder(self, start: str = ""):
        import webview

        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        result = self.window.create_file_dialog(kind, directory=start or "")
        if result:
            return result[0] if isinstance(result, (list, tuple)) else result
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seekdrop")
    ap.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of an app window")
    ap.add_argument("--headless", action="store_true", help="run without any UI (prints the UI address)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = ap.parse_args(argv)

    setup_logging(args.verbose)
    lock = acquire_instance_lock()
    if lock is None:
        if args.headless or args.browser:   # no window wanted: just say so
            print("SeekDrop is already running.", file=sys.stderr)
            return 1
        try:
            import webview
            webview.create_window(APP_NAME, html=ALREADY_RUNNING_HTML, width=460, height=220)
            webview.start()
        except Exception:
            print("SeekDrop is already running.", file=sys.stderr)
        return 1

    try:   # first start after a rename: take over the old data folder
        migrate_legacy_data()
    except OSError:
        logging.getLogger("seekdrop").exception("couldn't move the old data folder")

    backend = Backend(port=args.port)
    url = backend.start()

    def on_term(signum, frame):   # `kill` / logout: shut down like Ctrl+C so transfers get cleaned up
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError):
        pass

    use_window = not (args.browser or args.headless)
    if use_window:
        try:
            import webview
        except Exception:
            use_window = False

    try:
        if use_window:
            api = JsApi()
            window = webview.create_window(APP_NAME, url, js_api=api, width=1200, height=800,
                                           min_size=(860, 560), background_color="#0f0f10")
            api.window = window
            webview.start()
        else:
            print(f"{APP_NAME} is running at {url}", flush=True)
            if not args.headless:
                webbrowser.open(url)
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
