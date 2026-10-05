from __future__ import annotations

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QSlider, QSpinBox

from app.core.pixel_integrity import difference_map
from app.ui.views.base import View, fill_conditions, row
from app.ui.widgets.common import button, label
from app.ui.widgets.image_canvas import ImageCanvas, display_image

MODES = ["Side-by-Side", "Overlay", "Blink", "Difference", "Heatmap"]


def heat_lut() -> np.ndarray:
    x = np.linspace(0, 1, 256)
    stops = np.array([[0, 0, 0], [20, 40, 140], [40, 180, 220], [240, 210, 60], [230, 60, 50]], dtype=np.float64)
    pos = np.linspace(0, 1, len(stops))
    return np.stack([np.interp(x, pos, stops[:, c]) for c in range(3)], axis=1).astype(np.uint8)


LUT = heat_lut()


class ComparisonView(View):
    title = "Comparison"
    subtitle = "Zoom and pan are synchronised. Coordinates and values always refer to full-resolution source pixels."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        self.a, self.b = QComboBox(), QComboBox()
        for c in (self.a, self.b):
            c.currentIndexChanged.connect(self._load)
        self.mode_btns = []
        grp = QButtonGroup(self)
        for m in MODES:
            b = button(m, checkable=True)
            b.clicked.connect(self._render)
            grp.addButton(b)
            self.mode_btns.append(b)
        self.mode_btns[0].setChecked(True)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(50)
        self.opacity.setMaximumWidth(120)
        self.opacity.valueChanged.connect(self._render)
        self.amp = QSpinBox()
        self.amp.setRange(1, 64)
        self.amp.setValue(8)
        self.amp.setPrefix("x")
        self.amp.valueChanged.connect(self._render)
        self.root.addLayout(row(label("A"), self.a, label("B"), self.b, None, *self.mode_btns))
        z = [button(t) for t in ("Fit", "100%", "Actual Size", "+", "\u2212")]
        z[0].clicked.connect(lambda: self._each(lambda c: c.fit()))
        z[1].clicked.connect(lambda: self._each(lambda c: c.hundred()))
        z[2].clicked.connect(lambda: self._each(lambda c: c.actual_size()))
        z[3].clicked.connect(lambda: self._each(lambda c: c.zoom_by(1.25)))
        z[4].clicked.connect(lambda: self._each(lambda c: c.zoom_by(0.8)))
        self.root.addLayout(row(*z, label("Overlay opacity"), self.opacity, label("Difference gain"), self.amp, None))
        canv = QHBoxLayout()
        self.left, self.right = ImageCanvas(), ImageCanvas()
        self.left.link(self.right)
        for c in (self.left, self.right):
            c.hovered.connect(self._hover)
            c.viewChanged.connect(self._scale_text)
            canv.addWidget(c, 1)
        self.root.addLayout(canv, 1)
        self.px = label("X -   Y -   Original RGB -   Output RGB -   Difference -", mono=True, selectable=True)
        self.scale = label("", "Muted", mono=True)
        self.root.addWidget(self.px)
        self.root.addWidget(self.scale)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._blink)
        self._blink_state = False
        self._disp: dict = {}

    def _each(self, fn) -> None:
        fn(self.left)
        if not self.right.isHidden():
            fn(self.right)
        self._scale_text()

    def refresh(self) -> None:
        fill_conditions(self.a, self.ctl, keep=self.a.currentData() or "ORIGINAL")
        fill_conditions(self.b, self.ctl, keep=self.ctl.selected_tid or self.b.currentData())
        self._load()

    def _load(self, *_a) -> None:
        self._disp = {}
        for key, combo in (("A", self.a), ("B", self.b)):
            img = self.ctl.image_for(combo.currentData() or "ORIGINAL") if self.ctl.source else None
            self._disp[key] = (img, display_image(img) if img is not None else None)
        self._render()

    def _mode(self) -> str:
        return next((b.text() for b in self.mode_btns if b.isChecked()), MODES[0])

    def _render(self, *_a) -> None:
        self.timer.stop()
        a, b = self._disp.get("A", (None, None)), self._disp.get("B", (None, None))
        if a[0] is None:
            self.left.clear_image()
            self.right.clear_image()
            return
        mode = self._mode()
        self.right.setVisible(mode == "Side-by-Side")
        if mode == "Side-by-Side" or b[0] is None:
            self.left.set_display(a[1][0], a[0].size, a[1][1])
            if b[0] is not None:
                self.right.set_display(b[1][0], b[0].size, b[1][1])
        elif a[0].size != b[0].size:
            self.left.set_display(a[1][0], a[0].size, a[1][1])
            self.px.setText(f"{mode} requires equal resolution ({a[0].size} vs {b[0].size}). Use Side-by-Side.")
        elif mode == "Overlay":
            da, db = a[1][0].convert("RGBA"), b[1][0].convert("RGBA")
            self.left.set_display(Image.blend(da, db, self.opacity.value() / 100.0), a[0].size, a[1][1])
        elif mode == "Blink":
            self.timer.start()
            self._blink()
        else:
            d = difference_map(a[0], b[0])
            if d is None:
                return
            d = np.clip(d.astype(np.int32) * self.amp.value(), 0, 255).astype(np.uint8)
            img = Image.fromarray(d) if mode == "Difference" else Image.fromarray(LUT[d])
            disp, f = display_image(img)
            self.left.set_display(disp, a[0].size, f)
        self._scale_text()

    def _blink(self) -> None:
        self._blink_state = not self._blink_state
        key = "B" if self._blink_state else "A"
        img, disp = self._disp[key]
        if img is not None:
            self.left.set_display(disp[0], img.size, disp[1])
            self.scale.setText(f"BLINK showing {key}  |  {self.left.status_text()}")

    def _scale_text(self) -> None:
        self.scale.setText(f"A: {self.left.status_text()}" + (f"    B: {self.right.status_text()}" if not self.right.isHidden() else
                                                               f"    mode: {self._mode()}"))

    def _hover(self, x: int, y: int) -> None:
        if x < 0:
            return
        arr_a = self.ctl.array_for(self.a.currentData() or "ORIGINAL")
        arr_b = self.ctl.array_for(self.b.currentData() or "ORIGINAL")

        def val(arr):
            if arr is None or y >= arr.shape[0] or x >= arr.shape[1]:
                return None
            return [int(v) if not isinstance(v, float) else round(float(v), 4) for v in arr[y, x].tolist()]

        va, vb = val(arr_a), val(arr_b)
        diff = [abs(p - q) for p, q in zip(va, vb)] if va is not None and vb is not None and len(va) == len(vb) else None
        self.px.setText(f"X {x}   Y {y}   Original {va if va is not None else '-'}   Output {vb if vb is not None else '-'}   "
                        f"Difference {diff if diff is not None else '-'}")
