"""Premium splash screen with a real initialisation sequence.

Each step runs an actual check and reports its true outcome; no progress value is
faked. The splash closes when the sequence finishes (or immediately in quiet mode).
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from app import __classification__, __subtitle__, __version__
from app.ui.theme import C

STEPS = [
    ("Loading image engine", "image_engine"),
    ("Loading C2PA engine", "c2pa_engine"),
    ("Loading fingerprint taxonomy", "taxonomy"),
    ("Loading research library", "library"),
    ("Loading local research modules", "research"),
    ("Checking GPU", "gpu"),
    ("Checking external tools", "tools"),
    ("Checking experiment workspace", "workspace"),
]


def _check(key: str, ctl) -> str:
    if key == "image_engine":
        from app.core.image_loader import open_image_bytes  # noqa: F401
        from app.core.synthetic import make_png
        open_image_bytes(make_png(size=(16, 16)))
        return "Pillow + numpy OK"
    if key == "c2pa_engine":
        from app.analyzers import c2pa_analyzer  # noqa: F401
        from app.core import cbor, jumbf  # noqa: F401
        return "native JUMBF/CBOR parser ready"
    if key == "taxonomy":
        from app.research import taxonomy as T
        n = len(T.load().get("entries", []))
        return f"{n} terminology entries"
    if key == "library":
        from app.research import library as L
        return f"{len(L.all_items())} verified references"
    if key == "research":
        from app.research.methods import MethodRegistry
        r = MethodRegistry()
        return f"{len(r.ready())}/{len(r.all())} methods ready"
    if key == "gpu":
        from app.core.synthid_research_engine import gpu_info
        g = gpu_info()
        return (g.get("gpu") or "none")[:48]
    if key == "tools":
        if ctl is None:
            return "optional tools not probed"
        avail = [t.name for t in (ctl.exiftool, ctl.c2patool, ctl.c2pa_python) if t.available]
        return ", ".join(avail) if avail else "none (all optional)"
    if key == "workspace":
        if ctl is None:
            return "default workspace"
        return str(ctl.workspace.root)
    return "ok"


class Splash(QSplashScreen):
    def __init__(self) -> None:
        pm = QPixmap(640, 380)
        pm.fill(QColor(C["base"]))
        super().__init__(pm)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._status = "Starting..."
        self._paint_base()

    def _paint_base(self) -> None:
        pm = self.pixmap()
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(pm.rect(), QColor(C["base"]))
        p.setPen(QColor(C["line"]))
        p.drawRect(8, 8, pm.width() - 17, pm.height() - 17)
        p.setPen(QColor(C["cyan"]))
        f = QFont("Segoe UI", 30, QFont.Weight.Light)
        p.setFont(f)
        p.drawText(40, 90, "SynthProvenance")
        p.setPen(QColor(C["text"]))
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(42, 120, __subtitle__)
        p.setPen(QColor(C["muted"]))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(42, 150, "Insyide Innovations Lab  ·  NuRichter Workspace")
        p.drawText(42, 168, f"{__classification__}  ·  v{__version__}")
        p.setPen(QColor(C["line"]))
        p.drawLine(40, 184, pm.width() - 40, 184)
        p.end()
        self.setPixmap(pm)

    def drawContents(self, painter: QPainter) -> None:  # noqa: N802
        painter.setPen(QColor(C["muted"]))
        painter.setFont(QFont("Cascadia Mono", 9))
        painter.drawText(42, 360, self._status)

    def set_status(self, text: str) -> None:
        self._status = text
        self.repaint()

    def run_sequence(self, app: QApplication, ctl=None) -> None:
        for label, key in STEPS:
            self.set_status(f"{label} ...")
            app.processEvents()
            t0 = time.perf_counter()
            try:
                detail = _check(key, ctl)
                ok = "✓"
            except Exception as exc:  # noqa: BLE001 - a failed check is shown, never hidden
                detail, ok = f"{type(exc).__name__}: {exc}", "✕"
            self.set_status(f"{ok} {label}: {detail}  ({(time.perf_counter() - t0) * 1000:.0f} ms)")
            app.processEvents()
        self.set_status("Ready.")
        app.processEvents()
