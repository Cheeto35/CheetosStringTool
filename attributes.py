"""Item attributes: the saved values of an item's components (a potion's liquid, a dynamite fuse, durability, ...)
read and changed with the game's own layouts (components.py), plus friendly names for the ones players care about.

A component the string doesn't carry means the item keeps its normal values; changing one writes it in. One the
string carries from an older game version (a different layout) is shown but not changed.
"""
import re
from dataclasses import dataclass
from typing import Any, List, Optional

try:
    from . import components as C
    from . import edits
    from .stringcodec import Component, Prefab, SpawnString
except ImportError:  # loaded outside the package (tools)
    import components as C
    import edits
    from stringcodec import Component, Prefab, SpawnString

# handled elsewhere in the String Builder, or only meaningful to the game itself
HIDDEN = {"NetworkRigidbody", "Pickup", "PhysicalMaterialPart", "PickupDock", "SentGift"}

# component -> (icon and title, {field path: label}, fields to leave out); paths are dotted ("customData.color")
FRIENDLY = {
    "LiquidContainer": ("🧪 Liquid", {
        "hasContent": "Has liquid in it", "contentLevel": "Amount", "isCustom": "Custom mix instead of a preset",
        "preset": "Preset liquid", "customData": "Custom mix", "canAddTo": "Can be filled",
        "canRemoveFrom": "Can be poured out", "customData.color": "Colour",
        "customData.isConsumableThroughSkin": "Works when splashed on skin", "customData.liquidVisualData": "Looks like",
        "customData.effects": "Effects", "customData.effects.definition": "Effect",
        "customData.effects.strengthMultiplier": "Strength", "customData.chunks": "Floating bits"}, ()),
    "Fuse": ("🧨 Fuse", {"isLit": "Lit", "currentFuseAmount": "Fuse left (1 = full)", "isFinished": "Already went off"}, ()),
    "ColoredExplosive": ("🎆 Firework colour", {"colorIndex": "Colour number"}, ()),
    "DurabilityModule": ("🛡 Durability", {"integrity": "Condition (1 = new, 0 = broken)"}, ()),
    "BasicDecay": ("⏳ Despawning", {"isDisabled": "Never despawns"}, ("timelineEntry",)),
    "Cookable": ("🍖 Cooking", {"cookedProgress": "Cooked (0 to 1)", "burntProgress": "Burnt (0 to 1)"}, ()),
    "Enchantable": ("✨ Enchantments", {"enchantments": "Enchantments"}, ()),
    "Fire": ("🔥 Fire", {"fuelConsumptionProgress": "Fuel used (0 to 1)"}, ()),
    "HeatSourceBase": ("🔥 Heat", {"isLit": "Lit", "progress": "Progress"}, ("time",)),
    "Mould": ("🧱 Mould", {"definition": "Shape", "usage": "Uses"}, ()),
    "StatManager": ("📊 Stats", {"stats": "Stats", "stats.definition": "Stat", "stats.baseFlat": "Value",
                                "modifiers": "Timed changes", "indirectModifiers": "Effects over time"}, ()),
    "LevelStatModifier": ("📈 Level", {"currentLevel": "Level"}, ()),
    "CookingPot": ("🍲 Cooking pot", {"currentStage": "Stage"}, ()),
    "StewManager": ("🍲 Stew", {"ingredients": "Ingredients", "garnishes": "Garnishes", "liquidBase": "Base liquid"}, ()),
    "HealthBasedDigable": ("⛏ Dig health", {"currentHealth": "Health left"}, ()),
}
ORDER = list(FRIENDLY)

# values a component starts with when the player first changes it (otherwise blank: off, 0, empty)
STARTING = {
    "LiquidContainer": {"canAddTo": True, "canRemoveFrom": True, "hasContent": True, "contentLevel": 1},
    "Fuse": {"currentFuseAmount": 1.0},
    "DurabilityModule": {"integrity": 1.0},
    "BasicDecay": {"isDisabled": True},
}


def pretty(name: str) -> str:
    """'currentFuseAmount' -> 'Current fuse amount'."""
    name = re.sub(r"<(\w+)>k__BackingField", r"\1", name)
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").split()
    text = " ".join(words).lower()
    return text[:1].upper() + text[1:]


def title(component: str) -> str:
    f = FRIENDLY.get(component)
    return f[0] if f else "⚙ " + pretty(component)


def label(component: str, path: str) -> str:
    f = FRIENDLY.get(component)
    if f and path in f[1]:
        return f[1][path]
    return pretty(path.split(".")[-1])


def hidden_field(component: str, path: str) -> bool:
    f = FRIENDLY.get(component)
    return bool(f) and path in f[2]


@dataclass
class Attr:
    """One component an item part saves, and where its values stand in the string."""
    embed_h: int  # the part (embedded entity) it belongs to; the item's own part is its root entity
    component: str
    comp_h: int
    part_name: str
    friendly: bool
    status: str  # "default" (not in the string), "set", "old" (an older layout), "unreadable"
    value: Optional[dict]


def _root(cat, p: Prefab) -> Optional[int]:
    info = cat.prefabs.get(p.hash) or {}
    return info.get("root_entity")


def _find(p: Prefab, embed_h: int, comp_h: int, root_h) -> Optional[Component]:
    if embed_h == root_h:
        return next((c for c in p.components if c.hash == comp_h), None)
    return edits._embed_comp(p, embed_h, comp_h)


