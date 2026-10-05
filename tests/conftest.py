import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SYNTHPROVENANCE_HOME"] = tempfile.mkdtemp(prefix="sp_tests_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.core import synthetic  # noqa: E402


@pytest.fixture(scope="session")
def fx():
    return synthetic.all_fixtures()


@pytest.fixture()
def lab(tmp_path, fx):
    """Workspace + audit + service + source context for the AI/C2PA JPEG fixture."""
    from app.analyzers.synthid_analyzer import analyze_synthid
    from app.core.audit_engine import AuditLog
    from app.core.experiment_engine import Workspace
    from app.core.metadata_engine import analyze_bytes
    from app.core.synthid_engine import SynthIDEngine
    from app.services.transformation_service import SourceContext, TransformationService

    def make(name="fixture_ai_c2pa.jpg", data=None):
        data = data if data is not None else fx[name]
        ws, audit, eng = Workspace(tmp_path / "ws"), AuditLog(), SynthIDEngine()
        a = analyze_bytes(data, "", name)
        ad = a.to_dict()
        exp = ws.create(name, data, baseline=ad)
        audit.bind(exp.experiment_id, ws.audit_path(exp))
        sid = analyze_synthid(eng, ws.original_file(exp), "ORIGINAL", ad).to_dict()
        exp.synthid_baseline = sid
        svc = TransformationService(ws, audit, eng)
        return {"ws": ws, "audit": audit, "exp": exp, "svc": svc, "src": SourceContext(ws.original_file(exp), a, ad, sid),
                "engine": eng}
    return make
