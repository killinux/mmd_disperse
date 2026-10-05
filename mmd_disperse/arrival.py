"""Arrival field: how far the transformation front travels before it reaches each vertex.

The node trees compare this distance with the radius of the mask empty, so every path is driven by the
same keyframed mask. SPHERE is measured live by the node tree (distance to the mask). The other paths are
computed once at build time on the rest pose and stored in the 'disperse_arrival' point attribute:

* SURFACE - shortest paths through a voxelised copy of both outfits, so the wave flows over the body
  (around the torso, down the arms) instead of jumping through the air. Voxels instead of mesh edges
  because MMD meshes are thousands of disconnected pieces: PMX splits the vertices at every UV seam.
* UP / DOWN and the sideways sweeps - a flat front crossing the body along one of the model's axes (from the feet up,
  from the head down, across from one side to the other, from the front to the back ...).
* SPIRAL - the front winds up around the body: something circling it once per pitch changes, at each height, the
  part it passes over (Cinderella's sparkles spiralling up).
"""

import itertools
import math

import numpy as np
from mathutils import Matrix, Vector

from .model import rest_points_world
from .node_groups import ATTR_ARRIVAL

# Flat sweeps: the direction the front moves in, in the model's own axes (MMD models face -Y, so from the front the
# camera sees their right hand on the left of the picture, at -X).
SWEEPS = {"UP": (0.0, 0.0, 1.0), "DOWN": (0.0, 0.0, -1.0), "LEFT_RIGHT": (1.0, 0.0, 0.0),
          "RIGHT_LEFT": (-1.0, 0.0, 0.0), "FRONT_BACK": (0.0, 1.0, 0.0), "BACK_FRONT": (0.0, -1.0, 0.0)}
PATHS = ("SPHERE", "SURFACE", "SPIRAL") + tuple(SWEEPS)
CELLS_PER_HEIGHT = 96

# Extra start points for "hands and feet" (mmd_tools names first, then the original PMX / other rigs).
LIMB_BONES = (
    ("手首.L", "左手首", "wrist.L", "Wrist_L", "LeftHand", "hand.L"),
    ("手首.R", "右手首", "wrist.R", "Wrist_R", "RightHand", "hand.R"),
    ("足首.L", "左足首", "ankle.L", "Ankle_L", "LeftFoot", "foot.L"),
    ("足首.R", "右足首", "ankle.R", "Ankle_R", "RightFoot", "foot.R"),
)

_MOVES = [m for m in itertools.product((-1, 0, 1), repeat=3) if m != (0, 0, 0)]


def limb_points(armature):
    """Rest-pose world positions of both wrists and ankles (bones that are missing are skipped)."""
    if armature is None:
        return []
    bones = armature.data.bones
    points = []
    for names in LIMB_BONES:
        bone = next((bones[n] for n in names if n in bones), None)
        if bone is not None:
            points.append(armature.matrix_world @ bone.head_local)
    return points


def _triangles(ob):
    me = ob.data
    if hasattr(me, "calc_loop_triangles"):
        me.calc_loop_triangles()
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    return tris.reshape(-1, 3)


def _surface_samples(points, tris, step):
    """Extra points on triangles longer than a voxel, so the voxelised surface has no holes."""
    a, b, c = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    longest = np.maximum(np.maximum(np.linalg.norm(a - b, axis=1), np.linalg.norm(b - c, axis=1)),
                         np.linalg.norm(c - a, axis=1))
    splits = np.clip(np.ceil(longest / step).astype(np.int64), 1, 64)
    samples = []
    for k in np.unique(splits[splits > 1]):
        sel = splits == k
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = (i + j) <= k
        u = (i[keep] / k)[None, :, None]
        v = (j[keep] / k)[None, :, None]
        samples.append((a[sel][:, None] * (1.0 - u - v) + b[sel][:, None] * u + c[sel][:, None] * v).reshape(-1, 3))
    return samples


