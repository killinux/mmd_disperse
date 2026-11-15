"""The symbiote's roar (咆哮, 1.29): after the grin the jaws part wide (two rows of teeth, the mouth dark red inside:
the goo coat's face, materials._symbiote_face), a long tongue lolls out over her chin and sways, and her head tilts
back; the mask splits only after it (materials.face_beats times all of it).

Our objects: the tongue, a mesh object whose node tree (node_groups.build_tongue_group) makes it every frame, out of
her mouth and back in by the frame; it rides on her head bone (Child Of), placed in her rest pose just behind her
mouth (under her eyes, found by her eye bones), +Y the way she faces. And an empty whose turn (a frame driver) a Copy
Rotation constraint on her neck bone adds after the dance's own (in the bone's local space, After Original), so the
dance is not touched; removing the effect takes the constraint off. Her neck, not her head: her lower face is partly
bound to her neck, and turning the head alone would leave her mouth behind the tongue.

1.31: strands of slime between its jaws (Slime Strands): another mesh object placed and riding as the tongue, its
points the strands' halves (node_groups.build_slime_group makes them every frame): they stretch and thin as the jaws
part (as the face's Mouth Open), on either side of the tongue at the teeth's inner edge on her face, and some snap,
their halves pulling back to the teeth.
"""

import hashlib
import math
import random

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import clock, materials, motion, node_groups

P_ROAR = "mmd_disperse_roar"  # on our objects: the mask of their effect
P_BONE = "mmd_disperse_roar_bone"  # on the empty: (armature, bone) its constraint is on
TONGUE = "MMD Disperse Tongue"
TILT = "MMD Disperse Roar Tilt"
CONSTRAINT = "MMD Disperse Roar"
TONGUE_LENGTH = 0.2  # the tongue: this long (a share of her height) ...
TONGUE_WIDTH = 0.42  # ... this wide either side of its middle at the root (eye distances) ...
TONGUE_FLAT = 0.45  # ... and this thick for its width
MOUTH = (0.9, 0.2)  # it comes out this far under her eye bones and this far in front of them (eye distances) ...
LIPS = (0.12, 0.12)  # ... or this far behind her lips (found within this far of that line on her face) ...
DOWN = math.radians(15.0)  # ... heading this far down from the way she faces
OUT = (0.15, 0.3, 0.1)  # it starts out this many seconds into the roar, takes this many, is back in this many before its end
TILT_ANGLE = 0.38  # radians her head tilts back (22 degrees) ...
TILT_TIMES = (0.35, 0.4)  # ... taking this many seconds, and this many to come forward again at the end
SLIME = "MMD Disperse Slime"
P_PART = "mmd_disperse_roar_part"  # (1.31) on the slime: "SLIME" (the tongue and the empty have none)
P_SLIME = "mmd_disperse_slime_key"  # (1.31.1) on the slime: what its mesh holds (made again only when it changes)
SLIME_ACROSS = (0.48, 0.62, 0.76, 0.9)  # 1.31, the slime between its jaws: strands this far either side of the
# middle of the grin (eye distances; the tongue takes the middle) ...
SLIME_JITTER = 0.03  # ... give or take this much (they stay apart) ...
SLIME_THICK = (0.03, 0.05)  # ... this thick at the teeth (radius, eye distances) ...
SLIME_ROOT = 0.5  # ... from this far up the teeth (a share of how far they reach into the gap) ...
SLIME_FRONT = 0.0  # ... their roots on her face (they grow out of the teeth) ...
SLIME_BAND = 0.12  # ... (her face found within this far of where they are, eye distances) ...
SLIME_FIRST = 0.8  # ... the first may snap once the jaws are this far through parting ...
SLIME_SNAP = (0.65, 0.6)  # ... this share of them snap (picked at random), within this share of the rest of the roar
SLIME_PULL = 0.18  # ... and their halves pull back to the teeth in this many seconds
SLIME_POINTS = 8  # points along each half of a strand
SLIME_ATTRS = ("mmdd_w", "mmdd_upper", "mmdd_gap", "mmdd_teeth", "mmdd_snap", "mmdd_seed", "mmdd_thick")


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_ROAR) == mask]


def tongue(mask):
    """The tongue of the roar of `mask`'s effect, or None."""
    return next((ob for ob in objects(mask) if ob.type == "MESH" and ob.get(P_PART) is None), None)


