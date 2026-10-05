"""Prepare the portable distribution folder next to the executable."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import time
from importlib import metadata
from pathlib import Path

BUNDLED = ["PySide6-Essentials", "shiboken6", "pillow", "numpy", "blake3", "reportlab", "charset-normalizer", "pyinstaller"]


def license_texts() -> str:
    out = []
    for name in BUNDLED:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        out.append("=" * 78 + f"\n{dist.metadata['Name']} {dist.version}\nLicense: {dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'see files'}\n")
        for f in dist.files or []:
            n = str(f).lower()
            if any(k in n for k in ("license", "copying", "notice")) and not n.endswith((".py", ".pyc")):
                try:
                    text = Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace")
                    out.append(f"--- {f}\n{text[:200_000]}\n")
                except OSError:
                    pass
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--dist", required=True)
    a = ap.parse_args()
    root, dist = Path(a.root), Path(a.dist)
    for sub in ("assets", "config", "data"):
        if (root / sub).is_dir():
            shutil.copytree(root / sub, dist / sub, dirs_exist_ok=True)
    if (root / "app" / "i18n" / "locales").is_dir():
        shutil.copytree(root / "app" / "i18n" / "locales", dist / "app" / "i18n" / "locales", dirs_exist_ok=True)
    tools = dist / "tools"
    shutil.copytree(root / "tools", tools, dirs_exist_ok=True)
    lic = dist / "licenses"
    lic.mkdir(exist_ok=True)
    shutil.copy2(root / "LICENSE", lic / "LICENSE.txt")
    (lic / "THIRD_PARTY_NOTICES.txt").write_text(
        "Third-party components bundled with SynthProvenance. Qt for Python (PySide6/shiboken6) is used under the GNU "
        "LGPL v3 and is dynamically linked; its libraries in _internal/PySide6 may be replaced.\n\n" + license_texts(),
        encoding="utf-8")
    ws = dist / "workspace"
    ws.mkdir(exist_ok=True)
    (ws / "README.txt").write_text("Default portable workspace (experiments, reports, cache, logs, exports).\n"
                                   "If this folder is not writable, SynthProvenance uses %LOCALAPPDATA%\\SynthProvenance\\workspace.\n",
                                   encoding="utf-8")
    (dist / "README.txt").write_text(
        "SynthProvenance - Scientific AI Content Signal & Image Provenance Laboratory\n"
        "Insyide Innovations x NuRichter Workspace - LOCAL RESEARCH ENVIRONMENT\n\n"
        "Run SynthProvenance.exe. Everything is processed locally; no image is uploaded.\n"
        "Optional tools: put exiftool, c2patool or a SynthID verification engine under tools\\ (see tools\\README.md).\n"
        "Command line: SynthProvenance.exe --self-test | --version | <image path>\n", encoding="utf-8")
    import os
    sys.path.insert(0, str(root))
    from app import __version__
    info = {"application": "SynthProvenance", "version": __version__, "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "packages": {}}
    for n in BUNDLED:
        try:
            info["packages"][n] = metadata.version(n)
        except metadata.PackageNotFoundError:
            pass
    (dist / "BUILD_INFO.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    sums = []
    for f in sorted(p for p in dist.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
        h = hashlib.sha256()
        with f.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        sums.append(f"{h.hexdigest()}  {f.relative_to(dist).as_posix()}")
    (dist / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    print(f"Distribution ready: {dist} ({len(sums)} files, {size / 2**20:.0f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
