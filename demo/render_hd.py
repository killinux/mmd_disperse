"""HD showcase render of the suit-up effect (Tifa Gantz V2 -> V1).

Rebuilds the MMD toon materials as PBR (Principled BSDF) using the full texture set that ships with
the model (normal / roughness / metallic maps the PMX materials cannot use), lights the scene and renders
a 1080x1920 sequence.

blender -b "Tifa Gantz 18 V2.blend" --factory-startup --python demo/render_hd.py -- \
    --target-blend "Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" \
    --base-root "Tifa Gantz 18 V2" --out test_output/hd --frames 1,100,200
"""

import argparse
import math
import os
import re
import sys
import time

import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import mmd_disperse  # noqa: E402
from mmd_disperse import compositor  # noqa: E402
from mmd_disperse.model import resolve, rest_bounds  # noqa: E402
from scene_setup import add_model_args, load_models  # noqa: E402

TIFA_LOCK = "Face*;Hair*;Eye*;*Brows*;Eyelashes*;Mouth*;*Teeth*;Inners*"
NORMAL_NAME = re.compile(r"n(or)?m|nrm|[ _]n[ _.]|n_ao|mapn")  # CSuit_Body_norm, Arms_N, Tifa Head N_AO ...

# Per-surface Principled settings; maps found next to the base texture override roughness/metallic.
SURFACES = {
    "skin": dict(roughness=0.45, subsurface=0.12, normal=0.8),
    "hair": dict(roughness=0.6, specular=0.2, value=0.55, normal=0.5),
    "eye": dict(roughness=0.05, coat=1.0, normal=0.5),
    "mouth": dict(roughness=0.3, normal=0.6),
    "latex": dict(roughness=0.22, coat=0.6, coat_roughness=0.08, normal=0.25),
    "suit": dict(roughness=0.4, normal=1.0),
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    add_model_args(p)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", default="", help="stills, e.g. 1,100,200")
    p.add_argument("--anim", default="", help="sequence a:b")
    p.add_argument("--length", type=int, default=200)
    p.add_argument("--wave", default="10:185", help="first:last frame of the transformation")
    p.add_argument("--res", type=int, default=1920)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--orbit", type=float, default=12.0, help="camera orbit half-angle in degrees")
    p.add_argument("--save", default="")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- HD materials

def surface_kind(base_name):
    n = base_name.lower()
    if "hair" in n:
        return "hair"
    if "eye" in n:
        return "eye"
    if "mouth" in n:
        return "mouth"
    if "leather" in n:
        return "latex"
    if n.startswith(("tifa", "gens")):
        return "skin"
    return "suit"


def sibling_image(image, suffixes):
    """Find e.g. CSuit_Body_rough.jpg next to CSuit_Body_tex.jpg."""
    path = bpy.path.abspath(image.filepath)
    folder, name = os.path.split(path)
    stem = name.rsplit(".", 1)[0]
    for cut in ("_tex", "_metallic", "_metal", "_basecolor", "_base", "_C", "_D"):
        if stem.endswith(cut):
            stem = stem[: -len(cut)]
            break
    for suffix in suffixes:
        for ext in (".jpg", ".png"):
            candidate = os.path.join(folder, stem + suffix + ext)
            if os.path.exists(candidate):
                return bpy.data.images.load(candidate, check_existing=True)
    return None


def data_image(image):
    image.colorspace_settings.name = "Non-Color"
    return image


def hd_material(mat):
    """Turn an mmd_tools material into a Principled BSDF using every map we can find."""
    nt = mat.node_tree
    base_node = nt.nodes.get("mmd_base_tex")
    sphere_node = nt.nodes.get("mmd_sphere_tex")
    if base_node is None or base_node.image is None:
        return None
    base = base_node.image
    normal = sphere_node.image if sphere_node is not None else None
    if normal is not None and not NORMAL_NAME.search(normal.name.lower()):
        normal = None
    png = os.path.splitext(bpy.path.abspath(base.filepath))[0] + ".png"
    if base.name.lower().endswith(".jpg") and os.path.exists(png):  # eyelashes: lossless PNG with alpha
        base = bpy.data.images.load(png, check_existing=True)
    kind = surface_kind(base.name)
    cfg = SURFACES[kind]
    # Latex keeps a constant gloss; the leather roughness map is far too matte for it.
    rough = None if kind == "latex" else sibling_image(base, ("_rough", "_roughness"))
    metal = None if "met" in base.name.lower() else sibling_image(base, ("_met", "_metal", "_metallic"))

    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (350, 0)
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.location = (-700, 0)
    uv.uv_map = "UVMap"

    def tex(image, y, name=None):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.location = (-400, y)
        if name:
            node.name = name
        nt.links.new(uv.outputs["UV"], node.inputs["Vector"])
        return node

    color = tex(base, 300, "mmd_base_tex")  # name kept: the add-on masks its rim glow with this alpha
    if "value" in cfg:  # hair cards read silver under studio light; darken to the MMD look
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.location = (-100, 400)
        hsv.inputs["Value"].default_value = cfg["value"]
        nt.links.new(color.outputs["Color"], hsv.inputs["Color"])
        nt.links.new(hsv.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        nt.links.new(color.outputs["Color"], bsdf.inputs["Base Color"])
    if "specular" in cfg:
        bsdf.inputs["Specular IOR Level"].default_value = cfg["specular"]
    if kind in ("hair", "eye") or base.name.lower().endswith(".png"):
        nt.links.new(color.outputs["Alpha"], bsdf.inputs["Alpha"])
    if rough is not None:
        nt.links.new(tex(data_image(rough), 0).outputs["Color"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = cfg["roughness"]
    if metal is not None:
        nt.links.new(tex(data_image(metal), -300).outputs["Color"], bsdf.inputs["Metallic"])
    if normal is not None:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (100, -400)
        nmap.uv_map = "UVMap"
        nmap.inputs["Strength"].default_value = cfg["normal"]
        nt.links.new(tex(data_image(normal), -600).outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if kind == "skin":
        bsdf.inputs["Subsurface Weight"].default_value = cfg["subsurface"]
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        bsdf.inputs["Subsurface Scale"].default_value = 0.12  # ~1 cm on this 20.7-unit model
    if "coat" in cfg:
        bsdf.inputs["Coat Weight"].default_value = cfg["coat"]
        bsdf.inputs["Coat Roughness"].default_value = cfg.get("coat_roughness", 0.03)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return kind


def upgrade_materials(meshes):
    done = {}
    for ob in meshes:
        for slot in ob.material_slots:
            mat = slot.material
            if mat is not None and mat.name not in done and mat.node_tree is not None:
                done[mat.name] = hd_material(mat)
    return done


# --------------------------------------------------------------------------- stage

def setup_stage(scene, bounds, args):
    lo, hi = bounds
    center = (lo + hi) / 2
    height = hi.z - lo.z

    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    ee = scene.eevee
    ee.taa_render_samples = args.samples
    if hasattr(ee, "use_raytracing"):
        ee.use_raytracing = True
    scene.render.resolution_x = args.res * 9 // 16
    scene.render.resolution_y = args.res
    scene.render.film_transparent = False
    if hasattr(scene.render.image_settings, "media_type"):
        scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.frame_start, scene.frame_end = 1, args.length

    # World: studio HDRI for reflections, near-black background for the camera.
    world = bpy.data.worlds.new("HD World")
    scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    hdri = os.path.join(bpy.utils.system_resource("DATAFILES", path="studiolights/world"), "studio.exr")
    env.image = bpy.data.images.load(hdri, check_existing=True)
    light_bg = nt.nodes.new("ShaderNodeBackground")
    light_bg.inputs["Strength"].default_value = 0.35
    dark_bg = nt.nodes.new("ShaderNodeBackground")
    dark_bg.inputs["Color"].default_value = (0.006, 0.007, 0.01, 1.0)
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(env.outputs["Color"], light_bg.inputs["Color"])
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(light_bg.outputs[0], mix.inputs[1])
    nt.links.new(dark_bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])

    def sun(name, energy, color, rot, angle=4.0):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        light.data.energy = energy
        light.data.color = color
        light.data.angle = math.radians(angle)
        light.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(light)

    sun("Key", 3.2, (1.0, 0.96, 0.92), (52, 0, -28), 6.0)
    sun("Rim Left", 4.0, (0.45, 0.8, 1.0), (75, 0, -150))
    sun("Rim Right", 3.0, (0.6, 0.75, 1.0), (75, 0, 150))

    # Dark glossy floor that picks up the glow.
    bpy.ops.mesh.primitive_plane_add(size=height * 8, location=(center.x, center.y, lo.z))
    floor = bpy.context.active_object
    floor.name = "Floor"
    fmat = bpy.data.materials.new("Floor")
    if fmat.node_tree is None:
        fmat.use_nodes = True
    fbsdf = fmat.node_tree.nodes.get("Principled BSDF")
    fbsdf.inputs["Base Color"].default_value = (0.015, 0.016, 0.02, 1.0)
    fbsdf.inputs["Roughness"].default_value = 0.28
    floor.data.materials.append(fmat)

    # Camera on a slow orbit around the character.
    pivot = bpy.data.objects.new("Camera Pivot", None)
    pivot.location = (center.x, center.y, lo.z)
    scene.collection.objects.link(pivot)
    cam = bpy.data.objects.new("HD Camera", bpy.data.cameras.new("HD Camera"))
    cam.data.lens = 85
    cam.data.sensor_fit = "VERTICAL"
    view_h = height * 1.1
    dist = view_h / (cam.data.sensor_height / cam.data.lens)
    aim = Vector((0.0, 0.0, height * 0.5))
    cam.location = Vector((0.0, -dist, height * 0.52))
    cam.rotation_euler = (aim - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.parent = pivot
    scene.collection.objects.link(cam)
    scene.camera = cam
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "BEZIER"
    for frame, angle in ((1, -args.orbit), (args.length, args.orbit)):
        pivot.rotation_euler = (0.0, 0.0, math.radians(angle))
        pivot.keyframe_insert("rotation_euler", index=2, frame=frame)
    prefs.keyframe_new_interpolation_type = old


def main():
    args = parse_args()
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    mmd_disperse.register()
    scene = bpy.context.scene

    base_root, target_root = load_models(args)
    base, target = resolve(base_root), resolve(target_root)
    kinds = upgrade_materials(base.meshes + target.meshes)
    print("HD MATERIALS", kinds)

    s = scene.mmd_disperse
    s.base, s.target = base_root, target_root
    s.frame_start, s.frame_end = (int(v) for v in args.wave.split(":"))
    s.use_lock = True
    s.lock_patterns = TIFA_LOCK
    print("BUILD", bpy.ops.mmd_disperse.build())

    setup_stage(scene, rest_bounds(base.meshes), args)
    compositor.add_bloom(scene)

    frames = [int(f) for f in args.frames.split(",") if f]
    if args.anim:
        a, b = (int(v) for v in args.anim.split(":"))
        frames += list(range(a, b + 1))
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(args.out, "%04d.png" % f)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("RENDER %d %.1fs" % (f, time.time() - t0), flush=True)

    if args.save:
        scene.frame_set(s.frame_start + (s.frame_end - s.frame_start) // 3)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save), copy=True)
        print("SAVED", args.save)


main()
