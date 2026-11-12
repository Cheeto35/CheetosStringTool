"""Flat 2D layout of a string: each part as a box at its real size, placed where its slot puts it.

Plain Python maths (the launcher has no numpy). Children carry no position of their own in a string; the game
snaps them to their slot, so a child's root goes where the slot is, offset by the child's own plug point.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

try:
    from .stringcodec import Prefab
except ImportError:  # loaded outside the package (tools)
    from stringcodec import Prefab

VIEWS = {"side": (0, 1, 1), "front": (2, 1, 1), "top": (0, 2, 1), "back": (0, 1, -1)}
SMALL = 0.1  # box size for parts with no known size


@dataclass
class Shape:
    prefab: Prefab
    label: str
    rect: Tuple[float, float, float, float]  # x0, y0, x1, y1 in world units (y up)
    slot_points: List[Tuple[int, float, float, bool]] = field(default_factory=list)
    depth: int = 0


# ---- tiny transform maths: (rotation quaternion x,y,z,w; translation; uniform scale) -------------

def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _qnorm(q):
    n = sum(c * c for c in q) ** 0.5
    return (0.0, 0.0, 0.0, 1.0) if n < 1e-9 else tuple(c / n for c in q)


def _qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # v' = v + 2w(q×v) + 2 q×(q×v)
    cx, cy, cz = y * vz - z * vy, z * vx - x * vz, x * vy - y * vx
    ccx, ccy, ccz = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (vx + 2 * (w * cx + ccx), vy + 2 * (w * cy + ccy), vz + 2 * (w * cz + ccz))


def _qinv(q):
    return (-q[0], -q[1], -q[2], q[3])


class _T:
    def __init__(self, rot=(0.0, 0.0, 0.0, 1.0), pos=(0.0, 0.0, 0.0), scale=1.0):
        self.rot, self.pos, self.scale = _qnorm(rot), tuple(pos), scale

    def apply(self, v):
        r = _qrot(self.rot, tuple(c * self.scale for c in v))
        return tuple(r[i] + self.pos[i] for i in range(3))

    def then(self, local: "_T") -> "_T":
        """self ∘ local: a transform expressed in self's space."""
        return _T(_qmul(self.rot, local.rot), self.apply(local.pos), self.scale * local.scale)

    def inverse(self) -> "_T":
        inv = _qinv(self.rot)
        s = 1.0 / self.scale if self.scale else 1.0
        p = _qrot(inv, self.pos)
        return _T(inv, tuple(-c * s for c in p), s)


def _pose(d: Optional[dict]) -> _T:
    if not d:
        return _T()
    return _T(tuple(d.get("rot") or (0, 0, 0, 1)), tuple(d.get("pos") or (0, 0, 0)))


# ---- layout -------------------------------------------------------------------------------------

def layout(root: Prefab, cat, view: str = "side") -> List[Shape]:
    ax, ay, flip = VIEWS.get(view, VIEWS["side"])
    shapes: List[Shape] = []

    def project(v):
        return (flip * v[ax], v[ay])

    def walk(p: Prefab, world: _T, depth: int):
        info = cat.prefabs.get(p.hash) or {}
        b = info.get("bounds")
        c, s = (tuple(b[:3]), tuple(b[3:6])) if b else ((0.0, 0.0, 0.0), (SMALL, SMALL, SMALL))
        pts = [project(world.apply(tuple(c[i] + (s[i] / 2 if (k >> i) & 1 else -s[i] / 2) for i in range(3))))
               for k in range(8)]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        filled = {ch.parent_hash for ch in p.children}
        slots = []
        for h, _label, _kind in cat.slots(p.hash):
            e = cat.embed(p.hash, h)
            x, y = project(world.apply(tuple(e.get("pos") or (0, 0, 0))))
            slots.append((h, x, y, h in filled))
        shapes.append(Shape(p, cat.prefab_name(p.hash), (min(xs), min(ys), max(xs), max(ys)), slots, depth))
        for ch in p.children:
            slot = _pose(cat.embed(p.hash, ch.parent_hash))
            child_info = cat.prefabs.get(ch.prefab.hash) or {}
            plug = _pose(child_info.get("plug")).inverse()
            local = slot.then(_T(plug.rot, plug.pos, ch.prefab.scale * plug.scale))
            walk(ch.prefab, world.then(local), depth + 1)

    walk(root, _T(scale=root.scale), 0)
    return shapes


def fit(shapes: List[Shape], width: int, height: int, margin: int = 16) -> Tuple[float, float, float]:
    """(scale, ox, oy) so that canvas x = ox + x*scale, canvas y = oy - y*scale fits every shape."""
    if not shapes:
        return 1.0, width / 2, height / 2
    x0 = min(s.rect[0] for s in shapes); x1 = max(s.rect[2] for s in shapes)
    y0 = min(s.rect[1] for s in shapes); y1 = max(s.rect[3] for s in shapes)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    scale = min((width - 2 * margin) / w, (height - 2 * margin) / h)
    ox = width / 2 - (x0 + x1) / 2 * scale
    oy = height / 2 + (y0 + y1) / 2 * scale
    return scale, ox, oy


def to_canvas(rect, scale, ox, oy):
    x0, y0, x1, y1 = rect
    return (ox + x0 * scale, oy - y1 * scale, ox + x1 * scale, oy - y0 * scale)


def point_to_canvas(x, y, scale, ox, oy):
    return ox + x * scale, oy - y * scale
