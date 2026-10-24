"""The totem in the mist (雾中图腾, 1.15): mist swirls round and behind the dancer; when the transformation starts
(with Start On: Hand to the Sky, the moment her hand goes up: "I have the power!") it is drawn into a great shape behind
her, a star, a heart, words or a mesh of your own, holds it while she changes and blows away once the new outfit is
complete: the castle that forms in the storm behind He-Man as he raises his sword (Masters of the Universe, 2026; ILM
kept the 1983 opening's rhythm). Not the Dharma form: what shows behind her is any shape, not herself.

One object of ours, its points made here: each puff's place in the shape (mmdd_target), its swirl (mmdd_orbit: radius,
height and phase; mmdd_speed; most turn in a vortex in the shape's plane, some round her feet: mmdd_ground), when it
gets there (mmdd_delay) and which way it blows (mmdd_way). The object stands on the floor under her, turned to the
camera (X across the picture, Y away from it, Z up), and cover_nodes' totem group moves the points by the frame and
puts a puff on each (materials' MIST: soft light, adding up).
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials

P_TOTEM = "mmd_disperse_totem"  # on our object: the mask of its effect
P_KEY = "mmd_disperse_totem_key"  # ... and what its points were made for
NAME = "MMD Disperse Totem"
SHAPES = ("STAR", "HEART", "TEXT", "OBJECT")
PUFFS = 3500
BEHIND = 0.9  # the shape stands this far behind her (model heights)
GROUND = 0.22  # share of the puffs swirling round her feet rather than in the vortex behind her
GATHER = 0.45  # seconds the mist takes to gather into the shape (round the start) ...
AFTER = 0.25  # ... it holds till this long after the new outfit is complete (at least HOLD after it gathered) ...
HOLD = 0.8
BLOW = 1.3  # ... and blows away over this long
PUFF = 0.075  # a puff's size (model heights)


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_TOTEM) == mask]


def remove(mask):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    if not any(ob.get(P_TOTEM) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_totem_assets()
        mat = bpy.data.materials.get(materials._cover_name("MIST"))
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)


# --------------------------------------------------------------------------- the shape

def _font(path):
    """The font file `path` (Blender's own when empty or unreadable: Latin letters only on Blender 3.6)."""
    if path:
        try:
            return bpy.data.fonts.load(bpy.path.abspath(path), check_existing=True)
        except (RuntimeError, OSError):
            pass
    return bpy.data.fonts.load("<builtin>", check_existing=True)


def _triangles(settings):
    """The shape as triangles: (points (n, 3), triangles (m, 3)), X across, Z up, a unit tall or wide (whichever is
    more); flat ones have Y 0. None when there is nothing to show (no words, no mesh)."""
    from . import slot

    kind = settings.totem_shape
    if kind == "OBJECT":
        ob = settings.totem_object
        if ob is None or ob.type != "MESH":
            return None
        deps = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        try:
            me.calc_loop_triangles()
            pts = np.array([tuple(v.co) for v in me.vertices], dtype=np.float64).reshape(-1, 3)
            tris = np.array([tuple(t.vertices) for t in me.loop_triangles], dtype=np.int64).reshape(-1, 3)
        finally:
            ev.to_mesh_clear()
        if not len(tris):
            return None
        pts = pts * np.array(ob.scale)  # (its own size and proportions, not where it stands)
    else:
        if kind == "TEXT":
            text = settings.totem_text.strip()
            if not text:
                return None
            flat, tris = _glyphs(text, settings.totem_font)
            if not tris:
                return None
        else:
            shape = slot._star(0.0, 0.0, 0.5, 0.21) if kind == "STAR" else slot._heart(0.0, 0.0, 0.5)
            flat, tris = slot._filled(shape)
        pts = np.array([(x, 0.0, y) for x, y in flat], dtype=np.float64)
        tris = np.array(tris, dtype=np.int64).reshape(-1, 3)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    pts = (pts - 0.5 * (lo + hi)) / max(hi[0] - lo[0], hi[2] - lo[2], 1e-9)
    return pts, tris


def _glyphs(text, font_path):
    cu = bpy.data.curves.new("MMDD Totem Text", "FONT")
    cu.body = text
    font = _font(font_path)
    if font is not None:
        cu.font = font
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    ob = bpy.data.objects.new("MMDD Totem Text", cu)
    bpy.context.scene.collection.objects.link(ob)
    try:
        deps = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        flat = [(v.co.x, v.co.y) for v in me.vertices]
        tris = [tuple(t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
    return flat, tris


def _sample(pts, tris, count, rng):
    """`count` points spread evenly over the triangles."""
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if areas.sum() <= 0.0:
        return np.repeat(pts[:1], count, axis=0)
    pick = rng.choice(len(tris), size=count, p=areas / areas.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1.0
    u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
    return a[pick] + (b[pick] - a[pick]) * u[:, None] + (c[pick] - a[pick]) * v[:, None]


def points(settings, height):
    """The mesh of the puffs (the object's own space: X across, Y away from the camera, Z up, the floor under her at
    0), or None."""
    shape = _triangles(settings)
    if shape is None:
        return None
    rng = np.random.default_rng(29)
    n = PUFFS
    unit = _sample(shape[0], shape[1], n, rng)
    size = settings.totem_size * height
    span = unit.max(axis=0) - unit.min(axis=0)
    tall = span[2] * size
    centre = np.array([0.0, BEHIND * height, max(0.62 * height, 0.5 * tall + 0.05 * height)])
    target = centre + unit * size
    target[:, 1] += rng.normal(0.0, 0.025 * height, n)
    reach = max(span[0], span[2]) * size
    ground = rng.random(n) < GROUND
    radius = np.where(ground, (0.35 + 0.5 * rng.random(n)) * height,
                      reach * (0.15 + 0.5 * np.sqrt(rng.random(n))))
    lift = np.where(ground, 0.12 * height * rng.random(n), centre[2])
    phase = 2.0 * math.pi * rng.random(n)
    turn = np.where(ground, 0.5, 1.6 / (0.5 + radius / max(reach, 1e-9))) * (0.7 + 0.6 * rng.random(n))  # rad/s
    depth = np.where(ground, 0.0, centre[1] + rng.normal(0.0, 0.12 * height, n))
    across = (unit[:, 0] - unit[:, 0].min()) / max(span[0], 1e-9)
    delay = np.clip(0.6 * across + 0.4 * rng.random(n), 0.0, 1.0)  # (it blows away from one side)
    way = rng.normal(0.0, 1.0, (n, 3))
    way /= np.maximum(np.linalg.norm(way, axis=1), 1e-9)[:, None]
    me = bpy.data.meshes.new(NAME)
    me.vertices.add(n)
    me.vertices.foreach_set("co", np.zeros(3 * n, dtype=np.float32))
    for name, kind, values in (("mmdd_target", "FLOAT_VECTOR", target),
                               ("mmdd_orbit", "FLOAT_VECTOR", np.stack([radius, lift, phase], axis=1)),
                               ("mmdd_way", "FLOAT_VECTOR", way), ("mmdd_speed", "FLOAT", turn),
                               ("mmdd_depth", "FLOAT", depth), ("mmdd_ground", "FLOAT", ground.astype(np.float32)),
                               ("mmdd_delay", "FLOAT", delay), ("mmdd_seed", "FLOAT", rng.random(n))):
        attr = me.attributes.new(name, kind, "POINT")
        attr.data.foreach_set("vector" if kind == "FLOAT_VECTOR" else "value",
                              np.asarray(values, dtype=np.float32).ravel())
    me.update()
    return me


def _key(settings, height):
    ob = settings.totem_object
    mesh = ("%s:%d:%d" % (ob.name, len(ob.data.vertices), len(ob.data.polygons))
            if ob is not None and ob.type == "MESH" else "")
    return "%s|%s|%s|%s|%.4f|%.4f" % (settings.totem_shape, settings.totem_text, settings.totem_font, mesh,
                                     settings.totem_size, height)


# --------------------------------------------------------------------------- the panel -> the scene

def sync(settings, mask, models, frame_at, moment):
    """The totem as the panel says: gathering at the start of the transformation (frame_at(0)), blowing away after
    `moment` (the new outfit complete); taken away when it is off."""
    from . import cover_nodes, sampling
    from .model import rest_bounds

    if mask is None:
        return
    start = frame_at(0.0) if frame_at is not None else None
    meshes = [ob for m in models for ob in m.meshes] if models else []
    if not getattr(settings, "totem_enable", False) or start is None or not meshes:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    height = max(settings.size_reference, 1e-3)
    key = _key(settings, height)
    ob = next(iter(objects(mask)), None)
    if ob is not None and ob.get(P_KEY) != key:
        remove(mask)
        ob = None
    if ob is None:
        me = points(settings, height)
        if me is None:
            return
        ob = bpy.data.objects.new(NAME, me)
        collection = mask.users_collection[0] if mask.users_collection else scene.collection
        collection.objects.link(ob)
        ob[P_TOTEM] = mask
        ob[P_KEY] = key
        ob.hide_select = True
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
    lo, hi = rest_bounds(meshes)
    gather = float(start)
    camera = sampling.camera_at(scene, gather)  # (turned to the camera as it is when the mist gathers: it may orbit)
    back = Vector((0.0, 1.0, 0.0))
    if camera is not None:
        away = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), 0.0)) - sampling.matrix_at(camera, gather).translation
        away.z = 0.0
        if away.length > 1e-6:
            back = away.normalized()
    up = Vector((0.0, 0.0, 1.0))
    side = back.cross(up)
    ob.location = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z))
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Matrix((side, back, up)).transposed().to_quaternion()
    ob.scale = (1.0, 1.0, 1.0)
    ob["mmdd_color"] = tuple(settings.totem_color)
    ob["mmdd_height"] = height
    done = float(moment) if moment is not None else gather
    release = max(done + AFTER * fps, gather + HOLD * fps)
    mod = next((m for m in ob.modifiers if m.type == "NODES"), None)
    if mod is None:
        mod = ob.modifiers.new(NAME, "NODES")
    group = cover_nodes.ensure_totem_group()
    if mod.node_group != group:
        mod.node_group = group
    from .node_groups import input_identifiers

    ids = input_identifiers(group)
    for name, value in (("Start", gather - settings.totem_lead * fps), ("Gather", gather),
                        ("Gather Time", GATHER * fps), ("Release", release), ("Blow Time", BLOW * fps), ("Fps", fps),
                        ("Height", height), ("Puff", cover_nodes.ensure_puff_object(scene)),
                        ("Size", PUFF * height), ("Material", materials.ensure_cover_material("MIST"))):
        if name in ids:
            mod[ids[name]] = value
    ob.update_tag()
    return ob
