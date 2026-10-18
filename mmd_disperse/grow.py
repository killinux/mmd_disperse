"""Taller and stronger (长高变壮, 1.13): at the big moment the dancer grows a little taller and broader in the chest and
shoulders over half a second (He-Man's first change). The old model's armature object scales up about its origin
(its delta scale: the feet stay on the floor), the chest bone grows across (the shoulders and arms with it) and the
neck shrinks back by as much (the head keeps its size). All of it is drivers on the frame, so the dance's own
animation is not touched; removing the effect takes them off and puts the values back."""

import bpy

from . import motion

P_GROW = "mmd_disperse_grow"  # on the armature: the mask of the effect that drives it ...
P_SCALE = "mmd_disperse_grow_scale"  # ... its delta scale before ...
P_BONES = "mmd_disperse_grow_bones"  # ... and the bones driven, with their scale before
TALLER = 0.03  # at Taller and Stronger 1: this much taller ...
BROADER = 0.06  # ... and this much broader in the chest
BEFORE = 0.1  # seconds it starts before the moment ...
AFTER = 0.5  # ... and it is grown this long after
CHEST = ("上半身2", "上半身", "UpperBody2", "UpperBody", "upper body 2", "upper body", "Chest", "chest", "Spine2")
NECK = motion.NECK


def _drive(id_, path, index, expression):
    fc = id_.driver_add(path, index)
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = expression
    return fc


def _undo(arm):
    if P_SCALE in arm:
        arm.driver_remove("delta_scale")
        arm.delta_scale = tuple(arm[P_SCALE])
        del arm[P_SCALE]
    bones = arm.get(P_BONES)
    if bones is not None:
        for name, scale in bones.to_dict().items():
            pb = arm.pose.bones.get(name)
            if pb is not None:
                pb.driver_remove("scale")
                pb.scale = tuple(scale)
        del arm[P_BONES]
    if P_GROW in arm:
        del arm[P_GROW]


def remove(mask):
    for arm in [ob for ob in bpy.data.objects if ob.type == "ARMATURE" and ob.get(P_GROW) == mask]:
        _undo(arm)


def sync(settings, mask, model, moment):
    """Grow the old (or only) `model` at frame `moment` as the panel says; nothing when it is 0."""
    remove(mask)
    arm = model.armature if model is not None else None
    if settings.body_grow <= 0.0 or arm is None or moment is None:
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    ease = "smoothstep(%.2f, %.2f, frame)" % (moment - BEFORE * fps, moment + AFTER * fps)
    taller = TALLER * settings.body_grow
    broader = BROADER * settings.body_grow
    arm[P_GROW] = mask
    arm[P_SCALE] = list(arm.delta_scale)
    for k in range(3):
        _drive(arm, "delta_scale", k, "%.5f * (1 + %.4f * %s)" % (arm.delta_scale[k], taller, ease))
    bones = {}
    chest = motion.find_bone(arm, CHEST)
    neck = motion.find_bone(arm, NECK)
    for pb, grow in ((chest, True), (neck, False)):
        if pb is None:
            continue
        bones[pb.name] = list(pb.scale)
        for k in (0, 2):  # across the bone (its length is Y)
            base = pb.scale[k]
            if grow:
                _drive(pb, "scale", k, "%.5f * (1 + %.4f * %s)" % (base, broader, ease))
            else:
                _drive(pb, "scale", k, "%.5f / (1 + %.4f * %s)" % (base, broader, ease))
    arm[P_BONES] = bones
