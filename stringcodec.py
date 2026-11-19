"""Reads and writes A Township Tale spawn strings.

A string is ``prefabHash,sizeBytes,word,word,...,`` optionally followed by ``|count,hash,version,...,``
(the component versioning). The words hold a bit stream: each 32-bit word's bits, most significant
first. The stream describes one prefab: its hash, position, rotation, scale, components, embedded
entities and child prefabs attached to slots. Component bodies are kept as raw bits, so anything this
module doesn't understand is carried through untouched. Gift mail boxes (SentGift) are the exception: their names
are packed to where they sit in the whole stream, so they're read into a Gift and laid out again on writing.
"""
import re
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


class StringFormatError(ValueError):
    pass


SENT_GIFT = 661497638  # a gift mail box's names and contents
_SIGN = 0x80000000  # ints are stored with the top bit flipped


@dataclass
class Component:
    hash: int
    bits: str  # the component body as '0'/'1'
    gift: Optional["Gift"] = None  # set for a readable SentGift; its bits are rebuilt from it when written
    start: int = 0  # where its body began in the string it was read from
    layout: Optional[object] = None  # anything with to_bits(start): rebuilds the body wherever it lands


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


@dataclass
class GiftItem:
    """One thing packed in a gift: a whole spawn string of its own, kept as its words."""
    hash: int
    size: int  # as the game stores it: the string's byte size less 4
    words: List[int]
    versioning: List[int]  # component (hash, version) pairs, flat

    def text(self) -> str:
        text = ",".join(str(n) for n in [self.hash, self.size + 4] + self.words) + ","
        if self.versioning:
            text += "|" + ",".join(str(n) for n in [len(self.versioning) // 2] + self.versioning) + ","
        return text

    def spawn_string(self) -> "SpawnString":
        return decode(self.text())

    @classmethod
    def from_string(cls, ss: "SpawnString", versioning: List[int]) -> "GiftItem":
        nums = [int(x) for x in encode(ss, force=True).split("|")[0].rstrip(",").split(",")]
        size = nums[1]
        return cls(nums[0], size - 4, nums[2:2 + (size + 3) // 4], list(versioning))


def _read_text(bits: str, i: int, start: int) -> Tuple[str, int]:
    """A name: 16-bit length, then (if any) padding to the next byte of the stream and the characters; whole 32-bit
    words hold theirs in reverse order."""
    n = int(bits[i:i + 16], 2)
    i += 16
    if n == 0:
        return "", i
    while (start + i) % 8:
        i += 1
    out, j = [], 0
    while j < n and (start + i) % 32:
        out.append(bits[i:i + 8]); i += 8; j += 1
    while j + 4 <= n:
        out += [bits[i + k * 8:i + k * 8 + 8] for k in (3, 2, 1, 0)]; i += 32; j += 4
    while j < n:
        out.append(bits[i:i + 8]); i += 8; j += 1
    if i > len(bits):
        raise StringFormatError("Gift name runs past its data")
    return "".join(chr(int(b, 2)) for b in out), i


def _write_text(out: list, pos: int, text: str) -> int:
    data = text.encode("latin-1", "replace")
    out.append(format(len(data), "016b"))
    pos += 16
    if not data:
        return pos
    while pos % 8:
        out.append("0"); pos += 1
    j = 0
    while j < len(data) and pos % 32:
        out.append(format(data[j], "08b")); pos += 8; j += 1
    while j + 4 <= len(data):
        out += [format(b, "08b") for b in reversed(data[j:j + 4])]; pos += 32; j += 4
    while j < len(data):
        out.append(format(data[j], "08b")); pos += 8; j += 1
    return pos


@dataclass
class Gift:
    to: str
    sender: str
    items: List[GiftItem]
    tag: str  # what follows the contents (who sent it to whom, by id), kept as it came

    DEFAULT_TAG = "0" + format(_SIGN, "032b") * 2

    @classmethod
    def from_bits(cls, bits: str, start: int) -> Optional["Gift"]:
        """The gift in a SentGift body that begins at stream bit `start`, or None if it doesn't read cleanly."""
        try:
            to, i = _read_text(bits, 0, start)
            sender, i = _read_text(bits, i, start)
            count, i = int(bits[i:i + 32], 2), i + 32
            items = []
            for _ in range(count):
                if bits[i] != "0":
                    return None  # an empty entry; leave such gifts as they are
                i += 1
                n, i = int(bits[i:i + 32], 2), i + 32
                if 32 * n > len(bits) - i:
                    return None
                words = [int(bits[i + 32 * k:i + 32 * k + 32], 2) for k in range(n)]
                i += 32 * n
                size, i = int(bits[i:i + 32], 2), i + 32
                h, i = int(bits[i:i + 32], 2), i + 32
                n, i = int(bits[i:i + 32], 2), i + 32
                if 32 * n > len(bits) - i:
                    return None
                versioning = [int(bits[i + 32 * k:i + 32 * k + 32], 2) for k in range(n)]
                i += 32 * n
                items.append(GiftItem(h, size, words, versioning))
            if i > len(bits):
                return None
            return cls(to, sender, items, bits[i:])
        except (IndexError, ValueError, StringFormatError):
            return None

    def to_bits(self, start: int) -> str:
        out = []
        pos = _write_text(out, start, self.to)
        _write_text(out, pos, self.sender)
        out.append(_u(len(self.items)))
        for it in self.items:
            out += ["0", _u(len(it.words))] + [_u(w) for w in it.words]
            out += [_u(it.size), _u(it.hash), _u(len(it.versioning))] + [_u(v) for v in it.versioning]
        out.append(self.tag)
        return "".join(out)


_STRING = re.compile(r"\d+,\d+,(?:\d+,)*\d+,?(?:\|(?:\d+,)*\d+,?)?")


def _plausible(candidate: str) -> bool:
    """A spawn string repeats its prefab hash as the first data word and has all the words its size needs."""
    nums = candidate.split("|")[0].rstrip(",").split(",")
    if len(nums) < 3 or nums[0] != nums[2]:
        return False
    return len(nums) - 2 >= (int(nums[1]) + 3) // 4


def clean(text: str) -> str:
    """The first spawn string in pasted text, normalised to end each part with a comma.

    Spaces and line breaks after commas are dropped first (wrapped or ", "-separated pastes), and number runs
    that aren't a spawn string (a date, a version) are skipped."""
    text = re.sub(r"([,|])\s+", r"\1", text or "")
    first = None
    for m in _STRING.finditer(text):
        parts = m.group(0).split("|")
        candidate = "|".join(p if p.endswith(",") else p + "," for p in parts)
        if _plausible(candidate):
            return candidate
        first = first or candidate
    if first is None:
        raise StringFormatError("No spawn string found")
    return first


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
        start = r.pos
        c = Component(h, r.take(size), start=start)
        if h == SENT_GIFT:
            g = Gift.from_bits(c.bits, start)
            if g is not None and g.to_bits(start) == c.bits:  # only when it can be written back exactly
                c.gift = g
        out.append(c)


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

class _Out:
    """Collects bits and knows where in the stream the next ones land."""

    def __init__(self):
        self.parts = []
        self.pos = 0

    def add(self, *bits: str):
        for b in bits:
            self.parts.append(b)
            self.pos += len(b)


def _w_components(out: _Out, comps: List[Component]):
    for c in comps:
        if c.gift is not None:
            c.bits = c.gift.to_bits(out.pos + 64)  # after its hash and size
        elif c.layout is not None:
            c.bits = c.layout.to_bits(out.pos + 64)
        out.add(_u(c.hash), _u(len(c.bits)), c.bits)
    out.add(_u(0))


def _w_prefab(out: _Out, p: Prefab):
    out.add(_u(p.hash), *[_f(v) for v in p.pos], *[_f(v) for v in p.rot], _f(p.scale))
    _w_components(out, p.components)
    for e in p.embeds:
        out.add(_u(e.hash))
        if e.alive:
            out.add(_u(e.size), "1")
            _w_components(out, e.components or [])
        else:
            out.add(_u(len(e.raw or "")), "0", e.raw or "")
    out.add(_u(0))
    for c in p.children:
        out.add("1", _u(c.parent_hash))
        _w_prefab(out, c.prefab)
    out.add("0")


def encode(ss: SpawnString, versioning: Optional[List[int]] = None, force: bool = False) -> str:
    if ss.original is not None and not force:
        return ss.original
    out = _Out()
    _w_prefab(out, ss.root)
    bits = "".join(out.parts)
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
