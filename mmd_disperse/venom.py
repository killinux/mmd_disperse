"""Symbiote (Venom): tendrils of black goo crawl ahead of the edge, sticky strands bridge gaps in the outfit.

Films build the symbiote as an animated blob that grows tentacles, with layers of effects on top; Blender tutorials
grow curves along shortest paths over the mesh. Neither fits an MMD model: PMX splits a mesh into thousands of
pieces at the UV seams, so a path over the mesh stops at every seam, and curves drawn once leave the body as soon
as it dances.

So the tendrils are traced once on the rest pose, step by step the way the edge travels (along the arrival field),
each step dropped onto the outermost surface below it by a ray, whatever piece that surface belongs to. Every point
is bound to the triangle it lies on (three vertex indices and barycentric weights). The node tree
(node_groups.build_venom_group) rebuilds the points every frame from the deformed vertices, so the tendrils stick to
the dancing body. Strands join two facing surfaces close to each other (armpits, between the legs, skirt and legs),
each end bound the same way.

Where a branch splits off a tendril, a web of goo fills the fork (Venom: The Last Dance's webbing between tendrils): a
small grid of faces between the two, its free edge curved in, every vertex bound to the surface the same way and
timed like the tendril. Strands are also looked for in poses the body takes while it transforms (sampled frames of
its animation): arms down against the body, legs together. There they are bound where the two surfaces face each
other, so they stretch when the body opens up again.

The result is a hidden mesh, the skeleton: one chain of vertices per tendril, branch or strand and a grid of faces
per web, with the bindings and the timing as point attributes. It holds for the settings it was traced with (its
signature); effect.sync() traces it again when they change.
"""

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import particles
from .node_groups import ATTR_ARRIVAL, ATTR_LOCK, VENOM_ENDS

SKELETON = "MMD Disperse Venom"
P_SKELETON = "mmd_disperse_venom"  # on an outfit mesh: its skeleton
P_SIGNATURE = "mmd_disperse_venom_signature"  # on the skeleton: the settings it was traced with
P_VERTICES = "mmd_disperse_venom_vertices"  # ... and the vertex count of the mesh it is bound to

# Point attributes of the skeleton (besides the bindings of end A, a tendril point or the first end of a strand, and
# end B, the other end of a strand: VENOM_ENDS, three vertex indices and their weights each).
ATTR_T = "mmdd_t"  # strands: 0 at end A .. 1 at end B
ATTR_KIND = "mmdd_kind"  # 0 tendril, 1 strand, 2 web
ATTR_S = "mmdd_s"  # tendrils, webs: length along the tendril from its root (object units)
ATTR_LENGTH = "mmdd_len"  # tendrils, webs: s at the end of the branch; strands: rest length
ATTR_ROOT = "mmdd_root"  # tendrils, webs: skeleton index of the root, whose age times the whole tendril
ATTR_RND = "mmdd_rnd"  # random number per tendril / strand

STEPS = 24  # trace steps per tendril length
STRAND_POINTS = 8
COVER = 0.012  # a surface with another one this close above it (fraction of the model height) is hidden: no seeds
BRANCHES = (0.7, 0.3)  # chance of a first and a second branch
WEB_ROWS, WEB_COLUMNS = 6, 4  # faces of a web along the fork and across it
WEB_REACH = 0.5  # how far up the fork a web reaches (share of the shorter side)
WEB_CURVE = 0.6  # how far its free edge curves in, in the middle (share of the reach)
POSES = 4  # frames of the animation the strands are also looked for in


def skeleton(ob):
    sk = ob.get(P_SKELETON)
    return sk if isinstance(sk, bpy.types.Object) else None


def signature(settings, s):
    """What the skeleton of a mesh with scale `s` depends on (object units; the frames the strands are looked for in
    come from the transformation's frame range)."""
    return (float(settings.venom_tendrils), float(settings.venom_strands), settings.venom_length / s,
            float(settings.venom_webs), float(settings.frame_start), float(settings.frame_end))


def _encode(values):
    return ";".join(repr(float(v)) for v in values)


