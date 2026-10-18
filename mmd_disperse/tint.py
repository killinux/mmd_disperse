"""Recolouring (换色, 1.13): the old outfit takes on other colours on the way to the big moment, its own shading kept
(materials.add_tint: the material as it is lit, turned into a colour of a palette).

* FACE (变脸连变, Sichuan opera's face changing): the whole outfit flips to another colour of the opera masks, again
  and again, faster and faster, until the big moment;
* TUG (颜色拉锯, Sleeping Beauty's fairies fighting over the dress): two colours chase each other across the outfit,
  a sweep from one side and then from the other, on the beats with beat sync;
* ERAS (历代舞伴, the juke joint of Sinners): copies of the dancer, each in the look of an age (an old photo, black and
  white, neon, gold, ...), appear beside and behind her one after another and dance along; just before the big moment
  they fly into her and the outfits swap.

It all happens in the Tint Time before the big moment. The timing is in drivers on the frame on the tint's values in
each material of the old outfit (short simple expressions, which Blender runs without Python); the copies are a
Geometry Nodes object of ours per mesh of the old outfit. Removing the effect takes them all away."""

import fnmatch

import bpy
import numpy as np
from mathutils import Vector

from . import beats, materials, shots
from . import model as mdl

STYLES = ("NONE", "FACE", "TUG", "ERAS")
P_ERAS = "mmd_disperse_eras"  # on our copies objects: the mask of their effect ...
P_SOURCE = "mmd_disperse_eras_source"  # ... and the name of the mesh they copy
NAME = "MMD Disperse Era"
FACE_COLORS = ((0.85, 0.06, 0.05), (0.06, 0.06, 0.07), (1.0, 0.72, 0.12), (0.08, 0.55, 0.22), (0.12, 0.3, 0.95),
               (0.95, 0.95, 0.95), (0.6, 0.1, 0.72), (1.0, 0.42, 0.08))  # the opera masks: red, black, gold, green ...
ERA_COLORS = ((0.78, 0.56, 0.32), (0.85, 0.85, 0.85), (1.0, 0.25, 0.7), (1.0, 0.75, 0.25), (0.2, 0.85, 1.0),
              (0.45, 1.0, 0.35), (0.7, 0.4, 1.0), (1.0, 0.45, 0.3))  # an old photo, black and white, neon, gold, ...
FACE_SPEED = 0.78  # each colour of the face change lasts this share of the one before
SWEEP = 0.15  # seconds a colour takes to sweep across her (the tug)
ERA_ROWS = ((0.55, 0.35), (0.85, 0.7), (0.3, 1.05), (1.0, 1.05))  # each pair of copies: how far out to either
# side (shares of half the picture's width where they stand) and how far behind her (model heights)
ERA_FADE = 0.3  # seconds a copy takes to fade in
ERA_COME = 0.7  # share of the Tint Time (before they fly in) over which the copies come
ERA_CONVERGE = 0.35  # seconds before the moment they fly into her


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_ERAS) == mask]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        bpy.data.meshes.remove(data)


def remove(mask, meshes=()):
    """Our copies of the dancer, and with `meshes` the tint in their materials."""
    for ob in objects(mask):
        _delete(ob)
    for ob in meshes:
        for mat in _materials(ob):
            materials.remove_tint(mat)


def _materials(ob):
    return [slot.material for slot in ob.material_slots
            if slot.material is not None and slot.material.name != materials.WIRE_MATERIAL]


def _tinted(settings, ob, whole):
    """The materials of the mesh to recolour: with `whole` all of them, else the outfit's (not the locked parts)."""
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock and not whole else []
    return [mat for mat in _materials(ob) if not any(fnmatch.fnmatchcase(mdl.material_key(mat), p) for p in patterns)]


def _fps(scene):
    return scene.render.fps / scene.render.fps_base


def _num(value):
    return ("%.1f" % value).rstrip("0").rstrip(".")


def _past(frame):
    return "(frame>=%s)" % _num(frame)


def _snap(f, beat_frames, reach, after):
    """`f` moved to the nearest beat when one is within `reach` frames and later than `after`."""
    if not beat_frames:
        return f
    near = min(beat_frames, key=lambda b: abs(b - f))
    return near if abs(near - f) < reach and near > after else f


