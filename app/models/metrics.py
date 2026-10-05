"""Pixel-integrity and quality metric records."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.serialization import jsonable

VERDICT_EXACT = "PIXEL-EXACT"
VERDICT_CHANGED = "TRANSFORMATION DETECTED"
VERDICT_NOT_COMPARABLE = "NOT COMPARABLE"


@dataclass
class PixelIntegrityResult:
    verdict: str
    comparable: bool
    basis: str
    resolution_a: tuple[int, int]
    resolution_b: tuple[int, int]
    pixel_count_a: int
    pixel_count_b: int
    channels_a: int
    channels_b: int
    mode_a: str
    mode_b: str
    compared_mode: str = ""
    mae: float | None = None
    mse: float | None = None
    max_abs_error: float | None = None
    changed_pixels: int | None = None
    changed_pixel_pct: float | None = None
    psnr_db: float | None = None
    psnr_infinite: bool = False
    ssim: float | None = None
    histogram_difference: float | None = None
    perceptual_hash_distance: int | None = None
    perceptual_difference: float | None = None
    region: tuple[int, int, int, int] | None = None
    region_exact: bool | None = None
    pixel_sha256_a: str = ""
    pixel_sha256_b: str = ""
    notes: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def pixel_exact(self) -> bool:
        return self.verdict == VERDICT_EXACT

    def to_dict(self) -> dict:
        d = jsonable(self)
        d["pixel_exact"] = self.pixel_exact
        return d
