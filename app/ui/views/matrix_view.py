from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from app.services.transformation_service import MATRIX_COLUMNS, experiment_matrix
from app.ui.theme import state_color
from app.ui.views.base import View, row
from app.ui.widgets.common import button, label

LEGEND = ("\u2713 retained / identical to ORIGINAL   \u2715 lost   ALTERED present but changed   ? undetermined "
          "(e.g. SynthID NOT DETECTED after a transformation is not proof of removal)   N/A absent in ORIGINAL   "
          "UNAVAILABLE no local measurement engine   \u2014 not run")


class MatrixView(View):
    title = "Experiment Matrix"
    subtitle = "Latest completed run per condition. Hover a cell for the measured observation behind the symbol."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        b = button("Run full matrix battery", primary=True)
        b.clicked.connect(lambda: ctl.run_matrix())
        self.root.addLayout(row(b, label("Uses the default sanitization profile from Settings.", "Muted"), None))
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.root.addWidget(self.table, 1)
        self.root.addWidget(label(LEGEND, "Muted", wrap=True))

    def refresh(self) -> None:
        exp = self.ctl.experiment
        rows = experiment_matrix(exp) if exp else []
        cols = ["Run"] + MATRIX_COLUMNS
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(rows))
        self.table.setVerticalHeaderLabels([r["row"] for r in rows])
        f = QFont(self.font())
        f.setPointSizeF(12)
        f.setBold(True)
        for i, r in enumerate(rows):
            it = QTableWidgetItem(r["tid"] or "\u2014")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, it)
            for j, c in enumerate(MATRIX_COLUMNS, 1):
                sym, tip = r["cells"][c]
                it = QTableWidgetItem(sym)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setForeground(QColor(state_color(sym)))
                it.setFont(f)
                it.setToolTip(tip)
                self.table.setItem(i, j, it)
