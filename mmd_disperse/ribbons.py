"""Light ribbons that spiral around the arms and legs while they transform (magical-girl style), and the silk threads
that wind round the body, arms and legs as the old outfit turns into a cocoon.

One curve object per limb bone, holding a double helix around the bone in the rest pose (the silk: four threads, two
winding each way, round the body's bones too). It is parented to the bone, so it follows the dance, and a small
Geometry Nodes modifier (node_groups.build_ribbon_group) draws it along the limb as the transformation passes and lets
it fade afterwards (the silk snaps when the old outfit goes). The helix starts at the end of the limb the wave reaches
first.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials
from .model import rest_points_world
from .node_groups import ATTR_ARRIVAL, ATTR_LOCK, RIBBON_GROUP, ensure_ribbon_group, input_identifiers

NAME = "MMD Disperse Ribbon"
THREAD_NAME = "MMD Disperse Thread"
P_RIBBON = "mmd_disperse_ribbon"  # on ribbon objects: the mask of their effect
P_SPAN = "mmd_disperse_span"  # on ribbon objects: arrival distance at the start and the end of the helix
P_TURNS = "mmd_disperse_turns"
P_KIND = "mmd_disperse_kind"  # LIGHT (light ribbons) or SILK (the cocoon's threads)
P_SWELL = "mmd_disperse_swell"  # on the silk threads: the silk's swell they were wound over
LIGHT, SILK = "LIGHT", "SILK"
THREAD_WIDTH = 0.0016  # width of the silk threads, fraction of the model height

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
# ... and the body, for the silk
BODY_SEGMENTS = (
    (("下半身", "LowerBody", "lower body", "hips", "Hips"), 0.08),
    (("上半身", "UpperBody", "upper body", "spine", "Spine"), 0.075),
    (("上半身2", "UpperBody2", "upper body 2", "chest", "Chest"), 0.075),
    (("首", "Neck", "neck"), 0.03),
)
STRANDS = 2
POINTS = 72


def ribbon_objects(mask, kind=None):
    """The ribbon objects of the effect of `mask` (only those of `kind`, LIGHT or SILK, when given)."""
    return [ob for ob in bpy.data.objects if ob.get(P_RIBBON) == mask
            and (kind is None or ob.get(P_KIND, LIGHT) == kind)]


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


def _frame(u):
    """Two directions across the unit vector `u`, (e1, e2): angles round a segment are measured from e1 towards e2."""
    side = np.cross(u, (0.0, 0.0, 1.0))
    if np.linalg.norm(side) < 1e-3:  # vertical limb
        side = np.cross(u, (1.0, 0.0, 0.0))
    e1 = side / np.linalg.norm(side)
    return e1, np.cross(u, e1)


STATIONS, SECTORS = 10, 12  # a body part's profile: stations along its bone, sectors round it


def _profile(points, a, b, fallback):
    """How far the surface `points` (one part of the body) reaches out from the segment a -> b, per station along it
    and sector round it: the outermost tenth of the points there (90th percentile of their distance from the axis),
    gaps filled in from the neighbours, `fallback` where nothing is near. A (STATIONS, SECTORS) array."""
    axis = b - a
    length = float(np.linalg.norm(axis))
    u = axis / length
    e1, e2 = _frame(u)
    rel = points - a
    along = rel @ u
    radial = rel - np.outer(along, u)
    r = np.linalg.norm(radial, axis=1)
    angle = np.mod(np.arctan2(radial @ e2, radial @ e1), 2.0 * math.pi)
    t = along / length
    keep = (t > -0.05) & (t < 1.05) & (r < 3.0 * fallback)
    cell = (np.clip((t[keep] * STATIONS).astype(np.int64), 0, STATIONS - 1) * SECTORS
            + (angle[keep] / (2.0 * math.pi) * SECTORS).astype(np.int64) % SECTORS)
    grid = np.full(STATIONS * SECTORS, np.nan)
    reach = r[keep]
    for c in np.unique(cell):
        grid[c] = np.percentile(reach[cell == c], 90)
    grid = grid.reshape(STATIONS, SECTORS)
    for _ in range(STATIONS + SECTORS):  # gaps: the mean of the neighbours (round the axis wraps)
        missing = np.isnan(grid)
        if not missing.any():
            break
        around = np.stack([np.roll(grid, 1, axis=1), np.roll(grid, -1, axis=1), np.vstack([grid[:1], grid[:-1]]),
                           np.vstack([grid[1:], grid[-1:]])])
        count = (~np.isnan(around)).sum(axis=0)
        near = np.where(count > 0, np.nansum(around, axis=0) / np.maximum(count, 1), np.nan)
        grid[missing] = near[missing]
    grid[np.isnan(grid)] = fallback
    return 0.5 * grid + 0.25 * (np.roll(grid, 1, axis=1) + np.roll(grid, -1, axis=1))  # softened round the axis


def _profile_at(grid, t, angle):
    """A profile (see _profile) at `t` along the segment (0 .. 1) and `angle` round it (radians): bilinear."""
    x = np.clip(t * STATIONS - 0.5, 0.0, STATIONS - 1.0)
    y = np.mod(angle / (2.0 * math.pi) * SECTORS - 0.5, SECTORS)
    i0 = np.floor(x).astype(np.int64)
    i1 = np.minimum(i0 + 1, STATIONS - 1)
    j0 = np.floor(y).astype(np.int64) % SECTORS
    j1 = (j0 + 1) % SECTORS
    fx, fy = x - i0, y - np.floor(y)
    return ((grid[i0, j0] * (1.0 - fx) + grid[i1, j0] * fx) * (1.0 - fy)
            + (grid[i0, j1] * (1.0 - fx) + grid[i1, j1] * fx) * fy)


def _helix(a, b, radius, turns, strands=STRANDS, crossing=False, profile=None):
    """Points of `strands` helices around the segment a -> b (with `crossing` every other one winds the other way),
    `radius` from the axis, or with a `profile` (see _profile) that far out from the body's surface."""
    axis = b - a
    e1, e2 = _frame(axis / np.linalg.norm(axis))
    count = POINTS * max(1, int(math.ceil(turns / 3.0)))  # (enough points for the turns)
    t = np.linspace(0.0, 1.0, count)
    out = []
    for k in range(strands):
        way = -1.0 if crossing and k % 2 else 1.0
        angle = 2.0 * math.pi * (way * turns * t + k / strands)
        if profile is None:
            r = radius * (1.0 + 0.12 * np.sin(math.pi * t))
        else:
            r = _profile_at(profile, t, angle) + radius
        pts = a + np.outer(t, axis) + np.outer(r * np.cos(angle), e1) + np.outer(r * np.sin(angle), e2)
        out.append(pts)
    return out


