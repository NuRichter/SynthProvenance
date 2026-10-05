"""Easy Mode building blocks: step indicator, drop zone, summary cards, phase timeline."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from app.i18n import tr
from app.ui.easy.style import E
from app.utils.validation import SUPPORTED_EXTENSIONS

STEP_KEYS = ("easy.step1", "easy.step2", "easy.step3")


def elabel(text: str = "", name: str = "", wrap: bool = False, align=None, selectable: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    if align is not None:
        lab.setAlignment(align)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def amp(text: str) -> str:
    """Qt treats a single '&' in button / check-box text as a keyboard mnemonic; show it literally instead."""
    return str(text).replace("&", "&&")


class EasyButton(QPushButton):
    """A button whose label is shown verbatim (e.g. 'SAVE & RESTART') and announced under the same name."""

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        super().setText(amp(text))
        self.setAccessibleName(str(text))

    def label(self) -> str:
        return super().text().replace("&&", "&")


def ebutton(text: str, kind: str = "", accessible: str = "") -> QPushButton:
    """kind: '' (secondary), 'primary', 'link', 'header'."""
    b = EasyButton()
    b.setText(text)
    b.setObjectName({"primary": "EasyPrimary", "link": "EasyLink", "header": "HeaderButton"}.get(kind, ""))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if accessible:
        b.setAccessibleName(accessible)
    if kind == "primary":
        b.setMinimumHeight(60)
    elif kind != "link":
        b.setMinimumHeight(48)
    return b


def centered(widget: QWidget, max_width: int = 820) -> QWidget:
    """Put ``widget`` in a centred column of at most ``max_width`` px (lots of whitespace on wide windows)."""
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(24, 0, 24, 0)
    lay.addStretch(1)
    widget.setMaximumWidth(max_width)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lay.addWidget(widget, 100)
    lay.addStretch(1)
    return host


class StepIndicator(QWidget):
    """Always exactly three steps: 01 PILIH, 02 RUN, 03 OUTPUT (active / complete / pending)."""

    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(10)
        lay.addStretch(1)
        self.circles: list[QLabel] = []
        self.names: list[QLabel] = []
        self.items: list[QWidget] = []
        for i in range(3):
            item = QWidget()
            il = QHBoxLayout(item)
            il.setContentsMargins(0, 0, 0, 0)
            il.setSpacing(8)
            c = QLabel()
            c.setFixedSize(40, 40)
            c.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n = QLabel()
            il.addWidget(c)
            il.addWidget(n)
            self.circles.append(c)
            self.names.append(n)
            self.items.append(item)
            lay.addWidget(item)
            if i < 2:
                line = QFrame()
                line.setFixedSize(56, 2)
                line.setStyleSheet(f"background: {E['line']};")
                lay.addWidget(line)
        lay.addStretch(1)
        self.current = 0
        self.set_step(0)

    def state(self, i: int) -> str:
        return "complete" if i < self.current else ("active" if i == self.current else "pending")

    def set_step(self, current: int) -> None:
        self.current = current
        for i in range(3):
            st = self.state(i)
            c, n = self.circles[i], self.names[i]
            if st == "complete":
                c.setText("✓")
                c.setStyleSheet(f"background: {E['ok']}; color: #FFFFFF; border-radius: 20px; font-weight: 700; "
                                "font-size: 14pt;")
                n.setStyleSheet(f"color: {E['text']}; font-weight: 600; font-size: 12pt;")
            elif st == "active":
                c.setText(f"{i + 1:02d}")
                c.setStyleSheet(f"background: {E['accent']}; color: #FFFFFF; border-radius: 20px; font-weight: 700; "
                                "font-size: 12pt;")
                n.setStyleSheet(f"color: {E['text']}; font-weight: 800; font-size: 12pt; text-decoration: underline;")
            else:
                c.setText(f"{i + 1:02d}")
                c.setStyleSheet(f"background: {E['surface']}; color: {E['muted']}; border: 2px solid {E['pending']}; "
                                "border-radius: 20px; font-weight: 600; font-size: 12pt;")
                n.setStyleSheet(f"color: {E['muted']}; font-weight: 500; font-size: 12pt;")
            n.setText(tr(STEP_KEYS[i]))
            desc = f"{tr('easy.step_of', n=i + 1)}: {tr(STEP_KEYS[i])} - {tr('easy.state_' + st)}"
            self.items[i].setAccessibleName(desc)
            self.items[i].setToolTip(desc)
            c.setAccessibleName(desc)


class DropZone(QFrame):
    """Large drop target. Click, Enter or Space opens the file chooser; dropping a file selects it."""

    fileDropped = Signal(str)
    activated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(210)
        self.setProperty("active", False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(8)
        lay.addStretch(1)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setVisible(False)
        self.glyph = elabel("⇩", align=Qt.AlignmentFlag.AlignCenter)
        self.glyph.setStyleSheet(f"font-size: 30pt; color: {E['accent']};")
        self.title = elabel("", "DropTitle", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.or_label = elabel("", "Muted", align=Qt.AlignmentFlag.AlignCenter)
        self.choose = ebutton("")
        self.choose.clicked.connect(self.activated)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.choose)
        row.addStretch(1)
        for w in (self.preview, self.glyph, self.title, self.or_label):
            lay.addWidget(w)
        lay.addLayout(row)
        lay.addStretch(1)
        self.retranslate()

    def retranslate(self) -> None:
        self.title.setText(tr("easy.drop"))
        self.or_label.setText(tr("easy.or"))
        self.choose.setText(tr("easy.choose_image"))
        self.choose.setAccessibleName(tr("easy.choose_image"))
        self.setAccessibleName(tr("easy.drop"))
        self.setAccessibleDescription(tr("easy.drop_hint"))
        self.setToolTip(tr("easy.drop_hint"))

    def show_preview(self, pixmap) -> None:
        if pixmap is None or pixmap.isNull():
            self.preview.setVisible(False)
            self.glyph.setVisible(True)
            return
        self.preview.setPixmap(pixmap)
        self.preview.setVisible(True)
        self.glyph.setVisible(False)

    def _set_active(self, on: bool) -> None:
        self.setProperty("active", on)
        self.style().unpolish(self)
        self.style().polish(self)

    @staticmethod
    def _local_file(event) -> str:
        md = event.mimeData()
        if md is None or not md.hasUrls():
            return ""
        for url in md.urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
                return url.toLocalFile()
        return ""

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self._local_file(e):
            e.acceptProposedAction()
            self._set_active(True)
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self._set_active(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e) -> None:  # noqa: N802
        self._set_active(False)
        path = self._local_file(e)
        if path:
            e.acceptProposedAction()
            self.fileDropped.emit(path)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            e.accept()
            return
        super().keyPressEvent(e)


class Card(QFrame):
    """A small summary card: title + label/value rows (values selectable)."""

    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 14)
        self.lay.setSpacing(6)
        self.title = elabel(title, "CardTitle")
        self.lay.addWidget(self.title)
        self.body = QVBoxLayout()
        self.body.setSpacing(4)
        self.lay.addLayout(self.body)
        self.lay.addStretch(1)
        self.rows: list[tuple[QLabel, QLabel]] = []

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        while self.body.count():
            it = self.body.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self.rows = []
        for k, v in rows:
            kl = elabel(k, "Help", wrap=True)
            vl = elabel(v, "CardValue", wrap=True, selectable=True)
            vl.setAccessibleName(f"{k}: {v}")
            self.body.addWidget(kl)
            self.body.addWidget(vl)
            self.rows.append((kl, vl))
        self.setAccessibleName(f"{self.title.text()}: " + "; ".join(f"{k} {v}" for k, v in rows))


class PhaseTimeline(QWidget):
    """Five friendly words. Done = check mark, current = filled dot + bold, pending = hollow dot."""

    PHASES = ("Preparing", "Analyzing", "Reconstructing", "Validating", "Finalizing")

    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        lay.addStretch(1)
        self.labels = []
        for _p in self.PHASES:
            lab = QLabel()
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.labels.append(lab)
            lay.addWidget(lab)
        lay.addStretch(1)
        self.current = -1
        self.set_phase(-1)

    def set_phase(self, index: int, done_all: bool = False) -> None:
        self.current = index
        for i, (p, lab) in enumerate(zip(self.PHASES, self.labels)):
            word = tr(f"easy.phase.{p}")
            if done_all or i < index:
                lab.setText(f"✓ {word}")
                lab.setStyleSheet(f"color: {E['ok']}; font-weight: 600;")
                state = tr("easy.state_complete")
            elif i == index:
                lab.setText(f"● {word}")
                lab.setStyleSheet(f"color: {E['accent']}; font-weight: 800;")
                state = tr("easy.state_active")
            else:
                lab.setText(f"○ {word}")
                lab.setStyleSheet(f"color: {E['muted']};")
                state = tr("easy.state_pending")
            lab.setAccessibleName(f"{word}: {state}")
