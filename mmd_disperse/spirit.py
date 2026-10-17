"""The dancer's spirit self (1.12): the Dharma form (法相: a giant golden copy of the dancer in the new outfit stands
behind her and dances along, then shrinks and dives into her at the moment and the outfits swap: 《封神第二部》's 法天象地,
the guardian spirits of AI video templates) and three heads and six arms (三头六臂·千手开屏: golden copies of her arms
open out about her shoulders one pair after another like a peacock's tail, heads turn out to either side, and all
fold back after the swap: Ne Zha 2's flowing, half-there look rather than a solid blue skin).

Both outfits' Geometry Nodes draw it (node_groups._spirit): the new outfit what it shows, the old one its locked parts
(the head and hair the dancer keeps). Building writes how much each vertex belongs to each arm and to the head
(ATTR_LIMB) from the MMD vertex groups: every bone under the upper arm (腕), under the head (頭); a model whose bones
have other names is read by its skeleton (the long chains out to either side above the waist). Empties of ours follow
the floor under the hips, the shoulders, the neck and the hips, so the copies turn about the dancing joints.
"""

import bpy
import numpy as np
from mathutils import Vector

from .model import rest_bounds
from .node_groups import ATTR_LIMB

NAME = "MMD Disperse Spirit"
P_SPIRIT = "mmd_disperse_spirit"  # on our empties: the mask of their effect
P_ROLE = "mmd_disperse_spirit_role"  # ... ANCHOR, SHOULDER_L, SHOULDER_R, NECK, HIPS
MODES = {"GIANT": 1, "ARMS": 2}  # the entrances that call it up, as the node groups' Spirit input
ARMS = (("腕.L", "左腕", "arm.L", "Arm_L", "LeftArm", "J_Bip_L_UpperArm", "upper_arm.L", "UpperArm_L", "LeftUpperArm",
         "Left arm", "arm_L", "L_Arm", "Arm.L"),
        ("腕.R", "右腕", "arm.R", "Arm_R", "RightArm", "J_Bip_R_UpperArm", "upper_arm.R", "UpperArm_R",
         "RightUpperArm", "Right arm", "arm_R", "R_Arm", "Arm.R"))
HEADS = ("頭", "head", "Head", "J_Bip_C_Head")
HIPS = ("下半身", "lower body", "LowerBody", "Hips", "hips", "pelvis", "J_Bip_C_Hips", "センター", "center", "Center")
CENTRE = ("センター", "center", "Center", "下半身", "lower body", "Hips", "hips", "pelvis", "J_Bip_C_Hips")


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_SPIRIT) == mask]


def _descendants(bone):
    out = [bone]
    for child in bone.children:
        out += _descendants(child)
    return out


def limb_roots(armature):
    """The bones whose descendants make the left arm, the right arm and the head: {"L", "R", "HEAD": bone or None}.
    By name first; by the skeleton for the arms when the names are not known: of the bones well out to either side
    above the waist with long chains under them, the one nearest the middle (the shoulder or the upper arm)."""
    bones = armature.data.bones
    found = {"HEAD": next((bones[n] for n in HEADS if n in bones), None)}
    for side, names in zip(("L", "R"), ARMS):
        found[side] = next((bones[n] for n in names if n in bones), None)
    if found["L"] is None or found["R"] is None:
        heads = [b.head_local for b in bones]
        lo = min(h.z for h in heads)
        tall = max(max(h.z for h in heads) - lo, 1e-6)
        for side, sign in (("L", 1.0), ("R", -1.0)):
            if found[side] is not None:
                continue
            chains = [b for b in bones if b.parent is not None and sign * b.head_local.x > 0.06 * tall
                      and abs(b.parent.head_local.x) < abs(b.head_local.x) * 0.8
                      and b.head_local.z > lo + 0.6 * tall and len(_descendants(b)) > 8]
            found[side] = min(chains, key=lambda b: abs(b.head_local.x), default=None)
    return found


