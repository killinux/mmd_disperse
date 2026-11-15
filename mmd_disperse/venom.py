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

1.29: the big tendrils off her back (Venom's back tentacles) are chains too, every point bound to the root (a face
of her upper back between the shoulder blades, found by rays from behind); the node tree grows them out of the goo,
up and out, and lashes them about. Only one mesh of the outfit carries them: the one those rays meet first.
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
P_BACK = "mmd_disperse_venom_back"  # ... and how many big tendrils off her back it carries (1.29)

# Point attributes of the skeleton (besides the bindings of end A, a tendril point or the first end of a strand, and
# end B, the other end of a strand: VENOM_ENDS, three vertex indices and their weights each).
ATTR_T = "mmdd_t"  # strands: 0 at end A .. 1 at end B
ATTR_KIND = "mmdd_kind"  # 0 tendril, 1 strand, 2 web
ATTR_S = "mmdd_s"  # tendrils, webs: length along the tendril from its root (object units)
ATTR_LENGTH = "mmdd_len"  # tendrils, webs: s at the end of the branch; strands: rest length
ATTR_ROOT = "mmdd_root"  # tendrils, webs: skeleton index of the root, whose age times the whole tendril
ATTR_RND = "mmdd_rnd"  # random number per tendril / strand
ATTR_THICK = "mmdd_thick"  # thickness factor per tendril / strand (1.27: the feelers are thin)
ATTR_FAN = "mmdd_fan"  # 1.29, big tendrils off her back: which way they fan out (-1 .. 1 across her back)

STEPS = 24  # trace steps per tendril length
STRAND_POINTS = 8
COVER = 0.012  # a surface with another one this close above it (fraction of the model height) is hidden: no seeds
BRANCHES = (0.7, 0.3)  # chance of a first and a second branch
WEB_ROWS, WEB_COLUMNS = 6, 4  # faces of a web along the fork and across it
WEB_REACH = 0.5  # how far up the fork a web reaches (share of the shorter side)
WEB_CURVE = 0.6  # how far its free edge curves in, in the middle (share of the reach)
POSES = 4  # frames of the animation the strands are also looked for in
COIL_TURN = 0.75  # 1.27, coiling tendrils: a steady turn (radians) off the field each step, so they corkscrew round
# a limb (or across the body) instead of crawling straight ahead
FEELERS = 2  # 1.27: feelers off each tendril near its tip: short, thin branches ...
FEELER_LENGTH = (0.12, 0.22)  # ... this share of the tendril's length ...
FEELER_THICK = 0.45  # ... this share of its thickness
BACK_POINTS = 16  # 1.29: points along a big tendril off her back ...
BACK_SPREAD = 0.075  # ... their roots spread this far either side of her spine (a share of her height) ...
BACK_LEVEL = 0.65  # ... this far up from her chest bone's head to her neck's (between the shoulder blades)
BACK_CHEST = ("上半身2", "upper body2", "UpperBody2", "Chest", "chest", "J_Bip_C_Chest", "上半身", "UpperBody",
              "upper body", "Spine2")


def skeleton(ob):
    sk = ob.get(P_SKELETON)
    return sk if isinstance(sk, bpy.types.Object) else None


def signature(settings, s, back=False):
    """What the skeleton of a mesh with scale `s` depends on (object units; the frames the strands are looked for in
    come from the transformation's frame range); with `back` it carries the big tendrils off her back (1.29)."""
    count = int(getattr(settings, "venom_back", 0)) if back else 0
    return (float(settings.venom_tendrils), float(settings.venom_strands), settings.venom_length / s,
            float(settings.venom_webs), float(settings.frame_start), float(settings.frame_end),
            float(getattr(settings, "venom_coil", 0.0)), float(getattr(settings, "venom_feelers", False)),
            float(count), getattr(settings, "venom_back_length", 0.0) * settings.size_reference / s if count else 0.0)


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


def _length(v):
    """The length of the three-vector `v` (1.32: np.linalg.norm costs microseconds a call, and the traces call it a
    million times)."""
    return math.sqrt(float(v @ v))


