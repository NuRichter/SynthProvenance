"""TruthScan Cross-Detector Research Lab (Expert Mode).

SynthProvenance is the INDEPENDENT FORENSIC SYSTEM; TruthScan is an EXTERNAL DETECTOR whose
result is imported (user-supplied) and studied, never trusted as ground truth and never
fetched by this app. Tabs: Overview, External Result, Local Analysis, Agreement,
Disagreement, Heatmap Analysis, Transformation Study, Research Questions, Export.

Nothing here uploads an image. The optional browser hand-off opens TruthScan's site after
explicit consent; the researcher uploads manually and imports the result back.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit,
                               QTabWidget, QVBoxLayout, QWidget)

from app.research import cross_detector as XD
from app.ui.views.base import View, row
from app.ui.widgets.common import DataTable, KVTable, Panel, Readout, banner, button, fmt_num, label

GT_ITEMS = [f"LEVEL {k} - {v}" for k, v in XD.GROUND_TRUTH_LEVELS.items()]
DIR_ITEMS = ["UNKNOWN", XD.LEANS_SYNTHETIC, XD.LEANS_AUTHENTIC]
RUN_COLUMNS = ["Run", "Detector", "Outcome", "Ground truth", "Image", "Created (UTC)"]


class CrossDetectorView(View):
    title = "TruthScan Cross-Detector Lab"
    subtitle = ("Compare an external detector's result with SynthProvenance's independent local evidence. One detector "
                "is an opinion; multiple independent measurements create evidence. Local-only: TruthScan results are "
                "imported (user-supplied); this app never uploads an image.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        ro = QHBoxLayout()
        self.r_outcome = Readout("Comparison outcome")
        self.r_external = Readout("External detector")
        self.r_local = Readout("Local evidence")
        self.r_gt = Readout("Ground truth")
        for r in (self.r_outcome, self.r_external, self.r_local, self.r_gt):
            ro.addWidget(r)
        self.root.addLayout(ro)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(560)
        self.root.addWidget(self.tabs, 1)
        self._build_overview()
        self._build_external()
        self._build_local()
        self._build_agreement()
        self._build_disagreement()
        self._build_heatmap()
        self._build_transformation()
        self._build_questions()
        self._build_export()
        self.root.addWidget(banner("SynthProvenance does not declare the external detector wrong or itself correct. It "
                                   "reports an independent evidence profile under the tested condition and names the "
                                   "ground-truth level. TruthScan integration is OFF by default and never uploads an "
                                   "image from this app.", info=True))

    # ---- Overview
    def _build_overview(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("DETECT → DECOMPOSE → COMPARE → RESEARCH → MEASURE → REPRODUCE",
                            "LayerTitle"))
        lay.addWidget(label("1. Open an image.  2. Import a TruthScan result (or enter it) on the External Result tab.  "
                            "3. Set the ground-truth level.  4. RUN CROSS-DETECTOR STUDY.  5. Read Agreement / "
                            "Disagreement and export the report.", "Muted", wrap=True))
        gt = QHBoxLayout()
        self.gt_level = QComboBox()
        self.gt_level.addItems(GT_ITEMS)
        self.gt_dir = QComboBox()
        self.gt_dir.addItems(DIR_ITEMS)
        gt.addWidget(label("Ground-truth level:", "Muted"))
        gt.addWidget(self.gt_level, 1)
        gt.addWidget(label("Known direction:", "Muted"))
        gt.addWidget(self.gt_dir)
        gt.addStretch(1)
        lay.addLayout(gt)
        b_run = button("RUN CROSS-DETECTOR STUDY (local pipeline + comparison)", primary=True)
        b_run.clicked.connect(self._run_study)
        lay.addLayout(row(b_run, None))
        self.ov_evidence_map = QPlainTextEdit()
        self.ov_evidence_map.setReadOnly(True)
        self.ov_evidence_map.setMaximumHeight(170)
        self.ov_evidence_map.setPlainText(self._evidence_map_art())
        lay.addWidget(label("EXTERNAL EVIDENCE MAP", "PanelTitle"))
        lay.addWidget(self.ov_evidence_map)
        self.ov_statement = label("", "Muted", wrap=True)
        lay.addWidget(label("CURRENT STUDY", "PanelTitle"))
        lay.addWidget(self.ov_statement)
        self.tabs.addTab(w, "Overview")

    @staticmethod
    def _evidence_map_art() -> str:
        return ("                     IMAGE\n"
                "                       |\n"
                "         +-------------+-------------+\n"
                "         v             v             v\n"
                "       C2PA        Metadata       Pixels\n"
                "         |             |             |\n"
                "         +-------------+-------------+\n"
                "                       v\n"
                "              SynthProvenance (independent)\n"
                "                       |\n"
                "                       v\n"
                "              External Detector (TruthScan)\n"
                "                       |\n"
                "                       v\n"
                "                   COMPARISON")

    # ---- External Result (import + manual entry + browser hand-off)
    def _build_external(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("IMPORT TRUTHSCAN RESULT (user-supplied; nothing is uploaded).", "LayerTitle"))
        p_json = Panel("Import JSON result")
        self.json_in = QPlainTextEdit()
        self.json_in.setPlaceholderText('Paste the detector\'s JSON result here, e.g. {"result": {"final_result": '
                                        '"AI Generated", "confidence": 0.97, "detection_step": 3, ...}}')
        self.json_in.setMaximumHeight(150)
        p_json.add(self.json_in)
        b_load = button("Load JSON file...")
        b_load.clicked.connect(self._load_json_file)
        b_md = button("Load Markdown archive...")
        b_md.clicked.connect(self._load_markdown)
        b_csv = button("Load CSV...")
        b_csv.clicked.connect(self._load_csv)
        b_import = button("IMPORT JSON", primary=True)
        b_import.clicked.connect(self._import_json)
        p_json.add(row(b_load, b_md, b_csv, b_import, None))
        p_json.add(label("The TruthScan research archive (Markdown) imports as methodological context, not a per-image "
                         "score. A fenced result block is flagged as an archive example.", "Muted", wrap=True))
        lay.addWidget(p_json)
        p_manual = Panel("Or enter the result manually")
        self.m_final = QLineEdit()
        self.m_final.setPlaceholderText("Final result / label, e.g. 'AI Generated' or 'Likely human'")
        self.m_conf = QLineEdit()
        self.m_conf.setPlaceholderText("Confidence, e.g. 97% or 0.97")
        self.m_step = QComboBox()
        self.m_step.addItems(["(not reported)", "1 = metadata only", "2 = metadata + OCR", "3 = metadata + OCR + ML"])
        b_enter = button("IMPORT MANUAL RESULT")
        b_enter.clicked.connect(self._import_manual)
        p_manual.add(row(label("Final result:", "Muted"), self.m_final, None))
        p_manual.add(row(label("Confidence:", "Muted"), self.m_conf, label("Detection step:", "Muted"), self.m_step, None))
        p_manual.add(row(b_enter, None))
        lay.addWidget(p_manual)
        p_hand = Panel("Optional browser hand-off (consent-gated, no upload by this app)")
        self.b_enable = button("ENABLE TRUTHSCAN BROWSER HAND-OFF", checkable=True)
        self.b_enable.clicked.connect(self._toggle_handoff)
        self.b_open = button("OPEN TRUTHSCAN IN BROWSER")
        self.b_open.clicked.connect(self._open_browser)
        p_hand.add(label("SynthProvenance opens truthscan.com in your browser and shows the file in Explorer. You "
                         "upload it yourself, under TruthScan's sign-in and terms, then import the result above. "
                         "Automated repeated submission / optimisation against the service is not provided.", "Muted",
                         wrap=True))
        p_hand.add(row(self.b_enable, self.b_open, None))
        lay.addWidget(p_hand)
        self.ext_kv = KVTable()
        self.ext_kv.setMinimumHeight(180)
        lay.addWidget(label("Imported external result", "PanelTitle"))
        lay.addWidget(self.ext_kv)
        self.tabs.addTab(w, "External Result")

    # ---- Local Analysis
    def _build_local(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("SynthProvenance runs its full local research pipeline and distils independent, descriptive "
                            "evidence. It does not emit an AI/human verdict from pixels.", "Muted", wrap=True))
        self.local_table = DataTable(["Dimension", "Family", "Direction", "Strength", "Observation", "Method"])
        self.local_table.setMinimumHeight(240)
        self.evidence_table = DataTable(["Evidence", "Family", "Representation", "Method", "Observation", "Validation"])
        self.evidence_table.setMinimumHeight(220)
        lay.addWidget(label("Evidence dimensions", "PanelTitle"))
        lay.addWidget(self.local_table)
        lay.addWidget(label("Evidence map (feature → fingerprint family)", "PanelTitle"))
        lay.addWidget(self.evidence_table)
        self.tabs.addTab(w, "Local Analysis")

    # ---- Agreement
    def _build_agreement(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.agree_kv = KVTable()
        self.agree_kv.setMinimumHeight(160)
        self.cmp_table = DataTable(["Dimension", "Family", "Local direction", "vs external", "Observation"])
        self.cmp_table.setMinimumHeight(260)
        lay.addWidget(label("Independent-evidence scorecard (no single truth score) & agreement", "LayerTitle"))
        lay.addWidget(self.agree_kv)
        lay.addWidget(self.cmp_table)
        self.scorecard_table = DataTable(["Evidence dimension", "Direction", "Strength", "Observation"])
        self.scorecard_table.setMinimumHeight(200)
        lay.addWidget(label("Independent Evidence Scorecard", "PanelTitle"))
        lay.addWidget(self.scorecard_table)
        self.tabs.addTab(w, "Agreement")

    # ---- Disagreement (flagship)
    def _build_disagreement(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.dis_title = label("", "LayerTitle")
        self.dis_text = label("", "Muted", wrap=True)
        self.dis_kv = KVTable()
        self.dis_kv.setMinimumHeight(220)
        lay.addWidget(self.dis_title)
        lay.addWidget(self.dis_text)
        lay.addWidget(self.dis_kv)
        lay.addWidget(banner("A disagreement is not proof that either system is wrong. Without ground truth (LEVEL >= 3) "
                             "neither can be called correct. This is the scientific heart of the lab: documented "
                             "detector disagreement under the tested condition.", info=True))
        self.tabs.addTab(w, "Disagreement")

    # ---- Heatmap
    def _build_heatmap(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Import a TruthScan heatmap and compare it with local maps (FFT / residual / reconstruction). "
                            "Overlap (IoU / correlation) measures where the maps agree spatially; overlap is not "
                            "correctness.", "Muted", wrap=True))
        self.heat_path = QLineEdit()
        self.heat_path.setPlaceholderText("Path to the TruthScan heatmap image (optional; set before running the study)")
        b_pick = button("Choose heatmap...")
        b_pick.clicked.connect(self._pick_heatmap)
        lay.addLayout(row(self.heat_path, b_pick, None))
        self.heat_table = DataTable(["Local map", "Pearson", "IoU", "Dice", "Region consistency", "Agreement"])
        self.heat_table.setMinimumHeight(240)
        lay.addWidget(self.heat_table)
        self.tabs.addTab(w, "Heatmap Analysis")

    # ---- Transformation study
    def _build_transformation(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Transformation / robustness study", "LayerTitle"))
        lay.addWidget(label("Stability of classifications under standard transformations is studied on a controlled "
                            "surrogate with known ground truth in the Fingerprint Research Lab (Robustness tab). It "
                            "measures how a known signal persists; it is not a search for transformations that defeat "
                            "a detector. Use it to answer: which signals are persistent, which are representation-"
                            "specific, and which claims survive replication.", "Muted", wrap=True))
        b_go = button("Open Fingerprint Research Lab → Robustness")
        b_go.clicked.connect(lambda: self.win.go("Fingerprint Research Lab"))
        b_bench = button("Generate labelled hard-case benchmark...")
        b_bench.clicked.connect(self._generate_hardcases)
        lay.addLayout(row(b_go, b_bench, None))
        lay.addWidget(label("Hard-case benchmark: locally generated, reproducible, known ground truth. The "
                            "'natural-like' control imitates camera capture and is NOT a real photograph.", "Muted",
                            wrap=True))
        self.tabs.addTab(w, "Transformation Study")

    # ---- Research questions
    def _build_questions(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("The ten research questions this instrument is built to investigate:", "LayerTitle"))
        t = DataTable(["#", "Research question"])
        t.set_data(["#", "Research question"], [[f"Q{i+1}", q] for i, q in enumerate(XD.RESEARCH_QUESTIONS)])
        t.setMinimumHeight(320)
        lay.addWidget(t)
        lay.addWidget(label("ONE DETECTOR IS AN OPINION.  MULTIPLE INDEPENDENT MEASUREMENTS CREATE EVIDENCE.\n"
                            "WE DO NOT GUESS. WE MEASURE. WE CHALLENGE. WE REPRODUCE. WE DOCUMENT.", "Muted", wrap=True))
        self.tabs.addTab(w, "Research Questions")

    # ---- Export
    def _build_export(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.runs = DataTable(RUN_COLUMNS)
        self.runs.setMinimumHeight(260)
        b_exp = button("EXPORT CROSS-DETECTOR REPORT (HTML / PDF / JSON / CSV)...", primary=True)
        b_exp.clicked.connect(self._export)
        b_dir = button("Open run folder")
        b_dir.clicked.connect(lambda: self._sel() and self.ctl.open_path(self.ctl.cross_lab.run_dir(self._sel())))
        lay.addWidget(label("Cross-detector studies (SPX-XD runs)", "PanelTitle"))
        lay.addLayout(row(b_exp, b_dir, None))
        lay.addWidget(self.runs)
        self.tabs.addTab(w, "Export")

    # ---- actions
    def _run_study(self) -> None:
        self.ctl.run_cross_detector(self.gt_level.currentIndex(), self.gt_dir.currentText(),
                                    self.heat_path.text().strip() or None)

    def _import_json(self) -> None:
        text = self.json_in.toPlainText().strip()
        if not text:
            self.ctl.error.emit("Import JSON", "Paste a JSON result first.")
            return
        try:
            blob = json.loads(text)
        except json.JSONDecodeError as exc:
            self.ctl.error.emit("Import JSON", f"Not valid JSON: {exc}")
            return
        self.ctl.import_external_result(blob=blob)

    def _load_json_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load TruthScan JSON result", "", "JSON (*.json);;All files (*)")
        if path:
            try:
                self.json_in.setPlainText(Path(path).read_text(encoding="utf-8"))
            except OSError as exc:
                self.ctl.error.emit("Load JSON", str(exc))

    def _load_markdown(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load TruthScan research archive (Markdown)", "",
                                              "Markdown (*.md *.markdown *.txt);;All files (*)")
        if path:
            try:
                self.ctl.import_external_result(markdown=Path(path).read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                self.ctl.error.emit("Load Markdown", str(exc))

    def _load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load external result CSV", "", "CSV (*.csv);;All files (*)")
        if path:
            try:
                self.ctl.import_external_result(csv=Path(path).read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                self.ctl.error.emit("Load CSV", str(exc))

    def _import_manual(self) -> None:
        step = self.m_step.currentIndex() or None
        self.ctl.import_external_result(fields={"final_result": self.m_final.text().strip(),
                                                "confidence": self.m_conf.text().strip(), "detection_step": step})

    def _toggle_handoff(self) -> None:
        if self.b_enable.isChecked():
            if self.win.quiet or QMessageBox.question(
                    self, "Enable TruthScan browser hand-off",
                    "SynthProvenance will NOT upload any image or call any API. It can open truthscan.com in your "
                    "browser so you can upload manually, under TruthScan's terms. Enable this for the session?"
            ) == QMessageBox.StandardButton.Yes:
                self.ctl.set_truthscan_mode(True, confirmed=True)
            else:
                self.b_enable.setChecked(False)
        else:
            self.ctl.set_truthscan_mode(False)

    def _open_browser(self) -> None:
        plan = None
        try:
            plan = self.ctl.xd_gate.plan(self.ctl.research_image()) if self.ctl.research_image() else None
        except Exception as exc:  # noqa: BLE001
            self.ctl.error.emit("TruthScan integration", str(exc))
            return
        if plan is None:
            self.ctl.error.emit("No image", "Open an image first.")
            return
        if self.win.quiet or QMessageBox.question(self, "Open TruthScan", plan.confirmation_text()) == \
                QMessageBox.StandardButton.Yes:
            self.ctl.truthscan_open(consent=True)

    def _pick_heatmap(self) -> None:
        from app.ui.main_window import IMAGE_FILTER
        path, _ = QFileDialog.getOpenFileName(self, "Choose TruthScan heatmap image", "", IMAGE_FILTER)
        if path:
            self.heat_path.setText(path)

    def _generate_hardcases(self) -> None:
        dest = QFileDialog.getExistingDirectory(self, "Choose a folder for the labelled benchmark")
        if dest:
            self.ctl.generate_hardcases(dest, n_each=2)

    def _sel(self) -> str:
        r = self.runs.currentRow()
        it = self.runs.item(r, 0) if r >= 0 else None
        return it.text() if it is not None else ""

    def _export(self) -> None:
        rid = self._sel() or (self.ctl.last_xd_run.run_id if self.ctl.last_xd_run else "")
        if not rid:
            self.ctl.error.emit("Export", "Run or select a cross-detector study first.")
            return
        dest = QFileDialog.getExistingDirectory(self, "Export cross-detector report to folder")
        if dest:
            self.ctl.export_cross_detector(rid, dest)

    # ---- refresh
    def refresh(self) -> None:
        ext = self.ctl.last_external
        if ext is not None:
            self.r_external.set(ext.direction, f"{ext.detector}: {ext.final_result}"[:60],
                                state="RESEARCH" if ext.direction != XD.UNKNOWN else "UNKNOWN")
            self.ext_kv.set_rows([("Detector", ext.detector), ("Source", ext.source),
                                  ("Final result", ext.final_result or "-"), ("Direction", ext.direction),
                                  ("Confidence", f"{ext.confidence:.0%}" if ext.confidence is not None else "-"),
                                  ("Detection step", ext.detection_step_text), ("Metadata stage", ext.metadata_state),
                                  ("OCR / watermark stage", ext.ocr_watermark_state), ("ML stage", ext.ml_state),
                                  ("Warnings", "; ".join(ext.warnings) or "none"),
                                  ("Heatmap", ext.heatmap_ref or "none")])
        else:
            self.r_external.set("NOT IMPORTED", "Import a TruthScan result", state="NOT RUN")
            self.ext_kv.set_rows([("External result", "none imported yet")])
        self.b_enable.setChecked(self.ctl.xd_gate.enabled)
        self.b_open.setEnabled(self.ctl.xd_gate.enabled)
        run = self.ctl.last_xd_run
        if run is not None:
            self._apply_run(run)
        else:
            self.r_outcome.set("NOT RUN", "Run a study", state="NOT RUN")
            self.r_local.set("-", "", state="UNKNOWN")
            self.r_gt.set("LEVEL 0", "Unknown origin", state="UNKNOWN")
        self.runs.set_data(RUN_COLUMNS, [[r["run_id"], r["detector"], r["outcome"], f"LEVEL {r['ground_truth_level']}",
                                          r["input"], r["created"][:19]] for r in self.ctl.cross_lab.list_runs()])

    def _apply_run(self, run) -> None:
        cmp = run.comparison or {}
        local = run.local_evidence or {}
        self.r_outcome.set(run.outcome, run.run_id,
                           state={"AGREEMENT": "COMPLETE", "DISAGREEMENT": "WARNING", "PARTIAL AGREEMENT": "RESEARCH",
                                  "INSUFFICIENT EVIDENCE": "UNKNOWN"}.get(run.outcome, "RESEARCH"))
        self.r_local.set(cmp.get("local_direction", "DESCRIPTIVE"), f"{len(local.get('dimensions') or [])} dimensions")
        self.r_gt.set(f"LEVEL {run.ground_truth_level}", XD.GROUND_TRUTH_LEVELS.get(run.ground_truth_level, "")[:40],
                      state="RESEARCH" if run.ground_truth_level >= 3 else "UNKNOWN")
        self.ov_statement.setText(cmp.get("statement", run.detail))
        self.local_table.set_data(["Dimension", "Family", "Direction", "Strength", "Observation", "Method"],
                                  [[d.get("name"), d.get("family"), d.get("direction"), d.get("strength"),
                                    d.get("observation"), d.get("method")] for d in (local.get("dimensions") or [])])
        self.evidence_table.set_data(["Evidence", "Family", "Representation", "Method", "Observation", "Validation"],
                                     [[e.get("evidence_id"), e.get("family"), e.get("representation"), e.get("method"),
                                       e.get("observation"), e.get("validation_status")]
                                      for e in (local.get("evidence_items") or [])])
        self.cmp_table.set_data(["Dimension", "Family", "Local direction", "vs external", "Observation"],
                                [[r.get("dimension"), r.get("family"), r.get("local_direction"), r.get("vs_external"),
                                  r.get("observation")] for r in (cmp.get("dimension_rows") or [])])
        self.agree_kv.set_rows([("Outcome", run.outcome), ("Consistent dimensions",
                                                           ", ".join(cmp.get("agreements") or []) or "none"),
                                ("External vs ground truth", cmp.get("external_vs_truth", "-")),
                                ("Local vs ground truth", cmp.get("local_vs_truth", "-"))])
        sc = run.scorecard or {}
        self.scorecard_table.set_data(["Evidence dimension", "Direction", "Strength", "Observation"],
                                      [[k, v.get("direction"), v.get("strength"), v.get("observation")]
                                       for k, v in (sc.get("dimensions") or {}).items()])
        is_dis = run.outcome in ("DISAGREEMENT", "INSUFFICIENT EVIDENCE")
        self.dis_title.setText("DETECTOR DISAGREEMENT" if run.outcome == "DISAGREEMENT" else
                               "INDEPENDENT EVIDENCE INCOMPLETE" if run.outcome == "INSUFFICIENT EVIDENCE" else
                               "EVIDENCE CONSISTENT / PARTIAL")
        self.dis_text.setText(cmp.get("statement", run.detail))
        ext = run.external or {}
        self.dis_kv.set_rows([("External detector", f"{ext.get('detector','-')}: {ext.get('final_result','-')}"),
                              ("External confidence", f"{float(ext['confidence']):.0%}" if ext.get("confidence")
                               is not None else "-"),
                              ("Inconsistent dimensions", ", ".join(cmp.get("disagreements") or []) or "none"),
                              ("No independent evidence", ", ".join(cmp.get("unknowns") or []) or "none"),
                              ("External vs ground truth", cmp.get("external_vs_truth", "-")),
                              ("Status", "INDEPENDENT EVIDENCE INCOMPLETE" if is_dis and run.outcome ==
                               "INSUFFICIENT EVIDENCE" else run.outcome)])
        heat = run.heatmap or {}
        self.heat_table.set_data(["Local map", "Pearson", "IoU", "Dice", "Region consistency", "Agreement"],
                                 [[k, fmt_num(v.get("pearson"), 3), fmt_num(v.get("iou"), 3), fmt_num(v.get("dice"), 3),
                                   fmt_num(v.get("region_consistency"), 3), v.get("agreement")]
                                  for k, v in (heat.get("by_map") or {}).items() if "iou" in v])
