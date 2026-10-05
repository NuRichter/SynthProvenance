# Format Handling

## Input

JPEG, PNG, WebP, TIFF, BMP and GIF, identified by magic bytes (extensions are not trusted). Byte-level container parsing
(and therefore metadata-only sanitization and C2PA inspection) covers JPEG, PNG and WebP. TIFF, BMP and GIF use
decoder-level metadata, and C2PA is reported UNKNOWN for them.

## Output capability table

| Format | Modes | Alpha | ICC | Metadata | Pixel preservation |
|--------|-------|-------|-----|----------|--------------------|
| PNG | LOSSLESS | yes | iCCP | EXIF/XMP only with Carry | expected, verified |
| JPEG | LOSSY | no (discarded) | APP2 | EXIF/XMP only with Carry | not claimed, measured. WARNING: JPEG encoding may alter pixel values. |
| WEBP | LOSSLESS / LOSSY | yes | ICCP | EXIF/XMP only with Carry | lossless verified, lossy measured |
| TIFF | LOSSLESS (Deflate) / LOSSY (JPEG-in-TIFF) | yes (lossless) | tag 34675 | EXIF/XMP(700) only with Carry | lossless verified, lossy measured |
| BMP | LOSSLESS (uncompressed) | no (24-bit writer) | not supported | not supported | verified for 8-bit sources without alpha |

C2PA manifests are never copied into re-encoded outputs because a manifest cannot stay valid for new bytes without
re-signing, which this tool does not do.

16-bit sources stay 16-bit in PNG and lossless TIFF. JPEG, WebP and BMP reduce them to 8-bit and the action log says so.
Every export is measured against ORIGINAL, so a caveat always appears in the metrics rather than being assumed away.

## Chains

`FORMAT[:LOSSLESS|LOSSY[:quality]]` steps separated by `>`, up to 12 steps. Every step file is saved, hashed and compared
with ORIGINAL and with the previous step.
