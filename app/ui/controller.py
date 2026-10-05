"""Application controller: state, background jobs, and service orchestration.

All heavy work (loading, hashing, parsing, C2PA, SynthID, conversion, pixel
comparison, reports) runs in QThreadPool workers. Only one experimental
operation runs at a time so that experiment records stay strictly ordered.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from app.analyzers.synthid_analyzer import analyze_synthid
from app.core import audit_engine as A
from app.core import image_metrics
from app.core.audit_engine import AuditLog
from app.core.experiment_engine import Workspace
from app.core.cross_detector_lab import CrossDetectorLab, ExternalDetectorGate, XD_PolicyError
from app.core.fingerprint_lab import FingerprintLab
from app.core.image_loader import open_image_bytes, set_max_megapixels, to_array
from app.core.image_metrics import compute_statistics, strip_arrays
from app.core.metadata_engine import analyze_file
from app.core import synthid_source_manager
from app.core.synthid_benchmark import load_dataset
from app.core.synthid_detector_registry import MethodRegistry
from app.core.synthid_engine import SynthIDEngine
from app.core.synthid_local_verifier import LocalVerifier
from app.core.synthid_online import OnlineGate, OnlinePolicyError
from app.core.synthid_research_engine import ResearchStore
from app.core.transform_engine import OPERATIONS
from app.models.experiment import ExternalClassification, utc_now
from app.services.export_service import export_bundle
from app.services.provenance_service import c2pa_manifest_export, run_external_c2pa_validation
from app.services.report_service import write_all
from app.services.transformation_service import SourceContext, TransformationService
from app.ui.widgets.worker import Worker
from app.utils import netguard
from app.utils.config import Settings
from app.utils.serialization import write_json
from app.utils.system import ToolStatus, c2pa_python_status, find_c2patool, find_exiftool


def _safe_has(registry, key) -> bool:
    try:
        registry.get(key)
        return True
    except Exception:  # noqa: BLE001
        return False


class AppController(QObject):
    sourceChanged = Signal()
    experimentChanged = Signal()
    recordsChanged = Signal()
    statisticsChanged = Signal()
    selectionChanged = Signal(str)
    busyChanged = Signal(bool, str)
    progress = Signal(int, str)
    auditEvent = Signal(object)
    error = Signal(str, str)
    info = Signal(str)
    toolsChanged = Signal()
    researchChanged = Signal()
    fingerprintChanged = Signal()
    easyChanged = Signal()
    crossDetectorChanged = Signal()

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self.audit = AuditLog()
        self.audit.subscribe(self.auditEvent.emit)
        self.pool = QThreadPool.globalInstance()
        self.source: SourceContext | None = None
        self.experiment = None
        self.statistics: dict = {}
        self.selected_tid = ""
        self.busy = False
        self.operation = ""
        self._jobs: set = set()
        self._images: dict[str, object] = {}
        self._arrays: dict[str, object] = {}
        self.workspace = Workspace(self.settings.workspace_root())
        self.last_research_run = None
        self.last_fp_run = None
        self.last_composer = None
        self.last_easy = None
        self.last_external = None
        self.last_xd_run = None
        self.xd_gate = ExternalDetectorGate(opener=lambda url: QDesktopServices.openUrl(QUrl(url)),
                                            reveal=lambda p: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent))))
        self.last_benchmark: dict | None = None
        self.online_pending: dict | None = None
        self.online = OnlineGate(opener=lambda url: QDesktopServices.openUrl(QUrl(url)),
                                 reveal=lambda p: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent))))
        self.apply_settings()

    # ------------------------------------------------------------ settings
    def apply_settings(self) -> None:
        set_max_megapixels(float(self.settings.get("max_megapixels") or 0))
        image_metrics.MAX_ANALYSIS_PIXELS = int(self.settings.get("statistics_max_pixels") or 16_000_000)
        s = self.settings
        self.exiftool = find_exiftool(s.get("exiftool_path") or None) if s.get("use_exiftool") else \
            ToolStatus("ExifTool", False, detail="disabled in Settings")
        self.c2patool = find_c2patool(s.get("c2patool_path") or None)
        self.c2pa_python = c2pa_python_status() if s.get("use_c2pa_python") else \
            ToolStatus("c2pa-python", False, detail="disabled in Settings")
        self.synthid = SynthIDEngine.discover(s.get("synthid_engine_command") or None)
        self.verifier = LocalVerifier(self.synthid)
        self.registry = MethodRegistry(self.synthid.status(), self.last_benchmark)
        self.research = ResearchStore(self.workspace.root / "synthid_research")
        self.lab = FingerprintLab(self.workspace.root / "fingerprint_research")
        self.cross_lab = CrossDetectorLab(self.workspace.root / "cross_detector")
        from app.core.research_assistant import ResearchAssistant
        from app.core.unified_signal_decomposition import UnifiedSignalDecomposition

        self.assistant = ResearchAssistant(self.lab.registry)
        self.decomposer = UnifiedSignalDecomposition(self.lab.registry)
        self.sources, self.source_problems = synthid_source_manager.discover(self.workspace.root)
        self.service = TransformationService(self.workspace, self.audit, self.synthid,
                                             self.exiftool.path if self.exiftool.available else None)
        self.toolsChanged.emit()

    def set_workspace(self, path: str) -> None:
        self.settings.set("workspace", path)
        self.settings.save()
        self.workspace = Workspace(self.settings.workspace_root())
        self.experiment = None
        self.audit.bind("-", None)
        self.apply_settings()
        self.experimentChanged.emit()
        self.recordsChanged.emit()
        self.info.emit(f"Workspace: {self.workspace.root}")

    def engine_status(self) -> list[tuple[str, str, str]]:
        from app.core.hashing import BLAKE3_AVAILABLE

        rows = [("Container parsers (JPEG / PNG / WebP)", "READY", "native, byte-level"),
                ("EXIF / XMP / IPTC / ICC analyzers", "READY", "native"),
                ("C2PA manifest parser (JUMBF / CBOR)", "READY", "native; hard binding recomputed; signatures not validated"),
                ("SHA-256", "READY", "hashlib"),
                ("BLAKE3", "READY" if BLAKE3_AVAILABLE else "UNAVAILABLE", "blake3 module")]
        for t in (self.exiftool, self.c2patool, self.c2pa_python):
            rows.append((t.name, "AVAILABLE" if t.available else "UNAVAILABLE", t.version or t.detail))
        st = self.synthid.status()
        rows.append(("SynthID local verification engine", "AVAILABLE" if st["available"] else "UNAVAILABLE", st["detail"]))
        rows.append(("Network policy", "ACTIVE" if netguard.installed() else "NOT INSTALLED", "LOCAL-ONLY; outbound network blocked"))
        return rows

    # ------------------------------------------------------------ jobs
    def _run(self, name: str, fn, on_done, *args) -> bool:
        if self.busy:
            self.error.emit("Operation in progress", f"'{self.operation}' is still running. Please wait for it to finish.")
            return False
        self.busy, self.operation = True, name
        self.busyChanged.emit(True, name)
        w = Worker(fn, *args)
        self._jobs.add(w.signals)

        def finish(sig=w.signals):
            self.busy, self.operation = False, ""
            self._jobs.discard(sig)
            self.busyChanged.emit(False, "")

        def ok(result):
            finish()
            try:
                on_done(result)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(name, f"{type(exc).__name__}: {exc}")

        def bad(msg):
            finish()
            self.audit.log(A.ERROR, "ERROR", f"{name}: {msg}")
            self.error.emit(name, msg)

        w.signals.done.connect(ok)
        w.signals.failed.connect(bad)
        w.signals.progress.connect(self.progress.emit)
        self.pool.start(w)
        return True

    # ------------------------------------------------------------ loading
    def open_image(self, path: str) -> bool:
        return self._run("Loading and analysing image", self._job_open, self._on_opened, str(path))

    def _job_open(self, path: str, progress):
        progress(5, "Reading and validating file")
        an = analyze_file(path, self.exiftool.path if self.exiftool.available else None)
        progress(80, "C2PA validation engines")
        run_external_c2pa_validation(an, Path(an.info.path), self.c2patool.path if self.c2patool.available else None,
                                     bool(self.settings.get("use_c2pa_python")) and self.c2pa_python.available)
        progress(100, "Analysis complete")
        return an

    def _on_opened(self, an) -> None:
        self.source = SourceContext(Path(an.info.path), an, an.to_dict(), {})
        self.experiment, self.statistics, self.selected_tid = None, {}, ""
        self._images, self._arrays = {"ORIGINAL": an.image}, {}
        self.audit.bind("-", None)
        self.audit.log(A.IMAGE_LOADED, detail=f"{an.info.filename} {an.info.format} {an.info.width}x{an.info.height} "
                                             f"sha256 {an.hashes['sha256']}")
        self.sourceChanged.emit()
        self.experimentChanged.emit()
        self.recordsChanged.emit()
        self.statisticsChanged.emit()

    def open_demo_fixture(self) -> bool:
        from app.core.synthetic import make_jpeg

        path = self.workspace.cache_dir / "SYNTHETIC_TEST_FIXTURE_ai_c2pa.jpg"
        path.write_bytes(make_jpeg(size=(640, 427)))
        return self.open_image(str(path))

    # ------------------------------------------------------------ experiment
    def start_experiment(self) -> bool:
        if self.source is None:
            self.error.emit("No image", "Open an image first.")
            return False
        return self._run("Starting experiment", self._job_start, self._on_started)

    def _job_start(self, progress):
        src = self.source
        an = src.analysis
        progress(5, "Creating experiment workspace (original preserved untouched)")
        exp = self.workspace.create(an.info.filename, src.data, baseline=src.analysis_dict)
        self.audit.bind(exp.experiment_id, self.workspace.audit_path(exp), carry_unbound=True)
        self.audit.log(A.EXPERIMENT_STARTED, detail=f"{exp.experiment_id} input {an.info.filename} sha256 {an.hashes['sha256']}")
        self.audit.log(A.BASELINE_COMPLETE, detail=f"{an.info.format} {an.info.width}x{an.info.height} {an.info.mode}; "
                                                   f"pixel sha256 {an.hashes.get('pixel_sha256', '')}")
        self.audit.log(A.C2PA_COMPLETE, detail=f"{an.c2pa.state}: {an.c2pa.summary} binding {an.c2pa.hard_binding}")
        progress(30, "SynthID embedded-signal layer")
        sid = analyze_synthid(self.synthid, self.workspace.original_file(exp), "ORIGINAL", src.analysis_dict).to_dict()
        self.audit.log(A.SYNTHID_COMPLETE, detail=f"{sid['state']}: {sid.get('detail', '')}")
        self.audit.log(A.METADATA_COMPLETE, detail=", ".join(f"{k}:{g.state.value}" for k, g in an.groups.items()))
        progress(55, "Forensic statistics")
        quant = an.compression.get("quantization_tables") if isinstance(an.compression, dict) else None
        stats = compute_statistics(an.image, {"tables": quant} if quant else None)
        self.audit.log(A.STATISTICS_COMPLETE, detail=f"entropy {stats.get('entropy_bits', 0):.3f} bits")
        exp.synthid_baseline = sid
        exp.statistics = strip_arrays(stats)
        self.workspace.save(exp)
        src.synthid = sid
        progress(100, "Experiment ready")
        return exp, stats

    def _on_started(self, result) -> None:
        self.experiment, self.statistics = result
        self.experimentChanged.emit()
        self.statisticsChanged.emit()
        self.recordsChanged.emit()
        self.info.emit(f"Experiment {self.experiment.experiment_id} started")

    def load_experiment(self, experiment_id: str) -> bool:
        return self._run(f"Loading {experiment_id}", self._job_load, self._on_loaded, experiment_id)

    def _job_load(self, experiment_id: str, progress):
        exp = self.workspace.load(experiment_id)
        progress(20, "Re-analysing preserved original")
        an = analyze_file(self.workspace.original_file(exp), self.exiftool.path if self.exiftool.available else None)
        progress(70, "Forensic statistics")
        stats = compute_statistics(an.image)
        return exp, an, stats

    def _on_loaded(self, result) -> None:
        exp, an, stats = result
        self.source = SourceContext(Path(an.info.path), an, an.to_dict(), dict(exp.synthid_baseline or {}))
        self.experiment, self.statistics = exp, stats
        self._images, self._arrays = {"ORIGINAL": an.image}, {}
        self.audit.bind(exp.experiment_id, self.workspace.audit_path(exp), load_existing=True)
        self.audit.log(A.EXPERIMENT_LOADED, detail=exp.experiment_id)
        done = [t for t in exp.transformations if t.status == "COMPLETE"]
        self.selected_tid = done[-1].transformation_id if done else ""
        for sig in (self.sourceChanged, self.experimentChanged, self.recordsChanged, self.statisticsChanged):
            sig.emit()
        self.selectionChanged.emit(self.selected_tid)

    # ------------------------------------------------------------ transformations
    def run_transformation(self, op: str, params: dict | None = None) -> bool:
        if self.source is None:
            self.error.emit("No image", "Open an image first.")
            return False
        return self._run(OPERATIONS[op].label, self._job_transform, self._on_records, op, dict(params or {}))

    def run_matrix(self, sanitize_params: dict | None = None) -> bool:
        if self.source is None:
            self.error.emit("No image", "Open an image first.")
            return False
        return self._run("Experiment matrix battery", self._job_matrix, self._on_records, dict(sanitize_params or {}))

    def _ensure_exp(self, progress):
        if self.experiment is not None:
            return None, self.experiment
        started = self._job_start(progress)
        return started, started[0]

    def _job_transform(self, op, params, progress):
        started, exp = self._ensure_exp(progress)
        return started, [self.service.run(exp, self.source, op, params, progress)]

    def _job_matrix(self, sanitize_params, progress):
        started, exp = self._ensure_exp(progress)
        if not sanitize_params:
            sanitize_params = {"mode": "METADATA-ONLY", "profile": self.settings.get("default_sanitize_profile") or "BALANCED"}
        return started, self.service.run_battery(exp, self.source, sanitize_params, progress)

    def _on_records(self, result) -> None:
        started, recs = result[0], result[1]
        if started:
            self._on_started(started)
        if recs:
            last_ok = [r for r in recs if r.status == "COMPLETE"]
            if last_ok:
                self.selected_tid = last_ok[-1].transformation_id
        self.recordsChanged.emit()
        self.selectionChanged.emit(self.selected_tid)
        bad = [r for r in recs if r.status != "COMPLETE"]
        if bad:
            self.error.emit("Transformation not completed", "\n".join(f"{r.transformation_id} {r.label}: {r.status}\n{r.error}"
                                                                     for r in bad))
        if len(result) > 2 and result[2]:
            self.info.emit(result[2])

    def save_as(self, source_tid: str, fmt: str, compression: str, quality: int, keep_icc: bool, carry: bool, dest: str) -> bool:
        params = {"format": fmt, "compression": compression, "quality": quality, "keep_icc": keep_icc,
                  "carry_metadata": carry, "source": source_tid or "ORIGINAL"}
        return self._run(f"Save As {fmt}", self._job_save_as, self._on_records, params, dest)

    def _job_save_as(self, params, dest, progress):
        started, exp = self._ensure_exp(progress)
        rec = self.service.run(exp, self.source, "format_conversion", params, progress)
        msg = ""
        if rec.status == "COMPLETE" and dest:
            shutil.copyfile(self.workspace.resolve(exp, rec.output_path), dest)
            self.audit.log(A.FILE_EXPORTED, detail=f"{rec.transformation_id} -> {Path(dest).name} "
                                                   f"({(rec.pixel_metrics or {}).get('verdict')})")
            msg = f"Saved {Path(dest).name}: {(rec.pixel_metrics or {}).get('verdict')}"
        return started, [rec], msg

    def compare_external(self, path: str) -> bool:
        return self.run_transformation("external_comparison", {"path": path})

    # ------------------------------------------------------------ records / images
    def records(self) -> list:
        return list(self.experiment.transformations) if self.experiment else []

    def completed(self) -> list:
        return [t for t in self.records() if t.status == "COMPLETE"]

    def record(self, tid: str):
        return next((t for t in self.records() if t.transformation_id == tid), None)

    def select(self, tid: str) -> None:
        if tid != self.selected_tid:
            self.selected_tid = tid
            self.selectionChanged.emit(tid)

    def image_for(self, tid: str):
        tid = tid or "ORIGINAL"
        if tid in self._images:
            return self._images[tid]
        rec = self.record(tid)
        if rec is None or rec.status != "COMPLETE" or self.experiment is None:
            return None
        img = open_image_bytes(self.workspace.resolve(self.experiment, rec.output_path).read_bytes())
        if len(self._images) > 4:
            for k in [k for k in self._images if k != "ORIGINAL"][:2]:
                self._images.pop(k, None)
        self._images[tid] = img
        return img

    def array_for(self, tid: str):
        tid = tid or "ORIGINAL"
        if tid not in self._arrays:
            img = self.image_for(tid)
            if img is None:
                return None
            if len(self._arrays) > 3:
                self._arrays.pop(next(iter(self._arrays)))
            self._arrays[tid] = to_array(img)
        return self._arrays[tid]

    # ------------------------------------------------------------ records by the researcher
    def record_external(self, layer: str, platform: str, label_: str, condition: str, note: str) -> None:
        if self.experiment is None:
            self.error.emit("No experiment", "Start an experiment first.")
            return
        tier = ("EXTERNAL SYNTHID VERIFICATION (user-recorded, unverified)" if layer == "SYNTHID"
                else "EXTERNAL PLATFORM CLASSIFICATION (user-recorded, unverified)")
        e = ExternalClassification(platform=platform.strip()[:120], label=label_.strip()[:200], observed_on=utc_now(),
                                   note=note.strip()[:1000], layer=layer, condition=condition, tier=tier)
        self.experiment.external_classifications.append(e)
        self.workspace.save(self.experiment)
        self.audit.log(A.EXTERNAL_CLASSIFICATION, detail=f"{layer} {condition}: {e.platform} = {e.label} (user-recorded)")
        self.experimentChanged.emit()

    def update_notes(self, objective: str, notes: str) -> None:
        if self.experiment is None:
            return
        self.experiment.objective, self.experiment.notes = objective.strip(), notes.strip()
        self.workspace.save(self.experiment)
        self.info.emit("Research objective and notes saved")

    # ------------------------------------------------------------ export
    def export_report(self, fmt: str, dest: str) -> bool:
        if self.experiment is None:
            self.error.emit("No experiment", "Start an experiment first.")
            return False
        return self._run(f"Generating {fmt.upper()} report", self._job_report, lambda m: self.info.emit(m), fmt, dest)

    def _job_report(self, fmt, dest, progress):
        progress(20, "Assembling report")
        paths = write_all(self.experiment, self.workspace.subdir(self.experiment, "report"), self.audit.events(),
                          self.synthid.status(), formats=(fmt,))
        shutil.copyfile(paths[fmt], dest)
        self.audit.log(A.REPORT_GENERATED, detail=f"{fmt.upper()} -> {Path(dest).name}")
        return f"Report saved: {dest}"

    def export_bundle(self, dest: str) -> bool:
        if self.experiment is None:
            self.error.emit("No experiment", "Start an experiment first.")
            return False
        return self._run("Exporting experiment.zip", self._job_bundle, lambda m: self.info.emit(m), dest)

    def _job_bundle(self, dest, progress):
        progress(20, "Writing reports and bundle")
        p = export_bundle(self.experiment, self.workspace, self.audit, Path(dest), self.synthid.status())
        return f"Experiment bundle saved: {p}"

    def export_manifest_json(self, dest: str) -> None:
        if self.source is None:
            return
        write_json(Path(dest), c2pa_manifest_export(self.source.analysis_dict))
        self.audit.log(A.FILE_EXPORTED, detail=f"C2PA manifest JSON -> {Path(dest).name}")
        self.info.emit(f"Manifest JSON saved: {dest}")

    def rerun_synthid(self) -> bool:
        if self.experiment is None:
            self.error.emit("No experiment", "Start an experiment first.")
            return False
        return self._run("SynthID analysis", self._job_synthid, lambda _r: self.experimentChanged.emit())

    def _job_synthid(self, progress):
        sid = analyze_synthid(self.synthid, self.workspace.original_file(self.experiment), "ORIGINAL",
                              self.source.analysis_dict).to_dict()
        self.experiment.synthid_baseline = sid
        self.source.synthid = sid
        self.workspace.save(self.experiment)
        self.audit.log(A.SYNTHID_COMPLETE, detail=f"{sid['state']}: {sid.get('detail', '')}")
        return sid

    # ------------------------------------------------------------ SynthID Research Lab
    def research_image(self) -> Path | None:
        """The image the lab works on: the experiment's preserved original, else the opened file."""
        if self.experiment is not None:
            return self.workspace.original_file(self.experiment)
        return Path(self.source.path) if self.source is not None else None

    def run_synthid_detection(self, paths: list[str] | None = None) -> bool:
        img = self.research_image()
        targets = [Path(p) for p in paths] if paths else ([img] if img else [])
        if not targets:
            self.error.emit("No image", "Open an image (or choose files) first.")
            return False
        return self._run("SynthID research detection", self._job_sid_detect, self._on_research, targets)

    def _job_sid_detect(self, targets, progress):
        run = self.research.run_detection(targets, self.verifier, self.registry, progress)
        if self.experiment is not None:
            self.research.import_conditions(run, self.experiment)
        self.audit.log(A.SYNTHID_RESEARCH_RUN, detail=f"{run.run_id} DETECTION {run.status}; original unchanged "
                                                      f"{run.original_unchanged}")
        return run

    def run_synthid_benchmark(self, folder: str, threshold: float = 0.5, seed: int = 20261002) -> bool:
        try:
            items = load_dataset(Path(folder))
        except ValueError as exc:
            self.error.emit("Benchmark dataset", str(exc))
            return False
        return self._run("SynthID detection benchmark", self._job_sid_bench, self._on_research, items, threshold, seed)

    def _job_sid_bench(self, items, threshold, seed, progress):
        run = self.research.run_benchmark(items, self.verifier, self.registry, threshold, seed, progress)
        if run.status == "COMPLETE":
            m = run.benchmark.get("metrics") or {}
            auc = m.get("auc")
            self.last_benchmark = {"status": "COMPLETE", "run_id": run.run_id, "n_scored": run.benchmark.get("n_scored"),
                                   "auc_text": f"{auc:.3f}" if auc is not None else "-"}
            self.registry.update_engine(self.synthid.status(), self.last_benchmark)
        self.audit.log(A.SYNTHID_RESEARCH_RUN, detail=f"{run.run_id} BENCHMARK {run.status}: {run.detail[:200]}")
        return run

    def _on_research(self, run) -> None:
        self.last_research_run = run
        self.researchChanged.emit()
        self.info.emit(f"{run.run_id}: {run.status}")

    def export_synthid_paper(self, run_id: str, dest: str) -> bool:
        return self._run("Export for paper", self._job_sid_paper, lambda m: self.info.emit(m), run_id, dest)

    def _job_sid_paper(self, run_id, dest, progress):
        from app.services.synthid_paper_export import export_paper_zip

        progress(20, "Writing CSV / JSON / PDF / PNG and ZIP")
        run = self.research.load(run_id)
        p = export_paper_zip(self.research, run, Path(dest))
        self.audit.log(A.SYNTHID_PAPER_EXPORTED, detail=f"{run_id} -> {p.name}")
        return f"Paper export saved: {p}"

    def set_online_mode(self, enabled: bool, confirmed: bool = False) -> None:
        if enabled:
            self.online.enable(confirmed)
        else:
            self.online.disable()
            self.online_pending = None
        self.audit.log(A.ONLINE_MODE_CHANGED, detail="ONLINE OFFICIAL VERIFICATION enabled by explicit confirmation"
                       if enabled else "LOCAL MODE (online verification OFF)")
        self.researchChanged.emit()

    def online_plan(self, dest_id: str):
        img = self.research_image()
        if img is None:
            raise OnlinePolicyError("Open an image first.")
        return self.online.plan(dest_id, img)

    def online_open(self, plan, consent: bool) -> dict:
        entry = self.online.execute(plan, consent)
        self.online_pending = entry
        self.audit.log(A.ONLINE_VERIFIER_OPENED, detail=f"{plan.name} {plan.url} file {plan.image_name} "
                                                        f"sha256 {plan.image_sha256}")
        self.researchChanged.emit()
        return entry

    def record_online_result(self, service: str, reported: str, note: str) -> bool:
        if not self.online_pending:
            self.error.emit("Online verification", "Open an image in an official verifier first (explicit confirmation).")
            return False
        run = self.research.record_online(self.online_pending, reported.strip(), service.strip(), note.strip(), self.registry)
        if self.experiment is not None:
            self.record_external("SYNTHID", service or self.online_pending.get("name", ""), reported, "ORIGINAL",
                                 f"{run.run_id}; {note}")
        self.audit.log(A.SYNTHID_RESEARCH_RUN, detail=f"{run.run_id} ONLINE result recorded by researcher: {reported[:120]}")
        self._on_research(run)
        return True

    def revalidate_sources(self) -> None:
        self.sources, self.source_problems = synthid_source_manager.discover(self.workspace.root)
        self.researchChanged.emit()

    # ------------------------------------------------------------ Fingerprint Research Lab
    def run_fingerprint_method(self, method_key: str, params: dict | None = None, surrogate: dict | None = None,
                               references: list[str] | None = None) -> bool:
        img = self.research_image()
        if img is None:
            self.error.emit("No image", "Open an image first.")
            return False
        from app.research.surrogate import SurrogateConfig
        cfg = SurrogateConfig.from_dict(surrogate) if surrogate else None
        refs = [Path(p) for p in (references or [])]
        reg = self.lab.registry
        name = reg.get(method_key).name if _safe_has(reg, method_key) else method_key
        return self._run(f"Fingerprint method: {name}", self._job_fp_method, self._on_fp, method_key, img,
                         dict(params or {}), cfg, refs)

    def _job_fp_method(self, method_key, img, params, cfg, refs, progress):
        prior = [r.to_dict() if hasattr(r, "to_dict") else r for r in self._fp_runs_for_meta()]
        run = self.lab.run_method(method_key, [img], params, cfg, refs, progress)
        self.audit.log(A.SYNTHID_RESEARCH_RUN if False else A.FINGERPRINT_RUN,
                       detail=f"{run.run_id} {run.method_id} {run.status}; original unchanged {run.original_unchanged}")
        return run

    def _fp_runs_for_meta(self):
        try:
            return [self.lab.load(r["run_id"]) for r in self.lab.list_runs(limit=25)]
        except Exception:  # noqa: BLE001
            return []

    def _on_fp(self, run) -> None:
        self.last_fp_run = run
        self.fingerprintChanged.emit()
        self.info.emit(f"{run.run_id}: {run.status}")

    def embed_surrogate(self, surrogate: dict, dest: str) -> bool:
        img = self.research_image()
        if img is None:
            self.error.emit("No image", "Open an image first.")
            return False
        from app.research.surrogate import SurrogateConfig
        return self._run("Embed surrogate watermark", self._job_embed, lambda r: self._on_embed(r),
                         img, SurrogateConfig.from_dict(surrogate), dest)

    def _job_embed(self, img, cfg, dest, progress):
        progress(30, "Embedding keyed surrogate signal on a copy")
        rec = self.lab.embed_surrogate(img, cfg, Path(dest))
        self.audit.log(A.FINGERPRINT_RUN, detail=f"SURROGATE EMBED {cfg.family} key {cfg.key} -> {Path(dest).name} "
                                                 f"(valid ground truth {rec['valid_ground_truth']})")
        return rec

    def _on_embed(self, rec) -> None:
        self.info.emit(f"Surrogate embedded: {Path(rec['watermarked_file']).name} "
                       f"(ground truth {'valid' if rec['valid_ground_truth'] else 'INVALID'})")
        self.fingerprintChanged.emit()

    def run_composer(self, nodes: list, name: str = "pipeline", surrogate: dict | None = None) -> bool:
        img = self.research_image()
        if img is None:
            self.error.emit("No image", "Open an image first.")
            return False
        from app.research.surrogate import SurrogateConfig
        cfg = SurrogateConfig.from_dict(surrogate) if surrogate else None
        return self._run("Method composer pipeline", self._job_composer, self._on_composer, img, list(nodes), name, cfg)

    def _job_composer(self, img, nodes, name, cfg, progress):
        from app.core.method_composer import Pipeline, run_pipeline
        from app.core.image_loader import open_image_bytes
        from app.research.imaging import as_float, luminance
        from app.research import surrogate as SUR
        progress(20, "Running pipeline")
        base = as_float(open_image_bytes(Path(img).read_bytes()))
        known = None
        image = base
        if cfg is not None:
            emb = SUR.embed(base, cfg)
            image = emb.watermarked
            known = luminance(emb.watermarked) - luminance(base)
        res = run_pipeline(image, Pipeline(name=name, nodes=nodes), known)
        self.audit.log(A.FINGERPRINT_RUN, detail=f"COMPOSER {name} {len(res.stages)} stages {res.status}")
        self.last_composer = res
        return res

    def _on_composer(self, res) -> None:
        self.last_composer = res
        self.fingerprintChanged.emit()
        self.info.emit(f"Pipeline '{res.pipeline.get('name')}': {len(res.stages)} stages {res.status}")

    def advise(self, goal: str, has_ground_truth: bool = False, n_references: int = 0):
        info = {}
        if self.source is not None:
            a = self.source.analysis.info
            info = {"format": a.format, "width": a.width, "height": a.height}
        return self.assistant.advise(goal, info, has_ground_truth, n_references,
                                     {"synthid": self.synthid.status().get("available")})

    def discover_experiments(self, has_ground_truth: bool = False, n_references: int = 0):
        return self.assistant.discover(None, has_ground_truth, n_references)

    def export_fingerprint_paper(self, run_id: str, dest: str) -> bool:
        return self._run("Export fingerprint run for paper", self._job_fp_paper, lambda m: self.info.emit(m), run_id, dest)

    def _job_fp_paper(self, run_id, dest, progress):
        from app.services.fingerprint_paper_export import export_fingerprint_zip

        progress(20, "Writing CSV / JSON / PDF / maps and ZIP")
        run = self.lab.load(run_id)
        p = export_fingerprint_zip(self.lab, run, Path(dest))
        self.audit.log(A.FINGERPRINT_PAPER_EXPORTED, detail=f"{run_id} -> {p.name}")
        return f"Fingerprint paper export saved: {p}"

    # ------------------------------------------------------------ Easy Mode
    def easy_orchestrator(self):
        """The Easy Mode orchestrator over this controller's engines (same workspace, audit, tools, registry)."""
        from app.core.easy_mode_orchestrator import EasyModeOrchestrator

        return EasyModeOrchestrator(self.workspace, self.audit, self.synthid, self.service,
                                    exiftool_path=self.exiftool.path if self.exiftool.available else None,
                                    c2patool_path=self.c2patool.path if self.c2patool.available else None,
                                    use_c2pa_python=bool(self.settings.get("use_c2pa_python")) and self.c2pa_python.available,
                                    registry=self.lab.registry, max_file_mb=float(self.settings.get("max_file_mb") or 4096))

    def run_easy(self, request) -> bool:
        return self._run("Easy Mode research pipeline", self._job_easy, self._on_easy, request)

    def _job_easy(self, request, progress):
        return self.easy_orchestrator().run(request, progress)

    def _on_easy(self, res) -> None:
        self.last_easy = res
        self.easyChanged.emit()

    def save_easy_result(self, dest: str):
        from app.core.easy_mode_orchestrator import save_result

        return save_result(self.last_easy, dest, self.audit)

    # ------------------------------------------------------------ Cross-Detector Research Lab
    def import_external_result(self, blob=None, fields=None, markdown=None, csv=None,
                               detector: str = "TruthScan") -> bool:
        from app.research.cross_detector import ExternalResult
        try:
            if blob is not None:
                self.last_external = ExternalResult.from_json(blob, detector)
            elif markdown is not None:
                self.last_external = ExternalResult.from_markdown(markdown, detector)
            elif csv is not None:
                self.last_external = ExternalResult.from_csv(csv, detector)
            else:
                self.last_external = ExternalResult.from_fields(detector=detector, **(fields or {}))
        except Exception as exc:  # noqa: BLE001
            self.error.emit("Import external result", f"{type(exc).__name__}: {exc}")
            return False
        self.audit.log(A.EXTERNAL_CLASSIFICATION, detail=f"Imported {self.last_external.detector} result "
                       f"'{self.last_external.final_result}' (USER-SUPPLIED)")
        self.crossDetectorChanged.emit()
        self.info.emit(f"Imported {self.last_external.detector} result (USER-SUPPLIED).")
        return True

    def run_cross_detector(self, ground_truth_level: int = 0, ground_truth_direction: str = "UNKNOWN",
                           heatmap_path: str | None = None) -> bool:
        img = self.research_image()
        if img is None:
            self.error.emit("No image", "Open an image first.")
            return False
        return self._run("Cross-detector research study", self._job_cross, self._on_cross, img,
                         int(ground_truth_level), ground_truth_direction, heatmap_path)

    def _job_cross(self, img, gt_level, gt_dir, heatmap_path, progress):
        from app.core.easy_mode_orchestrator import EasyModeRequest
        progress(5, "Running local research pipeline")
        fmt = self.settings.get("easy_output_format") or "PNG"
        res = self.easy_orchestrator().run(EasyModeRequest(str(img), fmt, save_report=False),
                                           lambda p, _t: progress(5 + int(p * 0.8), "Local analysis"))
        progress(90, "Comparing evidence")
        local_maps = self._cross_local_maps(res)
        run = self.cross_lab.record_study(img, res.to_dict(), self.last_external, gt_level, gt_dir,
                                          Path(heatmap_path) if heatmap_path else None, local_maps)
        self.audit.log(A.FINGERPRINT_RUN, detail=f"{run.run_id} CROSS-DETECTOR {run.outcome}; original unchanged "
                       f"{run.original_unchanged}")
        return run

    def _cross_local_maps(self, easy_res) -> dict:
        # reuse the figures the Easy run already wrote (FFT, residual, candidate) as local maps for heatmap overlap
        maps = {}
        try:
            from app.core.image_loader import open_image_bytes
            from app.research.imaging import as_float
            for fig in (easy_res.figures or []):
                pth = Path(fig.get("path", ""))
                if pth.is_file():
                    key = Path(fig["file"]).stem.split("_", 1)[-1]
                    maps[key] = as_float(open_image_bytes(pth.read_bytes()))
        except Exception:  # noqa: BLE001
            pass
        return maps

    def _on_cross(self, run) -> None:
        self.last_xd_run = run
        self.crossDetectorChanged.emit()
        self.info.emit(f"{run.run_id}: {run.outcome}")

    def generate_hardcases(self, dest: str, n_each: int = 2) -> bool:
        return self._run("Hard-case benchmark generation", self._job_hardcases, self._on_hardcases, dest, int(n_each))

    def _job_hardcases(self, dest, n_each, progress):
        from app.research import hardcases
        progress(20, "Generating labelled benchmark")
        return dest, hardcases.generate(dest, n_each=n_each)

    def _on_hardcases(self, result) -> None:
        dest, cases = result
        self.info.emit(f"Generated {len(cases)} labelled hard-case images in {dest}")
        self.crossDetectorChanged.emit()

    def set_truthscan_mode(self, enabled: bool, confirmed: bool = False) -> None:
        try:
            if enabled:
                self.xd_gate.enable(confirmed)
            else:
                self.xd_gate.disable()
        except XD_PolicyError as exc:
            self.error.emit("TruthScan integration", str(exc))
            return
        self.audit.log(A.ONLINE_MODE_CHANGED, detail="TruthScan browser hand-off "
                       + ("ENABLED (no upload; browser only)" if enabled else "DISABLED"))
        self.crossDetectorChanged.emit()

    def truthscan_open(self, consent: bool) -> bool:
        img = self.research_image()
        if img is None:
            self.error.emit("No image", "Open an image first.")
            return False
        try:
            plan = self.xd_gate.plan(img)
            self.xd_gate.execute(plan, consent)
        except XD_PolicyError as exc:
            self.error.emit("TruthScan integration", str(exc))
            return False
        self.audit.log(A.ONLINE_VERIFIER_OPENED, detail=f"TruthScan opened in browser for {plan.image_name} "
                       f"sha256 {plan.image_sha256} (no upload by SynthProvenance)")
        self.info.emit("Opened TruthScan in your browser. Upload manually, then IMPORT the result.")
        self.crossDetectorChanged.emit()
        return True

    def export_cross_detector(self, run_id: str, dest: str) -> bool:
        return self._run("Export cross-detector report", self._job_cross_export, lambda m: self.info.emit(m),
                         run_id, dest)

    def _job_cross_export(self, run_id, dest, progress):
        from app.services.cross_detector_report import write_cross_detector_report
        progress(30, "Writing report")
        run = self.cross_lab.load(run_id)
        write_cross_detector_report(run, self.cross_lab.run_dir(run_id) / "report", copy_to=dest)
        self.audit.log(A.FINGERPRINT_PAPER_EXPORTED, detail=f"{run_id} cross-detector report -> {Path(dest).name}")
        return f"Cross-detector report exported: {dest}"

    # ------------------------------------------------------------ desktop
    @staticmethod
    def open_path(path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def experiment_dir(self):
        return self.workspace.experiment_dir(self.experiment.experiment_id) if self.experiment else None
