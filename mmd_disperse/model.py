"""Find the armature and render meshes of an MMD model (mmd_tools layout or plain objects)."""

import fnmatch
import re

import numpy as np
from mathutils import Vector

from .node_groups import ATTR_LOCK

# Helper empties created by mmd_tools; their children are physics, not render meshes.
_HELPER_EMPTIES = {"rigidbodies", "joints", "temporary"}
_PHYSICS_TYPES = {"RIGID_BODY", "JOINT", "TRACK_TARGET", "NON_COLLISION_CONSTRAINT"}
_DUP_SUFFIX = re.compile(r"\.\d{3}$")

# Where to start the reveal on an MMD skeleton (first match wins).
ORIGIN_BONES = (
    "上半身2", "上半身", "UpperBody2", "UpperBody", "upper body 2", "upper body",
    "Chest", "chest", "Spine2", "spine2", "Spine", "spine", "センター", "Center", "center",
)

DEFAULT_LOCK_PATTERNS = (
    "*face*;*顔*;*hair*;*髪*;*eye*;*目*;*瞳*;*白目*;*brow*;*眉*;*lash*;*まつ*;*睫*;"
    "*mouth*;*口*;*teeth*;*歯*;*tongue*;*舌*;*inner*"
)
DEFAULT_KEEP = "body;*skin*;*肌*;*体*;gen;-*"  # 1.19, peel.py: not torn (skin; this model pack's hidden variants)
DEFAULT_LOOSE = "*guard*;*armor*;*armour*;*pad*;*belt*;*buckle*;*pouch*;*earring*;*ガード*;*アーマー*;*ベルト*"  # 1.20


class Model:
    def __init__(self, root, armature, meshes):
        self.root = root
        self.armature = armature
        self.meshes = meshes

    def __bool__(self):
        return bool(self.meshes)


def _mmd_type(ob):
    return getattr(ob, "mmd_type", "NONE")


def find_root(ob):
    """Top of the hierarchy (the mmd_tools root empty for imported models)."""
    root = ob
    while root.parent is not None:
        if _mmd_type(root) == "ROOT":
            break
        root = root.parent
    return root


def _is_physics(ob):
    if _mmd_type(ob) in _PHYSICS_TYPES or getattr(ob, "rigid_body", None) is not None:
        return True
    p = ob.parent
    while p is not None:
        if p.type == "EMPTY" and p.name.split(".")[0] in _HELPER_EMPTIES:
            return True
        p = p.parent
    return False


def find_armature(ob):
    """The armature driving a model; cheap enough to call from draw()."""
    if ob is None:
        return None
    if ob.type == "ARMATURE":
        return ob
    root = find_root(ob)
    if root.type == "ARMATURE":
        return root
    for child in root.children:
        if child.type == "ARMATURE":
            return child
    if ob.type == "MESH":
        for mod in ob.modifiers:
            if mod.type == "ARMATURE" and mod.object:
                return mod.object
    return None


# Objects of the add-on's own that may hang in a model's hierarchy (paint on the palms and the glint in the eyes ride on
# its bones): these properties mark them, they are not the model's meshes.
HELPERS = ("mmd_disperse_picture_front", "mmd_disperse_glint", "mmd_disperse_finish", "mmd_disperse_light",
           "mmd_disperse_mist", "mmd_disperse_replay", "mmd_disperse_shell", "mmd_disperse_spirit",
           "mmd_disperse_peel", "mmd_disperse_fumble", "mmd_disperse_talisman",
           "mmd_disperse_plumage", "mmd_disperse_after", "mmd_disperse_crown")  # (twins of ours that render)


def resolve(ob):
    """Model for any object of a character: root empty, armature or one of its meshes."""
    if ob is None:
        return Model(None, None, [])
    root = find_root(ob)
    meshes = []
    for child in [root] + list(root.children_recursive):
        if (child.type == "MESH" and not _is_physics(child) and not child.hide_render and child.data.polygons
                and not any(key in child for key in HELPERS)):
            meshes.append(child)
    return Model(root, find_armature(ob), meshes)


