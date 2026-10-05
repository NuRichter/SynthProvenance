"""System inspection and safe external-tool execution.

External tools are launched only with argument lists (``shell=False``),
with a timeout and bounded output. Nothing is ever downloaded here.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.utils.paths import tool_search_dirs

MAX_TOOL_OUTPUT = 32 * 1024 * 1024


class ToolError(RuntimeError):
    pass


@dataclass
class ToolStatus:
    name: str
    available: bool
    path: str = ""
    version: str = ""
    detail: str = ""
    origin: str = ""  # bundled / PATH / configured


@dataclass
class ToolResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    args: list[str] = field(default_factory=list)


def run_tool(args: list[str], timeout: float = 60.0, cwd: str | None = None) -> ToolResult:
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        raise ToolError("External tool arguments must be a non-empty list of strings.")
    kwargs: dict = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(  # noqa: S603 - args list, shell=False
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
            cwd=cwd,
            check=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{Path(args[0]).name} timed out after {timeout:.0f}s") from exc
    except OSError as exc:
        raise ToolError(f"Could not start {Path(args[0]).name}: {exc}") from exc
    return ToolResult(proc.returncode, proc.stdout[:MAX_TOOL_OUTPUT], proc.stderr[:65536], args)


def _candidates(configured: str | None, names: list[str], subdirs: list[str]) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    if configured:
        out.append((Path(configured), "configured"))
    for base in tool_search_dirs():
        for sub in subdirs:
            for n in names:
                out.append((base / sub / n if sub else base / n, "bundled"))
    for n in names:
        found = shutil.which(n)
        if found:
            out.append((Path(found), "PATH"))
    return out


def _probe(name: str, configured: str | None, names: list[str], subdirs: list[str], ver_args: list[str]) -> ToolStatus:
    for cand, origin in _candidates(configured, names, subdirs):
        if not cand.is_file():
            continue
        try:
            res = run_tool([str(cand), *ver_args], timeout=15)
        except ToolError as exc:
            return ToolStatus(name, False, str(cand), detail=str(exc), origin=origin)
        text = (res.stdout or res.stderr).decode("utf-8", "replace").strip().splitlines()
        version = text[0].strip() if text else ""
        if res.returncode == 0:
            return ToolStatus(name, True, str(cand), version, origin=origin)
        return ToolStatus(name, False, str(cand), version, detail=f"exit code {res.returncode}", origin=origin)
    return ToolStatus(name, False, detail="not found (optional)")


def find_exiftool(configured: str | None = None) -> ToolStatus:
    exe = ["exiftool.exe", "exiftool(-k).exe"] if sys.platform.startswith("win") else ["exiftool"]
    return _probe("ExifTool", configured, exe, ["exiftool", ""], ["-ver"])


def find_c2patool(configured: str | None = None) -> ToolStatus:
    exe = ["c2patool.exe"] if sys.platform.startswith("win") else ["c2patool"]
    return _probe("c2patool", configured, exe, ["c2patool", ""], ["--version"])


def c2pa_python_status() -> ToolStatus:
    try:
        import c2pa  # type: ignore

        ver = getattr(c2pa, "__version__", "") or "installed"
        return ToolStatus("c2pa-python", True, version=str(ver), origin="python")
    except Exception as exc:  # noqa: BLE001 - any import failure means unavailable
        return ToolStatus("c2pa-python", False, detail=f"not installed (optional): {type(exc).__name__}")


def package_versions() -> dict[str, str]:
    from importlib import metadata

    out = {}
    for pkg in ("PySide6-Essentials", "shiboken6", "pillow", "numpy", "blake3", "reportlab"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def system_info() -> dict:
    info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "cpu_count": os.cpu_count(),
    }
    try:
        info["packages"] = package_versions()
    except Exception:  # noqa: BLE001
        info["packages"] = {}
    try:
        from PySide6 import QtCore

        info["qt"] = QtCore.qVersion()
    except Exception:  # noqa: BLE001
        info["qt"] = "unavailable"
    return info
