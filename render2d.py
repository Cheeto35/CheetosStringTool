"""Textured 2D drawing of a string: every mesh of every part as its outline, filled with its material's texture.

polygons() works in drawing units (metres, y up); render() paints them into a PIL image at canvas pixels and returns
the canvas-space polygons too, nearest last, for picking. Parts with no visual data are drawn as a plain box.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    Image = ImageChops = ImageDraw = None

try:
    from . import edits, layout2d
    from .stringcodec import Prefab
    from .visuals import hull
except ImportError:  # loaded outside the package (tools)
    import edits
    import layout2d
    from stringcodec import Prefab
    from visuals import hull

BG = "#16120e"
BOX = "#5a4a35"  # stand-in fill for parts with no visual data
SELECTED = "#ffd080"


@dataclass
class Poly:
    prefab: Prefab
    entity: int  # 0 for a stand-in box
    points: List[Tuple[float, float]]
    depth: float  # larger is nearer the viewer
    material: int  # 0: none, draw `color`
    color: str
    piece: bool = False  # the entity is a piece that takes its own material


def _axes(view):
    ax, ay, flip = layout2d.VIEWS.get(view, layout2d.VIEWS["side"])
    right = [0.0, 0.0, 0.0]
    up = [0.0, 0.0, 0.0]
    right[ax] = float(flip)
    up[ay] = 1.0
    out = (right[1] * up[2] - right[2] * up[1], right[2] * up[0] - right[0] * up[2], right[0] * up[1] - right[1] * up[0])
    return ax, ay, flip, out


def _material(p: Prefab, entity: int, default: int, cat, root_entity, pieces, own: int) -> int:
    """A piece shows its own material; any other mesh of an item that has a material of its own (`own` is that
    item's default, 0 if it has none) shows the item's material, as a blade's mesh does."""
    if entity in pieces:
        m = edits.get_piece_material(p, entity, cat)
        return m if m is not None else default
    if own and (entity == root_entity or not default):
        m = edits.get_material(p, cat)
        return m if m is not None else (default or own)
    return default


def polygons(root: Prefab, cat, vis, view: str = "side") -> List[Poly]:
    ax, ay, flip, out = _axes(view)
    polys: List[Poly] = []
    for s in layout2d.layout(root, cat, view):
        p = s.prefab
        parts = vis.parts(p.hash) if vis else []
        if not parts:
            x0, y0, x1, y1 = s.rect
            m = edits.get_material(p, cat) or 0
            polys.append(Poly(p, 0, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], -1e9 + s.depth, m, BOX))
            continue
        info = cat.prefabs.get(p.hash) or {}
        root_entity = info.get("root_entity")
        pieces = {h for h, _ in cat.pieces(p.hash)}
        own = next((q.material for q in parts if q.entity == root_entity and q.material), 0)
        if not own and cat.has_own_material(p.hash) and edits.get_material(p, cat) is not None:
            own = edits.get_material(p, cat)
        for part in parts:
            world = [s.world.apply(v) for v in part.points]
            pts = hull([(flip * v[ax], v[ay]) for v in world])
            if len(pts) < 3:
                continue
            depth = sum(v[0] * out[0] + v[1] * out[1] + v[2] * out[2] for v in world) / len(world)
            m = _material(p, part.entity, part.material, cat, root_entity, pieces, own)
            polys.append(Poly(p, part.entity, pts, depth, m, part.color, part.entity in pieces))
    polys.sort(key=lambda q: q.depth)
    return polys


def fit_points(polys: List[Poly], width: int, height: int, margin: int = 24) -> Tuple[float, float, float]:
    pts = [pt for q in polys for pt in q.points]
    if not pts:
        return 1.0, width / 2, height / 2
    x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
    y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    scale = min((width - 2 * margin) / w, (height - 2 * margin) / h)
    return scale, width / 2 - (x0 + x1) / 2 * scale, height / 2 + (y0 + y1) / 2 * scale


def _darker(hex_color: str, k: float = 0.5) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


class _Tiles:
    """A tiled copy of each swatch, big enough to crop any polygon's box from."""

    def __init__(self, vis, w, h):
        self.vis, self.w, self.h, self.cache = vis, w, h, {}

    def get(self, material):
        if material not in self.cache:
            sw = self.vis.swatch(material) if (self.vis and material) else None
            if sw is None:
                self.cache[material] = None
            else:
                t = Image.new("RGB", (self.w + sw.width, self.h + sw.height))
                for x in range(0, t.width, sw.width):
                    for y in range(0, t.height, sw.height):
                        t.paste(sw, (x, y))
                self.cache[material] = t
        return self.cache[material]


