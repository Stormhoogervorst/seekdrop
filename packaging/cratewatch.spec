# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller packaging/cratewatch.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))
src = os.path.join(root, "src")
sys.path.insert(0, src)
from cratewatch import __version__  # noqa: E402

datas = [
    (os.path.join(src, "cratewatch", "ui"), os.path.join("cratewatch", "ui")),
    (os.path.join(src, "cratewatch", "nicotine_plugin"), os.path.join("cratewatch", "nicotine_plugin")),
]
binaries = []
hiddenimports = collect_submodules("aioslsk") + [
    m for m in collect_submodules("cratewatch") if "nicotine_plugin" not in m  # plugin runs inside Nicotine+
]
for pkg in ("curl_cffi",):
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
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cratewatch",
    console=False,
    icon=os.path.join(root, "packaging", "icon.icns" if sys.platform == "darwin" else "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Cratewatch")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Cratewatch.app",
        icon=os.path.join(root, "packaging", "icon.icns"),
        bundle_identifier="app.cratewatch",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