def rest_points_world(ob):
    """Undeformed vertex positions (what the 'rest_position' attribute holds) in world space."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3]


def rest_bounds(meshes):
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for ob in meshes:
        pts = rest_points_world(ob)
        if len(pts):
            lo = np.minimum(lo, pts.min(axis=0))
            hi = np.maximum(hi, pts.max(axis=0))
    return Vector(lo), Vector(hi)


def max_distance(meshes, origin):
    o = np.array(origin, dtype=np.float64)
    far = 0.0
    for ob in meshes:
        pts = rest_points_world(ob)
        if len(pts):
            far = max(far, float(np.sqrt(((pts - o) ** 2).sum(axis=1)).max()))
    return far


def auto_origin_bone(armature):
    if armature is None:
        return ""
    bones = armature.data.bones
    for name in ORIGIN_BONES:
        if name in bones:
            return name
    roots = [b for b in bones if b.parent is None]
    return roots[0].name if roots else ""


_LEFT_OUT = _PHYSICS_TYPES | {"RIGID_GRP_OBJ", "JOINT_GRP_OBJ", "TEMPORARY_GRP_OBJ", "SPRING_CONSTRAINT",
                              "SPRING_GOAL"}  # (copy_model: mmd_tools' physics and the empties holding it)


def _left_out(ob, root):
    """(copy_model) A rigid body, joint or other physics of mmd_tools, a helper of ours, or something under one."""
    while ob is not None and ob is not root:
        if (ob.rigid_body is not None or ob.rigid_body_constraint is not None or _mmd_type(ob) in _LEFT_OUT
                or (ob.type == "EMPTY" and ob.name.split(".")[0] in _HELPER_EMPTIES)
                or any(key in ob for key in HELPERS)):
            return True
        ob = ob.parent
    return False


def copy_model(root):
    """A second copy of the model under `root` (1.31: a new outfit that is the same model, for when she turns into
    the symbiote and is herself again under it). The root and everything under it, with mesh and armature data of
    their own and materials of their own (what the effect does to one outfit's materials stays off the other), parents,
    modifiers and constraints pointing at the copies, linked where the originals are; but not the rigid bodies and
    joints, built or not: the copy is moved by the old model's armature (Follow the Old Armature), whose physics is
    the one simulated. Returns the new root."""
    copies = {}
    for ob in [root] + list(root.children_recursive):
        if _left_out(ob, root):
            continue
        dup = ob.copy()
        if ob.data is not None:
            dup.data = ob.data.copy()
        copies[ob] = dup
        for collection in ob.users_collection:
            collection.objects.link(dup)
    materials = {}
    for ob, dup in copies.items():
        if ob.parent in copies:
            dup.parent = copies[ob.parent]
        for mod in dup.modifiers:
            if getattr(mod, "object", None) in copies:
                mod.object = copies[mod.object]
        for con in dup.constraints:
            if getattr(con, "target", None) in copies:
                con.target = copies[con.target]
        if dup.type == "ARMATURE":
            for pb in dup.pose.bones:
                for con in pb.constraints:
                    if getattr(con, "target", None) in copies:
                        con.target = copies[con.target]
        if dup.type == "MESH":
            for slot in dup.material_slots:
                if slot.material is not None:
                    if slot.material not in materials:
                        materials[slot.material] = slot.material.copy()
                    slot.material = materials[slot.material]
    new_root = copies[root]
    mmd_root = getattr(new_root, "mmd_root", None)
    if mmd_root is not None and getattr(mmd_root, "is_built", False):
        try:
            mmd_root.is_built = False  # (its rigid bodies stayed behind)
        except (AttributeError, TypeError):
            pass
    return new_root


def material_key(mat):
    """Lower-case material name without Blender's .001 duplicate suffix, for pattern matching."""
    return _DUP_SUFFIX.sub("", mat.name).lower() if mat else ""


def split_patterns(text):
    return [p.strip().lower() for p in re.split(r"[;,，；\n]", text or "") if p.strip()]


def write_lock_attribute(ob, patterns):
    """Face attribute marking parts (by material name) that stay on the old model."""
    me = ob.data
    old = me.attributes.get(ATTR_LOCK)
    if old is not None:
        me.attributes.remove(old)
    slots = [material_key(s.material) for s in ob.material_slots]
    locked = np.array([any(fnmatch.fnmatchcase(n, p) for p in patterns) for n in slots] or [False], dtype=bool)
    idx = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", idx)
    values = locked[np.clip(idx, 0, len(locked) - 1)]
    attr = me.attributes.new(ATTR_LOCK, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", values)
    return int(values.sum())


def free_area(ob):
    """World-space area of the faces that are not locked to the old model."""
    me = ob.data
    area = np.empty(len(me.polygons), dtype=np.float32)
    me.polygons.foreach_get("area", area)
    attr = me.attributes.get(ATTR_LOCK)
    if attr is not None and attr.domain == "FACE":
        lock = np.zeros(len(me.polygons), dtype=bool)
        attr.data.foreach_get("value", lock)
        area = area[~lock]
    s = ob.matrix_world.to_scale()
    return float(area.sum()) * abs(s.x * s.y * s.z) ** (2.0 / 3.0)


def material_areas(ob, patterns):
    """(material, world area of its faces) of each of the mesh's materials not matching the lock `patterns`."""
    me = ob.data
    area = np.empty(len(me.polygons), dtype=np.float32)
    me.polygons.foreach_get("area", area)
    idx = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", idx)
    s = ob.matrix_world.to_scale()
    scale = abs(s.x * s.y * s.z) ** (2.0 / 3.0)
    out = []
    for k, slot in enumerate(ob.material_slots):
        mat = slot.material
        if mat is None or any(fnmatch.fnmatchcase(material_key(mat), p) for p in patterns):
            continue
        total = float(area[idx == k].sum()) * scale
        if total > 0.0:
            out.append((mat, total))
    return out


def remove_lock_attribute(ob):
    attr = ob.data.attributes.get(ATTR_LOCK)
    if attr is not None:
        ob.data.attributes.remove(attr)
