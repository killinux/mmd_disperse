"""Leave behind: record where the old outfit is at the moment it breaks apart.

Flakes and particles are stateless: every frame the Base node group places them relative to the body's
current pose, so on a dancing model they ride along with it. To let them stay where they broke off, the
build plays the transformation once and records, for every vertex of the old outfit, its position at the
moment the edge passes it (attribute `disperse_launch`); the node group then launches the pieces from
there. A probe modifier computes the very age the node group uses (mask radius minus the noisy
distance), so the recorded moment is the frame the piece really breaks off, interpolated between frames.

Bone animation (VMD) is followed; moving the whole object is not (the pieces live in object space).
"""

import bpy
import numpy as np

from .node_groups import ATTR_AGE, ATTR_LAUNCH, BASE_GROUP, FIELD_INPUTS, ensure_probe_group, input_identifiers

PROBE = "MMD Disperse Probe"


def has_launch(ob):
    return ob.type == "MESH" and ob.data.attributes.get(ATTR_LAUNCH) is not None


def remove(ob):
    attr = ob.data.attributes.get(ATTR_LAUNCH)
    if attr is not None:
        ob.data.attributes.remove(attr)


def _read(ob, deps, count):
    """(positions, age) of the evaluated mesh, or None when its vertices no longer match the original."""
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        attr = me.attributes.get(ATTR_AGE)
        if len(me.vertices) != count or attr is None:
            return None
        pos = np.empty(count * 3, dtype=np.float32)
        me.vertices.foreach_get("co", pos)
        age = np.empty(count, dtype=np.float32)
        attr.data.foreach_get("value", age)
        return pos.reshape(-1, 3), age
    finally:
        ev.to_mesh_clear()


def _add_probe(ob, group):
    """Probe modifier in front of our Base modifier, fed the same field inputs; everything from the Base
    modifier on is switched off. Returns (probe, {modifier: show_viewport} to restore)."""
    mods = list(ob.modifiers)
    base = next(i for i, m in enumerate(mods) if m.type == "NODES" and m.node_group
                and m.node_group.name == BASE_GROUP)
    probe = ob.modifiers.new(PROBE, "NODES")
    probe.node_group = group
    ob.modifiers.move(len(ob.modifiers) - 1, base)
    src, dst = input_identifiers(mods[base].node_group), input_identifiers(group)
    for spec in FIELD_INPUTS:
        name = spec[0]
        if name in src and name in dst:
            probe[dst[name]] = mods[base][src[name]]
    saved = {}
    for mod in mods[base:]:
        saved[mod] = mod.show_viewport
        mod.show_viewport = False
    return probe, saved


def record(context, meshes, others, frames, warmup=None):
    """Play `frames` and write the launch positions onto `meshes` (the old outfit, built). The node
    modifiers of `others` (new outfit, ribbons) are off meanwhile. `warmup` is an earlier frame to start
    playing from so physics settles. Returns how many vertices broke off within the frames."""
    frames = list(frames)
    if not frames or not meshes:
        return 0
    scene = context.scene
    group = ensure_probe_group()
    saved = {}
    probes = []
    for ob in others:
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.show_viewport:
                saved[mod] = True
                mod.show_viewport = False
    state = {}
    for ob in meshes:
        probe, off = _add_probe(ob, group)
        probes.append((ob, probe))
        saved.update(off)
        state[ob] = None
    current = scene.frame_current
    try:
        if warmup is not None:
            for f in range(warmup, frames[0]):
                scene.frame_set(f)
        for f in frames:
            scene.frame_set(f)
            deps = context.evaluated_depsgraph_get()
            for ob in meshes:
                count = len(ob.data.vertices)
                seen = _read(ob, deps, count)
                if seen is None:
                    continue
                pos, age = seen
                if state[ob] is None:
                    state[ob] = [pos.copy(), np.zeros(count, dtype=bool), pos, age]
                    continue
                launch, done, last_pos, last_age = state[ob]
                # The edge passed the vertex between the last frame and this one: interpolate to age 0.
                hit = ((last_age >= 0.0) != (age >= 0.0)) & ~done
                if hit.any():
                    a, b = last_age[hit], age[hit]
                    step = a - b
                    frac = np.clip(a / np.where(np.abs(step) > 1e-12, step, 1.0), 0.0, 1.0)
                    launch[hit] = last_pos[hit] + (pos[hit] - last_pos[hit]) * frac[:, None]
                    done |= hit
                state[ob][2:] = [pos, age]
    finally:
        for ob, probe in probes:
            ob.modifiers.remove(probe)
        for mod, shown in saved.items():
            mod.show_viewport = shown
        scene.frame_set(current)
    broken = 0
    for ob in meshes:
        remove(ob)
        if state[ob] is None:
            continue
        launch, done = state[ob][0], state[ob][1]
        attr = ob.data.attributes.new(ATTR_LAUNCH, "FLOAT_VECTOR", "POINT")
        attr.data.foreach_set("vector", launch.astype(np.float32).ravel())
        broken += int(done.sum())
    return broken
