"""The symbiote's roar (咆哮, 1.29): after the grin the jaws part wide (two rows of teeth, the mouth dark red inside:
the goo coat's face, materials._symbiote_face), a long tongue lolls out over her chin and sways, and her head tilts
back; the mask splits only after it (materials.face_beats times all of it).

Our objects: the tongue, a mesh object whose node tree (node_groups.build_tongue_group) makes it every frame, out of
her mouth and back in by the frame; it rides on her head bone (Child Of), placed in her rest pose just behind her
mouth (under her eyes, found by her eye bones), +Y the way she faces. And an empty whose turn (a frame driver) a Copy
Rotation constraint on her neck bone adds after the dance's own (in the bone's local space, After Original), so the
dance is not touched; removing the effect takes the constraint off. Her neck, not her head: her lower face is partly
bound to her neck, and turning the head alone would leave her mouth behind the tongue.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials, motion, node_groups

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


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_ROAR) == mask]


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
    found = {ob.type: ob for ob in objects(mask)}
    # --- the tongue
    tongue = found.get("MESH")
    if tongue is None:
        tongue = bpy.data.objects.new(TONGUE, bpy.data.meshes.new(TONGUE))
        collection.objects.link(tongue)
        tongue[P_ROAR] = mask
        tongue.hide_select = True
        mod = tongue.modifiers.new("MMD Disperse Tongue", "NODES")
        mod.node_group = node_groups.ensure_tongue_group()
    mod = next((m for m in tongue.modifiers if m.type == "NODES"), None)
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
    tongue.parent = None
    for con in list(tongue.constraints):
        tongue.constraints.remove(con)
    tongue.matrix_basis = Matrix(((side.x, out.x, lift.x, point.x), (side.y, out.y, lift.y, point.y),
                                  (side.z, out.z, lift.z, point.z), (0.0, 0.0, 0.0, 1.0)))
    con = tongue.constraints.new("CHILD_OF")
    con.name = CONSTRAINT
    con.target, con.subtarget = arm, head.name
    con.inverse_matrix = (arm.matrix_world @ head.matrix_local).inverted()
    height = max(settings.size_reference, 1e-3)
    if mod is not None:
        ids = node_groups.input_identifiers(mod.node_group)
        for name, value in (("Length", TONGUE_LENGTH * height), ("Width", TONGUE_WIDTH * size),
                            ("Flat", TONGUE_FLAT), ("Start", start + OUT[0] * fps), ("End", end - OUT[2] * fps),
                            ("Out Frames", OUT[1] * fps), ("Material", materials.ensure_tongue_material())):
            if ids.get(name) is not None:
                mod[ids[name]] = value
    tongue.update_tag()
    # --- her head tilting back
    empty = found.get("EMPTY")
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
    empty.driver_remove("rotation_euler", 0)
    angle = TILT_ANGLE * _tilt_sign(neck, _ahead(head, eyes))
    driver = empty.driver_add("rotation_euler", 0).driver
    driver.type = "SCRIPTED"
    driver.expression = "%.5f * smoothstep(%.2f, %.2f, frame) * (1 - smoothstep(%.2f, %.2f, frame))" % (
        angle, start, start + TILT_TIMES[0] * fps, end - TILT_TIMES[1] * fps, end)
    pb = arm.pose.bones[neck.name]
    tilt = pb.constraints.new("COPY_ROTATION")
    tilt.name = CONSTRAINT
    tilt.target = empty
    tilt.use_x, tilt.use_y, tilt.use_z = True, False, False
    tilt.mix_mode = "AFTER"
    tilt.target_space = "WORLD"  # (the empty has no parent; its Local Space reads as no turn at all)
    tilt.owner_space = "LOCAL"
