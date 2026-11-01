"""The rainbow afterimages (彩虹残影, 1.26): round the big moment she leaves a trail of afterimages behind her, a new
one every few frames. Each stays where she was when it was taken, drifting back and to one side as it ages, glows in
a colour a step further round the colour wheel than the one before (or all in the glow colour) and fades as the next
ones come: the old outfit's before the moment, the new outfit's from it (Cyberpunk: Edgerunners' Sandevistan).

Our objects, for each mesh of the outfits: a recording (a mesh of loose points: where the mesh's vertices were, world
space, at each snapshot, one snapshot after another; taken by playing the dance with only the skinning on: the rest
of her modifiers off and the bones the physics moves in their own pose, unless the rigid bodies are baked) and a twin
(the same mesh data at the world's origin, in materials of its own, slot by slot the afterimage light cut out as her
material there is, carrying cover_nodes' afterimage group: the latest snapshots as copies of the mesh).
"""

import bpy
import numpy as np

from . import materials

P_AFTER = "mmd_disperse_after"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_after_kind"  # ... TWIN or RECORDING ...
P_SOURCE = "mmd_disperse_after_source"  # ... the mesh it is of
P_KEY = "mmd_disperse_after_key"  # on a recording: what it was taken for (taken again when that changes) ...
P_ENDS = "mmd_disperse_after_ends"  # ... and the middle of its first and last snapshot (x, y, z, x, y, z)
NAME = "MMD Disperse Afterimage"
HUE_START = 0.45  # the first afterimage's hue (cyan green) ...
HUE_STEP = -0.065  # ... and each next one a step further round the wheel (green, yellow, orange, red, magenta ...)
BACK = 0.55  # they drift this much away from the camera for ...
SIDE = 0.85  # ... this much to the side: the side she came from (straight back they would hide behind her)
MOVED = 0.03  # (she counts as having come from a side when she moved this share of her height across the picture)
PUSH = 0.04  # each is pushed this much (a share of her height) away from the camera at once: the newest ones, still
# where she is, stay behind her instead of showing through her


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_AFTER) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _drop(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)


def remove(mask):
    for ob in objects(mask):
        _drop(ob)
    if not any(ob.get(P_AFTER) is not None for ob in bpy.data.objects):
        from .cover_nodes import AFTER_GROUP

        ng = bpy.data.node_groups.get(AFTER_GROUP)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
        for mat in materials.after_materials():
            if mat.users == 0:
                bpy.data.materials.remove(mat)


def _physics(scene, armature):
    """The constraints that let the rigid bodies move bones of `armature` (they aim at objects that are not armatures:
    a new outfit following the old model's armature copies its bones, and that stays); none when the rigid bodies are
    baked (then the physics plays right wherever the dance is played from)."""
    world = scene.rigidbody_world
    if world is not None and world.point_cache is not None and world.point_cache.is_baked:
        return []
    found = []
    for pb in armature.pose.bones if armature is not None else ():
        for con in pb.constraints:
            target = getattr(con, "target", None)
            if target is not None and target.type != "ARMATURE" and not con.mute:
                found.append(con)
    return found


def _record(scene, model, meshes, frames, hidden):
    """Where the vertices of `meshes` (of `model`) are at each of `frames`, world space: one (len(frames), vertices, 3)
    float32 array per mesh, None for a mesh whose posed vertices do not line up with its own. Only the skinning counts:
    the other modifiers are off meanwhile, the physics bones keep their own pose (unless the rigid bodies are baked:
    played from anywhere, unbaked rigid bodies only hang where they last were)."""
    from . import motion

    out = [np.zeros((len(frames), len(ob.data.vertices), 3), dtype=np.float32) for ob in meshes]
    good = [True] * len(meshes)

    def visit(i, _frame, positions):
        for j, pts in enumerate(positions):
            if len(pts) == out[j].shape[1]:
                out[j][i] = pts
            else:
                good[j] = False

    paused = [m for ob in meshes for m in ob.modifiers if m.type != "ARMATURE" and m.show_viewport]
    # (every armature posing them, and every armature those copy their bones from: the new outfit may follow the old
    # model's)
    armatures = {model.armature} | {m.object for ob in meshes for m in ob.modifiers
                                     if m.type == "ARMATURE" and m.object is not None}
    todo = [arm for arm in armatures if arm is not None]
    while todo:
        for pb in todo.pop().pose.bones:
            for con in pb.constraints:
                target = getattr(con, "target", None)
                if target is not None and target.type == "ARMATURE" and target not in armatures:
                    armatures.add(target)
                    todo.append(target)
    held = [con for arm in armatures for con in _physics(scene, arm)]
    for m in paused:
        m.show_viewport = False
    for con in held:
        con.mute = True
    try:
        motion.play(scene, model.armature, frames, hidden, meshes, visit)
    finally:
        for m in paused:
            m.show_viewport = True
        for con in held:
            con.mute = False
    return [o if ok else None for o, ok in zip(out, good)]


