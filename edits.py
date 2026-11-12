"""Changes to a spawn string (attach, detach, material, scale) and the labelled parts tree the tab shows."""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from stringcodec import Child, Component, Prefab, SpawnString, _u

MATERIAL = "PhysicalMaterialPart"
MATERIAL_HASH_FALLBACK = 272188517  # the component hash used by every archived string


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


def attach(ss: SpawnString, p: Prefab, slot_h: int, prefab_h: int) -> Prefab:
    child = Prefab(prefab_h)
    for i, c in enumerate(p.children):
        if c.parent_hash == slot_h:
            p.children[i] = Child(slot_h, child)
            break
    else:
        p.children.append(Child(slot_h, child))
    ss.original = None
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
