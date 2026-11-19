"""Reads and writes component bodies using the game's own saved layouts (data/components.json, exported from the
game: each component's save data fields in order).

Rules, matching how the game writes its save data:
  bool 1 bit · int 32 bits, top bit flipped · uint / float / reference-to-a-game-asset 32 bits
  TimeSpan / DateTime 64 bits, low word first · string: 16-bit length, byte-aligned characters (see stringcodec)
  array / list: 32-bit count, then the items · struct: its fields · class inside a class: a "missing" bit, then fields
A value decodes only when it uses up exactly the component's bits, so anything else is left alone.
"""
import json
import os
import struct
from typing import Any, Optional

try:
    from . import stringcodec as sc
except ImportError:  # loaded outside the package (tools)
    import stringcodec as sc

_SIGN = 0x80000000
TAIL = "__tail"  # key for trailing padding bits kept from the game's own copy


class LayoutError(ValueError):
    pass


class Schema:
    def __init__(self, data: dict):
        self.components = data.get("components", {})  # name -> {"save": type name, "fields": [...]}
        self.types = data.get("types", {})  # full type name -> {"struct": bool, "fields": [...]}

    @classmethod
    def load(cls, path: str) -> "Schema":
        with open(path, encoding="utf-8-sig") as f:
            return cls(json.load(f))

    def fields(self, component: str):
        c = self.components.get(component)
        return c["fields"] if c and isinstance(c.get("fields"), list) else None

    def has_text(self, component: str) -> bool:
        """Whether its bits depend on where they sit in the stream (strings are byte-aligned to the whole stream)."""
        seen = set()

        def walk(t):
            k = t["k"]
            if k == "string":
                return True
            if k in ("array", "list"):
                return walk(t["of"])
            if k in ("class", "struct") and t["name"] not in seen:
                seen.add(t["name"])
                d = self.types.get(t["name"]) or {}
                return any(walk(f["type"]) for f in (d.get("fields") or []) if isinstance(d.get("fields"), list))
            return False
        return any(walk(f["type"]) for f in (self.fields(component) or []))


def default_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "components.json")


# ---- decode -----------------------------------------------------------------------------------

class _R:
    def __init__(self, bits: str, start: int):
        self.bits, self.i, self.start = bits, 0, start

    def take(self, n: int) -> str:
        if self.i + n > len(self.bits):
            raise LayoutError("runs past the end")
        out = self.bits[self.i:self.i + n]
        self.i += n
        return out

    def u32(self) -> int:
        return int(self.take(32), 2)


def _read(s: Schema, t: dict, r: _R, top: bool = False) -> Any:
    k = t["k"]
    if k == "bool":
        return r.take(1) == "1"
    if k in ("int", "enum"):
        n = r.u32() ^ _SIGN
        return n - (1 << 32) if n >= _SIGN else n
    if k in ("uint", "ref"):
        return r.u32()
    if k == "float":
        return struct.unpack(">f", struct.pack(">I", r.u32()))[0]
    if k in ("timespan", "datetime", "long", "ulong"):
        lo = r.u32()
        hi = r.u32()
        v = (hi << 32) | lo
        return v - (1 << 64) if k in ("timespan", "long") and v >= 1 << 63 else v
    if k == "string":
        text, r.i = sc._read_text(r.bits, r.i, r.start)
        return text
    if k in ("array", "list"):
        n = r.u32()
        if n > len(r.bits) - r.i:
            raise LayoutError("impossible length")
        return [_read(s, t["of"], r) for _ in range(n)]
    if k in ("class", "struct"):
        d = s.types.get(t["name"])
        if not d or not isinstance(d.get("fields"), list):
            raise LayoutError("unknown type " + t["name"])
        if k == "class" and not top:
            if r.take(1) == "1":
                return None
        return {f["name"]: _read(s, f["type"], r) for f in d["fields"]}
    raise LayoutError("unsupported " + k)


def decode(s: Schema, component: str, bits: str, start: int = 0) -> Optional[dict]:
    """The component's saved values as a dict, or None when its layout is unknown or the bits don't fit it."""
    fields = s.fields(component)
    if fields is None:
        return None
    r = _R(bits, start)
    try:
        value = {f["name"]: _read(s, f["type"], r) for f in fields}
    except (LayoutError, IndexError, ValueError, sc.StringFormatError):
        return None
    rest = bits[r.i:]
    if rest and len(rest) < 8 and "1" not in rest and s.has_text(component):
        value[TAIL] = rest  # a few zero bits the game sometimes leaves after text; kept so it writes back the same
        return value
    return value if not rest else None


# ---- encode -----------------------------------------------------------------------------------

def _write(s: Schema, t: dict, v: Any, out: list, pos: list, top: bool = False):
    def add(b):
        out.append(b)
        pos[0] += len(b)
    k = t["k"]
    if k == "bool":
        add("1" if v else "0")
    elif k in ("int", "enum"):
        add(sc._u((int(v) & 0xFFFFFFFF) ^ _SIGN))
    elif k in ("uint", "ref"):
        add(sc._u(int(v)))
    elif k == "float":
        add(sc._f(float(v)))
    elif k in ("timespan", "datetime", "long", "ulong"):
        n = int(v) & 0xFFFFFFFFFFFFFFFF
        add(sc._u(n & 0xFFFFFFFF))
        add(sc._u(n >> 32))
    elif k == "string":
        part = []
        pos[0] = sc._write_text(part, pos[0], str(v or ""))
        out.append("".join(part))
    elif k in ("array", "list"):
        v = v or []
        add(sc._u(len(v)))
        for item in v:
            _write(s, t["of"], item, out, pos)
    elif k in ("class", "struct"):
        d = s.types[t["name"]]
        if k == "class" and not top:
            add("1" if v is None else "0")
            if v is None:
                return
        for f in d["fields"]:
            _write(s, f["type"], (v or {}).get(f["name"], blank(s, f["type"])), out, pos)
    else:
        raise LayoutError("unsupported " + k)


def encode(s: Schema, component: str, value: dict, start: int = 0) -> str:
    out, pos = [], [start]
    for f in s.fields(component):
        _write(s, f["type"], value.get(f["name"], blank(s, f["type"])), out, pos)
    return "".join(out) + value.get(TAIL, "")


def blank(s: Schema, t: dict) -> Any:
    """An empty value of a type: false, 0, "", [], or a class/struct with blank fields (a nested class is missing)."""
    k = t["k"]
    if k == "bool":
        return False
    if k == "float":
        return 0.0
    if k == "string":
        return ""
    if k in ("array", "list"):
        return []
    if k == "class":
        return None
    if k == "struct":
        d = s.types.get(t["name"]) or {}
        return {f["name"]: blank(s, f["type"]) for f in d.get("fields") or []}
    return 0


def blank_component(s: Schema, component: str) -> dict:
    return {f["name"]: blank(s, f["type"]) for f in s.fields(component) or []}


def blank_class(s: Schema, type_name: str) -> dict:
    d = s.types.get(type_name) or {}
    return {f["name"]: blank(s, f["type"]) for f in d.get("fields") or []}


class Layout:
    """A component body rebuilt from its values wherever it lands (for layouts with text in them)."""

    def __init__(self, schema: Schema, component: str, value: dict):
        self.schema, self.component, self.value = schema, component, value

    def to_bits(self, start: int) -> str:
        return encode(self.schema, self.component, self.value, start)
