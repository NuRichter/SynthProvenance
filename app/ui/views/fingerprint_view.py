"""Fingerprint Research Lab: the flagship module.

Tabs: Analysis (run any method, method card, result readouts and maps), Separation &
Reconstruction (the six-panel study on a controlled surrogate), Surrogate Ground-Truth
Lab (embed a keyed signal, see the detector and ground truth), Robustness (persistence
sweep), Hypothesis Lab (the speculative hypotheses), Methods (the full registry), and
Experiments (run history + EXPORT FOR PAPER).

Every method the UI can run is a real, validated capability. Methods that need a
deep-learning runtime show UNAVAILABLE with the reason; detector-evasion methods show
NOT IMPLEMENTED with the reason. No fake buttons.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from app.core.method_composer import STAGE_OPS, Pipeline, preset, PRESETS
from app.core.research_assistant import GOALS
from app.research.methods import REGISTRY_COLUMNS, MethodRegistry
from app.research.surrogate import AVAILABLE_FAMILIES, DEFAULT_THRESHOLD_Z
from app.ui.views.base import View, row
from app.ui.widgets.common import Badge, DataTable, KVTable, Panel, Readout, banner, button, fmt_num, label

# research goal label -> preset method for Easy Mode
GOAL_METHOD = {"Understand Provenance": "Method 02", "Find Fingerprint": "Method 03", "Study Diffusion Trace": "Method 11",
               "Study Spectral Trace": "Method 13", "Study Watermark": "Method 39", "Compare Images": "Method 25",
               "Run Controlled Experiment": "Method 34"}

PANELS = [("original", "Original"), ("candidate_signal", "Candidate Signal"), ("estimated_content", "Estimated Content"),
          ("residual", "Residual"), ("reconstructed", "Reconstructed"), ("difference", "Difference")]
RUN_COLUMNS = ["Run", "Method", "Maturity", "Status", "Created (UTC)", "Runtime s", "Original unchanged"]


def _map_label(title: str) -> QLabel:
    lab = QLabel(title + "\n(no data)")
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setMinimumSize(180, 150)
    lab.setStyleSheet("border: 1px solid #243140; background:#10171D; color:#7D8C9B;")
    return lab


class FingerprintLabView(View):
    title = "Fingerprint Research Lab"
    subtitle = ("Local forensic fingerprint research on decoded pixels. Descriptive statistics, controlled-surrogate "
                "studies with known ground truth, and explicit hypothesis tests. No AI/human verdict is produced.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        self.registry = MethodRegistry()
        # quick run: research goal -> preset method (Easy Mode itself is a separate application shell)
        self.easy = QWidget()
        el = QHBoxLayout(self.easy)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(label("QUICK RUN  \u00b7  RESEARCH GOAL:", "PanelTitle"))
        self.goal = QComboBox()
        self.goal.addItems(list(GOAL_METHOD))
        el.addWidget(self.goal)
        b_easy = button("ANALYZE  →  RUN", primary=True)
        b_easy.clicked.connect(self._run_easy)
        el.addWidget(b_easy)
        b_adv = button("Research Assistant: recommend")
        b_adv.clicked.connect(self._advise)
        el.addWidget(b_adv)
        el.addStretch(1)
        self.root.addWidget(self.easy)
        ro = QHBoxLayout()
        self.r_method = Readout("Selected method")
        self.r_status = Readout("Last run")
        self.r_integrity = Readout("Original file")
        self.r_ready = Readout("Methods ready")
        for r in (self.r_method, self.r_status, self.r_integrity, self.r_ready):
            ro.addWidget(r)
        self.root.addLayout(ro)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(560)
        self.root.addWidget(self.tabs, 1)
        self._build_analysis()
        self._build_separation()
        self._build_surrogate()
        self._build_robustness()
        self._build_hypotheses()
        self._build_composer()
        self._build_assistant()
        self._build_methods()
        self._build_experiments()
        self.root.addWidget(banner("Controlled surrogate studies run only against a local, keyed signal with known "
                                   "ground truth. SynthProvenance does not search for transformations that defeat a "
                                   "watermark detector and does not attack SynthID or any real watermark.", info=True))

    # ---- surrogate parameter form (shared)
    def _surrogate_form(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.s_family = QComboBox()
        self.s_family.addItems(list(AVAILABLE_FAMILIES))
        self.s_strength = QDoubleSpinBox()
        self.s_strength.setRange(0.5, 12.0)
        self.s_strength.setValue(3.0)
        self.s_strength.setSingleStep(0.5)
        self.s_key = QSpinBox()
        self.s_key.setRange(1, 2**31 - 1)
        self.s_key.setValue(20261005)
        for lab_, wdg in (("Family", self.s_family), ("Strength (8-bit RMS)", self.s_strength), ("Key", self.s_key)):
            lay.addWidget(label(lab_, "Muted"))
            lay.addWidget(wdg)
        lay.addStretch(1)
        return w

    def _surrogate_cfg(self) -> dict:
        return {"family": self.s_family.currentText(), "strength": self.s_strength.value(), "key": self.s_key.value(),
                "threshold_z": DEFAULT_THRESHOLD_Z}

    # ---- Analysis tab
    def _build_analysis(self) -> None:
        self.method = QComboBox()
        self.method.currentIndexChanged.connect(self._show_card)
        self.b_run = button("RUN METHOD (current image)", primary=True)
        self.b_run.clicked.connect(self._run_selected)
        self.card = KVTable()
        self.card.setMinimumHeight(300)
        self.readouts = DataTable(["Readout", "Value"], mono_cols=(1,))
        self.readouts.setMinimumHeight(150)
        self.maps_host = QWidget()
        self.maps_grid = QGridLayout(self.maps_host)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(self.maps_host)
        sa.setMinimumHeight(220)
        self.fail = DataTable(["Failure mode", "Symptom", "Likely cause", "Affected metric", "Possible improvement"])
        self.fail.setMinimumHeight(120)
        self.result_card = KVTable()
        self.result_card.setMinimumHeight(150)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addLayout(row(label("Method:", "Muted"), self.method, self.b_run, None))
        lay.addWidget(label("WHAT DID WE FIND?", "LayerTitle"))
        lay.addWidget(self.result_card)
        lay.addWidget(label("Why this method? / Method card", "PanelTitle"))
        lay.addWidget(self.card)
        lay.addLayout(row(self._wrap("RESULT READOUTS", self.readouts), self._wrap("OUTPUT MAPS", sa)))
        lay.addWidget(label("Failure analysis", "PanelTitle"))
        lay.addWidget(self.fail)
        self.tabs.addTab(w, "Analysis")

    def _wrap(self, title, widget):
        p = Panel(title)
        p.add(widget)
        return p

    # ---- Separation tab
    def _build_separation(self) -> None:
        self.sep_method = QComboBox()
        for code in ("Method 34", "Method 35", "Method 36", "Method 37", "Method 38", "Method 42"):
            m = self.registry.get(code)
            self.sep_method.addItem(f"{m.method_id}  {m.name}", code)
        b = button("RUN SEPARATION STUDY (controlled surrogate)", primary=True)
        b.clicked.connect(lambda: self.ctl.run_fingerprint_method(self.sep_method.currentData(),
                                                                  surrogate=self._surrogate_cfg()))
        self.sep_panels = {}
        grid = QGridLayout()
        for i, (key, title) in enumerate(PANELS):
            lab = _map_label(title)
            self.sep_panels[key] = lab
            grid.addWidget(label(title, "ReadoutCaption"), (i // 3) * 2, i % 3)
            grid.addWidget(lab, (i // 3) * 2 + 1, i % 3)
        self.sep_kv = KVTable()
        self.sep_kv.setMinimumHeight(180)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("A keyed surrogate signal is embedded on a copy of the current image; the chosen separation "
                            "estimates content and the candidate signal, scored against the known ground truth.", "Muted",
                            wrap=True))
        lay.addWidget(self._surrogate_form())
        lay.addLayout(row(label("Method:", "Muted"), self.sep_method, b, None))
        gw = QWidget()
        gw.setLayout(grid)
        lay.addWidget(gw)
        lay.addWidget(label("Recovery & reconstruction (vs ground truth)", "PanelTitle"))
        lay.addWidget(self.sep_kv)
        self.tabs.addTab(w, "Separation & Reconstruction")

    # ---- Surrogate ground-truth tab
    def _build_surrogate(self) -> None:
        b_embed = button("EMBED SURROGATE ON A COPY (SAVE AS)...", primary=True)
        b_embed.clicked.connect(self._embed)
        b_detect = button("RUN DETECTOR ON CURRENT IMAGE")
        b_detect.clicked.connect(lambda: self.ctl.run_fingerprint_method("Method 00") or None)
        self.sur_kv = KVTable()
        self.sur_kv.setMinimumHeight(220)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("CLEAN IMAGE -> SURROGATE EMBEDDER -> WATERMARKED IMAGE -> LOCAL DETECTOR -> GROUND TRUTH. "
                            "The embedder writes a new file; the original is never modified. The detector is blind "
                            "(needs only the key).", "Muted", wrap=True))
        lay.addWidget(self._surrogate_form())
        lay.addLayout(row(b_embed, None))
        lay.addWidget(self.sur_kv)
        lay.addWidget(banner("This is a transparent laboratory signal with known ground truth. It is not SynthID and "
                             "does not imitate SynthID internals.", info=True))
        self.tabs.addTab(w, "Surrogate Ground Truth")

    # ---- Robustness tab
    def _build_robustness(self) -> None:
        b = button("RUN ROBUSTNESS SWEEP (controlled surrogate)", primary=True)
        b.clicked.connect(lambda: self.ctl.run_fingerprint_method("Method 39", surrogate=self._surrogate_cfg()))
        self.rob_table = DataTable(["Transform", "Severity", "PSNR dB", "SSIM", "Persistence", "Detector z", "Detected"])
        self.rob_table.setMinimumHeight(360)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("A fixed battery of standard transformations is applied to a surrogate-watermarked copy; "
                            "persistence = detector z after / before. This characterises robustness (WAVES-style); it "
                            "is not a detector-evasion search.", "Muted", wrap=True))
        lay.addWidget(self._surrogate_form())
        lay.addLayout(row(b, None))
        lay.addWidget(self.rob_table)
        self.tabs.addTab(w, "Robustness")

    # ---- Hypothesis tab
    def _build_hypotheses(self) -> None:
        self.hyp_method = QComboBox()
        for code in ("Method 47", "Method 48", "Method 49", "Method 50", "Method 51", "Method 52"):
            m = self.registry.get(code)
            self.hyp_method.addItem(f"{m.method_id}  {m.name}", code)
        b = button("RUN HYPOTHESIS TEST (controlled data)", primary=True)
        b.clicked.connect(lambda: self.ctl.run_fingerprint_method(self.hyp_method.currentData(),
                                                                  surrogate=self._surrogate_cfg()))
        self.hyp_kv = KVTable()
        self.hyp_kv.setMinimumHeight(320)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Speculative research hypotheses, evaluated only on controlled data with ground truth. A "
                            "single positive result is never proof: the verdict is SUPPORTED / INCONCLUSIVE / NOT "
                            "SUPPORTED ON THIS CONTROLLED CASE.", "Muted", wrap=True))
        lay.addWidget(self._surrogate_form())
        lay.addLayout(row(label("Hypothesis:", "Muted"), self.hyp_method, b, None))
        lay.addWidget(self.hyp_kv)
        self.tabs.addTab(w, "Hypothesis Lab")

    # ---- Method Composer tab
    def _build_composer(self) -> None:
        self.preset = QComboBox()
        for p in PRESETS:
            self.preset.addItem(p, p)
        b_load = button("Load preset")
        b_load.clicked.connect(self._load_preset)
        self.nodes_table = DataTable(["#", "Stage", "Enabled"])
        self.nodes_table.setMinimumHeight(150)
        self.op_pick = QComboBox()
        for op, meta in STAGE_OPS.items():
            self.op_pick.addItem(f"{meta['label']}  ({op})", op)
        b_add = button("Add stage")
        b_add.clicked.connect(self._add_stage)
        b_del = button("Remove last")
        b_del.clicked.connect(lambda: (self._nodes.pop() if self._nodes else None, self._refresh_nodes()))
        b_run = button("RUN PIPELINE (controlled surrogate)", primary=True)
        b_run.clicked.connect(self._run_pipeline)
        b_save = button("Export pipeline JSON...")
        b_save.clicked.connect(self._save_pipeline)
        self.comp_stages = DataTable(["#", "Stage", "Energy", "Std", "Candidate vs known"])
        self.comp_stages.setMinimumHeight(200)
        self._nodes: list = []
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Chain analysis/estimation/reconstruction stages into a reproducible pipeline (e.g. "
                            "Residual → Wavelet → Robust-PCA → Reconstruct). On a controlled surrogate each "
                            "stage's candidate is scored against the known signal. Pipelines export to JSON and reproduce.",
                            "Muted", wrap=True))
        lay.addWidget(self._surrogate_form())
        lay.addLayout(row(self.preset, b_load, None))
        lay.addLayout(row(self.op_pick, b_add, b_del, None))
        lay.addWidget(self.nodes_table)
        lay.addLayout(row(b_run, b_save, None))
        lay.addWidget(label("Stage outputs (last run)", "PanelTitle"))
        lay.addWidget(self.comp_stages)
        self.tabs.addTab(w, "Method Composer")

    def _build_assistant(self) -> None:
        self.asg_goal = QComboBox()
        self.asg_goal.addItems(list(GOALS))
        b = button("RECOMMEND METHODS", primary=True)
        b.clicked.connect(self._advise)
        b2 = button("DISCOVER EXPERIMENTS")
        b2.clicked.connect(self._discover)
        self.asg_rationale = label("", "Muted", wrap=True)
        self.asg_table = DataTable(["Method", "Name", "Availability", "Required data", "Cost", "Reason"])
        self.asg_table.setMinimumHeight(220)
        self.asg_notes = label("", "Muted", wrap=True)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("The Research Assistant inspects the current image, provenance, format, resolution and the "
                            "available local engines, then recommends methods and controls with an explicit reason. It "
                            "never runs anything automatically.", "Muted", wrap=True))
        lay.addLayout(row(label("Research goal:", "Muted"), self.asg_goal, b, b2, None))
        lay.addWidget(self.asg_rationale)
        lay.addWidget(self.asg_table)
        lay.addWidget(self.asg_notes)
        self.tabs.addTab(w, "Research Assistant")

    # ---- Methods registry tab
    def _build_methods(self) -> None:
        self.reg_table = DataTable(REGISTRY_COLUMNS)
        self.reg_table.setMinimumHeight(440)
        self.reg_table.set_data(REGISTRY_COLUMNS, self.registry.to_rows())
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Method 00 - Method 54. READY methods run locally now; UNAVAILABLE methods need a "
                            "deep-learning runtime and weights that are not bundled; NOT_IMPLEMENTED methods are out of "
                            "scope by design (detector-evasion). See each method's card in the Analysis tab.", "Muted",
                            wrap=True))
        lay.addWidget(self.reg_table)
        self.tabs.addTab(w, "Methods")

    # ---- Experiments tab
    def _build_experiments(self) -> None:
        self.runs = DataTable(RUN_COLUMNS)
        self.runs.setMinimumHeight(260)
        self.runs.itemSelectionChanged.connect(self._show_run)
        b_exp = button("EXPORT FOR PAPER (ZIP)...", primary=True)
        b_exp.clicked.connect(self._export)
        b_dir = button("Open run folder")
        b_dir.clicked.connect(lambda: self._sel() and self.ctl.open_path(self.ctl.lab.run_dir(self._sel())))
        self.run_kv = KVTable()
        self.run_kv.setMinimumHeight(200)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("SPX-FP runs. EXPORT FOR PAPER writes CSV, JSON, PDF, PNG and a ZIP (inputs/ maps/ config/ "
                            "logs/ report/) with SHA-256 and BLAKE3 manifests.", "Muted", wrap=True))
        lay.addLayout(row(b_exp, b_dir, None))
        lay.addWidget(self.runs)
        lay.addWidget(self.run_kv)
        self.tabs.addTab(w, "Experiments")

    # ---- actions
    def _run_selected(self) -> None:
        mid = self.method.currentData()
        if not mid:
            return
        m = self.registry.get(mid)
        sur = self._surrogate_cfg() if (m.requires_ground_truth or m.capability.startswith(("sep:", "hyp:"))
                                        or m.capability in ("robustness", "persistence_map")) else None
        self.ctl.run_fingerprint_method(mid, surrogate=sur)

    def _run_easy(self) -> None:
        goal = self.goal.currentText()
        mid = GOAL_METHOD.get(goal, "Method 13")
        m = self.registry.get(mid)
        sur = self._surrogate_cfg() if (m.requires_ground_truth or m.capability.startswith(("sep:", "hyp:", "frontier:"))
                                        or m.capability in ("robustness", "persistence_map", "reconstruction")) else None
        self.tabs.setCurrentIndex(0)
        self.ctl.run_fingerprint_method(mid, surrogate=sur)

    def _advise(self) -> None:
        goal = self.asg_goal.currentText() if hasattr(self, "asg_goal") else self.goal.currentText()
        adv = self.ctl.advise(goal, has_ground_truth=True, n_references=0)
        self.tabs.setCurrentWidget(self.asg_table.parent())
        self.asg_rationale.setText(adv.rationale)
        self.asg_table.set_data(["Method", "Name", "Availability", "Required data", "Cost", "Reason"],
                                [[r.method_id, r.name, r.availability, r.required_data, r.compute_cost, r.reason]
                                 for r in adv.recommendations + adv.alternatives])
        self.asg_notes.setText("\n".join("• " + n for n in adv.notes))

    def _discover(self) -> None:
        rows = self.ctl.discover_experiments(has_ground_truth=True, n_references=5)
        self.asg_rationale.setText("Candidate experiments ranked by expected scientific value given a controlled "
                                   "surrogate and references.")
        self.asg_table.set_data(["Method", "Name", "Availability", "Required data", "Cost", "Reason"],
                                [[d["method_id"], d["name"], f"score {d['score']}", d["required_dataset"],
                                  d["expected_cost"], d["validation_plan"]] for d in rows])
        self.asg_notes.setText("")

    def _load_preset(self) -> None:
        self._nodes = list(preset(self.preset.currentData()).nodes)
        self._refresh_nodes()

    def _add_stage(self) -> None:
        self._nodes.append(Pipeline.node(self.op_pick.currentData()))
        self._refresh_nodes()

    def _refresh_nodes(self) -> None:
        self.nodes_table.set_data(["#", "Stage", "Enabled"],
                                  [[i + 1, STAGE_OPS[n["op"]]["label"], "yes" if n.get("enabled", True) else "no"]
                                   for i, n in enumerate(self._nodes)])

    def _run_pipeline(self) -> None:
        if not self._nodes:
            self.ctl.error.emit("Method composer", "Add at least one stage or load a preset.")
            return
        self.ctl.run_composer(self._nodes, self.preset.currentData() or "pipeline", surrogate=self._surrogate_cfg())

    def _save_pipeline(self) -> None:
        if not self._nodes:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export pipeline JSON", "pipeline.json", "JSON (*.json)")
        if dest:
            import json
            from pathlib import Path
            Path(dest).write_text(json.dumps(Pipeline(self.preset.currentData() or "pipeline", self._nodes).to_dict(),
                                             indent=2), encoding="utf-8")
            self.ctl.info.emit(f"Pipeline exported: {Path(dest).name}")

    def _embed(self) -> None:
        if self.ctl.research_image() is None:
            self.ctl.error.emit("No image", "Open an image first.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save surrogate-watermarked copy",
                                              f"surrogate_{self.s_family.currentText()}.png", "PNG (*.png)")
        if dest:
            self.ctl.embed_surrogate(self._surrogate_cfg(), dest)

    def _sel(self) -> str:
        r = self.runs.currentRow()
        it = self.runs.item(r, 0) if r >= 0 else None
        return it.text() if it is not None else ""

    def _export(self) -> None:
        rid = self._sel()
        if not rid:
            self.ctl.error.emit("Export for paper", "Select a run first.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export for paper", f"{rid}_paper.zip", "ZIP (*.zip)")
        if dest:
            self.ctl.export_fingerprint_paper(rid, dest)

    def _show_card(self) -> None:
        mid = self.method.currentData()
        if not mid:
            return
        m = self.registry.get(mid)
        self.card.set_rows(m.card())
        self.r_method.set(m.method_id, m.name, state="READY" if m.runnable else
                          ("UNAVAILABLE" if m.availability == "UNAVAILABLE" else "NOT IMPLEMENTED"))
        self.b_run.setEnabled(m.runnable)

    def _show_run(self) -> None:
        rid = self._sel()
        if not rid:
            return
        try:
            run = self.ctl.lab.load(rid)
        except Exception as exc:  # noqa: BLE001
            self.run_kv.set_rows([("Error", str(exc))])
            return
        res = run.result or {}
        rows_ = [("Run", run.run_id), ("Method", f"{run.method_id} {run.method_name}"), ("Status", run.status),
                 ("Maturity", run.maturity), ("Runtime", f"{run.runtime_s:.2f} s"),
                 ("Original unchanged", str(run.original_unchanged)), ("Detail", run.detail)]
        rows_ += [(f"readout: {k}", fmt_num(v)) for k, v in (res.get("readouts") or {}).items()]
        self.run_kv.set_rows(rows_)

    # ---- refresh
    def refresh(self) -> None:
        cur = self.method.currentData()
        self.method.blockSignals(True)
        self.method.clear()
        for m in self.registry.all():
            suffix = "" if m.runnable else (f"  ({m.availability})")
            self.method.addItem(f"{m.method_id}  {m.name}{suffix}", m.method_id)
        idx = self.method.findData(cur) if cur else 0
        self.method.setCurrentIndex(idx if idx >= 0 else 0)
        self.method.blockSignals(False)
        self._show_card()
        self.r_ready.set(f"{len(self.registry.ready())}/{len(self.registry.all())}", "methods runnable locally")
        img = self.ctl.research_image()
        run = self.ctl.last_fp_run
        if run is not None:
            self.r_status.set(run.status, f"{run.method_id} {run.run_id}", state=run.status if run.status in
                              ("COMPLETE", "FAILED", "UNAVAILABLE") else "RESEARCH")
            ok = run.original_unchanged
            self.r_integrity.set("UNCHANGED" if ok else ("CHANGED" if ok is False else "-"),
                                 state="PRESERVED" if ok else ("INVALID" if ok is False else "UNKNOWN"))
            self._apply_run(run)
        else:
            self.r_status.set("NOT RUN", "Select a method and run it.")
            self.r_integrity.set("-", img.name if img else "no image", state="UNKNOWN")
        self.runs.set_data(RUN_COLUMNS, [[r["run_id"], r["method"], r["maturity"], r["status"], r["created"][:19],
                                          fmt_num(r["runtime_s"], 2), r["original_unchanged"]]
                                         for r in self.ctl.lab.list_runs()])
        comp = getattr(self.ctl, "last_composer", None)
        if comp is not None:
            self.comp_stages.set_data(["#", "Stage", "Energy", "Std", "Candidate vs known"],
                                      [[s["index"], s["label"], fmt_num(s["energy"], 6), fmt_num(s["std"], 4),
                                        fmt_num(s["candidate_vs_known_corr"], 4)] for s in comp.stages])


    def _result_card(self, run) -> None:
        res = run.result or {}
        ro = res.get("readouts") or {}
        gt = res.get("ground_truth") or {}
        recon = res.get("reconstruction") or {}
        observation = run.detail or run.status
        conf = ro.get("Verdict") or (f"candidate vs known {fmt_num(gt.get('candidate_vs_known_corr'), 3)}"
                                     if gt.get("candidate_vs_known_corr") is not None else "descriptive measurement")
        pix = ("PSNR {p} dB / SSIM {s}".format(p=fmt_num(recon.get("psnr_db"), 1), s=fmt_num(recon.get("ssim"), 3))
               if recon.get("psnr_db") is not None else "original preserved; analysis on a copy")
        interp = res.get("note") or ("Controlled-surrogate result scored against ground truth." if run.surrogate else
                                     "Descriptive forensic measurement; not an AI/human verdict.")
        limits = "; ".join(f.get("possible_improvement", "") for f in (run.failure_analysis or [])[:2]) or \
            "See the method card for known limitations."
        self.result_card.set_rows([("Observation", observation), ("Method", f"{run.method_id} {run.method_name}"),
                                   ("Confidence / verdict", str(conf)), ("Pixel impact", pix),
                                   ("Research interpretation", interp), ("Limitations", limits)])

    def _apply_run(self, run) -> None:
        res = run.result or {}
        self._result_card(run)
        self.readouts.set_data(["Readout", "Value"], [[k, fmt_num(v)] for k, v in (res.get("readouts") or {}).items()])
        self.fail.set_data(["Failure mode", "Symptom", "Likely cause", "Affected metric", "Possible improvement"],
                           [[f.get("failure_mode"), f.get("symptom"), f.get("likely_cause"), f.get("affected_metric"),
                             f.get("possible_improvement")] for f in (run.failure_analysis or [])])
        self._load_maps_from_run(run, self.maps_grid)
        # separation panels
        if run.method_id in ("Method 34", "Method 35", "Method 36", "Method 37", "Method 38", "Method 41", "Method 42"):
            self._load_panels_from_run(run)
            gt = res.get("ground_truth") or {}
            recon = res.get("reconstruction") or {}
            self.sep_kv.set_rows([("Method", run.method_name), ("Recon PSNR (dB)", fmt_num(recon.get("psnr_db"), 2)),
                                  ("Recon SSIM", fmt_num(recon.get("ssim"), 4)), ("LPIPS", recon.get("lpips", "-")),
                                  ("Candidate vs known", fmt_num(gt.get("candidate_vs_known_corr"), 4)),
                                  ("Recovered energy fraction", fmt_num(gt.get("recovered_energy_fraction"), 4)),
                                  ("Signal reduction", fmt_num(gt.get("signal_reduction"), 4)),
                                  ("Still detected after", str(gt.get("still_detected_after")))])
        if run.method_id == "Method 39":
            data = res.get("data") or {}
            self.rob_table.set_data(["Transform", "Severity", "PSNR dB", "SSIM", "Persistence", "Detector z", "Detected"],
                                    [[r["label"], r["severity"], fmt_num(r["psnr_db"], 1), fmt_num(r["ssim"], 3),
                                      fmt_num(r["persistence"], 2), fmt_num(r["score_after"], 1), r["detected"]]
                                     for r in data.get("rows", [])])
        if run.method_id in ("Method 47", "Method 48", "Method 49", "Method 50", "Method 51", "Method 52"):
            data = res.get("data") or {}
            ev = data.get("evidence") or {}
            rows_ = [("Hypothesis", data.get("hypothesis", run.method_name)), ("Verdict", data.get("verdict", "-"))]
            rows_ += [(k, fmt_num(v) if isinstance(v, (int, float)) else str(v)[:80]) for k, v in ev.items()
                      if not isinstance(v, (list, dict))]
            rows_ += [("Failure modes", "; ".join(data.get("failure_modes", [])))]
            self.hyp_kv.set_rows(rows_)
        if run.method_id == "Method 00" and (res.get("ground_truth") or run.surrogate):
            self.sur_kv.set_rows([("Note", "Use EMBED to create a surrogate case; the detector readouts appear after a "
                                   "separation or robustness run.")])

    def _load_maps_from_run(self, run, grid: QGridLayout) -> None:
        while grid.count():
            it = grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for i, m in enumerate(run.maps or []):
            lab = _map_label(m["name"])
            try:
                p = self.ctl.lab.run_dir(run.run_id) / m["file"]
                if p.is_file():
                    lab.setPixmap(QPixmap(str(p)).scaled(220, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
                    lab.setToolTip(m["name"])
            except Exception:  # noqa: BLE001
                pass
            grid.addWidget(label(m["name"], "ReadoutCaption"), (i // 3) * 2, i % 3)
            grid.addWidget(lab, (i // 3) * 2 + 1, i % 3)

    def _load_panels_from_run(self, run) -> None:
        by = {m["name"]: m for m in (run.maps or [])}
        for key, lab in self.sep_panels.items():
            m = by.get(key)
            if m:
                p = self.ctl.lab.run_dir(run.run_id) / m["file"]
                if p.is_file():
                    lab.setPixmap(QPixmap(str(p)).scaled(220, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
                    continue
            lab.setText(f"{key}\n(no data)")
