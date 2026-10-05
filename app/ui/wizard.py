"""Guided Research Wizard (STEP X of 7).

A thin guide over the real controller actions: it does not re-implement anything, it
drives the existing pipeline (open image -> baseline -> method -> parameters -> run ->
verification -> report) and navigates to the view where each result appears.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from app.core.research_assistant import GOALS
from app.research.methods import MethodRegistry
from app.research.surrogate import AVAILABLE_FAMILIES
from app.ui.widgets.common import button, label

STEPS = ["Input", "Baseline", "Research Target", "Method", "Experiment", "Validation", "Report"]


class ResearchWizard(QDialog):
    def __init__(self, ctl, win) -> None:
        super().__init__(win)
        self.ctl, self.win = ctl, win
        self.registry = MethodRegistry()
        self.setWindowTitle("SynthProvenance Research Wizard")
        self.setMinimumSize(640, 440)
        root = QVBoxLayout(self)
        self.heading = label("", "AppTitle")
        self.step_label = label("", "Muted")
        root.addWidget(self.heading)
        root.addWidget(self.step_label)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self._build_steps()
        nav = QHBoxLayout()
        self.b_back = button("Back")
        self.b_back.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        self.b_next = button("Next", primary=True)
        self.b_next.clicked.connect(self._next)
        nav.addWidget(self.b_back)
        nav.addStretch(1)
        nav.addWidget(self.b_next)
        root.addLayout(nav)
        self._go(0)

    def _page(self, *widgets) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        for x in widgets:
            (lay.addWidget if isinstance(x, QWidget) else lay.addLayout)(x)
        lay.addStretch(1)
        return w

    def _build_steps(self) -> None:
        # 1 input
        b_open = button("Open image...")
        b_open.clicked.connect(self._open)
        b_demo = button("Use demo fixture")
        b_demo.clicked.connect(self.ctl.open_demo_fixture)
        self.input_state = label("No image loaded.", "Muted", wrap=True)
        self.stack.addWidget(self._page(label("Drop in an image to study. The original is always preserved; experiments "
                                              "run on copies.", "Muted", wrap=True),
                                        self._row(b_open, b_demo), self.input_state))
        # 2 baseline
        self.baseline_state = label("", "Muted", wrap=True)
        self.stack.addWidget(self._page(label("Start the experiment to compute the forensic baseline (hashes, C2PA, "
                                              "metadata, statistics).", "Muted", wrap=True), self.baseline_state))
        # 3 research target
        self.goal = QComboBox()
        self.goal.addItems(list(GOALS))
        self.goal.currentIndexChanged.connect(self._goal_changed)
        self.goal_note = label("", "Muted", wrap=True)
        self.stack.addWidget(self._page(label("Pick a research target. The assistant suggests a method; you can change "
                                              "it in the next step.", "Muted", wrap=True), self.goal, self.goal_note))
        # 4 method (+ surrogate parameters folded in)
        self.method = QComboBox()
        for m in self.registry.ready():
            self.method.addItem(f"{m.method_id}  {m.name}", m.method_id)
        self.method_card = label("", "Muted", wrap=True)
        self.method.currentIndexChanged.connect(self._card)
        self.family = QComboBox()
        self.family.addItems(list(AVAILABLE_FAMILIES))
        self.strength = QDoubleSpinBox()
        self.strength.setRange(0.5, 12.0)
        self.strength.setValue(3.0)
        self.key = QSpinBox()
        self.key.setRange(1, 2**31 - 1)
        self.key.setValue(20261005)
        self.stack.addWidget(self._page(label("Choose a READY fingerprint method. For controlled-surrogate / hypothesis "
                                              "methods, set the ground-truth signal below (descriptive methods ignore "
                                              "it).", "Muted", wrap=True), self.method, self.method_card,
                                        self._labeled("Surrogate family", self.family),
                                        self._labeled("Strength (8-bit RMS)", self.strength),
                                        self._labeled("Key", self.key)))
        # 5 experiment
        self.run_state = label("", "Muted", wrap=True)
        self.stack.addWidget(self._page(label("Run the selected method. The run is recorded with a reproducible "
                                              "SPX-FP id.", "Muted", wrap=True), self.run_state))
        # 6 validation
        self.verify_state = label("", "Muted", wrap=True)
        self.stack.addWidget(self._page(label("Verification: the original file is re-hashed and reported as unchanged; "
                                              "fidelity and ground-truth metrics are shown for the run.", "Muted",
                                              wrap=True), self.verify_state))
        # 7 report
        b_lab = button("Open Fingerprint Research Lab")
        b_lab.clicked.connect(lambda: (self.win.go("Fingerprint Research Lab"), self.accept()))
        b_exp = button("Export last run for paper...", primary=True)
        b_exp.clicked.connect(self._export)
        self.stack.addWidget(self._page(label("Review the run in the lab and export a paper-ready bundle (CSV / JSON / "
                                              "PDF / PNG / ZIP).", "Muted", wrap=True), self._row(b_lab, b_exp)))

    def _row(self, *w):
        h = QHBoxLayout()
        for x in w:
            h.addWidget(x)
        h.addStretch(1)
        return h

    def _labeled(self, text, w):
        h = QHBoxLayout()
        h.addWidget(label(text, "Muted"))
        h.addWidget(w)
        h.addStretch(1)
        return h

    def _card(self) -> None:
        mid = self.method.currentData()
        if mid:
            m = self.registry.get(mid)
            self.method_card.setText(f"{m.category} - {m.maturity}\n{m.scientific_basis}")

    def _open(self) -> None:
        from app.ui.main_window import IMAGE_FILTER
        path, _ = QFileDialog.getOpenFileName(self, "Open image", "", IMAGE_FILTER)
        if path:
            self.ctl.open_image(path)

    def _surrogate(self) -> dict | None:
        mid = self.method.currentData()
        if not mid:
            return None
        m = self.registry.get(mid)
        if m.requires_ground_truth or m.capability.startswith(("sep:", "hyp:")) or m.capability in ("robustness",
                                                                                                    "persistence_map"):
            return {"family": self.family.currentText(), "strength": self.strength.value(), "key": self.key.value()}
        return None

    def _goal_changed(self) -> None:
        from app.core.research_assistant import GOALS as _G
        spec = _G.get(self.goal.currentText(), {})
        pref = (spec.get("methods") or ["Method 13"])[0]
        i = self.method.findData(pref)
        if i >= 0:
            self.method.setCurrentIndex(i)
        self.goal_note.setText(spec.get("why", ""))

    def _next(self) -> None:
        i = self.stack.currentIndex()
        if i == 1 and self.ctl.experiment is None and self.ctl.source is not None:
            self.ctl.start_experiment()
        elif i == 4:  # Experiment step: run the selected method
            mid = self.method.currentData()
            if mid:
                self.ctl.run_fingerprint_method(mid, surrogate=self._surrogate())
        if i < len(STEPS) - 1:
            self._go(i + 1)

    def _export(self) -> None:
        run = self.ctl.last_fp_run
        if run is None:
            self.ctl.error.emit("Export", "Run a method first.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export for paper", f"{run.run_id}_paper.zip", "ZIP (*.zip)")
        if dest:
            self.ctl.export_fingerprint_paper(run.run_id, dest)

    def _go(self, i: int) -> None:
        i = max(0, min(i, len(STEPS) - 1))
        self.stack.setCurrentIndex(i)
        self.heading.setText(STEPS[i])
        self.step_label.setText(f"Step {i + 1} of {len(STEPS)}")
        self.b_back.setEnabled(i > 0)
        self.b_next.setText("Finish" if i == len(STEPS) - 1 else "Next")
        self._refresh_state()

    def _refresh_state(self) -> None:
        src = self.ctl.source
        self.input_state.setText(f"Loaded: {src.path.name}" if src else "No image loaded.")
        exp = self.ctl.experiment
        self.baseline_state.setText(f"Experiment {exp.experiment_id} ready." if exp else
                                    "No experiment yet - press Next to start one.")
        self._card()
        run = self.ctl.last_fp_run
        if run is not None:
            self.run_state.setText(f"{run.run_id}: {run.method_id} {run.status} ({run.runtime_s:.2f}s)")
            res = run.result or {}
            lines = [f"Original unchanged: {run.original_unchanged}"]
            for k, v in list((res.get("readouts") or {}).items())[:6]:
                lines.append(f"{k}: {v}")
            self.verify_state.setText("\n".join(lines))
        else:
            self.run_state.setText("No run yet.")
            self.verify_state.setText("No run to verify yet.")
