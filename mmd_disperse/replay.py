"""The tape look of Rewind and Replay (1.12, 倒带重放; timewarp's REWIND): while the picture rewinds, a sheet in front of
the camera lays scan lines, a rolling band of tracking noise and a rewind sign (◀◀) over it, and while it plays again
slowly, a play sign (▶) and fainter scan lines. The sheet reads its keyed object properties mmdd_rewind and
mmdd_replay (0 .. 1) and the frame (mmdd_tick, driven).
"""

import bpy

from . import materials, timewarp

P_REPLAY = "mmd_disperse_replay"  # on the sheet: the mask of its effect
NAME = "MMD Disperse Tape"


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_REPLAY) == mask]


def remove(mask):
    for ob in objects(mask):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    mat = bpy.data.materials.get(materials.TAPE_MATERIAL)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)


def _sheet(scene, mask, camera, collection):
    """The sheet just in front of `camera`, a little larger than its picture, its UVs 0 .. 1 across it."""
    from mathutils import Vector

    from .picture import _frame, _near

    depth = 0.97 * _near(camera)  # (in front of the picture fronts' sheet)
    key = "%s:%d:%d:%.4f" % (camera.name, scene.render.resolution_x, scene.render.resolution_y, depth)
    ob = next(iter(objects(mask)), None)
    if ob is not None and (ob.parent != camera or ob.get("mmdd_key") != key):
        remove(mask)
        ob = None
    if ob is not None:
        return ob
    centre, width, height = _frame(scene, camera, depth)
    half_w, half_h = 0.5 * width * materials.FRONT_SHEET, 0.5 * height * materials.FRONT_SHEET
    corners = [centre + Vector((sx * half_w, sy * half_h, 0.0)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = bpy.data.meshes.new(NAME)
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        uv.data[loop.index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
    me.materials.append(materials.ensure_tape_material())
    ob = bpy.data.objects.new(NAME, me)
    collection.objects.link(ob)
    ob.parent = camera
    ob.hide_select = True
    if hasattr(ob, "visible_shadow"):
        ob.visible_shadow = False
    ob[P_REPLAY] = mask
    ob["mmdd_key"] = key
    return ob


def sync(settings, mask, moment):
    """The tape sheet for Rewind and Replay round the moment at frame `moment` (none without it)."""
    scene = settings.id_data
    camera = scene.camera
    if settings.time_warp != "REWIND" or moment is None or camera is None:
        remove(mask)
        return None
    from .finish import _clear_keys, _key, sampling_aspect

    fps = scene.render.fps / scene.render.fps_base
    (a, b, c, d), _times = timewarp.rewind_frames(int(moment), settings.frame_start, settings.warp_length, fps)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    ob = _sheet(scene, mask, camera, collection)
    ob[materials.FRONT_ASPECT] = sampling_aspect(scene)
    ob[materials.FRONT_TICK] = 0.0
    ob.driver_remove('["%s"]' % materials.FRONT_TICK)
    tick = ob.driver_add('["%s"]' % materials.FRONT_TICK).driver
    tick.type = "SCRIPTED"
    tick.expression = "frame"
    _clear_keys(ob)
    _key(ob, '["mmdd_rewind"]', ((a - 1, 0.0), (a, 1.0), (b - 1, 1.0), (b, 0.0)), interpolation="CONSTANT")
    _key(ob, '["mmdd_replay"]', ((b - 1, 0.0), (b, 1.0), (c, 1.0), (c + 1, 0.0)), interpolation="CONSTANT")
    return ob
