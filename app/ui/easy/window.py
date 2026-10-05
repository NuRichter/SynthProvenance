"""Easy Mode application shell: 01 PILIH -> 02 RUN -> 03 OUTPUT.

A separate main window, not the Expert research console with tabs hidden. It drives the
same AppController (and therefore the same engines) as Expert Mode through one call,
``ctl.run_easy``; the Easy Mode orchestrator decides everything technical.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from app import __version__
from app.core.easy_mode_orchestrator import EasyModeRequest, SaveRefused, default_result_name
from app.i18n import active, tr
from app.ui.easy.pages import OutputPage, PilihPage, RunPage, cpu_text
from app.ui.easy.widgets import StepIndicator, centered, ebutton, elabel
from app.utils.paths import resource_path

IMAGE_FILTER = "Images (*.jpg *.jpeg *.jpe *.jfif *.png *.webp *.tif *.tiff *.bmp *.gif);;All files (*)"
SAVE_FILTERS = {"PNG": "PNG (*.png)", "JPG": "JPEG (*.jpg *.jpeg)", "WEBP": "WEBP (*.webp)", "TIFF": "TIFF (*.tif *.tiff)",
                "BMP": "BMP (*.bmp)"}


class EasyWindow(QMainWindow):
    def __init__(self, ctl, quiet: bool = False) -> None:
        super().__init__()
        self.ctl, self.quiet = ctl, quiet
        self.errors: list[str] = []
        self.step = 0
        self.request: EasyModeRequest | None = None
        self.setObjectName("EasyWindow")
        self.setWindowTitle(f"SynthProvenance {__version__}  —  {tr('easy.mode_easy')}")
        icon = resource_path("assets", "icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        avail = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        self.resize(min(1060, int(avail.width() * 0.92)) if avail else 1060,
                    min(940, int(avail.height() * 0.92)) if avail else 900)
        self.setMinimumSize(720, 560)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # header: brand + settings (nothing technical)
        header = QFrame()
        header.setObjectName("EasyHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 14, 28, 14)
        bv = QVBoxLayout()
        bv.setSpacing(0)
        self.brand = elabel("SynthProvenance", "EasyBrand")
        self.tagline = elabel("", "EasyTag")
        bv.addWidget(self.brand)
        bv.addWidget(self.tagline)
        hl.addLayout(bv)
        hl.addStretch(1)
        self.mode_chip = elabel("", "EasyTag")
        hl.addWidget(self.mode_chip)
        hl.addSpacing(12)
        self.b_settings = ebutton("", "header")
        self.b_settings.clicked.connect(self.open_settings)
        hl.addWidget(self.b_settings)
        outer.addWidget(header)
        self.steps = StepIndicator()
        outer.addWidget(self.steps)
        # pages
        self.pilih = PilihPage(ctl.settings)
        self.run_page = RunPage()
        self.output = OutputPage()
        self.stack = QStackedWidget()
        for page in (self.pilih, self.run_page, self.output):
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setWidget(centered(page))
            if page is not self.pilih:
                self.stack.addWidget(sa)
                continue
            holder = QWidget()
            hv = QVBoxLayout(holder)
            hv.setContentsMargins(0, 0, 0, 0)
            hv.setSpacing(0)
            hv.addWidget(sa, 1)
            bar = QFrame()
            bar.setObjectName("ActionBar")
            bl = QHBoxLayout(bar)
            bl.setContentsMargins(24, 12, 24, 12)
            bl.addStretch(1)
            bl.addWidget(self.pilih.b_continue)
            bl.addStretch(1)
            hv.addWidget(bar)
            self.stack.addWidget(holder)
        outer.addWidget(self.stack, 1)
        foot = QFrame()
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(28, 6, 28, 8)
        self.footer = elabel("", "Footer")
        fl.addWidget(self.footer)
        fl.addStretch(1)
        fl.addWidget(elabel(f"v{__version__}", "Footer"))
        outer.addWidget(foot)
        self.setCentralWidget(central)
        # wiring
        self.pilih.chooseRequested.connect(self.choose_image)
        self.pilih.locationRequested.connect(self.choose_location)
        self.pilih.continueRequested.connect(self.go_run)
        self.run_page.runRequested.connect(self.start_run)
        self.run_page.backRequested.connect(lambda: self.go_step(0))
        self.run_page.retryRequested.connect(self.retry)
        self.output.saveRequested.connect(self.save_result)
        self.output.openResultRequested.connect(self.open_result)
        self.output.openReportRequested.connect(self.open_report)
        self.output.detailsRequested.connect(self.show_details)
        self.output.anotherRequested.connect(self.run_another)
        ctl.progress.connect(self._progress)
        ctl.easyChanged.connect(self._on_result)
        ctl.error.connect(self._on_error)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Open), self, activated=lambda: self.step == 0 and self.choose_image())
        QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self,
                  activated=lambda: self.step == 2 and self.save_result())
        self.setAcceptDrops(True)
        if active().rtl:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.retranslate()
        self.go_step(0)
        self._probe_compute()

    # -- navigation ----------------------------------------------------------
    def go_step(self, i: int) -> None:
        if i != 1 and self.run_page.running:
            return
        self.step = i
        self.stack.setCurrentIndex(i)
        self.steps.set_step(i)
        if i == 1:
            info = self.pilih.info or {}
            self.run_page.set_summary(info.get("name", ""), self.pilih.output_format())
            if not self.run_page.running:
                self.run_page.set_ready()
            self.run_page.b_run.setFocus()
        elif i == 0:
            self.pilih.drop.setFocus()
        elif i == 2:
            self.output.b_save.setFocus()

    def go_run(self) -> None:
        if self.pilih.info is not None:
            self.go_step(1)

    # -- step 01 -------------------------------------------------------------
    def choose_image(self) -> None:
        start = str(Path(self.pilih.info["path"]).parent) if self.pilih.info else ""
        path, _ = QFileDialog.getOpenFileName(self, tr("easy.choose_image"), start, IMAGE_FILTER)
        if path:
            self.pilih.set_file(path)
            self.pilih.b_continue.setFocus()

    def choose_location(self) -> None:
        p = QFileDialog.getExistingDirectory(self, tr("easy.choose_location"), self.pilih.report_dir)
        if p:
            self.pilih.set_report_dir(p)

    # -- step 02 -------------------------------------------------------------
    def start_run(self) -> None:
        info = self.pilih.info
        if info is None or self.run_page.running:
            return
        self.request = EasyModeRequest(info["path"], self.pilih.output_format(), self.pilih.report.isChecked(),
                                       self.pilih.report_dir if self.pilih.report.isChecked() else "")
        self.ctl.last_easy = None
        self.run_page.set_running()
        if not self.ctl.run_easy(self.request):
            self.run_page.show_error(tr("easy.error_busy"))

    def retry(self) -> None:
        self.run_page.set_ready()
        self.start_run()

    def _progress(self, pct: int, phase: str) -> None:
        if self.step == 1:
            self.run_page.set_progress(pct, phase)

    def _on_result(self) -> None:
        res = self.ctl.last_easy
        if res is None:
            return
        if res.ok:
            self.run_page.set_finished()
            self.output.show_result(res)
            self.go_step(2)
        else:
            self.errors.append(f"{res.error}: {res.error_detail}")
            self.run_page.show_error(res.error, res.error_detail)

    def _on_error(self, title: str, msg: str) -> None:
        self.errors.append(f"{title}: {msg}")
        if self.step == 1 and self.run_page.running:
            self.run_page.show_error(tr("easy.error_generic"), f"{title}: {msg}")

    # -- step 03 -------------------------------------------------------------
    def save_result(self) -> None:
        res = self.ctl.last_easy
        if res is None or not res.ok:
            return
        start_dir = Path(str((res.input or {}).get("path") or "")).parent
        fmt = (res.output or {}).get("easy_format") or "PNG"
        dest, _ = QFileDialog.getSaveFileName(self, tr("easy.save_result"), str(start_dir / default_result_name(res)),
                                              SAVE_FILTERS.get(fmt, ""))
        if dest:
            self.save_to(dest)

    def save_to(self, dest: str) -> Path | None:
        try:
            saved = self.ctl.save_easy_result(dest)
        except (SaveRefused, OSError) as exc:
            self.errors.append(f"save: {exc}")
            if not self.quiet:
                QMessageBox.warning(self, tr("easy.error_title"), f"{tr('easy.save_refused')}\n\n{exc}")
            return None
        self.output.show_saved(str(saved))
        return saved

    def open_result(self) -> None:
        res = self.ctl.last_easy
        p = (res.output or {}).get("path") if res else None
        if p and Path(p).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def open_report(self) -> None:
        res = self.ctl.last_easy
        p = (res.report_paths or {}).get("html") if res else None
        if p and Path(p).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def show_details(self) -> None:
        if self.ctl.last_easy is None:
            return
        from app.ui.easy.dialogs import ResearchDetailsDialog

        dlg = ResearchDetailsDialog(self.ctl.last_easy, self.ctl, self)
        if self.quiet:
            dlg.show()
            self._details = dlg
        else:
            dlg.exec()

    def run_another(self) -> None:
        self.ctl.last_easy = None
        self.request = None
        self.pilih.reset()
        self.run_page.set_summary("", "")
        self.run_page.set_ready()
        self.output.res = None
        self.go_step(0)

    # -- settings / language ----------------------------------------------
    def open_settings(self) -> None:
        if self.ctl.busy:
            return
        from app.ui.easy.dialogs import EasySettingsDialog

        dlg = EasySettingsDialog(self.ctl, self)
        if dlg.exec() != EasySettingsDialog.DialogCode.Accepted:
            return
        self.apply_language()
        if self.step == 0 and self.pilih.info is None:
            self.pilih.reset()
        if dlg.restart_mode:
            from app.ui.app_mode import save_and_restart

            ok, msg = save_and_restart(self.ctl, dlg.restart_mode)
            if not ok:
                QMessageBox.warning(self, tr("easy.error_title"), msg)

    def apply_language(self, code: str | None = None) -> None:
        from app.i18n import set_active

        set_active(code or self.ctl.settings.get("language") or "en")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if active().rtl else Qt.LayoutDirection.LeftToRight)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(f"SynthProvenance {__version__}  —  {tr('easy.mode_easy')}")
        self.tagline.setText(tr("easy.subtitle"))
        self.mode_chip.setText(tr("easy.mode_easy").upper())
        self.b_settings.setText("⚙  " + tr("easy.settings"))
        self.b_settings.setAccessibleName(tr("easy.settings"))
        self.footer.setText(tr("easy.footer"))
        self.steps.set_step(self.step)
        for page in (self.pilih, self.run_page, self.output):
            page.retranslate()

    # -- environment (CPU / GPU only) ---------------------------------------
    def _probe_compute(self) -> None:
        from app.ui.widgets.worker import Worker

        def job(progress):
            from app.core.synthid_research_engine import gpu_info

            return gpu_info().get("gpu") or ""

        self.run_page.set_compute(cpu_text(), "…")
        w = Worker(job)
        self._compute_signals = w.signals
        w.signals.done.connect(lambda g: self.run_page.set_compute(cpu_text(), "" if str(g).startswith(("none", "probe", "unknown")) else str(g).split(",")[0].strip()))
        w.signals.failed.connect(lambda _m: self.run_page.set_compute(cpu_text(), ""))
        self.ctl.pool.start(w)

    # -- keyboard / drag & drop ---------------------------------------------
    def keyPressEvent(self, e) -> None:  # noqa: N802
        key = e.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            fw = QApplication.focusWidget()
            if isinstance(fw, QPushButton) and fw.isEnabled() and fw.isVisible():
                fw.click()
            else:   # like a dialog's default button (an open drop-down list consumes Enter itself)
                self.primary_action()
            e.accept()
            return
        if key == Qt.Key.Key_Escape:
            if self.step == 1 and not self.run_page.running:
                self.go_step(0)
            e.accept()
            return
        super().keyPressEvent(e)

    def primary_action(self) -> None:
        if self.step == 0 and self.pilih.b_continue.isEnabled():
            self.go_run()
        elif self.step == 1 and not self.run_page.running and self.run_page.panel.isVisible():
            self.start_run()
        elif self.step == 2:
            self.save_result()

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self.step == 0 and self.pilih.drop._local_file(e):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        path = self.pilih.drop._local_file(e)
        if self.step == 0 and path:
            self.pilih.set_file(path)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.ctl.busy and not self.quiet:
            if QMessageBox.question(self, "SynthProvenance", tr("easy.quit_running")) != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.ctl.pool.waitForDone(5000)
        super().closeEvent(e)