def _parts(points, segments):
    """Which of `segments` ((a, b) pairs) each of `points` is nearest to (by its distance from the segment)."""
    best = np.full(len(points), np.inf)
    owner = np.full(len(points), -1)
    for i, (a, b) in enumerate(segments):
        axis = b - a
        t = np.clip(((points - a) @ axis) / max(float(axis @ axis), 1e-12), 0.0, 1.0)
        d = np.linalg.norm(points - (a + np.outer(t, axis)), axis=1)
        closer = d < best
        best[closer] = d[closer]
        owner[closer] = i
    return owner


def _free_points(meshes):
    """World rest positions of the vertices of the faces that are not locked (the parts the silk covers)."""
    out = []
    for ob in meshes:
        pts = rest_points_world(ob)
        me = ob.data
        attr = me.attributes.get(ATTR_LOCK)
        if attr is None or attr.domain != "FACE":
            out.append(pts)
            continue
        lock = np.zeros(len(me.polygons), dtype=bool)
        attr.data.foreach_get("value", lock)
        totals = np.zeros(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_total", totals)
        corner_vertex = np.zeros(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", corner_vertex)
        free = np.zeros(len(pts), dtype=bool)
        free[corner_vertex[np.repeat(~lock, totals)]] = True
        out.append(pts[free])
    return np.concatenate(out) if out else np.zeros((0, 3))


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


def turns_of(settings, kind):
    return settings.thread_turns if kind == SILK else settings.ribbon_turns


def stale(ob, settings):
    """True when a ribbon object was made with other turns (or, a silk thread, over another swell)."""
    kind = ob.get(P_KIND, LIGHT)
    if abs(ob.get(P_TURNS, 0.0) - turns_of(settings, kind)) > 1e-6:
        return True
    return kind == SILK and abs(ob.get(P_SWELL, 0.0) - settings.silk_swell) > 1e-6


def create(settings, mask, meshes, armature, height, collection, kind=LIGHT):
    """Ribbon objects for every limb bone of `armature` found in SEGMENTS (the silk threads: also BODY_SEGMENTS, each
    wound tight round its own part of the body: the free surface nearest to its bone, swollen by the silk)."""
    if armature is None or not meshes:
        return []
    silk = kind == SILK
    group = ensure_ribbon_group()
    material = materials.ensure_silk_material() if silk else materials.ensure_ribbon_material()
    samples = _surface_samples(meshes, mask)
    every = np.concatenate([p for p, _ in samples])
    turns = turns_of(settings, kind)
    found = []
    for names, ratio in SEGMENTS + (BODY_SEGMENTS if silk else ()):
        bone = next((armature.data.bones[n] for n in names if n in armature.data.bones), None)
        if bone is not None and bone.length >= 0.02 * height:
            found.append((bone, ratio, np.array(armature.matrix_world @ bone.head_local),
                          np.array(armature.matrix_world @ bone.tail_local)))
    if silk:
        free = _free_points(meshes)
        owner = _parts(free, [(head, tail) for _bone, _ratio, head, tail in found])
        margin = max(settings.silk_swell, 0.0) + 0.003 * height
    made = []
    for i, (bone, ratio, head, tail) in enumerate(found):
        radius = _limb_radius(every, head, tail, ratio * height)
        start = _arrival_at(head, samples, 1.5 * radius)
        end = _arrival_at(tail, samples, 1.5 * radius)
        if end < start:  # grow from the end the wave reaches first
            head, tail, start, end = tail, head, end, start
        if silk:
            helices = _helix(head, tail, margin, turns, 4, True, _profile(free[owner == i], head, tail, radius / 1.35))
        else:
            helices = _helix(head, tail, radius, turns)
        curve = bpy.data.curves.new("%s %s" % (THREAD_NAME if silk else NAME, bone.name), "CURVE")
        curve.dimensions = "3D"
        for pts in helices:
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
        ob[P_TURNS] = turns
        ob[P_KIND] = kind
        if silk:
            ob[P_SWELL] = settings.silk_swell
        mod = ob.modifiers.new(NAME, "NODES")
        mod.node_group = group
        ob.data.materials.append(material)
        made.append(ob)
    return made


def sync(settings, mask, snap=None):
    """Push widths / timing to the ribbon modifiers and the colour to their material. The silk threads wind on with
    the silk ahead of the edge and snap at the mask radius `snap` (when the old outfit goes all at once), else soon
    after the edge has passed them."""
    materials.update_ribbon_material(settings)
    materials.update_silk_material(settings.surface_color if settings.old_surface == "SILK" else (0.93, 0.91, 0.86))
    height = max(settings.size_reference, 1e-3)
    for ob in ribbon_objects(mask):
        start, end = ob.get(P_SPAN, (0.0, 1.0))
        if ob.get(P_KIND, LIGHT) == SILK:
            values = {"Lead": settings.surface_width, "Fade From": end if snap is None else snap,
                      "Linger": settings.base_delete_offset, "Width": THREAD_WIDTH * height,
                      "Material": bpy.data.materials.get(materials.SILK_MATERIAL)}
        else:
            values = {"Lead": settings.edge_width, "Fade From": end, "Linger": settings.ribbon_linger,
                      "Width": settings.ribbon_width, "Material": bpy.data.materials.get(materials.RIBBON_MATERIAL)}
        values.update({"Mask": mask, "Start": start, "End": end})
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group and mod.node_group.name == RIBBON_GROUP:
                ids = input_identifiers(mod.node_group)
                for name, value in values.items():
                    if ids.get(name) is not None and value is not None:
                        mod[ids[name]] = value
        ob.update_tag()


def remove(mask, kind=None):
    for ob in ribbon_objects(mask, kind):
        curve = ob.data
        bpy.data.objects.remove(ob)
        if curve is not None and curve.users == 0:
            bpy.data.curves.remove(curve)
    for name in (materials.RIBBON_MATERIAL, materials.SILK_MATERIAL):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
