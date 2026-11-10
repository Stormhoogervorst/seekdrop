"""Entry point: `python -m seeksync` or the packaged app."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
import webbrowser

from . import __version__
from .app import Backend, acquire_instance_lock, setup_logging
from . import diag
from .config import APP_NAME, log_dir, migrate_legacy_data

ALREADY_RUNNING_HTML = """<html><body style="font-family:system-ui;background:#111;color:#eee;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><h2>SeekSync is already running</h2>
<p style="color:#999">Switch to the open SeekSync window.</p></div></body></html>"""


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


SHUTDOWN_GRACE = 12      # seconds the app may take to quit before it is ended by force


def _force_exit_later(seconds: float = SHUTDOWN_GRACE) -> None:
    """Safety net for closing the app. A download check or a connection that is still busy can keep the process
    alive without a window; it then holds the "already running" lock and the next start fails. This timer ends
    the process when quitting takes too long. It is a daemon thread, so it does nothing when the quit is quick."""
    def kill():
        time.sleep(seconds)
        logging.getLogger("seeksync").warning("quitting took more than %d s, ending the process", seconds)
        logging.shutdown()
        os._exit(0)
    threading.Thread(target=kill, name="force-exit", daemon=True).start()


def webview_unavailable() -> str:
    """Why the app window can't be used (a reason), or "" when it can. On Windows without the Edge WebView2
    runtime, pywebview silently falls back to Internet Explorer's engine, and the interface doesn't work there:
    then it is better to show it in the browser."""
    if not sys.platform.startswith("win"):
        return ""
    try:
        from webview.platforms import winforms
        if not winforms.is_chromium:
            return "the Microsoft Edge WebView2 runtime is not installed"
    except Exception as e:      # can't tell: try the window like before
        logging.getLogger("seeksync").debug("couldn't check WebView2: %s", e)
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seeksync")
    ap.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of an app window")
    ap.add_argument("--headless", action="store_true", help="run without any UI (prints the UI address)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = ap.parse_args(argv)

    setup_logging(args.verbose)
    diag.install(log_dir())
    logging.getLogger("seeksync").info("%s %s starting (%s, Python %s)", APP_NAME, __version__, sys.platform,
                                       sys.version.split()[0])
    lock = acquire_instance_lock()
    if lock is None:
        if args.headless or args.browser:   # no window wanted: just say so
            print("SeekSync is already running.", file=sys.stderr)
            return 1
        try:
            import webview
            webview.create_window(APP_NAME, html=ALREADY_RUNNING_HTML, width=460, height=220)
            webview.start()
        except Exception:
            print("SeekSync is already running.", file=sys.stderr)
        return 1

    try:   # first start after a rename: take over the old data folder
        migrate_legacy_data()
    except OSError:
        logging.getLogger("seeksync").exception("couldn't move the old data folder")

    backend = Backend(port=args.port)
    url = backend.start()

    def on_term(signum, frame):   # `kill` / logout: shut down like Ctrl+C so transfers get cleaned up
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError):
        pass

    log = logging.getLogger("seeksync")
    use_window = not (args.browser or args.headless)
    if use_window:
        try:
            import webview
        except Exception:
            use_window = False
    if use_window:
        reason = webview_unavailable()
        if reason:
            log.warning("no app window, the interface opens in your browser instead: %s", reason)
            use_window = False

    def run_in_browser() -> None:
        backend.on_quit = lambda: os.kill(os.getpid(), signal.SIGTERM)
        print(f"{APP_NAME} is running at {url}", flush=True)
        if not args.headless:
            webbrowser.open(url)
        while True:
            time.sleep(3600)

    try:
        if use_window:
            api = JsApi()
            window = webview.create_window(APP_NAME, url, js_api=api, width=1200, height=800,
                                           min_size=(860, 560), background_color="#0f0f10")
            api.window = window
            backend.on_quit = window.destroy          # the update button closes the app this way
            try:
                webview.start()
            except Exception:
                log.exception("the app window failed, the interface opens in your browser instead")
                run_in_browser()
        else:
            run_in_browser()
    except KeyboardInterrupt:
        pass
    finally:
        _force_exit_later()
        backend.stop()
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
