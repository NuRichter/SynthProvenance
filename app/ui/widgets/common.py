"""Shared widgets: panels, readouts, badges, tables, parameter forms."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.ui.theme import C, mono_font, state_color


def button(text: str, primary: bool = False, tooltip: str = "", checkable: bool = False) -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setObjectName("Primary")
    if tooltip:
        b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def label(text: str = "", name: str = "", wrap: bool = False, mono: bool = False, selectable: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    if mono:
        lab.setFont(mono_font())
    if selectable:
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def banner(text: str, info: bool = False) -> QLabel:
    lab = label(text, "InfoBanner" if info else "Banner", wrap=True)
    return lab


class Panel(QFrame):
    def __init__(self, title: str = "", parent=None, horizontal: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)
        if title:
            outer.addWidget(label(title.upper(), "PanelTitle"))
        self.body = QHBoxLayout() if horizontal else QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)

    def add(self, w, stretch: int = 0):
        (self.body.addWidget if isinstance(w, QWidget) else self.body.addLayout)(w, stretch)
        return w


class Readout(QFrame):
    """Instrument-style readout: caption, large value, detail line."""

    def __init__(self, caption: str, value: str = "-", detail: str = "") -> None:
        super().__init__()
        self.setObjectName("Readout")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        self.caption = label(caption.upper(), "ReadoutCaption")
        self.value = label(value, "ReadoutValue", selectable=True)
        self.value.setFont(mono_font(12))
        self.detail = label(detail, "ReadoutDetail", wrap=True)
        for w in (self.caption, self.value, self.detail):
            lay.addWidget(w)

    def set(self, value: str, detail: str = "", state: str | None = None) -> None:
        self.value.setText(str(value))
        self.detail.setText(str(detail))
        color = state_color(state if state is not None else value)
        self.value.setStyleSheet(f"color: {color};")
        self.setStyleSheet(f"QFrame#Readout {{ border-left: 3px solid {color}; }}")


class Badge(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setObjectName("Badge")
        self.set_state(text)

    def set_state(self, text: str, tooltip: str = "") -> None:
        self.setText(text)
        col = state_color(text)
        self.setStyleSheet(f"QLabel#Badge {{ color: {col}; border-color: {col}; }}")
        self.setToolTip(tooltip)


class DataTable(QTableWidget):
    """Read-only table; cells whose text is a known state are coloured. Double-click copies."""

    def __init__(self, columns: list[str] | None = None, stretch_last: bool = True, mono_cols: tuple = ()) -> None:
        super().__init__()
        self.mono_cols = set(mono_cols)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(stretch_last)
        self.setWordWrap(False)
        self.cellDoubleClicked.connect(self._copy)
        if columns:
            self.set_data(columns, [])

    def _copy(self, r: int, c: int) -> None:
        it = self.item(r, c)
        if it is not None:
            QGuiApplication.clipboard().setText(it.text())

    def set_data(self, columns: list[str], rows: list, tooltips: list | None = None) -> None:
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                text = "-" if val is None else str(val)
                it = QTableWidgetItem(text)
                col = state_color(text)
                if col != C["text"]:
                    it.setForeground(QColor(col))
                if c in self.mono_cols:
                    it.setFont(mono_font(8.5))
                tip = tooltips[r][c] if tooltips and r < len(tooltips) and c < len(tooltips[r]) else text
                it.setToolTip(tip if len(tip) < 2000 else tip[:2000] + "...")
                self.setItem(r, c, it)
        self.resizeColumnsToContents()
        hh = self.horizontalHeader()
        for c in range(self.columnCount()):
            if self.columnWidth(c) > 420:
                self.setColumnWidth(c, 420)
        if self.columnCount():
            hh.setSectionResizeMode(self.columnCount() - 1, QHeaderView.ResizeMode.Stretch if hh.stretchLastSection()
                                    else QHeaderView.ResizeMode.Interactive)


class KVTable(DataTable):
    def __init__(self) -> None:
        super().__init__(["Property", "Value"], mono_cols=(1,))
        self.horizontalHeader().setVisible(False)

    def set_rows(self, rows: list) -> None:
        self.set_data(["Property", "Value"], [[k, v] for k, v in rows])
        self.setColumnWidth(0, min(max(self.columnWidth(0), 160), 260))


class ParamForm(QWidget):
    """Builds a form from transform_engine.ParamSpec definitions."""

    changed = Signal()

    def __init__(self, specs: list, parent=None) -> None:
        super().__init__(parent)
        self.specs = specs
        self.widgets: dict[str, QWidget] = {}
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        for p in specs:
            if p.kind == "int":
                w = QSpinBox()
                w.setRange(int(p.minimum if p.minimum is not None else -10**9), int(p.maximum if p.maximum is not None else 10**9))
                w.setValue(int(p.default))
                w.valueChanged.connect(self.changed)
            elif p.kind == "float":
                w = QDoubleSpinBox()
                w.setDecimals(3)
                w.setRange(float(p.minimum if p.minimum is not None else -1e9), float(p.maximum if p.maximum is not None else 1e9))
                w.setSingleStep(0.05 if (p.maximum or 10) <= 10 else 1.0)
                w.setValue(float(p.default))
                w.valueChanged.connect(self.changed)
            elif p.kind == "choice":
                w = QComboBox()
                w.addItems(list(p.choices))
                w.setCurrentText(str(p.default))
                w.currentTextChanged.connect(self.changed)
            elif p.kind == "bool":
                w = QCheckBox()
                w.setChecked(bool(p.default))
                w.toggled.connect(self.changed)
            else:
                w = QLineEdit(str(p.default))
                w.textChanged.connect(self.changed)
            if p.help:
                w.setToolTip(p.help)
            self.widgets[p.name] = w
            form.addRow(p.label, w)

    def values(self) -> dict:
        out = {}
        for p in self.specs:
            w = self.widgets[p.name]
            if isinstance(w, QSpinBox):
                out[p.name] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                out[p.name] = w.value()
            elif isinstance(w, QComboBox):
                out[p.name] = w.currentText()
            elif isinstance(w, QCheckBox):
                out[p.name] = w.isChecked()
            else:
                out[p.name] = w.text()
        return out


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {C['line']};")
    return f


def fmt_num(v, nd: int = 4) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)
