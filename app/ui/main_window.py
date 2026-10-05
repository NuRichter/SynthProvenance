"""Main window: top bar, navigation, views, status bar, audit dock."""
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from app import __org__, __subtitle__, __version__
from app.i18n import tr
from app.ui.theme import mono_font
from app.ui.views.about_view import AboutView
from app.ui.views.c2pa_view import C2PAView
from app.ui.views.comparison_view import ComparisonView
from app.ui.views.dashboard import DashboardView
from app.ui.views.fingerprint_view import FingerprintLabView
from app.ui.views.format_lab import FormatLabView
from app.ui.views.inspector import InspectorView
from app.ui.views.integrity_view import IntegrityView
from app.ui.views.library_view import ResearchLibraryView
from app.ui.views.matrix_view import MatrixView
from app.ui.views.report_view import ReportView
from app.ui.views.separation_view import SignalSeparationView
from app.ui.views.settings_view import SettingsView
from app.ui.views.synthid_view import SynthIDResearchLabView
from app.ui.views.taxonomy_view import TaxonomyView
from app.ui.views.transformation_lab import TransformationLabView
from app.ui.widgets.common import Badge, label
from app.utils.memory import fmt_bytes, process_rss, system_memory
from app.utils.paths import resource_path

NAV = [("Dashboard", DashboardView), ("Forensic Inspector", InspectorView), ("C2PA Provenance", C2PAView),
       ("SynthID Research Lab", SynthIDResearchLabView), ("Fingerprint Research Lab", FingerprintLabView),
       ("Fingerprint Taxonomy", TaxonomyView), ("Research Library", ResearchLibraryView),
       ("Signal Separation", SignalSeparationView), ("Transformation Lab", TransformationLabView),
       ("Format Conversion", FormatLabView), ("Pixel Integrity", IntegrityView), ("Comparison", ComparisonView),
       ("Experiment Matrix", MatrixView), ("Research Report", ReportView), ("About This Program", AboutView),
       ("Settings", SettingsView)]
