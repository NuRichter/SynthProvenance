# Local Processing Policy

Default mode: **LOCAL-ONLY**. SynthProvenance itself never uses the network. The only exception to "nothing leaves
this computer" is the explicit, user-operated ONLINE OFFICIAL VERIFICATION hand-off described below, and even there
the application uploads nothing.

* Images, metadata, hashes, results and user information never leave the computer.
* No cloud APIs, no remote inference, no external classification API, no telemetry, no remote storage.
* A CPython audit hook (`app/utils/netguard.py`) is installed at start-up. It rejects `socket.connect`,
  `socket.getaddrinfo` and `socket.sendto` for non-loopback hosts from Python code in the application. The self-test and
  the test suite prove the block. The setting is not user-configurable in this release.
* Optional third-party executables (ExifTool, c2patool, a SynthID engine) run as subprocesses outside the Python hook.
  They are never bundled or downloaded automatically. Install only tools you trust to work offline. c2patool may consult
  trust lists only if you configure it to.
* Network use happens only while building: pip downloads the pinned packages from PyPI, and the optional Python runtime
  download from nuget.org happens only after explicit consent and signature verification.
* ONLINE OFFICIAL VERIFICATION (SynthID Research Lab) is OFF by default and lasts for one session only. It is enabled by
  explicit confirmation. Each hand-off shows the exact destination URL, the file and its SHA-256, and asks again. Windows
  then opens an allow-listed official https page in the default browser and shows the file's folder. The upload is the
  researcher's own manual action in the browser. SynthProvenance opens no socket, keeps the network guard installed, and
  sends nothing. Scripted runs (`--smoke-gui`) always refuse the confirmation. See `docs/SYNTHID_RESEARCH_LAB.md`.
* An optional `nvidia-smi` probe (a local subprocess, no network) records the GPU and CUDA version in SynthID research
  run records when the tool exists.
* Experiment data lives in the workspace chosen in Settings (OPEN WORKSPACE, OPEN EXPERIMENT FOLDER). The portable
  default is `workspace\` next to the executable, with `%LOCALAPPDATA%\SynthProvenance\workspace` as fallback.
