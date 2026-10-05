from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox

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
        self.mode = QComboBox()
        self.mode.addItems(["EASY", "EXPERT"])
        self.mode.setToolTip("EASY: drop image, pick a research goal, run. EXPERT: full method/parameter control.")
        self.mode.currentTextChanged.connect(self._change_mode)
        lf.addRow("Language", self.lang)
        lf.addRow("UI mode", self.mode)
        lang_panel.add(lf)
        self.lang_note = label("", "Muted", wrap=True)
        lang_panel.add(self.lang_note)
        self.root.addWidget(lang_panel)
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
        self.mode.blockSignals(True)
        self.mode.setCurrentText(str(st.get("ui_mode") or "EASY").upper())
        self.mode.blockSignals(False)
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

    def _change_mode(self) -> None:
        self.ctl.settings.set("ui_mode", self.mode.currentText())
        try:
            self.ctl.settings.save()
        except OSError:
            pass
        self.ctl.uiModeChanged.emit(self.mode.currentText())

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
