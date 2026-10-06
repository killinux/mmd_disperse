"""Petal, butterfly, star, cube, coin, ice shard, ember, music note, playing card, feather, bat, ink drop, code glyph
and pebble shapes the old outfit can turn into, and the ice crystals that grow on it with frost.

They are ordinary mesh objects in a hidden collection, so they can be edited (or swapped for any other
object with the "Custom Object" option); the node tree only reads their geometry.
"""

import math

import bpy

from . import materials
from .node_groups import ATTR_VARIANT, GLYPHS

COLLECTION = "MMD Disperse Particles"
PETAL = "MMD Disperse Petal"
BUTTERFLY = "MMD Disperse Butterfly"
STAR = "MMD Disperse Star"
CUBE = "MMD Disperse Cube"
COIN = "MMD Disperse Coin"
SHARD = "MMD Disperse Shard"
EMBER = "MMD Disperse Ember"
CRYSTAL = "MMD Disperse Crystal"
NOTE = "MMD Disperse Note"
CARD = "MMD Disperse Card"
FEATHER = "MMD Disperse Feather"
BAT = "MMD Disperse Bat"
INK = "MMD Disperse Ink Drop"
GLYPH = "MMD Disperse Glyphs"
PEBBLE = "MMD Disperse Pebble"
PAPER_BIRD = "MMD Disperse Paper Bird"
NAMES = {"PETAL": PETAL, "BUTTERFLY": BUTTERFLY, "STAR": STAR, "CUBE": CUBE, "COIN": COIN, "SHARD": SHARD,
         "EMBER": EMBER, "CRYSTAL": CRYSTAL, "NOTE": NOTE, "CARD": CARD, "FEATHER": FEATHER, "BAT": BAT, "INK": INK,
         "GLYPH": GLYPH, "PEBBLE": PEBBLE, "PAPER_BIRD": PAPER_BIRD}
FLAPPING = ("BUTTERFLY", "BAT", "PAPER_BIRD")  # shapes with two wings in the XY plane (x > 0, x < 0) that flap
UPRIGHT = ("NOTE", "GLYPH")  # shapes that stand facing the front (-Y) and only sway
VARIANTS = ("GLYPH",)  # shapes made of several (ATTR_VARIANT on their faces), one shown at a time

# The code glyphs: digits and mirrored half-width katakana as 5 x 7 dot patterns (top row first), like The Matrix's.
GLYPH_ROWS = (
    (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),  # 0
    ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),  # 1
    ("#####", "#....", "#....", "####.", "....#", "#...#", ".###."),  # 5
    ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),  # 7
    ("#####", "#....", "#####", "#....", ".#...", "..#..", "...#."),  # wo (mirrored)
    (".###.", "#....", ".###.", "#....", ".###.", "#....", "....."),  # mi
    ("#.#.#", "#.#.#", "#....", ".#...", "..#..", "...#.", "....#"),  # tsu
    ("#...#", "#...#", "#...#", "#....", ".#...", "..#..", "...#."),  # ri
    ("..#..", "#####", ".#...", "..#..", ".###.", "#.#.#", "..#.."),  # ne
    ("#####", "..#..", "#####", "..#..", "..#..", "..#..", "###.."),  # mo
    ("#####", "#....", "#....", "#....", "#....", "#....", "#####"),  # ko
    ("...##", "#....", "#..##", "#....", ".#...", "..#..", "...##"),  # shi
)
assert len(GLYPH_ROWS) == GLYPHS


def _petal():
    """Cherry-blossom petal: 1 unit long along Y, notched tip, cupped a little."""
    side = [(0.0, 0.0), (0.12, 0.07), (0.23, 0.2), (0.31, 0.38), (0.33, 0.58), (0.29, 0.77), (0.19, 0.93),
            (0.08, 0.99)]
    outline = side + [(0.0, 0.87)] + [(-x, y) for x, y in reversed(side[1:])]
    hub = (0.0, 0.5)
    flat = [hub] + outline
    verts = [(x, y - 0.5, 0.35 * x * x + 0.06 * (y - 0.5) ** 2) for x, y in flat]
    n = len(outline)
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    uvs = [(x + 0.5, y) for x, y in flat]  # U across, V from the base (0) to the tip (1)
    return verts, faces, uvs


