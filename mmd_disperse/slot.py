"""The slot machine (老虎机开奖, 1.15): a cover (cover.py, style SLOT). A slot machine drops from above the picture
onto the stage in front of the dancer, bouncing, big enough to hide all of her; its lever is pulled, the three reels
spin and stop one after another on the beats (with Sync to Beat; else GAP apart), the last on the big moment: 7 7 7.
The outfits swap behind it, its lights flash and coins gush out of its tray onto the floor; then it rises off the
picture. With Cherries First the first pull is a miss (cherry, cherry, bell) and the lever is pulled again: the slot
machine of Ensemble Stars!! Music's seventh anniversary MV (cherries tease, 777 brings the new outfit).

The cabinet is one mesh of ours, a unit tall and facing -Y (its width a share of that), each face with a colour (the
Col corner colour), how metallic and how bright it is and which bulbs it is (Phase: 0 or 1, -1 for the rest); the
reels and the lever are objects of their own (children of it) turning about X. Its material (materials' SLOT) reads
the object's mmdd_blink (the bulbs taking turns) and mmdd_jackpot (all of them flashing); a reel's (REEL) reads
mmdd_blur (the symbols smeared into streaks at speed). The symbols are flat shapes bent onto the reels: polygons of
our own (cherries, bell, star, heart) and the 7 and BAR in Blender's own font (3.6's has no ★ ♥).
"""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, geometry

from . import beats, materials

# timing (seconds)
DROP = 0.4  # it falls from above the picture onto the stage in front of her (bouncing) in this long ...
PULL = 0.15  # ... the lever is pulled this long after it lands ...
SPIN_AFTER = 0.12  # ... and the reels spin from this long after the pull ...
SPIN = 0.6  # ... for at least this long before the first of them stops
GAP = 0.45  # seconds between the stops without beats (on the beats with Sync to Beat) ...
LEAST, MOST = 0.22, 1.1  # ... beats closer together than the first are skipped, farther apart than the second ignored
SETTLE = 0.28  # a reel slows down and stops (overshooting a little) over this long
TEASE = 0.45  # with Cherries First: after the miss the lever is pulled again this long after the last stop
HOLD = 0.55  # the jackpot shines this long after the moment ...
RISE = 0.45  # ... then the machine rises off the picture in this long
AHEAD = 0.55  # it stands this far in front of her (model heights) ...
NEAR = 0.15  # ... hiding all of her for this long (seconds) either side of the moment, when the outfits swap
SPEED = 2.4  # turns a second while the reels spin
COINS = 160
COIN_GUSH = 0.6  # seconds the coins gush out for, from the moment on ...
COIN_LIFE = 2.6  # ... each one lying on the floor till its life is over
P_START = "mmdd_slot_start"  # on the cabinet: the frame it starts to fall (the panel warns before the scene)
BACK_SLOPE = 4.70158  # a BACK EASE_OUT key's speed at its start, a share of the even speed over the same travel

SLOTS = ("SEVEN", "CHERRY", "BAR", "BELL", "STAR", "HEART", "CHERRY", "BAR", "BELL", "STAR")  # round each reel
JACKPOT = (0, 0, 0)  # the slots the reels stop on at the moment: 7 7 7 ...
MISS = (1, 6, 3)  # ... and at the miss of Cherries First: cherry, cherry, bell
WIDE = 0.62  # the cabinet's width for its unit height; wider when she is
WINDOW = (0.41, 0.70)  # the band of the reel windows (cabinet heights)
DEPTH = 0.36  # how deep the cabinet is

RED = (0.85, 0.05, 0.04, 1.0)
DARK_RED = (0.35, 0.01, 0.01, 1.0)
BLACK = (0.02, 0.02, 0.025, 1.0)
WHITE = (0.95, 0.95, 0.92, 1.0)
GREEN = (0.08, 0.45, 0.08, 1.0)
GOLD = (1.0, 0.62, 0.08, 1.0)
DARK_GOLD = (0.45, 0.22, 0.02, 1.0)
YELLOW = (1.0, 0.85, 0.1, 1.0)
ORANGE = (0.95, 0.35, 0.02, 1.0)
PINK = (1.0, 0.18, 0.45, 1.0)
CREAM = (0.92, 0.88, 0.78, 1.0)
TRIM = (1.0, 0.66, 0.2, 1.0)
DARK = (0.015, 0.012, 0.012, 1.0)
CHROME = (0.8, 0.8, 0.82, 1.0)
BULB = (1.0, 0.85, 0.45, 1.0)
SIGN = (0.25, 0.01, 0.06, 1.0)
LETTERS = (1.0, 0.9, 0.2, 1.0)
LINE = (1.0, 0.1, 0.05, 1.0)