def _slices(move):
    """(to, frm) so that grid[to] is the neighbour `move` away from grid[frm]."""
    to, frm = [], []
    for m in move:
        if m > 0:
            to.append(slice(m, None))
            frm.append(slice(None, -m))
        elif m < 0:
            to.append(slice(None, m))
            frm.append(slice(-m, None))
        else:
            to.append(slice(None))
            frm.append(slice(None))
    return tuple(to), tuple(frm)


def _relax(dist, blocked, step):
    """Shortest paths over the voxel grid (26 neighbours), in place. `blocked` is +inf where paths may not go."""
    moves = [_slices(m) + (np.float32(step * math.sqrt(sum(v * v for v in m))),) for m in _MOVES]
    sweeps = 0
    while True:
        sweeps += 1
        before = dist.copy()
        for to, frm, length in moves:
            reach = dist[frm] + blocked[to]
            reach += length
            np.minimum(dist[to], reach, out=dist[to])
        if np.array_equal(before, dist):
            return sweeps


def _sample(dist, origin, step, points):
    """Trilinear interpolation of the voxel distances at `points`, ignoring voxels that were never reached."""
    grid = (points - origin) / step - 0.5
    base = np.clip(np.floor(grid).astype(np.int64), 0, np.array(dist.shape) - 2)
    frac = np.clip(grid - base, 0.0, 1.0)
    total = np.zeros(len(points))
    weight = np.zeros(len(points))
    for corner in itertools.product((0, 1), repeat=3):
        w = np.ones(len(points))
        for axis, c in enumerate(corner):
            w *= frac[:, axis] if c else 1.0 - frac[:, axis]
        value = dist[base[:, 0] + corner[0], base[:, 1] + corner[1], base[:, 2] + corner[2]]
        ok = np.isfinite(value)
        total += np.where(ok, value, 0.0) * w
        weight += np.where(ok, w, 0.0)
    return total / np.maximum(weight, 1e-12)


