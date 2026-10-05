"""Application mode (Easy / Expert) and SAVE & RESTART.

The two modes are different application shells (``EasyWindow`` vs the Expert
``MainWindow``), so a mode change is persisted to the settings file and the
application relaunches itself into the other shell: save config -> start a new
detached instance -> quit this one. The relaunch keeps the session's command-line
workspace override. Nothing here uses the network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from app.utils.config import UI_MODES
from app.utils.paths import install_dir, is_frozen, project_root

# set by app.main for the running session (e.g. {"workspace": "..."}); re-applied on relaunch
SESSION_ARGS: dict = {}


def relaunch_command(extra_args: list[str] | tuple = ()) -> tuple[str, list[str], str]:
    """(program, arguments, working directory) that starts a fresh instance of this application."""
    args: list[str] = []
    if is_frozen():
        program, cwd = sys.executable, str(install_dir())
    else:
        program = sys.executable
        if os.name == "nt" and Path(program).name.lower() == "python.exe":
            windowed = Path(program).with_name("pythonw.exe")
            if windowed.is_file():
                program = str(windowed)
        cwd = str(project_root())
        args.append(str(project_root() / "app" / "main.py"))
    if SESSION_ARGS.get("workspace"):
        args += ["--workspace", str(SESSION_ARGS["workspace"])]
    return program, args + [str(a) for a in extra_args], cwd


def _start_detached(program: str, args: list[str], cwd: str) -> bool:
    from PySide6.QtCore import QProcess

    r = QProcess.startDetached(program, args, cwd)
    return bool(r[0] if isinstance(r, tuple) else r)


def save_mode(settings, mode: str) -> None:
    mode = str(mode).upper()
    if mode not in UI_MODES:
        raise ValueError(f"unknown application mode {mode!r}")
    settings.set("ui_mode", mode)
    settings.save()


def save_and_restart(ctl, mode: str, launcher=None, quit_fn=None, extra_args: list[str] | tuple = ()) -> tuple[bool, str]:
    """Persist ``mode``, start a new instance and quit this one. Returns (ok, message)."""
    from app.core import audit_engine as A

    if getattr(ctl, "busy", False):
        return False, "An operation is still running. Wait for it to finish, then restart."
    try:
        save_mode(ctl.settings, mode)
    except (OSError, ValueError) as exc:
        return False, f"The setting could not be saved: {exc}"
    ctl.audit.log(A.UI_MODE_CHANGED, detail=f"application mode -> {mode.upper()} (save & restart)")
    program, args, cwd = relaunch_command(extra_args)
    try:
        ok = (launcher or _start_detached)(program, args, cwd)
    except Exception as exc:  # noqa: BLE001
        ok, err = False, f"{type(exc).__name__}: {exc}"
    else:
        err = ""
    if not ok:
        return False, ("The mode was saved, but the application could not restart itself"
                       + (f" ({err})" if err else "") + ". Close and reopen SynthProvenance to switch.")
    if quit_fn is None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        QTimer.singleShot(0, QApplication.instance().quit)
    else:
        quit_fn()
    return True, "Restarting"