def string_versions(ss: SpawnString) -> Optional[dict]:
    """{component hash: version} from the string's versioning tail, or None when it has none."""
    if not ss.versioning:
        return None
    nums = [int(x) for x in ss.versioning.rstrip(",").split(",") if x]
    if not nums:
        return None
    return dict(zip(nums[1:1 + 2 * nums[0]:2], nums[2:2 + 2 * nums[0]:2]))


def _current(cat) -> dict:
    v = cat.versioning()
    return dict(zip(v[0::2], v[1::2]))


def list_attrs(ss: SpawnString, p: Prefab, cat, schema: C.Schema, fresh: bool = False) -> List[Attr]:
    """The components this item's parts save that have a known layout, friendly ones first."""
    info = cat.prefabs.get(p.hash) or {}
    root_h = info.get("root_entity")
    order = info.get("embed_order") or [int(h) for h in info.get("embeds", {})]
    saved_with = None if fresh else string_versions(ss)
    current = _current(cat)
    out = []
    for eh in order:
        e = info["embeds"].get(str(eh)) or {}
        for name in e.get("saved", []):
            if name in HIDDEN or schema.fields(name) is None:
                continue
            ch = cat.component_hash(name)
            if ch is None:
                continue
            c = _find(p, eh, ch, root_h)
            if c is None:
                status, value = "default", None
            elif saved_with is not None and saved_with.get(ch, current.get(ch)) != current.get(ch):
                status, value = "old", None
            else:
                value = c.layout.value if isinstance(c.layout, C.Layout) else C.decode(schema, name, c.bits, c.start)
                status = "set" if value is not None else "unreadable"
            part = cat.embed_name(p.hash, eh) if eh != root_h else cat.prefab_name(p.hash)
            out.append(Attr(eh, name, ch, part, name in FRIENDLY, status, value))
    out.sort(key=lambda a: (not a.friendly, ORDER.index(a.component) if a.friendly else 0))
    return out


CUSTOM_MIX = "Alta.Liquid.LiquidContainerSaveData+CustomData"
MIX_LOOK = "Non Recipe Stew Raw Liquid Visual Data"  # the look the archived custom potions use


def starting_mix(schema: C.Schema, refs: dict) -> dict:
    """A custom potion mix to fill in: white, fully visible, with the usual potion look and no effects yet."""
    mix = C.blank_class(schema, CUSTOM_MIX)
    mix["color"] = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    look = next((h for h, n in ref_names(refs, "LiquidVisualData") if n == MIX_LOOK), 0)
    mix["liquidVisualData"] = look
    return mix


def starting_value(schema: C.Schema, component: str) -> dict:
    v = C.blank_component(schema, component)
    v.update(STARTING.get(component, {}))
    return v


def _insert_at(comps: List[Component], name: str, saved: List[str], cat) -> int:
    """Where a new component goes: in the order the part saves its components."""
    mine = saved.index(name) if name in saved else len(saved)
    for i, c in enumerate(comps):
        other = cat.component_name(c.hash)
        if other in saved and saved.index(other) > mine:
            return i
    return len(comps)


def _note_version(ss: SpawnString, comp_h: int, cat) -> None:
    """A component written into a string with a versioning tail must be listed in it, at the current version."""
    have = string_versions(ss)
    if have is None or comp_h in have:
        return
    ver = _current(cat).get(comp_h)
    if ver is None:
        return
    have[comp_h] = ver
    flat = [n for h, v in have.items() for n in (h, v)]
    ss.versioning = ",".join(str(n) for n in [len(have)] + flat) + ","


def set_values(ss: SpawnString, p: Prefab, a: Attr, value: dict, cat, schema: C.Schema) -> bool:
    """Writes a component's values into the string; False when its part was removed or the values don't fit."""
    root_h = _root(cat, p)
    info = cat.prefabs.get(p.hash) or {}
    saved = (info.get("embeds", {}).get(str(a.embed_h)) or {}).get("saved", [])
    try:
        bits = C.encode(schema, a.component, value)
    except (C.LayoutError, KeyError, TypeError, ValueError, OverflowError):
        return False
    if a.embed_h == root_h:
        comps = p.components
    else:
        e = edits._live_embed(p, a.embed_h, cat)
        if e is None:
            return False
        comps = e.components
    c = next((c for c in comps if c.hash == a.comp_h), None)
    if c is None:
        c = Component(a.comp_h, bits)
        comps.insert(_insert_at(comps, a.component, saved, cat), c)
    c.bits = bits
    c.layout = C.Layout(schema, a.component, value) if schema.has_text(a.component) else None
    _note_version(ss, a.comp_h, cat)
    a.status, a.value = "set", value
    ss.original = None
    return True


def reset(ss: SpawnString, p: Prefab, a: Attr, cat) -> None:
    """Takes the component out of the string, so the item keeps its normal values."""
    root_h = _root(cat, p)
    if a.embed_h == root_h:
        p.components[:] = [c for c in p.components if c.hash != a.comp_h]
    else:
        for e in p.embeds:
            if e.hash == a.embed_h and e.alive and e.components:
                e.components[:] = [c for c in e.components if c.hash != a.comp_h]
    a.status, a.value = "default", None
    ss.original = None


def summary(attrs: List[Attr]) -> str:
    """'🧪 Liquid · 🧨 Fuse' for the item's friendly attributes."""
    seen = []
    for a in attrs:
        if a.friendly and title(a.component) not in seen:
            seen.append(title(a.component))
    return " · ".join(seen)


def ref_names(refs: dict, type_name: str) -> List[Any]:
    """(hash, name) for a kind of game asset, by name."""
    return sorted(((int(h), n) for h, n in (refs.get(type_name) or {}).items()), key=lambda x: x[1].lower())
