"""Leave behind: record where the outfits are at the moments their pieces leave the body.

Flakes, chunks and particles are stateless: every frame the Base node group places them relative to the body's
current pose, so on a dancing model they ride along with it. To let them stay where they broke off, the build
plays the transformation once and records, for every vertex of the old outfit, its position at the moment the
edge passes it (attribute `disperse_launch`); the node group then launches the pieces from there. A probe
modifier computes the very age the node group uses (mask radius minus the noisy distance), so the recorded
moment is the frame the piece really breaks off, interpolated between frames.

A chunk (Cast Off) breaks off whole when the average age of its vertices turns positive, so its vertices are
recorded at that one moment, per face corner (`disperse_chunk_launch`): a vertex on a cut belongs to two chunks.
The probe cuts the mesh once the way the Base group does, to know which corner belongs to which chunk.

The new outfit is recorded the same way at its own moments: per vertex when its finale star is born (the stars
then burst out of where the body was), per piece when it takes off to fly in (it then flies from a fixed point in
the world to its place on the moving body).

Positions are recorded in world space, so moving or turning the whole model (object animation, not only
bones) leaves the pieces behind too. An empty (Launch Space) keeps the object's motion as it was recorded; the
node group brings the positions back into object space through it. Moving the model afterwards without
animating it (its world matrix changes the same way on every frame) carries the pieces along.

A recording only holds for the settings it was made with besides the mask keys (piece size, the finale's sweep
...): its signature, compared by effect.sync(), which drops a recording that no longer matches.
"""

import bpy
import numpy as np
from mathutils import Matrix

from . import particles
from .node_groups import (ATTR_AGE, ATTR_CHUNK_LAUNCH, ATTR_CORNER, ATTR_ISLAND, ATTR_LAUNCH, ATTR_PIECE_AGE,
                          ATTR_VERTEX, BASE_GROUP, PROBE_INPUTS, TARGET_GROUP, ensure_probe_group, input_identifiers)

PROBE = "MMD Disperse Probe"
SPACE = "MMD Disperse Motion"  # name of the empties holding the recorded object motion
P_SPACE = "mmd_disperse_launch_space"  # on a recorded mesh: its motion empty
P_SIGNATURE = "mmd_disperse_launch_signature"  # ... the settings its vertex moments depend on
P_CHUNK_SIGNATURE = "mmd_disperse_launch_chunk_signature"  # ... and its pieces'
P_PIECE = "mmd_disperse_launch_piece"  # 1.4: piece size the chunks were recorded with (their signature then)
GROUPS = (BASE_GROUP, TARGET_GROUP)


def space(ob):
    """The motion empty of a recorded mesh (None when there is no recording)."""
    sp = ob.get(P_SPACE)
    return sp if isinstance(sp, bpy.types.Object) else None


def has_launch(ob, chunks=False):
    """True when the mesh has a recording of its vertices (of its pieces with `chunks`)."""
    if ob.type != "MESH" or space(ob) is None:
        return False
    return ob.data.attributes.get(ATTR_CHUNK_LAUNCH if chunks else ATTR_LAUNCH) is not None


def _encode(values):
    return ";".join(repr(float(v)) for v in values)


def signature(ob, chunks=False):
    """Values the recording of the vertices (pieces) was made with; None when unknown."""
    text = ob.get(P_CHUNK_SIGNATURE if chunks else P_SIGNATURE)
    if text is None:  # recorded by 1.4: only the old outfit, its vertices depending on nothing else
        if chunks:
            return (float(ob[P_PIECE]),) if P_PIECE in ob else None
        return ()
    return tuple(float(v) for v in text.split(";")) if text else ()


def matches(ob, chunks, wanted):
    """True when the recording was made with the values `wanted`."""
    have = signature(ob, chunks)
    return have is not None and len(have) == len(wanted) and all(
        abs(a - b) <= 1e-4 * max(abs(a), abs(b), 1e-3) for a, b in zip(have, wanted))