def _unit(v):
    length = _length(v)
    return v / length if length > 1e-12 else v


def _cross(a, b):
    """a x b for three-vectors (1.32: np.cross is slow on single vectors)."""
    a0, a1, a2 = float(a[0]), float(a[1]), float(a[2])
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    return np.array((a1 * b2 - a2 * b1, a2 * b0 - a0 * b2, a0 * b1 - a1 * b0))


def _turn(v, axis, angle):
    """`v` rotated by `angle` about the unit `axis` (Rodrigues)."""
    c, s = math.cos(angle), math.sin(angle)
    return v * c + _cross(axis, v) * s + axis * float(axis @ v) * (1.0 - c)


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
        d00, d01, d11 = float(v0 @ v0), float(v0 @ v1), float(v1 @ v1)
        d20, d21 = float(v2 @ v0), float(v2 @ v1)
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-30:
            return np.array([1.0, 0.0, 0.0])
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        u, v, w = min(max(1.0 - v - w, 0.0), 1.0), min(max(v, 0.0), 1.0), min(max(w, 0.0), 1.0)
        total = max(u + v + w, 1e-12)
        return np.array((u / total, v / total, w / total))

    def field(self, k, p):
        return float(self.weights(k, p) @ self.values[self.tris[k]])

    def hidden(self, p, n, cover):
        """True when another surface lies within `cover` above `p` (an inner layer under the clothes)."""
        return self.bvh.ray_cast(Vector(p + n * cover * 0.05), Vector(n), cover)[0] is not None

    def samples(self, count, rng):
        """`count` random points on the free triangles, by area: (triangle, point) pairs."""
        picks, points = self.sample_arrays(count, rng)
        return list(zip(picks.tolist(), points))

    def sample_arrays(self, count, rng):
        """(triangles, points) of `count` random points on the free triangles, by area, as arrays (both empty when
        there are none)."""
        weight = np.where(self.free, self.area, 0.0)
        total = weight.sum()
        if total <= 0.0 or count <= 0:
            return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
        picks = rng.choice(len(weight), size=count, p=weight / total)
        r1, r2 = np.sqrt(rng.random(count)), rng.random(count)
        a, b, c = (self.co[self.tris[picks, i]] for i in range(3))
        points = a * (1.0 - r1)[:, None] + b * (r1 * (1.0 - r2))[:, None] + c * (r1 * r2)[:, None]
        return picks, points

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
                        if _length(other - p) < spacing:
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
        self.thick = 1.0  # thickness factor (feelers are thin)
        self.fan = 0.0  # big tendrils off her back: which way they fan out (1.29)


def _trace(surface, k, p, heading, length, step, rng, s0=0.0, bias=0.0):
    """Points (point, triangle, s) of a path from `p` on triangle `k` along the field for `length`, starting towards
    `heading` (None: straight along the field). It stops early at locked parts, sharp folds and dead ends. With a
    `bias` (radians) it keeps turning that far off the field: round a limb that is a corkscrew (1.27)."""
    path = [(p, k, s0)]
    n = surface.normals[k]
    d = heading if heading is not None else surface.grad[k]
    d = _unit(d - n * float(d @ n))
    if _length(d) < 0.5:
        return path
    f = surface.field(k, p)
    angle = 0.0
    s = s0
    while s - s0 < length:
        g = surface.grad[k] - n * float(surface.grad[k] @ n)
        g = _unit(g) if _length(g) > 1e-9 else d
        if bias:
            angle = min(max(0.5 * angle + bias + float(rng.normal(0.0, 0.15)), -1.25), 1.25)
        else:
            angle = min(max(angle + float(rng.normal(0.0, 0.3)), -0.9), 0.9)
        d = _unit(0.6 * d + 0.4 * _turn(g, n, angle))
        d = _unit(d - n * float(d @ n))
        q, kq = surface.drop(p + d * step, n, step)
        if q is None or not surface.free[kq]:
            break
        nq = surface.normals[kq]
        moved = _length(q - p)
        if float(nq @ n) < 0.35 or moved < 0.3 * step or moved > 2.5 * step:
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


