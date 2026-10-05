"""Base class for navigation views (lazy refresh when visible)."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from app.ui.widgets.common import label
from app.utils.logging import get_logger

_log = get_logger("ui")
REFRESH_ERRORS: list[str] = []


class View(QWidget):
    title = ""
    subtitle = ""

    def __init__(self, ctl, win) -> None:
        super().__init__()
        self.ctl, self.win = ctl, win
        self._dirty = True
        for sig in (ctl.sourceChanged, ctl.experimentChanged, ctl.recordsChanged, ctl.statisticsChanged, ctl.toolsChanged,
                    ctl.researchChanged, ctl.fingerprintChanged):
            sig.connect(self._mark)
        ctl.selectionChanged.connect(lambda _t: self._mark())
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 16, 20, 16)
        self.root.setSpacing(12)
        if self.title:
            head = QVBoxLayout()
            head.setSpacing(2)
            head.addWidget(label(self.title, "AppTitle"))
            if self.subtitle:
                head.addWidget(label(self.subtitle, "Muted", wrap=True))
            self.root.addLayout(head)

    def _mark(self) -> None:
        self._dirty = True
        if self.isVisible():
            self._do_refresh()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if self._dirty:
            self._do_refresh()

    def _do_refresh(self) -> None:
        self._dirty = False
        try:
            self.refresh()
        except Exception:  # noqa: BLE001 - a view refresh must never take the window down
            import traceback

            REFRESH_ERRORS.append(f"{type(self).__name__}: {traceback.format_exc()[-800:]}")
            _log.exception("View refresh failed: %s", type(self).__name__)

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass


def fill_conditions(combo: QComboBox, ctl, include_original: bool = True, only_ops: tuple = (), keep: str | None = None) -> None:
    current = keep if keep is not None else combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if include_original:
        combo.addItem("ORIGINAL", "ORIGINAL")
    for t in ctl.completed():
        if only_ops and t.operation not in only_ops:
            continue
        combo.addItem(f"{t.transformation_id}  {t.label}", t.transformation_id)
    idx = combo.findData(current) if current else -1
    if idx < 0 and ctl.selected_tid:
        idx = combo.findData(ctl.selected_tid)
    combo.setCurrentIndex(idx if idx >= 0 else combo.count() - 1)
    combo.blockSignals(False)


def row(*widgets, stretch_last: bool = False) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setSpacing(8)
    for w in widgets:
        if w is None:
            h.addStretch(1)
        else:
            h.addWidget(w)
    if stretch_last:
        h.addStretch(1)
    return h
