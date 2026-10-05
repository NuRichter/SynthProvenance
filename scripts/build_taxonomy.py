"""Regenerate data/fingerprint_taxonomy.json from the bundled taxonomy source file.

    python scripts/build_taxonomy.py [--source FILE] [--out FILE]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.research.taxonomy import SOURCE_NAME, write_database  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT / "data" / "source" / SOURCE_NAME))
    ap.add_argument("--out", default=str(ROOT / "data" / "fingerprint_taxonomy.json"))
    a = ap.parse_args()
    db = write_database(Path(a.source), Path(a.out))
    cats = Counter(e["category"] for e in db["entries"])
    print(f"{len(db['entries'])} entries, {len(db['references'])} references, {len(db['anchors'])} anchors -> {a.out}")
    for k, v in sorted(cats.items()):
        print(f"  {k:26s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
