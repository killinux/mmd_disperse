"""Petal, butterfly, star, cube, coin, ice shard and ember shapes the old outfit can turn into, and the ice crystals
that grow on it with frost.

They are ordinary mesh objects in a hidden collection, so they can be edited (or swapped for any other
object with the "Custom Object" option); the node tree only reads their geometry.
"""

import math

import bpy

from . import materials

COLLECTION = "MMD Disperse Particles"
PETAL = "MMD Disperse Petal"
BUTTERFLY = "MMD Disperse Butterfly"
STAR = "MMD Disperse Star"
CUBE = "MMD Disperse Cube"
COIN = "MMD Disperse Coin"
SHARD = "MMD Disperse Shard"
EMBER = "MMD Disperse Ember"
CRYSTAL = "MMD Disperse Crystal"
NAMES = {"PETAL": PETAL, "BUTTERFLY": BUTTERFLY, "STAR": STAR, "CUBE": CUBE, "COIN": COIN, "SHARD": SHARD,
         "EMBER": EMBER, "CRYSTAL": CRYSTAL}


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


_SHAPES = {"PETAL": _petal, "BUTTERFLY": _butterfly, "STAR": _star, "CUBE": _cube, "COIN": _coin, "SHARD": _shard,
           "EMBER": _ember, "CRYSTAL": _crystal}


def _material(kind):
    if kind == "COIN":
        return materials.ensure_coin_material()
    if kind in ("SHARD", "CRYSTAL"):
        return materials.ensure_ice_material()
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
    verts, faces, uvs = _SHAPES[kind]()
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        layer.data[loop.index].uv = uvs[loop.vertex_index]
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
    for name in (materials.PARTICLE_MATERIAL, materials.COIN_MATERIAL, materials.ICE_MATERIAL):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
