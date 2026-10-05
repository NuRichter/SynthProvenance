# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SynthProvenance (one-folder, windowed). Build via build.bat.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
IS_WIN = sys.platform.startswith("win")

hiddenimports = (collect_submodules("app") + collect_submodules("reportlab.pdfbase")
                 + collect_submodules("reportlab.graphics.barcode") + ["blake3"])

# Explicit Qt plugin collection (in addition to the PySide6 hook) so the platform,
# image-format, style and icon-engine plugins are always present in the build.
from PySide6.QtCore import QLibraryInfo  # noqa: E402

plugin_root = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
qt_plugins = []
for cat in ("platforms", "imageformats", "styles", "iconengines"):
    d = plugin_root / cat
    if not d.is_dir():
        continue
    for f in d.iterdir():
        if f.suffix.lower() not in (".dll", ".so", ".dylib"):
            continue
        if not IS_WIN and cat == "platforms" and not any(k in f.name for k in ("offscreen", "minimal", "xcb")):
            continue
        qt_plugins.append((str(f), f"PySide6/Qt/plugins/{cat}" if not IS_WIN else f"PySide6/plugins/{cat}"))

datas = [(str(ROOT / "assets"), "assets"), (str(ROOT / "config"), "config"), (str(ROOT / "data"), "data"),
         (str(ROOT / "app" / "i18n" / "locales"), "app/i18n/locales")]

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=qt_plugins,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "_tkinter", "pytest", "_pytest", "IPython", "matplotlib", "PySide6.QtWebEngineCore",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SynthProvenance",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icon.ico"),
    version=str(ROOT / "assets" / "version_info.txt") if IS_WIN else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SynthProvenance")