def _tendrils(surface, count, length, height, rng, webs=True, coil=0.0, feelers=False):
    """Tendrils over the free surface: trunks traced along the field (a `coil` share of them corkscrewing, 1.27),
    branches off their middles (with webs in the forks), and with `feelers` short thin ones off their tips."""
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
        bias = COIL_TURN * float(rng.choice((-1.0, 1.0))) if rng.random() < coil else 0.0
        path = _trace(surface, k, p, None, own, step, rng, bias=bias)
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
        if not feelers:
            continue
        # Feelers: short thin branches off the last part of the trunk, feeling about to either side.
        for _i in range(FEELERS):
            at = int(len(path) * (0.6 + 0.3 * rng.random()))
            fp, fk, fs = path[at]
            nf = surface.normals[fk]
            ahead = path[min(at + 1, len(path) - 1)][0] - fp
            side = _turn(_unit(ahead - nf * (ahead @ nf)), nf, (0.6 + 0.6 * rng.random()) * rng.choice((-1.0, 1.0)))
            feeler_path = _trace(surface, fk, fp, side, own * (FEELER_LENGTH[0] + (FEELER_LENGTH[1] - FEELER_LENGTH[0])
                                                              * rng.random()), step * 0.6, rng, fs)
            if len(feeler_path) < 3:
                continue
            feeler = _Chain(0, float(rng.random()))
            feeler.root = trunk
            feeler.thick = FEELER_THICK
            _fill(surface, feeler, feeler_path)
            chains.append(feeler)
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
    tilt = math.tan(math.radians(40.0))
    for surface in surfaces:
        # (1.32: the rays aimed all at once, within 40 degrees of the normal; only the casting one by one)
        ks, ps = surface.sample_arrays(count * 40, rng)
        if not len(ks):
            continue
        ns = surface.normals[ks]
        side = np.cross(ns, rng.normal(size=(len(ks), 3)))
        side /= np.maximum(np.sqrt((side * side).sum(axis=1)), 1e-12)[:, None]
        ds = ns + side * (tilt * np.sqrt(rng.random(len(ks))))[:, None]
        ds /= np.maximum(np.sqrt((ds * ds).sum(axis=1)), 1e-12)[:, None]
        starts = ps + ns * (1e-4 * height)
        for i in range(len(ks)):
            d = ds[i]
            # (an inner layer under the clothes hits them from inside: they face the same way and are skipped)
            loc, _nor, kq, dist = surface.bvh.ray_cast(Vector(starts[i]), Vector(d), far)
            if loc is None or dist < near or not surface.free[kq] or float(surface.normals[kq] @ d) > -0.2:
                continue
            k, p = int(ks[i]), ps[i]
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
    put(ATTR_THICK, "FLOAT", per_point(lambda c: c.thick, np.float32))
    put(ATTR_FAN, "FLOAT", per_point(lambda c: c.fan, np.float32))
    put(ATTR_ROOT, "INT", np.concatenate([np.full(len(c.points), first[id(c.root)] if c.root is not None
                                                  else start, dtype=np.int32) for c, start in zip(chains, starts)]))
    return me


