"""End-to-end test: Tifa (Gantz) V2 -> V1 suit-up, rendered headless.

blender -b "Tifa Gantz 18 V2.blend" --factory-startup --python tests/test_tifa.py -- \
    --target-blend "Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" \
    --base-root "Tifa Gantz 18 V2" --out test_output/run1

or, importing the PMX files with mmd_tools (e.g. on Blender 3.6):

blender -b --factory-startup --python tests/test_tifa.py -- \
    --pmx "Tifa Gantz 18 V2.pmx" "Tifa Gantz 18 V1.pmx" --out test_output/run1
"""

import argparse
import math
import os
import sys
import time

import bpy
from mathutils import Euler, Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import compositor, effect  # noqa: E402
from mmd_disperse.model import resolve, rest_bounds  # noqa: E402
from scene_setup import add_model_args, apply_settings, load_models  # noqa: E402

TIFA_LOCK = "Face*;Hair*;Eye*;*Brows*;Eyelashes*;Mouth*;*Teeth*;Inners*"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    add_model_args(p)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", default="1,20,35,50,65,80,100")
    p.add_argument("--close-frames", default="")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=100)
    p.add_argument("--space", default="REST")
    p.add_argument("--lock", action="store_true")
    p.add_argument("--motion", action="store_true")
    p.add_argument("--bloom", action="store_true")
    p.add_argument("--res", type=int, default=720)
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--anim", default="", help="render frames a:b:step to an image sequence")
    p.add_argument("--anim-cam", default="full", choices=("full", "close"))
    p.add_argument("--save", default="")
    p.add_argument("--set", action="append", default=[], help="override a setting, e.g. edge_push=0.5 or path=SURFACE")
    return p.parse_args(argv)


def pose_motion(armature, start, end):
    """A simple sway so we can see that the effect follows the deformation."""
    bones = armature.pose.bones

    def key(name, frame, euler):
        pb = bones.get(name)
        if pb is None:
            return
        if pb.rotation_mode == "QUATERNION":
            pb.rotation_quaternion = Euler(euler).to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=frame)
        else:
            pb.rotation_euler = euler
            pb.keyframe_insert("rotation_euler", frame=frame)

    mid = (start + end) // 2
    for frame, sign in ((start, 0.0), (mid, 1.0), (end, -1.0)):
        key("上半身", frame, (0.0, math.radians(18) * sign, 0.0))
        key("首", frame, (math.radians(-10) * sign, 0.0, 0.0))
        for arm, s in (("腕.L", 1.0), ("腕.R", -1.0)):
            key(arm, frame, (0.0, 0.0, math.radians(-25) * s * abs(sign)))


