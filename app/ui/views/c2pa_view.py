from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QTabWidget, QVBoxLayout, QWidget

from app.core.provenance_engine import build_provenance_graph
from app.services.c2pa_experiment import C2PA_WARNING
from app.ui.views.base import View, fill_conditions, row
from app.ui.widgets.charts import ProvenanceGraph
from app.ui.widgets.common import DataTable, KVTable, Panel, Readout, banner, button, label


class C2PAView(View):
    title = "C2PA Provenance"
    subtitle = "C2PA  \u00b7  PROVENANCE / CONTENT CREDENTIAL LAYER. Absence of C2PA never implies that an image is not AI-generated."

    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        ro = QHBoxLayout()
        self.r_pres, self.r_bind = Readout("Presence"), Readout("Hard binding (c2pa.hash.data)")
        self.r_val, self.r_trust = Readout("Signature validity"), Readout("Trust")
        for r in (self.r_pres, self.r_bind, self.r_val, self.r_trust):
            ro.addWidget(r)
        self.root.addLayout(ro)
        tabs = QTabWidget()
        # manifest store
        mw = QWidget()
        ml = QHBoxLayout(mw)
        left = QVBoxLayout()
        self.manifests = QListWidget()
        self.manifests.currentRowChanged.connect(self._show_manifest)
        b_json = button("Export manifest JSON")
        b_json.clicked.connect(self._export)
        left.addWidget(label("MANIFESTS (last = active)", "PanelTitle"))
        left.addWidget(self.manifests)
        left.addWidget(b_json)
        ml.addLayout(left, 2)
        inner = QTabWidget()
        self.m_kv = KVTable()
        self.actions = DataTable(["Action", "digitalSourceType", "softwareAgent", "When", "Description"])
        self.ingredients = DataTable(["Title", "Format", "Relationship", "Has manifest", "Instance ID"])
        self.assertions = DataTable(["Label", "Content type", "Bytes"])
        inner.addTab(self.m_kv, "Claim && Signature")  # "&&": a single "&" is a Qt mnemonic
        inner.addTab(self.actions, "Actions")
        inner.addTab(self.ingredients, "Ingredients")
        inner.addTab(self.assertions, "Assertions")
        ml.addWidget(inner, 5)
        tabs.addTab(mw, "Manifest Store")
        # separation experiment
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.addWidget(label("C2PA / PROVENANCE DATA SEPARATION EXPERIMENT", "LayerTitle"))
        sl.addWidget(banner(C2PA_WARNING))
        sl.addWidget(banner("Removes only the manifest store container (JPEG APP11 / PNG caBX / WebP C2PA). All other bytes, "
                            "including compressed image data, are copied verbatim. The original input is never modified. "
                            "Pixel identity is verified afterwards, not assumed.", info=True))
        self.inc_xmp = QCheckBox("Also remove XMP provenance declarations (DigitalSourceType, AISystemUsed, c2pa:*)")
        b_run = button("Run separation experiment", primary=True)
        b_run.clicked.connect(lambda: ctl.run_transformation("c2pa_separation",
                                                             {"include_xmp_declarations": self.inc_xmp.isChecked()}))
        sl.addLayout(row(self.inc_xmp, None, b_run))
        self.sep_cond = QComboBox()
        self.sep_cond.currentIndexChanged.connect(self._fill_sep)
        sl.addLayout(row(label("Condition:"), self.sep_cond, None))
        self.sep = DataTable(["Property", "BEFORE", "AFTER"], mono_cols=(1, 2))
        sl.addWidget(self.sep, 1)
        tabs.addTab(sw, "Separation Experiment")
        # AI content signal
        aw = QWidget()
        al = QVBoxLayout(aw)
        self.r_sig = Readout("Observable AI-content provenance signal")
        al.addWidget(self.r_sig)
        self.evidence = DataTable(["Tier", "Source", "Field", "Value", "Counted", "Note"])
        al.addWidget(self.evidence, 1)
        self.unknowns = label("", "Muted", wrap=True)
        al.addWidget(self.unknowns)
        tabs.addTab(aw, "AI Content Signal")
        # graph
        gw = QWidget()
        gl = QHBoxLayout(gw)
        self.graph = ProvenanceGraph()
        self.graph.nodeSelected.connect(self._node)
        gl.addWidget(self.graph, 2)
        self.node_kv = KVTable()
        gl.addWidget(self.node_kv, 3)
        tabs.addTab(gw, "Provenance Graph")
        # external records
        ew = QWidget()
        el = QVBoxLayout(ew)
        el.addWidget(banner("EXTERNAL PLATFORM CLASSIFICATION tier: record what a platform displayed, by hand. SynthProvenance "
                            "never contacts platforms. Entries are unverified and never counted as evidence.", info=True))
        self.ext_platform, self.ext_label, self.ext_note = QLineEdit(), QLineEdit(), QLineEdit()
        self.ext_platform.setPlaceholderText("Platform (e.g. social network name)")
        self.ext_label.setPlaceholderText("Label shown (e.g. 'AI info', 'Made with AI', none)")
        self.ext_note.setPlaceholderText("Note / date / account context")
        self.ext_cond = QComboBox()
        b_rec = button("Record")
        b_rec.clicked.connect(lambda: ctl.record_external("PLATFORM", self.ext_platform.text(), self.ext_label.text(),
                                                          self.ext_cond.currentData() or "ORIGINAL", self.ext_note.text()))
        el.addLayout(row(self.ext_platform, self.ext_label, self.ext_cond))
        el.addLayout(row(self.ext_note, b_rec))
        self.ext_table = DataTable(["Layer", "Condition", "Platform / tool", "Label", "Observed (UTC)", "Tier", "Note"])
        el.addWidget(self.ext_table, 1)
        tabs.addTab(ew, "External Records")
        self.root.addWidget(tabs, 1)
        self._nodes: list = []

    def _c2(self) -> dict:
        return (self.ctl.source.analysis_dict.get("c2pa") or {}) if self.ctl.source else {}

    def refresh(self) -> None:
        c2 = self._c2()
        self.r_pres.set(c2.get("state", "-"), c2.get("summary", "No image loaded"))
        self.r_bind.set(c2.get("hard_binding", "-"), c2.get("hard_binding_detail", ""))
        self.r_val.set(c2.get("validity", "-"), c2.get("validity_detail", ""))
        self.r_trust.set(c2.get("trust", "-"), f"engine: {c2.get('engine', '-')}")
        self.manifests.clear()
        for m in c2.get("manifests") or []:
            self.manifests.addItem(("\u25cf ACTIVE  " if m["label"] == c2.get("active_manifest") else "") + m["label"])
        if self.manifests.count():
            self.manifests.setCurrentRow(self.manifests.count() - 1)
        else:
            self._show_manifest(-1)
        fill_conditions(self.sep_cond, self.ctl, include_original=False, only_ops=("c2pa_separation", "metadata_sanitize"))
        self._fill_sep()
        sig = (self.ctl.source.analysis_dict.get("signal") or {}) if self.ctl.source else {}
        self.r_sig.set(sig.get("state", "-"), sig.get("statement", ""))
        rows = [[e["tier"], e["source"], e["field"], e["value"], "YES" if e["counted"] else "NO", e.get("note", "")]
                for e in (sig.get("evidence") or []) + (sig.get("interpretations") or [])]
        exp = self.ctl.experiment
        for e in (exp.external_classifications if exp else []):
            rows.append([e.tier, e.platform, e.condition, e.label, "NO", e.note])
        self.evidence.set_data(["Tier", "Source", "Field", "Value", "Counted", "Note"], rows)
        self.unknowns.setText("UNKNOWN INFORMATION:\n" + "\n".join(f"- {u}" for u in sig.get("unknowns") or []))
        if self.ctl.source:
            self._nodes = build_provenance_graph(exp.baseline if exp else self.ctl.source.analysis_dict,
                                                 exp.transformations if exp else [])
            self.graph.set_nodes(self._nodes)
            self._node(max(self.graph.selected, 0))
        fill_conditions(self.ext_cond, self.ctl)
        self.ext_table.set_data(["Layer", "Condition", "Platform / tool", "Label", "Observed (UTC)", "Tier", "Note"],
                                [[e.layer, e.condition, e.platform, e.label, e.observed_on[:19], e.tier, e.note]
                                 for e in (exp.external_classifications if exp else [])])

    def _show_manifest(self, idx: int) -> None:
        ms = self._c2().get("manifests") or []
        if not (0 <= idx < len(ms)):
            self.m_kv.set_rows([["Manifest", "none"]])
            for t in (self.actions, self.ingredients, self.assertions):
                t.setRowCount(0)
            return
        m = ms[idx]
        self.m_kv.set_rows([["Label", m["label"]], ["Claim version", m["claim_version"]], ["Claim generator", m["claim_generator"]],
                            ["Title", m["title"]], ["Format", m["format"]], ["Instance ID", m["instance_id"]],
                            ["Signature present", m["signature_present"]], ["Signature algorithm", m["signature_algorithm"]],
                            ["Issuer", m["issuer"] or "-"], ["Subject", m["subject"] or "-"],
                            ["Certificate validity", f"{m['cert_not_before']} .. {m['cert_not_after']}"],
                            ["Timestamp token", m["timestamp_token"]], ["Parse errors", "; ".join(m["errors"]) or "none"]])
        self.actions.set_data(["Action", "digitalSourceType", "softwareAgent", "When", "Description"],
                              [[a["action"], a["digital_source_type"], a["software_agent"], a["when"], a["description"]] for a in m["actions"]])
        self.ingredients.set_data(["Title", "Format", "Relationship", "Has manifest", "Instance ID"],
                                  [[g["title"], g["format"], g["relationship"], g["has_manifest"], g["instance_id"]] for g in m["ingredients"]])
        self.assertions.set_data(["Label", "Content type", "Bytes"], [[a["label"], a["content_type"], a["bytes"]] for a in m["assertions"]])

    def _fill_sep(self) -> None:
        t = self.ctl.record(self.sep_cond.currentData() or "")
        if t is None:
            self.sep.set_data(["Property", "BEFORE", "AFTER"], [["Run the separation experiment to compare BEFORE / AFTER", "", ""]])
            return
        pv, pm = t.provenance_differences or {}, t.pixel_metrics or {}
        lay = {x["layer"]: x for x in t.layers}
        self.sep.set_data(["Property", "BEFORE", "AFTER"], [
            ["C2PA presence", pv.get("c2pa_before"), pv.get("c2pa_after")],
            ["Manifests", pv.get("manifests_before"), pv.get("manifests_after")],
            ["Store SHA-256", pv.get("store_sha256_before") or "-", pv.get("store_sha256_after") or "-"],
            ["Active manifest", pv.get("active_manifest_before") or "-", pv.get("active_manifest_after") or "-"],
            ["Hard binding", pv.get("hard_binding_before"), pv.get("hard_binding_after")],
            ["AI-content signal", pv.get("signal_before"), pv.get("signal_after")],
            ["C2PA layer state", "", lay.get("C2PA", {}).get("state")],
            ["SynthID layer state", "", lay.get("SynthID", {}).get("state")],
            ["Ordinary metadata", "", lay.get("Ordinary metadata", {}).get("state")],
            ["Pixels", "baseline", pm.get("verdict")],
            ["File SHA-256", t.input_sha256, t.output_sha256],
            ["Statement", "", pv.get("statement")]])

    def _node(self, i: int) -> None:
        if not (0 <= i < len(self._nodes)):
            return
        n = self._nodes[i]
        self.node_kv.set_rows([["Stage", n["stage"]], ["State", n["state"]], ["Evidence basis", n["basis"]],
                               ["Timestamp", n["timestamp"] or "-"], ["Hash", n["hash"] or "-"], ["Operation", n["operation"] or "-"],
                               ["Tool", n["tool"] or "-"], ["Parameters", n["parameters"] or "-"],
                               ["Metadata state", n["metadata_state"] or "-"], ["C2PA / signal state", n["provenance_state"] or "-"]]
                              + [["Detail", d] for d in n["details"]])

    def _export(self) -> None:
        if self.ctl.source is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export C2PA manifest JSON", "c2pa_manifest.json", "JSON (*.json)")
        if path:
            self.ctl.export_manifest_json(path)
