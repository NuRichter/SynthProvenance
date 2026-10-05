"""SynthID Research Lab: local verification, method registry, sources, benchmark, online hand-off, experiments."""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLineEdit, QMessageBox,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from app.core.synthid_online import DESTINATIONS, NO_UPLOAD, NOT_INTEGRATED, OnlinePolicyError
from app.core.synthid_research_engine import MATRIX_COLUMNS
from app.core.synthid_source_manager import to_rows as source_rows
from app.models.synthid import DEFAULT_LIMITATION, UNAVAILABLE_REASON
from app.services.synthid_experiment import synthid_summary
from app.ui.views.base import View, row
from app.ui.widgets.charts import RocWidget
from app.ui.widgets.common import Badge, DataTable, KVTable, Panel, Readout, banner, button, fmt_num, label

REGISTRY_COLUMNS = ["Method ID", "Method", "Status", "Validation", "Local/Online", "GPU", "Dataset", "Maturity", "License",
                    "Source"]
SOURCE_COLUMNS = ["ID", "Kind", "Status", "Title", "Publisher", "Accessed", "URL", "Relevance"]
RECORD_COLUMNS = ["Image", "SHA-256", "State", "Detector", "Version", "Model", "Score", "Confidence", "Runtime ms", "Detail"]
RUN_COLUMNS = ["Run", "Kind", "Method", "Status", "Created (UTC)", "Inputs", "Original unchanged"]


def _tab(*widgets) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(8, 8, 8, 8)
    for x in widgets:
        if x is None:
            lay.addStretch(1)
        elif isinstance(x, QWidget):
            lay.addWidget(x)
        else:
            lay.addLayout(x)
    return w


