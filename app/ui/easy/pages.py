"""The three Easy Mode screens: 01 PILIH, 02 RUN, 03 OUTPUT.

Nothing technical is configured here. The only choices are the image, the output format
and whether / where the research report is written. Everything else is decided by the
Easy Mode orchestrator.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QPlainTextEdit, QProgressBar,
                               QVBoxLayout, QWidget)

from app.core.easy_mode_orchestrator import OUTPUT_FORMATS, PHASES
from app.i18n import tr
from app.ui.easy.style import E
from app.ui.easy.widgets import Card, DropZone, PhaseTimeline, amp, ebutton, elabel
from app.utils.memory import fmt_bytes
from app.utils.validation import sniff_format

CENTER = Qt.AlignmentFlag.AlignCenter


def probe_image(path: str) -> dict:
    """Header-only facts for the PILIH screen (format from magic bytes; never trusts the extension)."""
    p = Path(path)
    if not p.is_file():
        raise ValueError("not a file")
    with p.open("rb") as fh:
        fmt = sniff_format(fh.read(16))
    if fmt is None:
        raise ValueError("unsupported")
    reader = QImageReader(str(p))
    size = reader.size()
    w, h = (size.width(), size.height()) if size.isValid() else (0, 0)
    if not (w and h):
        from PIL import Image

        with Image.open(p) as im:
            w, h = im.size
    return {"name": p.name, "path": str(p), "format": {"JPEG": "JPG"}.get(fmt, fmt), "width": w, "height": h,
            "bytes": p.stat().st_size}


def thumbnail(path: str, box: QSize = QSize(400, 170)) -> QPixmap | None:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() * size.height() > 0:
        if size.width() * size.height() > 80_000_000:
            return None  # very large: skip the preview rather than block the interface
        reader.setScaledSize(size.scaled(box, Qt.AspectRatioMode.KeepAspectRatio))
    img = reader.read()
    if img.isNull():
        return None
    pm = QPixmap.fromImage(img)
    if pm.width() > box.width() or pm.height() > box.height():
        pm = pm.scaled(box, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return pm


def _column() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 8, 0, 24)
    v.setSpacing(14)
    return w, v


def _hcenter(*widgets) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setSpacing(12)
    h.addStretch(1)
    for w in widgets:
        h.addWidget(w)
    h.addStretch(1)
    return h


# ---------------------------------------------------------------------- 01 PILIH
class PilihPage(QWidget):
    continueRequested = Signal()
    chooseRequested = Signal()
    locationRequested = Signal()

    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings
        self.info: dict | None = None
        self.report_dir = str(settings.get("easy_report_dir") or "")
        col, v = _column()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(col)
        self.title = elabel("", "StepTitle", align=CENTER)
        self.sub = elabel("", "StepSub", wrap=True, align=CENTER)
        v.addWidget(self.title)
        v.addWidget(self.sub)
        self.drop = DropZone()
        self.drop.fileDropped.connect(self.set_file)
        self.drop.activated.connect(self.chooseRequested)
        v.addWidget(self.drop)
        self.error = elabel("", "InlineError", wrap=True, align=CENTER)
        self.error.setVisible(False)
        v.addWidget(self.error)
        # selected-file facts (no metadata, hashes or research terms here)
        self.facts = QFrame()
        self.facts.setObjectName("Card")
        g = QGridLayout(self.facts)
        g.setContentsMargins(18, 14, 18, 14)
        g.setHorizontalSpacing(28)
        g.setVerticalSpacing(4)
        self.fact_keys, self.fact_vals = [], []
        for i in range(4):
            k = elabel("", "Help")
            val = elabel("-", "CardValue", wrap=True, selectable=True)
            val.setStyleSheet("font-weight: 600;")
            g.addWidget(k, 0, i)
            g.addWidget(val, 1, i)
            g.setColumnStretch(i, 2 if i == 0 else 1)
            self.fact_keys.append(k)
            self.fact_vals.append(val)
        self.facts.setVisible(False)
        v.addWidget(self.facts)
        # output format
        self.fmt_label = elabel("", "SectionLabel")
        self.fmt = QComboBox()
        self.fmt.addItems(list(OUTPUT_FORMATS))
        default = str(settings.get("easy_output_format") or "PNG").upper()
        self.fmt.setCurrentText(default if default in OUTPUT_FORMATS else "PNG")
        self.fmt.setMinimumWidth(200)
        self.fmt_help = elabel("", "Help", wrap=True)
        # research report
        self.rep_label = elabel("", "SectionLabel")
        self.report = QCheckBox()
        self.report.setChecked(bool(settings.get("easy_save_report")))
        self.report.toggled.connect(self._report_toggled)
        self.loc_caption = elabel("", "Help")
        self.loc_value = elabel("", "CardValue", wrap=True, selectable=True)
        self.b_loc = ebutton("")
        self.b_loc.clicked.connect(self.locationRequested)
        self.b_default = ebutton("", "link")
        self.b_default.clicked.connect(lambda: self.set_report_dir(""))
        # two calm columns: OUTPUT FORMAT | RESEARCH REPORT
        cols = QHBoxLayout()
        cols.setSpacing(28)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.fmt_label)
        left.addWidget(self.fmt)
        left.addWidget(self.fmt_help)
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.rep_label)
        right.addWidget(self.report)
        right.addWidget(self.loc_caption)
        right.addWidget(self.loc_value)
        lr = QHBoxLayout()
        lr.setSpacing(8)
        lr.addWidget(self.b_loc)
        lr.addWidget(self.b_default)
        lr.addStretch(1)
        right.addLayout(lr)
        right.addStretch(1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        v.addLayout(cols)
        v.addSpacing(6)
        self.b_continue = ebutton("", "primary")
        self.b_continue.setMinimumWidth(320)
        self.b_continue.setEnabled(False)
        self.b_continue.clicked.connect(self.continueRequested)
        v.addStretch(1)   # CONTINUE lives in the window's fixed action bar so it is always visible
        self.retranslate()

    # -- state ---------------------------------------------------------------
    def set_file(self, path: str) -> bool:
        try:
            info = probe_image(path)
        except Exception:  # noqa: BLE001 - shown as a friendly inline message, never a traceback
            self.info = None
            self.facts.setVisible(False)
            self.drop.show_preview(None)
            self.error.setText(tr("easy.not_image"))
            self.error.setVisible(True)
            self.b_continue.setEnabled(False)
            return False
        self.info = info
        self.error.setVisible(False)
        self.drop.show_preview(thumbnail(path))
        vals = [info["name"], f"{info['width']} × {info['height']}", info["format"], fmt_bytes(info["bytes"])]
        for lab, val in zip(self.fact_vals, vals):
            lab.setText(str(val))
        for k, val in zip(self.fact_keys, self.fact_vals):
            val.setAccessibleName(f"{k.text()}: {val.text()}")
        self.facts.setVisible(True)
        self.b_continue.setEnabled(True)
        return True

    def set_report_dir(self, path: str) -> None:
        self.report_dir = str(path or "")
        self._report_toggled(self.report.isChecked())

    def _report_toggled(self, on: bool) -> None:
        self.loc_value.setText(self.report_dir or tr("easy.report_default"))
        for w in (self.loc_caption, self.loc_value, self.b_loc):
            w.setEnabled(on)
        self.b_default.setVisible(on and bool(self.report_dir))

    def reset(self) -> None:
        self.info = None
        self.drop.show_preview(None)
        self.facts.setVisible(False)
        self.error.setVisible(False)
        self.b_continue.setEnabled(False)
        default = str(self.settings.get("easy_output_format") or "PNG").upper()
        self.fmt.setCurrentText(default if default in OUTPUT_FORMATS else "PNG")
        self.report.setChecked(bool(self.settings.get("easy_save_report")))
        self.set_report_dir(str(self.settings.get("easy_report_dir") or ""))

    def output_format(self) -> str:
        return self.fmt.currentText()

    def retranslate(self) -> None:
        self.title.setText(f"01 · {tr('easy.step1')}")
        self.sub.setText(tr("easy.pilih_sub"))
        self.drop.retranslate()
        for k, key in zip(self.fact_keys, ("easy.selected_file", "easy.resolution", "easy.format", "easy.file_size")):
            k.setText(tr(key))
        self.fmt_label.setText(tr("easy.output_format"))
        self.fmt_help.setText(tr("easy.output_format_help"))
        self.fmt.setAccessibleName(tr("easy.output_format"))
        self.fmt.setAccessibleDescription(tr("easy.output_format_help"))
        self.rep_label.setText(tr("easy.research_report"))
        self.report.setText(amp(tr("easy.save_report")))
        self.report.setAccessibleName(tr("easy.save_report"))
        self.loc_caption.setText(tr("easy.report_location"))
        self.b_loc.setText(tr("easy.choose_location"))
        self.b_loc.setAccessibleName(tr("easy.choose_location"))
        self.b_default.setText(tr("easy.use_default"))
        self.b_continue.setText(tr("easy.continue"))
        self.b_continue.setAccessibleName(tr("easy.continue"))
        self.error.setText(tr("easy.not_image"))
        self._report_toggled(self.report.isChecked())


# ---------------------------------------------------------------------- 02 RUN
class RunPage(QWidget):
    runRequested = Signal()
    backRequested = Signal()
    retryRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.running = False
        self.phase = ""
        self.summary_text = ""
        col, v = _column()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(col)
        self.title = elabel("", "StepTitle", align=CENTER)
        v.addWidget(self.title)
        v.addSpacing(10)
        self.panel = QFrame()
        self.panel.setObjectName("Card")
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(28, 28, 28, 28)
        pv.setSpacing(14)
        self.state_title = elabel("", "StateTitle", wrap=True, align=CENTER)
        self.state_sub = elabel("", "StepSub", wrap=True, align=CENTER)
        self.summary = elabel("", "Help", wrap=True, align=CENTER)
        self.b_run = ebutton("", "primary")
        self.b_run.setMinimumWidth(380)
        self.b_run.setMinimumHeight(68)
        self.b_run.clicked.connect(self._run_clicked)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        self.phase_label = elabel("", "SectionLabel", align=CENTER)
        self.phase_label.setStyleSheet(f"color: {E['accent']}; font-size: 12pt;")
        self.phase_label.setVisible(False)
        self.timeline = PhaseTimeline()
        self.timeline.setVisible(False)
        for w in (self.state_title, self.state_sub, self.summary):
            pv.addWidget(w)
        pv.addSpacing(6)
        pv.addLayout(_hcenter(self.b_run))
        pv.addWidget(self.bar)
        pv.addWidget(self.phase_label)
        pv.addWidget(self.timeline)
        v.addWidget(self.panel)
        # error experience: friendly sentence, optional details, try again / back
        self.err = QFrame()
        self.err.setObjectName("ErrorBox")
        ev = QVBoxLayout(self.err)
        ev.setContentsMargins(22, 18, 22, 18)
        ev.setSpacing(10)
        self.err_title = elabel("", "ErrorTitle", wrap=True)
        self.err_msg = elabel("", wrap=True, selectable=True)
        self.b_details = ebutton("", "link")
        self.b_details.setCheckable(True)
        self.b_details.toggled.connect(lambda on: self.err_detail.setVisible(on))
        self.err_detail = QPlainTextEdit()
        self.err_detail.setReadOnly(True)
        self.err_detail.setMaximumHeight(140)
        self.err_detail.setVisible(False)
        self.b_retry = ebutton("", "primary")
        self.b_retry.setMinimumHeight(52)
        self.b_retry.clicked.connect(self.retryRequested)
        self.b_err_back = ebutton("")
        self.b_err_back.clicked.connect(self.backRequested)
        for w in (self.err_title, self.err_msg):
            ev.addWidget(w)
        dl = QHBoxLayout()
        dl.addWidget(self.b_details)
        dl.addStretch(1)
        ev.addLayout(dl)
        ev.addWidget(self.err_detail)
        bl = QHBoxLayout()
        bl.addStretch(1)
        bl.addWidget(self.b_err_back)
        bl.addWidget(self.b_retry)
        ev.addLayout(bl)
        self.err.setVisible(False)
        v.addWidget(self.err)
        # local environment (CPU / GPU only; no logs)
        self.env_title = elabel("", "SectionLabel", align=CENTER)
        self.env_line = elabel("", "Help", wrap=True, align=CENTER)
        self.env_note = elabel("", "Help", wrap=True, align=CENTER)
        v.addSpacing(8)
        v.addWidget(self.env_title)
        v.addWidget(self.env_line)
        v.addWidget(self.env_note)
        v.addSpacing(8)
        self.b_back = ebutton("")
        bb = QHBoxLayout()
        bb.addWidget(self.b_back)
        bb.addStretch(1)
        self.b_back.clicked.connect(self.backRequested)
        v.addLayout(bb)
        v.addStretch(1)
        self.compute = ("", "")
        self.retranslate()

    def _run_clicked(self) -> None:
        if not self.running:
            self.runRequested.emit()

    def set_summary(self, name: str, fmt: str) -> None:
        self.summary_text = f"{name}  →  {fmt}"
        self.summary.setText(self.summary_text)

    def set_compute(self, cpu: str, gpu: str) -> None:
        self.compute = (cpu, gpu)
        self.env_line.setText(tr("easy.compute_line", cpu=cpu or "?", gpu=gpu or tr("easy.gpu_none")))

    def set_ready(self) -> None:
        self.running = False
        self.err.setVisible(False)
        self.panel.setVisible(True)
        self.b_run.setEnabled(True)
        self.b_run.setText(tr("easy.run_transformation"))
        self.state_title.setText(tr("easy.ready"))
        self.state_sub.setText(tr("easy.ready_sub"))
        self.bar.setVisible(False)
        self.bar.setValue(0)
        self.phase_label.setVisible(False)
        self.timeline.setVisible(False)
        self.timeline.set_phase(-1)
        self.b_back.setEnabled(True)

    def set_running(self) -> None:
        self.running = True
        self.err.setVisible(False)
        self.b_run.setEnabled(False)
        self.b_run.setText(tr("easy.running"))
        self.b_run.setAccessibleName(tr("easy.running"))
        self.state_title.setText(tr("easy.analyzing_title"))
        self.state_sub.setText(tr("easy.analyzing_sub"))
        self.bar.setVisible(True)
        self.bar.setValue(0)
        self.phase_label.setVisible(True)
        self.timeline.setVisible(True)
        self.set_progress(0, PHASES[0])
        self.b_back.setEnabled(False)

    def set_progress(self, pct: int, phase: str) -> None:
        if not self.running:
            return
        self.bar.setValue(max(self.bar.value(), int(pct)))
        if phase in PHASES:
            self.phase = phase
            self.timeline.set_phase(PHASES.index(phase))
            self.phase_label.setText(tr(f"easy.phase.{phase}") + "...")
            self.bar.setAccessibleName(f"{tr('easy.analyzing_title')}: {self.bar.value()}% - {self.phase_label.text()}")

    def set_finished(self) -> None:
        self.running = False
        self.bar.setValue(100)
        self.timeline.set_phase(len(PHASES), done_all=True)

    def show_error(self, message: str, detail: str = "") -> None:
        self.running = False
        self.panel.setVisible(False)
        self.err.setVisible(True)
        self.err_title.setText(tr("easy.error_title"))
        self.err_msg.setText(message or tr("easy.error_generic"))
        self.err_detail.setPlainText(detail or "-")
        self.b_details.setChecked(False)
        self.b_details.setVisible(bool(detail))
        self.b_back.setEnabled(True)
        self.b_retry.setFocus()

    def retranslate(self) -> None:
        self.title.setText(f"02 · {tr('easy.step2')}")
        self.env_title.setText(tr("easy.local_env"))
        self.env_note.setText(tr("easy.local_note"))
        self.b_back.setText(tr("easy.back"))
        self.b_back.setAccessibleName(tr("easy.back"))
        self.b_err_back.setText(tr("easy.back"))
        self.b_retry.setText(tr("easy.try_again"))
        self.b_details.setText(tr("easy.details"))
        self.err_title.setText(tr("easy.error_title"))
        self.b_run.setAccessibleName(tr("easy.run_transformation"))
        self.bar.setAccessibleName(tr("easy.analyzing_title"))
        self.summary.setText(self.summary_text)
        if self.compute != ("", ""):
            self.set_compute(*self.compute)
        if self.running:
            self.b_run.setText(tr("easy.running"))
            self.state_title.setText(tr("easy.analyzing_title"))
            self.state_sub.setText(tr("easy.analyzing_sub"))
            if self.phase:
                self.set_progress(self.bar.value(), self.phase)
        elif not self.err.isVisible():
            self.set_ready()


# ---------------------------------------------------------------------- 03 OUTPUT
PIXEL_STATUS_KEYS = {"VERIFIED": ("✓", "easy.pixel_verified", "ok"),
                     "LOSSY (MEASURED)": ("≈", "easy.pixel_lossy", "warn"),
                     "CHANGED (MEASURED)": ("!", "easy.pixel_changed", "warn"),
                     "NOT COMPARABLE": ("–", "easy.pixel_nc", "muted")}


def pixel_status_text(out: dict) -> tuple[str, str]:
    sym, key, color = PIXEL_STATUS_KEYS.get(out.get("pixel_status", ""), ("?", "easy.pixel_nc", "muted"))
    text = f"{sym} {tr(key)}"
    if out.get("pixel_status") == "LOSSY (MEASURED)" and out.get("psnr_db") is not None:
        text += f" · PSNR {float(out['psnr_db']):.1f} dB"
    return text, E[color]


class OutputPage(QWidget):
    saveRequested = Signal()
    openResultRequested = Signal()
    openReportRequested = Signal()
    detailsRequested = Signal()
    anotherRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.res = None
        col, v = _column()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(col)
        self.title = elabel("", "StepTitle", align=CENTER)
        self.ready = elabel("", "StateTitle", align=CENTER)
        self.ready.setStyleSheet(f"color: {E['ok']};")
        v.addWidget(self.title)
        v.addWidget(self.ready)
        # large preview on the left, the result facts and actions on the right
        self.preview = elabel("", "Preview", align=CENTER)
        self.preview.setMinimumSize(300, 240)
        self.caption = elabel("", "CardTitle", align=CENTER)
        self.meta = elabel("", selectable=True)
        self.meta.setStyleSheet("font-size: 15pt; font-weight: 700;")
        self.pixel = elabel("", wrap=True)
        self.pixel.setStyleSheet("font-size: 12pt; font-weight: 700;")
        self.status = elabel("", "Help", wrap=True)
        self.b_save = ebutton("", "primary")
        self.b_save.clicked.connect(self.saveRequested)
        self.b_open = ebutton("")
        self.b_open.clicked.connect(self.openResultRequested)
        self.b_report = ebutton("")
        self.b_report.clicked.connect(self.openReportRequested)
        self.b_another = ebutton("")
        self.b_another.clicked.connect(self.anotherRequested)
        row = QHBoxLayout()
        row.setSpacing(24)
        lv = QVBoxLayout()
        lv.setSpacing(6)
        lv.addWidget(self.preview, 1)
        lv.addWidget(self.caption)
        row.addLayout(lv, 3)
        rv = QVBoxLayout()
        rv.setSpacing(10)
        for w in (self.meta, self.pixel, self.status):
            rv.addWidget(w)
        rv.addSpacing(8)
        for b in (self.b_save, self.b_open, self.b_report, self.b_another):
            rv.addWidget(b)
        rv.addStretch(1)
        row.addLayout(rv, 2)
        v.addLayout(row)
        self.saved = elabel("", "Success", wrap=True, align=CENTER, selectable=True)
        self.saved.setVisible(False)
        v.addWidget(self.saved)
        self.notice = elabel("", "Notice", wrap=True)
        self.notice.setVisible(False)
        v.addWidget(self.notice)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.c_image, self.c_prov, self.c_research = Card(), Card(), Card()
        for c in (self.c_prov, self.c_research, self.c_image):   # PROVENANCE · FINGERPRINT · PIXEL INTEGRITY
            cards.addWidget(c, 1)
        v.addLayout(cards)
        self.b_details = ebutton("", "link")
        self.b_details.clicked.connect(self.detailsRequested)
        v.addLayout(_hcenter(self.b_details))
        v.addStretch(1)
        self.retranslate()

    def show_result(self, res) -> None:
        self.res = res
        out, prov = res.output or {}, res.provenance or {}
        path = out.get("path", "")
        pm = thumbnail(path, QSize(480, 340)) if path else None
        if pm is not None:
            self.preview.setPixmap(pm)
        else:
            self.preview.setText(tr("easy.result_image"))
        self.preview.setAccessibleName(f"{tr('easy.result_image')}: {out.get('file_name', '')}")
        self.saved.setVisible(False)
        failed = res.counts()["failed"] or any(s.status in ("FAILED", "PARTIAL") for s in res.stages)
        self.notice.setVisible(bool(failed))
        self.b_report.setEnabled(bool(res.report_paths.get("html")) and Path(res.report_paths.get("html", "")).is_file())
        self._fill()

    def _fill(self) -> None:
        res = self.res
        if res is None:
            return
        out, prov = res.output or {}, res.provenance or {}
        fmt = out.get("easy_format") or out.get("format") or "-"
        res_text = f"{out.get('width')} × {out.get('height')}"
        self.meta.setText(f"{fmt}  ·  {res_text}")
        ptxt, pcol = pixel_status_text(out)
        self.pixel.setText(f"{tr('easy.pixel_status')}: {ptxt}")
        self.pixel.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {pcol};")
        self.status.setText(f"{tr('easy.output_format_label')}: {fmt}   ·   {tr('easy.status')}: "
                            f"{tr('easy.status_ready')}")
        c = res.counts()
        self.c_image.set_rows([(tr("easy.resolution"), res_text), (tr("easy.format"), fmt),
                               (tr("easy.pixel_status"), ptxt)])
        c2 = prov.get("c2pa_state", "-")
        if prov.get("c2pa_present"):
            c2 += f" · binding {prov.get('c2pa_hard_binding')}"
        self.c_prov.set_rows([("C2PA", c2), ("SynthID", prov.get("synthid_state", "-"))])
        self.c_research.set_rows([(tr("easy.methods_executed"), str(c["executed"])),
                                  (tr("easy.methods_unavailable"), str(c["unavailable"])),
                                  (tr("easy.experiment_id"), res.experiment_id)])

    def show_saved(self, path: str) -> None:
        self.saved.setText("✓ " + tr("easy.saved", name=str(path)))
        self.saved.setVisible(True)

    def retranslate(self) -> None:
        self.title.setText(f"03 · {tr('easy.step3')}")
        self.ready.setText("✓ " + tr("easy.result_ready"))
        self.caption.setText(tr("easy.result_image"))
        for b, key in ((self.b_save, "easy.save_result"), (self.b_open, "easy.open_result"),
                       (self.b_report, "easy.open_report"), (self.b_details, "easy.view_details"),
                       (self.b_another, "easy.run_another")):
            b.setText(tr(key))
            b.setAccessibleName(tr(key))
        self.notice.setText(tr("easy.some_unavailable"))
        self.c_image.title.setText(tr("easy.card_image"))
        self.c_prov.title.setText(tr("easy.card_provenance"))
        self.c_research.title.setText(tr("easy.card_research"))
        self._fill()


def cpu_text() -> str:
    return str(os.cpu_count() or "?")
