"""Load the SeekDrop Bridge plugin into a headless Nicotine+ core (no network) and
exercise it through SeekDrop's NicotineBridge client.

    PYTHONPATH=src:/path/to/nicotine-plus python tests/manual/nicotine_harness.py
"""
import asyncio
import os
import sys
import tempfile
import threading
import time

tmp = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")

from pynicotine.core import core            # noqa: E402
from pynicotine.events import events        # noqa: E402
from pynicotine import slskmessages         # noqa: E402

from seekdrop.config import Settings      # noqa: E402
from seekdrop.nicotine import NicotineBridge, install_plugin, new_token  # noqa: E402

PORT = 47899
token = new_token()
plugin_dir = install_plugin(PORT, token)
print("plugin installed at", plugin_dir)

core.init_components(enabled_components={"users", "network_filter", "shares", "search", "downloads",
                                         "uploads", "pluginhandler", "buddies", "userbrowse"})
core.start()
core.users.login_status = slskmessages.UserStatus.ONLINE
core.users.login_username = "nina_test"

sent = []
type(core).send_message_to_server = lambda self, msg: sent.append(msg)

assert core.pluginhandler.enable_plugin("seekdrop_bridge"), "plugin failed to load"


def main_loop():
    while True:
        events.process_thread_events()
        time.sleep(0.02)


threading.Thread(target=main_loop, daemon=True).start()


def fake_peer_reply(after):
    time.sleep(after)
    search_msgs = [m for m in sent if isinstance(m, slskmessages.FileSearch)]
    tok = search_msgs[-1].token
    msg = slskmessages.FileSearchResponse()
    msg.token = tok
    msg.username = "peer1"
    msg.addr = ("1.2.3.4", 2234)
    msg.list = [(1, "@@music\\Fresh Artist\\Fresh Artist - Brand New.flac", 31_000_000, "", {1: 301}),
                (1, "@@music\\Fresh Artist\\Fresh Artist - Brand New.mp3", 9_000_000, "", {0: 320, 1: 301})]
    msg.freeulslots, msg.ulspeed, msg.inqueue, msg.privatelist = True, 2_000_000, 0, []
    events.emit_main_thread("file-search-response", msg)


async def run():
    s = Settings(soulseek_mode="nicotine", nicotine_port=PORT, nicotine_token=token)
    bridge = NicotineBridge(os.path.join(tmp, "incoming"))
    await bridge.start(s)
    print("status:", bridge.status, bridge.username, bridge.error)
    assert bridge.connected
    # Step 8: the plugin reports how many folders Nicotine+ shares (None = it can't tell).
    from pynicotine.config import config
    print("shared folders:", bridge.shared_folders)
    assert bridge.shared_folders == 0
    config.sections["transfers"]["shared"] = [("Music", tmp)]
    await bridge._check()
    assert bridge.shared_folders == 1, bridge.shared_folders
    config.sections["transfers"]["shared"] = []

    threading.Thread(target=fake_peer_reply, args=(1.0,), daemon=True).start()
    results = await bridge.search("fresh artist brand new", wait=2)
    print("search sent to server:", [(m.token, m.searchterm) for m in sent if isinstance(m, slskmessages.FileSearch)])
    print("results:", [(c.username, c.filename, c.bitrate, c.duration, c.has_free_slots) for c in results])
    assert len(results) == 2
    assert not core.search.searches, "our search must not create a Nicotine+ search tab"

    h = await bridge.download("peer1", results[0].filename)
    await asyncio.sleep(0.5)
    t = core.downloads.transfers.get("peer1" + results[0].filename)
    print("nicotine transfer:", t.status if t else None, t.folder_path if t else None)
    print("seekdrop view:", bridge.transfer_info(h))
    assert t is not None and t.folder_path == os.path.join(tmp, "incoming")

    # pretend Nicotine+ finished it
    real = os.path.join(tmp, "incoming", "Fresh Artist - Brand New.flac")
    open(real, "wb").write(b"x")

    def finish():
        t.status = "Finished"
        core.pluginhandler.download_finished_notification("peer1", t.virtual_path, real)
    events.invoke_main_thread(finish)
    await asyncio.sleep(2.5)
    info = bridge.transfer_info(h)
    print("after finish:", info)
    assert info["state"] == "COMPLETE" and info["local_path"] == real

    # wrong key is rejected
    bad = NicotineBridge(tmp)
    await bad.start(Settings(soulseek_mode="nicotine", nicotine_port=PORT, nicotine_token="nope"))
    print("bad key:", bad.status, "|", bad.error)
    assert bad.status == "error"
    await bad.stop()

    # nothing listening
    off = NicotineBridge(tmp)
    await off.start(Settings(soulseek_mode="nicotine", nicotine_port=PORT + 1, nicotine_token=token))
    print("not running:", off.status, "|", off.error)
    await off.stop()

    # logged out of Soulseek
    core.users.login_status = slskmessages.UserStatus.OFFLINE
    await bridge._check()
    print("offline:", bridge.status, "|", bridge.error)
    await bridge.forget(h)
    await bridge.stop()

    core.pluginhandler.disable_plugin("seekdrop_bridge")
    await asyncio.sleep(0.5)
    print("ALL GOOD")


try:
    asyncio.run(run())
except BaseException:
    import traceback
    traceback.print_exc()
    os._exit(1)
os._exit(0)
