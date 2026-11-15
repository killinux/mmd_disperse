"""Inertia (惯性甩动, 1.30): the symbiote's tongue and the big tendrils off her back swing behind the way her head and
her upper back move.

Not a simulation at play time: that would only be right when the frames are played in order, and scrubbing to any
frame must show the same. Her armature is played through once (the dance as it is warped, with the roar's tilt and the
growth), a damped spring follows the point the tongue (the big tendrils) start from, frame by frame, and how far it
lags behind is keyed frame by frame: on the tongue's node tree, in the tongue's own space, and for the big tendrils on
the effect's clock empty (clock.py), in the back mesh's space, which drives that mesh's modifier. The armature is only
played again when what the motion depends on changed (the bone matrices are kept while Blender runs); a new strength
only scales the lag.
"""

import math

import numpy as np
from mathutils import Vector

from . import clock

TONGUE = (1.4, 0.18)  # the tongue's spring: how often it swings by itself (times a second) and its damping (1: none)
BACK = (0.9, 0.3)  # ... the big tendrils'
LIMIT = 0.35  # the lag is at most this share of the length
STEPS = 4  # spring steps a frame
P_KEY = "mmd_disperse_inertia_key"  # on what carries a lag: what it was worked out for
_PLAYED = {}  # motion key -> {bone: [world matrices]} while Blender runs


def forget():
    _PLAYED.clear()


def spring(points, fps, freq, damping):
    """How far (the tip minus the anchor) a damped spring following `points` ((frames, 3), a frame apart) lags behind,
    starting at rest; (frames, 3)."""
    points = np.asarray(points, dtype=np.float64)
    n = len(points)
    lag = np.zeros((n, 3))
    if n < 2:
        return lag
    dt = 1.0 / (fps * STEPS)
    w = 2.0 * math.pi * freq
    k, c = w * w, 2.0 * damping * w
    x = points[0].copy()
    v = (points[1] - points[0]) * fps
    for i in range(n):
        p0 = points[i - 1] if i else points[0]
        p1 = points[i]
        pv = (p1 - p0) * fps
        for s in range(STEPS):
            p = p0 + (p1 - p0) * ((s + 1) / STEPS)
            v += (k * (p - x) + c * (pv - v)) * dt
            x += v * dt
        lag[i] = x - p1
    return lag


def _limit(lag, length):
    size = np.linalg.norm(lag, axis=1)
    top = LIMIT * max(length, 1e-6)
    scale = np.where(size > top, top / np.maximum(size, 1e-12), 1.0)
    return lag * scale[:, None]


def play(scene, armature, bones, frames, hidden, key=None):
    """World matrices of the pose bones `bones` of `armature` at each of `frames`, played in order with the objects
    `hidden` off meanwhile (kept under `key` for the next time). The rigid body world is off meanwhile unless it is
    baked: the head and the chest are the dance's, and stepping it from here would fill its cache from the wrong
    start (switched on again, its cache is outdated and plays again from its first frame)."""
    if key is not None and key in _PLAYED:
        return _PLAYED[key]
    out = {name: [] for name in bones}
    current = scene.frame_current
    off = [ob for ob in hidden if ob is not None and not ob.hide_viewport]
    world = scene.rigidbody_world
    baked = world is not None and world.point_cache is not None and world.point_cache.is_baked
    paused = world is not None and world.enabled and not baked
    if paused:
        world.enabled = False
    for ob in off:
        ob.hide_viewport = True
    try:
        for f in frames:
            scene.frame_set(int(f))
            mw = armature.matrix_world.copy()
            for name in bones:
                out[name].append(mw @ armature.pose.bones[name].matrix)
    finally:
        for ob in off:
            ob.hide_viewport = False
        if paused:
            world.enabled = True
        scene.frame_set(current)
    if key is not None:
        _PLAYED.clear()
        _PLAYED[key] = out
    return out


def _motion_key(scene, armature, frames, extra):
    from .timewarp import strip_action

    action, _slot = strip_action(armature)
    return (armature.name, action.name if action is not None else "", tuple(action.frame_range) if action else (),
            len(armature.animation_data.nla_tracks) if armature.animation_data else 0, int(frames[0]),
            int(frames[-1]), round(scene.render.fps / scene.render.fps_base, 3)) + tuple(extra)


def tongue_lag(scene, armature, head, tongue, mats, strength, length):
    """The tongue's lag in its own space at each recorded frame: a spring following where it comes out of her mouth."""
    con = next((c for c in tongue.constraints if c.type == "CHILD_OF"), None)
    if con is None:
        return None
    basis = tongue.matrix_basis.copy()
    placed = [m @ con.inverse_matrix @ basis for m in mats]
    points = np.array([tuple(p.translation) for p in placed])
    fps = scene.render.fps / scene.render.fps_base
    lag = spring(points, fps, *TONGUE) * strength
    lag = _limit(lag, length)
    return np.array([tuple(p.to_3x3().normalized().transposed() @ Vector(v)) for p, v in zip(placed, lag)])


def back_lag(scene, chest, rest_chest, spine_world, mesh, mats, strength, length):
    """The big tendrils' lag in the back mesh's space at each recorded frame: a spring following her upper back."""
    to_bone = rest_chest.inverted() @ Vector(spine_world)
    points = np.array([tuple(m @ to_bone) for m in mats])
    fps = scene.render.fps / scene.render.fps_base
    lag = spring(points, fps, *BACK) * strength
    lag = _limit(lag, length)
    turn = mesh.matrix_world.to_3x3().normalized().transposed()
    return np.array([tuple(turn @ Vector(v)) for v in lag])


def key_tongue(tongue, mod, ident, frames, lag):
    """Key the tongue modifier's Lag input `ident` at `frames` (linear between, held outside)."""
    path = 'modifiers["%s"]["%s"]' % (mod.name, ident)
    from .timewarp import _curves

    owner, curves = _curves(tongue)
    for fc in [fc for fc in curves if fc.data_path == path]:
        owner.fcurves.remove(fc)
    if lag is None or not len(frames):
        mod[ident] = (0.0, 0.0, 0.0)
        return
    mod[ident] = tuple(float(v) for v in lag[0])
    for k in range(3):
        tongue.keyframe_insert(path, index=k, frame=frames[0])
    owner, curves = _curves(tongue)
    for k in range(3):
        fc = next((c for c in curves if c.data_path == path and c.array_index == k), None)
        if fc is None:
            continue
        points = fc.keyframe_points
        points.add(len(frames) - 1)
        points.foreach_set("co", [c for f, v in zip(frames, lag) for c in (float(f), float(v[k]))])
        for key in points:
            key.interpolation = "LINEAR"
        fc.update()


def clear(tongue=None, mod=None, ident=None, mask=None):
    """No lag: the tongue's keys gone (its Lag at 0), the clock's back lag gone."""
    if tongue is not None and mod is not None and ident is not None:
        key_tongue(tongue, mod, ident, [], None)
        if P_KEY in tongue:
            del tongue[P_KEY]
    if mask is not None:
        ob = clock.find(mask)
        if ob is not None:
            clock._drop(ob, clock.BACK_LAG)
            if P_KEY in ob:
                del ob[P_KEY]
