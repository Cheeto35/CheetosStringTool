"""What items look like (data/visuals.json): each mesh's outline points and colour, and a texture swatch per material.

The data comes from a game client, since a server has no meshes or textures. Points are in the item's own space.
"""
import base64
import io
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageOps
except ImportError:  # no Pillow: plain colours only
    Image = ImageOps = None


@dataclass
class Part:
    entity: int  # the embedded entity the mesh belongs to (a piece, or the item itself)
    material: int  # the material it has when nothing in the string changes it; 0 if it has none
    color: str  # the mesh's own colour, for meshes without a material
    points: List[Tuple[float, float, float]]


def hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


class Visuals:
    def __init__(self, data: dict):
        self._materials: Dict[int, list] = {int(h): m for h, m in data.get("materials", {}).items()}
        self._prefabs: Dict[str, list] = data.get("prefabs", {})
        self._parts: Dict[int, List[Part]] = {}
        self._swatches: Dict[int, object] = {}
        self._aliases: Dict[int, Tuple[Optional[int], Optional[str]]] = {}

    @classmethod
    def load(cls, path: str) -> "Visuals":
        try:
            with open(path, encoding="utf-8") as f:
                return cls(json.load(f))
        except (OSError, ValueError):
            return cls({})

    @classmethod
    def empty(cls) -> "Visuals":
        return cls({})

    def parts(self, prefab_h: int) -> List[Part]:
        if prefab_h not in self._parts:
            out = []
            for e, m, c, p in self._prefabs.get(str(prefab_h), []):
                pts = [(p[i] / 1000.0, p[i + 1] / 1000.0, p[i + 2] / 1000.0) for i in range(0, len(p) - 2, 3)]
                out.append(Part(int(e), int(m or 0), c, pts))
            self._parts[prefab_h] = out
        return self._parts[prefab_h]

    def has(self, prefab_h: int) -> bool:
        return str(prefab_h) in self._prefabs

    def alias(self, h: int, copies: Optional[int], colour: Optional[str] = None) -> None:
        """Draws material h (from a mod) like the game material it copies, recoloured when it has its own colour."""
        if h not in self._materials:
            self._aliases[h] = (copies, colour)
            self._swatches.pop(h, None)

    def material_color(self, h: int) -> Optional[str]:
        m = self._materials.get(h)
        if m:
            return m[1]
        if h in self._aliases:
            copies, colour = self._aliases[h]
            return colour or (self.material_color(copies) if copies in self._materials else None)
        return None

    def swatch(self, h: int):
        """The material's 32x32 texture swatch (a PIL image), or None when unknown or Pillow is missing."""
        if h in self._swatches:
            return self._swatches[h]
        m = self._materials.get(h)
        img = None
        if m is None and h in self._aliases and Image is not None:
            copies, colour = self._aliases[h]
            base = self.swatch(copies) if copies in self._materials else None
            if base is not None and colour:
                img = ImageOps.colorize(ImageOps.autocontrast(base.convert("L")), "#000000", "#ffffff", mid=colour)
            elif base is not None:
                img = base
            elif colour:
                img = Image.new("RGB", (32, 32), colour)
        elif m and Image is not None:
            if m[2]:
                img = Image.open(io.BytesIO(base64.b64decode(m[2]))).convert("RGB")
            else:
                img = Image.new("RGB", (32, 32), m[1])
        self._swatches[h] = img
        return img
