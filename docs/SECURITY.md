# Security

* All inputs are untrusted. Formats are sniffed by magic bytes, file size and decode memory are budgeted, Pillow runs
  with decompression-bomb protection, text chunks inflate under an 8 MiB bound, CBOR/JUMBF parsers have depth, item and
  length limits, and XMP with DOCTYPE/ENTITY declarations is rejected.
* Metadata is never executed or evaluated. No `eval`, no `exec`, no pickle of untrusted data.
* Paths from inputs are sanitised (`safe_filename`), writes are confined with `safe_join`, ZIP members use `safe_arcname`.
* External tools run with argument lists (`shell=False`), timeouts, bounded output and `CREATE_NO_WINDOW` on Windows.
* Outbound network access from Python code is blocked at runtime (see LOCAL_PROCESSING.md).
* Outputs are written atomically. The original input is never overwritten.
