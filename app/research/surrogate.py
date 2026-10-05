"""Controlled surrogate watermark / fingerprint system with known ground truth.

    CLEAN IMAGE -> SURROGATE EMBEDDER -> WATERMARKED IMAGE -> LOCAL DETECTOR -> GROUND TRUTH

This is NOT SynthID and does not imitate SynthID internals. It is a transparent,
keyed laboratory signal whose exact form is known, so that separation,
reconstruction, robustness and red-team experiments can be scored against ground
truth. Families (all keyed by an integer seed):

    spatial        additive Gaussian pseudo-noise, optionally masked by local activity
    pseudo_random  a 64x64 keyed tile repeated over the image (crop-tolerant, tile-folding detector)
    fft            keyed-phase energy on a mid-frequency annulus of the luminance spectrum
    dct            Cox-style multiplicative spread spectrum on mid-band 8x8 DCT coefficients
    wavelet        additive pseudo-noise in level-2 LH/HL Haar sub-bands
    multi_scale    sum of pseudo-noise patterns generated at 1, 1/2 and 1/4 scale
    learned        pseudo-noise spectrally shaped by a weighting learned (numpy, closed loop) to
                   maximise detection after blur + noise under the same energy budget
    multi_bit      k-bit payload, each bit modulating an orthogonal pseudo-noise carrier (CDMA)
    hybrid         spatial + dct + fft at one third of the energy each
    neural         UNAVAILABLE: a neural robust watermark needs a deep-learning runtime and trained
                   weights, which are not bundled

Detector: domain-matched normalised correlation between the (high-pass filtered) test
image and the keyed reference, reported as a z-score (approximately N(0,1) for an
unmarked image) with a one-sided p-value; multi-bit additionally reports per-bit
decisions and bit accuracy. The detector needs only the key and the configuration
(blind with respect to the clean image).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from app.research import dct as D
from app.research import wavelet as W
from app.research.imaging import EPS, box_mean, gaussian_blur, luminance, resize_plane, rgb_to_ycbcr, ycbcr_to_rgb

FAMILIES = ("spatial", "pseudo_random", "fft", "dct", "wavelet", "multi_scale", "learned", "multi_bit", "hybrid", "neural")
AVAILABLE_FAMILIES = tuple(f for f in FAMILIES if f != "neural")
UNAVAILABLE = {"neural": "Neural robust watermark: requires a deep-learning runtime (PyTorch/ONNX) and trained "
                         "encoder/decoder weights. Not bundled; nothing is simulated in its place."}
DEFAULT_THRESHOLD_Z = 4.0  # one-sided p ~ 3.2e-5 under the N(0,1) null
TILE = 64


@dataclass
class SurrogateConfig:
    family: str = "spatial"
    key: int = 20261005
    strength: float = 3.0          # target signal RMS in 8-bit levels (0..255 scale)
    adaptive: bool = True          # mask the signal by local activity (texture hides it better)
    bits: int = 16                 # multi_bit payload length
    message: int = 0xA5C3          # multi_bit payload (lower ``bits`` bits used)
    band: tuple = (0.25, 0.45)     # fft annulus (normalised frequency, 1 = Nyquist)
    threshold_z: float = DEFAULT_THRESHOLD_Z

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = list(self.band)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SurrogateConfig":
        d = dict(d or {})
        if "band" in d:
            d["band"] = tuple(d["band"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class SurrogateUnavailable(RuntimeError):
    pass


def _rng(key: int, salt: int = 0) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([int(key) & 0xFFFFFFFF, int(salt) & 0xFFFFFFFF, 0x5350]))


def _unit(p: np.ndarray) -> np.ndarray:
    p = p - p.mean()
    return p / (float(p.std()) + EPS)


def _activity_mask(y: np.ndarray) -> np.ndarray:
    """Local standard deviation, normalised to mean 1 and clipped to [0.25, 3]."""
    m = box_mean(y, 3)
    v = np.maximum(box_mean(y * y, 3) - m * m, 0)
    s = np.sqrt(v)
    s = s / (float(s.mean()) + EPS)
    return np.clip(s, 0.25, 3.0)


def highpass(y: np.ndarray) -> np.ndarray:
    """Detector pre-filter: removes most host content so the keyed signal dominates the correlation."""
    return y - gaussian_blur(y, 1.5)


# ------------------------------------------------------------------ keyed patterns (unit RMS, zero mean)
def _spatial(shape, key):
    return _unit(_rng(key, 1).standard_normal(shape))


def _tile(key):
    return _unit(_rng(key, 2).standard_normal((TILE, TILE)))


def _pseudo_random(shape, key):
    t = _tile(key)
    reps = (math.ceil(shape[0] / TILE), math.ceil(shape[1] / TILE))
    return np.tile(t, reps)[: shape[0], : shape[1]]


def _annulus(shape, band):
    fy = np.fft.fftfreq(shape[0])[:, None] * 2
    fx = np.fft.fftfreq(shape[1])[None, :] * 2
    r = np.hypot(fy, fx)
    return (r >= band[0]) & (r <= band[1])


def _fft(shape, key, band):
    mask = _annulus(shape, band)
    phase = _rng(key, 3).uniform(0, 2 * np.pi, shape)
    spec = mask * np.exp(1j * phase)
    p = np.fft.ifft2(spec).real
    return _unit(p)


def _wavelet(shape, key):
    z = np.zeros(shape, dtype=np.float64)
    dec = W.wavedec2(z, 2, "haar")
    rng = _rng(key, 5)
    for o in ("LH", "HL"):
        dec["details"][1][o] = rng.standard_normal(dec["details"][1][o].shape)
    return _unit(W.waverec2(dec))


def _multi_scale(shape, key):
    acc = np.zeros(shape, dtype=np.float64)
    for i, s in enumerate((1, 2, 4)):
        small = _rng(key, 10 + i).standard_normal((max(2, shape[0] // s), max(2, shape[1] // s))).astype(np.float32)
        acc += _unit(resize_plane(small, (shape[1], shape[0])).astype(np.float64)) / math.sqrt(3)
    return _unit(acc)


def _learned_weights(key: int, n: int = 32, iters: int = 6) -> np.ndarray:
    """Learn a radial spectral weighting (n bins) that maximises correlation after blur(1.0) + noise.

    Closed-loop numpy optimisation on a 128x128 probe: bins whose energy survives the
    channel are up-weighted (multiplicative update), at constant total energy. Deterministic per key.
    """
    shape = (128, 128)
    fy = np.fft.fftfreq(shape[0])[:, None] * 2
    fx = np.fft.fftfreq(shape[1])[None, :] * 2
    r = np.minimum(np.hypot(fy, fx), 0.999)
    bins = (r * n).astype(int)
    w = np.ones(n)
    rng = _rng(key, 20)
    base = np.fft.fft2(rng.standard_normal(shape))
    for _ in range(iters):
        spec = base * w[bins]
        p = _unit(np.fft.ifft2(spec).real)
        ch = gaussian_blur(p.astype(np.float32), 1.0) + 0.5 * rng.standard_normal(shape)
        gain = np.zeros(n)
        cp = np.fft.fft2(p)
        cc = np.fft.fft2(highpass(ch.astype(np.float32)))
        num = np.bincount(bins.ravel(), weights=(cc * np.conj(cp)).real.ravel(), minlength=n)
        den = np.bincount(bins.ravel(), weights=(np.abs(cp) ** 2).ravel(), minlength=n) + EPS
        gain = np.maximum(num / den, 0)
        w = w * (0.5 + gain / (gain.mean() + EPS))
        w = w / math.sqrt((w ** 2).mean())
    return w


def _learned(shape, key):
    n = 32
    w = _learned_weights(key, n)
    fy = np.fft.fftfreq(shape[0])[:, None] * 2
    fx = np.fft.fftfreq(shape[1])[None, :] * 2
    bins = (np.minimum(np.hypot(fy, fx), 0.999) * n).astype(int)
    spec = np.fft.fft2(_rng(key, 21).standard_normal(shape)) * w[bins]
    return _unit(np.fft.ifft2(spec).real)


def _carriers(shape, key, bits):
    return [_unit(_rng(key, 100 + b).standard_normal(shape)) for b in range(bits)]


def _bits(cfg: SurrogateConfig) -> np.ndarray:
    return np.array([(int(cfg.message) >> b) & 1 for b in range(int(cfg.bits))], dtype=int)


def pattern(shape: tuple[int, int], cfg: SurrogateConfig) -> np.ndarray:
    """Keyed reference pattern (unit RMS) in the pixel domain for additive families."""
    f = cfg.family
    if f in UNAVAILABLE:
        raise SurrogateUnavailable(UNAVAILABLE[f])
    if f == "spatial":
        return _spatial(shape, cfg.key)
    if f == "pseudo_random":
        return _pseudo_random(shape, cfg.key)
    if f == "fft":
        return _fft(shape, cfg.key, cfg.band)
    if f == "wavelet":
        return _wavelet(shape, cfg.key)
    if f == "multi_scale":
        return _multi_scale(shape, cfg.key)
    if f == "learned":
        return _learned(shape, cfg.key)
    if f == "multi_bit":
        signs = 2 * _bits(cfg) - 1
        return _unit(sum(s * c for s, c in zip(signs, _carriers(shape, cfg.key, int(cfg.bits)))))
    if f == "hybrid":
        return _unit(_spatial(shape, cfg.key) + _fft(shape, cfg.key, cfg.band) + _dct_pattern(shape, cfg.key))
    if f == "dct":
        return _dct_pattern(shape, cfg.key)
    raise ValueError(f"Unknown surrogate family {f!r}")


_MID = [(u, v) for u in range(8) for v in range(8) if 3 <= u + v <= 6]


def _dct_pattern(shape, key):
    """Pseudo-noise restricted to mid-band 8x8 DCT coefficients (additive form, used by hybrid and as reference)."""
    h, w = shape
    hh, ww = (h // 8) * 8, (w // 8) * 8
    c = np.zeros((hh // 8, ww // 8, 8, 8))
    rng = _rng(key, 4)
    for (u, v) in _MID:
        c[:, :, u, v] = rng.standard_normal(c.shape[:2])
    p = np.zeros(shape)
    if hh and ww:
        p[:hh, :ww] = D.block_idct(c)
    return _unit(p)


# ------------------------------------------------------------------ embed
@dataclass
class EmbedResult:
    watermarked: np.ndarray       # float HxWxC in [0, 1]
    signal: np.ndarray            # known signal on luminance, 0..1 scale (watermarked_Y - clean_Y before clipping)
    residual: np.ndarray          # watermarked - clean after clipping/quantisation (HxWxC, 0..1 scale)
    config: dict
    stats: dict = field(default_factory=dict)


def embed(clean: np.ndarray, cfg: SurrogateConfig) -> EmbedResult:
    """Embed into the luminance (Y of YCbCr) of a float image. Chroma is untouched. Returns float result.

    The returned image is quantised to 8-bit levels so that the ground-truth residual is exactly what an
    8-bit file would carry.
    """
    if cfg.family in UNAVAILABLE:
        raise SurrogateUnavailable(UNAVAILABLE[cfg.family])
    x = clean.astype(np.float32)
    grey = x.shape[2] == 1
    ycc = None if grey else rgb_to_ycbcr(x)
    y = x[:, :, 0] if grey else ycc[:, :, 0]
    amp = float(cfg.strength) / 255.0
    if cfg.family == "dct":
        # Cox et al. (1997) multiplicative spread spectrum: c' = c (1 + alpha w) on mid-band coefficients.
        h, w = y.shape
        hh, ww = (h // 8) * 8, (w // 8) * 8
        c = D.block_dct(y.astype(np.float64) * 255.0 - 128.0)
        rng = _rng(cfg.key, 4)
        alpha = 0.0
        wm = np.zeros_like(c)
        for (u, v) in _MID:
            wm[:, :, u, v] = rng.standard_normal(c.shape[:2])
        mid = np.zeros_like(c, dtype=bool)
        for (u, v) in _MID:
            mid[:, :, u, v] = True
        delta_unit = c * wm * mid
        rms = float(np.sqrt((delta_unit ** 2).sum() / max(hh * ww, 1))) or EPS
        alpha = float(cfg.strength) / rms
        sig = np.zeros_like(y, dtype=np.float64)
        if hh and ww:
            sig[:hh, :ww] = D.block_idct(alpha * delta_unit) / 255.0
        signal = sig.astype(np.float32)
    else:
        p = pattern(y.shape, cfg).astype(np.float32)
        if cfg.adaptive and cfg.family in ("spatial", "pseudo_random", "multi_scale", "learned", "multi_bit", "hybrid"):
            p = p * _activity_mask(y)
            p = p / (float(np.sqrt((p * p).mean())) + EPS)
        signal = (amp * p).astype(np.float32)
    y2 = y + signal
    if grey:
        out = y2[:, :, None]
    else:
        ycc2 = ycc.copy()
        ycc2[:, :, 0] = y2
        out = ycbcr_to_rgb(ycc2)
        # chroma-preserving round trip: keep the original RGB except for the luminance change
        out = x + (out - ycbcr_to_rgb(ycc))
    out = np.clip(np.rint(np.clip(out, 0, 1) * 255.0) / 255.0, 0, 1).astype(np.float32)
    residual = out - x
    st = {"signal_rms_8bit": float(np.sqrt((signal ** 2).mean()) * 255.0),
          "residual_rms_8bit": float(np.sqrt((residual ** 2).mean()) * 255.0),
          "clipped_fraction": float(((y2 < 0) | (y2 > 1)).mean())}
    return EmbedResult(out, signal, residual.astype(np.float32), cfg.to_dict(), st)


# ------------------------------------------------------------------ detect
def _ncc_z(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    a = a.astype(np.float64).ravel()
    b = b.astype(np.float64).ravel()
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    if den < EPS:
        return 0.0, 0.0
    rho = float((a * b).sum() / den)
    return rho, rho * math.sqrt(a.size)


def p_value(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _fold(x: np.ndarray, t: int) -> np.ndarray:
    h, w = (x.shape[0] // t) * t, (x.shape[1] // t) * t
    if h == 0 or w == 0:
        return np.zeros((t, t))
    return x[:h, :w].reshape(h // t, t, w // t, t).mean(axis=(0, 2))


@dataclass
class Detection:
    family: str
    score: float           # z-score
    p_value: float
    detected: bool
    threshold_z: float
    correlation: float
    bit_accuracy: float | None = None
    bits: list | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def detect(img: np.ndarray, cfg: SurrogateConfig) -> Detection:
    """Blind keyed detector on a float image (HxWxC or HxW) of any size >= 16x16."""
    if cfg.family in UNAVAILABLE:
        raise SurrogateUnavailable(UNAVAILABLE[cfg.family])
    y = img if img.ndim == 2 else luminance(img)
    y = y.astype(np.float32)
    thr = float(cfg.threshold_z)
    f = cfg.family
    if f == "pseudo_random":
        hp = highpass(y)
        folded = _fold(hp, TILE)
        folded = folded - folded.mean()
        nt = (y.shape[0] // TILE) * (y.shape[1] // TILE)
        tile = highpass(_tile(cfg.key).astype(np.float32)).astype(np.float64)
        tile = tile - tile.mean()
        # all 4096 circular tile phases at once (crop tolerance): rho(shift) = <a, roll(b, shift)> / (|a||b|)
        cc = np.fft.ifft2(np.fft.fft2(folded) * np.conj(np.fft.fft2(tile))).real
        den = math.sqrt(float((folded ** 2).sum()) * float((tile ** 2).sum())) or EPS
        rho_map = cc / den
        dy, dx = np.unravel_index(int(np.argmax(rho_map)), rho_map.shape)
        rho = float(rho_map[dy, dx])
        z = rho * math.sqrt(TILE * TILE)
        z_corr = z - math.sqrt(2 * math.log(TILE * TILE))  # approximate correction for the max over 4096 phases
        return Detection(f, z_corr, p_value(z_corr), z_corr > thr, thr, rho,
                         detail=f"tile phase ({dy}, {dx}), {nt} tiles folded; z corrected for 4096-phase search")
    if f == "dct":
        h, w = y.shape
        c = D.block_dct(y.astype(np.float64) * 255.0 - 128.0)
        rng = _rng(cfg.key, 4)
        vals = []
        for (u, v) in _MID:
            wv = rng.standard_normal(c.shape[:2])
            vals.append((np.abs(c[:, :, u, v]) * wv).ravel())
        a = np.concatenate(vals) if vals else np.zeros(0)
        n = a.size
        # c' = c (1 + alpha w)  =>  E[|c'| w] = alpha E|c| > 0, while E[|c| w] = 0 for an unmarked image (blind test)
        z = float(a.mean() / (a.std() + EPS) * math.sqrt(n)) if n else 0.0
        return Detection(f, z, p_value(z), z > thr, thr, float(a.mean() / (np.abs(a).mean() + EPS)),
                         detail="blind Cox-style statistic mean(|c| w) / sd over mid-band 8x8 DCT coefficients")
    hp = highpass(y)
    if f == "multi_bit":
        carriers = _carriers(y.shape, cfg.key, int(cfg.bits))
        corr = [_ncc_z(hp, highpass(c.astype(np.float32)))[1] for c in carriers]
        bits = [1 if c > 0 else 0 for c in corr]
        truth = _bits(cfg).tolist()
        acc = float(np.mean([int(a == b) for a, b in zip(bits, truth)]))
        z = float(sum(abs(c) for c in corr) / math.sqrt(len(corr)))  # aggregate presence statistic
        # presence: aggregate z of |corr| is biased under H0 (E|N(0,1)| = 0.798); centre it
        z_c = (sum(abs(c) for c in corr) - 0.7979 * len(corr)) / math.sqrt(len(corr) * (1 - 0.6366))
        return Detection(f, float(z_c), p_value(float(z_c)), z_c > thr, thr, float(np.mean(np.abs(corr)) / math.sqrt(y.size)),
                         bit_accuracy=acc, bits=bits, detail=f"aggregate |z| {z:.2f}; payload bits decoded by sign")
    ref = pattern(y.shape, cfg).astype(np.float32)
    rho, z = _ncc_z(hp, highpass(ref))
    return Detection(f, z, p_value(z), z > thr, thr, rho, detail="NCC of high-passed image with high-passed keyed pattern")


def ground_truth_record(clean: np.ndarray, emb: EmbedResult, det_clean: Detection, det_wm: Detection) -> dict:
    return {"config": emb.config, "embed_stats": emb.stats, "detector_clean": det_clean.to_dict(),
            "detector_watermarked": det_wm.to_dict(),
            "ground_truth": "known signal (luminance, pre-quantisation) and known residual (8-bit) stored with the run",
            "valid_ground_truth": bool(det_wm.detected and not det_clean.detected)}


def signal_reduction(clean: np.ndarray, watermarked: np.ndarray, attacked: np.ndarray) -> dict:
    """How much of the known embedded residual survives in ``attacked`` (projection onto the known residual)."""
    r0 = luminance(watermarked) - luminance(clean)
    r1 = luminance(attacked) - luminance(clean) if attacked.shape == clean.shape else None
    if r1 is None:
        return {"status": "NOT COMPARABLE", "detail": "geometry changed; projection onto the known residual undefined"}
    e0 = float((r0 * r0).sum())
    if e0 < EPS:
        return {"status": "NO SIGNAL"}
    proj = float((r1 * r0).sum()) / e0
    return {"status": "COMPLETE", "retained_fraction": proj, "signal_reduction": 1.0 - proj,
            "residual_energy_ratio": float((r1 * r1).sum()) / e0}
