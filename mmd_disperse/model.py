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


def resolve(ob):
    """Model for any object of a character: root empty, armature or one of its meshes."""
    if ob is None:
        return Model(None, None, [])
    root = find_root(ob)
    meshes = []
    for child in [root] + list(root.children_recursive):
        if child.type == "MESH" and not _is_physics(child) and not child.hide_render and child.data.polygons:
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


def remove_lock_attribute(ob):
    attr = ob.data.attributes.get(ATTR_LOCK)
    if attr is not None:
        ob.data.attributes.remove(attr)
