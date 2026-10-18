"""Stage flames (台口火柱, 1.13): at the big moment (the swap, or the new outfit complete) a row of flame jets along
the front of the stage shoots up columns of cartoon fire for a moment, lighting the dancer warm from below (a concert's
pyro: Eurovision 2026's jump into the flames, Uma Musume's live stage).

The jets are objects of ours where she stands, facing the camera of the moment; each column is a tapering tube whose
material burns in bands (materials.ensure_cover_material("FLAME")), its height keyed: up in a few frames, flickering,
down again. A point light flares with them. Removing the effect takes them away."""

import math

import bpy
from mathutils import Vector

from . import materials, shots

P_PYRO = "mmd_disperse_pyro"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_pyro_kind"  # ... JET_0 .. JET_5, LIGHT
NAME = "MMD Disperse Stage Flame"
JETS = (-0.42, -0.24, 0.24, 0.42)  # across the picture where she stands (shares of its width) ...
AHEAD = 0.3  # ... this far in front of her (model heights)
TALL = 0.95  # how tall a column of fire stands (model heights) ...
WIDE = 0.05  # ... how wide it is at its foot ...
UP = 3  # ... frames it takes to shoot up ...
HOLD = 0.7  # ... seconds it burns ...
DOWN = 6  # ... and frames it takes to die down
LIGHT_POWER = 700.0  # the flare of light with them, in watts per square model height


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_PYRO) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def remove(mask):
    for ob in objects(mask):
        _delete(ob)


def _column_mesh(sides=20, rings=14):
    """A tube of fire from z 0 (radius 1) to z 1 (radius 0.25), wavy; mmdd_t its height (0 .. 1), mmdd_uv x round it."""
    verts, faces, t, uvs = [], [], [], []
    for j in range(rings + 1):
        h = j / float(rings)
        r = 1.0 - 0.75 * h ** 0.8
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            wob = 1.0 + 0.08 * math.sin(3.0 * a + 5.0 * h)
            verts.append((r * wob * math.cos(a), r * wob * math.sin(a), h))
            t.append(h)
            uvs.append((k / float(sides), h, 0.0))
    for j in range(rings):
        for k in range(sides):
            a0, a1 = j * sides, (j + 1) * sides
            faces.append((a0 + k, a0 + (k + 1) % sides, a1 + (k + 1) % sides, a1 + k))
    me = bpy.data.meshes.new(NAME)
    me.from_pydata(verts, [], faces)
    for name, values, kind in (("mmdd_t", t, "FLOAT"), ("mmdd_uv", uvs, "FLOAT_VECTOR")):
        attr = me.attributes.new(name, kind, "POINT")
        attr.data.foreach_set("vector" if kind == "FLOAT_VECTOR" else "value",
                              [v for item in values for v in (item if isinstance(item, tuple) else (item,))])
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()
    return me


def _key(id_, path, keys, interpolation="LINEAR"):
    for frame, value in keys:
        if path.startswith('["'):
            id_[path[2:-2]] = value
        else:
            setattr(id_, path, value)
        id_.keyframe_insert(path, frame=frame)
    from .cover import _curves

    for fc in _curves(id_):
        if fc.data_path == path:
            for k in fc.keyframe_points:
                k.interpolation = interpolation
            fc.update()


def sync(settings, mask, models, moment):
    """The flame jets as the panel says, burning at the big moment (frame `moment`); none without them."""
    scene = settings.id_data
    camera = shots.carrier(scene, mask) if mask is not None else None
    if not getattr(settings, "stage_flames", False) or moment is None or not models:
        if mask is not None:
            remove(mask)
        return
    from .cover import _clear_keys, _drive_frame
    from .model import rest_bounds

    meshes = [ob for m in models for ob in m.meshes]
    lo, hi = rest_bounds(meshes)
    height = max(settings.size_reference, hi.z - lo.z, 1e-3)
    middle = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
    toward = (camera.matrix_world.translation - middle) if camera is not None else Vector((0.0, -1.0, 0.0))
    toward.z = 0.0
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    side = (-toward).cross(Vector((0.0, 0.0, 1.0)))
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    material = materials.ensure_cover_material("FLAME")
    hold = HOLD * fps
    # (spread across the picture as the camera sees it where they stand, so all of them are in it)
    front = middle + toward * (AHEAD * height)
    wide = 0.6 * height
    if camera is not None and camera.type == "CAMERA":
        from .picture import _frame

        depth = max(-(camera.matrix_world.inverted() @ (front + Vector((0.0, 0.0, 0.4 * height)))).z, 1e-3)
        wide = _frame(scene, camera, depth)[1]
    for k, across in enumerate(JETS):
        kind = "JET_%d" % k
        ob = next(iter(objects(mask, kind)), None)
        if ob is None:
            ob = bpy.data.objects.new("%s %d" % (NAME, k), _column_mesh())
            ob.data.materials.append(material)
            collection.objects.link(ob)
            ob[P_PYRO] = mask
            ob[P_KIND] = kind
            ob.hide_select = True
            if hasattr(ob, "visible_shadow"):
                ob.visible_shadow = False
        _clear_keys(ob)
        ob.location = front + side * (across * wide)
        ob["mmdd_seed"] = 0.37 * k
        _drive_frame(ob, materials.FRONT_TICK)  # (the fire rolls up with the frames)
        w = WIDE * height
        # up in a few frames, flickering while it burns, down again
        keys = [(m - 1.0, (w, w, 0.0)), (m - 1.0 + UP, (w * 1.15, w * 1.15, TALL * height * 1.08))]
        steps = 6
        for i in range(1, steps + 1):
            f = m - 1.0 + UP + hold * i / steps
            flicker = 1.0 + 0.07 * math.sin(2.7 * i + k)
            keys.append((f, (w, w, TALL * height * flicker)))
        keys.append((m - 1.0 + UP + hold + DOWN, (0.6 * w, 0.6 * w, 0.0)))
        _key(ob, "scale", keys)
        for path in ("hide_render", "hide_viewport"):
            _key(ob, path, ((m - 2.0, True), (m - 1.0, False), (m + UP + hold + DOWN, True)), interpolation="CONSTANT")
    # the flare of warm light from the fire, low in front of her
    light = next(iter(objects(mask, "LIGHT")), None)
    if light is None:
        light = bpy.data.objects.new(NAME + " Light", bpy.data.lights.new(NAME + " Light", "POINT"))
        collection.objects.link(light)
        light[P_PYRO] = mask
        light[P_KIND] = "LIGHT"
        light.hide_select = True
    _clear_keys(light.data)
    light.data.color = (1.0, 0.55, 0.2)
    light.data.shadow_soft_size = 0.3 * height
    light.location = middle + toward * (0.6 * height) + Vector((0.0, 0.0, 0.25 * height))
    peak = LIGHT_POWER * height * height
    _key(light.data, "energy", ((m - 1.0, 0.0), (m - 1.0 + UP, peak), (m + hold, 0.8 * peak),
                                (m + hold + DOWN, 0.0)))
