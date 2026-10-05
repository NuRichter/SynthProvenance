"""LOCAL-ONLY network policy enforcement.

A CPython audit hook rejects outbound socket connections and name
resolution for non-loopback hosts made from Python code in this process.
SynthProvenance itself never needs the network. External tools launched as
subprocesses (optional ExifTool / c2patool / SynthID engine) are outside this
hook; they are user-installed and documented in docs/LOCAL_PROCESSING.md.
"""
from __future__ import annotations

import sys

_INSTALLED = False
_BLOCKED: list[str] = []
_LOOPBACK = {"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1", None, ""}


class NetworkPolicyError(PermissionError):
    pass


def _host_of(event: str, args: tuple):
    if event == "socket.getaddrinfo":
        return args[0] if args else None
    if event in ("socket.connect", "socket.sendto"):
        addr = args[1] if len(args) > 1 else None
        if isinstance(addr, tuple) and addr:
            return addr[0]
        return None  # AF_UNIX path or unknown -> local
    return None


def _hook(event: str, args: tuple) -> None:
    if event not in ("socket.getaddrinfo", "socket.connect", "socket.sendto"):
        return
    host = _host_of(event, args)
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host in _LOOPBACK or (isinstance(host, str) and host.startswith("127.")):
        return
    _BLOCKED.append(f"{event} {host}")
    raise NetworkPolicyError(f"SynthProvenance LOCAL-ONLY policy blocked network access ({event} -> {host}).")


def install() -> bool:
    global _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True
    return _INSTALLED


def installed() -> bool:
    return _INSTALLED


def blocked_attempts() -> list[str]:
    return list(_BLOCKED)


def policy_text() -> str:
    return ("NETWORK ACCESS: DISABLED / NOT REQUIRED. Images, metadata, hashes and results never leave this computer. "
            + ("Runtime guard: ACTIVE." if _INSTALLED else "Runtime guard: not installed in this process."))
