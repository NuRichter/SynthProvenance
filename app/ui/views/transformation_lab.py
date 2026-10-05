from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QStackedWidget, QVBoxLayout, QWidget)

from app.core.transform_engine import OPERATIONS
from app.services.c2pa_experiment import C2PA_WARNING
from app.services.metadata_sanitizer import OPTION_HELP, OPTION_LABELS, PROFILE_HELP, PROFILES
from app.ui.views.base import View, row
from app.ui.widgets.common import DataTable, Panel, ParamForm, banner, button, label

LAB_OPS = ["metadata_sanitize", "c2pa_separation", "png_reencode", "jpeg_reencode", "webp_reencode", "lossless_export",
           "color_conversion", "resize", "crop", "controlled_recompression", "external_comparison"]


class TransformationLabView(View):
    title = "Transformation Lab"
    subtitle = "Every transformation is explicit, parameterised, recorded and measured. The original is never overwritten."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        top = QHBoxLayout()
        self.ops = QListWidget()
        self.ops.setMaximumWidth(280)
        for op in LAB_OPS:
            QListWidgetItem(OPERATIONS[op].label, self.ops).setData(256, op)
        top.addWidget(self.ops)
        right = QVBoxLayout()
        self.desc = label("", "Muted", wrap=True)
        right.addWidget(self.desc)
        self.stack = QStackedWidget()
        self.forms: dict[str, QWidget] = {}
        for op in LAB_OPS:
            w = self._build_form(op)
            self.forms[op] = w
            self.stack.addWidget(w)
        right.addWidget(self.stack, 1)
        self.b_run = button("RUN TRANSFORMATION", primary=True)
        self.b_run.clicked.connect(self._run)
        b_matrix = button("Run full matrix battery", tooltip="Sanitize (current settings), C2PA separation, PNG/JPEG/WEBP "
                                                               "re-encode, colour, resize, crop, lossless export")
        b_matrix.clicked.connect(lambda: ctl.run_matrix(self._sanitize_params()))
        right.addLayout(row(self.b_run, b_matrix, None))
        top.addLayout(right, 1)
        pan = Panel("Operation")
        pan.add(top)
        self.root.addWidget(pan)
        rp = Panel("Recorded transformations (select to inspect; double-click opens Pixel Integrity)")
        self.records = DataTable(["ID", "Operation", "Status", "Pixels", "Format", "Resolution", "Flags", "ms"], mono_cols=(0,))
        self.records.setMinimumHeight(220)
        self.records.itemSelectionChanged.connect(self._sel)
        self.records.cellDoubleClicked.connect(lambda *_: win.go("Pixel Integrity"))
        rp.add(self.records)
        self.root.addWidget(rp, 1)
        self.ops.currentRowChanged.connect(self._op_changed)
        self.ops.setCurrentRow(0)

    def _build_form(self, op: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if op == "metadata_sanitize":
            f = QFormLayout()
            self.s_mode = QComboBox()
            self.s_mode.addItems(["METADATA-ONLY", "LOSSLESS RE-ENCODE"])
            self.s_mode.setToolTip("METADATA-ONLY: byte-level container rewrite, pixel-exact by construction and verified. "
                                   "LOSSLESS RE-ENCODE: decode and write PNG with only ICC kept.")
            self.s_profile = QComboBox()
            self.s_profile.addItems(list(PROFILES) + ["CUSTOM"])
            self.s_profile.setCurrentText(self.ctl.settings.get("default_sanitize_profile") or "BALANCED")
            f.addRow("Mode", self.s_mode)
            f.addRow("Profile", self.s_profile)
            lay.addLayout(f)
            self.s_help = label("", "Muted", wrap=True)
            lay.addWidget(self.s_help)
            self.s_boxes: dict[str, QCheckBox] = {}
            grid = QHBoxLayout()
            cols = [QVBoxLayout(), QVBoxLayout(), QVBoxLayout()]
            for n, (k, text) in enumerate(OPTION_LABELS.items()):
                cb = QCheckBox(text)
                cb.setToolTip(OPTION_HELP[k])
                cb.toggled.connect(self._box_toggled)
                self.s_boxes[k] = cb
                cols[n % 3].addWidget(cb)
            for c in cols:
                grid.addLayout(c)
            lay.addLayout(grid)
            self.s_warn = banner("Nonessential application metadata includes C2PA / JUMBF manifest stores and XMP provenance "
                                 "declarations. Removing them removes the file's Content Credentials. " + C2PA_WARNING)
            lay.addWidget(self.s_warn)
            self.s_profile.currentTextChanged.connect(self._profile_changed)
            self._profile_changed(self.s_profile.currentText())
        elif op == "c2pa_separation":
            lay.addWidget(banner(C2PA_WARNING))
            self.c_xmp = QCheckBox("Also remove XMP provenance declarations")
            lay.addWidget(self.c_xmp)
        elif op == "external_comparison":
            self.x_path = QLineEdit()
            self.x_path.setPlaceholderText("File processed outside SynthProvenance (e.g. downloaded after a platform upload)")
            b = button("Browse...")
            b.clicked.connect(self._browse)
            lay.addLayout(row(self.x_path, b))
        else:
            form = ParamForm(OPERATIONS[op].params)
            w.form = form
            lay.addWidget(form)
        lay.addStretch(1)
        return w

    def _profile_changed(self, name: str) -> None:
        if name in PROFILES:
            opts = PROFILES[name].to_dict()
            for k, cb in self.s_boxes.items():
                cb.blockSignals(True)
                cb.setChecked(opts[k])
                cb.blockSignals(False)
        self.s_help.setText(PROFILE_HELP.get(name, "Custom selection."))
        self.s_warn.setVisible(self.s_boxes["nonessential"].isChecked())

    def _box_toggled(self, _v) -> None:
        if self.s_profile.currentText() != "CUSTOM":
            self.s_profile.blockSignals(True)
            self.s_profile.setCurrentText("CUSTOM")
            self.s_profile.blockSignals(False)
            self.s_help.setText("Custom selection.")
        self.s_warn.setVisible(self.s_boxes["nonessential"].isChecked())

    def _sanitize_params(self) -> dict:
        prof = self.s_profile.currentText()
        p = {"mode": self.s_mode.currentText(), "profile": prof}
        if prof == "CUSTOM":
            p["options"] = {k: cb.isChecked() for k, cb in self.s_boxes.items()}
        return p

    def _op_changed(self, i: int) -> None:
        op = LAB_OPS[max(i, 0)]
        self.stack.setCurrentWidget(self.forms[op])
        self.desc.setText(OPERATIONS[op].description)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "External file", "", "Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp *.gif)")
        if path:
            self.x_path.setText(path)

    def _run(self) -> None:
        op = LAB_OPS[max(self.ops.currentRow(), 0)]
        if op == "metadata_sanitize":
            params = self._sanitize_params()
        elif op == "c2pa_separation":
            params = {"include_xmp_declarations": self.c_xmp.isChecked()}
        elif op == "external_comparison":
            if not self.x_path.text().strip():
                self.ctl.error.emit("No file", "Choose the external file first.")
                return
            params = {"path": self.x_path.text().strip()}
        else:
            params = self.forms[op].form.values()
        self.ctl.run_transformation(op, params)

    def _sel(self) -> None:
        r = self.records.currentRow()
        it = self.records.item(r, 0) if r >= 0 else None
        if it is not None:
            self.ctl.select(it.text())

    def refresh(self) -> None:
        rows = []
        for t in self.ctl.records():
            dims = f"{t.output_dimensions[0]}x{t.output_dimensions[1]}" if t.output_dimensions else "-"
            rows.append([t.transformation_id, t.label, t.status, (t.pixel_metrics or {}).get("verdict", "-") if t.status == "COMPLETE"
                         else t.error[:80], t.output_format or "-", dims, "; ".join(t.flags) or "-", f"{t.duration_ms:.0f}"])
        self.records.blockSignals(True)
        self.records.set_data(["ID", "Operation", "Status", "Pixels", "Format", "Resolution", "Flags", "ms"], rows)
        for r in range(self.records.rowCount()):
            if self.records.item(r, 0).text() == self.ctl.selected_tid:
                self.records.selectRow(r)
        self.records.blockSignals(False)
        self.b_run.setEnabled(self.ctl.source is not None)
