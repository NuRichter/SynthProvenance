"""JSON-safe conversion used for every persisted record."""
from __future__ import annotations

import dataclasses
import enum
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any


def jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, enum.Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (bytes, bytearray, memoryview)):
        b = bytes(obj)
        return {"__bytes__": len(b), "hex_preview": b[:32].hex()}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:  # numpy scalars / arrays without importing numpy eagerly
        import numpy as np

        if isinstance(obj, np.generic):
            return jsonable(obj.item())
        if isinstance(obj, np.ndarray):
            return jsonable(obj.tolist())
    except ImportError:  # pragma: no cover
        pass
    return str(obj)


def dumps(obj: Any, indent: int | None = 2) -> str:
    return json.dumps(jsonable(obj), indent=indent, ensure_ascii=False, sort_keys=False)


def write_json(path: Path, obj: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dumps(obj), encoding="utf-8")
    tmp.replace(path)
    return path


def read_json(path: Path, max_bytes: int = 64 * 1024 * 1024) -> Any:
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError(f"JSON file too large: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