def matches(ob, wanted):
    sk = skeleton(ob)
    if sk is None or sk.get(P_VERTICES) != len(ob.data.vertices):
        return False
    have = tuple(float(v) for v in sk.get(P_SIGNATURE, "").split(";") if v)
    return len(have) == len(wanted) and all(abs(a - b) <= 1e-4 * max(abs(a), abs(b), 1e-3)
                                            for a, b in zip(have, wanted))


def remove(ob):
    sk = skeleton(ob)
    if sk is not None:
        me = sk.data
        bpy.data.objects.remove(sk)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    if P_SKELETON in ob:
        del ob[P_SKELETON]


def field_values(ob, sphere_center, arrival=True):
    """How far the edge travels to reach each vertex (object units, rest pose): the stored arrival distance (with
    `arrival`, when the mesh has one), or else the distance to `sphere_center` (world)."""
    me = ob.data
    attr = me.attributes.get(ATTR_ARRIVAL)
    if attr is not None and arrival:
        values = np.empty(len(me.vertices), dtype=np.float32)
        attr.data.foreach_get("value", values)
        return values.astype(np.float64)
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    center = np.array(ob.matrix_world.inverted() @ Vector(sphere_center), dtype=np.float64)
    return np.linalg.norm(co.reshape(-1, 3).astype(np.float64) - center, axis=1)


def _unit(v):
    length = np.linalg.norm(v)
    return v / length if length > 1e-12 else v


def _turn(v, axis, angle):
    """`v` rotated by `angle` about the unit `axis` (Rodrigues)."""
    c, s = math.cos(angle), math.sin(angle)
    return v * c + np.cross(axis, v) * s + axis * np.dot(axis, v) * (1.0 - c)


