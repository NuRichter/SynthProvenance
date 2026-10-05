"""C2PA / PROVENANCE DATA SEPARATION EXPERIMENT.

Removes ONLY the C2PA/JUMBF manifest store (JPEG APP11, PNG caBX, WebP C2PA
chunk) and, optionally, XMP provenance declarations. Every other byte of the
container, including the compressed image data, is copied verbatim. The
original input is never modified; the result is a new experimental output.
"""
from __future__ import annotations

from app.analyzers.xmp_analyzer import XMPError, edit_xmp
from app.core.containers import XMP_SIG, ContainerError, Segment, parse_container, png_text_chunk, rebuild_jpeg, rebuild_png, rebuild_webp
from app.services.metadata_sanitizer import SUPPORTED, SanitizeRefused, SanitizeResult

C2PA_WARNING = ("This operation may invalidate provenance authenticity information. "
                "This mode is intended for controlled laboratory research.")


def separate_provenance(data: bytes, fmt: str, include_xmp_declarations: bool = False) -> SanitizeResult:
    if fmt not in SUPPORTED:
        raise SanitizeRefused(f"C2PA separation is implemented for JPEG, PNG and WebP containers, not {fmt}.")
    try:
        st = parse_container(data, fmt)
    except ContainerError as exc:
        raise SanitizeRefused(f"Container cannot be parsed safely: {exc}") from exc
    res = SanitizeResult(data=data, format=fmt)

    def xmp_edit(packet: bytes, where: str):
        if not include_xmp_declarations:
            return True
        try:
            new, removed = edit_xmp(packet, {"provenance"})
        except XMPError as exc:
            res.notes.append(f"XMP invalid ({exc}); left untouched.")
            return True
        if not removed:
            return True
        res.removed.extend(f"{where}: {r}" for r in removed)
        res.provenance_removed = True
        return None if new is None else new

    def drop_store(seg: Segment, label: str) -> bool:
        res.removed.append(f"{label} ({seg.payload_length:,} bytes)")
        res.provenance_removed = True
        return False

    if fmt == "JPEG":
        def decide(seg: Segment):
            if seg.ident == "JUMBF":
                return drop_store(seg, "APP11 JUMBF / C2PA manifest store segment")
            if seg.ident == "XMP":
                out = xmp_edit(seg.payload(data)[len(XMP_SIG):], "APP1 XMP")
                return out if out is True else (False if out is None else XMP_SIG + out)
            return True
        out = rebuild_jpeg(data, st, decide)
    elif fmt == "PNG":
        def decide(seg: Segment):
            if seg.ident == "JUMBF":
                return drop_store(seg, "caBX C2PA manifest store chunk")
            if seg.ident == "XMP":
                _k, text, _n = png_text_chunk(data, seg)
                out = xmp_edit(text.encode("utf-8"), "iTXt XMP")
                return out if out is True else (False if out is None else b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + out)
            return True
        out = rebuild_png(data, st, decide)
    else:
        def decide(seg: Segment):
            if seg.ident == "JUMBF":
                return drop_store(seg, "C2PA RIFF chunk")
            if seg.name == "XMP ":
                out = xmp_edit(seg.payload(data), "XMP chunk")
                return out if out is True else (False if out is None else out)
            return True
        out = rebuild_webp(data, st, decide)
    res.data = out
    res.actions.append("C2PA / PROVENANCE DATA SEPARATION: container rewritten at byte level; compressed image data copied verbatim")
    if not res.removed:
        res.notes.append("No C2PA manifest store (or selected XMP declaration) was present; output content is unchanged.")
    res.notes.append(C2PA_WARNING)
    return res
