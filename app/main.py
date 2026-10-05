"""SynthProvenance entry point.

    SynthProvenance.exe [image]            start the GUI (optionally opening an image)
    --self-test [--self-test-output F]     headless pipeline verification (JSON result)
    --smoke-gui [--smoke-output F]         start the GUI, run a short scripted experiment, exit
    --version
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # executed as a script: make the project root importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _guard_stdio() -> None:
    # Windowed (no-console) builds have no stdout/stderr; give them a sink.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def _app_user_model_id() -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NuRichter.SynthProvenance.1")
        except Exception:  # noqa: BLE001
            pass


def _parse(argv):
    p = argparse.ArgumentParser(prog="SynthProvenance", add_help=True)
    p.add_argument("image", nargs="?", help="image to open at start-up")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--self-test-output")
    p.add_argument("--smoke-gui", action="store_true")
    p.add_argument("--smoke-output")
    p.add_argument("--version", action="store_true")
    p.add_argument("--workspace", help="override the workspace directory for this session")
    return p.parse_args(argv)


def _smoke(app, win, ctl, output: str | None) -> None:
    from PySide6.QtCore import QTimer

    t0 = time.perf_counter()
    result = {"ok": False, "steps": [], "errors": win.errors}
    state = {"phase": "open"}

    def done(ok: bool, why: str = "") -> None:
        from app.ui.views.base import REFRESH_ERRORS

        result["view_errors"] = list(REFRESH_ERRORS)
        ok = ok and not REFRESH_ERRORS
        result["ok"] = ok and not any("Transformation not completed" in e for e in win.errors)
        result["reason"] = why
        result["duration_s"] = round(time.perf_counter() - t0, 2)
        if output:
            Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        QTimer.singleShot(200, app.quit)

    def visit_all():
        from app.ui.main_window import NAV

        for name, _c in NAV:
            win.go(name)
            app.processEvents()
            win.views[name]._do_refresh()
            result["steps"].append(f"view {name}")
        QTimer.singleShot(50, fingerprint_lab)

    def fingerprint_lab():
        import hashlib

        win.go("Fingerprint Research Lab")
        app.processEvents()
        state["phase"] = "fp_run"
        state["fp_sha"] = hashlib.sha256(ctl.research_image().read_bytes()).hexdigest()
        result["steps"].append("Fingerprint Research Lab: running a controlled-surrogate separation (Method 34)")
        ctl.run_fingerprint_method("Method 34", surrogate={"family": "spatial", "strength": 4.0, "key": 20261005})

    def on_fingerprint():
        import hashlib

        if state["phase"] != "fp_run" or ctl.last_fp_run is None:
            return
        state["phase"] = "fp_done"
        run = ctl.last_fp_run
        same = hashlib.sha256(ctl.research_image().read_bytes()).hexdigest() == state["fp_sha"]
        win.views["Fingerprint Research Lab"]._do_refresh()
        result["steps"].append(f"{run.run_id} {run.method_id} {run.status}; original unchanged "
                               f"{run.original_unchanged and same}")
        if not (run.original_unchanged and same) or run.status not in ("COMPLETE", "SIGNAL PERSISTED"):
            done(False, f"fingerprint run failed: {run.status}")
            return
        QTimer.singleShot(50, synthid_lab)

    def synthid_lab():
        import hashlib

        win.go("SynthID Research Lab")
        view = win.views["SynthID Research Lab"]
        app.processEvents()
        view.b_online.click()  # scripted runs never confirm: online mode must stay OFF
        app.processEvents()
        if ctl.online.enabled:
            done(False, "online verification enabled without explicit confirmation")
            return
        src = ctl.research_image()
        state["sid_sha"] = hashlib.sha256(src.read_bytes()).hexdigest()
        state["phase"] = "sid_detect"
        result["steps"].append("SynthID Research Lab: LOCAL MODE, online OFF")
        view.tabs.setCurrentWidget(view.t_detect)
        ctl.run_synthid_detection()

    def on_research():
        import hashlib

        from app.utils import netguard

        if state["phase"] != "sid_detect" or ctl.last_research_run is None:
            return
        state["phase"] = "sid_export"
        run = ctl.last_research_run
        same = hashlib.sha256(ctl.research_image().read_bytes()).hexdigest() == state["sid_sha"]
        result["steps"].append(f"{run.run_id} {run.kind} {run.status}; original unchanged {run.original_unchanged and same}")
        if not (run.original_unchanged and same):
            done(False, "original file changed during the SynthID research run")
            return
        result["network_attempts"] = netguard.blocked_attempts()
        dest = ctl.workspace.exports_dir / f"{run.run_id}_paper.zip"
        state["sid_zip"] = dest
        ctl.export_synthid_paper(run.run_id, str(dest))

    def on_info(msg):
        if state["phase"] == "sid_export" and str(msg).startswith("Paper export saved"):
            import zipfile

            state["phase"] = "end"
            with zipfile.ZipFile(state["sid_zip"]) as zf:
                n = len(zf.namelist())
            result["steps"].append(f"paper export {state['sid_zip'].name} ({n} files)")
            view = win.views["SynthID Research Lab"]
            view._do_refresh()
            if result.get("network_attempts"):
                done(False, f"network attempts in LOCAL MODE: {result['network_attempts']}")
                return
            done(True, "all views rendered; SynthID Research experiment run and exported in LOCAL MODE")

    def on_source():
        if state["phase"] == "open":
            state["phase"] = "start"
            result["steps"].append("image loaded")
            ctl.start_experiment()

    def on_exp():
        if state["phase"] == "start" and ctl.experiment is not None:
            state["phase"] = "transform"
            result["steps"].append(f"experiment {ctl.experiment.experiment_id}")
            ctl.run_transformation("metadata_sanitize", {"mode": "METADATA-ONLY", "profile": "BALANCED"})

    def on_records():
        if state["phase"] == "transform" and ctl.completed():
            state["phase"] = "views"
            t = ctl.completed()[-1]
            result["steps"].append(f"{t.transformation_id} {t.pixel_metrics.get('verdict')}")
            if t.pixel_metrics.get("verdict") != "PIXEL-EXACT":
                done(False, "metadata-only sanitize was not pixel-exact")
                return
            QTimer.singleShot(100, visit_all)

    ctl.sourceChanged.connect(on_source)
    ctl.experimentChanged.connect(on_exp)
    ctl.recordsChanged.connect(on_records)
    ctl.researchChanged.connect(on_research)
    ctl.fingerprintChanged.connect(on_fingerprint)
    ctl.info.connect(on_info)
    ctl.error.connect(lambda t, m: state["phase"] in ("open", "start", "fp_run", "sid_detect", "sid_export")
                      and done(False, f"{t}: {m}"))
    QTimer.singleShot(300, ctl.open_demo_fixture)
    QTimer.singleShot(120_000, lambda: done(False, "timeout"))


def main(argv=None) -> int:
    _guard_stdio()
    args = _parse(sys.argv[1:] if argv is None else argv)
    from app import __version__
    from app.utils import netguard

    netguard.install()
    if args.version:
        print(f"SynthProvenance {__version__}")
        return 0
    if args.self_test:
        from app.selftest import run_self_test

        return run_self_test(args.self_test_output)
    if args.smoke_gui:
        import tempfile

        os.environ["SYNTHPROVENANCE_HOME"] = tempfile.mkdtemp(prefix="synthprovenance_smoke_")
    from app.utils.logging import setup_logging
    from app.utils.paths import user_data_dir

    setup_logging(user_data_dir() / "logs")
    _app_user_model_id()
    from PySide6.QtWidgets import QApplication

    from app.ui import theme
    from app.ui.controller import AppController
    from app.ui.main_window import MainWindow
    from app.utils.config import Settings

    app = QApplication(sys.argv[:1])
    app.setApplicationName("SynthProvenance")
    app.setOrganizationName("NuRichter Workspace")
    app.setApplicationVersion(__version__)
    theme.apply(app)
    settings = Settings()
    if args.workspace:
        settings.data["workspace"] = args.workspace
    from app import i18n

    i18n.set_active(settings.get("language") or "en")
    splash = None
    if not args.smoke_gui:
        try:
            from app.ui.splash import Splash

            splash = Splash()
            splash.show()
            app.processEvents()
        except Exception:  # noqa: BLE001 - the splash is never allowed to block startup
            splash = None
    ctl = AppController(settings)
    if splash is not None:
        try:
            splash.run_sequence(app, ctl)
        except Exception:  # noqa: BLE001
            pass
    win = MainWindow(ctl, quiet=args.smoke_gui)
    win.show()
    if splash is not None:
        splash.finish(win)
    if args.smoke_gui:
        _smoke(app, win, ctl, args.smoke_output)
    elif args.image:
        ctl.open_image(args.image)
    code = app.exec()
    ctl.pool.waitForDone(10000)
    return int(code)


if __name__ == "__main__":
    sys.exit(main())
