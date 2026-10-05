"""Pixel-integrity and load throughput benchmark on deterministic images.

    python benchmarks/bench_pixel_integrity.py [megapixels ...]
"""
from __future__ import annotations

import io
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.image_loader import open_image_bytes  # noqa: E402
from app.core.pixel_integrity import compare_images  # noqa: E402
from app.core.synthetic import pattern  # noqa: E402
from app.utils.memory import fmt_bytes, process_rss  # noqa: E402


def run(mp: float) -> None:
    w = int(math.sqrt(mp * 1e6 * 3 / 2))
    h = int(w * 2 / 3)
    img = pattern(w, h)
    buf = io.BytesIO()
    t0 = time.perf_counter()
    img.save(buf, "PNG", compress_level=1)
    t1 = time.perf_counter()
    dec = open_image_bytes(buf.getvalue())
    t2 = time.perf_counter()
    r = compare_images(img, dec)
    t3 = time.perf_counter()
    print(f"{w}x{h} ({w * h / 1e6:.1f} MP): encode {t1 - t0:.2f}s  decode {t2 - t1:.2f}s  "
          f"compare {t3 - t2:.2f}s ({r.verdict})  RSS {fmt_bytes(process_rss())}")


if __name__ == "__main__":
    for arg in sys.argv[1:] or ["1", "12", "24"]:
        run(float(arg))