def slime(mask):
    """(1.31) The strands of slime between its jaws, or None."""
    return next((ob for ob in objects(mask) if ob.type == "MESH" and ob.get(P_PART) == "SLIME"), None)


def _drop_constraint(empty):
    where = empty.get(P_BONE)
    arm = bpy.data.objects.get(where[0]) if where else None
    pb = arm.pose.bones.get(where[1]) if arm is not None and arm.pose is not None else None
    if pb is not None:
        for con in [c for c in pb.constraints if c.name.startswith(CONSTRAINT)]:
            pb.constraints.remove(con)


def remove(mask):
    for ob in objects(mask):
        if ob.type == "EMPTY":
            ob.driver_remove("rotation_euler")
            _drop_constraint(ob)
        data = ob.data
        bpy.data.objects.remove(ob)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)


def _bones(arm):
    bones = arm.data.bones if arm is not None else {}
    head = next((bones[n] for n in motion.HEAD if n in bones), None)
    eyes = [next((bones[n] for n in names if n in bones), None) for names in motion.EYES]
    return head, eyes


def _neck(arm, head):
    """The bone her head tilts back on: her neck (motion.NECK), else the head itself."""
    bones = arm.data.bones
    neck = next((bones[n] for n in motion.NECK if n in bones), None)
    return neck if neck is not None else head


def _ahead(head, eyes):
    """The way she faces (armature space, level): her eyes in front of her head bone; else -Y."""
    ahead = (eyes[0].head_local + eyes[1].head_local) / 2.0 - head.head_local
    ahead.z = 0.0
    return ahead.normalized() if ahead.length > 1e-6 else Vector((0.0, -1.0, 0.0))


def _lips(meshes, arm, head, eyes):
    """How far in front of the line under her eyes where the tongue comes out her lips are (along the way she faces,
    armature units, rest pose): the frontmost vertex of `meshes` near that line; None when none is."""
    left, right = eyes[0].head_local, eyes[1].head_local
    size = (right - left).length
    ahead = _ahead(head, eyes)
    side = ahead.cross(Vector((0.0, 0.0, 1.0)))
    line = (left + right) / 2.0 - Vector((0.0, 0.0, MOUTH[0] * size))
    best = None
    for ob in meshes:
        me = ob.data
        if not len(me.vertices):
            continue
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        to_arm = np.array(arm.matrix_world.inverted() @ ob.matrix_world, dtype=np.float64)
        d = co.reshape(-1, 3) @ to_arm[:3, :3].T + to_arm[:3, 3] - np.array(line)
        near = (np.abs(d[:, 2]) < LIPS[1] * size) & (np.abs(d @ np.array(side)) < LIPS[1] * size)
        if near.any():
            front = float((d[near] @ np.array(ahead)).max())
            best = front if best is None else max(best, front)
    return best


def _face_front(meshes, arm, head, eyes, across):
    """(1.31) How far in front of the middle of her eyes her face is on the middle line of the symbiote's grin
    (materials._symbiote_face) at each of `across` (eye distances along the line from her left eye to her right, from
    their middle), along the way she faces in eye distances, rest pose: the frontmost vertex of `meshes` there, not
    much in front of her lips (no hair hanging there); None where there is none."""
    from .effect import EYE_SHIFT  # (where the symbiote's face is drawn: round its eyes)

    left, right = eyes[0].head_local, eyes[1].head_local
    size = (right - left).length
    if size < 1e-6:
        return [None] * len(across)
    axis = (right - left).normalized()
    ahead = _ahead(head, eyes)
    up = Vector((0.0, 0.0, 1.0))
    mid = (left + right) / 2.0 + up * ((EYE_SHIFT[1] - materials.TEETH_SHAPE[0]) * size)
    pts = []
    for ob in meshes:
        me = ob.data
        if not len(me.vertices):
            continue
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        to_arm = np.array(arm.matrix_world.inverted() @ ob.matrix_world, dtype=np.float64)
        pts.append(co.reshape(-1, 3) @ to_arm[:3, :3].T + to_arm[:3, 3])
    if not pts:
        return [None] * len(across)
    d = np.concatenate(pts) - np.array(mid)
    side, high, front = d @ np.array(axis), d @ np.array(up), d @ np.array(ahead)
    band = np.abs(high) < SLIME_BAND * size
    middle = band & (np.abs(side) < SLIME_BAND * size)
    lips = float(front[middle].max()) if middle.any() else None
    out = []
    for gx in across:
        near = band & (np.abs(side - gx * size) < 0.5 * SLIME_BAND * size)
        if lips is not None:
            near &= front < lips + SLIME_BAND * size
        out.append(float(front[near].max()) / size if near.any() else None)
    return out


