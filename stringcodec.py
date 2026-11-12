"""Reads and writes A Township Tale spawn strings.

A string is ``prefabHash,sizeBytes,word,word,...,`` optionally followed by ``|count,hash,version,...,``
(the component versioning). The words hold a bit stream: each 32-bit word's bits, most significant
first. The stream describes one prefab: its hash, position, rotation, scale, components, embedded
entities and child prefabs attached to slots. Component bodies are kept as raw bits, so anything this
module doesn't understand is carried through untouched.
"""
import re
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


class StringFormatError(ValueError):
    pass


@dataclass
class Component:
    hash: int
    bits: str  # the component body as '0'/'1'


@dataclass
class Embed:
    hash: int
    size: int
    alive: bool
    components: Optional[List[Component]] = None
    raw: Optional[str] = None


@dataclass
class Child:
    parent_hash: int
    prefab: "Prefab"


@dataclass
class Prefab:
    hash: int
    pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: float = 1.0
    components: List[Component] = field(default_factory=list)
    embeds: List[Embed] = field(default_factory=list)
    children: List[Child] = field(default_factory=list)


@dataclass
class SpawnString:
    root: Prefab
    versioning: Optional[str] = None  # the text after '|', kept as it came in
    original: Optional[str] = None  # cleaned input; None once edited
    extra_words: List[int] = field(default_factory=list)  # words past sizeBytes; the game ignores them


_STRING = re.compile(r"\d+,\d+,(?:\d+,)*\d+,?(?:\|(?:\d+,)*\d+,?)?")


def clean(text: str) -> str:
    """The first spawn string in pasted text, normalised to end each part with a comma."""
    m = _STRING.search(text or "")
    if not m:
        raise StringFormatError("No spawn string found")
    parts = m.group(0).split("|")
    return "|".join(p if p.endswith(",") else p + "," for p in parts)


# ---- bits -------------------------------------------------------------------------------------

class _Reader:
    def __init__(self, bits: str):
        self.bits = bits
        self.pos = 0

    def take(self, n: int) -> str:
        if self.pos + n > len(self.bits):
            raise StringFormatError("String ends early")
        out = self.bits[self.pos:self.pos + n]
        self.pos += n
        return out

    def uint(self) -> int:
        return int(self.take(32), 2)

    def float(self) -> float:
        return struct.unpack(">f", struct.pack(">I", self.uint()))[0]

    def bool(self) -> bool:
        return self.take(1) == "1"


def _u(v: int) -> str:
    return format(v & 0xFFFFFFFF, "032b")


def _f(v: float) -> str:
    return _u(struct.unpack(">I", struct.pack(">f", v))[0])


# ---- decode -----------------------------------------------------------------------------------

def _components(r: _Reader) -> List[Component]:
    out = []
    while True:
        h = r.uint()
        if h == 0:
            return out
        size = r.uint()
        out.append(Component(h, r.take(size)))


def _embeds(r: _Reader) -> List[Embed]:
    out = []
    while True:
        h = r.uint()
        if h == 0:
            return out
        size = r.uint()
        alive = r.bool()
        if alive:
            out.append(Embed(h, size, True, components=_components(r)))
        else:
            out.append(Embed(h, size, False, raw=r.take(size)))


def _prefab(r: _Reader) -> Prefab:
    h = r.uint()
    pos = (r.float(), r.float(), r.float())
    rot = (r.float(), r.float(), r.float(), r.float())
    scale = r.float()
    p = Prefab(h, pos, rot, scale, _components(r), _embeds(r))
    while r.bool():
        parent = r.uint()
        p.children.append(Child(parent, _prefab(r)))
    return p


def decode(text: str) -> SpawnString:
    s = clean(text)
    body, _, tail = s.partition("|")
    nums = [int(x) for x in body.rstrip(",").split(",")]
    if len(nums) < 3:
        raise StringFormatError("String too short")
    size = nums[1]
    words = nums[2:]
    if len(words) < (size + 3) // 4:
        raise StringFormatError("String is missing data")
    if any(w > 0xFFFFFFFF for w in nums):
        raise StringFormatError("Number too large")
    need = (size + 3) // 4
    bits = "".join(_u(w) for w in words[:need])
    root = _prefab(_Reader(bits))
    if root.hash != nums[0]:
        raise StringFormatError("Prefab hash mismatch")
    return SpawnString(root, tail or None, s, words[need:])


# ---- encode -----------------------------------------------------------------------------------

def _w_components(out: list, comps: List[Component]):
    for c in comps:
        out += [_u(c.hash), _u(len(c.bits)), c.bits]
    out.append(_u(0))


def _w_prefab(out: list, p: Prefab):
    out.append(_u(p.hash))
    out += [_f(v) for v in p.pos] + [_f(v) for v in p.rot] + [_f(p.scale)]
    _w_components(out, p.components)
    for e in p.embeds:
        out += [_u(e.hash)]
        if e.alive:
            inner = []
            _w_components(inner, e.components or [])
            out += [_u(e.size), "1"] + inner
        else:
            out += [_u(len(e.raw or "")), "0", e.raw or ""]
    out.append(_u(0))
    for c in p.children:
        out += ["1", _u(c.parent_hash)]
        _w_prefab(out, c.prefab)
    out.append("0")


def encode(ss: SpawnString, versioning: Optional[List[int]] = None, force: bool = False) -> str:
    if ss.original is not None and not force:
        return ss.original
    parts = []
    _w_prefab(parts, ss.root)
    bits = "".join(parts)
    size = (len(bits) + 7) // 8
    bits = bits.ljust(((size + 3) // 4) * 32, "0")
    words = [int(bits[i:i + 32], 2) for i in range(0, len(bits), 32)]
    if ss.original is not None:  # an unedited re-encode keeps any trailing words exactly
        words += ss.extra_words
    text = ",".join(str(n) for n in [ss.root.hash, size] + words) + ","
    if versioning is not None:
        pairs = list(versioning)
        text += "|" + ",".join(str(n) for n in [len(pairs) // 2] + pairs) + ","
    elif ss.versioning:
        text += "|" + ss.versioning
    return text
