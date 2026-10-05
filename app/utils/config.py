"""Settings: bundled defaults (config/default_config.json) + user overrides."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.utils.paths import install_dir, is_frozen, resource_path, user_data_dir
from app.utils.serialization import write_json

DEFAULTS = {
    "workspace": "",
    "max_megapixels": 0,
    "max_file_mb": 4096,
    "statistics_max_pixels": 16_000_000,
    "use_exiftool": True,
    "exiftool_path": "",
    "c2patool_path": "",
    "use_c2pa_python": True,
    "synthid_engine_command": [],
    "default_sanitize_profile": "BALANCED",
    "network_access": "DISABLED",
    "language": "en",
    "ui_mode": "EASY",
    "easy_output_format": "PNG",
    "easy_save_report": True,
    "easy_report_dir": "",
    "truthscan_integration": False,
    "theme": "Dark Laboratory",
}
UI_MODES = ("EASY", "EXPERT")


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else user_data_dir() / "settings.json"
        self._lock = threading.RLock()
        self.data = dict(DEFAULTS)
        try:
            bundled = json.loads(resource_path("config", "default_config.json").read_text(encoding="utf-8"))
            self.data.update({k: v for k, v in bundled.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        if self.path.is_file():
            try:
                user = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update({k: v for k, v in user.items() if k in DEFAULTS})
            except (OSError, ValueError):
                pass
        self.data["network_access"] = "DISABLED"  # policy is not user-configurable in this release

    def get(self, key: str, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        if key not in DEFAULTS or key == "network_access":
            raise KeyError(key)
        with self._lock:
            self.data[key] = value

    def ui_mode(self) -> str:
        mode = str(self.get("ui_mode") or "EASY").upper()
        return mode if mode in UI_MODES else "EASY"

    def save(self) -> None:
        with self._lock:
            write_json(self.path, self.data)

    def workspace_root(self) -> Path:
        configured = str(self.get("workspace") or "").strip()
        if configured:
            return Path(configured).expanduser()
        if os.environ.get("SYNTHPROVENANCE_HOME"):
            return user_data_dir() / "workspace"
        if is_frozen():
            portable = install_dir() / "workspace"
            try:
                portable.mkdir(parents=True, exist_ok=True)
                probe = portable / ".write_test"
                probe.write_text("ok", encoding="ascii")
                probe.unlink()
                return portable
            except OSError:
                pass
        return user_data_dir() / "workspace"
