"""Headless checks: build / rebuild / sync / remove restore everything, both directions, no-base mode.

blender -b "Tifa Gantz 18 V2.blend" --factory-startup --python tests/test_api.py -- \
    --target-blend "Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2"
"""

import argparse
import os
import sys
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import effect, materials, particles  # noqa: E402
from mmd_disperse.arrival import limb_points  # noqa: E402
from mmd_disperse.model import resolve, rest_points_world  # noqa: E402
from mmd_disperse.node_groups import (ATTR_ARRIVAL, ATTR_EDGE, ATTR_LOCK, BASE_GROUP, TARGET_GROUP,  # noqa: E402
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
    """Stands in for UILayout so panel draw() code runs headless; validates names it is given."""

    def __init__(self):
        self.errors = []

    def _child(self, **_kw):
        child = FakeLayout()
        child.errors = self.errors
        return child

    row = column = box = _child

    def separator(self, **_kw):
        pass

    def label(self, **_kw):
        pass

    def prop(self, data, name, **_kw):
        if name not in data.bl_rna.properties:
            self.errors.append("prop " + name)

    def prop_search(self, data, name, search_data, search_name, **_kw):
        self.prop(data, name)
        if search_name not in search_data.bl_rna.properties:
            self.errors.append("search " + search_name)

    def operator(self, idname, **_kw):
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


def evaluated_faces_and_edge(ob):
    """Face count of the evaluated mesh and the largest disperse_edge value on it (glowing flakes)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        attr = me.attributes.get(ATTR_EDGE)
        top = 0.0
        if attr is not None and len(attr.data):
            values = np.zeros(len(attr.data), dtype=np.float32)
            attr.data.foreach_get("value", values)
            top = float(values.max())
        return len(me.polygons), top
    finally:
        ev.to_mesh_clear()


def instance_count(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    return sum(1 for inst in deps.object_instances
               if inst.is_instance and inst.parent is not None and inst.parent.original == ob)


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
    check(abs(target_root.location.x - base_root.location.x) < 1e-6, "new outfit snapped onto the old one")
    for ob in target.meshes + base.meshes:
        check(len(our_modifiers(ob)) == 1, "one effect modifier on " + ob.name)
        names = [m.type for m in ob.modifiers]
        check(names.index("NODES") == names.index("ARMATURE") + 1, "modifier right after armature on " + ob.name)
        check(ob.data.attributes.get(ATTR_LOCK) is not None, "lock attribute on " + ob.name)
    for ob in target.meshes:
        arms = [m.object for m in ob.modifiers if m.type == "ARMATURE"]
        check(arms == [base.armature], "new outfit bound to the old armature")
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

    # --- remove restores everything (attributes, materials, particle shapes)
    check(bpy.ops.mmd_disperse.remove() == {"FINISHED"}, "remove after the new paths")
    after = snapshot([base, target])
    check(all(before[k] == after[k] for k in before), "models restored after flakes, sweeps and petals")
    check(not any(bpy.data.objects.get(n) for n in particles.NAMES.values()), "particle shapes removed")

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
