from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout

from app import __brand_primary__, __brand_secondary__, __motto__, __subtitle__, __tagline__
from app.ui.views.base import View, row
from app.ui.widgets.charts import DropZone
from app.ui.widgets.common import DataTable, Panel, Readout, button, label


class DashboardView(View):
    def __init__(self, ctl, win) -> None:
        super().__init__(ctl, win)
        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(label(f"{__brand_primary__}   \u00b7   {__brand_secondary__}", "Brand"))
        brand.addWidget(label("SynthProvenance", "Hero"))
        brand.addWidget(label(__subtitle__, "Muted"))
        brand.addWidget(label(f"{__tagline__}   {__motto__}", "Muted"))
        self.root.addLayout(brand)

        top = QHBoxLayout()
        self.drop = DropZone()
        self.drop.fileDropped.connect(ctl.open_image)
        self.drop.clicked.connect(win.open_image_dialog)
        top.addWidget(self.drop, 5)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.r_exp = Readout("Current experiment ID")
        self.r_res = Readout("Loaded image resolution")
        self.r_pix = Readout("Pixel integrity status")
        self.r_prov = Readout("Provenance status (C2PA)")
        self.r_sid = Readout("SynthID analysis status")
        self.r_eng = Readout("Engine status")
        for i, r in enumerate((self.r_exp, self.r_res, self.r_pix, self.r_prov, self.r_sid, self.r_eng)):
            grid.addWidget(r, i // 2, i % 2)
        top.addLayout(grid, 6)
        self.root.addLayout(top)

        self.b_start = button("START EXPERIMENT", primary=True,
                              tooltip="Create the experiment workspace (original preserved), run baseline C2PA / SynthID / "
                                      "metadata / statistics analysis.")
        self.b_start.clicked.connect(ctl.start_experiment)
        b_open = button("Open Image")
        b_open.clicked.connect(win.open_image_dialog)
        b_demo = button("Open Demo Fixture", tooltip="Deterministic synthetic test image with EXIF/XMP/IPTC/ICC and an "
                                                     "UNSIGNED synthetic C2PA manifest.")
        b_demo.clicked.connect(ctl.open_demo_fixture)
        b_cmp = button("COMPARE", tooltip="Compare the original with a file processed elsewhere (e.g. a platform round-trip).")
        b_cmp.clicked.connect(win.compare_dialog)
        b_rep = button("EXPORT REPORT")
        b_rep.clicked.connect(lambda: win.go("Research Report"))
        self.root.addLayout(row(self.b_start, b_open, b_demo, b_cmp, b_rep, None))

        bottom = QHBoxLayout()
        p1 = Panel("Engine status")
        self.engines = DataTable(["Engine", "State", "Detail"])
        self.engines.setMinimumHeight(250)
        p1.add(self.engines)
        bottom.addWidget(p1, 5)
        p2 = Panel("Recent experiments")
        self.recent = DataTable(["Experiment ID", "Input", "Created (UTC)", "Transformations", "Signal"], mono_cols=(0,))
        self.recent.setMinimumHeight(220)
        self.recent.cellDoubleClicked.connect(self._load)
        p2.add(self.recent)
        b_load = button("Load selected")
        b_load.clicked.connect(lambda: self._load(self.recent.currentRow(), 0))
        b_ws = button("Open workspace")
        b_ws.clicked.connect(lambda: ctl.open_path(ctl.workspace.root))
        p2.add(row(b_load, b_ws, None))
        bottom.addWidget(p2, 6)
        self.root.addLayout(bottom)
        self.root.addStretch(1)

    def _load(self, r: int, _c: int) -> None:
        it = self.recent.item(r, 0) if r >= 0 else None
        if it is not None:
            self.ctl.load_experiment(it.text())

    def refresh(self) -> None:
        ctl = self.ctl
        exp, src = ctl.experiment, ctl.source
        self.r_exp.set(exp.experiment_id if exp else "NONE",
                       f"workspace: {ctl.workspace.root}" if exp else "Open an image, then press START EXPERIMENT", state="PRESENT" if exp else "ABSENT")
        if src:
            i = src.analysis.info
            self.r_res.set(f"{i.width} x {i.height}", f"{i.pixel_count / 1e6:.2f} MP | {i.mode} | {i.format} | {i.filename}", "PRESENT")
            c2 = src.analysis.c2pa
            sig = src.analysis.signal.state if src.analysis.signal else "UNKNOWN"
            self.r_prov.set(c2.state, f"binding {c2.hard_binding} | AI-content signal {sig}")
        else:
            self.r_res.set("-", "no image loaded", "ABSENT")
            self.r_prov.set("-", "", "ABSENT")
        done = ctl.completed()
        if done:
            t = done[-1]
            self.r_pix.set((t.pixel_metrics or {}).get("verdict", "-"), f"{t.transformation_id} {t.label}")
        else:
            self.r_pix.set("NO TRANSFORMATION", "baseline only", "ABSENT")
        sid = (exp.synthid_baseline or {}).get("state") if exp else None
        st = ctl.synthid.status()
        self.r_sid.set(sid or ("AVAILABLE" if st["available"] else "UNAVAILABLE"),
                       st["detail"] if not st["available"] else "local engine configured")
        rows = ctl.engine_status()
        ready = sum(1 for r in rows if r[1] in ("READY", "AVAILABLE", "ACTIVE"))
        self.r_eng.set(f"{ready}/{len(rows)} ready", "optional engines may be unavailable", "READY")
        self.engines.set_data(["Engine", "State", "Detail"], [list(r) for r in rows])
        rec = ctl.workspace.recent(30)
        self.recent.set_data(["Experiment ID", "Input", "Created (UTC)", "Transformations", "Signal"],
                             [[r["experiment_id"], r["input_name"], r["created"][:19], r["transformations"], r["signal"]] for r in rec])
        self.b_start.setEnabled(src is not None and exp is None)
