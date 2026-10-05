from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QRadioButton, QSpinBox)

from app.services.metadata_sanitizer import PROFILES
from app.ui.views.base import View, row
from app.ui.widgets.common import DataTable, KVTable, Panel, banner, button, label
from app.utils import netguard
from app.utils.memory import fmt_bytes, process_rss, system_memory
from app.utils.system import system_info


def _path_row(edit: QLineEdit, parent, directory: bool = False):
    b = button("Browse...")

    def pick():
        if directory:
            p = QFileDialog.getExistingDirectory(parent, "Choose directory", edit.text())
        else:
            p, _ = QFileDialog.getOpenFileName(parent, "Choose executable", edit.text())
        if p:
            edit.setText(p)
    b.clicked.connect(pick)
    return row(edit, b)


class SettingsView(View):
    title = "Settings"
    subtitle = "All processing is local. Optional external tools are detected, never downloaded."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        self.root.addWidget(banner(netguard.policy_text(), info=True))
        top = QHBoxLayout()
        p = Panel("Workspace")
        self.ws = QLineEdit()
        p.add(_path_row(self.ws, self, directory=True))
        b_apply = button("Apply workspace")
        b_apply.clicked.connect(lambda: ctl.set_workspace(self.ws.text().strip()))
        b_open = button("OPEN WORKSPACE")
        b_open.clicked.connect(lambda: ctl.open_path(ctl.workspace.root))
        b_exp = button("OPEN EXPERIMENT FOLDER")
        b_exp.clicked.connect(lambda: ctl.experiment and ctl.open_path(ctl.experiment_dir()))
        p.add(row(b_apply, b_open, b_exp, None))
        p.add(label("Leave empty for the default: <app folder>\\workspace when writable (portable), otherwise the "
                    "per-user application data folder.", "Muted", wrap=True))
        top.addWidget(p, 1)
        q = Panel("Processing")
        f = QFormLayout()
        self.max_mp = QSpinBox()
        self.max_mp.setRange(0, 100000)
        self.max_mp.setSuffix(" MP")
        self.max_mp.setToolTip("0 = no fixed limit; decoding is admitted by the available-memory budget.")
        self.stat_px = QSpinBox()
        self.stat_px.setRange(1, 1000)
        self.stat_px.setSuffix(" MP")
        self.profile = QComboBox()
        self.profile.addItems(list(PROFILES))
        f.addRow("Maximum megapixels (0 = memory-based)", self.max_mp)
        f.addRow("Statistics analysis cap (display stats only)", self.stat_px)
        f.addRow("Default sanitization profile", self.profile)
        q.add(f)
        top.addWidget(q, 1)
        self.root.addLayout(top)
        lang_panel = Panel("Interface")
        lf = QFormLayout()
        from app.i18n import LANGUAGES
        self.lang = QComboBox()
        for code, native, english, _rtl in LANGUAGES:
            self.lang.addItem(f"{native}  ({english})", code)
        self.lang.setToolTip("UI language. Technical and method names stay in English (canonical term preserved); "
                             "untranslated labels fall back to English.")
        self.lang.currentIndexChanged.connect(self._change_language)
        from app.ui.themes import THEME_NAMES
        self.theme = QComboBox()
        self.theme.addItems(list(THEME_NAMES))
        self.theme.setToolTip("Colour theme (presentation only; applied immediately). Easy Mode uses its own light look.")
        self.theme.currentTextChanged.connect(self._change_theme)
        lf.addRow("Theme", self.theme)
        lf.addRow("Language", self.lang)
        from app.core.easy_mode_orchestrator import OUTPUT_FORMATS
        self.easy_fmt = QComboBox()
        self.easy_fmt.addItems(list(OUTPUT_FORMATS))
        self.easy_report = QCheckBox("Save research report")
        self.easy_dir = QLineEdit()
        self.easy_dir.setPlaceholderText("empty = the experiment folder")
        lf.addRow("Easy Mode default output format", self.easy_fmt)
        lf.addRow("Easy Mode research report", self.easy_report)
        lf.addRow("Easy Mode default report location", _path_row(self.easy_dir, self, directory=True))
        b_easy = button("Save Easy Mode defaults")
        b_easy.clicked.connect(self._save_easy_defaults)
        lf.addRow("", row(b_easy, None))
        lang_panel.add(lf)
        self.lang_note = label("", "Muted", wrap=True)
        lang_panel.add(self.lang_note)
        self.root.addWidget(lang_panel)
        # APPLICATION MODE: a true application-layout switch (persist, close, relaunch into the other shell)
        mp = Panel("User Interface Mode")
        mp.add(label("APPLICATION MODE", "LayerTitle"))
        self.mode_easy = QRadioButton("Easy Mode  -  three steps: PILIH, RUN, OUTPUT (the engine decides the methods)")
        self.mode_expert = QRadioButton("Expert Mode  -  this research console (all labs, methods and parameters)")
        self.mode_group = QButtonGroup(self)
        for b_ in (self.mode_easy, self.mode_expert):
            self.mode_group.addButton(b_)
            mp.add(b_)
        self.mode_note = label("Your interface mode will change after restart.", "Banner", wrap=True)
        self.mode_note.setVisible(False)
        mp.add(self.mode_note)
        self.b_restart = button("SAVE && RESTART", primary=True)
        self.b_restart.setAccessibleName("SAVE & RESTART")
        self.b_restart.clicked.connect(self._save_restart)
        self.b_mode_cancel = button("CANCEL")
        self.b_mode_cancel.clicked.connect(self._mode_cancel)
        mp.add(row(self.b_restart, self.b_mode_cancel, None))
        self.mode_group.buttonToggled.connect(lambda *_: self._mode_changed())
        self.root.insertWidget(2, mp)   # directly under the title and the network banner
        t = Panel("Optional local engines")
        g = QFormLayout()
        self.use_exif = QCheckBox("Use ExifTool when available (read-only extraction)")
        self.exif = QLineEdit()
        self.c2pa = QLineEdit()
        self.use_c2py = QCheckBox("Use c2pa-python when installed")
        self.synth = QLineEdit()
        self.synth.setPlaceholderText("Path to a local SynthID verification engine (see tools/README.md)")
        g.addRow(self.use_exif)
        g.addRow("ExifTool path", _path_row(self.exif, self))
        g.addRow("c2patool path", _path_row(self.c2pa, self))
        g.addRow(self.use_c2py)
        g.addRow("SynthID engine", _path_row(self.synth, self))
        t.add(g)
        b_save = button("Save settings and re-detect engines", primary=True)
        b_save.clicked.connect(self._save)
        t.add(row(b_save, None))
        self.tools = DataTable(["Engine", "State", "Detail"])
        self.tools.setMinimumHeight(220)
        t.add(self.tools)
        self.root.addWidget(t)
        s = Panel("System")
        self.sys = KVTable()
        self.sys.setMinimumHeight(220)
        s.add(self.sys)
        self.root.addWidget(s, 1)

    def refresh(self) -> None:
        st = self.ctl.settings
        self.ws.setText(str(st.get("workspace") or ""))
        self.max_mp.setValue(int(st.get("max_megapixels") or 0))
        self.stat_px.setValue(max(1, int((st.get("statistics_max_pixels") or 16_000_000) / 1_000_000)))
        self.profile.setCurrentText(st.get("default_sanitize_profile") or "BALANCED")
        self.use_exif.setChecked(bool(st.get("use_exiftool")))
        self.exif.setText(st.get("exiftool_path") or "")
        self.c2pa.setText(st.get("c2patool_path") or "")
        self.use_c2py.setChecked(bool(st.get("use_c2pa_python")))
        cmd = st.get("synthid_engine_command") or []
        self.synth.setText(cmd[0] if isinstance(cmd, list) and cmd else str(cmd or ""))
        from app.i18n import active
        self.lang.blockSignals(True)
        i = self.lang.findData(st.get("language") or "en")
        self.lang.setCurrentIndex(i if i >= 0 else 0)
        self.lang.blockSignals(False)
        self.mode_group.blockSignals(True)
        (self.mode_easy if st.ui_mode() == "EASY" else self.mode_expert).setChecked(True)
        self.mode_group.blockSignals(False)
        self._mode_changed()
        self.theme.blockSignals(True)
        self.theme.setCurrentText(str(st.get("theme") or "Dark Laboratory"))
        self.theme.blockSignals(False)
        self.easy_fmt.setCurrentText(str(st.get("easy_output_format") or "PNG").upper())
        self.easy_report.setChecked(bool(st.get("easy_save_report")))
        self.easy_dir.setText(str(st.get("easy_report_dir") or ""))
        self.lang_note.setText(f"Active language core-UI completeness: {active().completeness():.0%}. Untranslated labels "
                               "show English. Scientific terms stay English by design.")
        self.tools.set_data(["Engine", "State", "Detail"], [list(r) for r in self.ctl.engine_status()])
        info = system_info()
        mem = system_memory()
        rows = [["Active workspace", str(self.ctl.workspace.root)], ["Settings file", str(st.path)],
                ["OS", info.get("os")], ["Machine", info.get("machine")], ["Python", info.get("python")],
                ["Qt", info.get("qt")], ["Frozen build", info.get("frozen")],
                ["RAM total / available", f"{fmt_bytes(mem.get('total'))} / {fmt_bytes(mem.get('available'))}"],
                ["Process memory", fmt_bytes(process_rss())], ["Network", netguard.policy_text()]]
        rows += [[f"package {k}", v] for k, v in (info.get("packages") or {}).items()]
        self.sys.set_rows(rows)

    def _change_language(self) -> None:
        from app.i18n import set_active
        code = self.lang.currentData()
        set_active(code)
        self.ctl.settings.set("language", code)
        try:
            self.ctl.settings.save()
        except OSError:
            pass
        if hasattr(self.win, "retranslate"):
            self.win.retranslate()
        self.ctl.info.emit(f"Language set to {code}. Scientific terms remain in English.")
        self._mark()

    def _change_theme(self, name: str) -> None:
        from PySide6.QtWidgets import QApplication
        from app.ui import theme as T
        self.ctl.settings.set("theme", name)
        try:
            self.ctl.settings.save()
        except OSError:
            pass
        app = QApplication.instance()
        if app is not None:
            T.apply(app, name)
        self.ctl.info.emit(f"Theme: {name}")

    def _chosen_mode(self) -> str:
        return "EASY" if self.mode_easy.isChecked() else "EXPERT"

    def _mode_changed(self) -> None:
        changed = self._chosen_mode() != self.ctl.settings.ui_mode()
        self.mode_note.setVisible(changed)
        self.b_restart.setEnabled(changed)
        self.b_mode_cancel.setEnabled(changed)

    def _mode_cancel(self) -> None:
        (self.mode_easy if self.ctl.settings.ui_mode() == "EASY" else self.mode_expert).setChecked(True)

    def _save_restart(self) -> None:
        from app.ui.app_mode import save_and_restart

        ok, msg = save_and_restart(self.ctl, self._chosen_mode())
        if not ok:
            self.ctl.error.emit("Application mode", msg)

    def _save_easy_defaults(self) -> None:
        st = self.ctl.settings
        st.set("easy_output_format", self.easy_fmt.currentText())
        st.set("easy_save_report", self.easy_report.isChecked())
        st.set("easy_report_dir", self.easy_dir.text().strip())
        try:
            st.save()
        except OSError as exc:
            self.ctl.error.emit("Settings", f"Could not save settings: {exc}")
            return
        self.ctl.info.emit("Easy Mode defaults saved")

    def _save(self) -> None:
        st = self.ctl.settings
        st.set("max_megapixels", self.max_mp.value())
        st.set("statistics_max_pixels", self.stat_px.value() * 1_000_000)
        st.set("default_sanitize_profile", self.profile.currentText())
        st.set("use_exiftool", self.use_exif.isChecked())
        st.set("exiftool_path", self.exif.text().strip())
        st.set("c2patool_path", self.c2pa.text().strip())
        st.set("use_c2pa_python", self.use_c2py.isChecked())
        st.set("synthid_engine_command", [self.synth.text().strip()] if self.synth.text().strip() else [])
        try:
            st.save()
        except OSError as exc:
            self.ctl.error.emit("Settings", f"Could not save settings: {exc}")
        self.ctl.apply_settings()
        self.ctl.info.emit("Settings saved; engines re-detected")
        self._mark()