def setup_render(scene, res, samples, bounds):
    lo, hi = bounds
    center = (lo + hi) / 2
    height = hi.z - lo.z
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = samples
    scene.render.resolution_x = res * 9 // 16
    scene.render.resolution_y = res
    if hasattr(scene.render.image_settings, "media_type"):  # Blender 5.0+
        scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.02, 0.022, 0.03, 1.0)
    bg.inputs[1].default_value = 1.0

    sun = bpy.data.objects.new("Test Sun", bpy.data.lights.new("Test Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(-30))
    scene.collection.objects.link(sun)

    cams = {}
    for name, target_z, view_h in (("full", center.z, height * 1.12), ("close", lo.z + height * 0.78, height * 0.42)):
        cam = bpy.data.objects.new("Test Cam " + name, bpy.data.cameras.new(name))
        cam.data.sensor_fit = "VERTICAL"
        cam.data.lens = 85
        dist = view_h / (cam.data.sensor_height / cam.data.lens)
        cam.location = (center.x + dist * 0.25, center.y - dist, target_z)
        direction = Vector((center.x, center.y, target_z)) - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(cam)
        cams[name] = cam
    return cams


def evaluated_stats(ob):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        mats = [m.name if m else None for m in me.materials]
        attrs = sorted(a.name for a in me.attributes if not a.name.startswith("."))
        return len(me.vertices), len(me.polygons), mats, attrs
    finally:
        ev.to_mesh_clear()


def main():
    args = parse_args()
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    mmd_disperse.register()
    scene = bpy.context.scene

    base_root, target_root = load_models(args)
    base = resolve(base_root)
    target = resolve(target_root)
    print("BASE meshes", [m.name for m in base.meshes], "armature", base.armature.name)
    print("TARGET meshes", [m.name for m in target.meshes], "armature", target.armature.name)

    if args.motion:
        pose_motion(base.armature, args.start, args.end)

    s = scene.mmd_disperse
    s.base = base_root
    s.target = target_root
    s.origin_mode = "BONE"
    s.space = args.space
    s.frame_start = args.start
    s.frame_end = args.end
    s.use_lock = args.lock
    if args.lock:
        s.lock_patterns = TIFA_LOCK

    apply_settings(s, args.set)  # build-time options (path, exit style ...)
    t0 = time.time()
    result = bpy.ops.mmd_disperse.build()
    print("BUILD", result, "in %.2fs" % (time.time() - t0))
    apply_settings(s, args.set)  # sizes again: the first build fits them to the model
    print("SETTINGS", {k: round(getattr(s, k), 4) for k in (
        "noise_scale", "noise_amount", "edge_width", "edge_push", "wire_inner", "wire_outer",
        "wire_radius", "wire_lift", "base_shrink", "base_delete_offset")})
    mask = s.mask
    print("MASK", mask.name, "location", tuple(round(v, 3) for v in mask.location))
    for ob in target.meshes + base.meshes:
        print("MODS", ob.name, [(m.type, m.name) for m in ob.modifiers],
              "arm ->", [m.object.name for m in ob.modifiers if m.type == "ARMATURE"])

    frames = [int(f) for f in args.frames.split(",") if f]
    for f in frames:
        t0 = time.time()
        scene.frame_set(f)
        dt = time.time() - t0
        tv, tf, tmats, tattrs = evaluated_stats(target.meshes[0])
        bv, bf, _, _ = evaluated_stats(base.meshes[0])
        print("FRAME %3d radius %.2f  eval %.2fs  target %7d v %7d f  base %7d v %7d f  wire mat %s" % (
            f, mask.scale.x, dt, tv, tf, bv, bf, [i for i, m in enumerate(tmats) if m == effect.WIRE_MATERIAL]))
    print("TARGET MATS", tmats)
    print("TARGET ATTRS", tattrs)

    bounds = rest_bounds(base.meshes or target.meshes)
    cams = setup_render(scene, args.res, args.samples, bounds)
    if args.bloom:
        compositor.add_bloom(scene)

    for f in frames:
        scene.frame_set(f)
        scene.camera = cams["full"]
        scene.render.filepath = os.path.join(args.out, "full_%03d.png" % f)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("RENDER full", f, "%.1fs" % (time.time() - t0))
    for f in [int(x) for x in args.close_frames.split(",") if x]:
        scene.frame_set(f)
        scene.camera = cams["close"]
        scene.render.filepath = os.path.join(args.out, "close_%03d.png" % f)
        bpy.ops.render.render(write_still=True)
        print("RENDER close", f)

    if args.anim:
        a, b, step = (int(x) for x in args.anim.split(":"))
        scene.camera = cams[args.anim_cam]
        for f in range(a, b + 1, step):
            scene.frame_set(f)
            scene.render.filepath = os.path.join(args.out, "anim_" + args.anim_cam, "%04d.png" % f)
            bpy.ops.render.render(write_still=True)
        print("ANIM done")

    if args.save:
        scene.camera = cams["full"]
        scene.frame_set(args.start + (args.end - args.start) // 4)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save), copy=True)
        print("SAVED", args.save)


main()
