"""Arrival field: how far the transformation front travels before it reaches each vertex.

The node trees compare this distance with the radius of the mask empty, so every path is driven by the
same keyframed mask. SPHERE is measured live by the node tree (distance to the mask). The other paths are
computed once at build time on the rest pose and stored in the 'disperse_arrival' point attribute:

* SURFACE - shortest paths through a voxelised copy of both outfits, so the wave flows over the body
  (around the torso, down the arms) instead of jumping through the air. Voxels instead of mesh edges
  because MMD meshes are thousands of disconnected pieces: PMX splits the vertices at every UV seam.
* UP / DOWN - a flat scan from the feet up, or from the head down.
"""

import itertools
import math

import numpy as np

from .model import rest_points_world
from .node_groups import ATTR_ARRIVAL

PATHS = ("SPHERE", "SURFACE", "UP", "DOWN")
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


def sweep_distances(point_sets, upward):
    """Height above the lowest point (or below the highest one), for each point set."""
    lo = min(float(p[:, 2].min()) for p in point_sets)
    hi = max(float(p[:, 2].max()) for p in point_sets)
    return [p[:, 2] - lo if upward else hi - p[:, 2] for p in point_sets]


def compute(meshes, path, seeds, height):
    """Arrival distance of every vertex (rest pose, world units): one array per mesh."""
    points = [rest_points_world(ob) for ob in meshes]
    if path in ("UP", "DOWN"):
        return sweep_distances(points, path == "UP")
    return surface_distances(points, [_triangles(ob) for ob in meshes], seeds, height)


def write(ob, values):
    remove(ob)
    attr = ob.data.attributes.new(ATTR_ARRIVAL, "FLOAT", "POINT")
    attr.data.foreach_set("value", np.ascontiguousarray(values, dtype=np.float32))


def remove(ob):
    attr = ob.data.attributes.get(ATTR_ARRIVAL)
    if attr is not None:
        ob.data.attributes.remove(attr)
