"""Changes to a spawn string (attach, detach, material, scale, piece materials, dock contents, string on string)
and the labelled parts tree the tab shows."""
import copy
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

try:
    from .stringcodec import Child, Component, Embed, Prefab, SpawnString, _u
except ImportError:  # loaded outside the package (tools)
    from stringcodec import Child, Component, Embed, Prefab, SpawnString, _u

MATERIAL = "PhysicalMaterialPart"
MATERIAL_HASH_FALLBACK = 272188517  # the component hash used by every archived string
DOCK = "PickupDock"
DOCK_HASH_FALLBACK = 2592242915
_SIGN = 0x80000000  # the game writes ints with the sign bit flipped (1 -> 2147483649)


@dataclass
class Row:
    depth: int
    prefab: Prefab
    slot_h: Optional[int]
    label: str
    material: Optional[str]
    empty_slots: List[Tuple[int, str]] = field(default_factory=list)
    slot_label: Optional[str] = None
    parent: Optional[Prefab] = None


def new_string(prefab_h: int) -> SpawnString:
    return SpawnString(Prefab(prefab_h), None, None)


def _material_comp(cat) -> int:
    return (cat.component_hash(MATERIAL) if cat else None) or MATERIAL_HASH_FALLBACK


def get_material(p: Prefab, cat) -> Optional[int]:
    h = _material_comp(cat)
    for c in p.components:
        if c.hash == h and len(c.bits) >= 32:
            return int(c.bits[:32], 2)
    return None


def set_material(ss: SpawnString, p: Prefab, material_h: int, cat) -> None:
    h = _material_comp(cat)
    for c in p.components:
        if c.hash == h:
            c.bits = _u(material_h) + c.bits[32:]
            break
    else:
        p.components.append(Component(h, _u(material_h)))
    ss.original = None


def set_scale(ss: SpawnString, p: Prefab, value: float) -> None:
    p.scale = float(value)
    ss.original = None


def _live_embed(p: Prefab, embed_h: int, cat) -> Optional[Embed]:
    """The prefab's live embed with that hash, added if missing. None if the string has it destroyed."""
    for e in p.embeds:
        if e.hash == embed_h:
            if not e.alive:
                return None
            if e.components is None:
                e.components = []
            return e
    e = Embed(embed_h, 0, True, components=[])  # live embeds are written with size 0 in every archived string
    # The game drops embeds listed out of its own order, so the new one goes before the first that comes after it.
    order = {h: i for i, h in enumerate(cat.embed_order(p.hash))} if cat else {}
    mine = order.get(embed_h)
    at = len(p.embeds)
    if mine is not None:
        at = next((i for i, x in enumerate(p.embeds) if order.get(x.hash, -1) > mine), at)
    p.embeds.insert(at, e)
    return e


def _embed_comp(p: Prefab, embed_h: int, comp_h: int) -> Optional[Component]:
    for e in p.embeds:
        if e.hash == embed_h and e.alive:
            for c in e.components or []:
                if c.hash == comp_h:
                    return c
    return None


def get_piece_material(p: Prefab, embed_h: int, cat) -> Optional[int]:
    c = _embed_comp(p, embed_h, _material_comp(cat))
    return int(c.bits[:32], 2) if c is not None and len(c.bits) >= 32 else None


def set_piece_material(ss: SpawnString, p: Prefab, embed_h: int, material_h: int, cat) -> bool:
    """Gives one piece of a part (a lantern bar, a pouch flap) its own material. False if that piece is destroyed."""
    e = _live_embed(p, embed_h, cat)
    if e is None:
        return False
    h = _material_comp(cat)
    for c in e.components:
        if c.hash == h:
            c.bits = _u(material_h) + c.bits[32:]
            break
    else:
        e.components.append(Component(h, _u(material_h)))
    ss.original = None
    return True


def _dock_comp(cat) -> int:
    return (cat.component_hash(DOCK) if cat else None) or DOCK_HASH_FALLBACK


def get_dock(p: Prefab, dock_h: int, cat) -> Optional[Tuple[int, int]]:
    """(item type, quantity) a dock holds, or None when it holds nothing."""
    c = _embed_comp(p, dock_h, _dock_comp(cat))
    if c is None or len(c.bits) < 64:
        return None
    t, q = int(c.bits[:32], 2), int(c.bits[32:64], 2) ^ _SIGN
    return (t, q) if t and q > 0 else None


def set_dock(ss: SpawnString, p: Prefab, dock_h: int, type_h: int, quantity: int, cat) -> bool:
    """Fills a dock with `quantity` items of one type (arrows in a quiver, fuel in a lantern)."""
    e = _live_embed(p, dock_h, cat)
    if e is None:
        return False
    h = _dock_comp(cat)
    bits = _u(type_h) + _u(quantity ^ _SIGN) + _u(0 ^ _SIGN)  # type, quantity, child index 0
    for c in e.components:
        if c.hash == h:
            c.bits = bits + c.bits[96:]
            break
    else:
        e.components.append(Component(h, bits))
    ss.original = None
    return True


def clear_dock(ss: SpawnString, p: Prefab, dock_h: int, cat) -> None:
    h = _dock_comp(cat)
    for e in p.embeds:
        if e.hash == dock_h and e.alive and e.components:
            e.components = [c for c in e.components if c.hash != h]
    ss.original = None


def attach_string(ss: SpawnString, p: Prefab, slot_h: int, inner: SpawnString) -> Prefab:
    """Puts a copy of a whole string (with everything attached to it) into a slot or dock."""
    child = copy.deepcopy(inner.root)
    child.pos, child.rot = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)  # placed by the slot, not where it was saved
    _put(ss, p, slot_h, child)
    return child


def _put(ss: SpawnString, p: Prefab, slot_h: int, child: Prefab) -> None:
    for i, c in enumerate(p.children):
        if c.parent_hash == slot_h:
            p.children[i] = Child(slot_h, child)
            break
    else:
        p.children.append(Child(slot_h, child))
    ss.original = None


def attach(ss: SpawnString, p: Prefab, slot_h: int, prefab_h: int) -> Prefab:
    child = Prefab(prefab_h)
    _put(ss, p, slot_h, child)
    return child


def detach(ss: SpawnString, p: Prefab, child: Prefab) -> None:
    p.children = [c for c in p.children if c.prefab is not child]
    ss.original = None


def find_parent(ss: SpawnString, target: Prefab) -> Optional[Tuple[Prefab, int]]:
    """(parent prefab, slot hash) holding `target`, or None for the root."""
    stack = [ss.root]
    while stack:
        p = stack.pop()
        for c in p.children:
            if c.prefab is target:
                return p, c.parent_hash
            stack.append(c.prefab)
    return None


def tree(ss: SpawnString, cat) -> List[Row]:
    rows: List[Row] = []

    def mat(p):
        m = get_material(p, cat)
        return cat.material_name(m) if m is not None else None

    def walk(p: Prefab, depth: int, slot_h: Optional[int], parent: Optional[Prefab]):
        filled = {c.parent_hash for c in p.children}
        empty = [(h, label) for h, label, _kind in cat.slots(p.hash) if h not in filled]
        rows.append(Row(depth, p, slot_h, cat.prefab_name(p.hash), mat(p), empty,
                        cat.embed_name(parent.hash, slot_h) if parent is not None else None, parent))
        for c in p.children:
            walk(c.prefab, depth + 1, c.parent_hash, p)

    walk(ss.root, 0, None, None)
    return rows