def remove(ob, part=None):
    """Drop the recording of a mesh, or only one `part` of it: "vertices" or "chunks"."""
    if ob.type != "MESH":
        return
    for key, attr_name, props in (("vertices", ATTR_LAUNCH, (P_SIGNATURE,)),
                                  ("chunks", ATTR_CHUNK_LAUNCH, (P_CHUNK_SIGNATURE, P_PIECE))):
        if part not in (None, key):
            continue
        attr = ob.data.attributes.get(attr_name)
        if attr is not None:
            ob.data.attributes.remove(attr)
        for prop in props:
            if prop in ob:
                del ob[prop]
    if part is not None and (has_launch(ob) or has_launch(ob, chunks=True)):
        return
    sp = space(ob)
    if sp is not None:
        action = sp.animation_data.action if sp.animation_data else None
        bpy.data.objects.remove(sp)
        if action is not None and action.users == 0:
            bpy.data.actions.remove(action)
    if P_SPACE in ob:
        del ob[P_SPACE]


class Job:
    """A mesh to record (built): the moments of its vertices with `vertices`, of its pieces with `chunks`, each
    with the signature they depend on; `target` for the new outfit."""

    def __init__(self, ob, target=False, vertices=True, chunks=False, signature=(), chunk_signature=()):
        self.ob = ob
        self.target = target
        self.vertices = vertices
        self.chunks = chunks
        self.signature = tuple(signature)
        self.chunk_signature = tuple(chunk_signature)


def _read(ob, deps, count):
    """(world positions, vertex age, piece age, world matrix) of the evaluated mesh, or None when its vertices no
    longer match the original."""
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        ages = [me.attributes.get(name) for name in (ATTR_AGE, ATTR_PIECE_AGE)]
        if len(me.vertices) != count or None in ages:
            return None
        pos = np.empty(count * 3, dtype=np.float32)
        me.vertices.foreach_get("co", pos)
        age, piece_age = np.empty(count, dtype=np.float32), np.empty(count, dtype=np.float32)
        ages[0].data.foreach_get("value", age)
        ages[1].data.foreach_get("value", piece_age)
        matrix = np.array(ev.matrix_world, dtype=np.float64)
        world = pos.reshape(-1, 3).astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
        return world, age, piece_age, matrix
    finally:
        ev.to_mesh_clear()


def _int_values(attributes, name, count):
    attr = attributes.get(name)
    if attr is None or len(attr.data) != count:
        return None
    values = np.empty(count, dtype=np.int32)
    attr.data.foreach_get("value", values)
    return values


def _ours(mod):
    return mod.type == "NODES" and mod.node_group is not None and mod.node_group.name in GROUPS


def _add_probe(ob, group, target):
    """Probe modifier in front of our Base / Target modifier, fed the same inputs; everything from that modifier on
    is switched off. Returns (probe, {modifier: show_viewport} to restore)."""
    mods = list(ob.modifiers)
    ours = next(i for i, m in enumerate(mods) if _ours(m))
    probe = ob.modifiers.new(PROBE, "NODES")
    probe.node_group = group
    ob.modifiers.move(len(ob.modifiers) - 1, ours)
    src, dst = input_identifiers(mods[ours].node_group), input_identifiers(group)
    for spec in PROBE_INPUTS:
        name = spec[0]
        if name in src and name in dst:
            probe[dst[name]] = mods[ours][src[name]]
    probe[dst["Target"]] = target
    saved = {}
    for mod in mods[ours:]:
        saved[mod] = mod.show_viewport
        mod.show_viewport = False
    return probe, saved


class _Chunks:
    """How the probe cuts a mesh into chunks, and the chunk recording."""

    def __init__(self, vertex, island, corner_island, corner_vertex):
        self.vertex = vertex  # per vertex of the cut mesh: original vertex
        self.island = island  # ... and its chunk
        self.count = np.bincount(island).astype(np.float64)
        self.corner_island = corner_island  # per original face corner: its chunk
        self.corner_vertex = corner_vertex  # ... and its vertex
        self.launch = None
        self.done = np.zeros(len(self.count), dtype=bool)
        self.last_age = None

    def age(self, age):
        """Age of every chunk: the average over its vertices, as the node groups take it."""
        return np.bincount(self.island, weights=age[self.vertex], minlength=len(self.count)) / self.count