def back_frame(ob):
    """(spine point, forward, up) of her upper back in the object space of mesh `ob` (rest pose, numpy arrays): the
    point BACK_LEVEL of the way from her chest bone's head to her neck's, the way she faces (her eyes in front of her
    head bone; else -Y of her armature) and her armature's up. None without a chest and a neck bone."""
    from . import motion
    from .model import find_armature

    arm = find_armature(ob)
    if arm is None:
        return None
    bones = arm.data.bones

    def bone(names):
        return next((bones[n] for n in names if n in bones), None)

    chest, neck, head = bone(BACK_CHEST), bone(motion.NECK), bone(motion.HEAD)
    if chest is None or neck is None:
        return None
    to_mesh = ob.matrix_world.inverted() @ arm.matrix_world
    spine = to_mesh @ chest.head_local.lerp(neck.head_local, BACK_LEVEL)
    ahead = Vector((0.0, -1.0, 0.0))
    eyes = [bone(names) for names in motion.EYES]
    if head is not None and all(e is not None for e in eyes):
        way = (eyes[0].head_local + eyes[1].head_local) / 2.0 - head.head_local
        way.z = 0.0
        if way.length > 1e-6:
            ahead = way.normalized()
    turn = to_mesh.to_3x3()
    forward = (turn @ ahead).normalized()
    up = (turn @ Vector((0.0, 0.0, 1.0))).normalized()
    return np.array(spine, dtype=np.float64), np.array(forward, dtype=np.float64), np.array(up, dtype=np.float64)


def _from_behind(bvh, free, normals, target, forward, height):
    """(point, triangle) where a ray from behind `target` (towards `forward`) first meets a free triangle facing back,
    passing through locked or front-facing ones; None when it meets none."""
    origin = target - forward * (0.6 * height)
    for _ in range(64):  # (through long hair: many cards of it)
        loc, _nor, k, _d = bvh.ray_cast(Vector(origin), Vector(forward), 1.5 * height)
        if loc is None:
            return None
        p = np.array(loc)
        if free[k] and float(np.dot(normals[k], -forward)) > 0.05:
            return p, k
        origin = p + forward * (1e-4 * height)
    return None


def _back(surface, frame, count, length, height, rng):
    """The big tendrils off her back (1.29): `count` chains of BACK_POINTS points, their roots spread across her
    upper back (rays from behind), every point bound to its root, about `length` long (object units, rest pose straight
    out along the root's normal; the node tree shapes them)."""
    spine, forward, up = frame
    side = np.cross(forward, up)
    side = side / max(np.linalg.norm(side), 1e-12)
    chains = []
    for i in range(count):
        share = (2.0 * (i + 0.5) / count - 1.0) if count > 1 else 0.0
        target = (spine + side * (share * BACK_SPREAD * height)
                  + up * ((rng.random() - 0.5) * 0.03 * height - abs(share) * 0.025 * height))
        hit = _from_behind(surface.bvh, surface.free, surface.normals, target, forward, height)
        if hit is None:
            continue
        p, k = hit
        chain = _Chain(3, float(rng.random()))
        chain.root = chain
        chain.fan = share
        chain.length = length * (0.85 + 0.3 * float(rng.random()))
        weights = surface.weights(k, p)
        for j in range(BACK_POINTS):
            sj = chain.length * j / (BACK_POINTS - 1)
            chain.points.append(p + surface.normals[k] * sj)
            chain.a.append((k, weights))
            chain.b.append((k, weights))
            chain.t.append(sj / chain.length)
            chain.s.append(sj)
        chains.append(chain)
    return chains


_BACK_MESH = {}  # (meshes, their vertex counts, her height) -> the name of the mesh the big tendrils grow out of


def back_mesh(meshes, height):
    """The mesh of `meshes` the big tendrils off her back grow out of (1.29): the one rays from behind her upper back
    meet first on a free face facing back; None when they meet none (or there are no chest and neck bones). `height`:
    hers, world units."""
    key = tuple((ob.name, len(ob.data.vertices)) for ob in meshes) + (round(height, 6),)  # (forget() on a rebuild)
    if key in _BACK_MESH:
        name = _BACK_MESH[key]
        return next((ob for ob in meshes if ob.name == name), None)
    best, nearest = None, None
    for ob in meshes:
        frame = back_frame(ob)
        if frame is None:
            continue
        s = max(sum(abs(v) for v in ob.matrix_world.to_scale()) / 3.0, 1e-9)
        surface = _Surface(ob, np.zeros(len(ob.data.vertices)))
        spine, forward, _up = frame
        hit = _from_behind(surface.bvh, surface.free, surface.normals, spine, forward, height / s)
        if hit is None:
            continue
        behind = float(np.dot(hit[0] - spine, -forward)) * s  # (how far behind her spine: world units)
        if nearest is None or behind > nearest:
            best, nearest = ob, behind
    _BACK_MESH[key] = best.name if best is not None else ""
    return best


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
    _BACK_MESH.clear()


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