class _Surface:
    """Rest-pose triangles of a mesh (or posed: vertex positions `co`) with a BVH, the arrival field's gradient per
    triangle and which ones may carry goo (not locked, not degenerate)."""

    def __init__(self, ob, values, co=None):
        me = ob.data
        if co is None:
            co = np.empty(len(me.vertices) * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
        self.co = np.asarray(co).reshape(-1, 3).astype(np.float64)
        if hasattr(me, "calc_loop_triangles"):
            me.calc_loop_triangles()
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
        self.tris = tris.reshape(-1, 3)
        poly = np.empty(len(me.loop_triangles), dtype=np.int64)
        me.loop_triangles.foreach_get("polygon_index", poly)
        a, b, c = (self.co[self.tris[:, i]] for i in range(3))
        cross = np.cross(b - a, c - a)
        twice = np.linalg.norm(cross, axis=1)
        self.area = twice * 0.5
        self.normals = cross / np.maximum(twice, 1e-20)[:, None]
        free = twice > 1e-12
        lock = me.attributes.get(ATTR_LOCK)
        if lock is not None and lock.domain == "FACE":
            locked = np.zeros(len(me.polygons), dtype=bool)
            lock.data.foreach_get("value", locked)
            free &= ~locked[poly]
        self.free = free
        # Gradient of the linear interpolation of the field over each triangle (in its plane).
        self.values = values
        f = values[self.tris]
        sq = np.maximum((cross * cross).sum(axis=1), 1e-30)[:, None]
        self.grad = ((f[:, 1] - f[:, 0])[:, None] * np.cross(c - a, cross)
                     + (f[:, 2] - f[:, 0])[:, None] * np.cross(cross, b - a)) / sq
        self.bvh = BVHTree.FromPolygons(self.co.tolist(), self.tris.tolist(), all_triangles=True)

    def weights(self, k, p):
        """Barycentric weights of `p` in triangle `k`."""
        a, b, c = self.co[self.tris[k]]
        v0, v1, v2 = b - a, c - a, p - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-30:
            return np.array([1.0, 0.0, 0.0])
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        bary = np.clip(np.array([1.0 - v - w, v, w]), 0.0, 1.0)
        return bary / max(bary.sum(), 1e-12)

    def field(self, k, p):
        return float(self.weights(k, p) @ self.values[self.tris[k]])

    def hidden(self, p, n, cover):
        """True when another surface lies within `cover` above `p` (an inner layer under the clothes)."""
        return self.bvh.ray_cast(Vector(p + n * cover * 0.05), Vector(n), cover)[0] is not None

    def samples(self, count, rng):
        """`count` random points on the free triangles, by area: (triangle, point) pairs."""
        weight = np.where(self.free, self.area, 0.0)
        total = weight.sum()
        if total <= 0.0 or count <= 0:
            return []
        picks = rng.choice(len(weight), size=count, p=weight / total)
        r1, r2 = np.sqrt(rng.random(count)), rng.random(count)
        a, b, c = (self.co[self.tris[picks, i]] for i in range(3))
        points = a * (1.0 - r1)[:, None] + b * (r1 * (1.0 - r2))[:, None] + c * (r1 * r2)[:, None]
        return list(zip(picks.tolist(), points))

    def drop(self, q, n, step):
        """The outermost surface point below `q` (a ray down along -n), or the nearest one: (point, triangle)."""
        loc, _nor, k, _d = self.bvh.ray_cast(Vector(q + n * 2.0 * step), Vector(-n), 4.0 * step)
        if loc is None:
            loc, _nor, k, _d = self.bvh.find_nearest(Vector(q), 3.0 * step)
        if loc is None:
            return None, None
        return np.array(loc), k


def _spaced(candidates, spacing):
    """Drop candidates closer than `spacing` to one kept before (grid hash)."""
    grid = {}
    kept = []
    for item in candidates:
        p = item[1]
        key = tuple(np.floor(p / spacing).astype(int))
        near = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if np.linalg.norm(other - p) < spacing:
                            near = True
                            break
                    if near:
                        break
                if near:
                    break
            if near:
                break
        if not near:
            grid.setdefault(key, []).append(p)
            kept.append(item)
    return kept


class _Chain:
    """One tendril branch, strand or web, in skeleton point attributes."""

    def __init__(self, kind, rnd):
        self.kind = kind
        self.rnd = rnd
        self.points = []  # rest positions
        self.a = []  # (triangle, weights) per point
        self.b = []
        self.t = []
        self.s = []
        self.length = 0.0
        self.root = None  # chain whose first point is the root (tendrils, webs), filled in later
        self.faces = []  # webs: faces, indices into points


def _trace(surface, k, p, heading, length, step, rng, s0=0.0):
    """Points (point, triangle, s) of a path from `p` on triangle `k` along the field for `length`, starting towards
    `heading` (None: straight along the field). It stops early at locked parts, sharp folds and dead ends."""
    path = [(p, k, s0)]
    n = surface.normals[k]
    d = heading if heading is not None else surface.grad[k]
    d = _unit(d - n * (d @ n))
    if np.linalg.norm(d) < 0.5:
        return path
    f = surface.field(k, p)
    angle = 0.0
    s = s0
    while s - s0 < length:
        g = surface.grad[k] - n * (surface.grad[k] @ n)
        g = _unit(g) if np.linalg.norm(g) > 1e-9 else d
        angle = float(np.clip(angle + rng.normal(0.0, 0.3), -0.9, 0.9))
        d = _unit(0.6 * d + 0.4 * _turn(g, n, angle))
        d = _unit(d - n * (d @ n))
        q, kq = surface.drop(p + d * step, n, step)
        if q is None or not surface.free[kq]:
            break
        nq = surface.normals[kq]
        moved = float(np.linalg.norm(q - p))
        if nq @ n < 0.35 or moved < 0.3 * step or moved > 2.5 * step:
            break
        fq = surface.field(kq, q)
        if fq < f - 0.6 * step:  # running back against the edge
            break
        s += moved
        p, k, n, f = q, kq, nq, fq
        path.append((p, k, s))
    return path


def _web(surface, side_a, side_b, trunk, step):
    """Web in the fork between two paths from the same point (lists of (point, triangle, s)): WEB_ROWS x WEB_COLUMNS
    faces between them reaching WEB_REACH of the way up the shorter one, the free edge curved in, every vertex dropped
    onto the surface and bound there, timed by the trunk's root. None when it does not fit."""
    m = min(len(side_a), len(side_b)) - 1
    reach = WEB_REACH * m
    if reach < 1.5:
        return None
    sides = [(np.array([p for p, _k, _s in side]), np.array([s for _p, _k, s in side]), [k for _p, k, _s in side])
             for side in (side_a, side_b)]

    def at(values, index):
        i = min(int(index), len(values) - 2)
        f = index - i
        return values[i] * (1.0 - f) + values[i + 1] * f

    web = _Chain(2, trunk.rnd)
    web.root = trunk
    grid = {}
    for r in range(WEB_ROWS + 1):
        for c in range(WEB_COLUMNS + 1):
            t = c / WEB_COLUMNS
            k = reach * r / WEB_ROWS * (1.0 - WEB_CURVE * math.sin(math.pi * t))
            (pa, sa, ka), (pb, sb, kb) = sides
            x = at(pa, k) + (at(pb, k) - at(pa, k)) * t
            n = _unit(surface.normals[ka[int(round(k))]] + surface.normals[kb[int(round(k))]])
            q, kq = surface.drop(x, n, step)
            if q is None or not surface.free[kq]:
                return None
            w = surface.weights(kq, q)
            grid[r, c] = len(web.points)
            web.points.append(q)
            web.a.append((kq, w))
            web.b.append((kq, w))
            web.t.append(0.0)
            web.s.append(float(at(sa, k) * (1.0 - t) + at(sb, k) * t))
    web.faces = [(grid[r, c], grid[r, c + 1], grid[r + 1, c + 1], grid[r + 1, c])
                 for r in range(WEB_ROWS) for c in range(WEB_COLUMNS)]
    web.length = max(side_a[-1][2], side_b[-1][2])
    return web


def _tendrils(surface, count, length, height, rng, webs=True):
    chains = []
    step = length / STEPS
    total = float(np.where(surface.free, surface.area, 0.0).sum())
    if total <= 0.0 or count <= 0:
        return chains
    cover = COVER * height
    spacing = 0.5 * math.sqrt(total / count)
    candidates = [(k, p) for k, p in surface.samples(count * 6, rng) if not surface.hidden(p, surface.normals[k], cover)]
    for k, p in _spaced(candidates, spacing)[:count]:
        rnd = float(rng.random())
        own = length * (0.7 + 0.6 * rng.random())
        path = _trace(surface, k, p, None, own, step, rng)
        if len(path) < 4:
            continue
        trunk = _Chain(0, rnd)
        trunk.root = trunk
        _fill(surface, trunk, path)
        chains.append(trunk)
        # Branches split off the middle of the trunk at an angle, timed by the trunk's root.
        for chance in BRANCHES:
            if rng.random() >= chance:
                continue
            at = int(len(path) * (0.25 + 0.35 * rng.random()))
            bp, bk, bs = path[at]
            nb = surface.normals[bk]
            ahead = path[min(at + 1, len(path) - 1)][0] - bp
            side = _turn(_unit(ahead - nb * (ahead @ nb)), nb, (0.4 + 0.4 * rng.random()) * rng.choice((-1.0, 1.0)))
            branch_path = _trace(surface, bk, bp, side, (own - bs) * (0.4 + 0.3 * rng.random()), step, rng, bs)
            if len(branch_path) < 3:
                continue
            branch = _Chain(0, float(rng.random()))
            branch.root = trunk
            _fill(surface, branch, branch_path)
            chains.append(branch)
            web = _web(surface, path[at:], branch_path, trunk, step) if webs else None
            if web is not None:
                chains.append(web)
    return chains


def _fill(surface, chain, path):
    for p, k, s in path:
        w = surface.weights(k, p)
        chain.points.append(p)
        chain.a.append((k, w))
        chain.b.append((k, w))
        chain.t.append(0.0)
        chain.s.append(s)
    chain.length = path[-1][2]


def _strands(surfaces, count, height, rng):
    """Strands across gaps: a ray out from the surface (within 40 degrees of the normal) that hits a surface facing
    back, not too close, not too far. Looked for in every one of `surfaces` (the rest pose first, then poses the body
    takes: the same triangles moved), each end bound where it was found; the rest length is the gap there."""
    chains = []
    if count <= 0:
        return chains
    rest = surfaces[0]
    near, far = 0.01 * height, 0.12 * height
    pairs = []
    for surface in surfaces:
        for k, p in surface.samples(count * 40, rng):
            n = surface.normals[k]
            d = _unit(n + np.tan(math.radians(40.0)) * math.sqrt(rng.random()) * _unit(np.cross(n, rng.normal(size=3))))
            # (an inner layer under the clothes hits them from inside: they face the same way and are skipped)
            loc, _nor, kq, dist = surface.bvh.ray_cast(Vector(p + n * 1e-4 * height), Vector(d), far)
            if loc is None or dist < near or not surface.free[kq] or surface.normals[kq] @ d > -0.2:
                continue
            q = np.array(loc)
            wa, wb = surface.weights(k, p), surface.weights(kq, q)
            # where the ends are on the rest pose (the skeleton's own vertices)
            pa, qb = wa @ rest.co[rest.tris[k]], wb @ rest.co[rest.tris[kq]]
            pairs.append((k, (pa + qb) * 0.5, wa, kq, wb, pa, qb, float(dist)))
    order = rng.permutation(len(pairs))  # the poses mixed, so none of them gets all the room
    spacing = 0.5 * math.sqrt(float(np.where(rest.free, rest.area, 0.0).sum()) / max(count, 1))
    for k, _mid, wa, kq, wb, p, q, gap in _spaced([pairs[i] for i in order], spacing)[:count]:
        chain = _Chain(1, float(rng.random()))
        for t in np.linspace(0.0, 1.0, STRAND_POINTS):
            chain.points.append(p + (q - p) * t)
            chain.a.append((k, wa))
            chain.b.append((kq, wb))
            chain.t.append(float(t))
            chain.s.append(0.0)
        chain.length = gap
        chains.append(chain)
    return chains


def _mesh(name, surface, chains):
    """The skeleton mesh: one edge chain per tendril, branch or strand, a grid of faces per web, the bindings and
    timing as point attributes."""
    me = bpy.data.meshes.new(name)
    starts = []
    total = 0
    for chain in chains:
        starts.append(total)
        total += len(chain.points)
    if total == 0:
        return me
    first = {id(chain): start for chain, start in zip(chains, starts)}
    co = np.concatenate([np.array(c.points) for c in chains]).astype(np.float32)
    edges = [(s + i, s + i + 1) for c, s in zip(chains, starts) if c.kind != 2 for i in range(len(c.points) - 1)]
    faces = [tuple(s + i for i in face) for c, s in zip(chains, starts) for face in c.faces]
    me.from_pydata(co.tolist(), edges, faces)
    me.update()

    def put(name, data_type, values):
        attr = me.attributes.new(name, data_type, "POINT")
        attr.data.foreach_set("vector" if data_type == "FLOAT_VECTOR" else "value", np.ascontiguousarray(values).ravel())

    for end, binding in zip(VENOM_ENDS, ("a", "b")):
        bound = [pair for c in chains for pair in getattr(c, binding)]
        corners = surface.tris[np.array([k for k, _w in bound])]
        for i in range(3):
            put(end[i], "INT", corners[:, i].astype(np.int32))
        put(end[3], "FLOAT_VECTOR", np.array([w for _k, w in bound], dtype=np.float32))
    per_point = (lambda f, dtype: np.concatenate([np.full(len(c.points), f(c), dtype=dtype) for c in chains]))
    put(ATTR_T, "FLOAT", np.concatenate([np.array(c.t, dtype=np.float32) for c in chains]))
    put(ATTR_S, "FLOAT", np.concatenate([np.array(c.s, dtype=np.float32) for c in chains]))
    put(ATTR_KIND, "FLOAT", per_point(lambda c: c.kind, np.float32))
    put(ATTR_LENGTH, "FLOAT", per_point(lambda c: c.length, np.float32))
    put(ATTR_RND, "FLOAT", per_point(lambda c: c.rnd, np.float32))
    put(ATTR_ROOT, "INT", np.concatenate([np.full(len(c.points), first[id(c.root)] if c.root is not None
                                                  else start, dtype=np.int32) for c, start in zip(chains, starts)]))
    return me


def _motion(ob):
    """What moves `ob`: (object, action, its frame range) for it, its armature and their parents that are animated (an
    action, NLA strips or drivers); empty when nothing is."""
    from .model import find_armature

    seen = set()
    todo = [ob, find_armature(ob)]
    found = []
    while todo:
        item = todo.pop()
        if item is None or item.name in seen:
            continue
        seen.add(item.name)
        ad = item.animation_data
        if ad is not None and (ad.action is not None or len(ad.nla_tracks) or len(ad.drivers)):
            action = ad.action
            found.append((item.name, action.name if action else "", tuple(action.frame_range) if action else ()))
        todo.append(item.parent)
    return tuple(sorted(found))


_POSES = {}  # (mesh, vertex count, frames) -> its poses, while Blender runs (a rebuild samples them again)
_STRANDS = {}  # (that, strand count, model height) -> the strands found in them


def forget():
    """Drop the poses and strands kept from earlier traces (a rebuild: the motion may have changed)."""
    _POSES.clear()
    _STRANDS.clear()


def sample_poses(scene, ob, frames, quiet):
    """(poses, key): vertex positions (object space) of mesh `ob` as its armature poses it at each of `frames` when it is
    animated (kept under `key` for the next trace), or else at the current frame (key None); our node modifiers on the
    objects `quiet` and everything after the armature on `ob` are off meanwhile. Frames whose positions do not line
    up with the mesh are left out."""
    motion = _motion(ob)
    animated = bool(motion)
    key = (ob.name, len(ob.data.vertices), tuple(sorted(set(frames))), motion) if animated else None
    if key in _POSES:
        return _POSES[key], key
    saved = {}
    for other in set(quiet) | {ob}:
        for mod in other.modifiers:
            ours = mod.type == "NODES" and mod.node_group is not None and mod.node_group.name.startswith("MMDDisperse")
            if ours and mod.show_viewport:
                saved[mod] = True
                mod.show_viewport = False
    mods = list(ob.modifiers)
    last = max((i for i, m in enumerate(mods) if m.type == "ARMATURE"), default=-1)
    for mod in mods[last + 1:]:
        if mod.show_viewport:
            saved[mod] = True
            mod.show_viewport = False
    count = len(ob.data.vertices)
    current = scene.frame_current
    poses = []
    try:
        for frame in sorted(set(frames)) if animated else [None]:
            if frame is not None:
                scene.frame_set(frame)
            ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            me = ev.to_mesh()
            try:
                if len(me.vertices) == count:
                    co = np.empty(count * 3, dtype=np.float32)
                    me.vertices.foreach_get("co", co)
                    poses.append(co)
            finally:
                ev.to_mesh_clear()
    finally:
        for mod in saved:
            mod.show_viewport = True
        if scene.frame_current != current:
            scene.frame_set(current)
    if key is not None:
        _POSES[key] = poses
    return poses, key


def build(ob, values, settings, height, scene, poses=(), pose_key=None):
    """Trace the tendrils, webs and strands of mesh `ob` (field `values` per vertex, object units) and give it a new
    skeleton; strands are also looked for in `poses` (vertex positions, object space), and kept for the next trace when
    those have a `pose_key` (sample_poses). Returns (tendrils, strands)."""
    remove(ob)
    s = max(sum(abs(v) for v in ob.matrix_world.to_scale()) / 3.0, 1e-9)
    surface = _Surface(ob, values)
    rng = np.random.default_rng(len(ob.data.vertices) + 7919)
    tendrils = _tendrils(surface, settings.venom_tendrils, settings.venom_length / s, height / s, rng,
                         settings.venom_webs)
    key = None if pose_key is None else (pose_key, settings.venom_strands, round(height / s, 6))
    strands = _STRANDS.get(key)
    if strands is None:
        posed = [_Surface(ob, values, co) for co in poses
                 if float(np.abs(np.asarray(co).reshape(-1, 3) - surface.co).max()) > 1e-4 * height / s]
        # (their own random numbers: the strands do not change with the tendrils)
        strands = _strands([surface] + posed, settings.venom_strands, height / s,
                           np.random.default_rng(len(ob.data.vertices) + 104729))
        if key is not None:
            _STRANDS[key] = strands
    me = _mesh(SKELETON, surface, tendrils + strands)
    sk = bpy.data.objects.new(SKELETON, me)
    sk.hide_render = True
    particles.asset_collection(scene).objects.link(sk)
    sk[P_SIGNATURE] = _encode(signature(settings, s))
    sk[P_VERTICES] = len(ob.data.vertices)
    ob[P_SKELETON] = sk
    return sum(1 for c in tendrils if c.kind == 0 and c.root is c), len(strands)