def _butterfly():
    """Butterfly about 1 unit across: wings in the XY plane (x > 0 right, x < 0 left), body along Y."""
    # Pointed forewing (+Y), rounded hindwing with a short tail; counter-clockwise around the hub.
    wing = [(0.03, -0.1), (0.08, -0.3), (0.14, -0.42), (0.24, -0.38), (0.36, -0.3), (0.43, -0.15), (0.4, -0.02),
            (0.3, 0.05), (0.42, 0.16), (0.52, 0.32), (0.55, 0.47), (0.45, 0.5), (0.25, 0.4), (0.1, 0.22),
            (0.03, 0.06)]
    hub = (0.16, 0.04)
    verts, faces, uvs = [], [], []
    for sign in (1.0, -1.0):
        start = len(verts)
        for x, y in [hub] + wing:
            verts.append((sign * x, y, 0.0))
            uvs.append((x / 0.55, y + 0.5))  # U = distance from the body: the material brightens the tips
        n = len(wing)
        for i in range(n):
            a, b = start + 1 + i, start + 1 + (i + 1) % n
            faces.append((start, a, b) if sign > 0 else (start, b, a))
    start = len(verts)
    for x, y in ((-0.012, -0.28), (0.012, -0.28), (0.012, 0.22), (-0.012, 0.22)):
        verts.append((x, y, 0.004))
        uvs.append((0.0, y + 0.5))
    faces.append((start, start + 1, start + 2, start + 3))
    return verts, faces, uvs


def _star():
    """Four-pointed sparkle, 1 unit across, in the XY plane; brightest in the middle (UV x = 1 - radius)."""
    verts, uvs = [(0.0, 0.0, 0.0)], [(1.0, 0.5)]
    points = 8
    for i in range(points):
        angle = math.pi * 2.0 * i / points
        r = 0.5 if i % 2 == 0 else 0.12
        verts.append((r * math.cos(angle), r * math.sin(angle), 0.0))
        uvs.append((1.0 - r * 2.0, 0.5))
    faces = [(0, 1 + i, 1 + (i + 1) % points) for i in range(points)]
    return verts, faces, uvs


