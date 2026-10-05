"""SynthProvenance entry point.



    SynthProvenance.exe [image]            start the GUI in the saved application mode (Easy / Expert)

    --ui-mode easy|expert                  use this mode for this session only (not saved)

    --self-test [--self-test-output F]     headless pipeline verification (JSON result)

    --smoke-gui [--smoke-output F]         start the Expert GUI, run a short scripted experiment, exit

    --smoke-easy [--smoke-output F] [--smoke-shots DIR] [--smoke-restart-to MODE --smoke-restart-ack F]

                                           start the Easy GUI, run PILIH > RUN > OUTPUT, optionally switch mode

                                           with SAVE & RESTART and let the relaunched instance acknowledge

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

    p.add_argument("--smoke-easy", action="store_true")

    p.add_argument("--smoke-cross", action="store_true")

    p.add_argument("--smoke-shots")

    p.add_argument("--smoke-restart-to", choices=("EASY", "EXPERT", "easy", "expert"))

    p.add_argument("--smoke-restart-ack")

    p.add_argument("--ui-mode", choices=("easy", "expert", "EASY", "EXPERT"))

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





def _smoke_cross(app, win, ctl, output) -> None:
    from app.ui.smoke_cross import run as _run

    _run(app, win, ctl, output)


def _restart_ack(app, win, settings, mode: str, path: str) -> None:

    """Relaunched by SAVE & RESTART during a smoke test: record which shell came up, then exit."""

    from PySide6.QtCore import QTimer



    from app.utils.paths import is_frozen



    def write():

        Path(path).write_text(json.dumps({"ui_mode": mode, "settings_ui_mode": settings.ui_mode(),

                                          "shell": type(win).__name__, "pid": os.getpid(), "frozen": is_frozen(),

                                          "visible": win.isVisible()}, indent=2), encoding="utf-8")

        QTimer.singleShot(200, app.quit)



    QTimer.singleShot(600, write)





def _smoke_easy(app, win, ctl, args) -> None:

    """Scripted PILIH > RUN > OUTPUT through the real Easy widgets (used by the build verifier)."""

    import hashlib

    import tempfile



    from PySide6.QtCore import QTimer



    from app.core.image_loader import open_image_bytes

    from app.core.synthetic import make_jpeg

    from app.utils import netguard



    t0 = time.perf_counter()

    result = {"ok": False, "steps": [], "errors": win.errors, "shell": type(win).__name__}

    state = {"phase": "pilih"}

    tmp = Path(tempfile.mkdtemp(prefix="sp_easy_smoke_"))

    src = tmp / "SMOKE_generative_image_ai_c2pa.jpg"

    src.write_bytes(make_jpeg(size=(640, 427)))

    sha = hashlib.sha256(src.read_bytes()).hexdigest()

    shots = Path(args.smoke_shots) if args.smoke_shots else None

    if shots:

        shots.mkdir(parents=True, exist_ok=True)



    def shot(name, widget=None):

        if shots is not None:

            app.processEvents()

            (widget or win).grab().save(str(shots / f"{name}.png"))



    def done(ok: bool, why: str = "") -> None:

        if state.get("finished"):

            return

        state["finished"] = True

        result["ok"] = bool(ok)

        result["reason"] = why

        result["duration_s"] = round(time.perf_counter() - t0, 2)

        result["network_attempts"] = netguard.blocked_attempts()

        if args.smoke_output:

            Path(args.smoke_output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

        if ok and args.smoke_restart_to and args.smoke_restart_ack:

            from app.ui.app_mode import save_and_restart



            started, msg = save_and_restart(ctl, args.smoke_restart_to.upper(),

                                            extra_args=["--smoke-restart-ack", args.smoke_restart_ack])

            result["restart"] = msg

            if args.smoke_output:

                Path(args.smoke_output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

            if started:

                return

        QTimer.singleShot(200, app.quit)



    def pilih():

        if win.step != 0 or win.steps.state(0) != "active":

            done(False, "Easy shell did not open on 01 PILIH")

            return

        if not win.pilih.set_file(str(src)) or not win.pilih.b_continue.isEnabled():

            done(False, "image selection failed")

            return

        win.pilih.fmt.setCurrentText("PNG")

        win.pilih.report.setChecked(True)

        result["steps"].append(f"01 PILIH: {src.name}, output PNG, report on")

        shot("01_pilih")

        win.pilih.b_continue.click()

        app.processEvents()

        if win.step != 1 or win.steps.state(0) != "complete" or win.steps.state(1) != "active":

            done(False, "CONTINUE did not open 02 RUN")

            return

        shot("02_run_ready")

        state["phase"] = "run"

        win.run_page.b_run.click()

        app.processEvents()

        if win.run_page.b_run.isEnabled() or not ctl.busy:

            done(False, "RUN TRANSFORMATION did not start the pipeline")

            return

        result["steps"].append("02 RUN: pipeline started (button disabled, RUNNING...)")

        QTimer.singleShot(1500, lambda: state["phase"] == "run" and shot("02_running"))



    def on_result():

        if state["phase"] != "run" or ctl.last_easy is None:

            return

        state["phase"] = "output"

        QTimer.singleShot(150, check_output)



    def check_output():

        res = ctl.last_easy

        c = res.counts()

        result["steps"].append(f"{res.experiment_id} {res.status}: {c['executed']} executed, {c['failed']} failed, "

                               f"{c['skipped']} skipped; reconstruction {res.reconstruction_status}")

        if not res.ok or win.step != 2:

            done(False, f"pipeline did not reach 03 OUTPUT: {res.status} {res.error} {res.error_detail}")

            return

        out = Path(res.output["path"])

        try:

            open_image_bytes(out.read_bytes())

        except Exception as exc:  # noqa: BLE001

            done(False, f"result image does not decode: {exc}")

            return

        if hashlib.sha256(src.read_bytes()).hexdigest() != sha or res.original_unchanged is not True:

            done(False, "original image changed")

            return

        html = Path(res.report_paths.get("html", ""))

        if not html.is_file():

            done(False, "research report missing")

            return

        result["steps"].append(f"03 OUTPUT: {out.name} {res.output['format']} {res.output['width']}x"

                               f"{res.output['height']} {res.output['pixel_status']}; report {html.name}")

        shot("03_output")

        saved = win.save_to(str(tmp / "saved_result.png"))

        if saved is None or hashlib.sha256(saved.read_bytes()).hexdigest() != res.output["sha256"]:

            done(False, "SAVE RESULT failed")

            return

        if win.save_to(str(src)) is not None or hashlib.sha256(src.read_bytes()).hexdigest() != sha:

            done(False, "SAVE RESULT was allowed to overwrite the original")

            return

        result["steps"].append(f"SAVE RESULT -> {saved.name} (sha256 verified); overwrite of original refused")

        win.show_details()

        app.processEvents()

        dlg = getattr(win, "_details", None)

        if dlg is not None:

            shot("03_details", dlg)

            dlg.close()

        win.output.b_another.click()

        app.processEvents()

        if win.step != 0 or win.pilih.info is not None or ctl.last_easy is not None:

            done(False, "RUN ANOTHER did not reset to 01 PILIH")

            return

        result["steps"].append("RUN ANOTHER -> 01 PILIH (state cleared)")

        shot("01_after_run_another")

        if netguard.blocked_attempts():

            done(False, f"network attempts: {netguard.blocked_attempts()}")

            return

        done(True, "PILIH > RUN > OUTPUT completed in the Easy shell; result saved; original unchanged; LOCAL-ONLY")



    ctl.easyChanged.connect(on_result)

    QTimer.singleShot(400, pilih)

    QTimer.singleShot(300_000, lambda: done(False, "timeout"))





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

    if (args.smoke_gui or args.smoke_easy or args.smoke_cross) and not os.environ.get("SYNTHPROVENANCE_HOME"):

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

    settings = Settings()

    from app.ui import app_mode



    if args.workspace:

        settings.data["workspace"] = args.workspace

        app_mode.SESSION_ARGS["workspace"] = args.workspace

    if args.smoke_gui or args.smoke_cross:

        mode = "EXPERT"

    elif args.smoke_easy:

        mode = "EASY"

    else:

        mode = args.ui_mode.upper() if args.ui_mode else settings.ui_mode()

    if mode == "EASY":

        from app.ui.easy.style import apply_easy



        apply_easy(app)

    else:

        theme.apply(app, settings.get("theme"))

    from app import i18n



    i18n.set_active(settings.get("language") or "en")

    quiet = bool(args.smoke_gui or args.smoke_easy or args.smoke_cross or args.smoke_restart_ack)

    splash = None

    if not quiet:

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

    if mode == "EASY":

        from app.ui.easy.window import EasyWindow



        win = EasyWindow(ctl, quiet=quiet)

    else:

        win = MainWindow(ctl, quiet=quiet)

    win.show()

    if splash is not None:

        splash.finish(win)

    if args.smoke_restart_ack and not args.smoke_easy:

        _restart_ack(app, win, settings, mode, args.smoke_restart_ack)

    elif args.smoke_gui:

        _smoke(app, win, ctl, args.smoke_output)

    elif args.smoke_easy:

        _smoke_easy(app, win, ctl, args)

    elif args.smoke_cross:

        _smoke_cross(app, win, ctl, args.smoke_output)

    elif args.image:

        if mode == "EASY":

            win.pilih.set_file(args.image)

        else:

            ctl.open_image(args.image)

    code = app.exec()

    ctl.pool.waitForDone(10000)

    return int(code)





if __name__ == "__main__":

    sys.exit(main())