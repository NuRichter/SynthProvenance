# Optional local tools

SynthProvenance works fully without anything in this folder. Tools placed here are
detected at start-up (Settings shows their state). Nothing is ever downloaded
automatically, and every tool is launched with an argument list, a timeout and
bounded output. The LOCAL-ONLY network guard covers Python code inside
SynthProvenance. It cannot police third-party executables, so only install tools
you trust and that work offline.

| Tool | Place it at | Used for |
|------|-------------|----------|
| ExifTool | `tools/exiftool/exiftool.exe` (or on PATH) | Read-only extra metadata listing, shown as EXTERNAL TOOL OUTPUT |
| c2patool | `tools/c2patool/c2patool.exe` (or on PATH) | C2PA signature validation and trust state |
| c2pa-python | `pip install c2pa-python` into `.venv` before building | Same as c2patool, in-process |
| SynthID engine | `tools/synthid/synthid_verifier.exe` or Settings path | SynthID embedded-signal measurement |

## SynthID local verification engine contract

SynthProvenance ships no SynthID detector. No compatible local verifier for images
is publicly available, and online verification services would require uploading the
image, which the LOCAL-ONLY policy forbids. Without an engine every SynthID result is
`UNAVAILABLE` with the reason "No compatible local verification engine is currently
available." Nothing is inferred from metadata.

A researcher-provided engine must behave like this:

```
synthid_verifier.exe --input <image path> --json
```

and print one JSON object on stdout:

```json
{"engine": "name", "version": "x.y",
 "state": "DETECTED | NOT_DETECTED | POSSIBLY_DETECTED | UNCERTAIN | ERROR",
 "confidence": 0.0, "detail": "free text",
 "model_version": "optional", "score": 0.0}
```

Mapping: `DETECTED` to DETECTED, `NOT_DETECTED` to NOT DETECTED, `POSSIBLY_DETECTED`
to POSSIBLY DETECTED, `UNCERTAIN` to UNKNOWN, `ERROR` or invalid JSON to INVALID.
`score` is optional. It is the engine's watermark likelihood (0 to 1), and the
SynthID Research Lab benchmark uses it for ROC/AUC. Without it, the ordinal state is
used and that basis is recorded. An engine that modifies its input file is
reported INVALID (integrity failure). A NOT DETECTED result after a
transformation is reported as a TRANSFORMATION EXPERIMENT observation. It is never
reported as removal, because a detector miss is not proof of absence.
