from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from app.ui.views.base import View, fill_conditions, row
from app.ui.widgets.common import KVTable, Readout, banner, fmt_num, label


class IntegrityView(View):
    title = "Pixel Integrity"
    subtitle = ("PIXEL-EXACT is shown only when every decoded sample is identical, the pixel representation is identical "
                "and the pixel SHA-256 digests match. It is never inferred.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        self.cond = QComboBox()
        self.cond.currentIndexChanged.connect(self._fill)
        self.cond.currentIndexChanged.connect(lambda _i: self.cond.currentData() and ctl.select(self.cond.currentData()))
        self.root.addLayout(row(label("Condition (vs ORIGINAL):"), self.cond, None))
        self.verdict = Readout("Verdict")
        self.verdict.value.setStyleSheet("font-size: 22pt;")
        self.root.addWidget(self.verdict)
        self.flags = banner("")
        self.root.addWidget(self.flags)
        self.kv = KVTable()
        self.root.addWidget(self.kv, 1)

    def refresh(self) -> None:
        fill_conditions(self.cond, self.ctl, include_original=False, keep=self.ctl.selected_tid or None)
        self._fill()

    def _fill(self, *_a) -> None:
        t = self.ctl.record(self.cond.currentData() or "")
        if t is None:
            self.verdict.set("NO DATA", "Run a transformation first.", "ABSENT")
            self.kv.set_rows([])
            self.flags.setVisible(False)
            return
        pm = t.pixel_metrics or {}
        v = pm.get("verdict", "-")
        self.verdict.set("PIXEL-EXACT \u2713" if v == "PIXEL-EXACT" else v, f"{t.transformation_id} {t.label} | {pm.get('basis', '')}", v)
        self.flags.setVisible(bool(t.flags))
        self.flags.setText("\n".join(t.flags))
        ra, rb = pm.get("resolution_a") or [0, 0], pm.get("resolution_b") or [0, 0]
        dim = "MATCH" if list(ra) == list(rb) else "DIMENSION CHANGE DETECTED"
        psnr = "infinite (identical arrays)" if pm.get("psnr_infinite") else fmt_num(pm.get("psnr_db"), 3) + " dB"
        self.kv.set_rows([
            ["Resolution (original / output)", f"{ra[0]}x{ra[1]} / {rb[0]}x{rb[1]}  [{dim}]"],
            ["Pixel count", f"{fmt_num(pm.get('pixel_count_a'))} / {fmt_num(pm.get('pixel_count_b'))}"],
            ["Channel count", f"{pm.get('channels_a')} / {pm.get('channels_b')}"],
            ["Pixel mode", f"{pm.get('mode_a')} / {pm.get('mode_b')} (compared as {pm.get('compared_mode') or '-'})"],
            ["MAE", fmt_num(pm.get("mae"), 6)], ["MSE", fmt_num(pm.get("mse"), 6)],
            ["Maximum error", fmt_num(pm.get("max_abs_error"))], ["Changed pixel count", fmt_num(pm.get("changed_pixels"))],
            ["Changed pixel percentage", fmt_num(pm.get("changed_pixel_pct"), 6) + " %"], ["PSNR", psnr],
            ["SSIM (7x7)", fmt_num(pm.get("ssim"), 6)], ["Histogram difference (TV distance)", fmt_num(pm.get("histogram_difference"), 6)],
            ["Perceptual difference (dHash)", f"{fmt_num(pm.get('perceptual_hash_distance'))} / 64 bits "
                                              f"({fmt_num(pm.get('perceptual_difference'), 4)})"],
            ["Region-aligned comparison", f"{pm.get('region')} exact={pm.get('region_exact')}" if pm.get("region") else "-"],
            ["Pixel SHA-256 original", pm.get("pixel_sha256_a")], ["Pixel SHA-256 output", pm.get("pixel_sha256_b")],
            ["File SHA-256 original", t.input_sha256], ["File SHA-256 output", t.output_sha256],
            ["Comparison time", f"{fmt_num(pm.get('duration_ms'), 1)} ms"]] + [["Note", n] for n in pm.get("notes") or []]
            + [["Action", a] for a in t.actions] + [["Transformation note", n] for n in t.notes])