def _ride(ob, place, arm, head):
    """`ob` put at `place` (world, her rest pose) and riding on her head bone (Child Of, its inverse her head's rest)."""
    ob.parent = None
    for con in list(ob.constraints):
        ob.constraints.remove(con)
    ob.matrix_basis = place
    con = ob.constraints.new("CHILD_OF")
    con.name = CONSTRAINT
    con.target, con.subtarget = arm, head.name
    con.inverse_matrix = (arm.matrix_world @ head.matrix_local).inverted()


def _drive_time(ob, mod, ids, own, mask):
    """(1.30) A driver on the Effect Time input of `ob`'s modifier `mod` when the effect has a time of its own."""
    if ids.get("Effect Time") is not None:
        path = 'modifiers["%s"]["%s"]' % (mod.name, ids["Effect Time"])
        ob.driver_remove(path)
        if own:
            clock.drive(ob, path, "frame", mask)


def _drop(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        bpy.data.meshes.remove(data)


def _sync_slime(settings, mask, collection, place, arm, head, eyes, shown, span, fps, own):
    """(1.31) The strands of slime between its jaws (Slime Strands) while it roars over `span` (frames): an object at
    `place` riding on her head as the tongue does, its mesh the strands' halves as points along them (their attributes
    SLIME_ATTRS, node_groups.build_slime_group); gone when off."""
    ob = slime(mask)
    if not getattr(settings, "venom_slime", False):
        if ob is not None:
            _drop(ob)
        return
    if ob is None:
        ob = bpy.data.objects.new(SLIME, bpy.data.meshes.new(SLIME))
        collection.objects.link(ob)
        ob[P_ROAR] = mask
        ob[P_PART] = "SLIME"
        ob.hide_select = True
        ob.modifiers.new("MMD Disperse Slime", "NODES").node_group = node_groups.ensure_slime_group()
    mod = next((m for m in ob.modifiers if m.type == "NODES"), None)
    if mod is not None and (mod.node_group is None
                            or mod.node_group.get("mmd_disperse_version") != node_groups.VERSION):
        mod.node_group = node_groups.ensure_slime_group()
    _ride(ob, place, arm, head)
    start, end = span
    rng = random.Random(131)
    across = [sign * (a + rng.uniform(-SLIME_JITTER, SLIME_JITTER)) for a in SLIME_ACROSS for sign in (-1.0, 1.0)]
    # (her face where they are: the new outfit's, measured on its own skeleton, as her lips for the tongue)
    s_head, s_eyes = _bones(shown.armature)
    fronts = (_face_front(shown.meshes, shown.armature, s_head, s_eyes, across)
              if s_head is not None and all(e is not None for e in s_eyes) else [None] * len(across))
    from .effect import EYE_SHIFT

    left, right = eyes[0].head_local, eyes[1].head_local
    size = (right - left).length
    axis = (right - left).normalized()
    ahead = _ahead(head, eyes)
    up = Vector((0.0, 0.0, 1.0))
    mid = (left + right) / 2.0 + up * ((EYE_SHIFT[1] - materials.TEETH_SHAPE[0]) * size)
    world = arm.matrix_world
    inv = place.inverted()
    turn = inv.to_3x3() @ world.to_3x3()
    size_w = (world @ right - world @ left).length
    open_f, close_f = materials.ROAR_OPEN[0] * fps, materials.ROAR_OPEN[1] * fps
    first = start + SLIME_FIRST * open_f
    window = max(end - close_f - first, 1.0) * SLIME_SNAP[1]
    verts, edges = [], []
    attrs = {name: [] for name in SLIME_ATTRS}
    order = list(range(len(across)))
    rng.shuffle(order)
    snapping = set(order[:int(round(SLIME_SNAP[0] * len(across)))])
    for i, (gx, front) in enumerate(zip(across, fronts)):
        snap = first + rng.random() * window if i in snapping else 1e9
        seed, thick = rng.random(), rng.uniform(*SLIME_THICK) * size_w
        if front is None:
            continue
        # where the jaws part there (materials._symbiote_face: the grin narrowing to its corners, the teeth's saw)
        taper = max(1.0 - (gx / materials.TEETH_SHAPE[1]) ** 2, 0.0)
        saw = abs((gx * materials.TEETH_SHAPE[3] + 0.5) % 1.0 - 0.5) * 2.0
        gap = materials.MOUTH_GAP * math.sqrt(taper) / 2.0 * size_w
        teeth = SLIME_ROOT * materials.TEETH_SHAPE[2] * taper * (0.45 + 0.55 * saw) * size_w
        if gap - teeth < 2.0 * thick:
            continue  # (the jaws hardly part past the teeth there)
        p = inv @ (world @ (mid + axis * (gx * size) + ahead * ((front + SLIME_FRONT) * size)))
        for upper in (1.0, 0.0):
            base = len(verts)
            for k in range(SLIME_POINTS):
                verts.append(tuple(p))
                for name, value in (("mmdd_w", k / (SLIME_POINTS - 1.0)), ("mmdd_upper", upper), ("mmdd_gap", gap),
                                    ("mmdd_teeth", teeth), ("mmdd_snap", snap), ("mmdd_seed", seed),
                                    ("mmdd_thick", thick)):
                    attrs[name].append(value)
            edges += [(base + k, base + k + 1) for k in range(SLIME_POINTS - 1)]
    # (a new mesh swapped in when what it holds changes, the old one dropped: a sync runs on every setting changed,
    # and clearing and refilling the mesh in place while its evaluated copy is about can crash Blender 3.6)
    digest = hashlib.md5(np.array(verts, dtype=np.float32).tobytes())
    for name in SLIME_ATTRS:
        digest.update(np.array(attrs[name], dtype=np.float32).tobytes())
    key = digest.hexdigest()
    if ob.get(P_SLIME) != key or len(ob.data.vertices) != len(verts):
        me = bpy.data.meshes.new(SLIME)
        me.from_pydata(verts, edges, [])
        for name, values in attrs.items():
            attr = me.attributes.new(name, "FLOAT", "POINT")
            if values:
                attr.data.foreach_set("value", np.array(values, dtype=np.float32))
        me.update()
        old = ob.data
        ob.data = me
        if old is not None and old.users == 0:
            bpy.data.meshes.remove(old)
        ob[P_SLIME] = key
    if mod is not None:
        ids = node_groups.input_identifiers(mod.node_group)
        for name, value in (("Start", start), ("End", end), ("Open Frames", open_f), ("Close Frames", close_f),
                            ("Pull Frames", SLIME_PULL * fps), ("Up", tuple((turn @ up).normalized())),
                            ("Out", tuple((turn @ ahead).normalized())),
                            ("Material", materials.ensure_slime_material(settings.venom_color,
                                                                         settings.venom_metallic)),
                            ("Effect Clock", own)):
            if ids.get(name) is not None:
                mod[ids[name]] = value
        _drive_time(ob, mod, ids, own, mask)
    ob.update_tag()


def _mouth(arm, head, eyes, lips=None):
    """(where the tongue starts, the way it heads out, up, her eye distance) in the world, rest pose: just behind her
    lips (`lips`: _lips) on the line under her eyes, heading a little down."""
    left, right = eyes[0].head_local, eyes[1].head_local
    size = (right - left).length
    ahead = _ahead(head, eyes)
    up = Vector((0.0, 0.0, 1.0))
    deep = (lips - LIPS[0] * size) if lips is not None else MOUTH[1] * size
    point = (left + right) / 2.0 - up * (MOUTH[0] * size) + ahead * deep
    out = (ahead * math.cos(DOWN) - up * math.sin(DOWN)).normalized()
    world = arm.matrix_world
    turn = world.to_3x3()
    return (world @ point, (turn @ out).normalized(), (turn @ up).normalized(),
            (world @ right - world @ left).length)


def _tilt_sign(bone, ahead):
    """+1 or -1: the way round `bone`'s own X axis that turns her face up (its tip back, away from `ahead`, armature
    space)."""
    z_axis = bone.matrix_local.to_3x3().col[2]
    return -1.0 if z_axis.dot(ahead) > 0.0 else 1.0


def sync(settings, mask, models, beats):
    """The roar as the face's `beats` time it (materials.face_beats: its "roar" (start, end) frames, "fps"); taken away
    when there is none (Roar off, no eyes, no room for it) or no head or eye bones."""
    if mask is None:
        return
    model = next(iter(models), None) if models else None
    arm = model.armature if model is not None else None
    head, eyes = _bones(arm)
    span = beats.get("roar") if beats else None
    if not getattr(settings, "venom_roar", False) or span is None or head is None or any(e is None for e in eyes):
        remove(mask)
        return
    scene = settings.id_data
    fps = float(beats.get("fps", scene.render.fps / scene.render.fps_base))
    start, end = float(span[0]), float(span[1])
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    own = clock.has_time(mask)  # (1.30: it comes out and sways by the transformation's own time)
    # --- the tongue
    tongue_ob = tongue(mask)
    if tongue_ob is None:
        tongue_ob = bpy.data.objects.new(TONGUE, bpy.data.meshes.new(TONGUE))
        collection.objects.link(tongue_ob)
        tongue_ob[P_ROAR] = mask
        tongue_ob.hide_select = True
        mod = tongue_ob.modifiers.new("MMD Disperse Tongue", "NODES")
        mod.node_group = node_groups.ensure_tongue_group()
    mod = next((m for m in tongue_ob.modifiers if m.type == "NODES"), None)
    if mod is not None and mod.node_group is not None and mod.node_group.get("mmd_disperse_version") != \
            node_groups.VERSION:
        mod.node_group = node_groups.ensure_tongue_group()
    # (her lips on the face that shows: the new outfit's, measured on its own skeleton)
    shown = models[-1]
    s_head, s_eyes = _bones(shown.armature)
    lips = (_lips(shown.meshes, shown.armature, s_head, s_eyes)
            if s_head is not None and all(e is not None for e in s_eyes) else None)
    point, out, up, size = _mouth(arm, head, eyes, lips)
    side = out.cross(up).normalized()
    lift = side.cross(out).normalized()
    place = Matrix(((side.x, out.x, lift.x, point.x), (side.y, out.y, lift.y, point.y),
                    (side.z, out.z, lift.z, point.z), (0.0, 0.0, 0.0, 1.0)))
    _ride(tongue_ob, place, arm, head)
    height = max(settings.size_reference, 1e-3)
    if mod is not None:
        ids = node_groups.input_identifiers(mod.node_group)
        for name, value in (("Length", TONGUE_LENGTH * height), ("Width", TONGUE_WIDTH * size),
                            ("Flat", TONGUE_FLAT), ("Start", start + OUT[0] * fps), ("End", end - OUT[2] * fps),
                            ("Out Frames", OUT[1] * fps), ("Material", materials.ensure_tongue_material()),
                            ("Effect Clock", own)):
            if ids.get(name) is not None:
                mod[ids[name]] = value
        _drive_time(tongue_ob, mod, ids, own, mask)
    tongue_ob.update_tag()
    # --- (1.31) strands of slime between its jaws
    _sync_slime(settings, mask, collection, place, arm, head, eyes, shown, (start, end), fps, own)
    # --- her head tilting back
    empty = next((ob for ob in objects(mask) if ob.type == "EMPTY"), None)
    if empty is None:
        empty = bpy.data.objects.new(TILT, None)
        collection.objects.link(empty)
        empty[P_ROAR] = mask
        empty.hide_select = True
        empty.empty_display_size = 0.01
    _drop_constraint(empty)
    neck = _neck(arm, head)
    empty[P_BONE] = [arm.name, neck.name]
    empty.rotation_mode = "XYZ"
    angle = TILT_ANGLE * _tilt_sign(neck, _ahead(head, eyes))
    clock.drive(empty, "rotation_euler", "%.5f * smoothstep(%.2f, %.2f, frame) * (1 - smoothstep(%.2f, %.2f, frame))"
                % (angle, start, start + TILT_TIMES[0] * fps, end - TILT_TIMES[1] * fps, end), mask, 0)
    pb = arm.pose.bones[neck.name]
    tilt = pb.constraints.new("COPY_ROTATION")
    tilt.name = CONSTRAINT
    tilt.target = empty
    tilt.use_x, tilt.use_y, tilt.use_z = True, False, False
    tilt.mix_mode = "AFTER"
    tilt.target_space = "WORLD"  # (the empty has no parent; its Local Space reads as no turn at all)
    tilt.owner_space = "LOCAL"