def _recording(source, mask, collection, positions, key):
    """The recording of mesh `source`: its snapshots' points one after another (world space, at the origin)."""
    ob = next((o for o in objects(mask, "RECORDING") if o.get(P_SOURCE) == source.name), None)
    if ob is None:
        ob = bpy.data.objects.new("%s Recording %s" % (NAME, source.name), bpy.data.meshes.new(NAME + " Recording"))
        collection.objects.link(ob)
        ob[P_AFTER], ob[P_KIND], ob[P_SOURCE] = mask, "RECORDING", source.name
        ob.hide_select = True
        ob.hide_render = True
    if positions is not None:
        me = ob.data
        count = positions.shape[0] * positions.shape[1]
        if len(me.vertices) != count:
            me.clear_geometry()
            me.vertices.add(count)
        me.vertices.foreach_set("co", positions.reshape(-1))
        me.update()
        ob[P_KEY] = key
        middles = positions.mean(axis=1)
        ob[P_ENDS] = [float(v) for v in tuple(middles[0]) + tuple(middles[-1])]
    ob.parent = None
    ob.matrix_world.identity()
    try:
        ob.hide_set(True)
    except RuntimeError:  # (not in the view layer: hidden there anyway)
        pass
    return ob


def _twin(source, mask, collection, group):
    """The twin of mesh `source`: its mesh data at the world's origin, in the afterimages' materials, carrying `group`."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_AFTER], ob[P_KIND], ob[P_SOURCE] = mask, "TWIN", source.name
        ob.hide_select = True
        for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
            if hasattr(ob, flag):
                setattr(ob, flag, False)
    for slot, hers in zip(ob.material_slots, source.material_slots):
        if slot.link != "OBJECT":
            slot.link = "OBJECT"
        mat = materials.after_material(hers.material)
        if slot.material != mat:
            slot.material = mat
    ob.parent = None
    ob.matrix_world.identity()
    mod = next((m for m in ob.modifiers if m.type == "NODES"), None)
    for other in [m for m in ob.modifiers if m != mod]:
        ob.modifiers.remove(other)
    if mod is None:
        mod = ob.modifiers.new(NAME, "NODES")
    if mod.node_group != group:
        mod.node_group = group
    return ob, mod


def _drift(scene, settings, moment, ends, height, fps):
    """(drift, push): units a frame the afterimages drift, away from the camera (at the moment) and to the side she came
    from (the camera's left when she kept to her place), and the push away from the camera they all get."""
    from mathutils import Vector

    from . import sampling

    start, end = Vector(ends[:3]), Vector(ends[3:])
    camera = sampling.camera_at(scene, moment)
    away, side = Vector((0.0, 1.0, 0.0)), Vector((1.0, 0.0, 0.0))
    if camera is not None:
        cam = sampling.matrix_at(camera, moment)
        away = 0.5 * (start + end) - cam.translation
        side = cam.to_3x3().col[0].copy()
    away.z = side.z = 0.0
    away = away.normalized() if away.length > 1e-6 else Vector((0.0, 1.0, 0.0))
    side = side.normalized() if side.length > 1e-6 else Vector((1.0, 0.0, 0.0))
    across = (end - start).dot(side)
    way = -1.0 if across > MOVED * height else 1.0 if across < -MOVED * height else -1.0
    drift = BACK * away + SIDE * way * side
    return tuple(drift.normalized() * (settings.after_drift * height / fps)), tuple(away * (PUSH * height))


def sync(settings, mask, models, moment):
    """The afterimages as the panel says, round the big moment at frame `moment`; all of it taken away when it is
    off."""
    from . import cover_nodes
    from .node_groups import input_identifiers

    if mask is None:
        return
    if not getattr(settings, "after_enable", False) or moment is None or not models:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    gap = max(int(settings.after_gap), 1)
    m = float(moment)
    first = int(round(m - settings.after_lead * fps))
    count = max(int((m + settings.after_tail * fps - first) // gap) + 1, 1)
    frames = [first + k * gap for k in range(count)]
    # the old outfit's snapshots before the moment, the new outfit's from it (one outfit: all of them)
    if len(models) > 1:
        cut = sum(1 for f in frames if f < m)
        parts = [(models[0], frames[:cut], 0), (models[1], frames[cut:], cut)]
    else:
        parts = [(models[0], frames, 0)]
    parts = [p for p in parts if p[1] and p[0].armature is not None]
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    group = cover_nodes.ensure_after_group()
    ids = input_identifiers(group)
    height = max(settings.size_reference, 1e-3)
    ours = [ob for ob in bpy.data.objects if ob.get(P_AFTER) is not None]
    everyone = [ob for model in models for ob in model.meshes]
    keep, made = [], []
    ends = []
    for model, part, offset in parts:
        meshes = [ob for ob in model.meshes if ob.material_slots and len(ob.data.vertices)]
        action = model.armature.animation_data.action if model.armature.animation_data else None
        key = "%d|%d|%d|%.3f|%s|%s" % (part[0], gap, len(part), fps, model.armature.name,
                                       action.name if action is not None else "")
        stale = [ob for ob in meshes
                 if next((r for r in objects(mask, "RECORDING") if r.get(P_SOURCE) == ob.name
                          and r.get(P_KEY) == key and len(r.data.vertices) == len(part) * len(ob.data.vertices)),
                         None) is None]
        taken = {}
        if stale:  # (nothing else to compute meanwhile: the rest of her and of the effect off)
            from .effect import P_MASK

            hidden = everyone + ours + [ob for ob in bpy.data.objects if ob.get(P_MASK) == mask]
            taken = dict(zip(stale, _record(scene, model, stale, part, hidden)))
        for ob in meshes:
            if ob in taken and taken[ob] is None:  # (its posed vertices do not line up with its own: left out)
                continue
            recording = _recording(ob, mask, collection, taken.get(ob), key)
            if recording.get(P_ENDS) is None or len(recording.data.vertices) != len(part) * len(ob.data.vertices):
                continue
            twin, mod = _twin(ob, mask, collection, group)
            keep += [recording, twin]
            made.append((mod, recording, part, offset))
            ends.append((offset, len(ob.data.vertices), list(recording[P_ENDS])))
    drift = push = (0.0, 0.0, 0.0)
    if ends:  # (from the middle of the biggest mesh's first snapshot to the middle of the last one's last)
        start = min(ends, key=lambda e: (e[0], -e[1]))[2][:3]
        end = max(ends, key=lambda e: (e[0], e[1]))[2][3:]
        drift, push = _drift(scene, settings, m, start + end, height, fps)
    for mod, recording, part, offset in made:
        for name, value in (("Recording", recording), ("First", float(part[0])), ("Gap", float(gap)),
                            ("Spawns", len(part)), ("Count", int(settings.after_count)),
                            ("Hue", HUE_START + offset * HUE_STEP), ("Hue Step", HUE_STEP), ("Drift", drift), ("Push", push)):
            if name in ids:
                mod[ids[name]] = value
        mod.id_data.update_tag()
    materials.update_after(settings.after_style, tuple(settings.glow_color), settings.after_glow)
    for ob in objects(mask):
        if ob not in keep:
            _drop(ob)
