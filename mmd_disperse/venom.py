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

The result is a hidden mesh, the skeleton: one chain of vertices per tendril, branch or strand, with the bindings and
the timing as point attributes. It holds for the settings it was traced with (its signature); effect.sync() traces it
again when they change.
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
ATTR_KIND = "mmdd_kind"  # 0 tendril, 1 strand
ATTR_S = "mmdd_s"  # tendrils: length along the tendril from its root (object units)
ATTR_LENGTH = "mmdd_len"  # tendrils: s at the end of the branch; strands: rest length
ATTR_ROOT = "mmdd_root"  # tendrils: skeleton index of the root, whose age times the whole tendril
ATTR_RND = "mmdd_rnd"  # random number per tendril / strand

STEPS = 24  # trace steps per tendril length
STRAND_POINTS = 8
COVER = 0.012  # a surface with another one this close above it (fraction of the model height) is hidden: no seeds
BRANCHES = (0.7, 0.3)  # chance of a first and a second branch


def skeleton(ob):
    sk = ob.get(P_SKELETON)
    return sk if isinstance(sk, bpy.types.Object) else None


def signature(settings, s):
    """What the skeleton of a mesh with scale `s` depends on (object units)."""
    return (float(settings.venom_tendrils), float(settings.venom_strands), settings.venom_length / s)


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
    """Rest-pose triangles of a mesh with a BVH, the arrival field's gradient per triangle and which ones may carry
    goo (not locked, not degenerate)."""

    def __init__(self, ob, values):
        me = ob.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        self.co = co.reshape(-1, 3).astype(np.float64)
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
    """One tendril branch or strand, in skeleton point attributes."""

    def __init__(self, kind, rnd):
        self.kind = kind
        self.rnd = rnd
        self.points = []  # rest positions
        self.a = []  # (triangle, weights) per point
        self.b = []
        self.t = []
        self.s = []
        self.length = 0.0
        self.root = None  # chain whose first point is the root (tendrils), filled in later


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


def _tendrils(surface, count, length, height, rng):
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


def _strands(surface, count, height, rng):
    """Strands across gaps: a ray out from the surface (within 40 degrees of the normal) that hits a surface facing
    back, not too close, not too far."""
    chains = []
    if count <= 0:
        return chains
    near, far = 0.01 * height, 0.12 * height
    pairs = []
    for k, p in surface.samples(count * 40, rng):
        n = surface.normals[k]
        d = _unit(n + np.tan(math.radians(40.0)) * math.sqrt(rng.random()) * _unit(np.cross(n, rng.normal(size=3))))
        # (an inner layer under the clothes hits them from inside: they face the same way and are skipped)
        loc, _nor, kq, dist = surface.bvh.ray_cast(Vector(p + n * 1e-4 * height), Vector(d), far)
        if loc is None or dist < near or not surface.free[kq] or surface.normals[kq] @ d > -0.2:
            continue
        q = np.array(loc)
        pairs.append((k, (p + q) * 0.5, p, kq, q))
    spacing = 0.5 * math.sqrt(float(np.where(surface.free, surface.area, 0.0).sum()) / max(count, 1))
    for k, _mid, p, kq, q in _spaced(pairs, spacing)[:count]:
        chain = _Chain(1, float(rng.random()))
        wa, wb = surface.weights(k, p), surface.weights(kq, q)
        for t in np.linspace(0.0, 1.0, STRAND_POINTS):
            chain.points.append(p + (q - p) * t)
            chain.a.append((k, wa))
            chain.b.append((kq, wb))
            chain.t.append(float(t))
            chain.s.append(0.0)
        chain.length = float(np.linalg.norm(q - p))
        chains.append(chain)
    return chains


def _mesh(name, surface, chains):
    """The skeleton mesh: one edge chain per chain, the bindings and timing as point attributes."""
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
    edges = np.concatenate([np.stack([np.arange(s, s + len(c.points) - 1), np.arange(s + 1, s + len(c.points))], 1)
                            for c, s in zip(chains, starts)]).astype(np.int32)
    me.vertices.add(total)
    me.vertices.foreach_set("co", co.ravel())
    me.edges.add(len(edges))
    me.edges.foreach_set("vertices", edges.ravel())
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


def build(ob, values, settings, height, scene):
    """Trace the tendrils and strands of mesh `ob` (field `values` per vertex, object units) and give it a new
    skeleton. Returns (tendrils, strands)."""
    remove(ob)
    s = max(sum(abs(v) for v in ob.matrix_world.to_scale()) / 3.0, 1e-9)
    surface = _Surface(ob, values)
    rng = np.random.default_rng(len(ob.data.vertices) + 7919)
    tendrils = _tendrils(surface, settings.venom_tendrils, settings.venom_length / s, height / s, rng)
    strands = _strands(surface, settings.venom_strands, height / s, rng)
    me = _mesh(SKELETON, surface, tendrils + strands)
    sk = bpy.data.objects.new(SKELETON, me)
    sk.hide_render = True
    particles.asset_collection(scene).objects.link(sk)
    sk[P_SIGNATURE] = _encode(signature(settings, s))
    sk[P_VERTICES] = len(ob.data.vertices)
    ob[P_SKELETON] = sk
    return sum(1 for c in tendrils if c.root is c), len(strands)
