"""Application logging (rotating file + optional console)."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    root = logging.getLogger("synthprovenance")
    if _CONFIGURED:
        return root
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass
    if sys.stderr is not None:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh.setLevel(logging.WARNING)
        root.addHandler(sh)
    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"synthprovenance.{name}")
