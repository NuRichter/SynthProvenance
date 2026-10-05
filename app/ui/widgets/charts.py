"""Histogram plot, provenance graph and drag-and-drop zone."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui.theme import C, state_color

CHANNEL_COLORS = {"R": "#E0605A", "G": "#46B37B", "B": "#3D7FD9", "L": "#D5DEE7", "Y": "#4CC3D9"}


class HistogramWidget(QWidget):
    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.title = title
        self.series: dict[str, list] = {}
        self.setMinimumHeight(150)

    def set_series(self, series: dict[str, list]) -> None:
        self.series = {k: list(v) for k, v in (series or {}).items() if v}
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(8, 20, -8, -10)
        p.fillRect(self.rect(), QColor(C["field"]))
        p.setPen(QPen(QColor(C["line"]), 1))
        p.drawRect(r)
        p.setPen(QColor(C["muted"]))
        p.drawText(10, 14, self.title)
        if not self.series:
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "no data")
            return
        peak = max(max(v) for v in self.series.values()) or 1
        for name, vals in self.series.items():
            n = len(vals)
            poly = QPolygonF([QPointF(r.left() + r.width() * i / max(n - 1, 1), r.bottom() - r.height() * v / peak)
                              for i, v in enumerate(vals)])
            p.setPen(QPen(QColor(CHANNEL_COLORS.get(name, C["cyan"])), 1.2))
            p.drawPolyline(poly)


class ProvenanceGraph(QWidget):
    nodeSelected = Signal(int)

    BOX_H, GAP = 58, 22

    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[dict] = []
        self.selected = -1
        self.setMinimumWidth(320)

    def set_nodes(self, nodes: list[dict]) -> None:
        self.nodes = nodes or []
        self.selected = -1 if not self.nodes else min(max(self.selected, 0), len(self.nodes) - 1)
        self.setMinimumHeight(len(self.nodes) * (self.BOX_H + self.GAP) + 20)
        self.update()

    def _rect(self, i: int) -> QRectF:
        return QRectF(20, 10 + i * (self.BOX_H + self.GAP), max(self.width() - 40, 200), self.BOX_H)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        for i in range(len(self.nodes)):
            if self._rect(i).contains(e.position()):
                self.selected = i
                self.nodeSelected.emit(i)
                self.update()
                return

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(self.font())
        for i, n in enumerate(self.nodes):
            r = self._rect(i)
            col = QColor(state_color(n.get("state", "")))
            p.setPen(QPen(QColor(C["cyan"]) if i == self.selected else QColor(C["line"]), 1.5 if i == self.selected else 1))
            p.setBrush(QColor(C["raised"] if i == self.selected else C["panel"]))
            p.drawRoundedRect(r, 3, 3)
            p.fillRect(QRectF(r.left(), r.top(), 4, r.height()), col)
            f.setBold(True)
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.setPen(QColor(C["text"]))
            p.drawText(r.adjusted(14, 6, -10, -30), Qt.AlignmentFlag.AlignLeft, n.get("stage", ""))
            p.setPen(col)
            p.drawText(r.adjusted(14, 6, -10, -30), Qt.AlignmentFlag.AlignRight, n.get("state", ""))
            f.setBold(False)
            f.setPointSizeF(8)
            p.setFont(f)
            p.setPen(QColor(C["muted"]))
            sub = n.get("operation") or (n.get("details") or [""])[0]
            p.drawText(r.adjusted(14, 30, -10, -4), Qt.AlignmentFlag.AlignLeft, str(sub)[:110])
            if i < len(self.nodes) - 1:
                x = r.center().x()
                p.setPen(QPen(QColor(C["line"]), 1.5))
                p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + self.GAP - 4))
                p.setBrush(QColor(C["line"]))
                p.drawPolygon(QPolygonF([QPointF(x - 4, r.bottom() + self.GAP - 8), QPointF(x + 4, r.bottom() + self.GAP - 8),
                                         QPointF(x, r.bottom() + self.GAP - 2)]))


class DropZone(QFrame):
    fileDropped = Signal(str)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(170)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style(False)
        lay = QVBoxLayout(self)
        t = QLabel("Drag & Drop Image")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(f"font-size: 15pt; color: {C['text']}; background: transparent;")
        s = QLabel("JPEG / PNG / WEBP / TIFF / BMP / GIF  |  any practical resolution  |  processed locally")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet(f"color: {C['muted']}; background: transparent;")
        lay.addStretch(1)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addStretch(1)

    def _style(self, active: bool) -> None:
        self.setStyleSheet(f"DropZone {{ border: 1px dashed {C['cyan'] if active else C['line']}; border-radius: 4px; "
                           f"background: {'#10252C' if active else C['field']}; }}")

    def mousePressEvent(self, _e) -> None:  # noqa: N802
        self.clicked.emit()

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._style(True)

    def dragLeaveEvent(self, _e) -> None:  # noqa: N802
        self._style(False)

    def dropEvent(self, e) -> None:  # noqa: N802
        self._style(False)
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.fileDropped.emit(url.toLocalFile())
                break


class RocWidget(QWidget):
    """ROC curve (FPR on x, TPR on y) with the chance diagonal."""

    def __init__(self) -> None:
        super().__init__()
        self.points: list = []
        self.setMinimumSize(220, 220)

    def set_points(self, points: list) -> None:
        self.points = [(float(p[0]), float(p[1])) for p in (points or [])]
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C["field"]))
        side = min(self.width(), self.height()) - 40
        r = QRectF(30, 10, side, side)
        p.setPen(QPen(QColor(C["line"]), 1))
        p.drawRect(r)
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(r.left(), r.bottom() + 4, r.width(), 16), Qt.AlignmentFlag.AlignCenter, "FPR")
        p.drawText(QRectF(0, r.top(), 28, r.height()), Qt.AlignmentFlag.AlignCenter, "TPR")
        if not self.points:
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "no benchmark")
            return
        pts = [QPointF(r.left() + x * r.width(), r.bottom() - y * r.height()) for x, y in self.points]
        pts.append(QPointF(r.right(), r.top()))
        p.setPen(QPen(QColor(C["cyan"]), 2))
        p.drawPolyline(QPolygonF(pts))
