"""Zoom/pan image canvas that separates SOURCE resolution from DISPLAY scale.

Very large sources are shown through a reduced display pixmap (integer
reduction), which is a visualisation choice only. Pixel coordinates reported
by hovering always refer to the full-resolution source.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from app.core.image_loader import canonical_image
from app.ui.theme import C

DISPLAY_MAX_PIXELS = 36_000_000


def display_image(img: Image.Image) -> tuple[Image.Image, int]:
    """8-bit L/RGB/RGBA preview of the source plus the integer reduction factor."""
    canon = canonical_image(img)
    if canon.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        arr = np.asarray(canon, dtype=np.float64)
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) * (255.0 / (hi - lo)) if hi > lo else arr * 0
        canon = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    elif canon.mode not in ("L", "RGB", "RGBA"):
        canon = canon.convert("RGBA" if "A" in canon.mode else "RGB")
    w, h = canon.size
    factor = max(1, math.ceil(math.sqrt(w * h / DISPLAY_MAX_PIXELS))) if w * h > DISPLAY_MAX_PIXELS else 1
    if factor > 1:
        canon = canon.reduce(factor)
    return canon, factor


def to_qimage(img: Image.Image) -> QImage:
    if img.mode not in ("L", "RGB", "RGBA"):
        img = img.convert("RGBA")
    w, h = img.size
    fmt = {"L": QImage.Format.Format_Grayscale8, "RGB": QImage.Format.Format_RGB888,
           "RGBA": QImage.Format.Format_RGBA8888}[img.mode]
    bpl = w * {"L": 1, "RGB": 3, "RGBA": 4}[img.mode]
    data = img.tobytes()
    return QImage(data, w, h, bpl, fmt).copy()


def array_to_image(arr: np.ndarray) -> Image.Image:
    arr = np.ascontiguousarray(arr)
    return Image.fromarray(arr.astype(np.uint8))


class ImageCanvas(QGraphicsView):
    hovered = Signal(int, int)
    viewChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._scene.addItem(self._item)
        self.factor = 1
        self.source_size = (0, 0)
        self._sync: list[ImageCanvas] = []
        self._syncing = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor("#0A0E12")))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 160)
        self.horizontalScrollBar().valueChanged.connect(self._emit_view)
        self.verticalScrollBar().valueChanged.connect(self._emit_view)

    # ---- content
    def set_pil(self, img: Image.Image | None, fit: bool = False) -> None:
        if img is None:
            self.clear_image()
            return
        disp, factor = display_image(img)
        self.set_display(disp, img.size, factor, fit)

    def set_display(self, disp: Image.Image, source_size: tuple[int, int], factor: int, fit: bool = False) -> None:
        first = self._item.pixmap().isNull()
        self._item.setPixmap(QPixmap.fromImage(to_qimage(disp)))
        self._scene.setSceneRect(self._item.boundingRect())
        self.source_size, self.factor = tuple(source_size), int(factor)
        if fit or first:
            self.fit()

    def clear_image(self) -> None:
        self._item.setPixmap(QPixmap())
        self.source_size, self.factor = (0, 0), 1

    # ---- zoom
    def zoom_percent(self) -> float:
        return self.transform().m11() / self.factor * 100.0 if self.factor else 0.0

    def set_zoom(self, source_scale: float) -> None:
        s = max(0.002, min(256.0, source_scale * self.factor))
        self.setTransform(QTransform.fromScale(s, s))
        self._emit_view()

    def fit(self) -> None:
        if not self._item.pixmap().isNull():
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
            self._emit_view()

    def hundred(self) -> None:
        self.set_zoom(1.0)

    def actual_size(self) -> None:
        """One source pixel per physical device pixel (accounts for display scaling)."""
        self.set_zoom(1.0 / max(self.devicePixelRatioF(), 1e-6))

    def zoom_by(self, k: float) -> None:
        self.scale(k, k)
        self._emit_view()

    def wheelEvent(self, event) -> None:  # noqa: N802
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(1.2 ** steps)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        p = self.mapToScene(event.position().toPoint())
        x, y = int(p.x() * self.factor), int(p.y() * self.factor)
        w, h = self.source_size
        self.hovered.emit(x, y) if 0 <= x < w and 0 <= y < h else self.hovered.emit(-1, -1)

    def status_text(self) -> str:
        w, h = self.source_size
        if not w:
            return "no image"
        extra = f" | preview 1/{self.factor} (display only)" if self.factor > 1 else ""
        return f"SOURCE {w}x{h} | DISPLAY {self.zoom_percent():.1f}%{extra}"

    # ---- synchronisation
    def link(self, other: "ImageCanvas") -> None:
        if other not in self._sync:
            self._sync.append(other)
            other.link(self)

    def _emit_view(self, *_a) -> None:
        self.viewChanged.emit()
        if self._syncing:
            return
        for o in self._sync:
            o._syncing = True
            try:
                o.setTransform(self.transform())
                o.horizontalScrollBar().setValue(self.horizontalScrollBar().value())
                o.verticalScrollBar().setValue(self.verticalScrollBar().value())
                o.viewChanged.emit()
            finally:
                o._syncing = False
