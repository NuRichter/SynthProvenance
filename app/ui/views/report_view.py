from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPlainTextEdit, QTextBrowser, QVBoxLayout

from app.services.report_service import build_report, render_html
from app.ui.views.base import View, row
from app.ui.widgets.common import Panel, button, label

EXPORTS = [("PDF", "pdf", "PDF (*.pdf)"), ("JSON", "json", "JSON (*.json)"), ("CSV", "csv", "CSV (*.csv)"),
           ("HTML", "html", "HTML (*.html)"), ("PNG", "png", "PNG (*.png)")]


class ReportView(View):
    title = "Research Report"
    subtitle = ("Scientifically cautious by design: no statement that an image is or is not AI-generated, and no prediction "
                "of platform behaviour.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        top = QHBoxLayout()
        p = Panel("Research objective and notes (stored in experiment.json)")
        self.objective = QPlainTextEdit()
        self.objective.setMaximumHeight(80)
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(80)
        self.notes.setPlaceholderText("Researcher notes, hypotheses, conditions ...")
        b_save = button("Save")
        b_save.clicked.connect(lambda: ctl.update_notes(self.objective.toPlainText(), self.notes.toPlainText()))
        p.add(self.objective)
        p.add(self.notes)
        p.add(row(b_save, None))
        top.addWidget(p, 3)
        q = Panel("Export")
        v = QVBoxLayout()
        for text, fmt, filt in EXPORTS:
            b = button(f"Export {text}")
            b.clicked.connect(lambda _c=False, f=fmt, fl=filt: self._export(f, fl))
            v.addWidget(b)
        bz = button("Export experiment.zip", primary=True)
        bz.clicked.connect(self._bundle)
        bo = button("Open experiment folder")
        bo.clicked.connect(lambda: ctl.experiment and ctl.open_path(ctl.experiment_dir()))
        v.addWidget(bz)
        v.addWidget(bo)
        q.add(v)
        top.addWidget(q, 1)
        self.root.addLayout(top)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.root.addWidget(label("PREVIEW", "PanelTitle"))
        self.root.addWidget(self.preview, 1)

    def refresh(self) -> None:
        exp = self.ctl.experiment
        if exp is None:
            self.preview.setPlainText("Start an experiment to generate a report.")
            return
        self.objective.setPlainText(exp.objective)
        self.notes.setPlainText(exp.notes)
        self.preview.setHtml(render_html(build_report(exp, self.ctl.audit.events(), self.ctl.synthid.status())))

    def _export(self, fmt: str, filt: str) -> None:
        exp = self.ctl.experiment
        if exp is None:
            self.ctl.error.emit("No experiment", "Start an experiment first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()} report",
                                              str(self.ctl.workspace.reports_dir / f"{exp.experiment_id}_report.{fmt}"), filt)
        if path:
            self.ctl.export_report(fmt, path)

    def _bundle(self) -> None:
        exp = self.ctl.experiment
        if exp is None:
            self.ctl.error.emit("No experiment", "Start an experiment first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export experiment.zip",
                                              str(self.ctl.workspace.exports_dir / f"{exp.experiment_id}_experiment.zip"), "ZIP (*.zip)")
        if path:
            self.ctl.export_bundle(path)
