"""Memory planning for arbitrary-resolution images.

There is no fixed resolution cap. A decode is admitted when the estimated
working set fits into currently available RAM; otherwise loading fails with
a diagnostic. The source is never silently downscaled.
"""
from __future__ import annotations

from app.utils.memory import fmt_bytes, system_memory

BYTES_PER_PIXEL = {"1": 1, "L": 1, "P": 1, "LA": 2, "PA": 2, "RGB": 3, "YCbCr": 3, "LAB": 3, "HSV": 3, "RGBA": 4,
                   "RGBX": 4, "CMYK": 4, "I;16": 2, "I;16B": 2, "I;16L": 2, "I;16N": 2, "I": 4, "F": 4}
WORKING_COPIES = 2.5  # decoded image + canonical/display/comparison headroom
SAFETY = 0.85


class MemoryBudgetError(RuntimeError):
    pass


def decoded_bytes(width: int, height: int, mode: str) -> int:
    return int(width) * int(height) * BYTES_PER_PIXEL.get(mode, 4)


def estimate(width: int, height: int, mode: str) -> dict:
    one = decoded_bytes(width, height, mode)
    canon = width * height * (4 if mode in ("P", "PA", "RGBA", "LA", "CMYK") else BYTES_PER_PIXEL.get(mode, 4))
    return {"decoded": one, "canonical": canon, "working_set": int(one * WORKING_COPIES),
            "comparison_peak": int(canon * 2 + min(canon, 512 * width * 8 * 4))}


def check_decode_budget(width: int, height: int, mode: str) -> dict:
    est = estimate(width, height, mode)
    avail = system_memory().get("available")
    est["available"] = avail
    if avail is None:
        est["decision"] = "admitted (available memory unknown)"
        return est
    if est["working_set"] > avail * SAFETY:
        raise MemoryBudgetError(
            f"Image {width}x{height} ({width * height / 1e6:.1f} MP, mode {mode}) needs about "
            f"{fmt_bytes(est['working_set'])} of working memory, but only {fmt_bytes(avail)} is available. "
            "SynthProvenance does not downscale sources to make them fit. Close other applications or use a "
            "machine with more RAM.")
    est["decision"] = "admitted"
    return est
