from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QRadioButton, QSpinBox

from app.core.image_writer import FORMAT_CAPS, pixel_expectation
from app.ui.views.base import View, fill_conditions, row
from app.ui.widgets.common import DataTable, KVTable, Panel, banner, button, fmt_num, label


class FormatLabView(View):
    title = "Format Conversion"
    subtitle = ("SAVE AS and FORMAT CONVERSION LAB. Every export is a recorded transformation: hashes, resolution, pixel "
                "metrics, metadata and provenance changes are measured against ORIGINAL.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        top = QHBoxLayout()
        p = Panel("Save As")
        self.src = QComboBox()
        self.fmt = QComboBox()
        for k, c in FORMAT_CAPS.items():
            self.fmt.addItem(c["label"], k)
        self.lossless, self.lossy = QRadioButton("LOSSLESS"), QRadioButton("LOSSY")
        grp = QButtonGroup(self)
        grp.addButton(self.lossless)
        grp.addButton(self.lossy)
        self.lossless.setChecked(True)
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(90)
        self.keep_icc = QCheckBox("Keep ICC profile")
        self.keep_icc.setChecked(True)
        self.carry = QCheckBox("Carry EXIF / XMP (C2PA never copied)")
        for w in (self.fmt, self.src):
            w.currentIndexChanged.connect(self._caps)
        for w in (self.lossless, self.lossy):
            w.toggled.connect(self._caps)
        self.quality.valueChanged.connect(self._caps)
        p.add(row(label("Source"), self.src, label("Format"), self.fmt, None))
        p.add(row(label("Compression mode"), self.lossless, self.lossy, label("Quality"), self.quality, None))
        p.add(row(self.keep_icc, self.carry, None))
        self.warn = banner("")
        p.add(self.warn)
        self.caps = KVTable()
        self.caps.setMinimumHeight(250)
        p.add(self.caps)
        b_save = button("SAVE AS...", primary=True)
        b_save.clicked.connect(self._save_as)
        b_rec = button("Convert (record in experiment only)")
        b_rec.clicked.connect(lambda: self._convert(""))
        p.add(row(b_save, b_rec, None))
        top.addWidget(p, 1)
        q = Panel("Format conversion chain")
        q.add(label("Syntax: FORMAT[:LOSSLESS|LOSSY[:quality]] steps separated by '>'. Every step file is saved and measured "
                    "against ORIGINAL and against the previous step.", "Muted", wrap=True))
        self.chain = QLineEdit("JPEG:LOSSY:90 > WEBP:LOSSY:90 > PNG:LOSSLESS")
        self.chain_icc = QCheckBox("Keep ICC")
        self.chain_icc.setChecked(True)
        self.chain_carry = QCheckBox("Carry EXIF/XMP")
        b_chain = button("Run chain", primary=True)
        b_chain.clicked.connect(lambda: ctl.run_transformation("format_chain", {
            "steps": self.chain.text(), "keep_icc": self.chain_icc.isChecked(), "carry_metadata": self.chain_carry.isChecked()}))
        q.add(self.chain)
        q.add(row(self.chain_icc, self.chain_carry, None, b_chain))
        self.chain_rec = QComboBox()
        self.chain_rec.currentIndexChanged.connect(self._fill_steps)
        q.add(row(label("Chain record"), self.chain_rec, None))
        self.steps = DataTable(["Step", "In", "Out", "Mode", "Quality", "In SHA-256", "Out SHA-256", "Resolution",
                                "vs ORIGINAL", "PSNR", "vs previous", "Metadata changes", "C2PA / signal"], mono_cols=(5, 6))
        self.steps.setMinimumHeight(250)
        q.add(self.steps)
        top.addWidget(q, 1)
        self.root.addLayout(top, 1)
        self._caps()

    def _caps(self, *_a) -> None:
        key = self.fmt.currentData() or "PNG"
        c = FORMAT_CAPS[key]
        self.lossless.setEnabled("LOSSLESS" in c["modes"])
        self.lossy.setEnabled("LOSSY" in c["modes"])
        if not self.lossless.isEnabled():
            self.lossy.setChecked(True)
        elif not self.lossy.isEnabled():
            self.lossless.setChecked(True)
        mode = "LOSSY" if self.lossy.isChecked() else "LOSSLESS"
        self.quality.setEnabled(mode == "LOSSY")
        src_mode = self.ctl.source.analysis.info.mode if self.ctl.source else "RGB"
        self.caps.set_rows([["Format", c["label"]], ["Compression mode", f"{mode} ({c['compression']})"],
                            ["Quality", self.quality.value() if mode == "LOSSY" else "n/a (lossless)"],
                            ["Alpha support", c["alpha"]], ["Color profile handling", c["icc"]], ["Bit depth", c["bit_depth"]],
                            ["Metadata handling", c["metadata"]],
                            ["Pixel preservation state", pixel_expectation(key, mode, src_mode)]])
        warn = c["warning"] if (mode == "LOSSY" or key == "JPEG") else ""
        self.warn.setText(f"{key} EXPORT\nWARNING: {warn}" if warn else "")
        self.warn.setVisible(bool(warn))

    def _params(self):
        return (self.src.currentData() or "ORIGINAL", self.fmt.currentData() or "PNG",
                "LOSSY" if self.lossy.isChecked() else "LOSSLESS", self.quality.value(), self.keep_icc.isChecked(),
                self.carry.isChecked())

    def _convert(self, dest: str) -> None:
        self.ctl.save_as(*self._params(), dest)

    def _save_as(self) -> None:
        if self.ctl.source is None:
            self.ctl.error.emit("No image", "Open an image first.")
            return
        key = self.fmt.currentData() or "PNG"
        stem = self.ctl.source.analysis.info.filename.rsplit(".", 1)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save As", f"{stem}_export{FORMAT_CAPS[key]['ext']}", FORMAT_CAPS[key]["filter"])
        if path:
            self._convert(path)

    def refresh(self) -> None:
        fill_conditions(self.src, self.ctl, keep=self.src.currentData() or "ORIGINAL")
        fill_conditions(self.chain_rec, self.ctl, include_original=False, only_ops=("format_chain",))
        self._caps()
        self._fill_steps()

    def _fill_steps(self, *_a) -> None:
        t = self.ctl.record(self.chain_rec.currentData() or "")
        if t is None:
            self.steps.setRowCount(0)
            return
        rows = []
        for s in t.steps:
            vo, vp = s.get("vs_original") or {}, s.get("vs_previous") or {}
            psnr = "inf" if vo.get("psnr_infinite") else fmt_num(vo.get("psnr_db"), 2)
            rows.append([f"{t.transformation_id}.{s['step']}", s["input_format"], s["output_format"], s["compression"],
                         s["quality"] or "-", (s["input_sha256"] or "")[:16], (s["output_sha256"] or "")[:16], s["resolution"],
                         vo.get("verdict"), psnr, vp.get("verdict"), ", ".join(f"{k}:{v}" for k, v in s["metadata_changes"].items()) or "-",
                         f"{s['provenance']['c2pa']} / {s['provenance']['signal']}"])
        self.steps.set_data(["Step", "In", "Out", "Mode", "Quality", "In SHA-256", "Out SHA-256", "Resolution", "vs ORIGINAL",
                             "PSNR", "vs previous", "Metadata changes", "C2PA / signal"], rows)