def _cube():
    """Cube 1 unit across, glowing all over (Tron's derez)."""
    verts = [(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return verts, faces, [(1.0, 0.5)] * len(verts)


def _coin(sides=24):
    """Coin 1 unit across and 0.1 thick, flat in the XY plane."""
    verts, uvs = [], []
    for z in (-0.05, 0.05):
        for i in range(sides):
            angle = math.pi * 2.0 * i / sides
            verts.append((0.5 * math.cos(angle), 0.5 * math.sin(angle), z))
            uvs.append((0.5 + 0.5 * math.cos(angle), 0.5 + 0.5 * math.sin(angle)))
    faces = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    faces += [(i, (i + 1) % sides, sides + (i + 1) % sides, sides + i) for i in range(sides)]
    return verts, faces, uvs


def _shard():
    """Splinter of ice about 1 unit long along Y: an uneven five-sided double point."""
    radii = (0.16, 0.11, 0.14, 0.09, 0.13)
    verts = [(0.0, 0.62, 0.0), (0.0, -0.38, 0.02)]
    for i, r in enumerate(radii):
        angle = math.pi * 2.0 * i / len(radii)
        verts.append((r * math.cos(angle), 0.08 * (i % 2), r * math.sin(angle)))
    n = len(radii)
    faces = [(0, 2 + (i + 1) % n, 2 + i) for i in range(n)] + [(1, 2 + i, 2 + (i + 1) % n) for i in range(n)]
    return verts, faces, [(1.0, 0.5)] * len(verts)


def _ember():
    """Glowing ember, an octahedron 1 unit across."""
    verts = [(0.5, 0.0, 0.0), (-0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, -0.5, 0.0), (0.0, 0.0, 0.5), (0.0, 0.0, -0.5)]
    faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    return verts, faces, [(1.0, 0.5)] * len(verts)


def _crystal(sides=6):
    """Ice crystal standing on the XY plane along +Z, 1 unit tall: a hexagonal prism with a pointed top."""
    verts = []
    for z in (0.0, 0.62):
        for i in range(sides):
            angle = math.pi * 2.0 * i / sides
            verts.append((0.3 * math.cos(angle), 0.3 * math.sin(angle), z))
    verts.append((0.0, 0.0, 1.0))
    top = 2 * sides
    faces = [tuple(range(sides - 1, -1, -1))]
    faces += [(i, (i + 1) % sides, sides + (i + 1) % sides, sides + i) for i in range(sides)]
    faces += [(sides + i, sides + (i + 1) % sides, top) for i in range(sides)]
    return verts, faces, [(1.0, 0.5)] * len(verts)


def _fan(outline, hub, flip=False):
    """Triangles from `hub` (index) to each edge of the closed `outline` (indices)."""
    n = len(outline)
    faces = []
    for i in range(n):
        a, b = outline[i], outline[(i + 1) % n]
        faces.append((hub, b, a) if flip else (hub, a, b))
    return faces


def _note():
    """Music note (a quaver) about 1 unit tall, standing in the XZ plane facing the front (-Y): an oval head, a stem
    and a flag."""
    verts, faces = [], []
    tilt = math.radians(25.0)
    verts.append((-0.1, 0.0, -0.33))  # head centre
    ring = []
    for i in range(16):
        a = math.pi * 2.0 * i / 16
        x, z = 0.17 * math.cos(a), 0.12 * math.sin(a)
        verts.append((-0.1 + x * math.cos(tilt) - z * math.sin(tilt), 0.0,
                      -0.33 + x * math.sin(tilt) + z * math.cos(tilt)))
        ring.append(len(verts) - 1)
    faces += _fan(ring, 0)
    start = len(verts)
    verts += [(0.03, 0.0, -0.33), (0.075, 0.0, -0.33), (0.075, 0.0, 0.47), (0.03, 0.0, 0.47)]
    faces.append((start, start + 1, start + 2, start + 3))
    # the flag: a curved strip from the top of the stem
    pairs = [((0.075, 0.47), (0.075, 0.34)), ((0.17, 0.38), (0.14, 0.28)), ((0.25, 0.25), (0.21, 0.17)),
             ((0.28, 0.1), (0.23, 0.06))]
    prev = None
    for (ox, oz), (ix, iz) in pairs:
        verts += [(ox, 0.0, oz), (ix, 0.0, iz)]
        here = (len(verts) - 2, len(verts) - 1)
        if prev is not None:
            faces.append((prev[0], here[0], here[1], prev[1]))
        prev = here
    return verts, faces, [(1.0, 0.5)] * len(verts)


def _card():
    """Playing card 0.63 x 0.88 in the XY plane with cut corners; UV across the card (the material draws it)."""
    w, h, c = 0.44, 0.62, 0.055
    outline = [(-w + c, -h), (w - c, -h), (w, -h + c), (w, h - c), (w - c, h), (-w + c, h), (-w, h - c), (-w, -h + c)]
    verts = [(0.0, 0.0, 0.0)] + [(x, y, 0.0) for x, y in outline]
    faces = _fan(list(range(1, len(verts))), 0)
    uvs = [(x / (2 * w) + 0.5, y / (2 * h) + 0.5) for x, y, _z in verts]
    return verts, faces, uvs


def _feather(steps=12, length=1.3):
    """Feather `length` long along Y (quill at -Y), the vane wider on one side and curved a little; brightest along the
    shaft (UV x)."""
    verts, uvs = [], []
    rows = []
    for i in range(steps + 1):
        t = i / steps
        y = t - 0.5
        width = max(0.13 * math.sin(math.pi * min(1.0, t * 1.15)) ** 0.8 if t > 0.12 else 0.0, 0.008)
        shaft = 0.06 * math.sin(math.pi * t)
        row = []
        for side, offset in ((-0.7, -0.7 * width), (0.0, 0.0), (1.0, width)):
            verts.append(((shaft + offset) * length, y * length, 0.02 * abs(side) * math.sin(math.pi * t) * length))
            uvs.append((1.0 - 0.7 * abs(side), t))
            row.append(len(verts) - 1)
        rows.append(row)
    faces = []
    for a, b in zip(rows, rows[1:]):
        faces.append((a[0], a[1], b[1], b[0]))
        faces.append((a[1], a[2], b[2], b[1]))
    return verts, faces, uvs


def _bat(size=3.5):
    """Bat about 3.9 units across (a dark shape has to be big to read): wings in the XY plane (x > 0 right, x < 0
    left) with a scalloped trailing edge, a small body with ears along Y (the wings flap like the butterfly's)."""
    wing = [(0.03, 0.1), (0.15, 0.16), (0.3, 0.2), (0.46, 0.22), (0.55, 0.12), (0.48, 0.04), (0.44, -0.06),
            (0.37, -0.02), (0.31, -0.12), (0.24, -0.05), (0.16, -0.14), (0.09, -0.06), (0.03, -0.08)]
    hub = (0.13, 0.03)
    verts, faces, uvs = [], [], []
    for sign in (1.0, -1.0):
        start = len(verts)
        for x, y in [hub] + wing:
            verts.append((sign * x * size, y * size, 0.0))
            uvs.append((x / 0.55, y + 0.5))
        faces += _fan(list(range(start + 1, len(verts))), start, flip=sign < 0)
    body = [(0.0, -0.16), (0.035, -0.05), (0.03, 0.1), (0.035, 0.22), (0.008, 0.14), (-0.008, 0.14), (-0.035, 0.22),
            (-0.03, 0.1), (-0.035, -0.05)]
    start = len(verts)
    verts.append((0.0, 0.03 * size, 0.004))
    uvs.append((0.0, 0.5))
    for x, y in body:
        verts.append((x * size, y * size, 0.004))
        uvs.append((0.0, y + 0.5))
    faces += _fan(list(range(start + 1, len(verts))), start)
    return verts, faces, uvs


def _paper_bird(size=1.6):
    """Folded paper bird (an origami crane seen from above) about 1.6 units across: flat swept wings in the XY plane
    (x > 0 right, x < 0 left) that flap like the butterfly's, a pointed neck and tail along Y."""
    wing = [(0.03, 0.08), (0.28, 0.06), (0.5, 0.0), (0.42, -0.05), (0.2, -0.08), (0.03, -0.1)]
    hub = (0.1, -0.01)
    verts, faces, uvs = [], [], []
    for sign in (1.0, -1.0):
        start = len(verts)
        for x, y in [hub] + wing:
            verts.append((sign * x * size, y * size, 0.0))
            uvs.append((x / 0.5, y + 0.5))
        faces += _fan(list(range(start + 1, len(verts))), start, flip=sign < 0)
    body = [(0.0, 0.42), (0.03, 0.1), (0.035, -0.1), (0.0, -0.38), (-0.035, -0.1), (-0.03, 0.1)]
    start = len(verts)
    verts.append((0.0, 0.0, 0.01 * size))
    uvs.append((0.0, 0.5))
    for x, y in body:
        verts.append((x * size, y * size, 0.006 * size))
        uvs.append((0.0, y + 0.5))
    faces += _fan(list(range(start + 1, len(verts))), start)
    return verts, faces, uvs


def _ink_drop(sides=18):
    """Splash of ink about 1 unit across, flat in the XY plane: an uneven blot with a small drop beside it."""
    verts = [(0.0, 0.0, 0.0)]
    for i in range(sides):
        a = math.pi * 2.0 * i / sides
        r = 0.42 * (1.0 + 0.18 * math.sin(3 * a + 1.0) + 0.1 * math.sin(7 * a + 2.0))
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
    faces = _fan(list(range(1, sides + 1)), 0)
    start = len(verts)
    verts.append((0.58, 0.2, 0.0))
    for i in range(6):
        a = math.pi * 2.0 * i / 6
        verts.append((0.58 + 0.07 * math.cos(a), 0.2 + 0.07 * math.sin(a), 0.0))
    faces += _fan(list(range(start + 1, start + 7)), start)
    return verts, faces, [(1.0, 0.5)] * len(verts)


def _glyphs():
    """The code glyphs, each 1 unit tall standing in the XZ plane facing the front (-Y), all at the origin: a square
    dot per pixel of its pattern. Returns (verts, faces, uvs, the glyph of each face)."""
    pixel = 1.0 / 7.0
    dot = 0.4 * pixel
    verts, faces, variants = [], [], []
    for k, rows in enumerate(GLYPH_ROWS):
        for row, line in enumerate(rows):
            for col, mark in enumerate(line):
                if mark != "#":
                    continue
                cx, cz = (col - 2.0) * pixel, (3.0 - row) * pixel
                start = len(verts)
                verts += [(cx - dot, 0.0, cz - dot), (cx + dot, 0.0, cz - dot), (cx + dot, 0.0, cz + dot),
                          (cx - dot, 0.0, cz + dot)]
                faces.append((start, start + 1, start + 2, start + 3))
                variants.append(k)
    return verts, faces, [(1.0, 0.5)] * len(verts), variants


def _pebble():
    """Pebble about 1 unit across: an icosahedron with its corners pushed in and out a little, flattened."""
    t = (1.0 + math.sqrt(5.0)) / 2.0
    corners = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
               (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    bumps = (1.0, 0.82, 0.93, 1.08, 0.86, 1.04, 0.9, 1.1, 0.84, 0.97, 1.06, 0.88)
    size = 0.5 / math.sqrt(1.0 + t * t)
    verts = [(x * size * r, y * size * r * 0.85, z * size * r * 0.7) for (x, y, z), r in zip(corners, bumps)]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    return verts, faces, [(1.0, 0.5)] * len(verts)


_SHAPES = {"PETAL": _petal, "BUTTERFLY": _butterfly, "STAR": _star, "CUBE": _cube, "COIN": _coin, "SHARD": _shard,
           "EMBER": _ember, "CRYSTAL": _crystal, "NOTE": _note, "CARD": _card, "FEATHER": _feather, "BAT": _bat,
           "INK": _ink_drop, "GLYPH": _glyphs, "PEBBLE": _pebble, "PAPER_BIRD": _paper_bird}


def _material(kind):
    if kind == "COIN":
        return materials.ensure_coin_material()
    if kind in ("SHARD", "CRYSTAL"):
        return materials.ensure_ice_material()
    if kind == "CARD":
        return materials.ensure_card_material()
    if kind == "BAT":
        return materials.ensure_bat_material()
    if kind == "INK":
        return materials.ensure_ink_material()
    if kind == "PEBBLE":
        return materials.ensure_pebble_material()
    if kind == "PAPER_BIRD":
        return materials.ensure_paper_material()
    return materials.ensure_particle_material()


def asset_collection(scene):
    """The hidden collection of the particle shapes (and the motion empties of leave behind)."""
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if scene is not None and coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    coll.hide_viewport = True
    coll.hide_render = True
    return coll


def ensure_asset(kind, scene):
    """The shape object for `kind` (a key of NAMES), created on first use."""
    name = NAMES[kind]
    ob = bpy.data.objects.get(name)
    if ob is not None and ob.type == "MESH":
        return ob
    shape = _SHAPES[kind]()
    verts, faces, uvs = shape[:3]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        layer.data[loop.index].uv = uvs[loop.vertex_index]
    if len(shape) > 3:  # which of its shapes each face belongs to
        me.attributes.new(ATTR_VARIANT, "INT", "FACE").data.foreach_set("value", shape[3])
    me.materials.append(_material(kind))
    me.update()
    ob = bpy.data.objects.new(name, me)
    asset_collection(scene).objects.link(ob)
    return ob


def remove_assets():
    for name in NAMES.values():
        ob = bpy.data.objects.get(name)
        if ob is not None:
            me = ob.data
            bpy.data.objects.remove(ob)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    coll = bpy.data.collections.get(COLLECTION)
    if coll is not None and not coll.all_objects:
        bpy.data.collections.remove(coll)
    for name in (materials.PARTICLE_MATERIAL, materials.COIN_MATERIAL, materials.ICE_MATERIAL, materials.CARD_MATERIAL,
                 materials.BAT_MATERIAL, materials.INK_MATERIAL, materials.SMOKE_MATERIAL, materials.DUST_MATERIAL,
                 materials.PEBBLE_MATERIAL, materials.ARC_MATERIAL, materials.BEAM_MATERIAL, materials.FLAME_MATERIAL,
                 materials.LOTUS_MATERIAL, materials.SOUL_MATERIAL, materials.SHOCK_MATERIAL):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
