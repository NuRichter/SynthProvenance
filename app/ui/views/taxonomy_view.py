"""Fingerprint Taxonomy browser.

Displays the structured taxonomy database parsed from the supplied source file. The
seven top-level families are kept separate (the UI never collapses them into one "AI
fingerprint" class), the explicit separation rules are shown, and every entry keeps its
source line and quoted definition.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from app.research import taxonomy as T
from app.ui.views.base import View, row
from app.ui.widgets.common import DataTable, KVTable, Panel, Readout, banner, button, label

COLUMNS = ["ID", "Term", "Category", "Subcategory", "Domain", "Representation", "Status", "Line"]


class TaxonomyView(View):
    title = "Fingerprint Taxonomy"
    subtitle = ("Structured taxonomy parsed from the supplied research file. Seven families kept separate by design; "
                "definitions quoted from the source; every entry records its source line.")

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        try:
            self.db = T.load()
        except Exception as exc:  # noqa: BLE001
            self.db = {"entries": [], "categories": [], "references": [], "separation_rules": [], "error": str(exc)}
        ro = QHBoxLayout()
        self.r_entries = Readout("Terminology entries")
        self.r_refs = Readout("Anchor references")
        self.r_cats = Readout("Families")
        self.r_source = Readout("Source")
        for r in (self.r_entries, self.r_refs, self.r_cats, self.r_source):
            ro.addWidget(r)
        self.root.addLayout(ro)
        rules = Panel("Separation rules (these layers are never merged)")
        for rtext in self.db.get("separation_rules", []):
            rules.add(label("• " + rtext, "Muted"))
        self.root.addWidget(rules)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search term / alias / definition / method / paper")
        self.search.textChanged.connect(self._mark)
        self.cat = QComboBox()
        self.cat.addItem("All families", "")
        for c in self.db.get("categories", []):
            self.cat.addItem(f"{c['code']}. {c['name']} ({c['entries']})", c["key"])
        self.cat.currentIndexChanged.connect(self._mark)
        bar.addWidget(label("Filter:", "Muted"))
        bar.addWidget(self.search, 1)
        bar.addWidget(self.cat)
        self.root.addLayout(bar)
        self.table = DataTable(COLUMNS, mono_cols=(7,))
        self.table.setMinimumHeight(320)
        self.table.itemSelectionChanged.connect(self._show)
        self.root.addWidget(self.table, 1)
        self.detail = KVTable()
        self.detail.setMinimumHeight(220)
        self.root.addWidget(self.detail)
        if self.db.get("error"):
            self.root.addWidget(banner("Taxonomy database error: " + self.db["error"]))
        self._rows: list = []

    def refresh(self) -> None:
        entries = self.db.get("entries", [])
        self.r_entries.set(str(len(entries)), "terms, aliases, methods and search vocabulary")
        self.r_refs.set(str(len(self.db.get("references", []))), "APA 7 references in the source file")
        self.r_cats.set(str(len(self.db.get("categories", []))), "top-level families (A-F)")
        src = self.db.get("source", {})
        self.r_source.set(src.get("file", "-"), f"sha256 {src.get('sha256', '')[:12]}")
        res = T.search(self.db, self.search.text(), self.cat.currentData() or "")
        self._rows = res
        self.table.set_data(COLUMNS, [[e["id"], e["term"], e["category_code"], e["subcategory"][:40], e.get("domain"),
                                       e.get("representation", "")[:30], e.get("research_status"), e.get("source_line")]
                                      for e in res[:1500]])

    def _show(self) -> None:
        r = self.table.currentRow()
        if r < 0 or r >= len(self._rows):
            return
        e = self._rows[r]
        self.detail.set_rows([("Term", e["term"]), ("Category", f"{e['category_code']} {e['category']}"),
                              ("Subcategory", e["subcategory"]), ("Domain", e.get("domain")),
                              ("Representation", e.get("representation")), ("Status", e.get("research_status")),
                              ("Definition (quoted)", e.get("definition", "")),
                              ("Methods", ", ".join(e.get("method", [])) or "-"),
                              ("Papers", "; ".join(e.get("paper", [])) or "-"),
                              ("Derived fields", ", ".join(e.get("derived_fields", []))),
                              ("Source line", str(e.get("source_line")))])
