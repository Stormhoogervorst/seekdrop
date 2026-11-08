"""Local web API + UI, bound to 127.0.0.1 and protected by a per-launch token."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from aiohttp import web

from . import __version__
from .db import Database
from .engine import Engine
from .nicotine import install_plugin, new_token, nicotine_plugins_dir, plugin_installed
from .soundcloud import ChannelError, is_playlist_url, normalize_channel_url

log = logging.getLogger(__name__)
UI_DIR = Path(__file__).parent / "ui"


def open_in_file_manager(path: str) -> None:
    if not path:
        return
    target = path if os.path.isdir(path) else os.path.dirname(path)
    if sys.platform == "darwin":
        args = ["open", "-R", path] if os.path.isfile(path) else ["open", target]
    elif sys.platform.startswith("win"):
        args = ["explorer", "/select,", path] if os.path.isfile(path) else ["explorer", target]
    else:
        args = ["xdg-open", target]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Api:
    def __init__(self, engine: Engine, db: Database, token: str | None = None, updates=None):
        self.engine = engine
        self.db = db
        self.updates = updates
        self.token = token or secrets.token_urlsafe(24)

    # -- helpers
    @web.middleware
    async def auth(self, request: web.Request, handler):
        if request.path.startswith("/api/"):
            if not secrets.compare_digest(request.headers.get("X-Token", ""), self.token):
                return web.json_response({"error": "unauthorized"}, status=401)
        resp = await handler(request)
        if request.path.startswith("/ui/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    @staticmethod
    async def body(request: web.Request) -> dict:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.auth])
        r = app.router
        r.add_get("/", self.index)
        r.add_static("/ui/", UI_DIR)
        r.add_get("/api/state", self.state)
        r.add_put("/api/settings", self.put_settings)
        r.add_post("/api/channels", self.add_channel)
        r.add_patch("/api/channels/{id}", self.patch_channel)
        r.add_delete("/api/channels/{id}", self.delete_channel)
        r.add_post("/api/channels/{id}/check", self.check_channel)
        r.add_post("/api/check-now", self.check_now)
        r.add_post("/api/tracks/{id}/retry", self.retry_track)
        r.add_post("/api/tracks/{id}/skip", self.skip_track)
        r.add_post("/api/rejects/{id}/approve", self.approve_reject)
        r.add_post("/api/rejects/{id}/delete", self.delete_reject)
        r.add_post("/api/open", self.open_path)
        r.add_post("/api/nicotine/install", self.install_nicotine)
        return app

    # -- routes
    async def index(self, request: web.Request):
        html = (UI_DIR / "index.html").read_text("utf-8")
        return web.Response(text=html, content_type="text/html",
                            headers={"Cache-Control": "no-store"})

    async def state(self, request: web.Request):
        e = self.engine
        channel_id = request.query.get("channel")
        tracks = self.db.tracks(limit=400, channel_id=int(channel_id) if channel_id else None)
        now = time.time()
        for t in tracks:
            entry = e.active.get(t["id"])
            if entry and entry.get("transfer") is not None:
                info = e.slsk.transfer_info(entry["transfer"])
                t["transfer_state"] = info["state"]
                t["place_in_queue"] = info["place_in_queue"]
            t["retry_in"] = max(0, int(t["next_attempt"] - now)) if t["state"] == "waiting" else None
        channels = self.db.channels()
        for c in channels:
            c["checking"] = c["id"] in e.checking
        return web.json_response({
            "version": __version__,
            "update": (self.updates.latest if self.updates and e.settings.check_updates else None),
            "settings": e.settings.public(),
            "soulseek": {"status": e.slsk.status, "error": e.slsk.error,
                         "username": getattr(e.slsk, "username", "") or e.settings.soulseek_username},
            "nicotine": {"plugin_installed": plugin_installed(), "plugins_dir": str(nicotine_plugins_dir())},
            "channels": channels,
            "tracks": tracks,
            "rejects": self.db.quarantined(),
            "checks": {"available": bool(e.file_checker and e.file_checker.tools.available)},
            "stats": self.db.stats(),
            "activity": list(e.activity)[:30],
            "next_check_in": max(0, int(e.next_poll_at - now)) if e.next_poll_at else 0,
        })

    async def put_settings(self, request: web.Request):
        data = await self.body(request)
        if "download_dir" in data and str(data["download_dir"]).strip():
            d = os.path.expanduser(str(data["download_dir"]).strip())
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as ex:
                return web.json_response({"error": f"Can't use that folder: {ex.strerror}"}, status=400)
            data["download_dir"] = os.path.abspath(d)
        _, changed = self.engine.store.update(data)
        if changed:
            asyncio.create_task(self.engine.apply_settings(changed))
        return web.json_response({"ok": True, "changed": sorted(changed)})

    async def install_nicotine(self, request: web.Request):
        store = self.engine.store
        token = store.settings.nicotine_token or new_token()
        try:
            path = await asyncio.to_thread(install_plugin, store.settings.nicotine_port, token)
        except OSError as ex:
            return web.json_response({"error": f"Couldn't install the plugin: {ex.strerror or ex}"}, status=500)
        _, changed = store.update({"nicotine_token": token, "soulseek_mode": "nicotine"})
        if changed and store.settings.configured:
            asyncio.create_task(self.engine.apply_settings(changed))
        self.engine.note("Installed the SeekDrop Bridge plugin for Nicotine+.")
        return web.json_response({"ok": True, "path": str(path)})

    async def add_channel(self, request: web.Request):
        data = await self.body(request)
        try:
            url = normalize_channel_url(data.get("url", ""))
        except ChannelError as ex:
            return web.json_response({"error": str(ex)}, status=400)
        if self.db.channel_by_url(url):
            what = "playlist" if is_playlist_url(url) else "channel"
            return web.json_response({"error": f"You're already watching this {what}."}, status=400)
        try:
            info = await asyncio.to_thread(self.engine.sc.channel_info, url)
        except ChannelError as ex:
            return web.json_response({"error": str(ex)}, status=400)
        backlog = max(0, min(int(data.get("backlog") or 0), 50))
        reposts = bool(data.get("include_reposts")) and info.kind == "profile"
        cid = self.db.add_channel(info.url, info.name, reposts, backlog, kind=info.kind)
        self.engine.note(f"Added {'playlist' if info.kind == 'playlist' else 'channel'} {info.name}.")
        asyncio.create_task(self.engine.check_channel(cid))
        return web.json_response({"ok": True, "id": cid, "name": info.name, "kind": info.kind})

    async def patch_channel(self, request: web.Request):
        cid = int(request.match_info["id"])
        data = await self.body(request)
        fields = {}
        if "enabled" in data:
            fields["enabled"] = int(bool(data["enabled"]))
        if "include_reposts" in data:
            fields["include_reposts"] = int(bool(data["include_reposts"]))
        self.db.update_channel(cid, **fields)
        return web.json_response({"ok": True})

    async def delete_channel(self, request: web.Request):
        self.engine.remove_channel(int(request.match_info["id"]))
        return web.json_response({"ok": True})

    async def check_channel(self, request: web.Request):
        asyncio.create_task(self.engine.check_channel(int(request.match_info["id"])))
        return web.json_response({"ok": True})

    async def check_now(self, request: web.Request):
        self.engine.wake(poll=True)
        return web.json_response({"ok": True})

    async def retry_track(self, request: web.Request):
        self.engine.retry_now(int(request.match_info["id"]))
        return web.json_response({"ok": True})

    async def skip_track(self, request: web.Request):
        self.engine.skip(int(request.match_info["id"]))
        return web.json_response({"ok": True})

    async def approve_reject(self, request: web.Request):
        path = self.engine.approve_reject(int(request.match_info["id"]))
        if not path:
            return web.json_response({"error": "That file is no longer in quarantine."}, status=404)
        return web.json_response({"ok": True, "path": path})

    async def delete_reject(self, request: web.Request):
        self.engine.delete_reject(int(request.match_info["id"]))
        return web.json_response({"ok": True})

    async def open_path(self, request: web.Request):
        data = await self.body(request)
        path = ""
        if data.get("track"):
            t = self.db.track(int(data["track"]))
            path = t["file_path"] if t else ""
        else:
            path = self.engine.settings.download_dir
            os.makedirs(path, exist_ok=True)
        if path and os.path.exists(path):
            open_in_file_manager(path)
            return web.json_response({"ok": True})
        return web.json_response({"error": "File not found. Was it moved?"}, status=404)
