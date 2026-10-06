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
from mathutils import Matrix, Quaternion, Vector
from mathutils.kdtree import KDTree

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import (arrival, beats, compositor, domain, effect, impact, launch, materials,  # noqa: E402
                          motion, particles, presets, ribbons, rings, toon, trails, venom)
from mmd_disperse import shots as camera_moves  # noqa: E402  (the checks use "shots" for their own lists)
from mmd_disperse.arrival import limb_points  # noqa: E402
from mmd_disperse.model import resolve, rest_points_world  # noqa: E402
from mmd_disperse.node_groups import (ATTR_ARRIVAL, ATTR_CUT, ATTR_EDGE, ATTR_HOLO, ATTR_HUSK,  # noqa: E402
                                      ATTR_LAYER, ATTR_AHEAD, ATTR_FRAME, ATTR_LOCK, ATTR_PAINT, ATTR_SHADOW,
                                      ATTR_VARIANT, BASE_GROUP, GLYPHS, RING_STYLES, TARGET_GROUP, VENOM_ATTRS,
                                      VENOM_ENDS, input_identifiers)
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


def material_values(ob, name, attribute):
    """Values of the point attribute `attribute` on the evaluated vertices of the faces drawn with material `name`."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        names = [m.name if m is not None else "" for m in me.materials]
        attr = me.attributes.get(attribute)
        if name not in names or attr is None or attr.domain != "POINT" or not len(me.polygons):
            return np.zeros(0)
        face_material = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("material_index", face_material)
        totals = np.zeros(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("loop_total", totals)
        corner_vertex = np.zeros(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", corner_vertex)
        picked = np.repeat(face_material == names.index(name), totals)
        values = np.zeros(len(attr.data), dtype=np.float32)
        attr.data.foreach_get("value", values)
        return values[np.unique(corner_vertex[picked])]
    finally:
        ev.to_mesh_clear()


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

    # --- 1.10: two fronts from the waist (Danny Phantom): the change sets off at the waist, one front going up the body
    # and one down, a ring of light on each
    saved = {key_: getattr(s, key_) for key_ in (
        "path", "seeds", "entrance", "exit_style", "exit_timing", "particles", "wire_enable", "easing", "finale",
        "frame_start", "frame_end", "trigger", "garment_order", "hand_side", "ring_enable", "ring_style")}
    s.wire_enable, s.particles, s.exit_style, s.finale, s.easing = False, "NONE", "SHRINK", False, "EASE"
    s.path = "MIDDLE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build split from the waist")
    check(not draw_panels(bpy.context), "panels draw with the waist split")
    lead = s.wire_outer + 0.005 * height
    outfits = target.meshes + base.meshes
    rest = [rest_points_world(ob) for ob in outfits]
    waist = arrival.waist_level(rest, (0.0, 0.0, 1.0), base.armature)
    off = max(float(np.abs(arrival_values(ob) * effect._object_scale(ob) - lead - np.abs(p[:, 2] - waist)).max())
              for ob, p in zip(outfits, rest))
    check(off < 2e-3 * height, "waist split: the change sets off from the waist (%.2f up) both ways (off by %.4f)"
          % (waist, off))
    s.ring_enable, s.ring_style = True, "HALO"
    halo = rings.ring_objects(s.mask)
    scene.frame_set(40)
    pts = world_vertices(halo[0])[0] if halo else np.zeros((0, 3))
    above, below = (float(pts[:, 2].max()) - waist, waist - float(pts[:, 2].min())) if len(pts) else (0.0, 0.0)
    check(len(halo) == 1 and above > 0.05 * height and abs(above - below) < 0.01 * height,
          "waist split: a ring of light on each front (%.2f above the waist, %.2f below)" % (above, below))
    s.ring_enable = False

    # --- 1.10: garment by garment (an idol anime's coord change): each material of the new outfit in its own turn,
    # swept from its top down (its bottom up), from the top of the body down (the feet up); the old outfit goes with
    # the garment nearest to it
    s.path = "GARMENTS"
    turn_length = 0.6 * height * (1.0 + arrival.GARMENT_GAP)
    for order, sign in (("DOWN", -1.0), ("UP", 1.0)):
        s.garment_order = order
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build garment by garment (%s)" % order.lower())
        got = arrival_values(new_mesh) * effect._object_scale(new_mesh) - lead
        z = rest_points_world(new_mesh)[:, 2]
        free = free_vertices(new_mesh)
        turn = np.floor(got / turn_length + 1e-6).astype(int)
        turns = sorted(set(turn[free].tolist()))
        middle = [float(np.median(z[free & (turn == k)])) for k in turns]
        first = free & (turn == turns[0])
        along = float(np.corrcoef(got[first], z[first])[0, 1]) if first.sum() > 2 else 0.0
        old_got = arrival_values(old_mesh) * effect._object_scale(old_mesh) - lead
        old_turns = set(np.floor(old_got / turn_length + 1e-6).astype(int)[free_vertices(old_mesh)].tolist())
        check(2 <= len(turns) <= arrival.MAX_GARMENTS and sign * (middle[-1] - middle[0]) > 0.0 and sign * along > 0.8
              and old_turns <= set(turns),
              "garments %s: %d garments in turn (middle heights %s), each swept from its %s (%.2f), the old outfit "
              "with them" % (order.lower(), len(turns), [round(m, 1) for m in middle],
                             "top" if order == "DOWN" else "bottom", along))
    check(not draw_panels(bpy.context), "panels draw garment by garment")

    def frame_at(radius):
        """First whole frame at which the mask radius reaches `radius` (the end frame if it never does)."""
        at = effect._frame_at(s.mask, radius)
        return int(math.ceil(at - 1e-6)) if at is not None else s.frame_end

    def wave_and_moment():
        wave_ = float(s.mask[effect.P_WAVE])
        return wave_, effect._moment(s, wave_, s.mask), effect._finale_start(s, wave_, s.mask)

    # --- 1.10: the instant swap: all of the new outfit is there at the moment the old one goes
    s.path, s.entrance = "SPHERE", "SWAP"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the instant swap")
    full = len(old_mesh.data.vertices)
    wave, moment, big = wave_and_moment()
    at_moment = frame_at(moment)
    scene.frame_set(s.frame_end)
    after = (evaluated_counts(old_mesh), evaluated_counts(new_mesh))
    swapped = {}
    for f in range(at_moment - 6, at_moment + 7):
        scene.frame_set(f)
        swapped[f] = (evaluated_counts(old_mesh), evaluated_counts(new_mesh))
    comes = min((f for f, (_o, n) in swapped.items() if n > 0), default=None)
    check(swapped[at_moment - 6] == (full, 0) and swapped[at_moment + 6] == after
          and all(n in (0, after[1]) for _o, n in swapped.values()) and comes is not None
          and abs(comes - at_moment) <= 1,
          "swap: all of the new outfit comes at once at the moment (frame %s, the moment %d) as the old one goes"
          % (comes, at_moment))

    def instance_matrices(ob):
        deps = bpy.context.evaluated_depsgraph_get()
        return [inst.matrix_world.copy() for inst in deps.object_instances
                if inst.is_instance and inst.parent is not None and inst.parent.original == ob]

    # --- 1.10: the lotus (Ne Zha 2): two rings of petals grow up from the floor round the body, close into a bud, the
    # outfits swap inside it at the moment, then it opens out flat and sinks away
    s.entrance, s.easing = "LOTUS", "LINEAR"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the lotus")
    check(not draw_panels(bpy.context), "panels draw with the lotus")
    main = max(target.meshes, key=lambda ob: len(ob.data.vertices))
    pts = rest_points_world(main)
    centre_xy = (pts[:, :2].min(axis=0) + pts[:, :2].max(axis=0)) / 2.0
    wave, moment, big = wave_and_moment()
    leaning = {}
    for p in (0.05, 0.8, 1.4, 1.7):
        f = frame_at(p * moment)
        scene.frame_set(f)
        lean = []
        for m in instance_matrices(main):
            up = np.array(m.col[2][:3])
            out = np.array(m.translation[:2]) - centre_xy
            if np.linalg.norm(up) > 1e-9 and np.linalg.norm(out) > 1e-9:
                lean.append(-float(up[:2] @ out) / (np.linalg.norm(up) * np.linalg.norm(out)))
        leaning[p] = (f, len(instance_matrices(main)), round(float(np.mean(lean)), 2) if lean else 0.0,
                      round(float(np.min(lean)), 2) if lean else 0.0)
    petals = 2 * s.lotus_petals
    check(leaning[0.05][1] == petals and leaning[0.05][2] < -0.8 and leaning[0.8][1] == petals
          and leaning[0.8][3] > 0.0 and leaning[1.4][1] == petals and leaning[1.4][2] < -0.9 and leaning[1.7][1] == 0,
          "lotus: %d petals open, shut round the body, opened out flat, then gone (frame, petals, mean and least lean "
          "in: %s)" % (petals, leaning))

    # --- 1.10: toon flames: a band of fire burning round the edge (a shell just over the surface and tongues of flame
    # turned to the camera), or an aura of fire over the whole body as the change comes to its height
    s.entrance, s.easing, s.path = "GROW", "EASE", "UP"
    s.flame_enable, s.flame_mode = True, "EDGE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with toon flames")
    check(not draw_panels(bpy.context), "panels draw with toon flames")
    scene.frame_set(50)
    shell = material_points(old_mesh, materials.FLAME_MATERIAL)
    mw = np.array(old_mesh.matrix_world)
    posed = skinned(old_mesh) @ mw[:3, :3].T + mw[:3, 3]
    posed_tree = KDTree(len(posed))
    for i, v in enumerate(posed):
        posed_tree.insert(Vector(v), i)
    posed_tree.balance()
    arrival_old = arrival_values(old_mesh) * effect._object_scale(old_mesh)
    radius = s.mask.matrix_world.to_scale().x
    off = np.array([abs(arrival_old[posed_tree.find(Vector(p))[1]] - radius) for p in shell[::5]])
    band = s.flame_width + s.noise_amount + 0.02 * height
    check(len(shell) > 100 and float(np.median(off)) < band and float(np.percentile(off, 95)) < band + 0.05 * height,
          "flames: a shell of fire round the edge (%d vertices, median %.2f from it, %.2f allowed)"
          % (len(shell), float(np.median(off)) if len(off) else -1.0, band))
    cam = scene.camera
    turned = []
    for m in instance_matrices(old_mesh):
        across = np.array(m.col[1][:2])
        to_cam = (np.array(cam.matrix_world.translation[:2]) - np.array(m.translation[:2]) if cam is not None
                  else np.array((0.0, -1.0)))
        turned.append(abs(float(across @ to_cam)) / max(np.linalg.norm(across) * np.linalg.norm(to_cam), 1e-9))
    check(len(turned) > 10 and float(np.mean(np.array(turned) > 0.95)) > 0.95,
          "flames: %d tongues of flame, turned to the camera" % len(turned))
    s.entrance, s.easing, s.flame_mode = "SWAP", "LINEAR", "AURA"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with a flame aura")
    wave, moment, big = wave_and_moment()
    aura = {}
    for name, f in (("before", frame_at(0.02 * big)), ("height", frame_at(0.7 * big)), ("after", s.frame_end)):
        scene.frame_set(f)
        aura[name] = (f, len(material_points(old_mesh, materials.FLAME_MATERIAL)),
                      len(material_points(new_mesh, materials.FLAME_MATERIAL)),
                      instance_count(old_mesh) + instance_count(new_mesh))
    check(aura["before"][1:] == (0, 0, 0) and aura["height"][1] > 0.9 * len(old_mesh.data.vertices)
          and aura["height"][3] > 0 and aura["after"][1:] == (0, 0, 0),
          "flame aura: none at first, all over the body as the change comes to its height, gone after it "
          "(frame, burning vertices old and new, tongues: %s)" % aura)
    s.flame_enable = False

    # --- 1.10: impact frames as the change completes: the picture drained of colour and inverted every other frame for
    # a few frames, speed lines rushing in to the character, a shockwave spreading out on the floor
    made_camera = None
    if scene.camera is None:  # (the speed lines hang in front of the camera)
        made_camera = bpy.data.objects.new("MMDD Test Camera", bpy.data.cameras.new("MMDD Test Camera"))
        scene.collection.objects.link(made_camera)
        made_camera.location = (float(centre_xy[0]), float(centre_xy[1]) - 2.5 * height, 0.55 * height)
        made_camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        scene.camera = made_camera
    s.impact_enable, s.speed_lines, s.shockwave, s.impact_frames = True, True, True, 3
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with impact frames")
    check(bpy.ops.mmd_disperse.add_impact() == {"FINISHED"}, "impact frames added to the compositor")
    check(not draw_panels(bpy.context), "panels draw with impact frames")
    tree = compositor._existing_tree(scene)
    grey, stark, invert = (tree.nodes.get(n) if tree is not None else None
                           for n in (compositor.IMPACT_GREY, compositor.IMPACT_CONTRAST, compositor.IMPACT_INVERT))
    sheets = impact.sheets(s.mask)
    wave, moment, big = wave_and_moment()
    first = frame_at(effect._impact_start(s, s.mask, wave))  # (a frame after the new outfit is complete)
    check(first == frame_at(big) + 1, "impact frames a frame after the new outfit is complete (%d, %d)"
          % (first, frame_at(big)))
    shots, shock_glow = [], []
    for f in range(first - 2, first + 5 + impact.LINGER):
        scene.frame_set(f)
        ring = material_points(main, materials.SHOCK_MATERIAL)
        glowing = material_values(main, materials.SHOCK_MATERIAL, ATTR_EDGE)
        shock_glow.append(round(float(glowing.max()), 2) if len(glowing) else 0.0)
        if f == first:
            check(stark is not None and grey is not None and compositor._flash_factor(stark).default_value
                  == compositor._flash_factor(grey).default_value == 1.0,
                  "impact frames: stark black and white as the colour drains (frame %d)" % f)
        shots.append((f, round(compositor._flash_factor(grey).default_value) if grey else -1,
                      round(compositor._flash_factor(invert).default_value) if invert else -1,
                      round(float(sheets[0][impact.SHOWN]), 2) if sheets else -1.0,
                      round(float(np.linalg.norm(ring[:, :2] - centre_xy, axis=1).max()), 2) if len(ring) else 0.0))
    check([g for _f, g, _i, _l, _r in shots[:7]] == [0, 0, 1, 1, 1, 0, 0]
          and [i for _f, _g, i, _l, _r in shots[:7]] == [0, 0, 1, 0, 1, 0, 0],
          "impact frames: three frames drained of colour, the first and the last inverted, from where the change is "
          "complete (frame %d): %s" % (first, [(f, g, i) for f, g, i, _l, _r in shots]))
    driven = [d for d in (tree.animation_data.drivers if tree is not None and tree.animation_data else [])
              if "MMD Disperse Impact" in d.data_path]
    driven += list(sheets[0].animation_data.drivers) if sheets and sheets[0].animation_data else []
    check(len(driven) == 5 and all(d.driver.is_valid and d.driver.is_simple_expression for d in driven),
          "impact frames and speed lines: five drivers, all simple expressions (they run with Python scripts off)")
    lines = [line for _f, _g, _i, line, _r in shots]
    check(len(sheets) == 1 and sheets[0].parent == scene.camera and lines[:2] == [0.0, 0.0] and lines[2:5] == [1.0] * 3
          and 0.0 < lines[5] < 1.0 and lines[-1] == 0.0,
          "speed lines in front of the camera while the impact frames run, fading after (%s)" % lines)
    spread = [r for _f, _g, _i, _l, r in shots]
    check(spread[0] == 0.0 and 0.0 < spread[3] < spread[8],
          "shockwave: a ring on the floor spreading out from the change (%s)" % spread)
    check(shock_glow[0] == 0.0 and min(shock_glow[3:6]) > 0.2 and shock_glow[5] < shock_glow[3],
          "shockwave: the ring glows as it spreads, fading (%s)" % shock_glow)
    shock_mat, dust_mat = (bpy.data.materials.get(n) for n in (materials.SHOCK_MATERIAL, materials.DUST_MATERIAL))
    check(shock_mat is not None and any(n.bl_idname == "ShaderNodeAddShader" for n in shock_mat.node_tree.nodes)
          and dust_mat is not None and any(n.bl_idname == "ShaderNodeLayerWeight" for n in dust_mat.node_tree.nodes),
          "shockwave: its glow added over the floor (no black band where it is faint), the dust thinning out at its "
          "outline")
    s.impact_enable = False
    check(not impact.sheets(s.mask) and (grey is None or compositor._flash_factor(grey).default_value == 0.0),
          "impact frames off: no speed lines, the picture left alone")
    if made_camera is not None:
        scene.camera = None
        bpy.data.objects.remove(made_camera)

    # --- 1.10: soul rings (Soul Land): rings of light rise round the body one after another, each to its own height
    # from the knees up to above the head, and fade after the change
    s.entrance, s.path, s.easing = "GROW", "SURFACE", "EASE"
    s.soul_enable, s.soul_count = True, 7
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with soul rings")
    check(not draw_panels(bpy.context), "panels draw with soul rings")
    wave, moment, big = wave_and_moment()
    risen = {}
    for name, f in (("start", s.frame_start), ("risen", frame_at(0.75 * big)), ("after", s.frame_end)):
        scene.frame_set(f)
        risen[name] = instance_positions(main)
    tall = float(pts[:, 2].max() - pts[:, 2].min())
    levels = np.sort(risen["risen"][:, 2]) if len(risen["risen"]) else np.zeros(1)
    check(len(risen["start"]) == 0 and len(risen["risen"]) == 7 and len(risen["after"]) == 0
          and abs(float(levels[-1] - levels[0]) - 0.76 * tall) < 0.05 * tall,
          "soul rings: none at first, 7 risen from %.2f to %.2f of the body, gone after the change"
          % (float(levels[0] - pts[:, 2].min()) / tall, float(levels[-1] - pts[:, 2].min()) / tall))
    s.soul_enable = False

    # --- 1.10: the husk (Black Myth's 聚形散气): at the moment the whole old model, its locked parts too, is left behind
    # where it stood, holding still while the body moves on, then it crumbles away from the top (or floats up and fades)
    s.entrance, s.exit_style, s.easing, s.path = "SWAP", "HUSK", "LINEAR", "SPHERE"
    arm = base.armature
    centre = arm.pose.bones.get("センター") or next(pb for pb in arm.pose.bones if pb.parent is None)
    arm.animation_data_create()
    kept_action = arm.animation_data.action
    slide = bpy.data.actions.new("MMDD Test Slide")
    arm.animation_data.action = slide
    centre.location = (0.0, 0.0, 0.0)
    centre.keyframe_insert("location", frame=1)
    centre.location = (0.5 * height, 0.0, 0.0)
    centre.keyframe_insert("location", frame=100)
    husk_mats = []
    try:
        for style, away in (("AMBER", "CRUMBLE"), ("GHOST", "FLOAT")):
            s.husk_style, s.husk_away = style, away
            check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the husk (%s, %s)" % (style.lower(),
                                                                                           away.lower()))
            wave, moment, big = wave_and_moment()
            frames = {"before": frame_at(moment) - 2, "left": frame_at(moment) + 1,
                      "held": frame_at(moment + 0.8 * s.husk_hold * wave),
                      "going": frame_at(moment + (s.husk_hold + 0.6 * s.husk_time) * wave), "gone": s.frame_end}
            husk = {}
            for key_, f in frames.items():
                scene.frame_set(f)
                values = evaluated_values(old_mesh, ATTR_HUSK)
                there = values > 0.0 if values is not None else np.zeros(0, dtype=bool)
                husk[key_] = (evaluated_positions(old_mesh)[there] if len(there) else np.zeros((0, 3)),
                              values[there] if values is not None else np.zeros(0))
            still = (len(husk["left"][0]) == len(husk["held"][0]) > 0
                     and float(np.abs(husk["left"][0] - husk["held"][0]).max()) < 1e-4 * height)
            check(len(husk["before"][0]) == 0 and len(husk["left"][0]) == full and still
                  and frames["held"] > frames["left"] + 3 and len(husk["gone"][0]) == 0,
                  "husk (%s): the whole old model (%d of %d vertices) left behind at the moment, holding still while "
                  "the body slides on (frames %d to %d), gone at the end" % (
                      style.lower(), len(husk["left"][0]), full, frames["left"], frames["held"]))
            if away == "FLOAT":
                rise = (float(husk["going"][0][:, 2].mean() - husk["left"][0][:, 2].mean())
                        if len(husk["going"][0]) else 0.0) * effect._object_scale(old_mesh)
                check(rise > 0.1 * effect.HUSK_RISE * height and float(husk["going"][1].max()) < 0.9,
                      "husk floats up (%.2f) and fades" % rise)
            else:
                check(len(husk["going"][0]) not in (0, full) and float(husk["going"][1].min()) == 1.0,
                      "husk crumbles from the top (%d vertices then)" % len(husk["going"][0]))
        husk_mats = [m for m in list(effect._glow_materials(old_mesh, s)) + list(effect._glow_materials(old_mesh, s,
                                                                                                         True))]
        check(husk_mats and all(m.get(materials.P_HUSK) and materials.HUSK + " Mix" in chain(m) for m in husk_mats),
              "husk: all of the old model's materials, its locked parts' too, can turn into the husk (%d)"
              % len(husk_mats))
    finally:
        arm.animation_data.action = kept_action
        bpy.data.actions.remove(slide)
        centre.location = (0.0, 0.0, 0.0)
    s.exit_style, s.entrance = "SHRINK", "GROW"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}
          and not any(m.get(materials.P_HUSK) or materials.HUSK + " Mix" in chain(m) for m in husk_mats),
          "husk taken out of the materials again")

    # --- 1.10: moves of the dance that start it, found in made-up motions (a 20 high model, 30 frames a second)
    def made_up(count, h=20.0):
        """A motion of `count` frames standing facing the front, hands at the sides, out of the rest pose."""
        t = motion.Track(range(count))
        for side_, x in (("L", 1.0), ("R", -1.0)):
            t.wrist[side_][:] = (0.2 * h * x, 0.0, 0.45 * h)
            t.palm[side_][:] = (0.2 * h * x, 0.0, 0.42 * h)
            t.tip[side_][:] = (0.2 * h * x, 0.0, 0.36 * h)
        t.eyes[:] = (0.0, -0.03 * h, 0.93 * h)
        t.up[:] = t.body_up[:] = (0.0, 0.0, 1.0)
        t.front[:] = t.facing[:] = (0.0, -1.0, 0.0)
        t.head_turn[:] = t.body_turn[:] = np.eye(3)
        t.chest[:] = (0.0, 0.0, 0.7 * h)
        t.from_rest[:] = 0.1 * h
        return t

    def hand_at(t, side_, i, spot, h=20.0):
        """The hand's fingers pointing up at `spot` (fingertips just past it) in frame i."""
        spot = np.asarray(spot, dtype=np.float64)
        t.tip[side_][i] = spot + (0.0, 0.0, 0.005 * h)
        t.palm[side_][i] = spot - (0.0, 0.0, 0.05 * h)
        t.wrist[side_][i] = spot - (0.0, 0.0, 0.08 * h)

    H, FPS = 20.0, 30.0
    for start_at_rest in (False, True):
        clap = made_up(70)
        for i in range(70):
            x = 0.2 * H * min(1.0, abs(i - 40) / 6.0) + 0.01 * H
            clap.palm["L"][i], clap.palm["R"][i] = (x, -0.1 * H, 0.75 * H), (-x, -0.1 * H, 0.75 * H)
        if start_at_rest:  # starting in the rest pose and jumping into the dance at frame 20: the clap is too soon
            clap.from_rest[:20] = 0.0
        found = motion.find(clap, "CLAP", H, FPS)
        check(found == (None if start_at_rest else (40, ("L", "R"))),
              "made-up clap found at its frame (%s), not within a second of leaving the rest pose" % (found,))
    slow = made_up(70)
    for i in range(70):
        x = 0.2 * H * max(0.0, 1.0 - i / 50.0) + 0.01 * H
        slow.palm["L"][i], slow.palm["R"][i] = (x, -0.1 * H, 0.75 * H), (-x, -0.1 * H, 0.75 * H)
    check(motion.find(slow, "CLAP", H, FPS) is None, "hands coming together slowly are no clap")
    mouth = clap.mouth(H)[0]
    brow = clap.brow(H)[0]
    for case, expect in (("kiss", (20, ("L",))), ("both hands", None), ("at the eye", None)):
        kiss = made_up(50)
        for i in range(50):
            lift = (0.0, 0.0, 0.08 * H) if case == "at the eye" else (0.0, 0.0, 0.0)  # (the palm at the eyes)
            spot = mouth + lift + (0.0, -0.3 * H * min(1.0, abs(i - 20) / 10.0), 0.0)  # (in from the front, away)
            hand_at(kiss, "L", i, spot)
            if case == "both hands":
                hand_at(kiss, "R", i, spot + (0.02 * H, 0.0, 0.0))
        found = motion.find(kiss, "KISS", H, FPS)
        check(found == expect, "made-up kiss (%s): %s" % (case, found))
    for case, expect in (("salute", (30, ("R",))), ("below the eyes", None), ("both hands", None)):
        salute = made_up(60)
        for i in range(30, 46):
            spot = brow - ((0.0, 0.0, 0.06 * H) if case == "below the eyes" else (0.0, 0.0, 0.0))
            hand_at(salute, "R", i, spot)
            if case == "both hands":
                hand_at(salute, "L", i, spot + (0.03 * H, 0.0, 0.0))
        found = motion.find(salute, "SALUTE", H, FPS)
        check(found == expect, "made-up salute (%s): %s" % (case, found))
    for axis_, expect in (("X", (42, ("HEAD",))), ("Z", None)):
        toss = made_up(60)
        for i in range(60):  # 10, 25, 20 and 5 degrees a frame from frame 41 on: fastest at 42
            angle = math.radians({41: 10.0, 42: 35.0, 43: 55.0}.get(i, 0.0 if i <= 40 else 60.0))
            toss.head_turn[i] = np.array(Matrix.Rotation(angle, 3, axis_))
        found = motion.find(toss, "FLIP", H, FPS)
        check(found == expect, "made-up toss of the head (about %s: %s): %s" % (
            axis_, "a nod" if axis_ == "X" else "turning it, no toss", found))
    spin = made_up(60)
    for i in range(60):
        a = 2.0 * math.pi * min(max((i - 10) / 40.0, 0.0), 1.0)
        spin.facing[i] = (math.sin(a), -math.cos(a), 0.0)
    check(motion.find(spin, "TURN", H, FPS) == (30, ()), "made-up spin: the back to the camera at frame 30")
    check(motion.snap(31.0, [24.0, 33.0], 30.0) == 33.0 and motion.snap(20.0, [33.0], 30.0) == 20.0,
          "moves snap to a beat within 0.3 seconds")

    # The real thing: the model spins round (its root turned) and the swap comes as its back is to the camera; then
    # it nods its head (an arm held out of the rest pose, as in a dance) and the transformation starts there, from
    # the head.
    root_action = base_root.animation_data.action if base_root.animation_data else None
    pose_action = arm.animation_data.action
    nod = bpy.data.actions.new("MMDD Test Nod")
    upper_arm = arm.pose.bones.get("腕.L") or arm.pose.bones.get("左腕")
    head_bone = motion.find_bone(arm, motion.HEAD)
    turned_at = None
    try:
        base_root.rotation_euler.z = 0.0
        base_root.keyframe_insert("rotation_euler", index=2, frame=30)
        base_root.rotation_euler.z = 2.0 * math.pi
        base_root.keyframe_insert("rotation_euler", index=2, frame=70)
        s.frame_start, s.frame_end, s.trigger, s.entrance, s.path = 1, 100, "TURN", "SWAP", "SPHERE"
        scene.frame_set(1)
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build to swap as the back is turned")
        turned_at = s.mask.get(effect.P_TRIGGER)
        wave, moment, big = wave_and_moment()
        scene.frame_set(int(round(turned_at or 0)) - 2)
        before_ = evaluated_counts(new_mesh)
        scene.frame_set(int(round(turned_at or 0)) + 2)
        after_ = evaluated_counts(new_mesh)
        check(turned_at is not None and abs(turned_at - 50.0) <= 1.0 and before_ == 0 and after_ > 0
              and abs(frame_at(moment) - turned_at) <= 1.0,
              "turn: the back to the camera found at frame %s (the root spins round from 30 to 70), the swap then "
              "(frames %d to %d)" % (turned_at, s.frame_start, s.frame_end))
        check(not draw_panels(bpy.context), "panels draw with a move found")
    finally:
        spun = base_root.animation_data.action if base_root.animation_data else None
        if base_root.animation_data is not None:
            base_root.animation_data.action = root_action
        if spun is not None and spun != root_action:
            bpy.data.actions.remove(spun)
        base_root.rotation_euler.z = 0.0
    modes = upper_arm.rotation_mode, head_bone.rotation_mode
    tilt = 0.0
    easing = s.easing
    try:
        arm.animation_data.action = nod
        upper_arm.rotation_mode = head_bone.rotation_mode = "QUATERNION"
        upper_arm.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(-40.0))
        upper_arm.keyframe_insert("rotation_quaternion", frame=1)
        for f, angle in ((60, 0.0), (63, 60.0), (66, 0.0)):
            head_bone.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(angle))
            head_bone.keyframe_insert("rotation_quaternion", frame=f)
        s.frame_start, s.frame_end, s.trigger, s.entrance, s.path = 1, 100, "FLIP", "GROW", "SPHERE"
        s.easing, s.impact_enable, s.impact_frames = "EASE", True, 3
        scene.frame_set(1)
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build to start on a toss of the head")
        head_rest = motion.rest_head(arm, motion.HEAD)
        tilt = s.mask.get(effect.P_TRIGGER)
        bpy.context.view_layer.update()
        check(tilt is not None and 60.0 <= tilt <= 65.0 and s.frame_start == int(round(tilt))
              and s.frame_end == s.frame_start + 99
              and (s.mask.matrix_world.translation - head_rest).length < 1e-3 * height,
              "flip: the toss of the head found at frame %s (it nods from 60 to 66), the transformation starts there "
              "(frames %d to %d), from the head" % (tilt, s.frame_start, s.frame_end))
        # impact frames as the front sets off: three whole frames, though it starts slowly (eased) and speeds up
        tree = compositor._existing_tree(scene)
        grey, invert = (tree.nodes.get(n) if tree is not None else None
                        for n in (compositor.IMPACT_GREY, compositor.IMPACT_INVERT))
        shots = []
        for f in range(s.frame_start - 1, s.frame_start + 6):
            scene.frame_set(f)
            shots.append((round(compositor._flash_factor(grey).default_value) if grey else -1,
                          round(compositor._flash_factor(invert).default_value) if invert else -1))
        check([g for g, _i in shots] == [0, 0, 1, 1, 1, 0, 0] and [i for _g, i in shots] == [0, 0, 1, 0, 1, 0, 0],
              "flip: impact frames as the change sets off from the toss of the head, three frames, the first and the "
              "last inverted, though the front starts slowly (frames %d on: %s)" % (s.frame_start - 1, shots))
    finally:
        arm.animation_data.action = pose_action
        bpy.data.actions.remove(nod)
        upper_arm.rotation_quaternion = head_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        upper_arm.rotation_mode, head_bone.rotation_mode = modes
        s.easing, s.impact_enable = easing, False
    s.trigger, s.frame_start, s.frame_end = "NONE", 1, 100

    # --- 1.10: where the hands sweep: the left arm comes down from held up to the side; the change comes where the hand
    # passes when it gets there, then over the rest of the body, the front keeping the hand's pace (linear) to the end
    sweep = bpy.data.actions.new("MMDD Test Sweep")
    try:
        arm.animation_data.action = sweep
        upper_arm.rotation_mode = "QUATERNION"
        upper_arm.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(60.0))
        upper_arm.keyframe_insert("rotation_quaternion", frame=1)
        upper_arm.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(-40.0))
        upper_arm.keyframe_insert("rotation_quaternion", frame=40)
        s.path, s.hand_side, s.frame_start, s.frame_end = "HAND", "LEFT", 1, 60
        scene.frame_set(1)
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build where the hands sweep")
        check(not draw_panels(bpy.context), "panels draw with the hand path")
        speed = float(s.mask.get(effect.P_SPEED, 0.0))
        tall = effect.model_height(s.target or s.base)  # (the effect is sized by the new outfit's height)
        check(abs(speed - tall / 59.0) < 1e-4 * tall and s.frame_end == int(math.ceil(
            1 + float(s.mask[effect.P_REACH]) / speed - 1e-6)),
              "hand path: the front at a body height in 59 frames, the end frame where it is done (%d)" % s.frame_end)
        for ob in outfits:
            for m in our_modifiers(ob):
                m.show_viewport = False
        try:
            touches = motion.hand_touches(scene, arm, outfits, range(1, 61), ("L",), s.hand_reach)
            # a modifier after the armature that changes the vertices (a mask without its group leaves none) is off
            # while the hands are traced, and back on after
            masking = outfits[0].modifiers.new("MMDD Test Mask", "MASK")
            try:
                again = motion.hand_touches(scene, arm, outfits, range(1, 61), ("L",), s.hand_reach)
                back_on = masking.show_viewport
            finally:
                outfits[0].modifiers.remove(masking)
        finally:
            for ob in outfits:
                for m in our_modifiers(ob):
                    m.show_viewport = True
        check(back_on and all(np.array_equal(x, y) for x, y in zip(touches, again)),
              "hand path: a mask after the armature is off while the hands are traced, and back on after")
        late = []
        for ob, when in zip(outfits, touches):
            got = arrival_values(ob) * effect._object_scale(ob) - lead
            hit = np.isfinite(when)
            late.append(float((got[hit] - (when[hit] - 1.0) * speed).max()) if hit.any() else -1.0)
        scene.frame_set(1)
        wrist_bone, finger_bone = (motion.find_bone(arm, names) for names in (motion.WRISTS[0], motion.FINGERS[0]))
        wrist = np.array(arm.matrix_world @ wrist_bone.head)
        tip = wrist + 2.0 * (np.array(arm.matrix_world @ finger_bone.head) - wrist)
        firsts = []
        for ob in outfits:
            got = arrival_values(ob)
            mw = np.array(ob.matrix_world)
            firsts.append((float(got.min()) * effect._object_scale(ob),
                           (skinned(ob)[int(np.argmin(got))] @ mw[:3, :3].T + mw[:3, 3])))
        nearest = min(firsts, key=lambda x: x[0])[1]
        u = float(np.clip((nearest - wrist) @ (tip - wrist) / max(float((tip - wrist) @ (tip - wrist)), 1e-12), 0.0,
                          1.0))
        from_hand = float(np.linalg.norm(nearest - (wrist + u * (tip - wrist))))
        passed = int(sum(np.isfinite(w).sum() for w in touches))
        check(passed > 100 and max(late) < 1e-3 * height and from_hand < s.hand_reach + 0.01 * height,
              "hand path: the change comes first where the left hand is at the start (%.2f from it) and nowhere later "
              "than the hand passes (%d spots it passes)" % (from_hand, passed))
    finally:
        arm.animation_data.action = pose_action
        bpy.data.actions.remove(sweep)
        upper_arm.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        upper_arm.rotation_mode = modes[0]
    for key_, value in saved.items():
        setattr(s, key_, value)
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "rebuilt after the 1.10 checks")

    # --- 1.11: more moves of the dance, found in made-up motions (a 20 high model, 30 frames a second)
    def on_floor(t, h=20.0):
        """Standing: both feet on the floor, the hips and the neck at their height."""
        for side_, x in (("L", 0.05 * h), ("R", -0.05 * h)):
            t.ankle[side_][:] = (x, 0.0, 0.04 * h)
            t.toe[side_][:] = (x, -0.05 * h, 0.01 * h)
        t.hips[:] = (0.0, 0.0, 0.55 * h)
        t.neck[:] = (0.0, 0.0, 0.82 * h)
        return t

    squat, shallow = on_floor(made_up(80)), on_floor(made_up(80))
    for i in range(80):
        dip = max(0.0, 1.0 - abs(i - 40) / 10.0)
        squat.hips[i, 2] = (0.55 - 0.15 * dip) * H
        shallow.hips[i, 2] = (0.55 - 0.05 * dip) * H
    found = motion.find(squat, "SQUAT", H, FPS)
    check(found == (40, ("HIPS",)) and motion.find(shallow, "SQUAT", H, FPS) is None,
          "made-up squat found at its bottom (frame 40: %s); a dip of a twentieth of the height is none" % (found,))
    jump = on_floor(made_up(80))
    for i in range(30, 41):  # both feet off the floor from 31 to 39, highest at 35
        up_ = 0.2 * H * (1.0 - abs(i - 35) / 6.0)
        for side_ in "LR":
            jump.ankle[side_][i, 2] += up_
        jump.hips[i, 2] += up_
    found = motion.find(jump, "JUMP", H, FPS), motion.find(jump, "LAND", H, FPS)
    check(found == ((35, ("FEET",)), (40, ("FEET",))),
          "made-up jump: its top at frame 35, back on the floor at 40 (%s)" % (found,))
    step = on_floor(made_up(80))
    step.ankle["L"][20:30, 2] += 0.06 * H  # the left foot lifted from 20 to 29, put down at 30, at rest from 31
    found = motion.find(step, "STEP", H, FPS)
    check(found == (31, ("FOOT_L",)) and motion.find(on_floor(made_up(80)), "STEP", H, FPS) is None,
          "made-up footfall: the left foot comes to rest at 31 (%s); feet standing from the start are no footfall"
          % (found,))
    reach_up = on_floor(made_up(80))
    for i in range(50, 56):
        reach_up.wrist["R"][i] = (-0.1 * H, 0.0, (1.12 + 0.02 * (1.0 - abs(i - 52) / 3.0)) * H)
    found = motion.find(reach_up, "RAISE", H, FPS)
    check(found == (52, ("R",)), "made-up hand thrown up to the sky: highest at frame 52 (%s)" % (found,))

    def heart(frames, index=0.9, middle=0.3, gap=0.01):
        """The right thumb and forefinger tips `gap` apart above the chest in `frames`, the fingers stretched so."""
        t = made_up(80)
        for i in frames:
            t.wrist["R"][i] = (-0.05 * H, -0.1 * H, 0.75 * H)
            t.index["R"][i] = (-0.05 * H, -0.12 * H, 0.82 * H)
            t.thumb["R"][i] = t.index["R"][i] + (gap * H, 0.0, 0.0)
            t.stretch["index"]["R"][i], t.stretch["middle"]["R"][i] = index, middle
        return motion.find(t, "HEART", H, FPS)

    found = [heart(range(40, 50)), heart(range(40, 50), index=0.4), heart(range(40, 50), index=0.5, middle=1.0),
             heart(range(40, 44))]
    check(found == [(40, ("R",)), None, None, None],
          "made-up finger heart found at frame 40; a fist, an OK sign and a heart held too briefly are none (%s)"
          % (found,))
    both = made_up(80)
    for i in range(40, 50):
        for side_, x in (("L", 1.0), ("R", -1.0)):
            both.wrist[side_][i] = (0.06 * H * x, -0.1 * H, 0.75 * H)
            both.index[side_][i] = (0.005 * H * x, -0.12 * H, 0.8 * H)
            both.thumb[side_][i] = (0.005 * H * x, -0.12 * H, 0.74 * H)
    found = motion.find(both, "HEART", H, FPS)
    check(found == (40, ("L", "R")), "made-up heart of both hands at frame 40 (%s)" % (found,))
    winking = made_up(80)
    winking.wink["R"][45:52] = 1.0
    found = motion.find(winking, "WINK", H, FPS)
    check(found == (45, ("EYE_R",)), "made-up wink of the right eye at frame 45 (%s)" % (found,))
    pull = made_up(80)
    pull.neck[:] = (0.0, 0.0, 0.82 * H)
    for i in range(80):  # the left palm on the chest, snatched away to the side from frame 30 to 36
        away = 0.3 * H * min(1.0, max(0.0, (i - 30) / 6.0))
        pull.palm["L"][i] = (0.02 * H + away, -0.03 * H, 0.76 * H)
    found = motion.find(pull, "PULL", H, FPS)
    check(found is not None and found[1] == ("L",) and 20 <= found[0] <= 30,
          "made-up cord pulled with the left hand: at the chest before it snaps away at frame 30 (%s)" % (found,))

    # A wink read off the facial expressions: a wink morph of the right eye (made up here: the model has none), keyed
    # shut from frame 40 to 44, starts the transformation there.
    face = base.meshes[0]
    had_keys = face.data.shape_keys is not None
    keys_action = None
    if had_keys and face.data.shape_keys.animation_data is not None:
        keys_action = face.data.shape_keys.animation_data.action
    if not had_keys:
        face.shape_key_add(name="Basis", from_mix=False)
    morph = face.shape_key_add(name="ウィンク右", from_mix=False)
    keys = face.data.shape_keys
    try:
        for f, value in ((1, 0.0), (40, 0.0), (44, 1.0)):
            morph.value = value
            morph.keyframe_insert("value", frame=f)
        s.trigger, s.entrance, s.path, s.frame_start, s.frame_end = "WINK", "GROW", "SPHERE", 1, 100
        scene.frame_set(1)
        check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build to start on a wink")
        winked = s.mask.get(effect.P_TRIGGER)
        check(winked is not None and 41.0 <= winked <= 44.0 and s.frame_start == int(round(winked)),
              "wink: the right eye's wink found at frame %s (keyed shut from 40 to 44), the transformation starts "
              "there" % winked)
    finally:
        made = keys.animation_data.action if keys.animation_data is not None else None
        if keys.animation_data is not None:
            keys.animation_data.action = keys_action
        if made is not None and made != keys_action:
            bpy.data.actions.remove(made)
        face.shape_key_remove(morph)
        if not had_keys:
            face.shape_key_clear()
        s.trigger, s.frame_start, s.frame_end = "NONE", 1, 100

    # --- 1.11: the world change, the camera and time, cartoon physics, the split self and the figurine, the dance
    # ribbons, the picture's looks, the veils, the paper cut and the band of toon water
    saved = {key_: getattr(s, key_) for key_ in (
        "path", "seeds", "entrance", "exit_style", "particles", "easing", "finale", "frame_start", "frame_end",
        "trigger", "ring_enable", "ring_style", "old_surface", "holo_enable", "husk_style", "husk_away",
        "husk_motion", "wire_enable")}
    made_camera = None
    if scene.camera is None:  # (the world opens out past the camera, the moves ride on it)
        made_camera = bpy.data.objects.new("MMDD Test Camera", bpy.data.cameras.new("MMDD Test Camera"))
        scene.collection.objects.link(made_camera)
        made_camera.location = (float(centre_xy[0]), float(centre_xy[1]) - 2.5 * height, 0.55 * height)
        made_camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        scene.camera = made_camera
    user = scene.camera
    s.trigger, s.entrance, s.easing, s.path, s.exit_style, s.particles = "NONE", "SWAP", "LINEAR", "SPHERE", "SHRINK", \
        "NONE"
    s.finale, s.wire_enable, s.domain_enable = False, False, True
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build with the world change")
    check(not draw_panels(bpy.context), "panels draw with the world change")
    wave, moment, big = wave_and_moment()
    at_big = effect._big_frame(s, s.mask, wave)  # (what the camera moves, the time warps and the looks are timed on)
    worlds = domain.world_objects(s.mask)
    scene.frame_set(1)
    shut = evaluated_counts(worlds[0]) if worlds else -1
    scene.frame_set(at_big)
    opened = evaluated_counts(worlds[0]) if worlds else -1
    check(len(worlds) == 1 and shut == 0 and opened > 0,
          "world change: nothing of it at the start, the world there at the big moment (%d, %d vertices)"
          % (shut, opened))
    s.domain_enable = False
    check(not domain.world_objects(s.mask), "world change switched off: its object gone")
    # (the world staying after the moment stretched the mask's timeline: without it the moment comes later)
    at_big = effect._big_frame(s, s.mask, float(s.mask[effect.P_WAVE]))

    s.shot_enable, s.shot_style = True, "WHIP"
    marks = sorted((m.frame, m.camera.name if m.camera else None) for m in scene.timeline_markers
                   if m.name.startswith(camera_moves.MARKER))
    scene.frame_set(at_big)
    moving = scene.camera
    scene.frame_set(s.frame_end)
    after_ = scene.camera
    check(marks and moving != user and moving.get(camera_moves.P_SHOT) == s.mask and after_ == user,
          "whip pan: markers switch to a camera riding on the scene camera at the moment (frame %d: %s), back to it "
          "after (%s; markers %s)" % (at_big, moving.name if moving else None, after_.name if after_ else None, marks))
    check(not draw_panels(bpy.context), "panels draw with a camera move")
    s.shot_style = "CUTS"
    roles = sorted(ob.get(camera_moves.P_ROLE) for ob in camera_moves.shot_objects(s.mask))
    cut_marks = sorted((m.frame, m.camera.name if m.camera else None) for m in scene.timeline_markers
                       if m.name.startswith(camera_moves.MARKER))
    check(roles == ["EYES", "LOW", "WIDE"] and len(cut_marks) >= 4 and cut_marks[-1][1] == user.name,
          "ultimate cuts: a low angle, the eyes and a wide shot, then back to the scene camera (%s, %s)"
          % (roles, cut_marks))
    s.shot_enable = False
    scene.frame_set(at_big)
    check(not camera_moves.shot_objects(s.mask) and scene.camera is user
          and not any(m.name.startswith(camera_moves.MARKER) for m in scene.timeline_markers),
          "camera move off: our camera and markers gone, the scene camera back")

    swing = bpy.data.actions.new("MMDD Test Swing")
    try:  # the left arm swings down from frame 1 to 100 (a dance)
        arm.animation_data.action = swing
        upper_arm.rotation_mode = "QUATERNION"
        for f, angle in ((1, 60.0), (100, -40.0)):
            upper_arm.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(angle))
            upper_arm.keyframe_insert("rotation_quaternion", frame=f)

        def elbow(f):
            scene.frame_set(f)
            return round((arm.matrix_world @ upper_arm.tail).z, 4)

        s.time_warp, s.warp_length = "FREEZE", 0.6
        frozen = [elbow(f) for f in (at_big - 2, at_big, at_big + 2)]
        ad_ = arm.animation_data
        check(len(set(frozen)) == 1 and not draw_panels(bpy.context),
              "freeze: the dance stands still round the moment (frame %d: %s; action %s, tracks %s)"
              % (at_big, frozen, ad_.action.name if ad_.action else None, [t.name for t in ad_.nla_tracks]))
        s.time_warp = "NONE"
        going = [elbow(f) for f in (at_big - 2, at_big, at_big + 2)]
        check(len(set(going)) == 3 and arm.animation_data.action == swing and not arm.animation_data.nla_tracks,
              "time as it is again: the dance moves on, its action back in place (%s)" % going)

        s.trail_enable, s.trail_style = True, "LIGHT"
        trail = next(iter(trails.objects(s.mask, "TRAIL")), None)
        scene.frame_set(50)
        lit = evaluated_counts(trail) if trail else -1
        scene.frame_set(s.frame_end + 90)
        late = evaluated_counts(trail) if trail else -1
        check(trail is not None and len(trail.data.vertices) > 100 and lit > 0 and late == 0
              and not draw_panels(bpy.context),
              "dance ribbons: the hands' way recorded (%d points), a trail of light at frame 50, gone after the end"
              % (len(trail.data.vertices) if trail else 0))
        s.trail_style = "SASH"
        scene.frame_set(50)
        check(evaluated_counts(trail) > 0 and len(material_points(trail, materials.TRAIL_MATERIAL + " Sash")) > 0,
              "dance ribbons: the red silk sash drawn in its material")
        s.step_flowers = True
        check(len(trails.objects(s.mask, "STEPS")) == 1, "flowers underfoot: the footfalls object there")
        s.trail_enable = s.step_flowers = False
        check(not trails.objects(s.mask), "ribbons and flowers off: gone")
    finally:
        arm.animation_data.action = pose_action
        bpy.data.actions.remove(swing)
        upper_arm.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        upper_arm.rotation_mode = modes[0]
        s.time_warp, s.trail_enable, s.step_flowers = "NONE", False, False

    s.toon_style = "SQUASH"
    landing = effect._big_frame(s, s.mask, float(s.mask[effect.P_WAVE]))
    scene.frame_set(int(math.ceil(effect._frame_at(s.mask, big) - 1e-6)))
    squashed = world_vertices(new_mesh)[0]
    tall_now = float(np.ptp(squashed[:, 2])) if len(squashed) else -1.0
    check(len(toon.anchors(s.mask)) == 1 and 0.0 < tall_now < 0.6 * height and not draw_panels(bpy.context),
          "squash: the body pressed flat at the moment (%.1f of %.1f tall)" % (tall_now, height))
    s.toon_style = "NONE"
    check(not toon.anchors(s.mask), "cartoon physics off: the anchor gone (big frame %s)" % landing)
    rest_z = arm.matrix_world.translation.z
    s.float_up = True
    scene.frame_set(max(2, (s.frame_start + at_big) // 2))
    lifted = arm.matrix_world.translation.z - rest_z
    s.float_up = False
    scene.frame_set(max(2, (s.frame_start + at_big) // 2))
    check(lifted > 0.05 * height and abs(arm.matrix_world.translation.z - rest_z) < 1e-5 * height
          and not (arm.animation_data and arm.animation_data.drivers.find("delta_location", index=2)),
          "float up: the dancer floats up on the way to the moment (%.2f), back down when it is off" % lifted)

    s.exit_style, s.husk_style, s.husk_motion, s.husk_away = "HUSK", "ASIS", "DANCE", "CRUMBLE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the split self")
    at_big = effect._big_frame(s, s.mask, float(s.mask[effect.P_WAVE]))
    scene.frame_set(at_big + 15)
    old_pts, new_pts = world_vertices(old_mesh)[0], world_vertices(new_mesh)[0]
    apart = float(abs(old_pts[:, 0].mean() - new_pts[:, 0].mean())) if len(old_pts) and len(new_pts) else 0.0
    check(apart > 0.2 * height and not draw_panels(bpy.context),
          "split self: the old self dances on beside the new one (%.1f apart)" % apart)
    s.husk_motion, s.husk_style, s.husk_away = "STILL", "PVC", "FIGURINE"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the figurine")
    scene.frame_set(at_big + 120)
    figure, husk_ = world_vertices(old_mesh, ATTR_HUSK)
    figure = figure[husk_ > 0.5]  # (the dancer's head and hair are the old mesh's too)
    small = float(np.ptp(figure[:, 2])) if len(figure) else -1.0
    check(0.0 < small < 0.3 * height and bpy.data.materials.get(materials.STAND_MATERIAL) is not None,
          "figurine: the old self a small figure on a stand afterwards (%.2f tall)" % small)
    s.exit_style, s.husk_style, s.husk_away, s.husk_motion = "SHRINK", "AMBER", "CRUMBLE", "STILL"

    s.look_style = "SILHOUETTE"
    at_big = effect._big_frame(s, s.mask, float(s.mask[effect.P_WAVE]))
    tree = compositor._existing_tree(scene)
    look = tree.nodes.get(compositor.LOOK) if tree is not None else None
    looks_driven = [d for d in (tree.animation_data.drivers if tree is not None and tree.animation_data else [])
                    if compositor.LOOK in d.data_path]
    scene.frame_set(1)
    off_ = compositor._flash_factor(look).default_value if look else -1.0
    scene.frame_set(at_big + 1)
    on_ = compositor._flash_factor(look).default_value if look else -1.0
    check(look is not None and len(looks_driven) == 1 and looks_driven[0].driver.is_simple_expression
          and any(n.bl_idname == "CompositorNodeCryptomatteV2" for n in compositor._look_nodes(tree))
          and off_ == 0.0 and on_ == 1.0 and not draw_panels(bpy.context),
          "silhouette: the look spliced into the compositor, on round the moment only (%s at 1, %s at %d; %s)"
          % (off_, on_, at_big + 1, [d.driver.expression for d in looks_driven]))
    s.look_style = "SONG"
    check(sum(n.name == compositor.LOOK for n in tree.nodes) == 1
          and any(n.bl_idname == "CompositorNodeBoxMask" for n in compositor._look_nodes(tree)),
          "old painting: the look rebuilt in its own style")
    s.look_style = "NONE"
    outputs = [n for n in tree.nodes if n.bl_idname in ("CompositorNodeComposite", "NodeGroupOutput")]
    check(not compositor._look_nodes(tree) and outputs and outputs[0].inputs[0].links,
          "look off: taken out of the compositor, the picture joined up again")

    s.holo_enable = True
    for style in ("STARS", "SHADOW", "ICE", "SCAN"):
        s.holo_style = style
        mats = set(effect._glow_materials(new_mesh, s))
        check(mats and all(m.get(materials.P_HOLO) == style for m in mats), "veil: %s on the new outfit" % style)
    s.holo_enable = False
    check(not any(m.get(materials.P_HOLO) for m in effect._glow_materials(new_mesh, s)), "veil off: gone")

    blends = {m.name: getattr(m, "blend_method", None) for m in effect._glow_materials(old_mesh, s)}
    s.old_surface, s.particles = "PAPERCUT", "PAPER_BIRD"
    mats = set(effect._glow_materials(old_mesh, s))
    bird = bpy.data.objects.get(particles.PAPER_BIRD)
    check(mats and all(m.get(materials.P_SURFACE) == "PAPERCUT" for m in mats) and bird is not None
          and bird.data.materials[0].name == materials.PAPER_MATERIAL and not draw_panels(bpy.context),
          "paper cut over the old outfit, red paper birds")
    s.old_surface, s.particles = "NONE", "NONE"
    check(all(getattr(m, "blend_method", None) == blends[m.name] and not m.get(materials.P_SURFACE)
              for m in effect._glow_materials(old_mesh, s)), "paper cut off: the old outfit's materials as they were")

    s.path, s.ring_enable, s.ring_style, s.entrance = "SPIRAL", True, "WATER", "GROW"
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "build the spiral with the band of toon water")
    band = rings.ring_objects(s.mask)
    scene.frame_set(50)
    check(len(band) == 1 and len(material_points(band[0], materials.WATER_RING_MATERIAL)) > 100,
          "toon water: a band of water at the front of the spiral")
    s.ring_enable = False
    if made_camera is not None:
        scene.camera = None
        bpy.data.objects.remove(made_camera)
    for key_, value in saved.items():
        setattr(s, key_, value)
    check(bpy.ops.mmd_disperse.build() == {"FINISHED"}, "rebuilt after the 1.11 checks")

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
        s.frame_start, s.frame_end = 1, 100  # (a move of the dance or the hands' pace moves them)
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
        if key in ("CLAP", "TURN", "HAND_SWIPE"):
            started = {"CLAP": s.trigger == "CLAP" and s.path == "SURFACE",
                       "TURN": s.trigger == "TURN" and s.entrance == "SWAP", "HAND_SWIPE": s.path == "HAND"}
            check(started[key], "%s preset: set off by the dance" % key)
        if key in ("BLUE_FLAME", "PHOENIX", "SUPER_AURA"):
            check(s.flame_enable and s.flame_mode == ("EDGE" if key == "PHOENIX" else "AURA")
                  and bpy.data.materials.get(materials.FLAME_MATERIAL) is not None,
                  "%s preset: toon flames (%s)" % (key, s.flame_mode.lower()))
        if key in ("CLAP", "BLUE_FLAME", "SUPER_AURA", "HUSK", "IMPACT"):
            tree = compositor._existing_tree(scene)
            check(s.impact_enable and tree is not None and tree.nodes.get(compositor.IMPACT_GREY) is not None
                  and tree.nodes.get(compositor.IMPACT_INVERT) is not None, "%s preset: impact frames" % key)
        if key == "LOTUS":
            check(s.entrance == "LOTUS" and s.easing == "LINEAR", "lotus preset: the lotus on a linear timeline")
        if key in ("HUSK", "SOUL_DEPART"):
            check(s.exit_style == "HUSK" and s.husk_away == ("CRUMBLE" if key == "HUSK" else "FLOAT")
                  and effect._recording(s, "BASE"), "%s preset: the old self left behind as a husk" % key)
        if key == "DANNY":
            check(s.path == "MIDDLE" and s.ring_enable and s.ring_style == "HALO"
                  and len(rings.ring_objects(s.mask)) == 1, "two rings preset: rings of light from the waist")
        if key == "IDOL":
            check(s.path == "GARMENTS" and s.garment_order == "DOWN", "idol preset: garment by garment from the top")
        if key == "SOUL_RINGS":
            check(s.soul_enable and s.soul_count == 7, "soul rings preset: seven soul rings")
        if key in ("DOMAIN", "CRIMSON", "FLOWER_FIELD", "SKY_MIRROR", "CONCERT"):
            check(s.domain_enable and len(domain.world_objects(s.mask)) == 1, "%s preset: the %s world opens"
                  % (key, s.domain_style.lower()))
        if key in ("BULLET_TIME", "VELOCITY"):
            check(s.time_warp == ("FREEZE" if key == "BULLET_TIME" else "SLOW") and s.shot_enable,
                  "%s preset: time %s, a camera move" % (key, s.time_warp.lower()))
        if key in ("CONCERT", "SLEEVES", "NEZHA"):
            check(s.trail_enable and len(trails.objects(s.mask, "TRAIL")) == 1, "%s preset: dance ribbons (%s)"
                  % (key, s.trail_style.lower()))
        if key in ("SQUISH", "PAPER_FLIP", "CARD_FLIP"):
            check(s.toon_style != "NONE" and s.entrance in effect.AT_ONCE and len(toon.anchors(s.mask)) == 1,
                  "%s preset: cartoon physics (%s)" % (key, s.toon_style.lower()))
        if key in ("SPLIT", "FIGURINE"):
            check(s.exit_style == "HUSK" and (s.husk_motion == "DANCE" if key == "SPLIT" else s.husk_away == "FIGURINE"),
                  "%s preset: the old self left beside the dancer" % key)
        if key in ("SILHOUETTE", "SONG_PAINTING"):
            tree = compositor._existing_tree(scene)
            check(tree is not None and tree.nodes.get(compositor.LOOK) is not None, "%s preset: the picture's look"
                  % key)
        if key == "STARRY_VEIL":
            check(all(m.get(materials.P_HOLO) == "STARS" for m in effect._glow_materials(target.meshes[0], s)),
                  "starry veil preset: the veil of stars on the new outfit")
        if key == "PAPER_CUT":
            check(s.old_surface == "PAPERCUT" and bpy.data.objects.get(particles.PAPER_BIRD) is not None,
                  "paper cut preset: the paper cut, paper birds")
        if key == "WATER_BREATHING":
            check(s.ring_style == "WATER" and len(rings.ring_objects(s.mask)) == 1,
                  "water breathing preset: the band of toon water")
    s.beat_sync = False  # (the beat drop preset turned it on; the finale checks below are not on the beat)
    s.frame_start, s.frame_end = 1, 100
    check(bpy.ops.mmd_disperse.apply_preset(preset="MAGICAL") == {"FINISHED"}, "magical girl preset again (the 1.11 "
          "presets came after it)")
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
