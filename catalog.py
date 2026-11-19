"""Item knowledge from data/items.json: names for prefabs, slots and materials, search, and what fits where."""
import json
import os
import re
from typing import Dict, List, Optional, Tuple

# Community names for the game's internal metal names.
METAL_NAMES = {
    "Orchi Alloy": "Viridium",
    "Evinon Steel Alloy": "Valyan",
    "Carsi Alloy": "Palladium",
    "White Gold Alloy": "Electrum",
    "Red Iron Alloy": "Red Iron",
    "Darksteel Alloy": "Darksteel",
}


def _slot_label(name: str) -> str:
    name = re.sub(r"\s*\(\d+\)$", "", name).strip()
    if name.lower().startswith("slot "):
        return name[5:].strip() + " slot"
    return name


class Catalog:
    def __init__(self, data: dict):
        self.data = data
        self.build = data.get("game_build", "?")
        self.prefabs: Dict[int, dict] = {int(h): p for h, p in data.get("prefabs", {}).items()}
        self._materials = {int(h): n for h, n in data.get("materials", {}).items()}
        self._components = {int(h): n for h, n in data.get("components", {}).items()}
        self._component_by_name = {n: h for h, n in self._components.items()}
        self._item_types = {int(h): n for h, n in data.get("item_types", {}).items()}
        self._sorted = sorted(self.prefabs.items(), key=lambda kv: kv[1]["name"].lower())

    @classmethod
    def load(cls, path: str) -> "Catalog":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        types = os.path.join(os.path.dirname(path), "item_types.json")
        if os.path.exists(types):
            with open(types, encoding="utf-8") as f:
                data["item_types"] = json.load(f).get("types", {})
        return cls(data)

    @classmethod
    def empty(cls) -> "Catalog":
        return cls({})

    # ---- names ---------------------------------------------------------------------------------
    def prefab_name(self, h: int) -> str:
        p = self.prefabs.get(h)
        return p["name"] if p else "Unknown item #%d" % h

    def embed(self, prefab_h: int, embed_h: int) -> Optional[dict]:
        p = self.prefabs.get(prefab_h)
        return p["embeds"].get(str(embed_h)) if p else None

    def embed_name(self, prefab_h: int, embed_h: int) -> str:
        e = self.embed(prefab_h, embed_h)
        return _slot_label(e["name"]) if e else "Unknown slot #%d" % embed_h

    def material_name(self, h: int) -> str:
        n = self._materials.get(h)
        if n is None:
            return "Unknown material #%d" % h
        return "%s (%s)" % (METAL_NAMES[n], n) if n in METAL_NAMES else n

    def material_short(self, h: int) -> str:
        n = self._materials.get(h)
        return METAL_NAMES.get(n, n) if n is not None else "Unknown material #%d" % h

    def materials(self) -> List[Tuple[int, str]]:
        return sorted(((h, self.material_name(h)) for h in self._materials), key=lambda x: x[1].lower())

    def component_hash(self, name: str) -> Optional[int]:
        return self._component_by_name.get(name)

    def component_name(self, h: int) -> str:
        return self._components.get(h, "Unknown part data #%d" % h)

    def versioning(self) -> List[int]:
        return list(self.data.get("versioning", []))

    def embed_order(self, prefab_h: int) -> List[int]:
        """The item's embedded entities in the game's order; strings must list them in this order."""
        p = self.prefabs.get(prefab_h)
        return list(p.get("embed_order") or [int(h) for h in p["embeds"]]) if p else []

    # ---- pieces and dock contents --------------------------------------------------------------
    MATERIAL = "PhysicalMaterialPart"

    def pieces(self, prefab_h: int) -> List[Tuple[int, str]]:
        """The sub-parts of an item (lantern bars, pouch flap...) that carry their own material.

        Only parts the game saves a material for: giving one to any other part (the item's fire, its own entity)
        makes the game drop every part listed after it."""
        p = self.prefabs.get(prefab_h)
        if not p:
            return []
        out = []
        for h, e in p["embeds"].items():
            if self.MATERIAL not in e.get("saved", []) or int(h) == p.get("root_entity"):
                continue
            label = re.sub(r"\s+", " ", e["name"].replace("_", " ")).strip()
            out.append((int(h), label[:1].upper() + label[1:]))
        return sorted(out, key=lambda x: x[1].lower())

    def has_own_material(self, prefab_h: int) -> bool:
        """Whether the item itself (not just its pieces) has a material, so "Whole part" applies."""
        p = self.prefabs.get(prefab_h)
        if not p or p.get("root_entity") is None:
            return True  # nothing known: leave it to the player
        own = p["embeds"].get(str(p["root_entity"]))
        return own is None or self.MATERIAL in own.get("saved", [self.MATERIAL])

    def item_types(self) -> List[Tuple[int, str]]:
        """Item types a dock can hold (docks store these, not prefab hashes)."""
        return sorted(self._item_types.items(), key=lambda x: x[1].lower())

    def item_type_name(self, h: int) -> str:
        return self._item_types.get(h, "Unknown item type #%d" % h)

    # ---- slots and search ----------------------------------------------------------------------
    def slots(self, prefab_h: int) -> List[Tuple[int, str, str]]:
        p = self.prefabs.get(prefab_h)
        if not p:
            return []
        out = [(int(h), _slot_label(e["name"]), e["kind"]) for h, e in p["embeds"].items() if e["kind"] in ("slot", "dock")]
        return sorted(out, key=lambda s: s[1].lower())

    def fits(self, prefab_h: int, embed_h: int, item_h: int) -> bool:
        """True if the item normally goes in that slot. Docks take anything (no rule in the data)."""
        e = self.embed(prefab_h, embed_h)
        if not e or e["kind"] != "slot":
            return True
        item = self.prefabs.get(item_h)
        return bool(item and set(item.get("plug_types", [])) & set(e.get("slot_types", [])))

    @staticmethod
    def hidden(p: dict) -> bool:
        """Invisible world objects (logic, spawners, growth stages, teleporter nodes): no size, or "(...)" names."""
        return not p.get("bounds") or p["name"].startswith("(")

    def search(self, query: str, fits: Optional[Tuple[int, int]] = None, limit: int = 200,
               include_hidden: bool = False) -> List[Tuple[int, str]]:
        words = [w for w in (query or "").lower().split() if w]
        out = []
        for h, p in self._sorted:
            if not include_hidden and self.hidden(p):
                continue
            name = p["name"].lower()
            if all(w in name or w == str(h) for w in words) and (fits is None or self.fits(fits[0], fits[1], h)):
                out.append((h, p["name"]))
                if len(out) >= limit:
                    break
        return out
