"""Headless checks: build / rebuild / sync / remove restore everything, both directions, no-base mode.

blender -b "Tifa Gantz 18 V2.blend" --factory-startup --python tests/test_api.py -- \
    --target-blend "Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2"
"""

import argparse
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import effect, materials  # noqa: E402
from mmd_disperse.model import resolve  # noqa: E402
from mmd_disperse.node_groups import ATTR_LOCK, BASE_GROUP, TARGET_GROUP, input_identifiers  # noqa: E402
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

    mmd_disperse.unregister()
    check(not hasattr(bpy.types.Scene, "mmd_disperse"), "unregistered cleanly")


try:
    run()
except Exception:
    traceback.print_exc()
    FAILURES.append("exception")
print("RESULT", "OK" if not FAILURES else "FAILED: %s" % FAILURES)