def render(root: Prefab, cat, vis, view: str, width: int, height: int, transform=None,
           selected: Optional[Prefab] = None, highlight=(), margin: int = 24, grid: bool = False, hover=()):
    """(PIL image, polygons in canvas pixels, nearest last).

    The selected part is tinted and outlined in bright amber; `highlight` narrows that to some of its entities
    (pieces), and `hover` entities get a lighter tint."""
    polys = polygons(root, cat, vis, view)
    scale, ox, oy = transform or fit_points(polys, width, height, margin)
    out: List[Poly] = []
    for q in polys:
        out.append(Poly(q.prefab, q.entity, [(ox + x * scale, oy - y * scale) for x, y in q.points], q.depth,
                        q.material, q.color, q.piece))
    if Image is None:
        return None, out
    img = Image.new("RGB", (width, height), BG)
    tiles = _Tiles(vis, width, height)
    draw = ImageDraw.Draw(img)
    if grid:
        for x in range(0, width, 20):
            draw.line([(x, 0), (x, height)], fill="#221c15")
        for y in range(0, height, 20):
            draw.line([(0, y), (width, y)], fill="#221c15")
    for q in out:
        xs = [x for x, _ in q.points]
        ys = [y for _, y in q.points]
        bx0, by0 = max(int(min(xs)), 0), max(int(min(ys)), 0)
        bx1, by1 = min(int(max(xs)) + 1, width), min(int(max(ys)) + 1, height)
        if bx1 <= bx0 or by1 <= by0:
            continue
        flat = vis.material_color(q.material) if (vis and q.material) else None
        flat = flat or q.color
        tex = tiles.get(q.material)
        size = (bx1 - bx0, by1 - by0)
        if size[0] * size[1] > 4:
            mask = Image.new("L", size, 0)
            ImageDraw.Draw(mask).polygon([(x - bx0, y - by0) for x, y in q.points], fill=255)
            fill = tex.crop((bx0, by0, bx1, by1)) if tex is not None else Image.new("RGB", size, flat)
            img.paste(fill, (bx0, by0), mask)
            _shade(img, mask, bx0, by0)
        else:
            draw.polygon(q.points, fill=flat)
        draw.line(q.points + [q.points[0]], fill=_darker(flat), width=1)
    if selected is not None:  # on top of everything, so the selection reads through whatever is in front of it
        mine = [q for q in out if q.prefab is selected]
        lit = [q for q in mine if not highlight or q.entity in highlight]
        hov = [q for q in mine if q.entity in hover and q not in lit]
        for group, alpha in ((hov, 60), (lit, 110)):
            for q in group:
                _tint(img, q.points, SELECTED, alpha)
        for q in hov:
            draw.line(q.points + [q.points[0]], fill="#fff1c8", width=2)
        for q in lit:
            draw.line(q.points + [q.points[0]], fill="#000000", width=5)
        for q in lit:
            draw.line(q.points + [q.points[0]], fill=SELECTED, width=3)
    return img, out


def _tint(img, points, color, alpha):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    x0, y0 = max(int(min(xs)), 0), max(int(min(ys)), 0)
    x1, y1 = min(int(max(xs)) + 1, img.width), min(int(max(ys)) + 1, img.height)
    if x1 <= x0 or y1 <= y0:
        return
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in points], fill=alpha)
    img.paste(color, (x0, y0, x1, y1), mask)


_GRADIENT = None


def _shade(img, mask, x0, y0):
    """Soft light from above: the top of each part a little brighter, the bottom a little darker."""
    global _GRADIENT
    if _GRADIENT is None:
        _GRADIENT = Image.linear_gradient("L")  # 256x256, black at the top to white at the bottom
    g = _GRADIENT.resize(mask.size)
    dark = ImageChops.multiply(g.point(lambda v: int(v * 0.32)), mask)
    light = ImageChops.multiply(g.point(lambda v: int((255 - v) * 0.14)), mask)
    img.paste((0, 0, 0), (x0, y0, x0 + mask.width, y0 + mask.height), dark)
    img.paste((255, 255, 255), (x0, y0, x0 + mask.width, y0 + mask.height), light)


def _inside(points, x, y) -> bool:
    inside = False
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def pick(polys: List[Poly], x: float, y: float, only: Optional[Prefab] = None) -> Optional[Poly]:
    """The nearest polygon under the point (optionally only those of one part)."""
    for q in reversed(polys):
        if (only is None or q.prefab is only) and _inside(q.points, x, y):
            return q
    return None
