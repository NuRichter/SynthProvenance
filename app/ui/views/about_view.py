"""About This Program, Research Foundations (HERE OUR HERO) and the ISO-5807-style workflow.

The workflow diagram uses conventional ISO 5807 flowchart notation (terminator,
process, decision, predefined process). The UI states this follows ISO 5807 conventions
and never claims certification. The quality section references ISO/IEC 25010:2023 as a
model, again without claiming certification.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget

from app import __subtitle__, __version__
from app.research import library as L
from app.research.methods import MethodRegistry
from app.ui.theme import C
from app.ui.views.base import View, row
from app.ui.widgets.common import DataTable, Panel, button, label

ABOUT_HTML = f"""
<h2 style="color:{C['cyan']}">SynthProvenance {__version__}</h2>
<p><b>{__subtitle__}</b><br>Insyide Innovations Lab &middot; NuRichter Workspace</p>
<p><i>SynthProvenance is a research masterpiece of NuRichter Workspace.</i></p>

<h3 style="color:{C['cyan']}">What is SynthProvenance?</h3>
<p>A local-first desktop laboratory that separates and measures the layers through which an image can carry
information about its origin: C2PA provenance, ordinary metadata, encoding, file structure, decoded pixels, and
candidate generative-image fingerprints. It also provides a controlled surrogate watermark laboratory with known
ground truth for separation, reconstruction, robustness and hypothesis research.</p>

<h3 style="color:{C['cyan']}">Research philosophy</h3>
<p>WE DO NOT GUESS. WE MEASURE. Every claim is a measurement, every experiment is logged with a reproducible
record, every external source is traceable, and every limitation is visible. Failed and weak experiments are
documented, never hidden.</p>

<h3 style="color:{C['cyan']}">Scientific scope</h3>
<p>In scope: descriptive forensic analysis (residual, FFT, DCT, wavelet, Benford, LID, consensus), controlled
surrogate watermark studies with ground truth, C2PA and metadata observation, pixel integrity and reproducibility.
Out of scope by design: claiming an image is AI-generated or human-made from pixels, attacking real pixel-domain
watermarks (SynthID included), and searching for transformations that defeat detectors.</p>

<h3 style="color:{C['cyan']}">Terminology kept separate</h3>
<p>Intrinsic/passive fingerprint &ne; causal fingerprint &ne; spectral cue &ne; proactive watermark &ne; detector
representation &ne; C2PA provenance &ne; external platform label. C2PA &ne; intrinsic fingerprint; metadata &ne;
SynthID; SynthID &ne; generic AI detector; no detected signal &ne; human-created.</p>

<h3 style="color:{C['cyan']}">Local processing</h3>
<p>Default mode is LOCAL-ONLY. A runtime audit hook blocks outbound network connections from the application. No
telemetry, no uploads, no hidden cloud inference, no silent model downloads during analysis. Online SynthID
verification is an explicit, consent-gated hand-off to an official Google page in the browser.</p>

<h3 style="color:{C['cyan']}">Reproducibility</h3>
<p>Every experiment and research run has an id (SPX-... / SPX-FP-...) and stores input/output hashes, parameters,
seed, environment (OS, CPU, GPU, CUDA, library versions), runtime and metrics. EXPORT FOR PAPER writes CSV, JSON,
PDF, PNG and a ZIP with SHA-256 and BLAKE3 manifests.</p>

