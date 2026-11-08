# Nicotine+ Sync Bridge: a Nicotine+ plugin that lets the Nicotine+ Sync app search and
# download through Nicotine+ (your own Soulseek account).
#
# GNU GENERAL PUBLIC LICENSE, Version 3 or later.
#
# It opens a small HTTP API on 127.0.0.1 only. Every request must carry the
# X-Token header with the key from bridge.json (written by Nicotine+ Sync when it
# installed this plugin). Nicotine+ objects are only touched on Nicotine+'s
# main thread.

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pynicotine.core import core
from pynicotine.events import events
from pynicotine.pluginsystem import BasePlugin

API_VERSION = 1
MAX_RESULTS_PER_SEARCH = 3000
MAX_SEARCH_WAIT = 30


class Plugin(BasePlugin):

    def init(self):
        self.lock = threading.Lock()
        self.searches = {}      # token -> list of results
        self.finished = {}      # username + virtual_path -> real path on disk
        self.server = None
        self.hooked = False

        cfg = self._read_config()
        self.key = cfg.get("token") or ""
        self.port = int(cfg.get("port") or 47820)
        if not self.key:
            self.log("no key found. Install the plugin from Nicotine+ Sync's settings.")
            return

        # Search results for our searches are dropped by Nicotine+ itself (they belong to no
        # search tab), so we must see them first: put our callback at the front.
        try:
            events._callbacks["file-search-response"].insert(0, self._on_search_response)  # noqa: SLF001
        except Exception:
            events.connect("file-search-response", self._on_search_response)
        self.hooked = True
        self._start_server()

    # ---------------------------------------------------------------- lifecycle
    def _read_config(self):
        try:
            with open(os.path.join(self.path, "bridge.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _start_server(self):
        plugin = self

        class Handler(_Handler):
            bridge = plugin

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as error:
            self.log("can't listen on port %s (%s)", (self.port, error))
            return
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="nicotine-sync-bridge", daemon=True).start()
        self.log("ready for Nicotine+ Sync on 127.0.0.1:%s", (self.port,))

    def _stop(self):
        if self.server is not None:
            server, self.server = self.server, None
            threading.Thread(target=server.shutdown, daemon=True).start()
        if self.hooked:
            try:
                events.disconnect("file-search-response", self._on_search_response)
            except Exception:
                pass
            self.hooked = False

    def disable(self):
        self._stop()

    def shutdown_notification(self):
        self._stop()

    def download_finished_notification(self, user, virtual_path, real_path):
        with self.lock:
            self.finished[user + virtual_path] = real_path

    # ---------------------------------------------------------------- main-thread helper
    @staticmethod
    def call(func, *args, timeout=10, **kwargs):
        done = threading.Event()
        box = {}

        def run():
            try:
                box["value"] = func(*args, **kwargs)
            except Exception as error:  # passed back to the HTTP thread
                box["error"] = error
            finally:
                done.set()

        events.invoke_main_thread(run)
        if not done.wait(timeout):
            raise TimeoutError("Nicotine+ didn't respond in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    # ---------------------------------------------------------------- operations (main thread)
    @staticmethod
    def _status():
        from pynicotine.slskmessages import UserStatus
        users = core.users
        return {
            "api": API_VERSION,
            "logged_in": users.login_status != UserStatus.OFFLINE,
            "username": users.login_username or "",
        }

    def _start_search(self, query):
        from pynicotine.slskmessages import FileSearch, increment_token

        search = core.search
        _sanitized, transmitted, _included, _excluded = search.sanitize_search_term(query)
        search.token = increment_token(search.token)
        token = search.token
        with self.lock:
            self.searches[token] = []
        search.add_allowed_token(token)
        core.send_message_to_server(FileSearch(token, transmitted))
        return token

    @staticmethod
    def _end_search(token):
        core.search.remove_allowed_token(token)

    def _on_search_response(self, msg):
        token = getattr(msg, "token", None)
        if token is None or msg.list is None:
            return
        with self.lock:
            bucket = self.searches.get(token)
            if bucket is None or len(bucket) >= MAX_RESULTS_PER_SEARCH:
                return
        username = msg.username
        try:
            if core.network_filter.is_user_ignored(username):
                return
        except Exception:
            pass
        rows = []
        for _code, path, size, ext, attrs in msg.list:
            attrs = attrs or {}
            rows.append({
                "username": username,
                "path": path,
                "size": size,
                "ext": ext or "",
                "bitrate": attrs.get(0),
                "duration": attrs.get(1),
                "free_slots": bool(msg.freeulslots),
                "speed": msg.ulspeed or 0,
                "queue": msg.inqueue or 0,
            })
        with self.lock:
            bucket = self.searches.get(token)
            if bucket is not None:
                bucket.extend(rows)

    @staticmethod
    def _download(username, path, size, folder):
        core.downloads.enqueue_download(username, path, folder_path=folder or None, size=size or 0)
        return True

    def _transfer(self, username, path):
        t = core.downloads.transfers.get(username + path)
        with self.lock:
            done_path = self.finished.get(username + path)
        if t is None:
            return {"status": "Finished" if done_path else "Missing", "local_path": done_path}
        return {
            "status": t.status,
            "size": t.size or 0,
            "bytes": t.current_byte_offset or 0,
            "queue_position": t.queue_position or 0,
            "local_path": done_path,
        }

    def _abort(self, username, path, clear):
        from pynicotine.transfers import TransferStatus
        t = core.downloads.transfers.get(username + path)
        if t is None:
            return False
        if t.status != TransferStatus.FINISHED:
            core.downloads.abort_downloads([t], status=TransferStatus.CANCELLED)
        if clear:
            core.downloads.clear_downloads([t])
        with self.lock:
            self.finished.pop(username + path, None)
        return True

    # ---------------------------------------------------------------- HTTP-thread entry points
    def http_search(self, query, wait):
        token = self.call(self._start_search, query)
        try:
            time.sleep(max(1.0, min(float(wait), MAX_SEARCH_WAIT)))
        finally:
            try:
                self.call(self._end_search, token)
            except Exception:
                pass
            with self.lock:
                results = self.searches.pop(token, [])
        return results


class _Handler(BaseHTTPRequestHandler):
    bridge = None
    server_version = "NicotineSyncBridge/1"

    def log_message(self, *_args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        return secrets.compare_digest(self.headers.get("X-Token", ""), self.bridge.key)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 100_000:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def do_GET(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/status":
                return self._send(200, self.bridge.call(self.bridge._status))
            if url.path == "/transfer":
                return self._send(200, self.bridge.call(self.bridge._transfer, q.get("username", ""), q.get("path", "")))
        except Exception as error:
            return self._send(500, {"error": str(error)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        path = urlparse(self.path).path
        data = self._body()
        b = self.bridge
        try:
            if path == "/search":
                query = str(data.get("query") or "").strip()
                if not query:
                    return self._send(400, {"error": "empty query"})
                return self._send(200, {"results": b.http_search(query, data.get("wait", 12))})
            if path == "/download":
                b.call(b._download, data["username"], data["path"], int(data.get("size") or 0), data.get("folder"))
                return self._send(200, {"ok": True})
            if path == "/abort":
                ok = b.call(b._abort, data["username"], data["path"], bool(data.get("clear", True)))
                return self._send(200, {"ok": ok})
        except KeyError as error:
            return self._send(400, {"error": f"missing {error}"})
        except Exception as error:
            return self._send(500, {"error": str(error)})
        return self._send(404, {"error": "not found"})
