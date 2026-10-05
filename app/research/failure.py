"""Rule-based failure analysis for research runs (Section 43 of the brief).

Given the measured metrics of a method result, report concrete failure modes with the
observed symptom, likely cause, the affected metric and a possible improvement. Nothing
is hidden: weak or negative results produce findings rather than being dropped.
"""
from __future__ import annotations

FAILURE_FIELDS = ("failure_mode", "symptom", "likely_cause", "affected_metric", "possible_improvement")


def _f(mode, symptom, cause, metric, fix) -> dict:
    return dict(zip(FAILURE_FIELDS, (mode, symptom, cause, metric, fix)))


def analyse(result: dict) -> list[dict]:
    """``result`` is a MethodResult.to_dict() (or any dict with the keys below). Returns a list of findings."""
    out: list[dict] = []
    recon = result.get("reconstruction") or {}
    gt = result.get("ground_truth") or {}
    cand = result.get("candidate_stats") or {}
    metrics = result.get("metrics") or {}

    psnr = recon.get("psnr_db")
    ssim = recon.get("ssim")
    if psnr is not None and psnr < 28:
        out.append(_f("over-smoothing / content damage", f"reconstruction PSNR {psnr:.1f} dB is low",
                      "the separation removed image content together with the signal", "PSNR / SSIM",
                      "reduce the operator strength or use an edge-aware (guided / wavelet) separation"))
    if ssim is not None and ssim < 0.85 and (psnr or 99) < 36:
        out.append(_f("structural degradation", f"SSIM {ssim:.3f}", "low-frequency content altered",
                      "SSIM", "constrain the separation to the high band, or lower the strength"))

    corr = gt.get("candidate_vs_known_corr")
    if corr is not None and corr < 0.3:
        out.append(_f("false candidate / poor recovery", f"candidate-vs-known correlation {corr:.2f}",
                      "the method did not isolate the embedded signal (wrong domain or key-blind method on a keyed signal)",
                      "recovery correlation", "match the analysis domain to the signal family, or raise embedding strength"))
    nr = gt.get("candidate_noise_ratio")
    if nr is not None and nr > 5:
        out.append(_f("noisy candidate", f"candidate energy is {nr:.1f}x the known-signal energy",
                      "the candidate map is dominated by content-driven residual, not the signal", "candidate energy",
                      "average over more images (cross-image consensus) or denoise the residual"))

    kurt = cand.get("kurtosis")
    if kurt is not None and kurt > 20:
        out.append(_f("heavy-tailed residual", f"residual kurtosis {kurt:.1f}",
                      "a few edges/outliers dominate the residual", "kurtosis / energy",
                      "use a median or wavelet residual, or clip outliers before statistics"))
    off = (cand.get("autocorrelation") or {}).get("max_offcentre")
    if off is not None and off > 0.3:
        out.append(_f("periodic / grid artifact in residual", f"off-centre autocorrelation peak {off:.2f}",
                      "an 8x8 JPEG grid or an up-sampling lattice is present", "autocorrelation",
                      "report the periodicity explicitly; it is a frequency artifact, not necessarily a fingerprint"))

    auc = metrics.get("auc")
    if auc is not None and auc < 0.6:
        out.append(_f("detector near chance", f"AUC {auc:.2f}", "the scored statistic barely separates the labels",
                      "AUC", "collect more labelled data, or the method does not apply to these generators"))
    red = gt.get("signal_reduction")
    persisted = result.get("status") == "SIGNAL PERSISTED" or gt.get("still_detected_after")
    if red is not None and red < 0.2 and persisted:
        out.append(_f("signal persistence", f"signal reduction only {red:.2f} and still detected",
                      "the surrogate signal is robust to this operation at the allowed fidelity", "signal reduction",
                      "this is an expected, informative result: record the robustness, do not force removal"))

    rel = (result.get("solver") or {}).get("final_rel_residual")
    if rel is not None and rel > 1e-3:
        out.append(_f("solver did not converge", f"final relative residual {rel:.1e}",
                      "Robust PCA reached the iteration limit", "convergence", "raise max_iter or lambda"))

    if not out:
        out.append(_f("none", "no failure rule triggered for the reported metrics", "-", "-",
                      "results are within expected ranges; still replicate before drawing conclusions"))
    return out
