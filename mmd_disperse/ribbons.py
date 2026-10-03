"""Light ribbons that spiral around the arms and legs while they transform (magical-girl style).

One curve object per limb bone, holding a double helix around the bone in the rest pose. It is parented to
the bone, so it follows the dance, and a small Geometry Nodes modifier (node_groups.build_ribbon_group) draws
it along the limb as the transformation passes and lets it fade afterwards. The helix starts at the end of
the limb the wave reaches first.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials
from .model import rest_points_world
from .node_groups import ATTR_ARRIVAL, RIBBON_GROUP, ensure_ribbon_group, input_identifiers

NAME = "MMD Disperse Ribbon"
P_RIBBON = "mmd_disperse_ribbon"  # on ribbon objects: the mask of their effect
P_SPAN = "mmd_disperse_span"  # on ribbon objects: arrival distance at the start and the end of the helix
P_TURNS = "mmd_disperse_turns"

# (bone names, default radius around the bone as a share of the model height)
SEGMENTS = (
    (("腕.L", "左腕", "upper_arm.L", "UpperArm_L", "LeftArm"), 0.03),
    (("ひじ.L", "左ひじ", "forearm.L", "LowerArm_L", "LeftForeArm"), 0.025),
    (("腕.R", "右腕", "upper_arm.R", "UpperArm_R", "RightArm"), 0.03),
    (("ひじ.R", "右ひじ", "forearm.R", "LowerArm_R", "RightForeArm"), 0.025),
    (("足.L", "左足", "thigh.L", "UpperLeg_L", "LeftUpLeg"), 0.045),
    (("ひざ.L", "左ひざ", "shin.L", "LowerLeg_L", "LeftLeg"), 0.035),
    (("足.R", "右足", "thigh.R", "UpperLeg_R", "RightUpLeg"), 0.045),
    (("ひざ.R", "右ひざ", "shin.R", "LowerLeg_R", "RightLeg"), 0.035),
)
STRANDS = 2
POINTS = 72


def ribbon_objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_RIBBON) == mask]


def _limb_radius(points, a, b, default):
    """How far the ribbon floats from the bone: from the surface points around the middle of the limb."""
    axis = b - a
    length = float(np.linalg.norm(axis))
    if length < 1e-6:
        return default
    u = axis / length
    rel = points - a
    along = rel @ u
    radial = np.linalg.norm(rel - np.outer(along, u), axis=1)
    near = (along > 0.25 * length) & (along < 0.75 * length) & (radial < 2.5 * default)
    if near.sum() < 20:
        return default
    return float(np.clip(np.percentile(radial[near], 60) * 1.35, 0.6 * default, 2.0 * default))


def _arrival_at(point, samples, radius):
    """Median arrival distance of the surface around `point` (samples: list of (points, arrival))."""
    best = []
    for pts, arrival in samples:
        near = np.linalg.norm(pts - point, axis=1) < radius
        if near.any():
            best.append(arrival[near])
    if best:
        return float(np.median(np.concatenate(best)))
    pts = np.concatenate([p for p, _ in samples])
    arrival = np.concatenate([v for _, v in samples])
    return float(arrival[np.argmin(np.linalg.norm(pts - point, axis=1))])


def _helix(a, b, radius, turns):
    """Points of `STRANDS` helices around the segment a -> b."""
    axis = b - a
    u = axis / np.linalg.norm(axis)
    side = np.cross(u, (0.0, 0.0, 1.0))
    if np.linalg.norm(side) < 1e-3:  # vertical limb
        side = np.cross(u, (1.0, 0.0, 0.0))
    e1 = side / np.linalg.norm(side)
    e2 = np.cross(u, e1)
    t = np.linspace(0.0, 1.0, POINTS)
    strands = []
    for k in range(STRANDS):
        angle = 2.0 * math.pi * (turns * t + k / STRANDS)
        r = radius * (1.0 + 0.12 * np.sin(math.pi * t))
        pts = a + np.outer(t, axis) + np.outer(r * np.cos(angle), e1) + np.outer(r * np.sin(angle), e2)
        strands.append(pts)
    return strands


def _surface_samples(meshes, mask):
    """(rest points, arrival distance) per mesh, both in world units."""
    samples = []
    centre = np.array(mask.matrix_world.translation)
    for ob in meshes:
        pts = rest_points_world(ob)
        attr = ob.data.attributes.get(ATTR_ARRIVAL)
        if attr is not None:
            arrival = np.zeros(len(attr.data), dtype=np.float32)
            attr.data.foreach_get("value", arrival)
            scale = ob.matrix_world.to_scale()
            arrival = arrival.astype(np.float64) * (abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3.0
        else:  # sphere: straight distance from the mask centre
            arrival = np.linalg.norm(pts - centre, axis=1)
        samples.append((pts, arrival))
    return samples


def create(settings, mask, meshes, armature, height, collection):
    """Ribbon objects for every limb bone of `armature` found in SEGMENTS."""
    if armature is None or not meshes:
        return []
    group = ensure_ribbon_group()
    material = materials.ensure_ribbon_material()
    samples = _surface_samples(meshes, mask)
    every = np.concatenate([p for p, _ in samples])
    made = []
    for names, ratio in SEGMENTS:
        bone = next((armature.data.bones[n] for n in names if n in armature.data.bones), None)
        if bone is None or bone.length < 0.02 * height:
            continue
        head = np.array(armature.matrix_world @ bone.head_local)
        tail = np.array(armature.matrix_world @ bone.tail_local)
        radius = _limb_radius(every, head, tail, ratio * height)
        start = _arrival_at(head, samples, 1.5 * radius)
        end = _arrival_at(tail, samples, 1.5 * radius)
        if end < start:  # grow from the end the wave reaches first
            head, tail, start, end = tail, head, end, start
        curve = bpy.data.curves.new("%s %s" % (NAME, bone.name), "CURVE")
        curve.dimensions = "3D"
        for pts in _helix(head, tail, radius, settings.ribbon_turns):
            spline = curve.splines.new("POLY")
            spline.points.add(len(pts) - 1)
            spline.points.foreach_set("co", np.hstack([pts, np.ones((len(pts), 1))]).ravel().tolist())
        ob = bpy.data.objects.new(curve.name, curve)
        collection.objects.link(ob)
        # Follow the bone: the curve is in world rest coordinates, so undo the bone's rest transform.
        ob.parent = armature
        ob.parent_type = "BONE"
        ob.parent_bone = bone.name
        rest_tail = armature.matrix_world @ bone.matrix_local @ Matrix.Translation((0.0, bone.length, 0.0))
        ob.matrix_parent_inverse = rest_tail.inverted()
        ob.matrix_basis = Matrix.Identity(4)
        ob[P_RIBBON] = mask
        ob[P_SPAN] = [start, end]
        ob[P_TURNS] = settings.ribbon_turns
        mod = ob.modifiers.new(NAME, "NODES")
        mod.node_group = group
        ob.data.materials.append(material)
        made.append(ob)
    return made


def sync(settings, mask):
    """Push widths / timing to the ribbon modifiers and the colour to their material."""
    materials.update_ribbon_material(settings)
    for ob in ribbon_objects(mask):
        start, end = ob.get(P_SPAN, (0.0, 1.0))
        values = {
            "Mask": mask,
            "Start": start,
            "End": end,
            "Lead": settings.edge_width,
            "Linger": settings.ribbon_linger,
            "Width": settings.ribbon_width,
            "Material": bpy.data.materials.get(materials.RIBBON_MATERIAL),
        }
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group and mod.node_group.name == RIBBON_GROUP:
                ids = input_identifiers(mod.node_group)
                for name, value in values.items():
                    if ids.get(name) is not None and value is not None:
                        mod[ids[name]] = value
        ob.update_tag()


def remove(mask):
    for ob in ribbon_objects(mask):
        curve = ob.data
        bpy.data.objects.remove(ob)
        if curve is not None and curve.users == 0:
            bpy.data.curves.remove(curve)
    mat = bpy.data.materials.get(materials.RIBBON_MATERIAL)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)
