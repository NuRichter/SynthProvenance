from __future__ import annotations

import json

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.core.image_memory import estimate
from app.ui.theme import C, mono_font, state_color
from app.ui.views.base import View
from app.ui.widgets.charts import HistogramWidget
from app.ui.widgets.common import DataTable, KVTable, fmt_num, label
from app.ui.widgets.image_canvas import array_to_image, to_qimage
from app.utils.memory import fmt_bytes


class InspectorView(View):
    title = "Forensic Inspector"
    subtitle = "Every value below is read from the file's bytes or decoder. Nothing is inferred."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        self.tabs = QTabWidget()
        self.file_kv = KVTable()
        self.tabs.addTab(self.file_kv, "File && Hashes")  # "&&": a single "&" is a Qt mnemonic
        mw = QWidget()
        ml = QVBoxLayout(mw)
        ml.setContentsMargins(0, 6, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter keys / values ...")
        self.filter.textChanged.connect(self._fill_tree)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Value", "State", "Category", "Namespace"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 460)
        self.tree.setAlternatingRowColors(True)
        ml.addWidget(self.filter)
        ml.addWidget(self.tree)
        self.tabs.addTab(mw, "Metadata")
        sw = QWidget()
        sl = QVBoxLayout(sw)
        self.structure = DataTable(["Segment", "Ident", "Offset", "Length", "Payload", "CRC", "Note"], mono_cols=(2, 3, 4))
        self.structure_info = QPlainTextEdit()
        self.structure_info.setReadOnly(True)
        self.structure_info.setFont(mono_font(8.5))
        self.structure_info.setMaximumHeight(160)
        sl.addWidget(self.structure)
        sl.addWidget(self.structure_info)
        self.tabs.addTab(sw, "File Structure")
        cw = QWidget()
        cl = QVBoxLayout(cw)
        self.comp_kv = KVTable()
        self.quant = QPlainTextEdit()
        self.quant.setReadOnly(True)
        self.quant.setFont(mono_font(8.5))
        cl.addWidget(self.comp_kv, 2)
        cl.addWidget(label("JPEG quantisation tables (natural order)", "PanelTitle"))
        cl.addWidget(self.quant, 3)
        self.tabs.addTab(cw, "Compression")
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.addWidget(label("", "Banner", wrap=True))
        self.stats_banner = fl.itemAt(0).widget()
        hl = QHBoxLayout()
        self.stats_kv = KVTable()
        hl.addWidget(self.stats_kv, 3)
        right = QVBoxLayout()
        self.hist = HistogramWidget("RGB / channel histogram")
        self.lum = HistogramWidget("Luminance histogram")
        self.fft = QLabel("FFT log-magnitude spectrum")
        self.fft.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fft.setMinimumSize(256, 256)
        self.fft.setStyleSheet(f"border: 1px solid {C['line']}; color: {C['muted']};")
        right.addWidget(self.hist)
        right.addWidget(self.lum)
        right.addWidget(self.fft)
        hl.addLayout(right, 2)
        fl.addLayout(hl)
        self.tabs.addTab(fw, "Forensic Statistics")
        self.ext = DataTable(["Tag", "Value"])
        self.tabs.addTab(self.ext, "External Tools (ExifTool)")
        self.root.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        src = self.ctl.source
        if src is None:
            self.file_kv.set_rows([["Status", "No image loaded"]])
            self.tree.clear()
            return
        a, d = src.analysis, src.analysis_dict
        i, h = a.info, a.hashes
        est = estimate(i.width, i.height, i.mode)
        rows = [["Filename", i.filename], ["File path", i.path], ["File size", f"{i.file_size:,} bytes ({fmt_bytes(i.file_size)})"],
                ["Format / MIME", f"{i.format} / {i.mime}"], ["Resolution (SOURCE)", f"{i.width} x {i.height}"],
                ["Aspect ratio", i.aspect_ratio], ["Pixel count", f"{i.pixel_count:,}"], ["Color space", i.color_space],
                ["ICC profile", i.icc_profile], ["Bit depth", i.bit_depth], ["Channels", i.channels], ["Pixel mode", i.mode],
                ["Compression", i.compression], ["Frames", i.frames], ["EXIF orientation", i.orientation],
                ["Decoded memory", f"{fmt_bytes(est['decoded'])} (working set ~{fmt_bytes(est['working_set'])})"],
                ["SHA-256 (file)", h.get("sha256")], ["BLAKE3 (file)", h.get("blake3") or h.get("blake3_state")],
                ["SHA-256 (decoded pixels)", h.get("pixel_sha256")], ["Analysis time", f"{a.duration_ms:.1f} ms"]]
        rows += [["Warning", w] for w in i.warnings] + [["Parse error", e] for e in a.errors]
        self.file_kv.set_rows(rows)
        self._fill_tree()
        st = d.get("structure") or {}
        self.structure.set_data(["Segment", "Ident", "Offset", "Length", "Payload", "CRC", "Note"],
                                [[s["name"], s["ident"], s["offset"], s["length"], s["payload_length"],
                                  {True: "OK", False: "MISMATCH", None: "-"}[s.get("crc_ok")], s.get("note", "")]
                                 for s in st.get("segments", [])])
        self.structure_info.setPlainText(json.dumps({"container": st.get("container"), "info": st.get("info"),
                                                     "trailing_bytes": st.get("trailing_bytes"), "errors": st.get("errors")},
                                                    indent=2, default=str))
        comp = d.get("compression") or {}
        self.comp_kv.set_rows([[k, v] for k, v in comp.items() if k != "quantization_tables"])
        lines = []
        for t in comp.get("quantization_tables") or []:
            q = t.get("quality_estimate", {})
            lines.append(f"Table {t['id']} ({t['precision_bits']}-bit)  IJG~Q{q.get('ijg_equivalent_quality')} [{q.get('basis')}]")
            nat = t["natural_order"]
            lines += ["  " + " ".join(f"{v:4d}" for v in nat[r * 8:(r + 1) * 8]) for r in range(8)]
        self.quant.setPlainText("\n".join(lines) or "Not a JPEG (no quantisation tables).")
        self._fill_stats()
        ext = (d.get("external") or {}).get("exiftool")
        if ext and ext.get("status") == "OK":
            self.ext.set_data(["Tag (ExifTool, read-only external output)", "Value"], [[k, v] for k, v in ext["tags"].items()])
        else:
            self.ext.set_data(["Tag", "Value"], [["ExifTool", (ext or {}).get("detail") or
                                                  f"not used: {self.ctl.exiftool.detail or 'unavailable'} (optional)"]])

    def _fill_tree(self) -> None:
        src = self.ctl.source
        self.tree.clear()
        if src is None:
            return
        q = self.filter.text().strip().lower()
        for name, g in src.analysis_dict["groups"].items():
            top = QTreeWidgetItem([name, f"{len(g['fields'])} fields  {g.get('location', '')}", g["state"], "", ""])
            top.setForeground(2, QColor(state_color(g["state"])))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            shown = 0
            for fld in g["fields"]:
                if q and q not in fld["key"].lower() and q not in str(fld["value"]).lower():
                    continue
                it = QTreeWidgetItem([fld["key"], str(fld["value"]), fld["state"], fld["category"], fld["namespace"]])
                it.setFont(1, mono_font(8.5))
                it.setToolTip(1, str(fld["value"])[:3000])
                it.setForeground(2, QColor(state_color(fld["state"])))
                top.addChild(it)
                shown += 1
            for note in g.get("notes") or []:
                n = QTreeWidgetItem(["note", note, "", "", ""])
                n.setForeground(1, QColor(C["muted"]))
                top.addChild(n)
            if q and not shown:
                continue
            self.tree.addTopLevelItem(top)
            top.setExpanded(bool(q) or g["state"] in ("PRESENT", "INVALID") and len(g["fields"]) < 60)

    def _fill_stats(self) -> None:
        s = self.ctl.statistics or {}
        self.stats_banner.setText("ANALYTICAL ONLY. " + (s.get("disclaimer") or "Statistics are computed when an experiment "
                                                                                 "starts (START EXPERIMENT)."))
        if not s:
            self.stats_kv.set_rows([])
            self.hist.set_series({})
            self.lum.set_series({})
            return
        rows = [["Analysis size", f"{s.get('analysis_size')} (reduction factor {s.get('reduction_factor')}; source unchanged)"]]
        for k in ("entropy_bits", "edge_density", "noise_sigma_estimate", "blockiness_8px"):
            rows.append([k, fmt_num(s.get(k))])
        rows += [[f"channel entropy {c}", fmt_num(v)] for c, v in (s.get("channel_entropy_bits") or {}).items()]
        for k, v in (s.get("color_distribution") or {}).items():
            rows.append([f"color {k}", ", ".join(fmt_num(x, 2) for x in v) if isinstance(v, list) else fmt_num(v)])
        fft_img = None
        for k, v in (s.get("fft") or {}).items():
            if isinstance(v, np.ndarray):
                fft_img = v
            elif not isinstance(v, (list, dict)):
                rows.append([f"fft {k}", fmt_num(v)])
        rows.append(["duration", f"{s.get('duration_ms', 0):.0f} ms"])
        self.stats_kv.set_rows(rows)
        self.hist.set_series(s.get("histograms") or {})
        self.lum.set_series({"Y": s.get("luminance_histogram") or []})
        if fft_img is not None:
            arr = np.asarray(fft_img)
            if arr.dtype != np.uint8:
                arr = (255 * (arr - arr.min()) / max(float(arr.max() - arr.min()), 1e-9)).astype(np.uint8)
            self.fft.setPixmap(QPixmap.fromImage(to_qimage(array_to_image(arr))).scaled(
                256, 256, Qt.AspectRatioMode.KeepAspectRatio))