<h3 style="color:{C['cyan']}">Software quality</h3>
<p>Quality is organised against ISO/IEC 25010:2023 as a reference model (functional suitability, performance
efficiency, compatibility, usability, reliability, security, maintainability, portability). See
docs/SOFTWARE_QUALITY.md. This is a reference mapping, not a certification.</p>
"""


class ISOWorkflow(QWidget):
    """ISO-5807-style research workflow flowchart (terminators, processes, decisions)."""

    NODES = [
        ("term", "START"), ("io", "INPUT IMAGE"), ("proc", "FILE INTEGRITY CHECK"), ("proc", "FORENSIC BASELINE"),
        ("proc", "METADATA ANALYSIS"), ("proc", "C2PA ANALYSIS"), ("dec", "LOCAL METHOD AVAILABLE?"),
        ("proc", "SYNTHID / FINGERPRINT ANALYSIS"), ("proc", "METHOD SELECTION"), ("dec", "GROUND TRUTH AVAILABLE?"),
        ("pre", "CONTROLLED EXPERIMENT"), ("pre", "SEPARATION / RECONSTRUCTION"), ("dec", "PIXEL INTEGRITY ACCEPTABLE?"),
        ("proc", "PROVENANCE COMPARISON"), ("proc", "STATISTICAL EVALUATION"), ("dec", "RESULT VALIDATED?"),
        ("proc", "REPRODUCIBILITY RECORD"), ("io", "RESEARCH REPORT"), ("term", "END"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(360, len(self.NODES) * 64 + 40)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C["base"]))
        w = self.width()
        cx = w / 2
        bw, bh, gap = min(300, w - 60), 40, 24
        y = 20
        centers = []
        for kind, text in self.NODES:
            rect = QRectF(cx - bw / 2, y, bw, bh)
            self._shape(p, kind, rect, text)
            centers.append((cx, y + bh))
            y += bh + gap
        p.setPen(QPen(QColor(C["muted"]), 1.4))
        for i in range(len(centers) - 1):
            x0, y0 = centers[i]
            x1 = centers[i + 1][0]
            y1 = y0 + gap
            p.drawLine(int(x0), int(y0), int(x1), int(y1))
            p.drawPolygon(QPolygonF([self._pt(x1, y1), self._pt(x1 - 4, y1 - 7), self._pt(x1 + 4, y1 - 7)]))

    @staticmethod
    def _pt(x, y):
        from PySide6.QtCore import QPointF
        return QPointF(x, y)

    def _shape(self, p: QPainter, kind: str, r: QRectF, text: str) -> None:
        colors = {"term": C["ok"], "io": C["blue"], "proc": C["cyan"], "dec": C["warn"], "pre": C["cyan"]}
        p.setPen(QPen(QColor(colors.get(kind, C["cyan"])), 1.6))
        p.setBrush(QColor(C["panel"]))
        if kind == "term":
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        elif kind == "dec":
            poly = QPolygonF([self._pt(r.center().x(), r.top()), self._pt(r.right(), r.center().y()),
                              self._pt(r.center().x(), r.bottom()), self._pt(r.left(), r.center().y())])
            p.drawPolygon(poly)
        elif kind == "io":
            sk = r.height() * 0.3
            poly = QPolygonF([self._pt(r.left() + sk, r.top()), self._pt(r.right(), r.top()),
                              self._pt(r.right() - sk, r.bottom()), self._pt(r.left(), r.bottom())])
            p.drawPolygon(poly)
        elif kind == "pre":
            p.drawRect(r)
            p.drawLine(int(r.left() + 6), int(r.top()), int(r.left() + 6), int(r.bottom()))
            p.drawLine(int(r.right() - 6), int(r.top()), int(r.right() - 6), int(r.bottom()))
        else:
            p.drawRect(r)
        p.setPen(QColor(C["text"]))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)


class AboutView(View):
    title = "About This Program"
    subtitle = "What SynthProvenance is, how it works, and the research foundations it is built on."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        bar = QHBoxLayout()
        self.b_about = button("ABOUT", checkable=True)
        self.b_hero = button("HERE OUR HERO", primary=True, checkable=True,
                             tooltip="Open RESEARCH FOUNDATIONS: the literature behind SynthProvenance")
        self.b_flow = button("ISO-5807 WORKFLOW", checkable=True)
        self.b_quality = button("SOFTWARE QUALITY (ISO/IEC 25010)", checkable=True)
        for i, b in enumerate((self.b_about, self.b_hero, self.b_flow, self.b_quality)):
            b.clicked.connect(lambda _c=False, n=i: self.stack.setCurrentIndex(n))
            bar.addWidget(b)
        bar.addStretch(1)
        self.b_about.setChecked(True)
        self.root.addLayout(bar)
        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)
        # 0 about
        about = QTextBrowser()
        about.setOpenExternalLinks(False)
        about.setHtml(ABOUT_HTML)
        self.stack.addWidget(about)
        # 1 foundations
        self.stack.addWidget(self._foundations())
        # 2 workflow
        sa = _scroll(ISOWorkflow())
        self.stack.addWidget(_wrap_note(sa, "Workflow notation follows ISO 5807 conventions. SynthProvenance does not "
                                        "claim ISO certification."))
        # 3 quality
        self.stack.addWidget(self._quality())

    def _foundations(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("RESEARCH FOUNDATIONS", "LayerTitle"))
        lay.addWidget(label("The literature that forms the scientific foundation of SynthProvenance. Taxonomy-file "
                            "references come first; validated external additions follow. Full details and exports are in "
                            "the Research Library.", "Muted", wrap=True))
        table = DataTable(["ID", "Year", "Title", "Category", "Origin", "Verified"])
        table.setMinimumHeight(420)
        try:
            items = L.foundations()
            table.set_data(["ID", "Year", "Title", "Category", "Origin", "Verified"],
                           [[it.get("id"), it.get("year"), it.get("title"), it.get("fingerprint_category"),
                             it.get("origin", "").split()[0], it.get("verification_status")] for it in items])
            n_tax = sum(1 for i in items if i.get("origin") == "TAXONOMY_FILE")
            lay.addWidget(label(f"{len(items)} verified references ({n_tax} from the taxonomy file, "
                                f"{len(items) - n_tax} external research additions).", "Muted"))
        except Exception as exc:  # noqa: BLE001
            lay.addWidget(label(f"Library unavailable: {exc}", "Muted"))
        lay.addWidget(table)
        b = button("Open Research Library")
        b.clicked.connect(lambda: self.win.go("Research Library"))
        lay.addWidget(b)
        return w

    def _quality(self) -> QWidget:
        from app.research.methods import MethodRegistry
        reg = MethodRegistry()
        rows = [
            ["Functional suitability", f"{len(reg.ready())} methods run and are validated by the test suite; honest "
             "UNAVAILABLE/NOT_IMPLEMENTED status for the rest"],
            ["Performance efficiency", "overlap-aware tiling, Welch spectra and strip-wise metrics bound memory; "
             "any-resolution engine"],
            ["Compatibility", "PNG/JPEG/WEBP/TIFF/BMP/GIF; portable one-folder Windows build"],
            ["Usability", "guided wizard, method cards, tooltips, clear status language"],
            ["Reliability", "pixel integrity verified; originals preserved and re-hashed; failed runs recorded"],
            ["Security", "untrusted images; no code execution from metadata; path-traversal guards; safe subprocess"],
            ["Maintainability", "plugin method registry; pure numpy engine separated from Qt; full test suite"],
            ["Portability", "local-only; numpy/Pillow/PySide6 only; no GPU or model required"],
        ]
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("SOFTWARE QUALITY - ISO/IEC 25010:2023 reference model", "LayerTitle"))
        lay.addWidget(label("Mapping of SynthProvenance characteristics to the ISO/IEC 25010:2023 product-quality model. "
                            "Reference mapping only; not a certification. See docs/SOFTWARE_QUALITY.md.", "Muted",
                            wrap=True))
        t = DataTable(["Quality characteristic", "How SynthProvenance addresses it"])
        t.setMinimumHeight(360)
        t.set_data(["Quality characteristic", "How SynthProvenance addresses it"], rows)
        lay.addWidget(t)
        return w


def _scroll(widget):
    from PySide6.QtWidgets import QScrollArea
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(widget)
    return sa


def _wrap_note(widget, note: str) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(label("ISO-5807-STYLE RESEARCH WORKFLOW", "LayerTitle"))
    lay.addWidget(widget, 1)
    lay.addWidget(label(note, "Muted", wrap=True))
    return w