class SynthIDResearchLabView(View):
    title = "SynthID Research Lab"
    subtitle = ("Local / Online Verification  ·  SynthID is an EMBEDDED SIGNAL LAYER in pixel values. It is never "
                "treated as metadata, never inferred from metadata or C2PA, and never reported as removed.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        # ---- top-level mode
        mode = QHBoxLayout()
        self.b_local = button("LOCAL RESEARCH", checkable=True)
        self.b_online = button("ONLINE OFFICIAL VERIFICATION", checkable=True)
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for b in (self.b_local, self.b_online):
            grp.addButton(b)
            mode.addWidget(b)
        self.b_local.setChecked(True)
        self.b_local.clicked.connect(lambda: self._set_mode(False))
        self.b_online.clicked.connect(lambda: self._set_mode(True))
        self.mode_badge = Badge("LOCAL MODE")
        mode.addSpacing(12)
        mode.addWidget(self.mode_badge)
        mode.addStretch(1)
        self.root.addLayout(mode)
        ro = QHBoxLayout()
        self.r_engine = Readout("Local SynthID engine")
        self.r_state = Readout("Last verification")
        self.r_run = Readout("Last research run")
        self.r_integrity = Readout("Original file")
        for r in (self.r_engine, self.r_state, self.r_run, self.r_integrity):
            ro.addWidget(r)
        self.root.addLayout(ro)
        self.unavail = banner("")
        self.b_official = button("OPEN OFFICIAL GOOGLE VERIFICATION", primary=True)
        self.b_official.clicked.connect(lambda: (self.tabs.setCurrentWidget(self.t_online)))
        self.root.addWidget(self.unavail)
        self.root.addLayout(row(self.b_official, None))
        # ---- method selection + card
        mp = Panel("Method")
        self.method = QComboBox()
        self.method.currentIndexChanged.connect(self._show_method)
        mp.add(row(label("Method:", "Muted"), self.method, None))
        self.card = KVTable()
        self.card.setMinimumHeight(250)
        mp.add(self.card)
        self.root.addWidget(mp)
        # ---- tabs
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(520)
        self.root.addWidget(self.tabs, 1)
        self._build_detection()
        self._build_methods()
        self._build_sources()
        self._build_benchmark()
        self._build_comparison()
        self._build_online()
        self._build_experiments()
        self.root.addWidget(banner("LIMITATION: " + DEFAULT_LIMITATION, info=True))

    # ------------------------------------------------------------ tabs
    def _build_detection(self) -> None:
        b_run = button("RUN LOCAL DETECTION (current image)", primary=True)
        b_run.clicked.connect(lambda: self.ctl.run_synthid_detection())
        b_files = button("Run on chosen files...")
        b_files.clicked.connect(self._choose_files)
        self.records = DataTable(RECORD_COLUMNS, mono_cols=(1,))
        self.records.setMinimumHeight(180)
        self.context = label("", "Muted", wrap=True)
        self.t_detect = _tab(label("Method SID-M1: the configured local engine runs on a preserved copy. The original is "
                                   "hashed before and after every run. Without an engine the result is UNAVAILABLE and "
                                   "nothing is inferred.", "Muted", wrap=True),
                             row(b_run, b_files, None), self.records, self.context)
        self.tabs.addTab(self.t_detect, "Detection")

    def _build_methods(self) -> None:
        self.reg_table = DataTable(REGISTRY_COLUMNS)
        self.reg_table.setMinimumHeight(360)
        self.t_methods = _tab(label("Every method with the status it actually has on this machine. Methods marked NOT "
                                    "IMPLEMENTED are out of scope by design (docs/SYNTHID_RESEARCH_LAB.md).", "Muted",
                                    wrap=True), self.reg_table)
        self.tabs.addTab(self.t_methods, "Local Methods")

    def _build_sources(self) -> None:
        self.src_table = DataTable(SOURCE_COLUMNS)
        self.src_table.setMinimumHeight(360)
        self.src_problems = label("", "Muted", wrap=True)
        b = button("Re-validate catalogue")
        b.clicked.connect(self.ctl.revalidate_sources)
        self.t_sources = _tab(label("Curated, offline catalogue (config/synthid_sources.json plus an optional "
                                    "<workspace>/synthid_sources.json). SynthProvenance never fetches these URLs.", "Muted",
                                    wrap=True), row(b, None), self.src_table, self.src_problems)
        self.tabs.addTab(self.t_sources, "Research Sources")

    def _build_benchmark(self) -> None:
        self.ds = QLineEdit()
        self.ds.setPlaceholderText("Dataset folder with positive/ and negative/ (or manifest.csv: path,label,group,split)")
        b_browse = button("Browse...")
        b_browse.clicked.connect(self._choose_dataset)
        self.thr = QDoubleSpinBox()
        self.thr.setRange(0.0, 1.0)
        self.thr.setSingleStep(0.05)
        self.thr.setValue(0.5)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2**31 - 1)
        self.seed.setValue(20261002)
        b_run = button("RUN BENCHMARK", primary=True)
        b_run.clicked.connect(lambda: self.ctl.run_synthid_benchmark(self.ds.text().strip(), self.thr.value(),
                                                                      self.seed.value()))
        self.bm_kv = KVTable()
        self.bm_kv.setMinimumHeight(260)
        self.roc = RocWidget()
        self.groups = DataTable(["Group", "Kind", "n", "TPR", "FPR", "TPR 95% CI", "FPR 95% CI"])
        self.groups.setMinimumHeight(140)
        res = QHBoxLayout()
        res.addWidget(self.bm_kv, 2)
        res.addWidget(self.roc, 1)
        self.t_bench = _tab(label("Evaluates SID-M1 on researcher-labelled images (labels are ground truth supplied by you). "
                                  "Include real-image and other-generator controls under negative/<group>/. Metrics: AUC "
                                  "(bootstrap 95% CI), ROC, TPR, FPR, precision, recall, F1 (Wilson 95% CI).", "Muted",
                                  wrap=True),
                            row(self.ds, b_browse), row(label("Threshold", "Muted"), self.thr, label("Seed", "Muted"),
                                                        self.seed, b_run, None), res, self.groups)
        self.tabs.addTab(self.t_bench, "Benchmark")

    def _build_comparison(self) -> None:
        self.cmp = DataTable(["Condition", "Label", "Before", "After", "State", "Observation"])
        self.cmp.setMinimumHeight(260)
        self.t_cmp = _tab(label("SynthID before / after for every transformation of the current experiment. Each entry is a "
                                "TRANSFORMATION EXPERIMENT observation, never a removal claim.", "Muted", wrap=True),
                          self.cmp)
        self.tabs.addTab(self.t_cmp, "Comparison")

    def _build_online(self) -> None:
        self.online_state = banner("")
        self.dest = QComboBox()
        for d in DESTINATIONS:
            self.dest.addItem(d.name, d.dest_id)
        b_open = button("OPEN IMAGE IN OFFICIAL VERIFIER...", primary=True)
        b_open.clicked.connect(self._open_official)
        self.dest_table = DataTable(["Destination", "Operator", "URL", "Access", "Upload", "Notes"])
        self.dest_table.setMinimumHeight(130)
        self.dest_table.set_data(["Destination", "Operator", "URL", "Access", "Upload", "Notes"],
                                 [[d.name, d.operator, d.url, d.access, d.upload_method, d.notes] for d in DESTINATIONS])
        self.svc, self.rep, self.note = QLineEdit(), QLineEdit(), QLineEdit()
        self.svc.setPlaceholderText("Service / version (e.g. Gemini app, date)")
        self.rep.setPlaceholderText("Result exactly as reported by the service")
        self.note.setPlaceholderText("Note")
        b_rec = button("Record reported result")
        b_rec.clicked.connect(lambda: self.ctl.record_online_result(self.svc.text(), self.rep.text(), self.note.text()))
        self.hist = DataTable(["Opened (UTC)", "Destination", "URL", "File", "SHA-256", "Uploaded by SynthProvenance"])
        self.hist.setMinimumHeight(100)
        not_int = "\n".join(f"- {n}: {why}" for n, why in NOT_INTEGRATED)
        self.t_online = _tab(self.online_state, label(NO_UPLOAD, "Muted", wrap=True), self.dest_table,
                             row(label("Destination:", "Muted"), self.dest, b_open, None),
                             label("After checking the image in your browser, record what the service reported "
                                   "(stored as EXTERNAL, user-recorded, unverified):", "Muted", wrap=True),
                             row(self.svc, self.rep), row(self.note, b_rec), self.hist,
                             label("Not integrated:\n" + not_int, "Muted", wrap=True))
        self.tabs.addTab(self.t_online, "Online Verification")

    def _build_experiments(self) -> None:
        self.runs = DataTable(RUN_COLUMNS)
        self.runs.setMinimumHeight(150)
        self.runs.itemSelectionChanged.connect(self._show_run)
        self.matrix = DataTable(MATRIX_COLUMNS)
        self.matrix.setMinimumHeight(200)
        b_exp = button("EXPORT FOR PAPER (ZIP)...", primary=True)
        b_exp.clicked.connect(self._export)
        b_dir = button("Open run folder")
        b_dir.clicked.connect(lambda: self._selected_run() and self.ctl.open_path(
            self.ctl.research.run_dir(self._selected_run())))
        self.t_exp = _tab(label("SPX-SID runs. EXPORT FOR PAPER writes CSV, JSON, PDF, PNG and a ZIP (source/ output/ "
                                "metrics/ config/ logs/ report/) with SHA-256 and BLAKE3 manifests.", "Muted", wrap=True),
                          row(b_exp, b_dir, None), self.runs, label("SYNTHID RESEARCH MATRIX", "PanelTitle"), self.matrix)
        self.tabs.addTab(self.t_exp, "Experiments")

    # ------------------------------------------------------------ actions
    def _confirm(self, title: str, text: str) -> bool:
        if self.win.quiet:  # scripted/smoke runs never auto-confirm anything
            return False
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def _set_mode(self, online: bool) -> None:
        if online and not self.ctl.online.enabled:
            ok = self._confirm("Enable ONLINE OFFICIAL VERIFICATION",
                               "Online verification hands an image off to an official Google service in your browser. "
                               "SynthProvenance itself never uploads anything.\n\nEvery hand-off shows the exact destination "
                               "and asks again before anything opens.\n\nEnable online verification for this session?")
            if not ok:
                self.b_local.setChecked(True)
                return
            self.ctl.set_online_mode(True, confirmed=True)
            self.tabs.setCurrentWidget(self.t_online)
        elif not online and self.ctl.online.enabled:
            self.ctl.set_online_mode(False)
        self._mark()

    def _open_official(self) -> None:
        try:
            plan = self.ctl.online_plan(self.dest.currentData())
        except OnlinePolicyError as exc:
            self.ctl.error.emit("Online verification", str(exc))
            return
        if self._confirm("Open official verifier", plan.confirmation_text()):
            try:
                self.ctl.online_open(plan, consent=True)
            except OnlinePolicyError as exc:
                self.ctl.error.emit("Online verification", str(exc))

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Images for SynthID research detection", "",
                                                "Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp *.gif)")
        if paths:
            self.ctl.run_synthid_detection(paths)

    def _choose_dataset(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Benchmark dataset folder", self.ds.text())
        if d:
            self.ds.setText(d)

    def _selected_run(self) -> str:
        r = self.runs.currentRow()
        it = self.runs.item(r, 0) if r >= 0 else None
        return it.text() if it is not None else ""

    def _export(self) -> None:
        rid = self._selected_run()
        if not rid:
            self.ctl.error.emit("Export for paper", "Select a research run first.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export for paper", f"{rid}_paper.zip", "ZIP (*.zip)")
        if dest:
            self.ctl.export_synthid_paper(rid, dest)

    def _show_method(self) -> None:
        mid = self.method.currentData()
        if not mid:
            return
        m = self.ctl.registry.get(mid)
        self.card.set_rows([("Method ID", m.method_id), ("Method Name", m.method_name), ("Description", m.description),
                            ("Status", m.scientific_status), ("Validation", m.validation_status),
                            ("Local/Online", m.location), ("GPU", "required" if m.requires_gpu else "not required"),
                            ("Dataset Requirement", m.dataset_requirement), ("Research Maturity", m.research_maturity),
                            ("Source / license", f"{m.source} / {m.license}"),
                            ("Input formats", ", ".join(m.input_formats) or "-"), ("Output", m.output)])

    def _show_run(self) -> None:
        rid = self._selected_run()
        if not rid:
            return
        try:
            run = self.ctl.research.load(rid)
        except Exception as exc:  # noqa: BLE001 - unreadable runs are shown, not fatal
            self.matrix.set_data(["Error"], [[str(exc)]])
            return
        self.matrix.set_data(MATRIX_COLUMNS, [[r.get(c) if not isinstance(r.get(c), float) else fmt_num(r.get(c))
                                               for c in MATRIX_COLUMNS] for r in run.matrix])

    # ------------------------------------------------------------ refresh
    def refresh(self) -> None:
        ctl = self.ctl
        st = ctl.synthid.status()
        online = ctl.online.enabled
        self.b_online.setChecked(online)
        self.b_local.setChecked(not online)
        self.mode_badge.set_state("ONLINE MODE" if online else "LOCAL MODE",
                                  "Online verification hand-off enabled for this session" if online
                                  else "No network use; online verification OFF")
        self.r_engine.set("AVAILABLE" if st["available"] else "UNAVAILABLE", st["command"] or st["detail"])
        self.unavail.setVisible(not st["available"])
        self.b_official.setVisible(not st["available"])
        self.unavail.setText(f"LOCAL SYNTHID ENGINE: UNAVAILABLE\nReason: {UNAVAILABLE_REASON} No validated local SynthID "
                             "image detector is publicly available (see Research Sources). No result is fabricated. "
                             "Official verification is offered as an explicit, user-controlled online hand-off.")
        run = ctl.last_research_run
        if run is not None:
            last = run.records[-1] if run.records else {}
            self.r_state.set(last.get("state", run.status), last.get("detail", "")[:160])
            self.r_run.set(run.run_id, f"{run.kind} {run.status}", state=run.status)
            ok = run.original_unchanged
            self.r_integrity.set("UNCHANGED" if ok else ("CHANGED" if ok is False else "-"),
                                 "SHA-256 identical before and after the run" if ok else "", state="PRESERVED" if ok else
                                 ("INVALID" if ok is False else "UNKNOWN"))
            if run.kind == "DETECTION":
                self.records.set_data(RECORD_COLUMNS, [[r.get("image"), r.get("image_sha256", "")[:16], r.get("state"),
                                                        r.get("detector"), r.get("detector_version"), r.get("model_version"),
                                                        fmt_num(r.get("score")), fmt_num(r.get("confidence")),
                                                        fmt_num(r.get("runtime_ms"), 1), r.get("detail")] for r in run.records])
            if run.kind == "BENCHMARK":
                self._show_benchmark(run)
        else:
            img = ctl.research_image()
            self.r_state.set("NOT RUN", "Run local detection or record an official verification.")
            self.r_run.set("NONE", "")
            self.r_integrity.set("-", img.name if img else "no image", state="UNKNOWN")
        # method dropdown (keep selection)
        cur = self.method.currentData()
        self.method.blockSignals(True)
        self.method.clear()
        for m in ctl.registry.all():
            self.method.addItem(m.method_name + ("" if m.implemented else "  (not implemented)"), m.method_id)
        idx = self.method.findData(cur) if cur else -1
        self.method.setCurrentIndex(idx if idx >= 0 else 0)
        self.method.blockSignals(False)
        self._show_method()
        self.reg_table.set_data(REGISTRY_COLUMNS, ctl.registry.to_rows())
        self.src_table.set_data(SOURCE_COLUMNS, source_rows(ctl.sources))
        self.src_problems.setText(f"{len(ctl.sources)} valid source(s). " + (
            "Validation problems:\n" + "\n".join(ctl.source_problems) if ctl.source_problems else "No validation problems."))
        self.online_state.setText(("ONLINE OFFICIAL VERIFICATION: ENABLED for this session. Each hand-off shows the exact "
                                   "destination and asks for confirmation." if online else
                                   "ONLINE OFFICIAL VERIFICATION: OFF (LOCAL MODE). Switch the mode at the top to enable it "
                                   "explicitly."))
        self.hist.set_data(["Opened (UTC)", "Destination", "URL", "File", "SHA-256", "Uploaded by SynthProvenance"],
                           [[h["opened_utc"][:19], h["name"], h["url"], h["image_name"], h["image_sha256"][:16],
                             "NO"] for h in ctl.online.history])
        exp = ctl.experiment
        if exp:
            s = synthid_summary(exp, st)
            self.cmp.set_data(["Condition", "Label", "Before", "After", "State", "Observation"],
                              [[r["transformation_id"], r["label"], r["before"], r["after"], r["state"], r["observation"]]
                               for r in s["conditions"]])
            notes = (exp.synthid_baseline or {}).get("context") or []
            self.context.setText("\n".join(f"- {c}" for c in notes))
        keep = self._selected_run()
        runs = ctl.research.list_runs()
        self.runs.set_data(RUN_COLUMNS, [[r["run_id"], r["kind"], r["method"], r["status"], r["created"][:19], r["inputs"],
                                          r["original_unchanged"]] for r in runs])
        for i in range(self.runs.rowCount()):
            if self.runs.item(i, 0).text() == (keep or (run.run_id if run else "")):
                self.runs.selectRow(i)
                break

    def _show_benchmark(self, run) -> None:
        b = run.benchmark or {}
        m = b.get("metrics") or {}

        def ci(v):
            return f"{v[0]:.3f} - {v[1]:.3f}" if v else "-"

        self.bm_kv.set_rows([("Run", run.run_id), ("Status", b.get("status", run.status)), ("Detail", b.get("detail", "")),
                             ("Items / positives / negatives", f"{b.get('n_items')} / {b.get('n_positive')} / "
                                                               f"{b.get('n_negative')}"),
                             ("Scored / abstained", f"{b.get('n_scored')} / {b.get('n_abstained')}"),
                             ("Score basis", ", ".join(b.get("score_basis") or []) or "-"),
                             ("AUC (95% bootstrap CI)", f"{fmt_num(m.get('auc'))} ({ci(m.get('auc_ci95'))})"),
                             ("Threshold", fmt_num(m.get("threshold"), 3)),
                             ("TPR (95% CI)", f"{fmt_num(m.get('tpr'))} ({ci(m.get('tpr_ci95'))})"),
                             ("FPR (95% CI)", f"{fmt_num(m.get('fpr'))} ({ci(m.get('fpr_ci95'))})"),
                             ("Precision / Recall / F1", f"{fmt_num(m.get('precision'))} / {fmt_num(m.get('recall'))} / "
                                                         f"{fmt_num(m.get('f1'))}"),
                             ("TP / FP / TN / FN", f"{m.get('tp', '-')} / {m.get('fp', '-')} / {m.get('tn', '-')} / "
                                                   f"{m.get('fn', '-')}")])
        self.roc.set_points([(p[0], p[1]) for p in b.get("roc") or []])
        self.groups.set_data(["Group", "Kind", "n", "TPR", "FPR", "TPR 95% CI", "FPR 95% CI"],
                             [[g["group"], g["kind"], g["n"], fmt_num(g.get("tpr")), fmt_num(g.get("fpr")),
                               ci(g.get("tpr_ci95")), ci(g.get("fpr_ci95"))] for g in b.get("groups") or []])


SynthIDView = SynthIDResearchLabView
