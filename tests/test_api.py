"""Headless checks: build / rebuild / sync / remove restore everything, both directions, no-base mode.

blender -b "Tifa Gantz 18 V2.blend" --factory-startup --python tests/test_api.py -- \
    --target-blend "Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2"
"""

import argparse
import math
import os
import sys
import traceback

import bpy
import numpy as np
from mathutils import Matrix

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import compositor, effect, launch, materials, particles, presets, ribbons  # noqa: E402
from mmd_disperse.arrival import limb_points  # noqa: E402
from mmd_disperse.model import resolve, rest_points_world  # noqa: E402
from mmd_disperse.node_groups import (ATTR_ARRIVAL, ATTR_CUT, ATTR_EDGE, ATTR_HOLO, ATTR_LAYER,  # noqa: E402
                                      ATTR_LOCK, BASE_GROUP, TARGET_GROUP, input_identifiers)
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


def instance_positions(ob):
    """World positions of the instances (stars, petals ...) `ob` makes, in their order."""
    deps = bpy.context.evaluated_depsgraph_get()
    return np.array([tuple(inst.matrix_world.translation) for inst in deps.object_instances
                     if inst.is_instance and inst.parent is not None and inst.parent.original == ob]).reshape(-1, 3)


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


def arrival_values(ob):
    attr = ob.data.attributes.get(ATTR_ARRIVAL)
    if attr is None:
        return None
    values = np.zeros(len(attr.data), dtype=np.float32)
    attr.data.foreach_get("value", values)
    return values


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
    s.entrance, s.exit_style = "GROW", "SHRINK"

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
        if key == "NANO_FINALE":
            check(s.layer_enable and s.inner_glow and s.finale_style == "SWEEP" and white_flash(scene)[0] is not None
                  and len(white_flash(scene)[1]) == 1, "nanotech finale: undersuit, light sweep and the white flash")
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