def _face(start, moment, count, beat_frames):
    """The face change: from `start` a new colour (A, the next slot of the palette) at each of `count` - 1 steps,
    each FACE_SPEED as long as the one before, the last until the moment (on the beats when there are some)."""
    total = sum(FACE_SPEED ** k for k in range(count))
    first = (moment - start) / max(total, 1e-6)
    edges, f = [], start
    for k in range(count - 1):
        gap = first * FACE_SPEED ** k
        f += gap
        edges.append(_snap(f, beat_frames, 0.5 * gap, edges[-1] if edges else start))
        f = edges[-1]
    edges = [e for e in edges if e < moment - 0.5]
    return {"On": "%s*(frame<%s)" % (_past(start), _num(moment + 1.0)),
            "A": "+".join(_past(e) for e in edges) or "0", "B": 0.0, "Front": 2.0, "Side": 1.0}


def _tug(start, moment, count, fps, beat_frames):
    """The colour tug: `count` sweeps, one every period from `start` (a whole number of beats with beat sync), each
    SWEEP long, from the left and from the right in turn, colour A (slot 0) and B (slot 1) taking over from each other
    (the first sweep brings A over B)."""
    period = (moment - start) / float(max(count, 1))
    if len(beat_frames) > 1:
        beat = float(np.median(np.diff(beat_frames)))
        start = _snap(start, beat_frames, 0.5 * beat, start - beat)
        period = max(round(period / beat), 1) * beat
        count = max(min(count, int((moment - start) // period)), 1)
    edges = [start + k * period for k in range(count)]
    last = min(moment, start + count * period) - 0.5
    sweep = max(SWEEP * fps, 1.0)
    flips = "".join(("+" if k % 2 else "-") + _past(e) for k, e in enumerate(edges[1:], 1))
    a = "(%s)" % flips.lstrip("+") if flips else "0"  # 0 in the first sweep, 1 in the second, ...
    front = "clamp(fmod(min(frame,%s)-%s,%s)/%s,0,1)*2.4-1.2" % (_num(last), _num(start), _num(period), _num(sweep))
    return {"On": "%s*(frame<%s)" % (_past(start), _num(moment + 1.0)), "A": a, "B": "1-" + a, "Front": front,
            "Side": "1-2*" + a}


def _across(ob):
    """The middle and half the width of the mesh across it (x of its own space, undeformed)."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    x = co[0::3]
    if not len(x):
        return 0.0, 1.0
    return 0.5 * float(x.min() + x.max()), max(0.5 * float(x.max() - x.min()), 1e-6)


def _places(count, toward, side, height, wide):
    """Where the copies stand (offsets from her, world), in the order they come: in pairs to either side of her and
    behind her, away from the camera, left and right in turn (ERA_ROWS); `wide(back)` is the width of the picture
    `back` behind her."""
    out = []
    for k in range(count):
        pair, way = divmod(k, 2)
        across, back = ERA_ROWS[min(pair, len(ERA_ROWS) - 1)]
        lateral = 0.5 * across * wide(back * height) * (1.0 if way else -1.0)
        out.append(side * lateral - toward * (back * height))
    return out


def _eras(settings, mask, model, start, moment, height, beat_frames, collection):
    """The copies of every era: an object of ours per mesh of the old outfit, the copies coming one after another
    (on the beats when there are some), flying into her in the last ERA_CONVERGE seconds."""
    from . import cover_nodes
    from .node_groups import input_identifiers

    scene = settings.id_data
    fps = _fps(scene)
    count = max(2, min(settings.tint_count, len(ERA_COLORS)))
    lo, hi = mdl.rest_bounds(model.meshes)
    middle = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
    camera = shots.carrier(scene, mask)
    toward = (camera.matrix_world.translation - middle) if camera is not None else Vector((0.0, -1.0, 0.0))
    toward.z = 0.0
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    side = (-toward).cross(Vector((0.0, 0.0, 1.0)))
    if camera is not None and camera.type == "CAMERA":
        from .picture import _frame

        depth = max(-(camera.matrix_world.inverted() @ (middle + Vector((0.0, 0.0, 0.5 * height)))).z, 1e-3)

        def wide(back):
            return _frame(scene, camera, depth + back)[1]
    else:
        def wide(back):
            return 1.2 * height + back
    places = _places(count, toward, side, height, wide)
    end = float(moment)
    converge = end - ERA_CONVERGE * fps
    gap = max((converge - start) * ERA_COME / count, 1.0)
    comes = []
    for k in range(count):
        f = start + k * gap
        comes.append(_snap(f, beat_frames, 0.5 * gap, comes[-1] if comes else start - 1.0))
    keep = set()
    for k, source in enumerate(model.meshes):
        ob = next((o for o in objects(mask) if o.get(P_SOURCE) == source.name), None)
        if ob is None:
            ob = bpy.data.objects.new("%s %d" % (NAME, k), bpy.data.meshes.new("%s %d" % (NAME, k)))
            collection.objects.link(ob)
            ob[P_ERAS] = mask
            ob[P_SOURCE] = source.name
            ob.hide_select = True
        keep.add(ob.name)
        me = ob.data
        me.clear_geometry()
        me.from_pydata([tuple(p) for p in places], [], [])
        for name, values in (("mmdd_era", [float(i + 1) for i in range(count)]), ("mmdd_t0", comes)):
            attr = me.attributes.get(name) or me.attributes.new(name, "FLOAT", "POINT")
            attr.data.foreach_set("value", values)
        me.update()
        mod = next((m for m in ob.modifiers if m.type == "NODES"), None) or ob.modifiers.new(NAME, "NODES")
        mod.node_group = cover_nodes.ensure_eras_group()
        ids = input_identifiers(mod.node_group)
        for key, value in (("Dancer", source), ("Converge Start", converge), ("Converge End", end),
                           ("Fade", ERA_FADE * fps)):
            if ids.get(key) is not None:
                mod[ids[key]] = value
        ob.update_tag()
    for ob in objects(mask):
        if ob.name not in keep:
            _delete(ob)


def sync(settings, mask, models, moment):
    """The recolouring as the panel says, the big moment at frame `moment`: the tint in the old outfit's materials
    driven on the frame, and the copies of the dancers of every era; all taken away without it."""
    style = getattr(settings, "tint_style", "NONE")
    model = mdl.resolve(settings.base) if settings.base else None
    meshes = list(model.meshes) if model is not None else []
    if style == "NONE" or moment is None or not meshes or mask is None:
        if mask is not None:
            remove(mask, meshes)
        return
    scene = settings.id_data
    fps = _fps(scene)
    lo, hi = mdl.rest_bounds(meshes)
    height = max(settings.size_reference, hi.z - lo.z, 1e-3)
    moment = float(moment)
    start = max(moment - max(settings.tint_length, 0.2) * fps, float(scene.frame_start))
    beat_frames = beats.beat_frames() if settings.beat_sync else []
    count = max(2, min(settings.tint_count, materials.TINT_SLOTS))
    if style == "FACE":
        palette, drivers = FACE_COLORS, _face(start, moment, count, beat_frames)
    elif style == "TUG":
        palette = (tuple(settings.tint_color_a), tuple(settings.tint_color_b))
        drivers = _tug(start, moment, count, fps, beat_frames)
    else:  # ERAS: she keeps her colours; only her copies are tinted
        palette, drivers = ERA_COLORS, {"On": 0.0, "A": 0.0, "B": 0.0, "Front": 2.0, "Side": 1.0}
    for ob in meshes:  # (the face change and the copies the whole of her, the tug the outfit)
        middle, half = _across(ob)
        tinted = _tinted(settings, ob, style != "TUG")
        for mat in _materials(ob):
            if mat in tinted:
                materials.add_tint(mat)
                materials.update_tint(mat, palette, middle, half, drivers)
            else:
                materials.remove_tint(mat)
    if style == "ERAS":
        collection = mask.users_collection[0] if mask.users_collection else scene.collection
        _eras(settings, mask, model, start, moment, height, beat_frames, collection)
    else:
        for ob in objects(mask):
            _delete(ob)