def _cut(context, ob, probe):
    """_Chunks of the mesh, from the probe switched to Pieces for one evaluation; None when the cut mesh does
    not line up with the original."""
    key = input_identifiers(probe.node_group)["Pieces"]
    probe[key] = True
    ob.update_tag()
    try:
        ev = ob.evaluated_get(context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        try:
            vertex = _int_values(me.attributes, ATTR_VERTEX, len(me.vertices))
            island = _int_values(me.attributes, ATTR_ISLAND, len(me.vertices))
            corner = _int_values(me.attributes, ATTR_CORNER, len(me.loops))
            loop_vertex = np.empty(len(me.loops), dtype=np.int32)
            me.loops.foreach_get("vertex_index", loop_vertex)
        finally:
            ev.to_mesh_clear()
    finally:
        probe[key] = False
        ob.update_tag()
    corners = len(ob.data.loops)
    if vertex is None or island is None or corner is None or len(corner) != corners or len(vertex) == 0:
        return None
    if vertex.min() < 0 or vertex.max() >= len(ob.data.vertices):
        return None
    corner_island = np.full(corners, -1, dtype=np.int64)
    corner_island[corner] = island[loop_vertex]
    if (corner_island < 0).any():
        return None
    corner_vertex = np.empty(corners, dtype=np.int32)
    ob.data.loops.foreach_get("vertex_index", corner_vertex)
    return _Chunks(vertex, island, corner_island, corner_vertex)


def _crossing(last, now, done):
    """Where the age changed sign between two frames (and was not recorded yet), and the fraction of the step
    at which it was 0."""
    hit = ((last >= 0.0) != (now >= 0.0)) & ~done
    a, b = last[hit], now[hit]
    step = a - b
    return hit, np.clip(a / np.where(np.abs(step) > 1e-12, step, 1.0), 0.0, 1.0)


class _Track:
    """Recording of one mesh while the frames play."""

    def __init__(self, job, chunks):
        self.job = job
        self.ob = job.ob
        self.chunks = chunks
        self.launch = None
        self.done = None
        self.last_pos = None
        self.last_age = None
        self.matrices = []

    def add(self, frame, pos, age, piece_age, matrix):
        self.matrices.append((frame, matrix))
        chunks = self.chunks
        chunk_age = chunks.age(piece_age) if chunks is not None else None
        if self.launch is None:
            self.launch = pos.copy()
            self.done = np.zeros(len(age), dtype=bool)
            if chunks is not None:
                chunks.launch = pos[chunks.corner_vertex]
                chunks.last_age = chunk_age
        else:
            # The moment came for the vertex between the last frame and this one: interpolate to age 0.
            hit, frac = _crossing(self.last_age, age, self.done)
            if hit.any():
                self.launch[hit] = self.last_pos[hit] + (pos[hit] - self.last_pos[hit]) * frac[:, None]
                self.done |= hit
            if chunks is not None:
                # ... and for a chunk: all its corners at the same moment, so it stays in one piece.
                hit, frac = _crossing(chunks.last_age, chunk_age, chunks.done)
                if hit.any():
                    at = np.zeros(len(hit))
                    at[hit] = frac
                    corners = np.nonzero(hit[chunks.corner_island])[0]
                    v = chunks.corner_vertex[corners]
                    step = at[chunks.corner_island[corners]][:, None]
                    chunks.launch[corners] = self.last_pos[v] + (pos[v] - self.last_pos[v]) * step
                    chunks.done |= hit
                chunks.last_age = chunk_age
        self.last_pos, self.last_age = pos, age


def _key_motion(sp, matrices):
    """Give the empty the recorded world matrices: a constant transform, or one linear key per frame."""
    first = matrices[0][1]
    if all(np.allclose(m, first, rtol=0.0, atol=1e-6) for _f, m in matrices):
        sp.matrix_world = Matrix(first.tolist())
        return
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR"
    try:
        euler = None
        for frame, m in matrices:
            loc, rot, scale = Matrix(m.tolist()).decompose()
            euler = rot.to_euler("XYZ", euler) if euler is not None else rot.to_euler("XYZ")
            sp.location, sp.rotation_euler, sp.scale = loc, euler, scale
            for path in ("location", "rotation_euler", "scale"):
                sp.keyframe_insert(path, frame=frame)
    finally:
        prefs.keyframe_new_interpolation_type = old
    ad = sp.animation_data
    action = ad.action if ad is not None else None
    curves = getattr(action, "fcurves", None) if action is not None else []
    if curves is None:  # Blender 5.0+: the curves are kept per slot
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    for fc in curves:  # (Blender 3.6 run from the command line keeps Bezier keys whatever the preference says)
        for key in fc.keyframe_points:
            key.interpolation = "LINEAR"


def _write(track, scene):
    """Store the recording on the mesh and wire its motion empty into our modifier."""
    ob, job = track.ob, track.job
    remove(ob)
    if job.vertices:
        attr = ob.data.attributes.new(ATTR_LAUNCH, "FLOAT_VECTOR", "POINT")
        attr.data.foreach_set("vector", track.launch.astype(np.float32).ravel())
        ob[P_SIGNATURE] = _encode(job.signature)
    if track.chunks is not None:
        attr = ob.data.attributes.new(ATTR_CHUNK_LAUNCH, "FLOAT_VECTOR", "CORNER")
        attr.data.foreach_set("vector", track.chunks.launch.astype(np.float32).ravel())
        ob[P_CHUNK_SIGNATURE] = _encode(job.chunk_signature)
    sp = bpy.data.objects.new(SPACE, None)
    sp.empty_display_size = 0.1
    sp.hide_render = True
    particles.asset_collection(scene).objects.link(sp)
    _key_motion(sp, track.matrices)
    ob[P_SPACE] = sp
    for mod in ob.modifiers:
        if _ours(mod):
            key = input_identifiers(mod.node_group).get("Launch Space")
            if key is not None:
                mod[key] = sp
            ob.update_tag()


def record(context, jobs, others, frames, warmup=None):
    """Play `frames` and write the launch positions of every Job's mesh. The node modifiers of `others` (meshes
    not recorded, ribbons) are off meanwhile. `warmup` is an earlier frame to start playing from so physics
    settles. Returns how many vertices reached their moment within the frames."""
    frames = list(frames)
    if not frames or not jobs:
        return 0
    scene = context.scene
    # Evaluate once with our modifiers on: Blender 3.6 never evaluates a hidden object our modifiers were the first
    # to reference (the particle and star shapes just created) if they are off at that moment, and Object Info then
    # keeps getting an empty geometry from it.
    context.view_layer.update()
    group = ensure_probe_group()
    saved = {}
    probes = {}
    for ob in others:
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.show_viewport:
                saved[mod] = True
                mod.show_viewport = False
    for job in jobs:
        probe, off = _add_probe(job.ob, group, job.target)
        probes[job.ob] = probe
        saved.update(off)
    tracks = []
    current = scene.frame_current
    try:
        for job in jobs:
            tracks.append(_Track(job, _cut(context, job.ob, probes[job.ob]) if job.chunks else None))
        if warmup is not None:
            for f in range(warmup, frames[0]):
                scene.frame_set(f)
        for f in frames:
            scene.frame_set(f)
            deps = context.evaluated_depsgraph_get()
            for track in tracks:
                seen = _read(track.ob, deps, len(track.ob.data.vertices))
                if seen is not None:
                    track.add(f, *seen)
        reached = 0
        for track in tracks:
            if track.launch is not None and (track.job.vertices or track.chunks is not None):
                _write(track, scene)
                reached += int(track.done.sum()) if track.job.vertices else 0
            else:
                remove(track.ob)
    finally:
        for ob, probe in probes.items():
            ob.modifiers.remove(probe)
        for mod, shown in saved.items():
            mod.show_viewport = shown
        scene.frame_set(current)
    return reached