IMAGE_FILTER = "Images (*.jpg *.jpeg *.jpe *.jfif *.png *.webp *.tif *.tiff *.bmp *.gif);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self, ctl, quiet: bool = False) -> None:
        super().__init__()
        self.ctl, self.quiet = ctl, quiet
        self.errors: list[str] = []
        self.setWindowTitle(f"SynthProvenance {__version__}  \u2014  {__subtitle__}")
        icon = resource_path("assets", "icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1480, 940)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 8, 16, 8)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.addWidget(label("SynthProvenance", "AppTitle"))
        tv.addWidget(label(__subtitle__, "Muted"))
        tl.addLayout(tv)
        tl.addStretch(1)
        self.exp_label = label("EXPERIMENT: NONE", mono=True, selectable=True)
        tl.addWidget(self.exp_label)
        tl.addSpacing(18)
        tl.addWidget(label("Research Mode:", "Muted"))
        tl.addWidget(Badge("ACTIVE"))
        tl.addSpacing(18)
        env = QVBoxLayout()
        env.setSpacing(0)
        env.addWidget(label("Environment:", "Muted"))
        env.addWidget(label("Insyide Innovations \u00b7 NuRichter Workspace"))
        tl.addLayout(env)
        outer.addWidget(top)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(208)
        self.stack = QStackedWidget()
        self.views: dict[str, QWidget] = {}
        for name, cls in NAV:
            self.nav.addItem(tr(f"nav.{name}"))
            view = cls(ctl, self)
            self.views[name] = view
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setWidget(view)
            self.stack.addWidget(sa)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        foot = QFrame()
        foot.setObjectName("FooterBar")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(16, 4, 16, 4)
        fl.addWidget(label(f"SynthProvenance  \u00b7  {__subtitle__}  \u00b7  {__org__}", "Footer"))
        fl.addStretch(1)
        fl.addWidget(label("LOCAL RESEARCH ENVIRONMENT", "Footer"))
        outer.addWidget(foot)
        self.setCentralWidget(central)
        # status bar
        sb = self.statusBar()
        self.op_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.elapsed_label = QLabel("")
        self.ram_label = QLabel("")
        sb.addWidget(self.op_label, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.elapsed_label)
        sb.addPermanentWidget(self.ram_label)
        sb.addPermanentWidget(Badge("LOCAL-ONLY"))
        # audit dock
        self.audit_view = QPlainTextEdit()
        self.audit_view.setReadOnly(True)
        self.audit_view.setFont(mono_font(8.5))
        self.audit_view.setMaximumBlockCount(5000)
        dock = QDockWidget("AUDIT LOG", self)
        dock.setObjectName("AuditDock")
        dock.setWidget(self.audit_view)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        dock.setMinimumHeight(120)
        self._menus(dock)
        # timers & signals
        self.timer = QElapsedTimer()
        self.tick = QTimer(self)
        self.tick.setInterval(200)
        self.tick.timeout.connect(self._elapsed)
        self.ram = QTimer(self)
        self.ram.setInterval(2000)
        self.ram.timeout.connect(self._ram)
        self.ram.start()
        self._ram()
        ctl.busyChanged.connect(self._busy)
        ctl.progress.connect(self._progress)
        ctl.auditEvent.connect(lambda ev: self.audit_view.appendPlainText(ev.to_line()))
        ctl.error.connect(self._error)
        ctl.info.connect(lambda m: self.statusBar().showMessage(m, 8000))
        ctl.experimentChanged.connect(self._exp)
        self.nav.setCurrentRow(0)

    def _menus(self, dock) -> None:
        m = self.menuBar().addMenu("&File")
        for text, key, fn in (("Open Image...", QKeySequence.StandardKey.Open, self.open_image_dialog),
                              ("Open Demo Fixture", None, self.ctl.open_demo_fixture),
                              ("Compare External File...", None, self.compare_dialog),
                              ("Quit", QKeySequence.StandardKey.Quit, self.close)):
            a = QAction(text, self)
            if key is not None:
                a.setShortcut(key)
            a.triggered.connect(fn)
            m.addAction(a)
        v = self.menuBar().addMenu("&View")
        v.addAction(dock.toggleViewAction())
        for i, (name, _c) in enumerate(NAV):
            a = QAction(name, self)
            a.setShortcut(f"Ctrl+{i + 1}" if i < 9 else "")
            a.triggered.connect(lambda _c=False, n=name: self.go(n))
            v.addAction(a)
        r = self.menuBar().addMenu("&Research")
        wiz = QAction("Research Wizard...", self)
        wiz.setShortcut("Ctrl+W")
        wiz.triggered.connect(self.open_wizard)
        r.addAction(wiz)
        for text, nav_name in (("Fingerprint Research Lab", "Fingerprint Research Lab"),
                               ("Fingerprint Taxonomy", "Fingerprint Taxonomy"),
                               ("Research Library (HERE OUR HERO)", "Research Library")):
            a = QAction(text, self)
            a.triggered.connect(lambda _c=False, n=nav_name: self.go(n))
            r.addAction(a)
        h = self.menuBar().addMenu("&Help")
        a = QAction("About This Program", self)
        a.triggered.connect(lambda: self.go("About This Program"))
        h.addAction(a)
        a2 = QAction("About (dialog)", self)
        a2.triggered.connect(self._about)
        h.addAction(a2)

    def open_wizard(self) -> None:
        from app.ui.wizard import ResearchWizard

        ResearchWizard(self.ctl, self).show()

    def retranslate(self) -> None:
        """Re-apply the active language to the navigation labels (called when the language changes)."""
        for i, (name, _c) in enumerate(NAV):
            it = self.nav.item(i)
            if it is not None:
                it.setText(tr(f"nav.{name}"))

    def go(self, name: str) -> None:
        names = [n for n, _c in NAV]
        if name in names:
            self.nav.setCurrentRow(names.index(name))

    def open_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open image", "", IMAGE_FILTER)
        if path:
            self.ctl.open_image(path)

    def compare_dialog(self) -> None:
        if self.ctl.source is None:
            self._error("No image", "Open the original image first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Compare with external file", "", IMAGE_FILTER)
        if path:
            self.ctl.compare_external(path)

    def _busy(self, busy: bool, name: str) -> None:
        self.progress.setVisible(busy)
        self.progress.setValue(0)
        if busy:
            self.op_label.setText(name)
            self.timer.start()
            self.tick.start()
        else:
            self.tick.stop()
            self.op_label.setText(f"Ready (last operation {self.timer.elapsed() / 1000:.1f} s)")

    def _progress(self, pct: int, text: str) -> None:
        self.progress.setValue(max(0, min(100, pct)))
        self.op_label.setText(text)

    def _elapsed(self) -> None:
        self.elapsed_label.setText(f"elapsed {self.timer.elapsed() / 1000:.1f} s")

    def _ram(self) -> None:
        mem = system_memory()
        self.ram_label.setText(f"RAM process {fmt_bytes(process_rss())} | available {fmt_bytes(mem.get('available'))}")

    def _exp(self) -> None:
        exp = self.ctl.experiment
        self.exp_label.setText(f"EXPERIMENT: {exp.experiment_id}" if exp else "EXPERIMENT: NONE")

    def _error(self, title: str, msg: str) -> None:
        self.errors.append(f"{title}: {msg}")
        if not self.quiet:
            QMessageBox.warning(self, title, msg)

    def _about(self) -> None:
        QMessageBox.about(self, "About SynthProvenance",
                          f"<b>SynthProvenance {__version__}</b><br>{__subtitle__}<br><br>Faculty of Computer Science<br>"
                          "Insyide Innovations Lab<br>NuRichter Workspace<br><br>PRIVATE SCIENTIFIC RESEARCH SOFTWARE<br>"
                          "LOCAL RESEARCH ENVIRONMENT: no network access, no uploads, no telemetry.<br><br>"
                          "WE DO NOT GUESS. WE MEASURE.")

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.ctl.busy and not self.quiet:
            if QMessageBox.question(self, "Operation running", "An operation is still running. Quit anyway?") != \
                    QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.ctl.pool.waitForDone(5000)
        super().closeEvent(e)