def sample_poses_many(scene, obs, frames, quiet):
    """(1.32) sample_poses for all of the meshes `obs` in one pass over `frames` (a frame change each, not one per mesh
    and frame): their poses kept for the traces that follow (sample_poses finds them there)."""
    wanted = sorted(set(frames))
    todo = []
    for ob in obs:
        motion = _motion(ob)
        key = (ob.name, len(ob.data.vertices), tuple(wanted), motion) if motion else None
        if key is not None and key not in _POSES:
            todo.append((ob, key))
    if not todo:
        return
    saved = {}
    for other in set(quiet) | {ob for ob, _key in todo}:
        for mod in other.modifiers:
            ours = mod.type == "NODES" and mod.node_group is not None and mod.node_group.name.startswith("MMDDisperse")
            if ours and mod.show_viewport:
                saved[mod] = True
                mod.show_viewport = False
    for ob, _key in todo:
        mods = list(ob.modifiers)
        last = max((i for i, m in enumerate(mods) if m.type == "ARMATURE"), default=-1)
        for mod in mods[last + 1:]:
            if mod.show_viewport:
                saved[mod] = True
                mod.show_viewport = False
    current = scene.frame_current
    found = {key: [] for _ob, key in todo}
    try:
        for frame in wanted:
            scene.frame_set(frame)
            deps = bpy.context.evaluated_depsgraph_get()
            for ob, key in todo:
                count = len(ob.data.vertices)
                ev = ob.evaluated_get(deps)
                me = ev.to_mesh()
                try:
                    if len(me.vertices) == count:
                        co = np.empty(count * 3, dtype=np.float32)
                        me.vertices.foreach_get("co", co)
                        found[key].append(co)
                finally:
                    ev.to_mesh_clear()
    finally:
        for mod in saved:
            mod.show_viewport = True
        if scene.frame_current != current:
            scene.frame_set(current)
    _POSES.update(found)


def build(ob, values, settings, height, scene, poses=(), pose_key=None, back=False):
    """Trace the tendrils, webs and strands of mesh `ob` (field `values` per vertex, object units) and give it a new
    skeleton; strands are also looked for in `poses` (vertex positions, object space), and kept for the next trace when
    those have a `pose_key` (sample_poses); with `back` the big tendrils off her back too (1.29). Returns (tendrils,
    strands)."""
    remove(ob)
    s = max(sum(abs(v) for v in ob.matrix_world.to_scale()) / 3.0, 1e-9)
    surface = _Surface(ob, values)
    rng = np.random.default_rng(len(ob.data.vertices) + 7919)
    tendrils = _tendrils(surface, settings.venom_tendrils, settings.venom_length / s, height / s, rng,
                         settings.venom_webs, getattr(settings, "venom_coil", 0.0),
                         getattr(settings, "venom_feelers", False))
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
    bigs = []
    count = int(getattr(settings, "venom_back", 0))
    frame = back_frame(ob) if back and count > 0 else None
    if frame is not None:
        bigs = _back(surface, frame, count, getattr(settings, "venom_back_length", 0.45) * height / s, height / s,
                     np.random.default_rng(len(ob.data.vertices) + 31337))
    me = _mesh(SKELETON, surface, tendrils + strands + bigs)
    sk = bpy.data.objects.new(SKELETON, me)
    sk.hide_render = True
    particles.asset_collection(scene).objects.link(sk)
    sk[P_SIGNATURE] = _encode(signature(settings, s, back))
    sk[P_BACK] = len(bigs)
    sk[P_VERTICES] = len(ob.data.vertices)
    ob[P_SKELETON] = sk
    return sum(1 for c in tendrils if c.kind == 0 and c.root is c), len(strands)
