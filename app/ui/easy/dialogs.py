"""Easy Mode dialogs: minimal settings (with the application-mode switch) and the research-details viewer."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLineEdit, QMessageBox, QRadioButton, QTabWidget, QVBoxLayout)

from app.core.easy_mode_orchestrator import OUTPUT_FORMATS
from app.i18n import LANGUAGES, tr
from app.ui.easy.widgets import amp, ebutton, elabel
from app.ui.widgets.common import DataTable, KVTable, fmt_num


def confirm_restart(parent, mode: str) -> bool:
    """'Your interface mode will change after restart.'  [SAVE & RESTART] [CANCEL]"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(tr("easy.app_mode").title())
    target = tr("easy.mode_easy") if mode == "EASY" else tr("easy.mode_expert")
    box.setText(f"<b>{target}</b><br><br>{tr('easy.restart_note')}")
    ok = box.addButton(amp(tr("easy.save_restart")), QMessageBox.ButtonRole.AcceptRole)
    ok.setAccessibleName(tr("easy.save_restart"))
    cancel = box.addButton(amp(tr("easy.cancel")), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(ok)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is ok


class ModeChooser(QGroupBox):
    """APPLICATION MODE: ( ) Easy Mode  ( ) Expert Mode. Shared by both shells' settings."""

    def __init__(self, current: str) -> None:
        super().__init__(tr("easy.app_mode"))
        self.current = current.upper()
        lay = QHBoxLayout(self)
        lay.setSpacing(18)
        self.easy = QRadioButton(amp(tr("easy.mode_easy")))
        self.expert = QRadioButton(amp(tr("easy.mode_expert")))
        self.group = QButtonGroup(self)
        for b in (self.easy, self.expert):
            self.group.addButton(b)
            b.setAccessibleName(f"{tr('easy.app_mode')}: {b.text().replace('&&', '&')}")
            lay.addWidget(b)
        lay.addStretch(1)
        (self.easy if self.current == "EASY" else self.expert).setChecked(True)
        self.setAccessibleName(tr("easy.app_mode"))

    def chosen(self) -> str:
        return "EASY" if self.easy.isChecked() else "EXPERT"

    def changed(self) -> bool:
        return self.chosen() != self.current


class EasySettingsDialog(QDialog):
    """Language, mode, default output format, report on/off and default report location. Nothing else."""

    def __init__(self, ctl, parent=None) -> None:
        super().__init__(parent)
        self.ctl = ctl
        st = ctl.settings
        self.restart_mode: str | None = None
        self.language_changed = False
        self.setWindowTitle(tr("easy.settings"))
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addWidget(elabel(tr("easy.settings"), "StateTitle"))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.lang = QComboBox()
        for code, native, english, _rtl in LANGUAGES:
            self.lang.addItem(f"{native}  ({english})", code)
        i = self.lang.findData(st.get("language") or "en")
        self.lang.setCurrentIndex(i if i >= 0 else 0)
        self.lang.setAccessibleName(tr("easy.language"))
        form.addRow(tr("easy.language"), self.lang)
        self.fmt = QComboBox()
        self.fmt.addItems(list(OUTPUT_FORMATS))
        cur = str(st.get("easy_output_format") or "PNG").upper()
        self.fmt.setCurrentText(cur if cur in OUTPUT_FORMATS else "PNG")
        self.fmt.setAccessibleName(tr("easy.default_output"))
        form.addRow(tr("easy.default_output"), self.fmt)
        self.report = QCheckBox(amp(tr("easy.save_report")))
        self.report.setChecked(bool(st.get("easy_save_report")))
        form.addRow(tr("easy.research_report"), self.report)
        self.loc = QLineEdit(str(st.get("easy_report_dir") or ""))
        self.loc.setReadOnly(True)
        self.loc.setPlaceholderText(tr("easy.report_default"))
        self.loc.setAccessibleName(tr("easy.default_report_location"))
        b_loc = ebutton(tr("easy.choose_location"))
        b_loc.clicked.connect(self._choose)
        b_def = ebutton(tr("easy.use_default"), "link")
        b_def.clicked.connect(lambda: self.loc.setText(""))
        lr = QHBoxLayout()
        lr.addWidget(self.loc, 1)
        lr.addWidget(b_def)
        lr.addWidget(b_loc)
        form.addRow(tr("easy.default_report_location"), lr)
        root.addLayout(form)
        self.mode = ModeChooser(st.ui_mode())
        root.addWidget(self.mode)
        self.note = elabel(tr("easy.restart_note"), "Notice", wrap=True)
        self.note.setVisible(False)
        root.addWidget(self.note)
        bl = QHBoxLayout()
        bl.addStretch(1)
        self.b_cancel = ebutton(tr("easy.cancel"))
        self.b_cancel.clicked.connect(self.reject)
        self.b_save = ebutton(tr("easy.save"), "primary")
        self.b_save.setMinimumHeight(52)
        self.b_save.clicked.connect(self._save)
        self.b_save.setDefault(True)
        bl.addWidget(self.b_cancel)
        bl.addWidget(self.b_save)
        root.addLayout(bl)
        self.mode.group.buttonToggled.connect(lambda *_: self._mode_changed())

    def _mode_changed(self) -> None:
        changed = self.mode.changed()
        self.note.setVisible(changed)
        self.b_save.setText(tr("easy.save_restart") if changed else tr("easy.save"))

    def _choose(self) -> None:
        p = QFileDialog.getExistingDirectory(self, tr("easy.choose_location"), self.loc.text())
        if p:
            self.loc.setText(p)

    def _save(self) -> None:
        st = self.ctl.settings
        code = self.lang.currentData()
        self.language_changed = code != (st.get("language") or "en")
        st.set("language", code)
        st.set("easy_output_format", self.fmt.currentText())
        st.set("easy_save_report", self.report.isChecked())
        st.set("easy_report_dir", self.loc.text().strip())
        try:
            st.save()
        except OSError as exc:
            QMessageBox.warning(self, tr("easy.error_title"), str(exc))
            return
        self.restart_mode = self.mode.chosen() if self.mode.changed() else None
        self.accept()


class ResearchDetailsDialog(QDialog):
    """Expert-style detailed viewer of one Easy run, without switching the application into Expert Mode."""

    def __init__(self, res, ctl, parent=None) -> None:
        super().__init__(parent)
        self.res, self.ctl = res, ctl
        self.setWindowTitle(f"Research details - {res.experiment_id}")
        self.resize(1180, 760)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        head = elabel(f"{res.experiment_id}   ·   {res.status}   ·   {res.runtime_s:.1f} s", "SectionLabel")
        root.addWidget(head)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        c = res.counts()
        out, prov, inp = res.output or {}, res.provenance or {}, res.input or {}
        summary = KVTable()
        summary.set_rows([
            ("Status", res.status), ("Experiment ID", res.experiment_id), ("Experiment folder", res.experiment_dir),
            ("Input", f"{inp.get('name')}  {inp.get('format')}  {inp.get('width')}x{inp.get('height')}"),
            ("Input SHA-256 (before / after)", f"{inp.get('sha256')} / {inp.get('sha256_after', '-')}"),
            ("Original unchanged", str(res.original_unchanged)),
            ("Output", f"{out.get('file_name')}  {out.get('format')}  {out.get('width')}x{out.get('height')}"),
            ("Output SHA-256", out.get("sha256", "-")), ("Pixel verdict", out.get("pixel_verdict", "-")),
            ("Output content", out.get("content", "-")),
            ("Analysis region", f"{(res.analysis_region or {}).get('width')}x{(res.analysis_region or {}).get('height')} "
                                f"{(res.analysis_region or {}).get('note', '')}"),
            ("Reconstruction (controlled surrogate)", f"{res.reconstruction_status} {res.best_candidate}"),
            ("Methods: complete / no data / failed", f"{c['executed']} / {c['insufficient']} / {c['failed']}"),
            ("Skipped: unavailable / not in Easy",
             f"{c['skipped'] - c['not_in_easy_pipeline']} / {c['not_in_easy_pipeline']}"),
            ("Warnings", "; ".join(res.warnings) or "none")])
        tabs.addTab(summary, "Summary")
        cols = ["Method", "Name", "Stage", "Arm", "Decision", "Status", "Runtime s", "Readouts", "Reason / detail"]
        methods = DataTable(cols)
        methods.set_data(cols, [[m.method_id, m.name, m.stage, m.arm, m.decision, m.status,
                                 f"{m.runtime_s:.2f}" if m.decision == "RUN" else "-",
                                 "; ".join(f"{k}: {fmt_num(v, 3)}" for k, v in list((m.readouts or {}).items())[:4]),
                                 (f"shared execution with {m.shared_with}. " if m.shared_with else "")
                                 + (m.detail if m.decision == "RUN" else m.reason)] for m in res.methods])
        tabs.addTab(methods, f"Methods ({len(res.methods)})")
        ccols = ["Rank", "Method", "Recovery corr", "PSNR dB", "SSIM", "Agreement", "Score", "Validated", "Gate failures"]
        cand = DataTable(ccols)
        cand.set_data(ccols, [[x.rank, f"{x.method_id} {x.name}", fmt_num(x.metrics.get("candidate_vs_known_corr"), 3),
                               fmt_num(x.metrics.get("recon_psnr_db"), 2), fmt_num(x.metrics.get("recon_ssim"), 4),
                               fmt_num(x.metrics.get("method_agreement"), 3), fmt_num(x.total, 3),
                               "YES" if x.passed else "NO", "; ".join(x.gate_failures) or "-"] for x in res.candidates])
        tabs.addTab(cand, "Reconstruction candidates")
        cc = res.controlled_case or {}
        ctrl = KVTable()
        ctrl.set_rows([("Arm", "CONTROLLED SURROGATE RESEARCH (keyed local signal, ground truth known)"),
                       ("Host region", f"{cc.get('width')}x{cc.get('height')} at {cc.get('region_box')}"),
                       ("Surrogate", str(cc.get("surrogate", "-"))),
                       ("Detector z clean / embedded", f"{fmt_num(cc.get('detector_z_clean'), 2)} / "
                                                       f"{fmt_num(cc.get('detector_z_embedded'), 2)}"),
                       ("Valid ground truth", str(cc.get("valid_ground_truth", "-"))), ("Note", cc.get("note", "-"))])
        tabs.addTab(ctrl, "Controlled case")
        pv = KVTable()
        pv.set_rows([(k.replace("_", " "), str(v)) for k, v in prov.items()])
        tabs.addTab(pv, "Provenance")
        fam_cols = ["Code", "Taxonomy family", "Category", "Entries", "Investigated by"]
        fam = DataTable(fam_cols)
        fam.set_data(fam_cols, [[f["code"], f["family"], f["category"], f["taxonomy_entries"], ", ".join(f["methods"])]
                                for f in res.families])
        tabs.addTab(fam, "Fingerprint families")
        scols = ["#", "Stage", "Phase", "Status", "Runtime s", "Detail"]
        stages = DataTable(scols)
        stages.set_data(scols, [[f"{s.number:02d}", s.label, s.phase, s.status, f"{s.runtime_s:.2f}", s.detail]
                                for s in res.stages])
        tabs.addTab(stages, "Pipeline")
        bl = QHBoxLayout()
        b_dir = ebutton("Open experiment folder")
        b_dir.clicked.connect(lambda: res.experiment_dir and ctl.open_path(res.experiment_dir))
        bl.addWidget(b_dir)
        html = res.report_paths.get("html")
        if html and Path(html).is_file():
            b_rep = ebutton(tr("easy.open_report"))
            b_rep.clicked.connect(lambda: ctl.open_path(html))
            bl.addWidget(b_rep)
        bl.addStretch(1)
        b_close = ebutton(tr("btn.close"))
        b_close.clicked.connect(self.accept)
        b_close.setDefault(True)
        bl.addWidget(b_close)
        root.addLayout(bl)