# --------------------------------------------------------------------------- flat shapes (a unit square)

def _circle(cx, cy, r, n=28):
    return [(cx + r * math.cos(2.0 * math.pi * i / n), cy + r * math.sin(2.0 * math.pi * i / n)) for i in range(n)]


def _ellipse(cx, cy, rx, ry, angle, n=24):
    ca, sa = math.cos(angle), math.sin(angle)
    out = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + ca * x - sa * y, cy + sa * x + ca * y))
    return out


def _star(cx, cy, r_out, r_in, n=5):
    out = []
    for i in range(2 * n):
        r = r_out if i % 2 == 0 else r_in
        a = 0.5 * math.pi + math.pi * i / n
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def _heart(cx, cy, size, n=48):
    out = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        x = 16.0 * math.sin(t) ** 3
        y = 13.0 * math.cos(t) - 5.0 * math.cos(2.0 * t) - 2.0 * math.cos(3.0 * t) - math.cos(4.0 * t)
        out.append((cx + size * x / 17.0, cy + size * (y + 2.5) / 17.0))
    return out


def _rounded(cx, cy, w, h, r, n=6):
    out = []
    for qx, qy, a0 in ((w / 2 - r, h / 2 - r, 0.0), (-w / 2 + r, h / 2 - r, 90.0), (-w / 2 + r, -h / 2 + r, 180.0),
                       (w / 2 - r, -h / 2 + r, 270.0)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            out.append((cx + qx + r * math.cos(a), cy + qy + r * math.sin(a)))
    return out


def _strip(points, width):
    """A line through `points` made `width` thick (the cherries' stems)."""
    left, right = [], []
    for i, (x, y) in enumerate(points):
        a, b = points[max(i - 1, 0)], points[min(i + 1, len(points) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d * width / 2, dx / d * width / 2
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    return left + right[::-1]


def _bell(cx, cy, s):
    side = ((0.0, 0.5), (0.12, 0.49), (0.22, 0.42), (0.28, 0.28), (0.3, 0.05), (0.34, -0.12), (0.44, -0.24),
            (0.5, -0.3), (0.0, -0.3))
    right = [(cx + s * x, cy + s * y) for x, y in side]
    return right + [(cx - s * x, cy + s * y) for x, y in reversed(side[1:-1])]


def glyphs(text, size, cx=0.0, cy=0.0, offset=0.0):
    """(points, triangles) of `text` in Blender's own font, `size` tall, its middle at (cx, cy); thicker by
    `offset`."""
    cu = bpy.data.curves.new("MMDD Glyph", "FONT")
    cu.body = text
    cu.font = bpy.data.fonts.load("<builtin>")
    cu.offset = offset
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    ob = bpy.data.objects.new("MMDD Glyph", cu)
    bpy.context.scene.collection.objects.link(ob)
    try:
        deps = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        pts = [(v.co.x, v.co.y) for v in me.vertices]
        tris = [tuple(t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
    if not pts:
        return [], []
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    k = size / max(max(ys) - min(ys), 1e-9)
    mx, my = 0.5 * (max(xs) + min(xs)), 0.5 * (max(ys) + min(ys))
    return [(cx + k * (x - mx), cy + k * (y - my)) for x, y in pts], tris


def _filled(shape):
    """(points, triangles) of a polygon, or of what glyphs() gave."""
    if isinstance(shape, tuple):
        return shape
    tris = geometry.tessellate_polygon([[Vector((x, y, 0.0)) for x, y in shape]])
    return shape, [tuple(t) for t in tris]


def _refined(pts, tris, longest=0.08):
    """The triangles split in four till no side is longer than `longest` (bent onto a reel, a shape keeps to it)."""
    pts = [tuple(p) for p in pts]
    halves = {}
    out = []
    todo = list(tris)

    def half(a, b):
        key = (min(a, b), max(a, b))
        if key not in halves:
            pa, pb = pts[a], pts[b]
            pts.append((0.5 * (pa[0] + pb[0]), 0.5 * (pa[1] + pb[1])))
            halves[key] = len(pts) - 1
        return halves[key]

    while todo:
        a, b, c = todo.pop()
        if max(math.dist(pts[a], pts[b]), math.dist(pts[b], pts[c]), math.dist(pts[c], pts[a])) <= longest:
            out.append((a, b, c))
            continue
        ab, bc, ca = half(a, b), half(b, c), half(c, a)
        todo.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
    return pts, out


def symbol(kind):
    """The layers of a reel's symbol, back to front: (shape, colour), in a unit square round the middle."""
    if kind == "SEVEN":
        return [(glyphs("7", 0.88, offset=0.07), DARK_RED), (glyphs("7", 0.8, offset=0.025), RED)]
    if kind == "BAR":
        return [(_rounded(0.0, 0.0, 0.92, 0.42, 0.08), BLACK), (glyphs("BAR", 0.24), WHITE)]
    if kind == "CHERRY":
        return [(_strip([(-0.22, -0.12), (-0.12, 0.12), (0.02, 0.3), (0.1, 0.38)], 0.05), GREEN),
                (_strip([(0.24, -0.06), (0.2, 0.14), (0.14, 0.3), (0.1, 0.38)], 0.05), GREEN),
                (_ellipse(0.24, 0.38, 0.17, 0.07, 0.35), GREEN),
                (_circle(-0.2, -0.24, 0.2), RED), (_circle(0.24, -0.18, 0.2), RED),
                (_circle(-0.27, -0.17, 0.05), WHITE), (_circle(0.17, -0.11, 0.05), WHITE)]
    if kind == "BELL":
        return [(_bell(0.0, 0.04, 0.86), DARK_GOLD), (_bell(0.0, 0.05, 0.78), GOLD),
                (_circle(0.0, -0.27, 0.08), DARK_GOLD)]
    if kind == "STAR":
        return [(_star(0.0, -0.02, 0.48, 0.21), ORANGE), (_star(0.0, -0.02, 0.4, 0.17), YELLOW)]
    if kind == "HEART":
        return [(_heart(0.0, -0.02, 0.48), DARK_RED), (_heart(0.0, -0.01, 0.42), PINK),
                (_ellipse(-0.14, 0.1, 0.07, 0.04, 0.6), WHITE)]
    raise ValueError(kind)


# --------------------------------------------------------------------------- meshes

class _Builder:
    """Faces with a colour, metal, glow and bulb phase each, made into one mesh (attributes Col, Metal, Glow,
    Phase)."""

    def __init__(self):
        self.bm = bmesh.new()
        self.tags = []

    def _tag(self, faces, colour, metal=0.0, glow=0.0, phase=-1.0, smooth=False):
        for f in faces:
            f.smooth = smooth
            self.tags.append((f, colour, metal, glow, phase))

    def _new_faces(self, make):
        before = set(self.bm.faces)
        make()
        return [f for f in self.bm.faces if f not in before]

    def box(self, centre, size, colour, metal=0.0, glow=0.0, bevel=0.0):
        def make():
            geom = bmesh.ops.create_cube(self.bm, size=1.0, matrix=Matrix.Translation(centre) @ Matrix.Diagonal(
                (size[0], size[1], size[2], 1.0)))
            if bevel > 0.0:
                edges = list({e for v in geom["verts"] for e in v.link_edges})
                bmesh.ops.bevel(self.bm, geom=edges, offset=bevel, segments=3, affect="EDGES", profile=0.5)
        self._tag(self._new_faces(make), colour, metal, glow)

    def cylinder(self, centre, radius, depth, axis, colour, metal=0.0, glow=0.0, segments=24):
        turn = {"X": Matrix.Rotation(0.5 * math.pi, 4, "Y"), "Y": Matrix.Rotation(0.5 * math.pi, 4, "X"),
                "Z": Matrix.Identity(4)}[axis]
        self._tag(self._new_faces(lambda: bmesh.ops.create_cone(
            self.bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=depth,
            matrix=Matrix.Translation(centre) @ turn)), colour, metal, glow, smooth=True)

    def sphere(self, centre, radius, colour, metal=0.0, glow=0.0, phase=-1.0, segments=12):
        self._tag(self._new_faces(lambda: bmesh.ops.create_uvsphere(
            self.bm, u_segments=segments, v_segments=max(6, segments // 2), radius=radius,
            matrix=Matrix.Translation(centre))), colour, metal, glow, phase, smooth=True)

    def flat(self, pts, tris, origin, right, up, colour, glow=0.0):
        vs = [self.bm.verts.new(origin + right * x + up * y) for x, y in pts]
        faces = []
        for t in tris:
            try:
                faces.append(self.bm.faces.new([vs[i] for i in t]))
            except ValueError:
                pass
        self._tag(faces, colour, 0.0, glow)

    def mesh(self, name):
        bm = self.bm
        bm.normal_update()
        bm.faces.index_update()
        tags = {f.index: (colour, metal, glow, phase) for f, colour, metal, glow, phase in self.tags if f.is_valid}
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        n = len(me.polygons)
        rows = [tags.get(i, (CREAM, 0.0, 0.0, -1.0)) for i in range(n)]
        counts = np.zeros(n, dtype=np.int64)
        me.polygons.foreach_get("loop_total", counts)
        col = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
        col.data.foreach_set("color", np.repeat(np.array([r[0] for r in rows], dtype=np.float32), counts, axis=0)
                             .ravel())
        for name_, k in (("Metal", 1), ("Glow", 2), ("Phase", 3)):
            attr = me.attributes.new(name_, "FLOAT", "FACE")
            attr.data.foreach_set("value", np.array([r[k] for r in rows], dtype=np.float32))
        me.update()
        return me


def reel_mesh(name, radius, width, slots=SLOTS):
    """A reel turning about X: a cream drum with gold ends and the symbols bent onto it, slot k at the angle k turn /
    len(slots) (turned by that angle about X it faces -Y)."""
    b = _Builder()
    bm = b.bm
    n = 96
    ring = [[bm.verts.new((side * 0.5 * width, -radius * math.cos(2.0 * math.pi * i / n),
                           radius * math.sin(2.0 * math.pi * i / n))) for i in range(n)] for side in (-1.0, 1.0)]
    b._tag([bm.faces.new((ring[0][i], ring[1][i], ring[1][(i + 1) % n], ring[0][(i + 1) % n])) for i in range(n)],
           CREAM, smooth=True)
    b._tag([bm.faces.new(list(reversed(ring[0]))), bm.faces.new(ring[1])], DARK_GOLD)
    step = 2.0 * math.pi / len(slots)
    arc = radius * step
    tall = 0.8 * arc
    wide = min(1.3 * tall, 0.9 * width)
    for k, kind in enumerate(slots):
        theta = k * step
        for layer, (shape, colour) in enumerate(symbol(kind)):
            pts, tris = _refined(*_filled(shape))
            lift = radius * (1.0 + 0.004 * (layer + 1))
            vs = []
            for u, v in pts:
                phi = theta + v * tall / radius
                vs.append(bm.verts.new((u * wide, -lift * math.cos(phi), lift * math.sin(phi))))
            faces = []
            for t in tris:
                try:
                    faces.append(bm.faces.new([vs[i] for i in t]))
                except ValueError:
                    pass
            b._tag(faces, colour, smooth=True)
    return b.mesh(name)


def _reels(wide):
    """(x of each reel, its radius, its width) in the cabinet."""
    inner = wide - 0.12
    pitch = inner / 3.0
    radius = 0.5 * (WINDOW[1] - WINDOW[0]) + 0.005
    return [(k - 1) * pitch for k in range(3)], radius, pitch - 0.02


def cabinet_mesh(name, wide=WIDE, paint=(0.62, 0.02, 0.03)):
    """The cabinet, a unit tall and `wide` across, facing -Y: a body in `paint` open at the reel windows, gold trim, a
    topper with JACKPOT and two rows of bulbs, three buttons, a coin tray and the lever's hub on the right."""
    b = _Builder()
    w, d = wide, DEPTH
    lo, hi = WINDOW
    paint = tuple(paint)[:3] + (1.0,)
    b.box(Vector((0, 0, 0.5 * (0.03 + lo))), (w, d, lo - 0.03), paint, bevel=0.02)
    b.box(Vector((0, 0, 0.5 * (hi + 0.77))), (w, d, 0.77 - hi), paint, bevel=0.02)
    for sx in (-1, 1):
        b.box(Vector((sx * (0.5 * w - 0.03), 0, 0.5 * (lo + hi))), (0.06, d, hi - lo), paint)
    b.box(Vector((0, 0.5 * d - 0.03, 0.5 * (lo + hi))), (w - 0.12, 0.06, hi - lo), DARK)
    b.box(Vector((0, 0, 0.025)), (w + 0.05, d + 0.05, 0.05), DARK, bevel=0.01)
    for sx in (-1, 1):
        b.box(Vector((sx * (0.5 * w - 0.012), -0.5 * d - 0.006, 0.4)), (0.03, 0.02, 0.72), TRIM, metal=1.0,
              bevel=0.006)
    # the topper: JACKPOT on a dark red sign between two rows of bulbs
    b.box(Vector((0, 0.01, 0.88)), (w + 0.04, d - 0.04, 0.22), TRIM, metal=1.0, bevel=0.02)
    b.box(Vector((0, -0.002, 0.88)), (w - 0.02, d - 0.06, 0.17), SIGN, bevel=0.01)
    pts, tris = glyphs("JACKPOT", 0.085, offset=0.01)
    scale = min(1.0, (w - 0.1) / max(max(p[0] for p in pts) - min(p[0] for p in pts), 1e-6)) if pts else 1.0
    b.flat([(x * scale, y * scale) for x, y in pts], tris, Vector((0, -0.5 * (d - 0.06) - 0.004, 0.875)),
           Vector((1, 0, 0)), Vector((0, 0, 1)), LETTERS, glow=6.0)
    count = max(int(round((w - 0.07) / 0.0425)), 6)
    for i in range(count):
        x = -0.5 * w + 0.035 + (w - 0.07) * i / (count - 1)
        for z in (0.81, 0.945):
            b.sphere(Vector((x, -0.5 * (d - 0.04) - 0.004, z)), 0.012, BULB, glow=8.0, phase=float(i % 2))
    # the windows: a gold frame round the band, dark bars between the reels, the red pay line
    y = -0.5 * d - 0.006
    for cx, cz, sx, sz in ((0, hi + 0.012, w - 0.06, 0.024), (0, lo - 0.012, w - 0.06, 0.024),
                           (-(0.5 * w - 0.042), 0.5 * (lo + hi), 0.024, hi - lo + 0.048),
                           (0.5 * w - 0.042, 0.5 * (lo + hi), 0.024, hi - lo + 0.048)):
        b.box(Vector((cx, y, cz)), (sx, 0.014, sz), TRIM, metal=1.0, bevel=0.005)
    xs, _radius, _width = _reels(w)
    for x in (0.5 * (xs[0] + xs[1]), 0.5 * (xs[1] + xs[2])):
        b.box(Vector((x, y + 0.004, 0.5 * (lo + hi))), (0.012, 0.012, hi - lo), DARK)
    b.box(Vector((0, y - 0.01, 0.5 * (lo + hi))), (w - 0.1, 0.003, 0.005), LINE, glow=4.0)
    # the buttons on a shelf, the coin tray, the lever's hub
    b.box(Vector((0, -0.5 * d - 0.035, 0.36)), (w - 0.04, 0.08, 0.04), TRIM, metal=1.0, bevel=0.01)
    for i, c in enumerate(((0.1, 0.5, 1.0, 1.0), (1.0, 0.85, 0.1, 1.0), (1.0, 0.15, 0.1, 1.0))):
        b.cylinder(Vector(((i - 1) * 0.12, -0.5 * d - 0.05, 0.385)), 0.025, 0.02, "Z", c, glow=3.0)
    b.box(Vector((0, -0.5 * d - 0.04, 0.12)), (w - 0.14, 0.1, 0.07), CHROME, metal=1.0, bevel=0.01)
    b.box(Vector((0, -0.5 * d - 0.05, 0.135)), (w - 0.2, 0.08, 0.05), DARK)
    b.cylinder(Vector((0.5 * w + 0.03, 0, 0.5)), 0.04, 0.05, "X", CHROME, metal=1.0)
    return b.mesh(name)


def lever_mesh(name):
    """The lever: an arm up from its hub (the origin) with a red ball on top; it swings about X."""
    b = _Builder()
    b.cylinder(Vector((0.03, 0, 0.12)), 0.012, 0.24, "Z", CHROME, metal=1.0)
    b.sphere(Vector((0.03, 0, 0.25)), 0.04, (0.9, 0.02, 0.02, 1.0), segments=20)
    return b.mesh(name)


def tray(wide=WIDE):
    """Where the coins come out (the cabinet's own space)."""
    return Vector((0.0, -0.5 * DEPTH - 0.07, 0.15)), 0.5 * (wide - 0.2)


# --------------------------------------------------------------------------- timing

def stops(anchor, beat_list, fps):
    """The frames the three reels stop on, the last at `anchor`: the beats before it (at least LEAST and at most MOST
    seconds apart) with beats, else GAP apart."""
    out = [float(anchor)]
    for b in sorted((b for b in beat_list if b < anchor - 0.5), reverse=True):
        if len(out) == 3:
            break
        if b <= out[-1] - LEAST * fps + 0.5:
            if out[-1] - b > MOST * fps:
                break
            out.append(float(b))
    while len(out) < 3:
        out.append(out[-1] - GAP * fps)
    return sorted(out)


def plan(moment, beat_list, fps, tease=False):
    """The pulls of the lever: [(pull, spin, stops, slots)] in order (the miss first with `tease`), and the frames it
    starts to fall (start), lands (land), starts to rise (rise) and is gone (gone)."""
    rounds = []
    anchor = float(moment)
    for slots in ((JACKPOT, MISS) if tease else (JACKPOT,)):
        at = stops(anchor, beat_list, fps)
        spin = at[0] - SPIN * fps
        pull = spin - SPIN_AFTER * fps
        rounds.insert(0, (pull, spin, at, slots))
        anchor = pull - TEASE * fps
    land = rounds[0][0] - PULL * fps
    rise = float(moment) + HOLD * fps
    return rounds, {"start": land - DROP * fps, "land": land, "rise": rise, "gone": rise + RISE * fps}


def reel_keys(rounds, k, fps, start_slot):
    """Keys of reel `k`'s turn about X: [(frame, angle, interpolation)], and of its blur: [(frame, value)]."""
    step = 2.0 * math.pi / len(SLOTS)
    angle = start_slot * step
    turn = []
    blur = []
    omega = 2.0 * math.pi * SPEED / fps
    for _pull, spin, at, slots in rounds:
        stop = at[k]
        span = max(stop - spin, 2.0)
        settle = min(SETTLE * fps, 0.6 * span)
        even = (span - settle) + settle / BACK_SLOPE
        base = (slots[k] * step - angle) % (2.0 * math.pi)
        turns = max(int(round((omega * even - base) / (2.0 * math.pi))), 1)
        travel = base + 2.0 * math.pi * turns
        speed = travel / even
        slowing = stop - settle
        turn += [(spin, angle, "LINEAR"), (slowing, angle + speed * (span - settle), "BACK"),
                 (stop, angle + travel, "CONSTANT")]
        blur += [(spin, 0.0), (spin + min(4.0, 0.3 * span), 1.0), (slowing, 1.0), (slowing + 0.6 * settle, 0.15),
                 (stop, 0.0)]
        angle += travel
    return turn, blur


def _keys(id_, path, keys, index=-1):
    """Key `path` at (frame, value, interpolation) with the interpolation per key (BACK: easing out, BOUNCE: easing
    out, EASE_IN: a cubic easing in)."""
    from .cover import _curves

    prop = path[2:-2] if path.startswith('["') else None
    for frame, value, _how in keys:
        if prop is not None:
            id_[prop] = value
        elif index >= 0:
            getattr(id_, path)[index] = value
        else:
            setattr(id_, path, value)
        id_.keyframe_insert(path, index=index, frame=frame)
    hows = {round(f, 3): how for f, _v, how in keys}
    for fc in _curves(id_):
        if fc.data_path != path or (index >= 0 and fc.array_index != index):
            continue
        for kp in fc.keyframe_points:
            how = hows.get(round(kp.co[0], 3), "LINEAR")
            if how == "EASE_IN":
                kp.interpolation, kp.easing = "CUBIC", "EASE_IN"
            elif how in ("BACK", "BOUNCE"):
                kp.interpolation, kp.easing = how, "EASE_OUT"
            else:
                kp.interpolation = how
        fc.update()


# --------------------------------------------------------------------------- on the stage

def place(settings, mask, seen, moment, camera, collection, fps, aspect, height, floor):
    """The slot machine for the big moment at frame `moment` (cover.sync, style SLOT): the cabinet, its reels and
    lever, and the coins."""
    from . import cover, cover_nodes, particles

    scene = settings.id_data
    m = float(moment)
    here = cover.row(seen, m)
    if here is None or not cover._finite(here["chest_w"]):
        return None
    beat_list = beats.beat_frames() if settings.beat_sync else []
    rounds, when = plan(m, beat_list, fps, settings.slot_tease)
    chest = Vector(here["chest_w"])
    toward, side, up = cover._toward(scene, camera, chest)
    stand = Vector((chest.x, chest.y, floor)) + toward * (AHEAD * height)
    depth = max(-(camera.matrix_world.inverted() @ (stand + up * (0.5 * height))).z, 1e-3)
    _c, _w, unit = cover._plane(scene, camera, depth)
    # as wide as she is on the picture round the moment, and up above her head (her arms may reach out past it
    # while it stands there: she dances behind it)
    frames = list(seen.get("frames", ()))
    boxes = list(seen.get("box", ()))
    lo, hi, top = float("inf"), -float("inf"), -float("inf")
    for i, f in enumerate(frames):
        if abs(f - m) <= NEAR * fps + 0.5 and len(boxes) >= 4 * (i + 1):
            x0, x1, _y0, y1 = boxes[4 * i:4 * i + 4]
            if math.isfinite(x0) and math.isfinite(x1) and math.isfinite(y1):
                lo, hi, top = min(lo, x0), max(hi, x1), max(top, y1)
    if not math.isfinite(lo):
        box = here["box"]
        lo, hi, top = (box[0], box[1], box[3]) if cover._finite(box) else (-0.2, 0.2, 0.4)
    mid = camera.matrix_world @ cover._to_camera(scene, camera, 0.5 * (lo + hi), 0.0, depth, aspect)
    stand = Vector((mid.x, mid.y, floor))
    crown = camera.matrix_world @ cover._to_camera(scene, camera, 0.5 * (lo + hi), min(top + 0.03, 0.5), depth,
                                                    aspect)
    tall = max((crown.z - floor) * 1.04, 0.6 * height)  # (as tall as she is on the picture: it fits when she does)
    across = (hi - lo) * unit * 1.1
    wide = round(min(max(across / tall, WIDE), 1.4), 2)
    turn = Matrix((side, -toward, up)).transposed().to_quaternion()  # (its front, -Y, at the camera; Z up)
    start, land, rise, gone = when["start"], when["land"], when["rise"], when["gone"]

    paint = tuple(settings.cover_color)
    machine = cover._piece(mask, "SLOT", collection, "slot:%.2f:%.3f:%.3f:%.3f" % ((wide,) + paint),
                           lambda: cabinet_mesh(cover.NAME + " Slot Machine", wide, paint))
    if not machine.data.materials:
        machine.data.materials.append(materials.ensure_cover_material("SLOT"))
    machine.rotation_mode = "QUATERNION"
    machine.rotation_quaternion = turn
    machine.scale = (tall, tall, tall)
    above = stand + up * (tall + 1.2 * height)
    _keys(machine, "location", ((start - 1.0, above, "CONSTANT"), (start, above, "BOUNCE"),
                                (land, stand, "CONSTANT"), (rise, stand, "EASE_IN"), (gone, above, "CONSTANT")))
    cover._shown(machine, int(math.floor(start)), int(math.ceil(gone)))
    machine[P_START] = float(start)
    cover._drive_frame(machine, "mmdd_blink", "floor(frame / 3) - 2 * floor(frame / 6)")  # (0, 1, 0 ...: simple)
    machine["mmdd_jackpot"] = 0.0
    cover._key(machine, '["mmdd_jackpot"]', ((m - 1.0, 0.0), (m, 1.0), (rise, 1.0), (rise + 3.0, 0.0)),
               interpolation="CONSTANT")
    # the reels behind the windows, each stopping on its beat
    xs, radius, width = _reels(wide)
    rng = np.random.default_rng(17)
    first = [int(rng.integers(1, len(SLOTS))) for _k in range(3)]
    made = [machine]
    for k in range(3):
        reel = cover._piece(mask, "REEL_%d" % k, collection, "reel:%.3f:%.3f" % (radius, width),
                            lambda: reel_mesh(cover.NAME + " Reel", radius, width), parent=machine)
        if not reel.data.materials:
            reel.data.materials.append(materials.ensure_cover_material("REEL"))
        reel.location = (xs[k], -0.5 * DEPTH + radius + 0.012, 0.5 * sum(WINDOW))
        reel.rotation_mode = "XYZ"
        turn_keys, blur_keys = reel_keys(rounds, k, fps, first[k])
        _keys(reel, "rotation_euler", [(start - 1.0, turn_keys[0][1], "CONSTANT")] + turn_keys, index=0)
        reel["mmdd_blur"] = 0.0
        cover._key(reel, '["mmdd_blur"]', [(start - 1.0, 0.0)] + blur_keys)
        cover._shown(reel, int(math.floor(start)), int(math.ceil(gone)))
        made.append(reel)
    lever = cover._piece(mask, "LEVER", collection, "lever", lambda: lever_mesh(cover.NAME + " Lever"),
                         parent=machine)
    if not lever.data.materials:
        lever.data.materials.append(materials.ensure_cover_material("SLOT"))
    lever.location = (0.5 * wide + 0.03, 0.0, 0.5)
    lever.rotation_mode = "XYZ"
    pulls = [(start - 1.0, 0.0, "CONSTANT")]
    for pull, _spin, _at, _slots in rounds:
        pulls += [(pull - 1.0, 0.0, "LINEAR"), (pull + 0.12 * fps, math.radians(62.0), "LINEAR"),
                  (pull + 0.3 * fps, math.radians(-12.0), "LINEAR"), (pull + 0.45 * fps, 0.0, "CONSTANT")]
    _keys(lever, "rotation_euler", pulls, index=0)
    cover._shown(lever, int(math.floor(start)), int(math.ceil(gone)))
    made.append(lever)
    # the coins: out of the tray from the moment on, falling onto the floor
    world = Matrix.Translation(stand) @ turn.to_matrix().to_4x4() @ Matrix.Scale(tall, 4)
    mouth, half = tray(wide)
    rng = np.random.default_rng(23)
    pts, t0, vel, rnd, axis = [], [], [], [], []
    for _k in range(COINS):
        p = world @ (mouth + Vector((rng.uniform(-half, half), 0.0, 0.0)))
        pts.append(tuple(p))
        t0.append(m + COIN_GUSH * fps * rng.uniform() ** 1.5)
        out = toward * rng.uniform(0.2, 0.65) + up * rng.uniform(0.8, 1.6) + side * rng.uniform(-0.9, 0.9)
        vel.append(tuple(out * (height * rng.uniform(0.8, 1.2) / fps)))
        rnd.append(rng.uniform())
        axis.append(tuple(rng.normal(size=3)))
    key = "coins:%.3f:%.3f:%.3f:%.3f:%.2f" % (stand.x, stand.y, stand.z, tall, m)
    coins = cover._piece(mask, "COINS", collection, key,
                         lambda: cover._mesh(cover.NAME + " Coins", pts, [], (("mmdd_t0", "FLOAT", t0),
                                                                             ("mmdd_v", "FLOAT_VECTOR", vel),
                                                                             ("mmdd_r", "FLOAT", rnd),
                                                                             ("mmdd_axis", "FLOAT_VECTOR", axis))))
    cover._modifier(coins, cover_nodes.ensure_pieces_group(),
                    {"Instance": particles.ensure_asset("COIN", scene), "Size": 0.032 * height,
                     "Gravity": (0.0, 0.0, -3.2 * height / (fps * fps)), "Drag": 0.02, "Flutter": 0.0,
                     "Spin": 0.6, "Life": COIN_LIFE * fps, "Floor": floor + 0.003 * height,
                     "Material": materials.ensure_cover_material("COIN")})
    made.append(coins)
    return made
