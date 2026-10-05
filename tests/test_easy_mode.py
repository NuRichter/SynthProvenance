"""Easy Mode: mode persistence + SAVE & RESTART, the orchestrator (suitability, fallback, critical stops,
candidate evaluation, output formats, report), result saving, and the three-step Easy shell (rendering,
keyboard, accessibility, 30 languages, full PILIH > RUN > OUTPUT integration)."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

import pytest

from app.core.audit_engine import AuditLog
from app.core.easy_mode_orchestrator import (ARM_CONTROLLED, ARM_REAL, CANDIDATE_GATES, OUTPUT_FORMATS, STAGES,
                                             EasyModeOrchestrator, EasyModeRequest, SaveRefused, save_result)
from app.core.experiment_engine import Workspace
from app.core.image_loader import open_image_bytes
from app.core.synthid_engine import SynthIDEngine
from app.research import procedural as P
from app.research.imaging import from_float

ROOT = Path(__file__).resolve().parents[1]


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture()
def orch(tmp_path):
    ws = Workspace(tmp_path / "ws")
    return EasyModeOrchestrator(ws, AuditLog(), SynthIDEngine(), workers=2)


@pytest.fixture()
def jpeg_c2pa(tmp_path, fx):
    p = tmp_path / "in" / "generative_ai_c2pa.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(fx["fixture_ai_c2pa.jpg"])
    return p


@pytest.fixture()
def scene_png(tmp_path):
    p = tmp_path / "in" / "scene.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    from_float(P.scene(256, 320, seed=11)).save(p)
    return p


# ------------------------------------------------------------------ mode persistence & restart
def test_mode_persistence_and_fallback(tmp_path):
    from app.ui.app_mode import save_mode
    from app.utils.config import Settings

    st = Settings(tmp_path / "settings.json")
    assert st.ui_mode() == "EASY"                      # bundled default
    save_mode(st, "expert")
    assert Settings(tmp_path / "settings.json").ui_mode() == "EXPERT"
    save_mode(st, "EASY")
    assert Settings(tmp_path / "settings.json").ui_mode() == "EASY"
    with pytest.raises(ValueError):
        save_mode(st, "SIMPLE")
    (tmp_path / "settings.json").write_text(json.dumps({"ui_mode": "bogus"}), encoding="utf-8")
    assert Settings(tmp_path / "settings.json").ui_mode() == "EASY"


class _Ctl:
    def __init__(self, settings, busy=False):
        self.settings, self.busy, self.audit = settings, busy, AuditLog()


def test_save_and_restart_persists_relaunches_and_quits(tmp_path, monkeypatch):
    from app.ui import app_mode
    from app.utils.config import Settings

    st = Settings(tmp_path / "settings.json")
    calls, quits = [], []
    monkeypatch.setitem(app_mode.SESSION_ARGS, "workspace", str(tmp_path / "ws"))
    ok, _msg = app_mode.save_and_restart(_Ctl(st), "EXPERT", launcher=lambda p, a, c: calls.append((p, a, c)) or True,
                                         quit_fn=lambda: quits.append(1), extra_args=["--x"])
    assert ok and quits == [1]
    assert Settings(tmp_path / "settings.json").ui_mode() == "EXPERT"
    program, args, cwd = calls[0]
    assert program and Path(cwd).is_dir()
    assert args[-1] == "--x" and "--workspace" in args          # session workspace override survives the restart
    assert any(a.endswith("main.py") for a in args)              # source mode relaunches app/main.py
    # frozen build relaunches the executable itself, no script argument
    monkeypatch.setattr(app_mode, "is_frozen", lambda: True)
    prog, fargs, _ = app_mode.relaunch_command()
    assert prog == sys.executable and not any(a.endswith("main.py") for a in fargs)


def test_restart_refused_while_busy_or_when_launch_fails(tmp_path):
    from app.ui import app_mode
    from app.utils.config import Settings

    st = Settings(tmp_path / "settings.json")
    quits = []
    ok, msg = app_mode.save_and_restart(_Ctl(st, busy=True), "EXPERT", launcher=lambda *a: True,
                                        quit_fn=lambda: quits.append(1))
    assert not ok and "running" in msg and not quits
    assert Settings(tmp_path / "settings.json").ui_mode() == "EASY"   # nothing saved while busy
    ok, msg = app_mode.save_and_restart(_Ctl(st), "EXPERT", launcher=lambda *a: False, quit_fn=lambda: quits.append(1))
    assert not ok and not quits and "saved" in msg


# ------------------------------------------------------------------ orchestrator
def test_pipeline_runs_twelve_stages_and_keeps_original(orch, jpeg_c2pa):
    sha = _sha(jpeg_c2pa)
    progress = []
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", True), lambda p, ph: progress.append((p, ph)))
    assert res.status == "COMPLETE", (res.error, res.error_detail, res.warnings)
    assert [s.number for s in res.stages] == list(range(1, 13))
    assert [s.key for s in res.stages] == [s.key for s in STAGES]
    assert _sha(jpeg_c2pa) == sha and res.original_unchanged is True
    assert res.input["sha256"] == sha and res.input["sha256_after"] == sha
    # progress is monotonic and only uses the five friendly phase words
    pcts = [p for p, _ in progress]
    assert pcts == sorted(pcts) and pcts[-1] == 100
    assert {ph for _, ph in progress} <= {"Preparing", "Analyzing", "Reconstructing", "Validating", "Finalizing"}
    # a real, decodable image file in the chosen format, pixel-verified against the original
    out = Path(res.output["path"])
    assert out.is_file() and out.suffix == ".png" and out != jpeg_c2pa
    open_image_bytes(out.read_bytes())
    assert res.output["pixel_verdict"] == "PIXEL-EXACT" and res.output["pixel_status"] == "VERIFIED"
    # provenance observed (fixture has C2PA + AI declaration); SynthID only from a local engine
    assert res.provenance["c2pa_present"] and res.provenance["synthid_state"] == "UNAVAILABLE"
    # report written into the experiment folder and the run record kept
    for k in ("html", "pdf", "json"):
        assert Path(res.report_paths[k]).is_file()
    exp_dir = Path(res.experiment_dir)
    assert (exp_dir / "easy_mode_run.json").is_file() and (exp_dir / "original" / jpeg_c2pa.name).is_file()


def test_every_method_has_a_real_execution_state(orch, jpeg_c2pa):
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", False))
    c = res.counts()
    assert c["total"] == 64 == len(res.methods)
    assert c["executed"] + c["insufficient"] + c["failed"] + c["skipped"] == c["total"]
    for m in res.methods:
        assert m.decision in ("RUN", "SKIP")
        if m.decision == "SKIP":
            assert m.status in ("UNAVAILABLE", "NOT IMPLEMENTED", "REQUIRES DATA", "INCOMPATIBLE", "EXPERT ONLY",
                                "REDUNDANT") and m.reason, m.method_id
        else:
            assert m.status != "PENDING" and m.arm in (ARM_REAL, ARM_CONTROLLED)
    by = {m.method_id: m for m in res.methods}
    assert by["Method 09"].status == "UNAVAILABLE"            # DIRE: model not installed
    assert by["Method 43"].status == "NOT IMPLEMENTED"        # detector evasion: out of scope by design
    assert by["Method 25"].status == "REQUIRES DATA"          # cross-image needs references
    assert by["Method 18"].decision == "RUN"                  # JPEG input -> JPEG-domain method eligible
    # the 96x64 fixture is below the controlled-case minimum: skipped honestly, no fabricated reconstruction
    assert by["Method 35"].status == "INCOMPATIBLE" and res.reconstruction_status == "NO VALIDATED RECONSTRUCTION"
    assert not res.candidates and not res.best_candidate


def test_suitability_rules(orch):
    plan = {m.method_id: m for m in orch.plan("PNG", 2048, 1536)}
    assert plan["Method 18"].status == "INCOMPATIBLE" and "JPEG" in plan["Method 18"].reason
    assert plan["Method 35"].decision == "RUN" and plan["Method 35"].arm == ARM_CONTROLLED
    assert plan["Method 13"].decision == "RUN" and plan["Method 13"].arm == ARM_REAL
    assert plan["Method 26"].status == "UNAVAILABLE" and not plan["Method 26"].suitability["model_available"]
    assert plan["Method 39"].status == "EXPERT ONLY"
    assert plan["Method 53"].status == "REDUNDANT"
    # deterministic: the same input always yields the same plan
    again = orch.plan("PNG", 2048, 1536)
    assert [(m.method_id, m.decision, m.status) for m in again] == [(m.method_id, m.decision, m.status)
                                                                    for m in plan.values()]


def test_controlled_arm_ranks_candidates_against_ground_truth(orch, scene_png):
    res = orch.run(EasyModeRequest(str(scene_png), "PNG", False))
    assert res.ok and res.controlled_case["valid_ground_truth"] is True
    cands = res.candidates
    assert len(cands) >= 5
    # shared executions (41 == 35, 42 == 38) are not double-counted as candidates
    ids = [c.method_id for c in cands]
    assert "Method 41" not in ids and "Method 42" not in ids
    assert [c.rank for c in cands] == list(range(1, len(cands) + 1))
    passed = [c for c in cands if c.passed]
    # validated candidates always rank above rejected ones, and every gate is enforced
    assert ids[:len(passed)] == [c.method_id for c in passed]
    for c in passed:
        m = c.metrics
        assert m["candidate_vs_known_corr"] >= CANDIDATE_GATES["min_candidate_vs_known_corr"]
        assert m["recon_ssim"] >= CANDIDATE_GATES["min_recon_ssim"]
        assert m["recon_psnr_db"] >= CANDIDATE_GATES["min_recon_psnr_db"]
    assert any(not c.passed for c in cands)                   # e.g. the FFT separation is rejected, not promoted
    if passed:
        assert res.reconstruction_status == "VALIDATED" and res.best_candidate == passed[0].method_id
    else:
        assert res.reconstruction_status == "NO VALIDATED RECONSTRUCTION" and not res.best_candidate
    # the result image is never a reconstruction: it is the pixel-preserving export of the real image
    assert res.output["pixel_verdict"] == "PIXEL-EXACT"


def test_method_failure_does_not_abort_the_run(orch, jpeg_c2pa, monkeypatch):
    from app.research import runner as RUN

    real = RUN.run

    def flaky(method, inp, progress=None):
        if method.capability == "fft":
            raise RuntimeError("simulated FFT engine failure")
        return real(method, inp, progress)

    monkeypatch.setattr(RUN, "run", flaky)
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", True))
    assert res.status == "COMPLETE WITH WARNINGS" and res.ok
    by = {m.method_id: m for m in res.methods}
    assert by["Method 13"].status == "FAILED" and "simulated" in by["Method 13"].detail
    assert by["Method 16"].status == "FAILED"                 # shares the FFT implementation
    assert by["Method 15"].status == "COMPLETE"               # wavelet still ran
    assert res.counts()["failed"] >= 2
    assert Path(res.output["path"]).is_file()
    html = Path(res.report_paths["html"]).read_text(encoding="utf-8")
    assert "Methods Failed" in html and "simulated FFT engine failure" in html


def test_stage_failure_is_recorded_and_the_run_continues(orch, jpeg_c2pa, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("signal stage exploded")

    monkeypatch.setattr(orch, "_signal", boom)
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", False))
    assert res.ok and res.status == "COMPLETE WITH WARNINGS"
    st = {s.key: s for s in res.stages}
    assert st["signal"].status == "FAILED" and st["output"].status == "COMPLETE"
    assert {m.status for m in res.methods if m.stage == "signal"} == {"NOT RUN"}


def test_undecodable_source_stops_with_a_friendly_error(orch, tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00garbage" * 50)
    res = orch.run(EasyModeRequest(str(bad), "PNG", True))
    assert res.status == "FAILED" and not res.output
    assert res.error and "Traceback" not in res.error and res.error_detail
    not_image = tmp_path / "notes.png"
    not_image.write_text("hello", encoding="utf-8")
    res2 = orch.run(EasyModeRequest(str(not_image), "PNG", True))
    assert res2.status == "FAILED" and res2.error == "The selected file could not be read as an image."


def test_output_failure_stops_but_reports_the_analysis(orch, jpeg_c2pa, monkeypatch):
    real = orch.service.run

    def failing(exp, src, op, params, progress=None):
        rec = real(exp, src, "c2pa_separation", {}, progress)
        rec.status, rec.error = "FAILED", "simulated encoder failure"
        return rec

    monkeypatch.setattr(orch.service, "run", failing)
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", True))
    assert res.status == "FAILED" and res.error == "No valid result image could be generated."
    assert Path(res.report_paths["html"]).is_file()           # analysis still reported
    assert res.original_unchanged is True


@pytest.mark.parametrize("fmt,ext,lossless", [("PNG", ".png", True), ("JPG", ".jpg", False), ("WEBP", ".webp", True),
                                              ("TIFF", ".tif", True), ("BMP", ".bmp", True)])
def test_output_format_selection(orch, scene_png, fmt, ext, lossless):
    res = orch.run(EasyModeRequest(str(scene_png), fmt, False))
    assert res.ok, res.error_detail
    out = Path(res.output["path"])
    assert out.suffix == ext and res.output["easy_format"] == fmt
    img = open_image_bytes(out.read_bytes())
    assert img.size == (320, 256)
    assert (res.output["pixel_status"] == "VERIFIED") is lossless
    if not lossless:
        assert res.output["pixel_status"] == "LOSSY (MEASURED)" and res.output["psnr_db"] > 30


def test_save_result_never_overwrites_the_original(orch, jpeg_c2pa, tmp_path):
    sha = _sha(jpeg_c2pa)
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "JPG", False))
    with pytest.raises(SaveRefused):
        save_result(res, jpeg_c2pa)
    with pytest.raises(SaveRefused):
        save_result(res, jpeg_c2pa.with_suffix(""))           # extension auto-fix must not reach the original
    assert _sha(jpeg_c2pa) == sha
    saved = save_result(res, tmp_path / "out" / "mine")      # extension is added for the chosen format
    assert saved.name == "mine.jpg" and _sha(saved) == res.output["sha256"]


def test_report_location_and_report_toggle(orch, jpeg_c2pa, tmp_path):
    dest = tmp_path / "my_reports"
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", True, str(dest)))
    assert Path(res.report_paths["html"]).parent == dest and Path(res.report_paths["experiment_html"]).is_file()
    text = Path(res.report_paths["html"]).read_text(encoding="utf-8")
    for needle in ("Experiment ID", res.experiment_id, "SHA-256", "C2PA", "SynthID", "Fingerprint Families",
                   "Methods Executed", "Methods Skipped", "Reconstruction Candidates", "Pixel Integrity", "Limitations",
                   "Research Notes", "Source References", "REAL IMAGE OBSERVATION", "CONTROLLED SURROGATE RESEARCH"):
        assert needle in text, needle
    off = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", False))
    assert not off.report_paths and {s.key: s.status for s in off.stages}["report"] == "SKIPPED"
    assert (Path(off.experiment_dir) / "easy_mode_run.json").is_file()


def test_pipeline_is_local_only(orch, jpeg_c2pa):
    from app.utils import netguard

    netguard.install()
    before = len(netguard.blocked_attempts())
    res = orch.run(EasyModeRequest(str(jpeg_c2pa), "PNG", True))
    assert res.ok and len(netguard.blocked_attempts()) == before


# ------------------------------------------------------------------ the Easy shell (Qt)
def _app():
    from PySide6.QtWidgets import QApplication

    from app.ui.easy.style import apply_easy

    app = QApplication.instance() or QApplication([])
    apply_easy(app)
    return app


def _wait(app, ctl, timeout=180):
    t = time.time()
    while ctl.busy or time.time() - t < 0.2:
        app.processEvents()
        time.sleep(0.01)
        assert time.time() - t < timeout


def _texts(widget) -> list[str]:
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel

    out = []
    for w in widget.findChildren(QLabel) + widget.findChildren(QAbstractButton):
        if w.isVisibleTo(widget):
            out.append(w.text())
    for c in widget.findChildren(QComboBox):
        out += [c.itemText(i) for i in range(c.count())]
    return out


FORBIDDEN_TECH = ("FFT", "DCT", "DWT", "Wavelet", "wavelet", "LID", "RPCA", "Robust PCA", "CLIP", "DINO",
                  "residual", "Residual", "taxonomy", "Taxonomy", "hypothesis", "Hypothesis", "Composer", "threshold",
                  "confidence", "SPX-FP", "audit", "Traceback")


@pytest.fixture()
def easy_win(tmp_path):
    from app.i18n import set_active
    from app.ui.controller import AppController
    from app.ui.easy.window import EasyWindow
    from app.utils.config import Settings

    set_active("en")
    app = _app()
    st = Settings(tmp_path / "settings.json")
    st.set("workspace", str(tmp_path / "ws"))
    ctl = AppController(st)
    win = EasyWindow(ctl, quiet=True)
    win.show()
    app.processEvents()
    yield app, ctl, win
    win.close()


def test_easy_shell_three_steps_and_no_technical_controls(easy_win, jpeg_c2pa):
    app, ctl, win = easy_win
    assert type(win).__name__ == "EasyWindow" and win.stack.count() == 3
    assert [win.steps.state(i) for i in range(3)] == ["active", "pending", "pending"]
    assert [n.text() for n in win.steps.names] == ["PILIH", "RUN", "OUTPUT"]
    assert win.pilih.title.text() == "01 · PILIH"
    assert not win.pilih.b_continue.isEnabled()
    assert win.pilih.set_file(str(jpeg_c2pa)) and win.pilih.b_continue.isEnabled()
    assert [win.pilih.fmt.itemText(i) for i in range(win.pilih.fmt.count())] == list(OUTPUT_FORMATS)
    assert win.pilih.fmt.currentText() == "PNG" and win.pilih.report.isChecked()
    texts = " ".join(_texts(win.pilih) + _texts(win.run_page))
    for word in FORBIDDEN_TECH + ("C2PA", "SynthID", "SHA"):
        assert word not in texts, word
    assert not re.search(r"Method \d|FP-\d", texts)
    win.pilih.b_continue.click()
    assert win.step == 1 and [win.steps.state(i) for i in range(3)] == ["complete", "active", "pending"]
    assert win.run_page.b_run.label() == "RUN TRANSFORMATION"


def test_keyboard_navigation(easy_win, jpeg_c2pa):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    app, ctl, win = easy_win

    def key(k):
        QApplication.sendEvent(win, QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))
        app.processEvents()

    win.pilih.set_file(str(jpeg_c2pa))
    win.pilih.fmt.setFocus()
    key(Qt.Key.Key_Return)                 # Enter = the step's primary action (CONTINUE)
    assert win.step == 1
    key(Qt.Key.Key_Escape)                 # Escape = BACK
    assert win.step == 0
    # every interactive control is keyboard-focusable, labelled for screen readers, and a large hit target
    from PySide6.QtWidgets import QAbstractButton

    for page in (win.pilih, win.run_page, win.output):
        for b in page.findChildren(QAbstractButton):
            assert b.focusPolicy() & Qt.FocusPolicy.TabFocus, b.text()
            assert b.accessibleName() or b.text(), b
    for b in (win.pilih.b_continue, win.pilih.drop.choose, win.run_page.b_run, win.output.b_save, win.output.b_another):
        assert b.minimumHeight() >= 44
    assert win.pilih.drop.focusPolicy() & Qt.FocusPolicy.TabFocus and win.pilih.drop.accessibleName()
    # Tab moves focus forward through the Pilih controls
    win.pilih.drop.setFocus()
    seen = set()
    for _ in range(8):
        win.focusNextChild()
        app.processEvents()
        seen.add(QApplication.focusWidget())
    assert win.pilih.fmt in seen and win.pilih.report in seen


def test_full_pilih_run_output_integration(easy_win, jpeg_c2pa, tmp_path):
    app, ctl, win = easy_win
    sha = _sha(jpeg_c2pa)
    win.pilih.set_file(str(jpeg_c2pa))                       # PILIH: choose image
    win.pilih.fmt.setCurrentText("PNG")                      #        select PNG
    win.pilih.b_continue.click()                             #        CONTINUE
    win.run_page.b_run.click()                               # RUN TRANSFORMATION
    assert not win.run_page.b_run.isEnabled() and win.run_page.b_run.label() == "RUNNING..."
    _wait(app, ctl)
    app.processEvents()
    res = ctl.last_easy
    assert res is not None and res.ok and win.step == 2      # OUTPUT
    assert [win.steps.state(i) for i in range(3)] == ["complete", "complete", "active"]
    assert "VERIFIED" in win.output.pixel.text() and "PNG" in win.output.meta.text()
    rows = dict((k.text(), v.text()) for k, v in win.output.c_research.rows)
    assert rows["Experiment ID"] == res.experiment_id and int(rows["Methods executed"]) == res.counts()["executed"]
    prov = dict((k.text(), v.text()) for k, v in win.output.c_prov.rows)
    assert prov["SynthID"] == "UNAVAILABLE" and prov["C2PA"].startswith("PRESENT")
    assert Path(res.report_paths["html"]).is_file()          # report generated
    saved = win.save_to(str(tmp_path / "result"))            # SAVE RESULT
    assert saved is not None and saved.suffix == ".png" and _sha(saved) == res.output["sha256"]
    assert _sha(jpeg_c2pa) == sha                            # original untouched
    out_texts = " ".join(_texts(win.output))
    for word in FORBIDDEN_TECH:
        assert word not in out_texts, word
    assert not re.search(r"Method \d|FP-\d", out_texts)          # no method IDs on the Easy screens
    win.output.b_another.click()                             # RUN ANOTHER
    assert win.step == 0 and win.pilih.info is None and ctl.last_easy is None
    assert not win.pilih.b_continue.isEnabled()


def test_failed_run_shows_friendly_error_with_try_again(easy_win, tmp_path):
    app, ctl, win = easy_win
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 300)
    # the header probe accepts the container; decoding fails inside the pipeline
    win.pilih.info = {"name": bad.name, "path": str(bad), "format": "PNG", "width": 0, "height": 0, "bytes": 308}
    win.pilih.b_continue.setEnabled(True)
    win.pilih.b_continue.click()
    win.run_page.b_run.click()
    _wait(app, ctl)
    app.processEvents()
    assert win.step == 1 and win.run_page.err.isVisible()
    assert win.run_page.err_title.text() == "Something went wrong."
    assert "Traceback" not in win.run_page.err_msg.text() and win.run_page.b_retry.isVisible()
    assert not win.run_page.err_detail.isVisible()           # technical detail only behind DETAILS
    win.run_page.b_details.click()
    assert win.run_page.err_detail.isVisible() and win.run_page.err_detail.toPlainText()


def test_all_30_languages_translate_the_easy_shell(easy_win):
    from app.i18n import LANG_CODES, Translator, active, set_active

    app, ctl, win = easy_win
    en = json.loads((ROOT / "app" / "i18n" / "locales" / "en.json").read_text(encoding="utf-8"))
    keys = [k for k in en if k.startswith("easy.")]
    required = ("easy.step1", "easy.step2", "easy.step3", "easy.choose_image", "easy.output_format",
                "easy.research_report", "easy.choose_location", "easy.continue", "easy.run_transformation",
                "easy.phase.Analyzing", "easy.phase.Reconstructing", "easy.phase.Validating", "easy.result_ready",
                "easy.save_result", "easy.open_report", "easy.run_another", "easy.settings", "easy.mode_easy",
                "easy.mode_expert")
    assert len(LANG_CODES) == 30
    for code in LANG_CODES:
        data = json.loads((ROOT / "app" / "i18n" / "locales" / f"{code}.json").read_text(encoding="utf-8"))
        missing = [k for k in keys if not data.get(k)]
        assert not missing, (code, missing[:5])
        t = Translator(code)
        assert t.t("easy.step_of", n=2) and "{" not in t.t("easy.compute_line", cpu=8, gpu="x")
        if code not in ("en", "id"):
            assert sum(t.t(k) != en[k] for k in required) >= len(required) - 4, code
        set_active(code)
        win.apply_language(code)
        app.processEvents()
        assert win.steps.names[0].text() == t.t("easy.step1")
        assert win.pilih.b_continue.label() == t.t("easy.continue")
        assert win.pilih.b_continue.accessibleName() == t.t("easy.continue")
        assert (win.layoutDirection().name == "RightToLeft") == active().rtl
    set_active("en")
    win.apply_language()


def test_easy_settings_dialog_offers_save_and_restart(easy_win):
    from app.ui.easy.dialogs import EasySettingsDialog

    app, ctl, win = easy_win
    dlg = EasySettingsDialog(ctl, win)
    assert dlg.mode.chosen() == "EASY" and not dlg.note.isVisibleTo(dlg)
    dlg.mode.expert.setChecked(True)
    assert dlg.note.isVisibleTo(dlg) and dlg.b_save.label() == "SAVE & RESTART"
    assert dlg.b_save.accessibleName() == "SAVE & RESTART" and dlg.b_save.text() == "SAVE && RESTART"
    assert dlg.note.text() == "Your interface mode will change after restart."
    dlg.mode.easy.setChecked(True)
    assert dlg.b_save.label() == "SAVE"
    dlg.close()


def test_expert_settings_application_mode_panel(tmp_path):
    from app.ui import theme
    from app.ui.controller import AppController
    from app.ui.main_window import MainWindow
    from app.utils.config import Settings

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    st = Settings(tmp_path / "settings.json")
    st.set("ui_mode", "EXPERT")
    st.set("workspace", str(tmp_path / "ws"))
    ctl = AppController(st)
    win = MainWindow(ctl, quiet=True)
    view = win.views["Settings"]
    view._do_refresh()
    assert view.mode_expert.isChecked() and not view.b_restart.isEnabled()
    view.mode_easy.setChecked(True)
    assert view.mode_note.isVisibleTo(view) and view.b_restart.isEnabled() and view.b_restart.accessibleName() == "SAVE & RESTART"
    view.b_mode_cancel.click()
    assert view.mode_expert.isChecked() and not view.b_restart.isEnabled()
    # the Fingerprint Lab keeps every expert tab in the Expert shell
    fp = win.views["Fingerprint Research Lab"]
    assert all(fp.tabs.isTabVisible(i) for i in range(fp.tabs.count()))
    win.close()
