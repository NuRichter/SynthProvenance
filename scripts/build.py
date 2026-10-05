"""SynthProvenance build stages 3-8 (cross-platform; invoked by build.bat / build.ps1).

    python scripts/build.py --root <project> [--skip-tests] [--from-stage N] [--to-stage N]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STAGES = {3: "Installing dependencies", 4: "Validating source", 5: "Running tests", 6: "Building executable",
          7: "Verifying executable", 8: "Preparing distribution"}


class StageError(Exception):
    def __init__(self, reason: str, remediation: str, log: str = "build\\build.log") -> None:
        super().__init__(reason)
        self.reason, self.remediation, self.log = reason, remediation, log


def say(msg: str) -> None:
    print(f"      {msg}", flush=True)


class Builder:
    def __init__(self, root: Path, skip_tests: bool) -> None:
        self.root = root
        self.build = root / "build"
        self.build.mkdir(exist_ok=True)
        self.log_path = self.build / "build.log"
        self.skip_tests = skip_tests
        self.py = sys.executable
        self.exe_name = "SynthProvenance.exe" if os.name == "nt" else "SynthProvenance"
        self.dist = root / "dist" / "SynthProvenance"

    def log(self, text: str) -> None:
        with self.log_path.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(text.rstrip("\n") + "\n")

    def run(self, cmd: list[str], log_file: Path | None = None, env: dict | None = None, timeout: int = 3600) -> tuple[int, str]:
        self.log(f"$ {' '.join(cmd)}")
        e = dict(os.environ)
        e.update(env or {})
        try:
            proc = subprocess.run(cmd, cwd=self.root, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            self.log("TIMEOUT")
            return 124, "timeout"
        except OSError as exc:
            self.log(f"OSError: {exc}")
            return 127, str(exc)
        out = proc.stdout.decode("utf-8", "replace")
        self.log(out)
        if log_file is not None:
            with log_file.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(out)
        return proc.returncode, out

    # ------------------------------------------------------------ stages
    def stage3(self) -> None:
        reqs = [self.root / "requirements.txt", self.root / "requirements-build.txt"]
        digest = hashlib.sha256(b"".join(p.read_bytes() for p in reqs) + sys.version.encode()).hexdigest()
        marker = self.root / ".venv" / ".synthprovenance_deps"
        if marker.is_file() and marker.read_text().strip() == digest:
            rc, _ = self.run([self.py, "-m", "pip", "check"])
            if rc == 0:
                say("Dependencies already installed (pinned set unchanged).")
                return
        say(f"Python {platform.python_version()} ({platform.architecture()[0]}) at {self.py}")
        say("Installing pinned packages from PyPI (this can take a few minutes the first time)...")
        rc, out = self.run([self.py, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                            "-r", str(reqs[0]), "-r", str(reqs[1])], timeout=3600)
        if rc != 0:
            hint = "Check the internet connection / proxy (pip must reach https://pypi.org)."
            if "No matching distribution" in out:
                hint = "No wheel for this Python version/architecture. Use 64-bit Python 3.12 (delete .venv and rebuild)."
            raise StageError("pip could not install the pinned dependencies.", hint)
        rc, out = self.run([self.py, "-m", "pip", "check"])
        if rc != 0:
            raise StageError("Installed dependencies are inconsistent (pip check failed).", "Delete the .venv folder and run the build again.")
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(digest)
        except OSError:
            pass
        say("Dependencies installed.")

    def stage4(self) -> None:
        rc, out = self.run([self.py, "-m", "compileall", "-q", "app", "scripts", "tests"])
        if rc != 0:
            raise StageError("Source files failed to compile.", "See build\\build.log for the syntax error.")
        env = {"QT_QPA_PLATFORM": "offscreen", "SYNTHPROVENANCE_HOME": tempfile.mkdtemp(prefix="sp_validate_")}
        code = ("import importlib,pkgutil,app\n"
                "mods=[m.name for m in pkgutil.walk_packages(app.__path__,'app.')]\n"
                "[importlib.import_module(m) for m in mods]\nprint('modules', len(mods))\n"
                "from app.utils.system import find_exiftool, find_c2patool, c2pa_python_status\n"
                "from app.core.synthid_engine import SynthIDEngine\n"
                "for t in (find_exiftool(), find_c2patool(), c2pa_python_status()):\n"
                "    print('optional tool', t.name, 'AVAILABLE' if t.available else 'not available', t.version or t.detail)\n"
                "print('optional tool SynthID engine', SynthIDEngine.discover().status()['detail'])\n"
                "from app.core import synthid_source_manager as SM\n"
                "s,p=SM.discover(None)\nassert s and not p, p\n"
                "print('optional tool SynthID research sources', len(s), 'validated')\n")
        rc, out = self.run([self.py, "-c", code], env=env)
        if rc != 0:
            raise StageError("Application modules failed to import.", "See build\\build.log; dependencies may be incomplete.")
        for line in out.splitlines():
            if line.startswith(("modules", "optional tool")):
                say(line)
        if not (self.root / "assets" / "icon.ico").is_file() or not (self.root / "assets" / "icon.png").is_file():
            say("Generating application icons...")
            rc, _ = self.run([self.py, "scripts/make_assets.py"])
            if rc != 0:
                raise StageError("Icon generation failed.", "See build\\build.log.")
        for rel in ("SynthProvenance.spec", "assets/version_info.txt", "assets/templates/report.html", "config/default_config.json"):
            if not (self.root / rel).is_file():
                raise StageError(f"Required build resource missing: {rel}", "Re-extract the complete SynthProvenance ZIP.")
        say("Source validated.")

    def stage5(self) -> None:
        if self.skip_tests:
            say("Tests skipped by request (--skip-tests).")
            return
        test_log = self.build / "test.log"
        test_log.write_text(f"==== SynthProvenance tests {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n", encoding="utf-8")
        env = {"QT_QPA_PLATFORM": "offscreen", "SYNTHPROVENANCE_HOME": tempfile.mkdtemp(prefix="sp_tests_")}
        rc, out = self.run([self.py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml", str(self.build / "junit.xml")],
                           log_file=test_log, env=env, timeout=3600)
        summary = next((l.strip() for l in reversed(out.splitlines()) if re.search(r"\d+ (passed|failed|error)", l)), "")
        say(f"Tests: {summary or 'no summary'}")
        if rc != 0:
            raise StageError(f"Automated tests failed ({summary}).", "Open build\\test.log to see the failing test.", "build\\test.log")

    def stage6(self) -> None:
        if self.dist.exists():
            try:
                shutil.rmtree(self.dist)
            except OSError as exc:
                raise StageError(f"Cannot remove previous build: {exc}",
                                 "Close any running SynthProvenance.exe and Explorer windows showing dist\\, then rebuild.")
        say("Running PyInstaller (windowed, --clean). This takes several minutes...")
        rc, out = self.run([self.py, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(self.root / "dist"),
                            "--workpath", str(self.build / "pyinstaller"), "--log-level", "WARN", "SynthProvenance.spec"],
                           timeout=5400)
        exe = self.dist / self.exe_name
        if rc != 0 or not exe.is_file():
            hint = "See build\\build.log."
            if "Permission denied" in out or "Access is denied" in out:
                hint = "A file is locked. Close SynthProvenance.exe; antivirus may be scanning dist\\ (add an exclusion or retry)."
            raise StageError("PyInstaller did not produce the executable.", hint)
        say(f"Executable built: {exe.relative_to(self.root)} ({exe.stat().st_size:,} bytes)")

    def stage7(self) -> None:
        rc, out = self.run([self.py, "scripts/verify_build.py", "--dist", str(self.dist), "--log", str(self.build / "verification.log")],
                           timeout=1200)
        for line in out.splitlines():
            if line.startswith(("PASS", "FAIL", "WARN")):
                say(line)
        if rc != 0:
            raise StageError("Executable verification failed.", "Open build\\verification.log. Antivirus software can block "
                             "freshly built executables; allow dist\\SynthProvenance and rebuild.", "build\\verification.log")

    def stage8(self) -> None:
        rc, out = self.run([self.py, "scripts/collect_runtime.py", "--root", str(self.root), "--dist", str(self.dist)])
        if rc != 0:
            raise StageError("Distribution folder could not be prepared.", "See build\\build.log.")
        for line in out.splitlines():
            say(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--from-stage", type=int, default=3)
    ap.add_argument("--to-stage", type=int, default=8)
    a = ap.parse_args()
    b = Builder(Path(a.root).resolve(), a.skip_tests)
    (b.build / "failure.txt").unlink(missing_ok=True)
    for n in range(a.from_stage, a.to_stage + 1):
        print(f"[{n}/8] {STAGES[n]}...", flush=True)
        b.log(f"==== [{n}/8] {STAGES[n]} ====")
        t0 = time.time()
        try:
            getattr(b, f"stage{n}")()
        except StageError as exc:
            (b.build / "failure.txt").write_text(f" Stage: {n}/8 {STAGES[n]}\n Reason: {exc.reason}\n"
                                                 f" Remediation: {exc.remediation}\n Details: {exc.log}\n", encoding="ascii",
                                                 errors="replace")
            b.log(f"FAILED at stage {n}: {exc.reason}")
            return 1
        except Exception as exc:  # noqa: BLE001
            (b.build / "failure.txt").write_text(f" Stage: {n}/8 {STAGES[n]}\n Reason: unexpected {type(exc).__name__}: {exc}\n"
                                                 " Remediation: see build\\build.log\n", encoding="ascii", errors="replace")
            b.log(f"UNEXPECTED at stage {n}: {exc!r}")
            return 1
        b.log(f"stage {n} ok in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
