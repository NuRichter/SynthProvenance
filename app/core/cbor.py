"""Minimal, bounded CBOR (RFC 8949) decoder and encoder.

The decoder is defensive: nesting depth, item count and string length are
capped so a hostile manifest cannot exhaust memory or recursion. Decoded
content is only ever treated as data.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any


class CBORError(ValueError):
    pass


@dataclass(frozen=True)
class CBORTag:
    tag: int
    value: Any


class _Break:
    pass


_BREAK = _Break()


class _Decoder:
    def __init__(self, data: bytes, max_depth: int, max_items: int, max_len: int):
        self.data = data
        self.pos = 0
        self.max_depth = max_depth
        self.max_items = max_items
        self.max_len = max_len
        self.items = 0

    def _read(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise CBORError("Unexpected end of CBOR data")
        b = self.data[self.pos : self.pos + n]
        self.pos += n
        return b

    def _arg(self, info: int) -> int | None:
        if info < 24:
            return info
        if info == 24:
            return self._read(1)[0]
        if info == 25:
            return struct.unpack(">H", self._read(2))[0]
        if info == 26:
            return struct.unpack(">I", self._read(4))[0]
        if info == 27:
            return struct.unpack(">Q", self._read(8))[0]
        if info == 31:
            return None
        raise CBORError(f"Reserved additional info {info}")

    def decode(self, depth: int = 0) -> Any:
        if depth > self.max_depth:
            raise CBORError("CBOR nesting too deep")
        self.items += 1
        if self.items > self.max_items:
            raise CBORError("CBOR item limit exceeded")
        ib = self._read(1)[0]
        major, info = ib >> 5, ib & 0x1F
        if major == 7:
            if info == 20:
                return False
            if info == 21:
                return True
            if info in (22, 23):
                return None
            if info == 25:
                return struct.unpack(">e", self._read(2))[0]
            if info == 26:
                return struct.unpack(">f", self._read(4))[0]
            if info == 27:
                return struct.unpack(">d", self._read(8))[0]
            if info == 31:
                return _BREAK
            if info < 24:
                return f"simple({info})"
            if info == 24:
                return f"simple({self._read(1)[0]})"
            raise CBORError("Invalid simple value")
        arg = self._arg(info)
        if major == 0:
            if arg is None:
                raise CBORError("Indefinite integer")
            return arg
        if major == 1:
            if arg is None:
                raise CBORError("Indefinite integer")
            return -1 - arg
        if major in (2, 3):
            if arg is None:
                chunks = []
                while True:
                    item = self.decode(depth + 1)
                    if item is _BREAK:
                        break
                    chunks.append(item)
                if major == 2:
                    return b"".join(c for c in chunks if isinstance(c, (bytes, bytearray)))
                return "".join(c for c in chunks if isinstance(c, str))
            if arg > self.max_len:
                raise CBORError("CBOR string exceeds length limit")
            raw = self._read(arg)
            return raw if major == 2 else raw.decode("utf-8", "replace")
        if major == 4:
            out = []
            if arg is None:
                while True:
                    item = self.decode(depth + 1)
                    if item is _BREAK:
                        return out
                    out.append(item)
            if arg > self.max_items:
                raise CBORError("CBOR array too large")
            for _ in range(arg):
                out.append(self.decode(depth + 1))
            return out
        if major == 5:
            out_map: dict = {}
            count = 0
            while arg is None or count < arg:
                key = self.decode(depth + 1)
                if key is _BREAK and arg is None:
                    break
                val = self.decode(depth + 1)
                out_map[_hashable(key)] = val
                count += 1
                if count > self.max_items:
                    raise CBORError("CBOR map too large")
            return out_map
        if major == 6:
            if arg is None:
                raise CBORError("Indefinite tag")
            return CBORTag(arg, self.decode(depth + 1))
        raise CBORError(f"Unknown major type {major}")


def _hashable(key: Any) -> Any:
    if isinstance(key, (list, dict, bytearray)):
        return repr(key)
    return key


def loads(data: bytes, max_depth: int = 48, max_items: int = 250_000, max_len: int = 64 * 1024 * 1024) -> Any:
    dec = _Decoder(bytes(data), max_depth, max_items, max_len)
    value = dec.decode()
    if value is _BREAK:
        raise CBORError("Unexpected break")
    return value


def untag(value: Any) -> Any:
    while isinstance(value, CBORTag):
        value = value.value
    return value


def _head(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([(major << 5) | n])
    if n < 256:
        return bytes([(major << 5) | 24, n])
    if n < 65536:
        return bytes([(major << 5) | 25]) + struct.pack(">H", n)
    if n < 2**32:
        return bytes([(major << 5) | 26]) + struct.pack(">I", n)
    return bytes([(major << 5) | 27]) + struct.pack(">Q", n)


def dumps(obj: Any) -> bytes:
    """Deterministic encoder used for synthetic fixtures and self-tests."""
    if obj is None:
        return b"\xf6"
    if obj is True:
        return b"\xf5"
    if obj is False:
        return b"\xf4"
    if isinstance(obj, int):
        return _head(0, obj) if obj >= 0 else _head(1, -1 - obj)
    if isinstance(obj, float):
        return b"\xfb" + struct.pack(">d", obj)
    if isinstance(obj, (bytes, bytearray)):
        return _head(2, len(obj)) + bytes(obj)
    if isinstance(obj, str):
        raw = obj.encode("utf-8")
        return _head(3, len(raw)) + raw
    if isinstance(obj, (list, tuple)):
        return _head(4, len(obj)) + b"".join(dumps(v) for v in obj)
    if isinstance(obj, dict):
        return _head(5, len(obj)) + b"".join(dumps(k) + dumps(v) for k, v in obj.items())
    if isinstance(obj, CBORTag):
        return _head(6, obj.tag) + dumps(obj.value)
    raise TypeError(f"Cannot CBOR-encode {type(obj).__name__}")
