"""Verify a built SynthProvenance distribution (exe, resources, Qt plugins, self-test, GUI smoke test)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    dist = Path(a.dist).resolve()
    lines: list[str] = [f"SynthProvenance build verification {time.strftime('%Y-%m-%d %H:%M:%S')}", f"dist: {dist}"]
    ok = True

    def res(passed: bool, name: str, detail: str = "", warn: bool = False) -> None:
        nonlocal ok
        tag = "PASS" if passed else ("WARN" if warn else "FAIL")
        if not passed and not warn:
            ok = False
        line = f"{tag}  {name}" + (f": {detail}" if detail else "")
        lines.append(line)
        print(line, flush=True)

    exe = dist / ("SynthProvenance.exe" if os.name == "nt" else "SynthProvenance")
    res(exe.is_file() and exe.stat().st_size > 0, "executable exists", f"{exe.name} {exe.stat().st_size if exe.is_file() else 0:,} bytes")
    internal = dist / "_internal"
    res(internal.is_dir(), "_internal runtime folder present")
    plats = list(internal.rglob("platforms/*")) if internal.is_dir() else []
    names = {p.name.lower() for p in plats}
    needed = "qwindows.dll" if os.name == "nt" else "libqoffscreen.so"
    res(needed in names, "Qt platform plugin", ", ".join(sorted(names)) or "none")
    imgf = list(internal.rglob("imageformats/*")) if internal.is_dir() else []
    res(bool(imgf), "Qt image-format plugins", f"{len(imgf)} files", warn=True)
    for rel in ("assets/icon.png", "assets/templates/report.html", "config/default_config.json"):
        found = (internal / rel).is_file() or (dist / rel).is_file()
        res(found, f"resource {rel}")
    if not exe.is_file():
        Path(a.log).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="sp_verify_"))
    env = dict(os.environ)
    env["SYNTHPROVENANCE_HOME"] = str(tmp / "home")
    if os.name != "nt":
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    st_out = tmp / "selftest.json"
    t0 = time.time()
    try:
        p = subprocess.run([str(exe), "--self-test", "--self-test-output", str(st_out)], env=env, cwd=str(dist),
                           capture_output=True, timeout=600)
        rc = p.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        rc = -1
        lines.append(f"self-test launch error: {exc}")
    data = json.loads(st_out.read_text(encoding="utf-8")) if st_out.is_file() else {}
    for c in data.get("checks", []):
        lines.append(f"    self-test {c['name']}: {'ok' if c['passed'] else 'FAILED'} - {c['detail']}")
    res(rc == 0 and data.get("passed") is True, "self-test (imports, network guard, sample image load, C2PA, sanitize, "
        "pixel verification, 5 export formats, high resolution, reports, bundle, SynthID Research Lab)", f"exit {rc}, {time.time() - t0:.1f}s")
    sm_out = tmp / "smoke.json"
    t0 = time.time()
    try:
        p = subprocess.run([str(exe), "--smoke-gui", "--smoke-output", str(sm_out)], env=env, cwd=str(dist),
                           capture_output=True, timeout=300)
        rc = p.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        rc = -1
        lines.append(f"GUI smoke launch error: {exc}")
    sm = json.loads(sm_out.read_text(encoding="utf-8")) if sm_out.is_file() else {}
    lines.append(f"    smoke: {json.dumps(sm)[:1500]}")
    res(rc == 0 and sm.get("ok") is True, "GUI launches, runs an experiment and a SynthID Research run + paper export, renders all views, exits cleanly",
        f"exit {rc}, {time.time() - t0:.1f}s")
    lines.append("RESULT: " + ("VERIFIED" if ok else "FAILED"))
    Path(a.log).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