def write_limbs(ob, armature):
    """ATTR_LIMB on mesh `ob`: per vertex the share of its bone weights that belong to the left arm (x), the right arm
    (y) and the head (z). False when the armature has none of them."""
    roots = limb_roots(armature)
    sets = [{b.name for b in _descendants(roots[k])} if roots[k] is not None else set() for k in ("L", "R", "HEAD")]
    if not any(sets):
        return False
    bones = armature.data.bones
    groups = {vg.index: vg.name for vg in ob.vertex_groups if vg.name in bones}
    which = {index: [name in s for s in sets] for index, name in groups.items()}
    me = ob.data
    out = np.zeros((len(me.vertices), 3), dtype=np.float32)
    for v in me.vertices:
        total = 0.0
        share = [0.0, 0.0, 0.0]
        for g in v.groups:
            flags = which.get(g.group)
            if flags is None:
                continue
            total += g.weight
            for k in range(3):
                if flags[k]:
                    share[k] += g.weight
        if total > 0.0:
            out[v.index] = (share[0] / total, share[1] / total, share[2] / total)
    remove_limbs(ob)
    attr = me.attributes.new(ATTR_LIMB, "FLOAT_VECTOR", "POINT")
    attr.data.foreach_set("vector", out.ravel())
    return True


def remove_limbs(ob):
    if ob.type == "MESH":
        attr = ob.data.attributes.get(ATTR_LIMB)
        if attr is not None:
            ob.data.attributes.remove(attr)


def _empty(mask, role, collection):
    ob = next((o for o in objects(mask) if o.get(P_ROLE) == role), None)
    if ob is None:
        ob = bpy.data.objects.new("%s %s" % (NAME, role.replace("_", " ").title()), None)
        ob.empty_display_type = "PLAIN_AXES"
        ob.empty_display_size = 0.3
        ob.hide_render = True
        ob.hide_select = True
        collection.objects.link(ob)
        ob[P_SPIRIT] = mask
        ob[P_ROLE] = role
    return ob


def _follow(ob, armature, bone, level=False, floor=None):
    """`ob` follows the head of `bone` (its height kept at `floor` with `level`)."""
    for con in list(ob.constraints):
        ob.constraints.remove(con)
    if bone is None:
        ob.location = armature.matrix_world.translation
        return
    ob.location = armature.matrix_world @ bone.head_local
    if level and floor is not None:
        ob.location.z = floor
    con = ob.constraints.new("COPY_LOCATION")
    con.target = armature
    con.subtarget = bone.name
    if level:
        con.use_z = False


def sync(settings, mask, model, meshes):
    """The empties the spirit turns about (a dict of the node groups' object inputs), or None (and nothing of ours)
    when the entrance does not call it up. With the arms, `meshes` get ATTR_LIMB when they have none yet."""
    mode = MODES.get(settings.entrance, 0)
    arm = model.armature if model else None
    if not mode or arm is None:
        remove(mask)
        return None
    scene = settings.id_data
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    bones = arm.data.bones
    roots = limb_roots(arm)
    lo, _hi = rest_bounds(model.meshes)
    centre = next((bones[n] for n in CENTRE if n in bones), None)
    hips = next((bones[n] for n in HIPS if n in bones), None)
    neck = roots["HEAD"]
    made = {}
    for role, bone, level in (("ANCHOR", centre, True), ("SHOULDER_L", roots["L"], False),
                              ("SHOULDER_R", roots["R"], False), ("NECK", neck, False), ("HIPS", hips, False)):
        ob = _empty(mask, role, collection)
        _follow(ob, arm, bone, level, lo.z)
        made[role] = ob
    if mode == 2:
        for ob in meshes:
            if ob.type == "MESH" and ob.data.attributes.get(ATTR_LIMB) is None:
                write_limbs(ob, arm)
    return {"Spirit Anchor": made["ANCHOR"], "Shoulder L": made["SHOULDER_L"], "Shoulder R": made["SHOULDER_R"],
            "Neck Object": made["NECK"], "Hips Object": made["HIPS"]}


def back(scene, meshes):
    """The level direction from the scene camera through the dancer (away from the camera; +Y without a camera)."""
    lo, hi = rest_bounds(meshes)
    centre = (lo + hi) / 2.0
    camera = scene.camera
    if camera is None:
        return Vector((0.0, 1.0, 0.0))
    away = centre - camera.matrix_world.translation
    away.z = 0.0
    return away.normalized() if away.length > 1e-6 else Vector((0.0, 1.0, 0.0))


def remove(mask):
    for ob in objects(mask):
        bpy.data.objects.remove(ob)
