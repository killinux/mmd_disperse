"""Headless checks: build / rebuild / sync / remove restore everything, both directions, no-base mode.

blender -b "Tifa Gantz 18 V2.blend" --factory-startup --python tests/test_api.py -- \
    --target-blend "Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2"
"""

import argparse
import math
import os
import sys
import tempfile
import traceback
import wave

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import (beats, compositor, effect, launch, materials, particles, presets, ribbons,  # noqa: E402
                          rings, venom)
from mmd_disperse.arrival import limb_points  # noqa: E402
from mmd_disperse.model import resolve, rest_points_world  # noqa: E402
from mmd_disperse.node_groups import (ATTR_ARRIVAL, ATTR_CUT, ATTR_EDGE, ATTR_HOLO, ATTR_LAYER,  # noqa: E402
                                      ATTR_AHEAD, ATTR_FRAME, ATTR_LOCK, ATTR_PAINT, ATTR_SHADOW, ATTR_VARIANT,
                                      BASE_GROUP, GLYPHS, RING_STYLES, TARGET_GROUP, VENOM_ATTRS, VENOM_ENDS,
                                      input_identifiers)
from scene_setup import add_model_args, load_models  # noqa: E402

FAILURES = []


def check(cond, message):
    print(("PASS " if cond else "FAIL ") + message)
    if not cond:
        FAILURES.append(message)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    add_model_args(p)
    return p.parse_args(argv)


def snapshot(models):
    """Everything build() may touch, to compare after remove()."""
    snap = {}
    for model in models:
        snap[model.root.name] = [[round(v, 5) for v in r] for r in model.root.matrix_world]
        for ob in model.meshes:
            snap[ob.name] = {
                "mods": [(m.type, m.name, getattr(m, "object", None) and m.object.name) for m in ob.modifiers],
                "rest": ob.add_rest_position_attribute,
                "attrs": sorted(a.name for a in ob.data.attributes),
                "props": sorted(k for k in ob.keys()),
                "mats": {s.material.name: len(s.material.node_tree.nodes)
                         for s in ob.material_slots if s.material and s.material.node_tree},
            }
    return snap


class FakeLayout:
    """Stands in for UILayout so panel draw() code runs headless; validates names (and icons) it is given."""

    ICONS = set(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())

    def __init__(self):
        self.errors = []

    def _child(self, **_kw):
        child = FakeLayout()
        child.errors = self.errors
        return child

    row = column = box = _child

    def _icon(self, kw):
        if kw.get("icon", "NONE") not in self.ICONS:
            self.errors.append("icon " + kw["icon"])

    def separator(self, **_kw):
        pass

    def label(self, **kw):
        self._icon(kw)

    def prop(self, data, name, **kw):
        self._icon(kw)
        if name not in data.bl_rna.properties:
            self.errors.append("prop " + name)

    def prop_search(self, data, name, search_data, search_name, **_kw):
        self.prop(data, name)
        if search_name not in search_data.bl_rna.properties:
            self.errors.append("search " + search_name)

    def operator_menu_enum(self, idname, prop, **kw):
        self.operator(idname, **kw)

    def operator(self, idname, **kw):
        self._icon(kw)
        module, name = idname.split(".")
        try:
            getattr(getattr(bpy.ops, module), name).get_rna_type()
        except (AttributeError, KeyError):
            self.errors.append("operator " + idname)
        return type("OpProps", (), {})()


def draw_panels(context):
    from mmd_disperse import ui

    layout = FakeLayout()
    holder = type("PanelSelf", (), {"layout": layout})()
    for cls in ui.classes:
        if hasattr(cls, "draw_header"):
            cls.draw_header(holder, context)
        cls.draw(holder, context)
    return layout.errors


