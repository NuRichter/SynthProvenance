"""Filesystem locations and path-safety helpers.

All user-controlled names that end up on disk pass through ``safe_filename``
and every write into a managed directory is checked with ``safe_join`` so
that imported names can never escape their destination (path traversal).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_NAME = "SynthProvenance"

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def install_dir() -> Path:
    """Directory holding the executable (frozen) or the project root (source)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def bundle_dir() -> Path:
    """PyInstaller extraction directory (``_internal``) or the project root."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", install_dir()))
    return project_root()


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource. Top-level copies next to the EXE win."""
    for base in (install_dir(), bundle_dir()):
        candidate = base.joinpath(*parts)
        if candidate.exists():
            return candidate
    return bundle_dir().joinpath(*parts)


def user_data_dir() -> Path:
    override = os.environ.get("SYNTHPROVENANCE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_NAME


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def tool_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    for base in (install_dir(), bundle_dir(), project_root()):
        d = base / "tools"
        if d not in dirs:
            dirs.append(d)
    return dirs


def safe_filename(name: str, default: str = "file", max_len: int = 120) -> str:
    """Reduce an arbitrary (possibly hostile) name to a safe single component."""
    name = str(name).replace("\\", "/").split("/")[-1]
    name = _UNSAFE.sub("_", name).strip("._ ")
    if not name:
        name = default
    stem = name.split(".")[0].upper()
    if stem in _RESERVED:
        name = f"_{name}"
    if len(name) > max_len:
        if "." in name:
            stem, ext = name.rsplit(".", 1)
            ext = ext[:10]
            name = f"{stem[: max_len - len(ext) - 1]}.{ext}"
        else:
            name = name[:max_len]
    return name


def is_within(base: Path, target: Path) -> bool:
    base_r = Path(base).resolve()
    target_r = Path(target).resolve()
    try:
        target_r.relative_to(base_r)
        return True
    except ValueError:
        return False


def safe_join(base: Path, *parts: str) -> Path:
    """Join ``parts`` under ``base``; raise ``ValueError`` on traversal."""
    candidate = Path(base).joinpath(*parts)
    if not is_within(base, candidate):
        raise ValueError(f"Path escapes managed directory: {'/'.join(parts)}")
    return candidate


def safe_arcname(*parts: str) -> str:
    """Build a ZIP member name that cannot traverse outside the archive root."""
    clean: list[str] = []
    for part in parts:
        for piece in str(part).replace("\\", "/").split("/"):
            if piece in ("", ".", ".."):
                continue
            if ":" in piece:
                raise ValueError(f"Unsafe archive component: {piece!r}")
            clean.append(piece)
    if not clean:
        raise ValueError("Empty archive name")
    return "/".join(clean)
