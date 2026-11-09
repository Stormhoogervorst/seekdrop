# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller packaging/seeksync.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))
src = os.path.join(root, "src")
sys.path.insert(0, src)
from seeksync import __version__  # noqa: E402

datas = [
    (os.path.join(src, "seeksync", "ui"), os.path.join("seeksync", "ui")),
    (os.path.join(src, "seeksync", "nicotine_plugin"), os.path.join("seeksync", "nicotine_plugin")),
]
binaries = []
hiddenimports = collect_submodules("aioslsk") + collect_submodules("mutagen") + collect_submodules("anyascii") + [
    m for m in collect_submodules("seeksync") if "nicotine_plugin" not in m  # plugin runs inside Nicotine+
]
for pkg in ("curl_cffi", "anyascii"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [os.path.join(root, "packaging", "launch.py")],
    pathex=[src],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "PIL", "pytest", "playwright"],   # numpy is used (spectrum check)
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SeekSync",
    console=False,
    icon=os.path.join(root, "packaging", "icon.icns" if sys.platform == "darwin" else "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="SeekSync")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SeekSync.app",
        icon=os.path.join(root, "packaging", "icon.icns"),
        bundle_identifier="app.seeksync",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleName": "SeekSync",
            "CFBundleDisplayName": "SeekSync",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