def evaluated_counts(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        return len(me.vertices)
    finally:
        ev.to_mesh_clear()


def evaluated_faces_and_edge(ob, name=ATTR_EDGE):
    """Face count of the evaluated mesh and the largest value of attribute `name` on it (glowing flakes ...)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        attr = me.attributes.get(name)
        top = 0.0
        if attr is not None and len(attr.data):
            values = np.zeros(len(attr.data), dtype=np.float32)
            attr.data.foreach_get("value", values)
            top = float(values.max())
        return len(me.polygons), top
    finally:
        ev.to_mesh_clear()


def evaluated_values(ob, name):
    """Values of attribute `name` on the evaluated mesh (None when it is missing)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        attr = me.attributes.get(name)
        if attr is None:
            return None
        values = np.zeros(len(attr.data), dtype=np.float32)
        attr.data.foreach_get("value", values)
        return values
    finally:
        ev.to_mesh_clear()


def flake_positions(ob):
    """Object-space positions of the evaluated vertices and which of them glow (the flakes in the air)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        glow = np.zeros(len(me.vertices), dtype=np.float32)
        me.attributes[ATTR_EDGE].data.foreach_get("value", glow)
        co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        return co.reshape(-1, 3), glow > 0.0
    finally:
        ev.to_mesh_clear()


def world_flakes(ob):
    """flake_positions() in world space."""
    co, glow = flake_positions(ob)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3], glow


def busiest_frame(ob, frames):
    """The frame of `frames` with the most flakes in the air."""
    counts = []
    for f in frames:
        bpy.context.scene.frame_set(f)
        counts.append(int(flake_positions(ob)[1].sum()))
    return frames[int(np.argmax(counts))]


def evaluated_islands(ob):
    """Per vertex of the evaluated mesh: the lowest vertex index of its connected piece (a chunk once cast off)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        corner_vertex = np.zeros(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", corner_vertex)
        starts = np.zeros(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", starts)
        label = np.arange(len(me.vertices))
    finally:
        ev.to_mesh_clear()
    face_of = np.repeat(np.arange(len(starts)), np.diff(np.append(starts, len(corner_vertex))))
    while True:
        lowest = np.minimum.reduceat(label[corner_vertex], starts)
        new = label.copy()
        np.minimum.at(new, corner_vertex, lowest[face_of])
        new = new[new]
        if (new == label).all():
            return label
        label = new


def piece_spread(vectors, label):
    """Per piece: how far its vectors stray from the piece's mean (0 when the piece moved as a whole)."""
    ids, inv = np.unique(label, return_inverse=True)
    mean = np.zeros((len(ids), 3))
    np.add.at(mean, inv, vectors)
    mean /= np.bincount(inv)[:, None]
    spread = np.zeros(len(ids))
    np.maximum.at(spread, inv, np.linalg.norm(vectors - mean[inv], axis=1))
    return spread


def fcurves(ob, path):
    """F-curves of `ob` animating `path` (Blender 5.0+ keeps them per action slot)."""
    ad = ob.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return []
    curves = getattr(action, "fcurves", None)
    if curves is None:
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    return [fc for fc in curves if fc.data_path == path]


def white_flash(scene):
    """(node, its drivers) of the compositor's white flash."""
    tree = scene.compositing_node_group if hasattr(scene, "compositing_node_group") else scene.node_tree
    node = tree.nodes.get(compositor.FLASH_NAME) if tree is not None else None
    drivers = tree.animation_data.drivers if tree is not None and tree.animation_data else []
    return node, [d for d in drivers if compositor.FLASH_NAME in d.data_path]


def white_flash_value(scene):
    """How far the white flash blends to white at the current frame (as driven)."""
    node = white_flash(scene)[0]
    sock = node.inputs["Fac"] if "Fac" in node.inputs else next(s for s in node.inputs if s.identifier == "Factor_Float")
    return float(sock.default_value)


def instance_count(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    return sum(1 for inst in deps.object_instances
               if inst.is_instance and inst.parent is not None and inst.parent.original == ob)


def instance_scales(ob):
    """Sizes (length of the scale vector) of the instances `ob` makes."""
    deps = bpy.context.evaluated_depsgraph_get()
    return np.array([inst.matrix_world.to_scale().length for inst in deps.object_instances
                     if inst.is_instance and inst.parent is not None and inst.parent.original == ob])


def instance_positions(ob):
    """World positions of the instances (stars, petals ...) `ob` makes, in their order."""
    deps = bpy.context.evaluated_depsgraph_get()
    return np.array([tuple(inst.matrix_world.translation) for inst in deps.object_instances
                     if inst.is_instance and inst.parent is not None and inst.parent.original == ob]).reshape(-1, 3)


def evaluated_positions(ob):
    """Object-space positions of the evaluated vertices."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
    finally:
        ev.to_mesh_clear()
    return co.reshape(-1, 3)


def world_vertices(ob, name=ATTR_EDGE):
    """World positions of the evaluated vertices and attribute `name` on them."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        values = np.zeros(len(me.vertices), dtype=np.float32)
        attr = me.attributes.get(name)
        if attr is not None and attr.domain == "POINT":
            attr.data.foreach_get("value", values)
    finally:
        ev.to_mesh_clear()
    mw = np.array(ob.matrix_world, dtype=np.float64)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3], values


def chain(mat):
    """Name prefixes of our shader nodes between the material output and the surface, output first."""
    out = next(n for n in mat.node_tree.nodes
               if n.bl_idname == "ShaderNodeOutputMaterial" and n.inputs["Surface"].links)
    names = []
    socket = out.inputs["Surface"]
    while socket.links:
        node = socket.links[0].from_node
        place = materials._place(node)
        if place is None:
            break
        names.append(node.name.rsplit(" ", 1)[0])
        socket = node.inputs[place[1]]
    return names


def material_points(ob, name, others=False):
    """World positions of the evaluated vertices of the faces drawn with material `name` (with `others`, of the faces
    drawn with any other material)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        names = [m.name if m is not None else "" for m in me.materials]
        if not len(me.polygons):
            return np.zeros((0, 3))
        face_material = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("material_index", face_material)
        totals = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("loop_total", totals)
        corner_vertex = np.zeros(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", corner_vertex)
        drawn = face_material == (names.index(name) if name in names else -1)
        picked = np.repeat(~drawn if others else drawn, totals)
        co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)[np.unique(corner_vertex[picked])]
    finally:
        ev.to_mesh_clear()
    mw = np.array(ob.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3]


def goo_points(ob):
    """World positions of the evaluated vertices drawn with the symbiote's goo (its tendrils and strands)."""
    return material_points(ob, materials.GOO_MATERIAL)


def surface_distance(points, ob):
    """Distance of world `points` to the skinned surface of mesh `ob` (our modifier off)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    mw = np.array(ob.matrix_world, dtype=np.float64)
    world = skinned(ob).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
    me = ob.data
    me.calc_loop_triangles()
    tris = np.zeros(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    bvh = BVHTree.FromPolygons(world.tolist(), tris.reshape(-1, 3).tolist(), all_triangles=True)
    return np.array([bvh.find_nearest(Vector(p))[3] for p in points])


def strand_gaps(skeleton, ob):
    """Per strand of a symbiote skeleton: how far apart its two ends are on the rest pose of `ob`, and its rest length
    (the gap where it was found)."""
    attrs = skeleton.data.attributes
    n = len(skeleton.data.vertices)

    def values(name, size=1, prop="value", dtype=np.float32):
        arr = np.zeros(n * size, dtype=dtype)
        attrs[name].data.foreach_get(prop, arr)
        return arr.reshape(n, size) if size > 1 else arr

    kinds, t, length = values("mmdd_kind"), values("mmdd_t"), values("mmdd_len")
    co = np.zeros(len(ob.data.vertices) * 3, dtype=np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    first = (kinds > 0.5) & (kinds < 1.5) & (t == 0.0)
    ends = []
    for end in VENOM_ENDS:
        index = np.stack([values(name, dtype=np.int32) for name in end[:3]], 1)
        ends.append((co[index] * values(end[3], 3, "vector")[:, :, None]).sum(axis=1))
    return np.linalg.norm(ends[1] - ends[0], axis=1)[first], length[first]


def write_clicks(path, times, seconds, rate=44100):
    """A WAV file with a kick-like click at each of `times` (seconds) over quiet noise."""
    rng = np.random.default_rng(3)
    data = rng.normal(0.0, 0.004, int(seconds * rate))
    k = np.arange(int(0.08 * rate))
    click = (0.8 * np.sin(2.0 * math.pi * 70.0 * k / rate) * np.exp(-k / (0.015 * rate))
             + rng.normal(0.0, 0.2, len(k)) * np.exp(-k / (0.004 * rate)))
    for t in times:
        i = int(t * rate)
        n = min(len(k), len(data) - i)
        data[i:i + n] += click[:n]
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(data, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def arrival_values(ob):
    attr = ob.data.attributes.get(ATTR_ARRIVAL)
    if attr is None:
        return None
    values = np.zeros(len(attr.data), dtype=np.float32)
    attr.data.foreach_get("value", values)
    return values


def free_vertices(ob):
    """Per vertex: True when none of its faces is locked (face, hair ...)."""
    me = ob.data
    lock = np.zeros(len(me.polygons), dtype=bool)
    me.attributes[ATTR_LOCK].data.foreach_get("value", lock)
    totals = np.zeros(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_total", totals)
    corner_vertex = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", corner_vertex)
    locked = np.zeros(len(me.vertices), dtype=bool)
    locked[corner_vertex[np.repeat(lock, totals)]] = True
    return ~locked


def locked_faces(ob):
    attr = ob.data.attributes.get(ATTR_LOCK)
    values = np.zeros(len(attr.data), dtype=bool)
    attr.data.foreach_get("value", values)
    return int(values.sum())


def our_modifiers(ob):
    return [m for m in ob.modifiers if m.type == "NODES" and m.node_group
            and m.node_group.name in (TARGET_GROUP, BASE_GROUP)]


def skinned(ob):
    """Vertex positions after skinning only (our node modifier switched off)."""
    mods = our_modifiers(ob)
    for m in mods:
        m.show_viewport = False
    try:
        deps = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        return co.reshape(-1, 3)
    finally:
        for m in mods:
            m.show_viewport = True


def arm_swing(base, target):
    """How far the old and the new outfit move when the old armature lifts the left arm."""
    pb = base.armature.pose.bones.get("腕.L") or base.armature.pose.bones.get("左腕")
    meshes = (base.meshes[0], target.meshes[0])
    before = [skinned(ob) for ob in meshes]
    pb.matrix_basis = Matrix.Rotation(math.radians(60.0), 4, "X")
    bpy.context.view_layer.update()
    after = [skinned(ob) for ob in meshes]
    pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    return [float(np.linalg.norm(a - b, axis=1).max()) for a, b in zip(after, before)]


def run():
    args = parse_args()
    mmd_disperse.register()
    scene = bpy.context.scene
    base_root, target_root = load_models(args)
    # Offset the new outfit like a user would after importing it next to the old one.
    target_root.location.x += 12.0
    bpy.context.view_layer.update()
    base, target = resolve(base_root), resolve(target_root)
    before = snapshot([base, target])

    s = scene.mmd_disperse
    errors = draw_panels(bpy.context)
    check(not errors, "panels draw with an empty setup %s" % errors)
    s.base, s.target = base_root, target_root
    s.use_lock = True
    s.lock_patterns = "Face*;Hair*;Eye*;*Brows*;Eyelashes*;Mouth*;*Teeth*;Inners*"
    s.frame_start, s.frame_end = 1, 100

    # --- build
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build finished")
    mask = s.mask
    check(mask is not None and mask.empty_display_type == "SPHERE", "mask empty created")
    check((target_root.matrix_world.translation - base_root.matrix_world.translation).length < 1e-6
          and sum(c.name.startswith(effect.FOLLOW) for c in target_root.constraints) == 1,
          "new outfit snapped onto the old one (and follows it)")
    for ob in target.meshes + base.meshes:
        check(len(our_modifiers(ob)) == 1, "one effect modifier on " + ob.name)
        names = [m.type for m in ob.modifiers]
        check(names.index("NODES") == names.index("ARMATURE") + 1, "modifier right after armature on " + ob.name)
        check(ob.data.attributes.get(ATTR_LOCK) is not None, "lock attribute on " + ob.name)
    old_move, new_move = arm_swing(base, target)
    check(old_move > 0.02 * effect.model_height(base_root) and new_move > 0.5 * old_move,
          "new outfit follows the old armature (arm lifted: old %.2f, new %.2f)" % (old_move, new_move))
    glow = [s_.material for ob in target.meshes for s_ in ob.material_slots
            if s_.material and s_.material.get(materials.P_GLOW)]
    check(len(glow) > 0, "edge glow injected into %d materials" % len(glow))
    check(not any(m.name.lower().startswith(("face", "hair")) for m in glow), "locked materials not glowing")

    errors = draw_panels(bpy.context)
    check(not errors, "panels draw with a built effect %s" % errors)

    # --- reveal progresses over time
    t_counts, b_counts = [], []
    for f in (1, 30, 60, 100):
        scene.frame_set(f)
        t_counts.append(evaluated_counts(target.meshes[0]))
        b_counts.append(evaluated_counts(base.meshes[0]))
    print("target verts", t_counts, "base verts", b_counts)
    check(t_counts[0] == 0, "new outfit hidden at the start")
    check(b_counts[0] == len(base.meshes[0].data.vertices), "old outfit complete at the start")
    check(b_counts[-1] < b_counts[1] < b_counts[0], "old outfit is consumed over time")
    check(t_counts[-1] > 0, "new outfit visible at the end")
    check(evaluated_counts(target.meshes[0]) < len(target.meshes[0].data.vertices), "locked parts removed from new")

    # --- live sync of a parameter
    s.wire_radius = 0.123
    mod = our_modifiers(target.meshes[0])[0]
    key = input_identifiers(mod.node_group)["Wire Radius"]
    check(abs(mod[key] - 0.123) < 1e-6, "panel change synced to modifier")
    s.edge_glow = False
    check(not any(m.get(materials.P_GLOW) for m in glow), "edge glow removed when disabled")
    s.edge_glow = True
    check(all(m.get(materials.P_GLOW) for m in glow), "edge glow re-added when enabled")

    # --- rebuild replaces the old effect
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "rebuild finished")
    masks = [o for o in bpy.data.objects if o.name.startswith(effect.MASK_NAME)]
    check(len(masks) == 1, "single mask after rebuild (%d)" % len(masks))
    check(all(len(our_modifiers(ob)) == 1 for ob in target.meshes + base.meshes), "single modifier after rebuild")
    check(abs(s.wire_radius - 0.123) < 1e-6, "rebuild keeps tuned sizes")

    # --- suit down
    s.direction = "SHRINK"
    bpy.ops.mmd_disperse.build()
    scene.frame_set(1)
    full = evaluated_counts(target.meshes[0])
    scene.frame_set(100)
    check(full > 0 and evaluated_counts(target.meshes[0]) == 0, "suit down: new outfit retracts")
    check(evaluated_counts(base.meshes[0]) == len(base.meshes[0].data.vertices), "suit down: old outfit restored")
    s.direction = "GROW"

    # --- remove restores the scene
    check(bpy.ops.mmd_disperse.remove() == {"FINISHED"}, "remove finished")
    after = snapshot([base, target])
    for key_ in before:
        check(before[key_] == after[key_], "restored " + key_)
    check(not any(o.name.startswith(effect.MASK_NAME) for o in bpy.data.objects), "mask deleted")
    check(not any(c.name.startswith(effect.FOLLOW) for pb in target.armature.pose.bones for c in pb.constraints),
          "no pose-copy constraints left on the new armature")

    # --- new outfit only (materialises from nothing)
    s.base = None
    s.use_lock = False
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build without old outfit")
    scene.frame_set(50)
    n50 = evaluated_counts(target.meshes[0])
    check(n50 > 0, "new outfit partially visible mid-way (%d verts)" % n50)
    bpy.ops.mmd_disperse.remove()

    # --- posed space + bloom operator
    s.base = base_root
    s.space = "POSED"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build in posed space")
    check(any(c.type == "COPY_LOCATION" for c in s.mask.constraints), "mask follows the bone when posed")
    check(bpy.ops.mmd_disperse.add_bloom() == {"FINISHED"}, "bloom added")
    check(bpy.ops.mmd_disperse.add_bloom() == {"FINISHED"}, "bloom idempotent")
    bpy.ops.mmd_disperse.remove()
    s.space = "REST"
    height = effect.model_height(base_root)

    # --- along the body, from the chest and both hands and feet at once
    s.path, s.seeds = "SURFACE", "ORIGIN_LIMBS"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build along the body")
    values = {ob.name: arrival_values(ob) for ob in target.meshes + base.meshes}
    check(all(v is not None and np.isfinite(v).all() and v.min() > 0 for v in values.values()),
          "arrival distance on every mesh, finite and positive")
    bv = values[base.meshes[0].name]
    near = np.linalg.norm(rest_points_world(base.meshes[0]) - np.array(limb_points(base.armature)[0]), axis=1)
    near = near < 0.03 * height
    check(near.any() and float(np.median(bv[near])) < 0.15 * float(bv.max()),
          "wave starts at the wrist (%.2f of %.2f)" % (float(np.median(bv[near])), float(bv.max())))
    check(s.mask[effect.P_REACH] > float(bv.max()), "mask grows past the farthest vertex")
    scene.frame_set(1)
    check(evaluated_counts(target.meshes[0]) == 0, "along the body: nothing of the new outfit at frame 1")
    scene.frame_set(100)
    check(evaluated_counts(target.meshes[0]) > 0, "along the body: new outfit there at the end")
    s.seeds = "LIMBS"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build from the hands and feet only")

    # --- sweep up: arrival grows with height
    s.path = "UP"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build sweep up")
    z = rest_points_world(base.meshes[0])[:, 2]
    check(float(np.corrcoef(arrival_values(base.meshes[0]), z)[0, 1]) > 0.999, "sweep up follows the height")
    check(s.mask.empty_display_type == "SINGLE_ARROW", "arrow mask for sweeps")
    s.path = "SPHERE"

    # --- disintegrate into glowing flakes + petals (face, hair ... stay)
    s.use_lock = True
    s.exit_style, s.particles = "FRAGMENTS", "PETAL"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with flakes and petals")
    check(not draw_panels(bpy.context), "panels draw with flakes and petals")
    base_mats = [s_.material for ob in base.meshes for s_ in ob.material_slots if s_.material]
    check(any(m.get(materials.P_GLOW) for m in base_mats), "old outfit materials glow for the flakes")
    scene.frame_set(50)
    faces, glow_top = evaluated_faces_and_edge(base.meshes[0])
    check(glow_top > 0.0, "flakes in the air at frame 50 (glow %.2f)" % glow_top)
    petals = instance_count(base.meshes[0])
    check(petals > 0, "petals released at frame 50 (%d)" % petals)
    # the other shapes: the same flight, each with its material
    for kind, mat_name in (("CUBE", materials.PARTICLE_MATERIAL), ("COIN", materials.COIN_MATERIAL),
                           ("SHARD", materials.ICE_MATERIAL), ("EMBER", materials.PARTICLE_MATERIAL)):
        s.particles = kind
        shape = bpy.data.objects.get(particles.NAMES[kind])
        check(shape is not None and len(shape.data.polygons) > 0 and shape.data.materials[0].name == mat_name
              and instance_count(base.meshes[0]) == petals,
              "%s released like the petals (%d)" % (kind.lower(), instance_count(base.meshes[0])))
    s.particles = "PETAL"
    scene.frame_set(100)
    faces, _ = evaluated_faces_and_edge(base.meshes[0])
    check(faces == locked_faces(base.meshes[0]), "only the shared parts of the old outfit left (%d faces)" % faces)
    check(instance_count(base.meshes[0]) == 0, "every petal gone at the end")

    # --- the wind blows in the world: turning the whole model leaves its direction alone. Without the burst and the
    # swirl the flakes only drift: turned with the model they would land on the old picture turned the same way.
    saved = s.frag_wind_dir[:], s.frag_burst, s.frag_turbulence
    s.frag_wind_dir, s.frag_burst, s.frag_turbulence = (1.0, 0.0, 0.0), 0.0, 0.0
    scene.frame_set(50)
    still, flying = world_flakes(base.meshes[0])
    pivot = np.array(base_root.matrix_world.translation)
    base_root.rotation_euler.z += math.pi / 2
    bpy.context.view_layer.update()
    scene.frame_set(51)
    scene.frame_set(50)
    turned, flying_turned = world_flakes(base.meshes[0])
    base_root.rotation_euler.z -= math.pi / 2
    bpy.context.view_layer.update()
    drift = np.zeros(3)
    if still.shape == turned.shape and flying.any() and (flying == flying_turned).all():
        quarter = np.array(Matrix.Rotation(math.pi / 2, 3, "Z"))
        drift = (turned - ((still - pivot) @ quarter.T + pivot))[flying].mean(axis=0)
    # (I - R) * wind: the wind along +X, turned with the model it would blow along +Y
    check(drift[0] > 0.01 * height and drift[1] < -0.01 * height and abs(drift[0] + drift[1]) < 0.25 * drift[0],
          "the wind keeps its world direction when the model turns (drift off the turned picture %s)"
          % np.round(drift, 3))
    s.frag_wind_dir, s.frag_burst, s.frag_turbulence = saved

    # --- butterflies, then live switch back to shrinking
    s.particles = "BUTTERFLY"
    check(bpy.data.objects.get(particles.BUTTERFLY) is not None, "butterfly shape created")
    scene.frame_set(50)
    check(instance_count(base.meshes[0]) > 0, "butterflies released at frame 50")
    s.particles = "OBJECT"
    s.particle_object = bpy.data.objects.get(particles.PETAL)
    check(not draw_panels(bpy.context), "panels draw with a custom particle object")
    s.exit_style, s.particles = "SHRINK", "NONE"
    check(not any(m.get(materials.P_GLOW) for m in base_mats), "flake glow removed when shrinking again")

    # --- suit down with flakes: the old outfit re-forms from its pieces
    s.exit_style, s.direction = "FRAGMENTS", "SHRINK"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build suit down with flakes")
    scene.frame_set(1)
    check(evaluated_faces_and_edge(base.meshes[0])[0] == locked_faces(base.meshes[0]),
          "suit down: old outfit still in pieces at the start")
    scene.frame_set(100)
    check(evaluated_counts(base.meshes[0]) == len(base.meshes[0].data.vertices), "suit down: old outfit re-formed")
    s.direction = "GROW"

    # --- hologram ahead of the edge, then the glitch
    s.exit_style, s.holo_enable = "SHRINK", True
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with the hologram")
    target_mats = [s_.material for ob in target.meshes for s_ in ob.material_slots if s_.material]
    check(any(m.get(materials.P_HOLO) for m in target_mats), "hologram added to the new outfit materials")
    scene.frame_set(1)
    check(evaluated_counts(target.meshes[0]) == 0, "hologram: nothing of the new outfit at frame 1")
    scene.frame_set(50)
    check(evaluated_faces_and_edge(target.meshes[0], ATTR_HOLO)[1] > 0.5, "hologram ahead of the edge at frame 50")
    s.holo_enable = False
    check(not any(m.get(materials.P_HOLO) for m in target_mats), "hologram removed when switched off")
    scene.frame_set(50)
    smooth_new, smooth_old = evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0])
    scene.frame_set(100)
    end_new, end_old = evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0])
    s.glitch_enable = True
    scene.frame_set(1)
    check(evaluated_counts(target.meshes[0]) == 0 and
          evaluated_counts(base.meshes[0]) == len(base.meshes[0].data.vertices), "glitch: untouched at frame 1")
    scene.frame_set(50)
    glitch_new, glitch_old = evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0])
    check((glitch_new, glitch_old) != (smooth_new, smooth_old), "glitch slices change frame 50 (%d/%d vs %d/%d)"
          % (glitch_new, glitch_old, smooth_new, smooth_old))
    scene.frame_set(51)
    scene.frame_set(50)
    check((evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0])) == (glitch_new, glitch_old),
          "glitch is the same every time frame 50 is shown")
    scene.frame_set(100)
    check((evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0])) == (end_new, end_old),
          "glitch: same end state as without it")
    check(bpy.ops.mmd_disperse.add_glitch_fx() == {"FINISHED"}, "RGB split added")
    check(bpy.ops.mmd_disperse.add_glitch_fx() == {"FINISHED"}, "RGB split idempotent")
    tree = scene.compositing_node_group if hasattr(scene, "compositing_node_group") else scene.node_tree
    lens = [n for n in tree.nodes if n.name.startswith(compositor.GLITCH_NAME)]
    drivers = tree.animation_data.drivers if tree.animation_data else []
    check(len(lens) == 1 and len(drivers) == 1 and drivers[0].driver.is_valid, "one lens node driven by the frame")
    check(not draw_panels(bpy.context), "panels draw with hologram and glitch")

    # --- the glitch on the beat: beats found in a click track (two a second from the scene's start); the slices flash
    # most on them and the RGB split spikes on them
    track = os.path.join(tempfile.gettempdir(), "mmdd_beats_test.wav")
    write_clicks(track, [0.5 * i for i in range(10)], 5.5)
    s.beat_audio = track
    check(bpy.ops.mmd_disperse.find_beats() == {"FINISHED"}, "beats found in a click track")
    beat_ob = beats.beat_object()
    fps = scene.render.fps / scene.render.fps_base
    on = [int(round(scene.frame_start + 0.5 * i * fps)) for i in range(10)]
    off = [f + int(round(0.25 * fps)) for f in on]
    check(beat_ob is not None and beat_ob.get(beats.P_BEATS) == 10 and s.beat_sync,
          "ten beats, the glitch follows them (%s)" % (beat_ob.get(beats.P_BEATS) if beat_ob else None))
    pulses = []
    for f_on, f_off in zip(on, off):
        scene.frame_set(f_on)
        a = beat_ob.location.x if beat_ob else 0.0
        scene.frame_set(f_off)
        pulses.append((round(a, 2), round(beat_ob.location.x if beat_ob else 0.0, 2)))
    check(all(a > 0.7 and b_ < 0.2 for a, b_ in pulses), "the beat empty pulses on the beats %s" % pulses)
    mod_ids = input_identifiers(our_modifiers(base.meshes[0])[0].node_group)
    check(our_modifiers(base.meshes[0])[0][mod_ids["Beat Sync"]] and
          our_modifiers(base.meshes[0])[0][mod_ids["Beat Object"]] == beat_ob, "modifiers read the beats")
    # Same frames, the pulse held on and off (its curve muted), so the same slices are in the band either way.
    pulse_curve = next((c for c in beats._fcurves(beat_ob) if c.data_path == "location" and c.array_index == 0), None)
    flashes = {"on": 0, "off": 0}
    if pulse_curve is not None:
        pulse_curve.mute = True
        for f in (30, 40, 50, 60):
            scene.frame_set(f)
            for name, value in (("on", 1.0), ("off", 0.0)):
                beat_ob.location.x = value
                bpy.context.view_layer.update()
                values = evaluated_values(base.meshes[0], ATTR_EDGE)
                flashes[name] += int((values > 0.5).sum()) if values is not None else 0
        pulse_curve.mute = False
    check(flashes["on"] > 3 * max(flashes["off"], 1), "slices flash on the beat %s" % flashes)
    drivers = tree.animation_data.drivers if tree.animation_data else []
    check(len(drivers) == 1 and drivers[0].driver.is_valid and [v.name for v in drivers[0].driver.variables] == ["b"],
          "the RGB split spikes on the beat")
    # The wires flare and the particles pop on the beat (the pulse held on and off at the same frames) ...
    s.particles = "PETAL"
    flare, pop = {"on": 0.0, "off": 0.0}, {"on": 0.0, "off": 0.0}
    if pulse_curve is not None:
        pulse_curve.mute = True
        for f in (40, 50):
            scene.frame_set(f)
            for name, value in (("on", 1.0), ("off", 0.0)):
                beat_ob.location.x = value
                bpy.context.view_layer.update()
                values = evaluated_values(target.meshes[0], ATTR_EDGE)
                flare[name] = max(flare[name], float(values.max()) if values is not None and len(values) else 0.0)
                sizes = instance_scales(base.meshes[0])
                pop[name] += float(sizes.mean()) if len(sizes) else 0.0
        pulse_curve.mute = False
    check(flare["on"] > 1.3 * flare["off"] > 0.0, "the wires flare on the beat %s" % flare)
    check(pop["on"] > 1.3 * pop["off"] > 0.0, "the particles pop on the beat %s" % pop)
    s.particles = "NONE"
    # ... and the finale waits for the next beat: the new outfit lights up first on a beat
    s.finale = True
    finale_mod = our_modifiers(target.meshes[0])[0]
    start = (finale_mod[input_identifiers(finale_mod.node_group)["Finale Start"]]
             * effect._object_scale(target.meshes[0]))
    first = None
    for f in range(1, 101):
        scene.frame_set(f)
        if first is None and s.mask.scale[0] > start * (1.0 + 1e-6):
            first = f
    check(first is not None and first in beats.beat_frames() and start > 0.9 * float(s.mask[effect.P_WAVE]),
          "the finale starts on a beat (frame %s; beats %s)" % (first, beats.beat_frames()))
    s.finale = False
    s.beat_sync = False
    drivers = tree.animation_data.drivers if tree.animation_data else []
    check(not our_modifiers(base.meshes[0])[0][mod_ids["Beat Sync"]] and len(drivers) == 1
          and not drivers[0].driver.variables, "beat sync off: back to the flicker rate")
    s.glitch_enable = False
    scene.frame_set(100)
    grown_faces = evaluated_faces_and_edge(target.meshes[0])[0]

    # --- inner glow: both outfits mark how close each vertex is to the cut, their materials light the back faces
    # there; the dark undersuit: the new outfit first forms dark and takes on its own look behind the edge, so the
    # mask grows that much further
    wave, reach_plain = float(s.mask[effect.P_WAVE]), float(s.mask[effect.P_REACH])
    base_free = [s_.material for ob in base.meshes for s_ in ob.material_slots
                 if s_.material and not s_.material.name.lower().startswith(("face", "hair"))]
    s.inner_glow = True
    check(all(m.get(materials.P_INNER) for m in glow) and any(m.get(materials.P_INNER) for m in base_free),
          "inner glow added to both outfits' materials")
    scene.frame_set(50)
    cut_new, cut_old = evaluated_values(target.meshes[0], ATTR_CUT), evaluated_values(base.meshes[0], ATTR_CUT)
    check(cut_new is not None and cut_old is not None and float(cut_new.max()) > 0.9 and float(cut_old.max()) > 0.9
          and float(cut_new.min()) == 0.0, "inner glow: the cut marked on both outfits at frame 50")
    s.layer_enable = True
    s.holo_enable = True  # every spliced node at once: they run in a fixed order, whatever order they were added in
    order = {tuple(chain(m)) for m in glow}
    check(order == {("MMDD Edge Add", "MMDD Holo Mix", "MMDD Inner Mix", "MMDD Layer Mix")},
          "shader nodes spliced in order (%s)" % order)
    s.holo_enable = False
    check(abs(float(s.mask[effect.P_REACH]) - (wave + s.layer_width)) < 1e-4 * wave,
          "undersuit: the mask grows on by its width (%.3f -> %.3f)" % (reach_plain, float(s.mask[effect.P_REACH])))
    scene.frame_set(50)
    layer = evaluated_values(target.meshes[0], ATTR_LAYER)
    check(layer is not None and (layer > 0.99).any() and (layer < 0.01).any(),
          "undersuit: dark at the edge, the final look behind it at frame 50 (%.0f%% dark)"
          % (100.0 * float((layer > 0.5).mean()) if layer is not None else 0.0))
    scene.frame_set(100)
    layer = evaluated_values(target.meshes[0], ATTR_LAYER)
    check(layer is not None and float(layer.max()) == 0.0, "undersuit: the final look everywhere at the end")
    check(not draw_panels(bpy.context), "panels draw with the undersuit and inner glow")
    s.layer_enable, s.inner_glow = False, False
    check(not any(m.get(materials.P_LAYER) or m.get(materials.P_INNER) for m in glow + base_free)
          and abs(float(s.mask[effect.P_REACH]) - reach_plain) < 1e-4 * reach_plain,
          "undersuit and inner glow removed, the mask back to its length")

    # --- symbiote: black veins on the old outfit ahead of the edge, tendrils and strands of goo bound to its
    # triangles (so they stick to the body when it moves) and the goo undersuit on the new outfit
    old_mesh = base.meshes[0]
    s.venom_enable, s.old_surface = True, "VEINS"
    skeleton = venom.skeleton(old_mesh)
    check(skeleton is not None and venom.skeleton(target.meshes[0]) is None, "symbiote: a skeleton on the old outfit")
    if skeleton is not None:
        sk_attrs = skeleton.data.attributes
        check(all(sk_attrs.get(n) is not None for n in VENOM_ATTRS), "the skeleton carries its bindings and timing")
        n_points = len(skeleton.data.vertices)
        kinds = np.zeros(n_points, dtype=np.float32)
        sk_attrs["mmdd_kind"].data.foreach_get("value", kinds)
        index = np.zeros((6, n_points), dtype=np.int32)
        for i, name in enumerate(VENOM_ENDS[0][:3] + VENOM_ENDS[1][:3]):
            sk_attrs[name].data.foreach_get("value", index[i])
        weights = np.zeros((2, n_points * 3), dtype=np.float32)
        for i, end in enumerate(VENOM_ENDS):
            sk_attrs[end[3]].data.foreach_get("vector", weights[i])
        check(int((kinds < 0.5).sum()) > 100 and int(((kinds > 0.5) & (kinds < 1.5)).sum()) >= 3 * 8,
              "tendrils (%d points) and strands (%d points)" % ((kinds < 0.5).sum(),
                                                              ((kinds > 0.5) & (kinds < 1.5)).sum()))
        check(int((kinds > 1.5).sum()) > 0 and len(skeleton.data.polygons) > 0,
              "webs in the forks of the tendrils (%d points, %d faces)" % ((kinds > 1.5).sum(),
                                                                          len(skeleton.data.polygons)))
        check(index.min() >= 0 and index.max() < len(old_mesh.data.vertices)
              and float(np.abs(weights.reshape(2, -1, 3).sum(axis=2) - 1.0).max()) < 1e-4,
              "every point bound to a triangle of the old outfit")
    veined = set(effect._glow_materials(old_mesh, s))
    check(veined and all(m.get(materials.P_SURFACE) == "VEINS" for m in veined)
          and not any(m.get(materials.P_SURFACE) for m in glow),
          "veins added to the old outfit's materials (%d), not to locked parts or the new outfit" % len(veined))
    scene.frame_set(1)
    check(len(goo_points(old_mesh)) == 0, "symbiote: no goo at frame 1")
    busiest, most = None, 0
    for f in range(10, 100, 5):
        scene.frame_set(f)
        count = len(goo_points(old_mesh))
        if count > most:
            busiest, most = f, count
    check(busiest is not None, "tendrils grow while the edge passes (most at frame %s: %d vertices)" % (busiest, most))
    if busiest is not None:
        scene.frame_set(busiest)
        near = float(np.median(surface_distance(goo_points(old_mesh), old_mesh)))
        pb = base.armature.pose.bones.get("腕.L") or base.armature.pose.bones.get("左腕")
        pb.matrix_basis = Matrix.Rotation(math.radians(60.0), 4, "X")
        bpy.context.view_layer.update()
        lifted = float(np.median(surface_distance(goo_points(old_mesh), old_mesh)))
        pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        check(near < 2.0 * s.venom_thickness and lifted < 2.0 * s.venom_thickness,
              "the goo lies on the body, also with the arm lifted (median distance %.3f / %.3f, radius %.3f)"
              % (near, lifted, s.venom_thickness))
        with_webs = len(goo_points(old_mesh))
        s.venom_webs = False
        without_webs = len(goo_points(old_mesh))
        s.venom_webs = True
        check(with_webs > without_webs, "the webs add goo between the tendrils at frame %d (%d vs %d vertices)"
              % (busiest, with_webs, without_webs))
        vein = evaluated_values(old_mesh, ATTR_AHEAD)
        check(vein is not None and float(vein.max()) > 0.9 and float(vein.min()) == 0.0,
              "veins marked ahead of the edge at frame %d" % busiest)
    scene.frame_set(100)
    check(len(goo_points(old_mesh)) == 0, "every tendril and strand gone at the end")
    s.layer_enable, s.layer_style = True, "GOO"
    styles = [m.node_tree.nodes.get(materials.LAYER + " Style") for m in glow]
    target_mod = our_modifiers(target.meshes[0])[0]
    goo_input = target_mod[input_identifiers(target_mod.node_group)["Goo"]]
    check(all(n is not None and n.outputs[0].default_value == 1.0 for n in styles) and goo_input,
          "goo undersuit: the layer's goo style and the lumpy edge")
    check({tuple(chain(m)) for m in veined} == {("MMDD Surface Mix",)},
          "veins spliced into the old outfit (%s)" % {tuple(chain(m)) for m in veined})
    # liquid metal (T-1000): the goo turns to polished metal everywhere, the tendrils, the goo undersuit and the veins
    s.venom_metallic = 1.0
    goo_bsdfs = [bpy.data.materials[materials.GOO_MATERIAL].node_tree.nodes.get("MMDD Goo BSDF")]
    goo_bsdfs += [m.node_tree.nodes.get(materials.LAYER + " Goo BSDF") for m in glow]
    goo_bsdfs += [m.node_tree.nodes.get(materials.SURFACE + " Goo BSDF") for m in veined]
    check(all(n is not None and n.inputs["Metallic"].default_value == 1.0 for n in goo_bsdfs),
          "liquid metal: every goo shader metallic (%d)" % len(goo_bsdfs))
    s.venom_metallic = 0.0
    skeleton = venom.skeleton(old_mesh)  # (traced again with the webs off and on)
    points = len(skeleton.data.vertices) if skeleton is not None else 0
    s.venom_tendrils += 60
    skeleton = venom.skeleton(old_mesh)
    check(skeleton is not None and len(skeleton.data.vertices) > points,
          "more tendrils: traced again (%d -> %d points)" % (points, len(skeleton.data.vertices) if skeleton else 0))
    s.venom_tendrils -= 60
    # Strands are also looked for in the poses the body takes while it transforms: with the left upper arm coming down
    # against the body and going back, some are bound where surfaces face each other in a pose, farther apart at rest.
    gaps, lengths = strand_gaps(venom.skeleton(old_mesh), old_mesh)
    check(len(gaps) > 0 and float(np.abs(gaps - lengths).max()) < 0.01 * float(lengths.max()),
          "without motion every strand is found on the rest pose (%d)" % len(gaps))
    pb = base.armature.pose.bones.get("腕.L") or base.armature.pose.bones.get("左腕")
    arm_ad = base.armature.animation_data
    arm_action = arm_ad.action if arm_ad is not None else None
    for frame, angle in ((1, 0.0), (50, -40.0), (100, 0.0)):  # (about its X axis: down to the side)
        pb.matrix_basis = Matrix.Rotation(math.radians(angle), 4, "X")
        pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", frame=frame)
    scene.frame_set(100)
    s.venom_strands += 1  # traced again, now with the poses
    gaps, lengths = strand_gaps(venom.skeleton(old_mesh), old_mesh)
    moved = np.abs(gaps - lengths) > 0.25 * lengths
    check(len(gaps) > 0 and int(moved.sum()) >= 2 and scene.frame_current == 100,
          "strands found in the poses: %d of %d bound where the arm comes down (the frame put back)"
          % (int(moved.sum()), len(gaps)))
    if arm_action is None:
        base.armature.animation_data_clear()
    else:
        base.armature.animation_data.action = arm_action
    pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    s.venom_strands -= 1
    check(not draw_panels(bpy.context), "panels draw with the symbiote")
    s.venom_enable = False
    scene.frame_set(busiest or 50)
    check(venom.skeleton(old_mesh) is None and not bpy.data.objects.get(venom.SKELETON)
          and len(goo_points(old_mesh)) == 0, "symbiote off: skeleton and goo gone")
    s.layer_enable, s.layer_style = False, "NANO"

    # --- frost: the old outfit freezes ahead of the edge and ice crystals grow out of it, gone where the edge passed;
    # char: it smoulders instead
    s.old_surface = "FROST"
    check(all(m.get(materials.P_SURFACE) == "FROST" for m in veined)
          and all(m.node_tree.nodes.get(materials.SURFACE + " Ice BSDF") for m in veined)
          and not any(m.node_tree.nodes.get(materials.SURFACE + " Veins") for m in veined),
          "frost replaces the veins in the old outfit's materials")
    crystal_shape = bpy.data.objects.get(particles.CRYSTAL)
    check(crystal_shape is not None and crystal_shape.data.materials[0].name == materials.ICE_MATERIAL,
          "ice crystal shape (ice material)")
    grown = {}
    for f in (1, busiest or 50, 100):
        scene.frame_set(f)
        grown[f] = instance_count(old_mesh)
    check(grown[1] == 0 and grown[busiest or 50] > 0 and grown[100] == 0,
          "ice crystals grow ahead of the edge and are gone where it passed (%s)" % grown)
    # clear ice: between the white frost the light goes through, so EEVEE refracts through those materials; the
    # crystals and shards are clear glass
    clarity = [m.node_tree.nodes.get(materials.SURFACE + " Clarity") for m in veined]
    check(all(n is not None and abs(n.outputs[0].default_value - s.ice_clarity) < 1e-6 for n in clarity)
          and all(materials.P_REFRACT in m for m in veined), "clear ice: refraction on in %d materials" % len(veined))
    ice = bpy.data.materials.get(materials.ICE_MATERIAL)
    ice_bsdf = ice.node_tree.nodes.get("MMDD_BSDF") if ice is not None else None
    transmission = None
    if ice_bsdf is not None:
        transmission = ice_bsdf.inputs.get("Transmission Weight") or ice_bsdf.inputs.get("Transmission")
    check(transmission is not None and transmission.default_value == 1.0
          and (getattr(ice, "use_raytrace_refraction", False) or getattr(ice, "use_screen_refraction", False)),
          "the crystals and shards are clear glass")
    s.ice_clarity = 0.0
    check(not any(materials.P_REFRACT in m for m in veined), "milky ice: the materials' refraction put back")
    s.ice_clarity = 0.5
    # Freeze, then shatter: the old outfit stays whole while the frost covers it and goes all at once when the wave is
    # done (the new outfit forms underneath meanwhile).
    s.exit_timing = "AT_ONCE"
    whole, frozen, drop = None, 0.0, None
    full = len(old_mesh.data.vertices)
    for f in range(5, 101, 5):
        scene.frame_set(f)
        count = evaluated_counts(old_mesh)
        if count == full:
            whole = f
            ahead = evaluated_values(old_mesh, ATTR_AHEAD)
            frozen = float(np.median(ahead)) if ahead is not None else 0.0
        elif drop is None and count < 0.5 * full:
            drop = f
    scene.frame_set(whole or 1)
    crystals_then = instance_count(old_mesh)
    check(whole is not None and whole >= 70 and frozen > 0.9 and crystals_then > 0,
          "frozen over before it goes: whole until frame %s, frost %.2f, %d crystals" % (whole, frozen, crystals_then))
    check(drop is not None and whole is not None and drop - whole <= 15,
          "then it shatters all at once (whole at frame %s, mostly gone at %s)" % (whole, drop))
    scene.frame_set(100)
    check(evaluated_counts(target.meshes[0]) > 0 and instance_count(old_mesh) == 0,
          "the new outfit there at the end, the crystals gone")
    s.exit_timing = "EDGE"
    s.ice_crystals = 0
    scene.frame_set(busiest or 50)
    check(instance_count(old_mesh) == 0, "no crystals with the count at 0")
    s.ice_crystals = 400
    s.old_surface = "CHAR"
    check(all(m.get(materials.P_SURFACE) == "CHAR" and m.node_tree.nodes.get(materials.SURFACE + " Char BSDF")
              for m in veined), "char replaces the frost")
    scene.frame_set(busiest or 50)
    check(instance_count(old_mesh) == 0, "no crystals without frost")
    s.old_surface = "NONE"
    check(not any(m.get(materials.P_SURFACE) for m in base_free)
          and evaluated_values(old_mesh, ATTR_AHEAD) is None, "surface effect off: materials and attribute clean")

    # --- pieces: the new outfit flies in, the old one is cast off in chunks
    s.entrance, s.exit_style = "ASSEMBLE", "CHUNKS"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build fly-in + cast-off")
    check(not draw_panels(bpy.context), "panels draw with fly-in and cast-off")
    scene.frame_set(1)
    check(evaluated_faces_and_edge(target.meshes[0])[0] == 0, "fly-in: no pieces at frame 1")
    check(evaluated_faces_and_edge(base.meshes[0])[0] == len(base.meshes[0].data.polygons),
          "cast-off: old outfit whole at frame 1")
    scene.frame_set(40)
    faces, glow_top = evaluated_faces_and_edge(base.meshes[0])
    check(0 < faces < len(base.meshes[0].data.polygons) and glow_top > 0.0, "cast-off: chunks flying at frame 40")
    scene.frame_set(100)
    check(evaluated_faces_and_edge(target.meshes[0])[0] == grown_faces,
          "fly-in: every piece landed (%d faces)" % grown_faces)
    check(evaluated_faces_and_edge(base.meshes[0])[0] == locked_faces(base.meshes[0]),
          "cast-off: only the shared parts left")

    # --- front and back halves (Kamen Rider Build): printed from the feet up in frames in front of and behind the body,
    # sliding in and clamping shut, when the old outfit goes
    s.entrance, s.exit_style = "CLAMP", "SHRINK"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with the clamping halves")
    check(not draw_panels(bpy.context), "panels draw with the clamping halves")
    closing = effect.CLAMP_AT * float(s.mask[effect.P_WAVE])
    moments = {}
    for f in range(1, 101):
        scene.frame_set(f)
        progress = sum(s.mask.matrix_world.to_scale()) / 3.0 / closing
        for name, at in (("printing", 0.15), ("sliding", 0.6), ("closed", 1.12)):
            if name not in moments and progress >= at:
                moments[name] = f
    check(len(moments) == 3, "the halves print, slide and close within the frames (%s)" % moments)
    new_mesh, old_mesh = target.meshes[0], base.meshes[0]
    spans = {}
    for name, f in moments.items():
        scene.frame_set(f)
        suit = material_points(new_mesh, effect.WIRE_MATERIAL, others=True)
        spans[name] = (len(suit), round(float(suit[:, 1].min()), 2) if len(suit) else 0.0,
                       round(float(suit[:, 1].max()), 2) if len(suit) else 0.0,
                       len(material_points(new_mesh, effect.WIRE_MATERIAL)), evaluated_counts(old_mesh))
    scene.frame_set(100)  # long closed: where the halves sit on the body
    rest_y = material_points(new_mesh, effect.WIRE_MATERIAL, others=True)[:, 1]
    gap = s.clamp_distance
    if len(spans) == 3:
        printing, sliding, closed = spans["printing"], spans["sliding"], spans["closed"]
        check(0 < printing[0] < sliding[0] and printing[3] > 0, "printing: part of the halves in their frames %s"
              % (printing,))
        check(sliding[1] < rest_y.min() - 0.3 * gap and sliding[2] > rest_y.max() + 0.3 * gap and sliding[3] > 0,
              "sliding: the halves still apart, in front of and behind the body (%s, body %.2f .. %.2f)"
              % (sliding, rest_y.min(), rest_y.max()))
        check(abs(closed[1] - rest_y.min()) < 0.02 * gap and abs(closed[2] - rest_y.max()) < 0.02 * gap
              and closed[3] == 0, "closed: the halves on the body, the frames gone %s" % (closed,))
        check(printing[4] == len(old_mesh.data.vertices) and sliding[4] == len(old_mesh.data.vertices)
              and closed[4] < sliding[4], "the old outfit stays until the halves close (%s)"
              % [spans[k][4] for k in ("printing", "sliding", "closed")])

    # --- converging ghosts (Kamen Rider Decade): see-through copies stand around the body and converge into it; the
    # outfit is there when they meet, and the old one goes
    s.entrance, s.holo_enable = "GHOSTS", True
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with converging ghosts")
    check(not draw_panels(bpy.context), "panels draw with the ghosts")
    closing = effect.CLAMP_AT * float(s.mask[effect.P_WAVE])
    seen = {}
    for f in range(1, 101):
        scene.frame_set(f)
        progress = sum(s.mask.matrix_world.to_scale()) / 3.0 / closing
        for name, at in (("apart", 0.3), ("closer", 0.8), ("met", 1.05)):
            if name not in seen and progress >= at:
                spots = instance_positions(new_mesh)
                spread = float(np.linalg.norm(spots - np.array(new_mesh.matrix_world.translation), axis=1).mean()) \
                    if len(spots) else 0.0
                seen[name] = (len(spots), round(spread, 2), evaluated_counts(new_mesh), evaluated_counts(old_mesh))
    check(len(seen) == 3, "the ghosts gather and meet within the frames (%s)" % seen)
    if len(seen) == 3:
        apart, closer, met = seen["apart"], seen["closer"], seen["met"]
        check(apart[0] == s.ghost_count and closer[0] == s.ghost_count and apart[1] > closer[1] > 0.0,
              "%d ghosts drawing in (%s, %s)" % (s.ghost_count, apart, closer))
        check(apart[2] == 0 and closer[2] == 0 and met[0] == 0 and met[2] > 0,
              "the outfit itself only once they met, the ghosts gone then (%s)" % (met,))
        check(apart[3] == closer[3] == len(old_mesh.data.vertices) and met[3] < closer[3],
              "the old outfit goes when they meet (%s)" % [seen[k][3] for k in ("apart", "closer", "met")])
    s.holo_enable = False
    s.entrance, s.exit_style = "GROW", "SHRINK"

    # --- flipping scales (Mystique): both outfits break into scales that turn over where the edge passes, the old
    # outfit the first half of each turn (flat to edge-on), the new one the second (edge-on to flat), in step; they
    # stand up off the body as they turn
    wire_was, s.wire_enable = s.wire_enable, False
    s.entrance = "SCALES"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with flipping scales")
    check(not draw_panels(bpy.context), "panels draw with the scales")
    scene.frame_set(1)
    check(evaluated_counts(new_mesh) == 0 and evaluated_counts(old_mesh) == len(old_mesh.data.vertices),
          "scales: nothing turned at frame 1")
    standing = {}
    for f in range(10, 95, 5):
        scene.frame_set(f)
        standing[f] = tuple(int((world_vertices(ob)[1] > 0.75).sum()) for ob in (old_mesh, new_mesh))
    busiest = max(standing, key=lambda f: min(standing[f]))
    check(min(standing[busiest]) > 30, "scales standing edge-on in both outfits at frame %d %s"
          % (busiest, standing[busiest]))
    scene.frame_set(busiest)
    old_co, old_glint = world_vertices(old_mesh)
    up_old = old_co[old_glint > 0.75]
    lying = old_co[old_glint == 0.0]
    rise = float(np.median(surface_distance(up_old[::max(1, len(up_old) // 400)], old_mesh))) if len(up_old) else 0.0
    flat = float(np.median(surface_distance(lying[::max(1, len(lying) // 400)], old_mesh))) if len(lying) else 1.0
    check(rise > 0.15 * s.scale_size and flat < 0.01 * s.scale_size,
          "scales stand up off the body as they turn (median %.3f), the rest lies on it (%.4f; scale size %.3f)"
          % (rise, flat, s.scale_size))
    # In step: a scale is timed by its site, the same in both outfits. Where they lie on top of each other on the body,
    # the old one goes as the new one comes, so they never both sit still there: the old one not turned yet while the
    # new one has finished turning.
    old_pose, new_pose = skinned(old_mesh), skinned(new_mesh)
    free_new = np.nonzero(free_vertices(new_mesh))[0]  # (locked parts never turn)
    tree = KDTree(len(free_new))
    for i in free_new:
        tree.insert(Vector(new_pose[i]), int(i))
    tree.balance()
    free_old = free_vertices(old_mesh)
    # (a seam vertex of a locked part sits on the same spot and stays: leave those spots out)
    locked_spots = set(map(tuple, np.round(old_pose[~free_old], 3)))
    picks = np.random.default_rng(5).choice(np.nonzero(free_old)[0], size=min(20000, int(free_old.sum())),
                                            replace=False)
    pairs = [(tuple(np.round(old_pose[i], 3)), tuple(np.round(new_pose[j], 3))) for i in picks
             for (_co, j, dist) in [tree.find(Vector(old_pose[i]))] if dist < 0.05 * s.scale_size]
    pairs = [(a, c) for a, c in pairs if a not in locked_spots]
    both, seen = 0, 0
    for f in range(10, 95, 5):
        scene.frame_set(f)
        still_old = set(map(tuple, np.round(evaluated_positions(old_mesh), 3)))
        still_new = set(map(tuple, np.round(evaluated_positions(new_mesh), 3)))
        for a, c in pairs:
            seen += a in still_old or c in still_new
            both += a in still_old and c in still_new
    check(len(pairs) > 100 and seen > 0 and both <= 0.002 * seen,
          "the old and the new half of every turn in step: where the outfits lie on top of each other (%d spots) they "
          "never both sit still across the edge (%d of %d)" % (len(pairs), both, seen))
    scene.frame_set(100)
    check(evaluated_faces_and_edge(new_mesh)[0] == grown_faces
          and evaluated_faces_and_edge(old_mesh)[0] == locked_faces(old_mesh),
          "scales: the new outfit whole, the old one gone at the end")
    s.entrance, s.wire_enable = "GROW", wire_was

    # --- 1.8: new particle shapes: music notes, playing cards, feathers, bats and ink drops, each with its material;
    # bats flap like the butterflies, notes stand facing the front
    saved = {key_: getattr(s, key_) for key_ in ("path", "seeds", "exit_style", "particles", "wire_enable", "easing")}
    s.wire_enable = False
    s.path, s.exit_style, s.particles = "SPHERE", "FRAGMENTS", "NOTE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with music notes")
    mod = our_modifiers(old_mesh)[0]
    ids = input_identifiers(mod.node_group)
    for kind, mat_name in (("NOTE", materials.PARTICLE_MATERIAL), ("CARD", materials.CARD_MATERIAL),
                           ("FEATHER", materials.PARTICLE_MATERIAL), ("BAT", materials.BAT_MATERIAL),
                           ("INK", materials.INK_MATERIAL), ("GLYPH", materials.PARTICLE_MATERIAL),
                           ("PEBBLE", materials.PEBBLE_MATERIAL)):
        s.particles = kind
        scene.frame_set(51)
        scene.frame_set(50)
        shape = bpy.data.objects.get(particles.NAMES[kind])
        check(instance_count(old_mesh) > 0 and shape is not None and shape.data.materials[0].name == mat_name,
              "%s released at frame 50 (%d), %s" % (kind.lower(), instance_count(old_mesh), mat_name))
        if kind in ("NOTE", "BAT"):
            check(bool(mod[ids["Flap"]]) == (kind == "BAT") and bool(mod[ids["Upright"]]) == (kind == "NOTE"),
                  "bats flap, notes stand facing the front (%s)" % kind.lower())
        if kind == "GLYPH":  # (1.9) twelve glyphs in one shape, one shown at a time, standing facing the front
            variant = shape.data.attributes.get(ATTR_VARIANT)
            kinds = np.zeros(len(shape.data.polygons), dtype=np.int32)
            if variant is not None:
                variant.data.foreach_get("value", kinds)
            check(variant is not None and set(kinds.tolist()) == set(range(GLYPHS)) and mod[ids["Glyphs"]]
                  and mod[ids["Upright"]], "code glyphs: %d glyphs in the shape, picked one at a time, upright"
                  % len(set(kinds.tolist())))
    s.exit_style, s.particles = "SHRINK", "NONE"

    # --- sweeps across the body along the model's own axes, and the spiral (at one height the change goes round the
    # body, a turn per pitch)
    for path, axis in (("LEFT_RIGHT", 0), ("FRONT_BACK", 1)):
        s.path = path
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build " + path.lower())
        coord = rest_points_world(old_mesh)[:, axis]
        check(float(np.corrcoef(arrival_values(old_mesh), coord)[0, 1]) > 0.999
              and s.mask.empty_display_type == "SINGLE_ARROW", "%s follows the model's %s axis"
              % (path.lower(), "XY"[axis]))
    s.path = "SPIRAL"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the spiral")
    pts = rest_points_world(old_mesh)
    turn_of = arrival_values(old_mesh) * effect._object_scale(old_mesh)
    centre_ = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
    band = np.abs(pts[:, 2] - np.median(pts[:, 2])) < 0.01 * height
    angle = np.mod(np.arctan2(pts[band, 0] - centre_[0], -(pts[band, 1] - centre_[1])), 2.0 * math.pi)
    spread = float(turn_of[band].max() - turn_of[band].min())
    # at one height the arrival is a sawtooth of the angle; where it jumps depends on the height, so correlate it with
    # the angle as a circular quantity (circular-linear correlation)
    rc, rs, cs = (float(np.corrcoef(turn_of[band], np.cos(angle))[0, 1]),
                  float(np.corrcoef(turn_of[band], np.sin(angle))[0, 1]),
                  float(np.corrcoef(np.cos(angle), np.sin(angle))[0, 1]))
    circular = math.sqrt(max((rc * rc + rs * rs - 2.0 * rc * rs * cs) / (1.0 - cs * cs), 0.0))
    check(band.sum() > 50 and circular > 0.4 and 0.7 * s.spiral_pitch < spread < 1.3 * s.spiral_pitch,
          "spiral: at one height the change goes round the body (circular correlation %.2f, spread %.2f, pitch %.2f)"
          % (circular, spread, s.spiral_pitch))

    # --- the front's decoration: a magic circle, sparks, a panel, TV static on a sweep, all at the front, gone before
    # and after; a comet circling up the spiral. None for the sphere.
    s.path, s.ring_enable, s.ring_style = "LEFT_RIGHT", True, "MAGIC"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build a sweep with a ring")
    check(not draw_panels(bpy.context), "panels draw with a ring")
    loops = rings.ring_objects(s.mask)
    check(len(loops) == 1, "a ring object for the sweep")
    layout = s.mask[effect.P_LAYOUT].to_dict()
    start, axis_ = np.array(layout["start"]), np.array(layout["axis"])
    for style in RING_STYLES[:4]:
        s.ring_style = style
        drawn = {}
        for f in (1, 50, 100):
            scene.frame_set(f)
            drawn[f] = world_vertices(loops[0])[0]
            if f == 50:
                front = s.mask.scale.x - layout["lead"]
        placed = len(drawn[50]) > 0 and abs(float(np.median((drawn[50] - start) @ axis_)) - front) < 0.02 * height
        check(placed and len(drawn[1]) == 0 and len(drawn[100]) == 0,
              "%s ring at the front at frame 50, gone at frames 1 and 100" % style.lower())
    s.path, s.ring_style = "SPIRAL", "COMET"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the spiral with the comet")
    loops = rings.ring_objects(s.mask)
    heads = []
    for f in (40, 41, 60):
        scene.frame_set(f)
        heads.append(world_vertices(loops[0])[0].mean(axis=0))
    check(np.linalg.norm(heads[1][:2] - heads[0][:2]) > 0.05 and heads[2][2] > heads[0][2] + 0.1 * height,
          "the comet circles the body and climbs (%.2f round, %.2f up)"
          % (np.linalg.norm(heads[1][:2] - heads[0][:2]), heads[2][2] - heads[0][2]))
    s.ring_enable = False
    check(not rings.ring_objects(s.mask), "ring removed when switched off")
    s.ring_enable, s.path = True, "SPHERE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"} and not rings.ring_objects(s.mask),
          "no ring for the sphere (it needs a sweep or the spiral)")
    s.ring_enable = False

    # --- sucked into the brooch: the flakes gather at the start point on the chest instead of blowing away
    def gathered(exit_style):
        s.exit_style = exit_style
        bpy.ops.mmd_disperse.build()
        brooch = np.array(s.mask[effect.P_BROOCH])
        counts = []
        for f in range(30, 90, 6):
            scene.frame_set(f)
            co, glow = world_vertices(old_mesh)
            counts.append(int(((np.linalg.norm(co - brooch, axis=1) < 0.06 * height) & (glow > 0.3)).sum()))
        return counts

    s.path = "SURFACE"
    blown, sucked = gathered("FRAGMENTS"), gathered("SUCK")
    check(max(sucked) > 100 and max(sucked) > 3 * max(max(blown), 1),
          "sucked in: glowing flakes gather at the brooch (%d, blown away %d)" % (max(sucked), max(blown)))
    s.exit_style, s.path = "SHRINK", "SPHERE"

    # --- the evolution flash: no front; the outfits show in turn, faster and faster, then the new one stays; the old
    # outfit's locked parts glow too
    s.entrance = "EVOLVE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the evolution flash")
    check(not draw_panels(bpy.context), "panels draw with the evolution flash")
    shown = []
    for f in range(1, 101):
        scene.frame_set(f)
        shown.append(evaluated_counts(new_mesh) > 0)
    flips = [i for i, (a, b) in enumerate(zip(shown, shown[1:])) if a != b]
    check(len(flips) >= 8 and not shown[0] and shown[-1] and flips[1] - flips[0] > flips[-1] - flips[-2],
          "evolution: the outfits flash in turn, faster and faster (%d flips), the new one stays" % len(flips))
    check(any(m.get(materials.P_GLOW) for m in effect._glow_materials(old_mesh, s, True)),
          "evolution: the locked parts glow too")

    # --- smoke puff: the new outfit is there at the moment, a puff of smoke around it then
    s.entrance = "POOF"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the smoke puff")
    seen = []
    for f in range(1, 101, 3):
        scene.frame_set(f)
        seen.append((evaluated_counts(new_mesh) > 0, instance_count(new_mesh)))
    swap = next((i for i, (there, _n) in enumerate(seen) if there), None)
    check(swap is not None and not any(there for there, _n in seen[:swap]) and all(there for there, _n in seen[swap:])
          and seen[swap][1] > 20 and seen[0][1] == 0 and seen[-1][1] == 0,
          "smoke puff: the new outfit appears at once inside a puff of smoke (%s)"
          % (seen[swap][1] if swap is not None else None))

    # --- rising from the shadow: the old outfit sinks into its shadow on the floor, the new one stands up out of it;
    # every material can turn black
    s.entrance = "SHADOW"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build rising from the shadow")
    tops = []
    for f in range(1, 101, 3):
        scene.frame_set(f)
        both = np.concatenate([world_vertices(ob)[0] for ob in (old_mesh, new_mesh)])
        tops.append(float(both[:, 2].max() - both[:, 2].min()) if len(both) else 0.0)
    low = min(tops)
    check(tops[0] > 0.9 * height and low < 0.02 * height and tops[-1] > 0.9 * height,
          "shadow: standing, then flat on the floor (%.3f), then standing again" % low)
    check(all(sl.material.get(materials.P_SHADOW) for sl in old_mesh.material_slots if sl.material)
          and evaluated_values(new_mesh, ATTR_SHADOW) is not None, "shadow: every material can turn black")
    s.entrance = "GROW"
    check(not any(sl.material.get(materials.P_SHADOW) for sl in old_mesh.material_slots if sl.material),
          "shadow: the black shadow taken out of the materials again")

    # --- line art and ink wash: the new outfit drawn ahead of the edge (line art), outlined, its colours coming in
    # behind it; the old outfit's ink wash surface
    s.path = "UP"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build a sweep for the drawings")
    scene.frame_set(50)
    plain = evaluated_counts(new_mesh)
    s.paint_style = "LINEART"
    scene.frame_set(51)
    scene.frame_set(50)
    paint = evaluated_values(new_mesh, ATTR_PAINT)
    deps = bpy.context.evaluated_depsgraph_get()
    ev = new_mesh.evaluated_get(deps)
    used = {ev.material_slots[p.material_index].material.name for p in ev.data.polygons
            if p.material_index < len(ev.material_slots) and ev.material_slots[p.material_index].material}
    check(evaluated_counts(new_mesh) > plain and paint is not None and paint.min() < 0.05 and paint.max() > 0.95
          and materials.OUTLINE_MATERIAL in used, "line art: drawn ahead of the edge (%d > %d vertices), outlined"
          % (evaluated_counts(new_mesh), plain))
    painted = list(effect._glow_materials(new_mesh, s))
    check(painted and all(m.get(materials.P_PAINT) for m in painted)
          and all(materials.PAINT + " Mix" in chain(m) for m in painted[:3]),
          "line art: the drawing injected into %d materials"
          % len(painted))
    check(not draw_panels(bpy.context), "panels draw with line art")
    s.paint_style, s.old_surface = "INK", "INK"
    inked = list(effect._glow_materials(old_mesh, s))
    check(all(m.get(materials.P_SURFACE) == "INK" for m in inked), "ink wash: the old outfit turns into ink")
    s.paint_style, s.old_surface = "NONE", "NONE"
    check(not any(m.get(materials.P_PAINT) for m in painted) and not any(m.get(materials.P_SURFACE) for m in inked),
          "drawings taken out of the materials again")

    # --- Mark 50: the reactor (the suit around the start point there first, glowing) and the armour plates rising
    # behind the edge (gone at the end)
    s.path, s.seeds, s.reactor = "SURFACE", "ORIGIN", True
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with the reactor")
    early = []
    for f in range(2, 16):
        scene.frame_set(f)
        co, glow = world_vertices(new_mesh)
        early.append((len(co), int((glow > 0.9).sum())))
    check(any(0 < n < 0.1 * len(new_mesh.data.vertices) and bright > 0 for n, bright in early),
          "reactor: a small glowing patch of the suit first %s" % early[::3])
    s.reactor = False
    scene.frame_set(50)
    flat_co = evaluated_positions(new_mesh)
    s.plates = True
    scene.frame_set(51)
    scene.frame_set(50)
    raised_co = evaluated_positions(new_mesh)
    tree = KDTree(len(flat_co))
    for i, v in enumerate(flat_co):
        tree.insert(Vector(v), i)
    tree.balance()
    off = np.array([tree.find(Vector(v))[2] for v in raised_co[::max(1, len(raised_co) // 20000)]])
    check(int((off > 0.3 * s.plate_lift).sum()) > 20, "plates rise off the suit behind the edge (%d vertices)"
          % int((off > 0.3 * s.plate_lift).sum()))
    scene.frame_set(100)
    check(evaluated_faces_and_edge(new_mesh)[0] == grown_faces, "plates: settled at the end")
    s.plates = False

    # --- 1.9: lightning: a bolt comes down from high above onto the start point for the first frames (the white flash
    # flashes then), then arcs of electricity crackle along the edge, new ones every frame
    s.path, s.seeds, s.arc_enable, s.arc_strike = "SURFACE", "ORIGIN", True, True
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with lightning")
    check(not draw_panels(bpy.context), "panels draw with lightning")
    check(bpy.ops.mmd_disperse.add_white_flash() == {"FINISHED"}, "white flash added for the strike")
    body_top = float(rest_points_world(new_mesh)[:, 2].max())
    bolt = {}
    for f in (1, 2, 4, 14):
        scene.frame_set(f)
        pts = material_points(new_mesh, materials.ARC_MATERIAL)
        bolt[f] = (len(pts), round(float(pts[:, 2].max()), 2) if len(pts) else 0.0, round(white_flash_value(scene), 3))
    check(bolt[1][0] == 0 and bolt[2][0] > 0 and bolt[2][1] > body_top + 0.5 * height and bolt[4][1] > body_top
          and 0 < bolt[14][0] and bolt[14][1] < body_top, "lightning: a bolt from high above for the first frames, "
          "then arcs on the body %s (top of the body %.2f)" % (bolt, body_top))
    check(bolt[1][2] == 0.0 and bolt[2][2] > 0.3 and bolt[14][2] == 0.0,
          "lightning: the picture flashes white as it strikes %s" % [bolt[f][2] for f in (1, 2, 4, 14)])
    mod = our_modifiers(new_mesh)[0]
    reach = (mod[input_identifiers(mod.node_group)["Arc Reach"]] + 0.5 * mod[input_identifiers(mod.node_group)[
        "Arc Length"]] + mod[input_identifiers(mod.node_group)["Noise Amount"]]) * effect._object_scale(new_mesh)
    rest_tree = KDTree(len(new_mesh.data.vertices))
    mw = np.array(new_mesh.matrix_world)
    for i, v in enumerate(skinned(new_mesh) @ mw[:3, :3].T + mw[:3, 3]):
        rest_tree.insert(Vector(v), i)
    rest_tree.balance()
    arrival_new = arrival_values(new_mesh) * effect._object_scale(new_mesh)
    shots = {}
    for f in (50, 51):
        scene.frame_set(f)
        pts = material_points(new_mesh, materials.ARC_MATERIAL)
        off = np.array([abs(arrival_new[rest_tree.find(Vector(p))[1]] - s.mask.scale.x) for p in pts[::7]])
        shots[f] = (pts, float(np.median(off)) if len(off) else np.inf)
    check(len(shots[50][0]) > 200 and shots[50][1] < reach and len(shots[51][0]) > 200 and shots[51][1] < reach,
          "lightning: arcs along the edge (median %.3f from it, %.3f allowed)" % (shots[50][1], reach))
    check(len(shots[50][0]) != len(shots[51][0]) or not np.allclose(shots[50][0], shots[51][0]),
          "lightning: new arcs every frame (%d, %d vertices)" % (len(shots[50][0]), len(shots[51][0])))
    s.arc_enable = False
    scene.frame_set(50)
    check(len(material_points(new_mesh, materials.ARC_MATERIAL)) == 0, "lightning off: no arcs")

    # --- 1.9: the digital rain: code rains down the old outfit ahead of the edge and the new one behind it (both carry
    # the frame for their materials to scroll it)
    s.path, s.old_surface, s.paint_style, s.exit_style = "DOWN", "CODE", "CODE", "FRAGMENTS"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the digital rain")
    check(not draw_panels(bpy.context), "panels draw with the digital rain")
    scene.frame_set(50)
    frames = [evaluated_values(ob, ATTR_FRAME) for ob in (old_mesh, new_mesh)]
    check(all(v is not None and len(v) and abs(float(v.mean()) - 50.0) < 1e-3 for v in frames),
          "digital rain: both outfits carry the frame for their code")
    coded = list(effect._glow_materials(old_mesh, s))
    drawn = list(effect._glow_materials(new_mesh, s))
    check(all(m.get(materials.P_SURFACE) == "CODE" and m.node_tree.nodes.get(materials.SURFACE + " Code Scale")
              for m in coded)
          and all(m.node_tree.nodes.get(materials.PAINT + " Code Scale") is not None
                  and m.node_tree.nodes[materials.PAINT + " Style"].outputs[0].default_value == 2.0 for m in drawn),
          "digital rain: in the old outfit's surface (%d) and the new outfit's drawing (%d)" % (len(coded), len(drawn)))
    s.old_surface, s.paint_style, s.exit_style = "NONE", "NONE", "SHRINK"
    check(not any(m.get(materials.P_PAINT) for m in drawn) and evaluated_values(old_mesh, ATTR_FRAME) is None,
          "digital rain taken out again")

    # --- 1.9: stone, gold and silk over the old outfit; going all at once under them, the new outfit waits for that
    # moment (it would show through as it grows); the silk swells the old outfit out and silk threads wind round it
    s.path, s.exit_timing = "UP", "AT_ONCE"
    for style, node in (("STONE", " Stone BSDF"), ("GOLD", " Gold BSDF"), ("SILK", " Silk BSDF")):
        s.old_surface = style
        check(all(m.get(materials.P_SURFACE) == style and m.node_tree.nodes.get(materials.SURFACE + node)
                  for m in coded), "%s over the old outfit's materials" % style.lower())
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the silk cocoon")
    check(not draw_panels(bpy.context), "panels draw with the silk cocoon")
    full = len(old_mesh.data.vertices)
    timing = []
    for f in range(5, 101, 5):
        scene.frame_set(f)
        timing.append((f, evaluated_counts(old_mesh), evaluated_counts(new_mesh)))
    goes = next((f for f, o, _n in timing if o < full), None)
    comes = next((f for f, _o, n in timing if n > 0), None)
    check(goes is not None and comes is not None and abs(goes - comes) <= 5 and goes >= 60,
          "under the silk the new outfit comes when the old one goes (frames %s, %s)" % (comes, goes))
    scene.frame_set((goes or 60) - 10)
    moved = np.linalg.norm(evaluated_positions(old_mesh) - skinned(old_mesh), axis=1)
    free_old = free_vertices(old_mesh)
    swell = float(np.median(moved[free_old])) * effect._object_scale(old_mesh)
    check(abs(swell - s.silk_swell) < 0.2 * s.silk_swell and float(moved[~free_old].max()) < 1e-5,
          "the silk swells the old outfit out by %.3f (silk swell %.3f), its locked parts stay" % (swell, s.silk_swell))
    threads = ribbons.ribbon_objects(s.mask, ribbons.SILK)
    names = {ob.parent_bone for ob in threads}
    check(len(threads) >= 10 and {"上半身", "下半身"} <= names and not ribbons.ribbon_objects(s.mask, ribbons.LIGHT),
          "silk threads round the arms, legs and body (%d: %s)" % (len(threads), sorted(names)))
    tight = []
    for ob in threads:
        pts = np.concatenate([np.array([tuple(p.co)[:3] for p in sp.points]) for sp in ob.data.splines])
        mw = np.array(ob.matrix_world)
        tight.append(float(np.median(surface_distance(pts[::9] @ mw[:3, :3].T + mw[:3, 3], old_mesh))))
    check(len(tight) and float(np.median(tight)) < s.silk_swell + 0.012 * height,
          "the threads wind tight round the body (median %.3f from its surface)" % float(np.median(tight or [0.0])))
    deps = bpy.context.evaluated_depsgraph_get()
    wound = []
    for f in ((goes or 60) - 10, 100):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        count = 0
        for ob in threads:
            me = ob.evaluated_get(deps).to_mesh()
            count += bool(me is not None and len(me.polygons))
            ob.evaluated_get(deps).to_mesh_clear()
        wound.append(count)
    check(wound[0] == len(threads) and wound[1] == 0, "the threads are wound, then snap with the old outfit %s"
          % wound)
    s.silk_threads = False
    check(not ribbons.ribbon_objects(s.mask), "silk threads removed when switched off")
    s.old_surface, s.exit_timing, s.silk_threads = "NONE", "EDGE", True

    # --- 1.9: the transporter beam: the old outfit shimmers away a few faces at a time and the new one in, inside a
    # column of light with sparkles; the locked parts go with the old outfit and come back
    s.entrance, s.easing = "BEAM", "LINEAR"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the transporter beam")
    check(not draw_panels(bpy.context), "panels draw with the transporter beam")
    old_faces = len(old_mesh.data.polygons)
    beamed = []
    for f in range(1, 101, 3):
        scene.frame_set(f)
        beamed.append((f, evaluated_faces_and_edge(old_mesh)[0],
                       len(material_points(new_mesh, materials.BEAM_MATERIAL, others=True)),
                       len(material_points(new_mesh, materials.BEAM_MATERIAL)), instance_count(new_mesh)))
    locked_old = locked_faces(old_mesh)
    going = [o for _f, o, _n, _c, _i in beamed if 0.1 * old_faces < o < 0.9 * old_faces]
    gone = min(o for _f, o, _n, _c, _i in beamed)
    check(beamed[0][1] == old_faces and going and gone < 0.5 * locked_old and beamed[-1][1] == locked_old,
          "beam: the old outfit shimmers away (%d frames part way), its locked parts too (%d of %d) and they come back"
          % (len(going), gone, locked_old))
    coming = [n for _f, _o, n, _c, _i in beamed if 0 < n < 0.9 * len(new_mesh.data.vertices)]
    check(beamed[0][2] == 0 and coming and evaluated_faces_and_edge(new_mesh)[0] == grown_faces,
          "beam: the new outfit shimmers in (%d frames part way) and is whole at the end" % len(coming))
    column = [(c, i) for _f, _o, _n, c, i in beamed]
    check(column[0] == (0, 0) and column[-1] == (0, 0) and max(c for c, _i in column) > 0
          and max(i for _c, i in column) >= s.beam_sparkles,
          "beam: a column of light with %d sparkles while it beams, gone before and after" % s.beam_sparkles)
    check(any(m.get(materials.P_GLOW) for m in effect._glow_materials(old_mesh, s, True)),
          "beam: the locked parts glow too")
    s.entrance, s.easing = "GROW", "EASE"
    for key_, value in saved.items():
        setattr(s, key_, value)

    # --- leave behind: the body slides sideways while it disintegrates; recorded flakes stay where they
    # broke off, the others ride along
    arm = base.armature
    centre = arm.pose.bones.get("センター") or next(pb for pb in arm.pose.bones if pb.parent is None)
    old_action = arm.animation_data.action if arm.animation_data else None
    centre.location = (0.0, 0.0, 0.0)
    centre.keyframe_insert("location", frame=1)
    centre.location = (0.5 * height, 0.0, 0.0)
    centre.keyframe_insert("location", frame=100)
    to_mesh = base.meshes[0].matrix_world.inverted() @ arm.matrix_world
    scene.frame_set(30)
    head30 = to_mesh @ centre.head
    scene.frame_set(60)
    slide = (to_mesh @ centre.head) - head30
    direction = np.array(slide.normalized())
    s.exit_style, s.particles = "FRAGMENTS", "PETAL"
    shots, petals = {}, {}
    for keep in (False, True):
        s.leave_behind = keep
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with leave behind = %s" % keep)
        scene.frame_set(60)
        shots[keep] = flake_positions(base.meshes[0])
        petals[keep] = instance_count(base.meshes[0])
    check(launch.has_launch(base.meshes[0]), "launch positions recorded")
    # (Blender 3.6 lost the petal shape when it was first referenced during the recording)
    check(petals[True] == petals[False] > 0, "the same petals released with leave behind (%s)" % petals)
    check(not draw_panels(bpy.context), "panels draw with leave behind")
    # Same flakes in both builds; recorded ones trail the riding ones by the slide since they broke off
    # (flakes live a few frames), and none is ahead of where the body was.
    (riding, flying), (left, flying_left) = shots[False], shots[True]
    same = riding.shape == left.shape and bool((flying == flying_left).all()) and bool(flying.any())
    lag = (riding[flying] - left[flying]) @ direction if same else np.zeros(1)
    per_frame = slide.length / 30.0
    check(same and np.percentile(lag, 90) > per_frame and lag.min() > -0.01 * height,
          "flakes left behind: 10%% trail by over %.2f (body slides %.2f per frame), none ahead (%.3f)"
          % (np.percentile(lag, 90), per_frame, lag.min()))
    s.particle_life = s.particle_life + 0.05  # the petals set the tail: the mask keys change
    check(not launch.has_launch(base.meshes[0]), "recording dropped when the timing changes")
    s.particle_life = s.particle_life - 0.05
    # Chunks break off whole: each is thrown from where the body was at that moment, all of it at once (its
    # vertices taken at their own moments would shear it along the slide).
    s.exit_style, s.particles = "CHUNKS", "NONE"
    shots = {}
    for keep in (False, True):
        s.leave_behind = keep
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build cast-off with leave behind = %s" % keep)
        scene.frame_set(60)
        shots[keep] = flake_positions(base.meshes[0])
    check(launch.has_launch(base.meshes[0], chunks=True), "chunk launch positions recorded")
    check(not draw_panels(bpy.context), "panels draw with chunks left behind")
    (riding, flying), (left, flying_left) = shots[False], shots[True]
    same = riding.shape == left.shape and bool((flying == flying_left).all()) and bool(flying.any())
    along, spread = np.zeros(1), np.full(1, np.inf)
    if same:
        lag = riding[flying] - left[flying]
        along = lag @ direction
        spread = piece_spread(lag, evaluated_islands(base.meshes[0])[flying])
    check(same and np.percentile(along, 90) > per_frame and along.min() > -0.01 * height,
          "chunks left behind: 10%% trail by over %.2f, none ahead (%.3f)" % (np.percentile(along, 90), along.min()))
    check(float(np.median(spread)) < 0.002 * height, "each chunk left behind in one piece (median spread %.4f, "
          "%d chunks in the air)" % (float(np.median(spread)), len(spread)))
    s.piece_size = s.piece_size * 1.2
    check(not launch.has_launch(base.meshes[0], chunks=True) and launch.has_launch(base.meshes[0]),
          "chunk recording dropped when the piece size changes, the flakes' kept")
    s.piece_size = s.piece_size / 1.2
    s.leave_behind, s.exit_style, s.particles = False, "SHRINK", "NONE"
    centre.location = (0.0, 0.0, 0.0)
    if old_action is None:
        arm.animation_data_clear()
    else:
        arm.animation_data.action = old_action

    # --- leave behind while the whole model moves (object animation, not bones): the flakes stay where they
    # broke off in the world; moving the model afterwards (the same offset on every frame) takes them along
    s.path, s.exit_style = "SURFACE", "FRAGMENTS"
    start_x = base_root.location.x
    base_root.keyframe_insert("location", index=0, frame=1)
    base_root.location.x = start_x + 0.5 * height
    base_root.keyframe_insert("location", index=0, frame=100)
    world = {}
    for keep in (False, True):
        s.leave_behind = keep
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with the model sliding, leave behind = %s" % keep)
        if not keep:  # from the hands and feet: on some models the old outfit is done by frame 60
            busiest = busiest_frame(base.meshes[0], (40, 50, 60, 70, 80))
        scene.frame_set(busiest)
        world[keep] = world_flakes(base.meshes[0])
    (riding, flying), (left, flying_left) = world[False], world[True]
    same = riding.shape == left.shape and bool((flying == flying_left).all()) and bool(flying.any())
    lag = (riding[flying] - left[flying])[:, 0] if same else np.zeros(1)
    per_frame = 0.5 * height / 99.0
    check(same and np.percentile(lag, 90) > per_frame and lag.min() > -0.01 * height,
          "flakes left behind in the world while the model slides: 10%% trail by over %.2f (it slides %.2f per "
          "frame), none ahead (%.3f), frame %d" % (np.percentile(lag, 90), per_frame, lag.min(), busiest))
    space = launch.space(base.meshes[0])
    check(space is not None and bool(fcurves(space, "location")), "the model's motion is kept on its motion empty")
    check((target_root.matrix_world.translation - base_root.matrix_world.translation).length < 1e-4,
          "the new outfit moves along with the old model")
    for fc in fcurves(base_root, "location"):
        for key in fc.keyframe_points:
            key.co[1] += 3.0
            key.handle_left[1] += 3.0
            key.handle_right[1] += 3.0
        fc.update()
    scene.frame_set(busiest + 1)
    scene.frame_set(busiest)
    moved = world_flakes(base.meshes[0])[0]
    off = np.full(1, np.inf)
    if same and moved.shape == left.shape:
        off = np.abs(moved[flying] - left[flying] - np.array((3.0, 0.0, 0.0)))
    check(float(off.max()) < 1e-3 * height, "moving the model afterwards carries the flakes along (off by %.5f)"
          % float(off.max()))
    # The new outfit too: its pieces fly in from fixed points in the world (homing in on the sliding body) and the
    # finale stars stay where they burst out; without leave behind both ride along with the body.
    s.exit_style, s.entrance, s.finale, s.finale_style = "SHRINK", "ASSEMBLE", True, "PULSE"
    pieces, stars = {}, {}
    for keep in (False, True):
        s.leave_behind = keep
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build fly-in + finale with the model sliding, "
              "leave behind = %s" % keep)
        if not keep:
            counts = []
            for f in (30, 45, 60, 75):
                scene.frame_set(f)
                counts.append(int((world_vertices(target.meshes[0])[1] >= 0.89).sum()))
            fly_frame = (30, 45, 60, 75)[int(np.argmax(counts))]
            wave = float(s.mask[effect.P_WAVE])
            finale_frame = None
            for f in range(1, 101):
                scene.frame_set(f)
                if finale_frame is None and (s.mask.scale[0] - wave) / (s.finale_length * wave) >= 0.4:
                    finale_frame = f
        scene.frame_set(fly_frame)
        pieces[keep] = world_vertices(target.meshes[0])
        scene.frame_set(finale_frame or 100)
        stars[keep] = instance_positions(target.meshes[0])
    check(launch.has_launch(target.meshes[0]) and launch.has_launch(target.meshes[0], chunks=True),
          "the new outfit's star births and take-offs recorded")
    (riding, edge), (left, _edge) = pieces[False], pieces[True]
    moved, lag = np.zeros(1, dtype=bool), np.zeros(1)
    if riding.shape == left.shape:
        moved = np.linalg.norm(riding - left, axis=1) > 1e-4 * height
        lag = (riding - left)[moved, 0] if moved.any() else np.zeros(1)
    # A piece trails by the slide since it took off, less and less as it homes in (by the square of the flight left),
    # so the lag is smaller than the flakes'.
    check(moved.any() and bool((edge[moved] >= 0.89).all()) and np.percentile(lag, 90) > 0.3 * per_frame
          and lag.min() > -0.01 * height, "pieces fly in from fixed points: only those in the air differ (%d vertices), "
          "10%% trail by over %.2f (a third of a frame's slide: %.2f), none ahead (%.3f), frame %d"
          % (int(moved.sum()), np.percentile(lag, 90), 0.3 * per_frame, lag.min(), fly_frame))
    lag = (stars[False] - stars[True])[:, 0] if stars[False].shape == stars[True].shape else np.zeros(1)
    check(len(stars[True]) > 0 and np.percentile(lag, 90) > per_frame and lag.min() > -0.01 * height,
          "finale stars stay where they burst out: %d stars, 10%% trail by over %.2f, none ahead (%.3f), frame %s"
          % (len(stars[True]), np.percentile(lag, 90), lag.min(), finale_frame))
    # A turning model: in the air (no spin) a piece keeps the orientation it took off with in the world; riding along
    # with the body it turns with the model, by as much as the model turned since the piece took off.
    saved_spin, s.frag_spin = s.frag_spin, 0.0
    base_root.animation_data_clear()
    base_root.location.x = start_x
    turn_z = base_root.rotation_euler.z
    base_root.keyframe_insert("rotation_euler", index=2, frame=1)
    base_root.rotation_euler.z = turn_z + math.radians(90.0)
    base_root.keyframe_insert("rotation_euler", index=2, frame=100)
    poses = {}
    for keep in (False, True):
        s.leave_behind = keep
        scene.frame_set(1)  # (the body path is voxelised in the world: build both with the model turned alike)
        bpy.ops.mmd_disperse.build()
        scene.frame_set(fly_frame)
        poses[keep] = world_vertices(target.meshes[0])
    islands = evaluated_islands(target.meshes[0])
    (ride, edge), (kept, _edge) = poses[False], poses[True]
    angles = []
    if ride.shape == kept.shape and len(islands) == len(ride):
        for piece in np.unique(islands[edge >= 0.89]):
            sel = islands == piece
            if sel.sum() < 3:
                continue
            a = ride[sel][:, :2] - ride[sel][:, :2].mean(axis=0)
            k = kept[sel][:, :2] - kept[sel][:, :2].mean(axis=0)
            angles.append(math.degrees(math.atan2(float((k[:, 0] * a[:, 1] - k[:, 1] * a[:, 0]).sum()),
                                                  float((k * a).sum()))))
    angles = np.array(angles) if angles else np.zeros(1)
    check(len(angles) > 3 and np.percentile(angles, 90) > 1.0 and angles.max() > 3.0 and angles.min() > -1.0,
          "in the air the pieces keep their orientation in the world while the model turns: %d pieces, turned by "
          "%.1f..%.1f degrees against riding along (90%%: %.1f)" % (len(angles), angles.min(), angles.max(),
                                                                  np.percentile(angles, 90)))
    s.frag_spin = saved_spin
    base_root.animation_data_clear()
    base_root.rotation_euler.z = turn_z
    s.leave_behind = True
    s.fly_range = s.fly_range * 1.2
    check(not launch.has_launch(target.meshes[0], chunks=True) and launch.has_launch(target.meshes[0]),
          "take-offs dropped when the fly range changes, star births kept")
    s.fly_range = s.fly_range / 1.2
    s.finale_style = "SWEEP"
    check(not launch.has_launch(target.meshes[0]) and launch.space(target.meshes[0]) is None,
          "star births dropped when the finale's timing changes (and the motion empty with them)")
    s.finale_style, s.entrance, s.finale = "PULSE", "GROW", False
    s.leave_behind, s.path, s.exit_style = False, "SPHERE", "SHRINK"
    base_root.animation_data_clear()
    base_root.location.x = start_x
    bpy.context.view_layer.update()
    # The sphere's centre (rest space) moves with the model too: moving the model changes nothing.
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build a sphere on the model")
    check(any(c.type == "CHILD_OF" and c.target == base_root for c in s.mask.constraints), "mask moves with the model")
    scene.frame_set(50)
    here = (evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0]))
    base_root.location.x += 5.0
    bpy.context.view_layer.update()
    scene.frame_set(51)
    scene.frame_set(50)
    there = (evaluated_counts(target.meshes[0]), evaluated_counts(base.meshes[0]))
    base_root.location.x -= 5.0
    bpy.context.view_layer.update()
    check(here == there, "moving the model keeps the sphere on the body (%s vs %s)" % (here, there))

    # --- presets; the magical girl adds light ribbons, sparkles and the glowing silhouette
    for key, _label, _desc in presets.ITEMS:
        check(bpy.ops.mmd_disperse.apply_preset(preset=key) == {"FINISHED"}, "preset " + key)
        if key == "VENOM":
            check(s.venom_enable and s.layer_style == "GOO" and s.old_surface == "VEINS"
                  and venom.skeleton(base.meshes[0]) is not None, "symbiote preset: tendrils traced, veins, goo")
        if key in ("CLAMP", "GHOSTS"):
            check(s.entrance == key and len(white_flash(scene)[1]) == 1, "%s preset: entrance and white flash" % key)
        if key in ("ICE", "BURN"):
            mats = set(effect._glow_materials(base.meshes[0], s))
            check(mats and all(m.get(materials.P_SURFACE) == s.old_surface for m in mats)
                  and s.particles in ("SHARD", "EMBER"), "%s preset: %s ahead of the edge, %s"
                  % (key, s.old_surface.lower(), s.particles.lower()))
        if key == "NANO_FINALE":
            check(s.layer_enable and s.inner_glow and s.finale_style == "SWEEP" and white_flash(scene)[0] is not None
                  and len(white_flash(scene)[1]) == 1, "nanotech finale: undersuit, light sweep and the white flash")
        if key == "ICE":
            ee = scene.eevee
            check(s.exit_timing == "AT_ONCE" and s.ice_clarity > 0.0
                  and (getattr(ee, "use_raytracing", False) or getattr(ee, "use_ssr_refraction", False)),
                  "freeze and shatter: clear ice, all at once, EEVEE refraction on")
        if key == "LIQUID_METAL":
            goo_bsdf = bpy.data.materials[materials.GOO_MATERIAL].node_tree.nodes.get("MMDD Goo BSDF")
            check(s.venom_enable and venom.skeleton(base.meshes[0]) is not None and s.venom_metallic == 1.0
                  and goo_bsdf.inputs["Metallic"].default_value == 1.0, "liquid metal preset: metal tendrils and goo")
        if key == "MYSTIQUE":
            mod = our_modifiers(target.meshes[0])[0]
            check(s.entrance == "SCALES" and mod[input_identifiers(mod.node_group)["Scales"]],
                  "Mystique preset: flipping scales")
        if key == "BEAT_DROP":
            check(s.beat_sync and s.finale and s.glitch_enable and len(white_flash(scene)[1]) == 1,
                  "beat drop preset: on the beat, glitch, finale and the white flash")
        if key in ("MAGIC_CIRCLE", "SPARK_PORTAL", "TV_BARRIER", "SPARKLE_SPIRAL"):
            check(s.ring_enable and len(rings.ring_objects(s.mask)) == 1, "%s preset: a %s at the front"
                  % (key, s.ring_style.lower()))
        if key in ("EVOLUTION", "SMOKE_PUFF", "SHADOW_RISE"):
            check(s.easing == "LINEAR" and s.entrance in effect.AT_ONCE, "%s preset: %s on a linear timeline"
                  % (key, s.entrance.lower()))
        if key == "SKETCH":
            check(s.paint_style == "LINEART" and s.path == "UP", "sketch preset: line art from the feet up")
        if key == "INK_WASH":
            check(s.paint_style == "INK" and s.old_surface == "INK" and s.particles == "INK",
                  "ink wash preset: ink over the old outfit, ink drops, the new one in ink")
        if key == "BROOCH":
            check(s.exit_style == "SUCK" and s.finale, "brooch preset: sucked into the brooch")
        if key == "MARK50":
            check(s.reactor and s.plates and s.layer_enable and len(white_flash(scene)[1]) == 1,
                  "Mark 50 preset: reactor, plates, undersuit and the white flash")
        if key == "LIGHTNING":
            check(s.arc_enable and s.arc_strike and len(white_flash(scene)[1]) == 1,
                  "lightning preset: arcs, the strike and the white flash")
        if key == "MATRIX":
            check(s.old_surface == "CODE" and s.paint_style == "CODE" and s.particles == "GLYPH",
                  "digital rain preset: code over both outfits, falling glyphs")
        if key in ("PETRIFY", "MIDAS", "COCOON"):
            check(s.old_surface == {"PETRIFY": "STONE", "MIDAS": "GOLD", "COCOON": "SILK"}[key]
                  and s.exit_timing == "AT_ONCE" and effect._held(s), "%s preset: %s, all at once"
                  % (key, s.old_surface.lower()))
        if key == "COCOON":
            check(len(ribbons.ribbon_objects(s.mask, ribbons.SILK)) >= 10 and s.particles == "BUTTERFLY",
                  "cocoon preset: silk threads, butterflies")
        if key == "TRANSPORTER":
            check(s.entrance == "BEAM" and s.easing == "LINEAR", "transporter preset: the beam on a linear timeline")
    s.beat_sync = False  # (the beat drop preset turned it on; the finale checks below are not on the beat)
    check(s.path == "SURFACE" and s.seeds == "LIMBS" and s.ribbon_enable and s.particles == "STAR",
          "magical girl preset applied (and rebuilt)")
    strands = ribbons.ribbon_objects(s.mask)
    check(len(strands) == 8, "a ribbon around each arm and leg segment (%d)" % len(strands))
    check(bpy.data.objects.get(particles.STAR) is not None, "sparkle shape created")
    check(any(m.get(materials.P_GLOW) for m in base_mats), "old outfit glows for the silhouette")
    scene.frame_set(30)
    deps = bpy.context.evaluated_depsgraph_get()
    drawn = 0
    for ob in strands:
        me = ob.evaluated_get(deps).to_mesh()
        drawn += bool(me is not None and len(me.polygons))
        ob.evaluated_get(deps).to_mesh_clear()
    check(drawn > 0, "ribbons drawn at frame 30 (%d of %d)" % (drawn, len(strands)))
    scene.frame_set(100)
    check(evaluated_faces_and_edge(base.meshes[0])[0] == locked_faces(base.meshes[0]),
          "magical girl: only the shared parts of the old outfit left")

    # --- finale: once the new outfit is complete all of it flashes and stars burst out, then it settles
    check(s.finale, "magical girl preset has the finale")
    wave = float(s.mask[effect.P_WAVE])
    before_flash = flash_frame = None
    for f in range(1, 101):
        scene.frame_set(f)
        progress = (s.mask.scale[0] - wave) / (s.finale_length * wave)
        if progress < -0.05:
            before_flash = f
        elif 0.1 <= progress <= 0.4:
            flash_frame = f
            break
    check(flash_frame is not None and before_flash is not None,
          "finale inside the frame range (frame %s)" % flash_frame)
    if flash_frame is not None and before_flash is not None:
        scene.frame_set(before_flash)
        glow = evaluated_values(target.meshes[0], ATTR_EDGE)
        check(float(np.median(glow)) == 0.0 and instance_count(target.meshes[0]) == 0,
              "no flash and no stars before the outfit is complete (frame %d)" % before_flash)
        scene.frame_set(flash_frame)
        glow = evaluated_values(target.meshes[0], ATTR_EDGE)
        stars = instance_count(target.meshes[0])
        check(float(np.median(glow)) > 0.5, "the whole new outfit flashes at frame %d (median %.2f)"
              % (flash_frame, float(np.median(glow))))
        check(stars > 50, "stars burst out with the flash (%d)" % stars)
    scene.frame_set(100)
    glow = evaluated_values(target.meshes[0], ATTR_EDGE)
    check(float(glow.max()) == 0.0 and instance_count(target.meshes[0]) == 0, "flash and stars over at the end")

    # --- light sweep: instead, a band of light runs out along the wave's path (from the hands and feet here)
    # and stars burst where it passes
    s.finale_style = "SWEEP"
    check(not draw_panels(bpy.context), "panels draw with the light sweep")
    moments = {}
    for f in range(1, 101):
        scene.frame_set(f)
        progress = (s.mask.scale[0] - wave) / (s.finale_length * wave)
        for key_, at in (("early", 0.15), ("late", 0.45)):
            if key_ not in moments and progress >= at:
                moments[key_] = f
    bands = []
    for key_ in ("early", "late"):
        if key_ in moments:
            scene.frame_set(moments[key_])
            lit = evaluated_values(target.meshes[0], ATTR_EDGE) > 0.5
            path = evaluated_values(target.meshes[0], ATTR_ARRIVAL)
            bands.append((round(float(lit.mean()), 3), round(float(np.median(path[lit])), 2) if lit.any() else 0.0,
                          instance_count(target.meshes[0])))
    check(len(bands) == 2 and all(0.0 < b_[0] < 0.5 for b_ in bands) and bands[1][1] > 1.3 * bands[0][1],
          "light sweep: a band moving out along the path (lit share, median path, stars at frames %s: %s)"
          % (sorted(moments.values()), bands))
    check(len(bands) == 2 and bands[1][2] > 0, "stars burst where the light passes")
    scene.frame_set(100)
    check(float(evaluated_values(target.meshes[0], ATTR_EDGE).max()) == 0.0 and instance_count(target.meshes[0]) == 0,
          "light sweep and its stars over at the end")
    s.finale_style = "PULSE"

    # --- white flash: the compositor blends the picture to white as the finale starts, driven by the mask
    check(bpy.ops.mmd_disperse.add_white_flash() == {"FINISHED"}, "white flash added")
    check(bpy.ops.mmd_disperse.add_white_flash() == {"FINISHED"}, "white flash idempotent")
    flash_node, flash_drivers = white_flash(scene)
    check(flash_node is not None and len(flash_drivers) == 1 and flash_drivers[0].driver.is_valid
          and flash_drivers[0].driver.is_simple_expression, "one white flash node driven by the mask (simple expression)")
    # Driven values against the expression evaluated here on the mask radius: a flash where the finale starts.
    seen = []
    if flash_frame is not None and before_flash is not None and flash_drivers:
        functions = {"clamp": lambda v, lo, hi: min(max(v, lo), hi), "pow": pow}
        for f in list(range(before_flash, flash_frame + 2)) + [100]:
            scene.frame_set(f)
            radius_now = sum(s.mask.matrix_world.to_scale()) / 3.0
            want = eval(flash_drivers[0].driver.expression, dict(functions, r=radius_now))
            seen.append((round(white_flash_value(scene), 3), round(want, 3)))
    check(len(seen) > 2 and all(abs(a - b) < 2e-3 for a, b in seen) and seen[0][0] == 0.0 and seen[-1][0] == 0.0
          and max(a for a, _b in seen) > 0.2, "white flash only around the start of the finale (driven, expected: %s)"
          % seen)

    # --- the tail follows the panel: without the sparkles the mask stops sooner (the flakes and finale fit)
    reach = float(s.mask[effect.P_REACH])
    s.particles = "NONE"
    radius = wave * (1.0 + max(s.frag_life, s.finale_length))
    scene.frame_set(100)
    check(abs(float(s.mask[effect.P_REACH]) - radius) < 1e-4 * radius and abs(s.mask.scale[0] - radius) < 1e-3 * radius,
          "mask keys retimed live (%.3f -> %.3f)" % (reach, s.mask.scale[0]))
    s.particles = "STAR"
    check(abs(float(s.mask[effect.P_REACH]) - reach) < 1e-4 * reach, "and stretched again with the sparkles")
    s.ribbon_enable = False
    check(not ribbons.ribbon_objects(s.mask), "ribbons removed when switched off")
    s.ribbon_enable = True
    check(len(ribbons.ribbon_objects(s.mask)) == 8, "ribbons back when switched on")
    check(not draw_panels(bpy.context), "panels draw with the magical girl preset")
    bpy.ops.mmd_disperse.apply_preset(preset="NANOTECH")
    check(not ribbons.ribbon_objects(s.mask) and s.path == "SPHERE", "back to the nanotech suit")
    flash_drivers = white_flash(scene)[1]
    check(len(flash_drivers) == 1 and flash_drivers[0].driver.is_valid
          and flash_drivers[0].driver.variables[0].targets[0].id == s.mask, "white flash follows the rebuilt mask")

    # --- remove restores everything (attributes, materials, particle shapes, motion empties)
    check(bpy.ops.mmd_disperse.remove() == {"FINISHED"}, "remove after the new paths")
    after = snapshot([base, target])
    check(all(before[k] == after[k] for k in before), "models restored after flakes, sweeps and petals")
    check(not any(bpy.data.objects.get(n) for n in particles.NAMES.values()), "particle shapes removed")
    check(not any(o.name.startswith(ribbons.NAME) for o in bpy.data.objects), "ribbons removed")
    check(not any(o.name.startswith(launch.SPACE) for o in bpy.data.objects), "motion empties removed")
    check(not any(o.name.startswith(venom.SKELETON) for o in bpy.data.objects)
          and bpy.data.materials.get(materials.GOO_MATERIAL) is None, "symbiote skeletons and goo removed")
    flash_node, flash_drivers = white_flash(scene)
    check(flash_node is not None and not flash_drivers and white_flash_value(scene) == 0.0,
          "white flash node kept but switched off")

    # --- a scaled model transforms the same way: sizes are converted to object space
    s.exit_style, s.particles = "FRAGMENTS", "PETAL"

    def picture(path):
        s.path = path
        bpy.ops.mmd_disperse.build()
        seen = []
        for f in (35, 65):
            scene.frame_set(f)
            seen.append((evaluated_faces_and_edge(target.meshes[0])[0], evaluated_faces_and_edge(base.meshes[0])[0],
                         instance_count(base.meshes[0])))
        bpy.ops.mmd_disperse.remove()
        return seen

    def close(a, b):
        return all(abs(x - y) <= 0.01 * max(x, y) + 2 for x, y in zip(a, b))

    for path in ("SPHERE", "SURFACE"):
        plain = picture(path)
        base_root.scale = [v * 0.5 for v in base_root.scale]
        bpy.context.view_layer.update()
        scaled = picture(path)
        base_root.scale = [v * 2.0 for v in base_root.scale]
        bpy.context.view_layer.update()
        check(all(close(a, b) for a, b in zip(plain, scaled)),
              "half-size model, %s: same faces and petals (%s vs %s)" % (path, plain, scaled))
    s.path, s.exit_style, s.particles = "SPHERE", "SHRINK", "NONE"

    # --- old outfit only: the whole model disintegrates
    s.target, s.use_lock, s.particles = None, False, "NONE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with only the old outfit")
    scene.frame_set(100)
    check(evaluated_faces_and_edge(base.meshes[0])[0] == 0, "old outfit gone completely")
    bpy.ops.mmd_disperse.remove()

    mmd_disperse.unregister()
    check(not hasattr(bpy.types.Scene, "mmd_disperse"), "unregistered cleanly")


try:
    run()
except Exception:
    traceback.print_exc()
    FAILURES.append("exception")
print("RESULT", "OK" if not FAILURES else "FAILED: %s" % FAILURES)
