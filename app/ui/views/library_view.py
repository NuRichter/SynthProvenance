"""Research Library: a searchable, verified knowledge base, kept as separate kinds
(v4 Section 25): TERMINOLOGY, METHODS, PAPERS, TOOLS, DATASETS.

Papers were verified against DOI/arXiv/CVF/PMLR and are marked VERIFIED or
VERIFIED_WITH_CORRECTIONS. The number of papers is not inflated to match the number of
terminology entries. Per-paper actions (HERE OUR HERO): COPY APA, COPY BIBTEX, OPEN
PAPER, OPEN SOURCE. APA 7 / BibTeX / CITATION.cff export the current paper selection. No
citation, DOI, dataset or tool entry is fabricated.
"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from app.research import library as L
from app.research import taxonomy as T
from app.ui.views.base import View, row
from app.ui.widgets.common import DataTable, KVTable, Panel, Readout, banner, button, label


class ResearchLibraryView(View):
    title = "Research Library"
    subtitle = ("Verified knowledge base kept as separate kinds: Terminology, Methods, Papers, Tools, Datasets. Papers "
                "carry verification status and corrections. Nothing is fabricated; the paper count is not inflated.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        try:
            self.items = L.all_items()
            self.accessed = L.load()["accessed"]
            self.cat = L.catalog()
            self.err = ""
        except Exception as exc:  # noqa: BLE001
            self.items, self.accessed, self.cat, self.err = [], "", {"methods": [], "datasets": [], "tools": []}, str(exc)
        try:
            self.tax = T.load()
        except Exception:  # noqa: BLE001
            self.tax = {"entries": []}
        ro = QHBoxLayout()
        self.r_terms = Readout("Terminology")
        self.r_papers = Readout("Papers (verified)")
        self.r_methods = Readout("Methods surveyed")
        self.r_datasets = Readout("Datasets")
        for r in (self.r_terms, self.r_papers, self.r_methods, self.r_datasets):
            ro.addWidget(r)
        self.root.addLayout(ro)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(520)
        self.root.addWidget(self.tabs, 1)
        self._build_papers()
        self._build_terminology()
        self._build_methods()
        self._build_tools()
        self._build_datasets()
        if self.err:
            self.root.addWidget(banner("Research library error: " + self.err))

    # ---- Papers (HERE OUR HERO wall)
    def _build_papers(self) -> None:
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title / authors / venue / idea / DOI / arXiv")
        self.search.textChanged.connect(self._mark)
        self.f_cat = self._combo("fingerprint_category", "Category")
        self.f_gen = self._combo("generator_family", "Generator")
        self.f_local = self._combo("local_reproducibility", "Local")
        self.f_origin = self._combo("origin", "Origin")
        bar.addWidget(self.search, 1)
        for c in (self.f_cat, self.f_gen, self.f_local, self.f_origin):
            bar.addWidget(c)
        actions = QHBoxLayout()
        for text, fn in (("COPY APA", lambda: self._copy("apa")), ("COPY BIBTEX", lambda: self._copy("bib")),
                         ("OPEN PAPER", lambda: self._open("paper_url")), ("OPEN SOURCE", lambda: self._open("repo_url")),
                         ("Export APA 7...", lambda: self._export("apa")), ("Export BibTeX...", lambda: self._export("bib")),
                         ("Export CITATION.cff...", lambda: self._export("cff"))):
            b = button(text, primary=text in ("COPY APA", "COPY BIBTEX"))
            b.clicked.connect(fn)
            actions.addWidget(b)
        actions.addStretch(1)
        self.table = DataTable(L.DISPLAY_COLUMNS)
        self.table.setMinimumHeight(260)
        self.table.itemSelectionChanged.connect(self._show)
        self.detail = KVTable()
        self.detail.setMinimumHeight(200)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("RESEARCH FOUNDATIONS - the literature wall behind SynthProvenance.", "LayerTitle"))
        lay.addLayout(bar)
        lay.addLayout(actions)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.detail)
        self.tabs.addTab(w, "Papers")
        self._rows: list = []

    def _build_terminology(self) -> None:
        self.tsearch = QLineEdit()
        self.tsearch.setPlaceholderText("Search terminology / alias / definition")
        self.tsearch.textChanged.connect(self._mark)
        self.tcat = QComboBox()
        self.tcat.addItem("All families", "")
        for c in self.tax.get("categories", []):
            self.tcat.addItem(f"{c['code']}. {c['name']}", c["key"])
        self.tcat.currentIndexChanged.connect(self._mark)
        self.tterm = DataTable(["ID", "Term", "Family", "Status", "Representation"])
        self.tterm.setMinimumHeight(380)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Terminology from the taxonomy file. Terms, aliases, method names and search vocabulary are "
                            "distinct kinds; the seven families are kept separate.", "Muted", wrap=True))
        lay.addLayout(row(self.tsearch, self.tcat))
        lay.addWidget(self.tterm)
        self.tabs.addTab(w, "Terminology")

    def _build_methods(self) -> None:
        self.mtable = DataTable(["Method", "Verdict", "Framework", "License", "Repository"])
        self.mtable.setMinimumHeight(400)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Open-source implementations surveyed for SynthProvenance (none were executed in the "
                            "survey; see docs/SYNTHID_IMPLEMENTATION_SURVEY.md). Verdict = local feasibility.", "Muted",
                            wrap=True))
        lay.addWidget(self.mtable)
        self.tabs.addTab(w, "Methods")

    def _build_tools(self) -> None:
        self.ttable = DataTable(["Tool", "Role", "Version", "License", "URL"])
        self.ttable.setMinimumHeight(200)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Optional external tools and the official SynthID service. SynthProvenance never downloads "
                            "or redistributes them; they are user-installed.", "Muted", wrap=True))
        lay.addWidget(self.ttable)
        self.tabs.addTab(w, "Tools")

    def _build_datasets(self) -> None:
        self.dtable = DataTable(["Dataset", "License", "Size / generators", "URL"])
        self.dtable.setMinimumHeight(360)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Benchmark datasets for AI-image forensics. Most are non-commercial; check each licence "
                            "before use. SynthProvenance bundles no dataset.", "Muted", wrap=True))
        lay.addWidget(self.dtable)
        self.tabs.addTab(w, "Datasets")

    # ---- helpers
    def _combo(self, field: str, label_text: str) -> QComboBox:
        c = QComboBox()
        c.setToolTip(label_text)
        c.addItem(f"All {label_text}", "")
        try:
            for v in L.options(field):
                c.addItem(str(v), v)
        except Exception:  # noqa: BLE001
            pass
        c.currentIndexChanged.connect(self._mark)
        return c

    def _filters(self) -> dict:
        return {"fingerprint_category": self.f_cat.currentData(), "generator_family": self.f_gen.currentData(),
                "local_reproducibility": self.f_local.currentData(), "origin": self.f_origin.currentData()}

    def _current(self) -> dict | None:
        r = self.table.currentRow()
        return self._rows[r] if 0 <= r < len(self._rows) else None

    def _copy(self, kind: str) -> None:
        it = self._current()
        if not it:
            return
        QGuiApplication.clipboard().setText(it.get("apa7" if kind == "apa" else "bibtex", ""))
        self.ctl.info.emit(f"Copied {kind.upper()} for {it.get('id')}")

    def _open(self, field: str) -> None:
        it = self._current()
        if it and it.get(field):
            QDesktopServices.openUrl(QUrl(it[field]))
        else:
            self.ctl.info.emit("No URL recorded for this item.")

    def _export(self, kind: str) -> None:
        res = L.search(self.search.text(), self._filters())
        if kind == "apa":
            text, name = L.to_apa7(res), "references_apa7.txt"
        elif kind == "bib":
            text, name = L.to_bibtex(res), "references.bib"
        else:
            text, name = L.citation_cff(), "CITATION.cff"
        dest, _ = QFileDialog.getSaveFileName(self, "Export", name)
        if dest:
            from pathlib import Path
            Path(dest).write_text(text, encoding="utf-8")
            self.ctl.info.emit(f"Exported: {Path(dest).name}")

    def refresh(self) -> None:
        self.r_terms.set(str(len(self.tax.get("entries", []))), "taxonomy entries")
        self.r_papers.set(str(len(self.items)), f"verified ({self.accessed})")
        self.r_methods.set(str(len(self.cat.get("methods", []))), "open-source implementations")
        self.r_datasets.set(str(len(self.cat.get("datasets", []))), "benchmark datasets")
        res = L.search(self.search.text(), self._filters())
        self._rows = res
        self.table.set_data(L.DISPLAY_COLUMNS, L.rows(res))
        te = T.search(self.tax, self.tsearch.text(), self.tcat.currentData() or "") if self.tax.get("entries") else []
        self.tterm.set_data(["ID", "Term", "Family", "Status", "Representation"],
                            [[e["id"], e["term"], e["category_code"], e.get("research_status"),
                              e.get("representation", "")[:30]] for e in te[:1500]])
        self.mtable.set_data(["Method", "Verdict", "Framework", "License", "Repository"],
                             [[m.get("method"), m.get("verdict"), m.get("framework"), (m.get("license") or "")[:40],
                               m.get("repo") or "-"] for m in self.cat.get("methods", [])])
        self.ttable.set_data(["Tool", "Role", "Version", "License", "URL"],
                             [[t.get("name"), t.get("role"), t.get("version"), t.get("license"), t.get("url")]
                              for t in self.cat.get("tools", [])])
        self.dtable.set_data(["Dataset", "License", "Size / generators", "URL"],
                             [[d.get("name"), (d.get("license") or "")[:50], (d.get("size") or "")[:60], d.get("url")]
                              for d in self.cat.get("datasets", [])])

    def _show(self) -> None:
        it = self._current()
        if not it:
            return
        self.detail.set_rows([("Title", it.get("title")), ("Authors", "; ".join(it.get("authors", []))),
                              ("Year / Venue", f"{it.get('year')} - {it.get('venue')}"),
                              ("DOI / arXiv", f"{it.get('doi') or '-'} / {it.get('arxiv') or '-'}"),
                              ("Key idea", it.get("key_idea")), ("Code availability", it.get("code_availability")),
                              ("Local reproducibility", it.get("local_reproducibility")),
                              ("Limitations", it.get("limitations")), ("Origin", it.get("origin")),
                              ("Verification", it.get("verification_status")),
                              ("Verification note", it.get("verification_note") or "-"), ("APA 7", it.get("apa7"))])
