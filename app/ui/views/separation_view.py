from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout

from app.models.provenance import LAYER_KIND
from app.ui.theme import state_color
from app.ui.views.base import View, fill_conditions, row
from app.ui.widgets.common import DataTable, Panel, banner, label


class SignalSeparationView(View):
    title = "Signal Separation"
    subtitle = ("PROVENANCE SEPARATION EXPERIMENT. Seven layers are measured independently: C2PA, SynthID, ordinary "
                "metadata, pixels, encoding, file structure and external classification.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        self.root.addWidget(banner("EXPERIMENTAL OBSERVATION ONLY. Removing metadata is never assumed to remove embedded "
                                   "signals. No platform classification is predicted or guaranteed."))
        self.cond = QComboBox()
        self.cond.currentIndexChanged.connect(self._fill)
        self.root.addLayout(row(label("Condition:"), self.cond, None))
        flow = Panel("BEFORE  \u2192  CONTROLLED CONDITION  \u2192  AFTER")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(6)
        flow.add(self.grid)
        self.cond_label = label("", "Muted", wrap=True)
        flow.add(self.cond_label)
        self.root.addWidget(flow)
        p = Panel("Layer results: observation / method / condition / limitation")
        self.table = DataTable(["Layer", "Kind", "Before", "After", "State", "Observation", "Method", "Limitation"])
        self.table.setMinimumHeight(260)
        self.table.setWordWrap(True)
        p.add(self.table)
        self.root.addWidget(p, 1)

    def refresh(self) -> None:
        fill_conditions(self.cond, self.ctl, include_original=False)
        self._fill()

    def _fill(self) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        t = self.ctl.record(self.cond.currentData() or "")
        if t is None:
            self.cond_label.setText("No completed transformation yet. Run one in the Transformation Lab, Format Conversion "
                                    "or C2PA Provenance views.")
            self.table.setRowCount(0)
            return
        for c, h in enumerate(("LAYER", "BEFORE", "AFTER", "STATE")):
            self.grid.addWidget(label(h, "PanelTitle"), 0, c)
        for r, lay in enumerate(t.layers, 1):
            name = label(f"{lay['layer']}  \u00b7  {LAYER_KIND.get(lay['layer'], '')}")
            before, after = label(str(lay["before"]), mono=True), label(str(lay["after"]), mono=True)
            state = label(lay["state"], mono=True)
            state.setStyleSheet(f"color: {state_color(lay['state'])}; font-weight: 600;")
            for c, w in enumerate((name, before, after, state)):
                self.grid.addWidget(w, r, c)
        self.cond_label.setText(f"Condition {t.transformation_id}: {t.label}  |  parameters {t.parameters}  |  "
                                f"source {t.source_condition}  |  {t.timestamp}")
        self.table.set_data(["Layer", "Kind", "Before", "After", "State", "Observation", "Method", "Limitation"],
                            [[x["layer"], x["kind"], x["before"], x["after"], x["state"], x["observation"], x["method"],
                              x["limitation"]] for x in t.layers])
        self.table.resizeRowsToContents()