def surface_distances(point_sets, tri_sets, seeds, height):
    """Distance along the body from the nearest seed, for each point set (world units)."""
    step = height / CELLS_PER_HEIGHT
    every = list(point_sets)
    for points, tris in zip(point_sets, tri_sets):
        every += _surface_samples(points, tris, step)
    every = np.concatenate(every)
    origin = every.min(axis=0) - 2.0 * step
    dims = tuple(int(n) for n in np.ceil((every.max(axis=0) + 2.0 * step - origin) / step) + 1)

    voxels = np.zeros(dims, dtype=bool)
    idx = np.floor((every - origin) / step).astype(np.int64)
    voxels[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    # Grow by one voxel: closes small gaps (clothes floating over the skin, accessories).
    grown = voxels.copy()
    for move in _MOVES:
        to, frm = _slices(move)
        grown[to] |= voxels[frm]
    voxels = grown

    # Seeds usually sit inside the body (bones): start from the surface nearest to each of them.
    dist = np.full(dims, np.inf, dtype=np.float32)
    cells = np.argwhere(voxels)
    centers = origin + (cells + 0.5) * step
    for seed in seeds:
        d = np.linalg.norm(centers - np.asarray(seed, dtype=np.float64), axis=1)
        near = d <= d.min() + 2.5 * step
        c = cells[near]
        dist[c[:, 0], c[:, 1], c[:, 2]] = np.minimum(dist[c[:, 0], c[:, 1], c[:, 2]],
                                                     (d[near] - d.min()).astype(np.float32))

    _relax(dist, np.where(voxels, 0.0, np.inf).astype(np.float32), step)
    lost = voxels & ~np.isfinite(dist)
    if lost.any():  # pieces that do not touch the body (floating accessories): reach them through the air
        air = dist.copy()
        _relax(air, np.zeros(dims, dtype=np.float32), step)
        dist[lost] = air[lost]
    return [_sample(dist, origin, step, points) for points in point_sets]


def axes(frame, path):
    """World (axis, u, v) of a sweep or the spiral: the direction the front moves in and two directions across it, a
    right-handed set (u, v, axis). For the upward sweep and the spiral u points at the model's front and v at its left,
    so angles around the body start in front of it and turn left (counter-clockwise from above). `frame` is the model's
    rotation (3x3)."""
    axis = (frame @ Vector(SWEEPS.get(path, (0.0, 0.0, 1.0)))).normalized()
    up = (frame @ Vector((0.0, 0.0, 1.0))).normalized()
    front = (frame @ Vector((0.0, -1.0, 0.0))).normalized()
    u = front if abs(axis.dot(up)) > 0.5 else up  # across a sideways sweep: up the body
    u = (u - axis * u.dot(axis)).normalized()
    return axis, u, axis.cross(u)


def sweep_distances(point_sets, axis):
    """Distance along `axis` from the point set's first point the front reaches, for each point set."""
    axis = np.asarray(axis, dtype=np.float64)
    proj = [p @ axis for p in point_sets]
    lo = min(float(v.min()) for v in proj)
    return [v - lo for v in proj]


def spiral_distances(point_sets, frame, pitch):
    """The front winding up around the body: at each height a point changes when the thing circling the body (once
    per `pitch`, starting in front) passes over it, on the turn that reaches that height:
    d = h + pitch * (1 - frac(h / pitch - angle / 2pi)), h the height above the lowest point."""
    axis, u, v = (np.asarray(a, dtype=np.float64) for a in axes(frame, "SPIRAL"))
    every = np.concatenate(point_sets)
    centre = (every.min(axis=0) + every.max(axis=0)) / 2.0
    low = float((every @ axis).min())
    pitch = max(float(pitch), 1e-6)
    out = []
    for p in point_sets:
        rel = p - centre
        h = p @ axis - low
        angle = np.mod(np.arctan2(rel @ v, rel @ u), 2.0 * math.pi)
        turn = h / pitch - angle / (2.0 * math.pi)
        out.append(h + pitch * (1.0 - (turn - np.floor(turn))))
    return out


def compute(meshes, path, seeds, height, frame=None, pitch=1.0):
    """Arrival distance of every vertex (rest pose, world units): one array per mesh. `frame` is the model's rotation
    (sweeps and the spiral follow the model's own axes)."""
    points = [rest_points_world(ob) for ob in meshes]
    frame = frame if frame is not None else Matrix.Identity(3)
    if path in SWEEPS:
        return sweep_distances(points, axes(frame, path)[0])
    if path == "SPIRAL":
        return spiral_distances(points, frame, pitch)
    return surface_distances(points, [_triangles(ob) for ob in meshes], seeds, height)


def front_layout(meshes, path, frame):
    """Where a sweep or the spiral starts, for the mask and the front's decoration (world units, rest pose): a dict with
    the start centre (on the plane the front starts from, through the middle of the body; the bottom centre for the
    spiral), the axes (axis, u, v), the length the front travels across the body ('span') and the body's half size
    across it along u and v ('half_u', 'half_v')."""
    every = np.concatenate([rest_points_world(ob) for ob in meshes])
    axis, u, v = axes(frame, path)
    lo, hi = every.min(axis=0), every.max(axis=0)
    centre = Vector(((lo + hi) / 2.0).tolist())
    a, uu, vv = (np.asarray(x, dtype=np.float64) for x in (axis, u, v))
    along = every @ a
    start = centre + axis * (float(along.min()) - float(np.dot(np.asarray(centre), a)))
    rel = every - np.asarray(centre)
    return {"start": start, "axis": axis, "u": u, "v": v, "span": float(along.max() - along.min()),
            "half_u": float(np.abs(rel @ uu).max()), "half_v": float(np.abs(rel @ vv).max())}


def write(ob, values):
    remove(ob)
    attr = ob.data.attributes.new(ATTR_ARRIVAL, "FLOAT", "POINT")
    attr.data.foreach_set("value", np.ascontiguousarray(values, dtype=np.float32))


def remove(ob):
    attr = ob.data.attributes.get(ATTR_ARRIVAL)
    if attr is not None:
        ob.data.attributes.remove(attr)
