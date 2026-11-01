"""Load the old and new outfit for the tests: append from .blend files, or import PMX with mmd_tools."""

import addon_utils
import bpy


def add_model_args(parser):
    parser.add_argument("--target-blend", help="append the new outfit from this .blend (old outfit = opened file)")
    parser.add_argument("--target-root", help="root object of the new outfit inside --target-blend")
    parser.add_argument("--base-root", help="root object of the old outfit in the opened file")
    parser.add_argument("--pmx", nargs=2, metavar=("OLD", "NEW"), help="import both outfits with mmd_tools")
    parser.add_argument("--toon-dir", help="folder with MMD shared toons (toon01.bmp ...) when mmd_tools has none")
    parser.add_argument("--vmd", help="dance: VMD motion for the old model's armature (the new outfit follows it)")
    parser.add_argument("--vmd-scale", type=float, default=1.0,
                        help="VMD scale: 1.0 for models in MMD units, 0.08 for mmd_tools' default PMX import")


def apply_settings(settings, items):
    """--set key=value overrides: numbers, 0/1 for booleans, enum names, comma separated vectors."""
    for item in items:
        key, value = item.split("=", 1)
        current = getattr(settings, key)
        if isinstance(current, bool):
            value = value in ("1", "true", "True")
        elif isinstance(current, (int, float)):
            value = type(current)(float(value))
        elif not isinstance(current, str):
            value = tuple(float(v) for v in value.split(","))
        setattr(settings, key, value)


def _has_pmx_import():
    try:  # bpy.ops proxies always exist; only a registered operator has an RNA type
        bpy.ops.mmd_tools.import_model.get_rna_type()
        return True
    except (AttributeError, KeyError):
        return False


def enable_mmd_tools():
    for name in ("mmd_tools", "bl_ext.user_default.mmd_tools", "bl_ext.blender_org.mmd_tools"):
        if _has_pmx_import():
            return
        addon_utils.enable(name, default_set=False)
    if not _has_pmx_import():
        raise RuntimeError("mmd_tools is not installed for this Blender")


def _import_pmx(path):
    before = set(bpy.data.objects)
    bpy.ops.mmd_tools.import_model(filepath=path)
    roots = [ob for ob in bpy.data.objects if ob not in before and getattr(ob, "mmd_type", "") == "ROOT"]
    return roots[0]


def _fix_shared_toons(folder):
    import os

    for image in bpy.data.images:
        path = os.path.join(folder, image.name)
        if image.name.lower().startswith("toon") and not image.has_data and os.path.exists(path):
            image.filepath = path
            image.reload()


def load_dance(armature, path, scale=1.0):
    """Import a VMD motion onto `armature` with mmd_tools (bone animation only)."""
    import os

    enable_mmd_tools()
    folder, name = os.path.split(os.path.abspath(path))
    with bpy.context.temp_override(selected_objects=[armature], active_object=armature, object=armature):
        try:
            bpy.ops.mmd_tools.import_vmd(directory=folder, files=[{"name": name}], scale=scale,
                                         update_scene_settings=False)
        except TypeError:  # the legacy mmd_tools of Blender 3.6 takes one file path
            bpy.ops.mmd_tools.import_vmd(filepath=os.path.join(folder, name), scale=scale,
                                         update_scene_settings=False)
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise RuntimeError("no motion was imported from " + path)
    # the scene runs at least to the end of the dance (as mmd_tools' own import sets it up): moves of the dance that
    # start the transformation are looked for up to the scene's end frame
    scene = bpy.context.scene
    scene.frame_end = max(scene.frame_end, int(action.frame_range[1]))
    return action


def load_models(args):
    """Return (old_root, new_root)."""
    if args.pmx:
        for ob in list(bpy.data.objects):  # factory-startup cube, light and camera
            bpy.data.objects.remove(ob)
        enable_mmd_tools()
        roots = _import_pmx(args.pmx[0]), _import_pmx(args.pmx[1])
        if args.toon_dir:
            _fix_shared_toons(args.toon_dir)
        return roots
    import os

    coll = bpy.data.collections.new("New Outfit")
    bpy.context.scene.collection.children.link(coll)
    if os.path.abspath(args.target_blend) == os.path.abspath(bpy.data.filepath):
        # the opened file itself: a second copy of the same model (she turns into something that hides her, like the
        # symbiote), duplicated here with its own mesh data and materials
        root = _duplicate_tree(bpy.data.objects[args.target_root])
        keep = {root} | set(root.children_recursive)
    else:
        # (every object of the file: a model's meshes need not carry its root's name; its lights and cameras, and
        # whatever is not under the root, go)
        with bpy.data.libraries.load(args.target_blend, link=False) as (src, dst):
            dst.objects = list(src.objects)
        appended = [ob for ob in dst.objects if ob is not None]
        root = next((ob for ob in appended if ob.parent is None and ob.type == "EMPTY" and ob.children
                     and ob.name.startswith(args.target_root)), None)
        if root is None:
            root = next((ob for ob in appended if ob.name.startswith(args.target_root)), None)
        if root is None:
            root = bpy.data.objects[args.target_root]
        keep = {root} | set(root.children_recursive)
        for ob in appended:
            if ob not in keep:
                bpy.data.objects.remove(ob)
    for ob in keep:
        if ob.name not in coll.objects:
            coll.objects.link(ob)
    return bpy.data.objects[args.base_root], root


MMD_GRAVITY = 9.81 * 10.0  # mmd_tools' gravity for a model in MMD units (scale 1): MMD's own, about 8 cm a unit


def model_height(root):
    """Height of the model's meshes (not its rigid bodies), world units."""
    zs = [(ob.matrix_world @ ob.data.vertices[i].co).z for ob in root.children_recursive
          if ob.type == "MESH" and ob.rigid_body is None and ob.rigid_body_constraint is None
          for i in range(0, len(ob.data.vertices), 25)]
    return max(zs) - min(zs) if zs else 0.0


def ensure_physics(root, frame=None, reach=None):
    """Build the model's physics with mmd_tools when it never was (the rigid bodies of an imported PMX only move its
    bones once mmd_tools has built the rig: before that the hair and skirts only follow the bones), at `frame` (the
    dance's first frame: the simulation must start there, in the pose it was built in), and give the scene MMD's gravity
    for the model's units (mmd_tools' -9.81 * 10 * scale: in MMD units, a model some twenty units tall, Blender's
    default 9.81 is a tenth of what the models' springs are made for, and hair and skirts float up). Returns how many
    bones the rigid bodies move, or None without mmd_tools."""
    mmd_root = getattr(root, "mmd_root", None)
    if mmd_root is None or not hasattr(bpy.ops, "mmd_tools") or not hasattr(bpy.ops.mmd_tools, "build_rig"):
        return None
    scene = bpy.context.scene
    if frame is not None:
        scene.frame_set(int(frame))
    scale = 1.0 if model_height(root) > 5.0 else 0.08  # (mmd_tools imports at 1 or at 0.08)
    scene.gravity = (0.0, 0.0, -MMD_GRAVITY * scale)
    scene.use_gravity = True
    if not mmd_root.is_built:
        for ob in bpy.context.view_layer.objects:
            ob.select_set(False)
        bpy.context.view_layer.objects.active = root
        root.select_set(True)
        if reach is None:
            bpy.ops.mmd_tools.build_rig()
        else:  # (non-collision pairs found this far apart, in the bodies' sizes: mmd_tools' default is 1.5)
            bpy.ops.mmd_tools.build_rig(non_collision_distance_scale=reach)
    arm = next((ob for ob in root.children_recursive if ob.type == "ARMATURE" and len(ob.data.bones) > 1), None)
    return sum(1 for pb in arm.pose.bones if "mmd_tools_rigid_track" in pb.constraints) if arm is not None else 0


def _duplicate_tree(root):
    """A copy of `root` and everything under it (own mesh and armature data, own materials; parents, modifiers and
    constraints pointing at the copies), but not its rigid bodies and joints: the copy's bones keep following the
    original's rigid bodies (the only ones simulated). Returns the new root."""
    copies = {}
    for ob in [root] + list(root.children_recursive):
        if ob.rigid_body is not None or ob.rigid_body_constraint is not None:
            continue
        dup = ob.copy()
        if ob.data is not None:
            dup.data = ob.data.copy()
        copies[ob] = dup
    materials = {}
    for ob, dup in copies.items():
        if ob.parent in copies:
            dup.parent = copies[ob.parent]
        for mod in dup.modifiers:
            if getattr(mod, "object", None) in copies:
                mod.object = copies[mod.object]
        for con in dup.constraints:
            if getattr(con, "target", None) in copies:
                con.target = copies[con.target]
        if dup.type == "ARMATURE":
            for pb in dup.pose.bones:
                for con in pb.constraints:
                    if getattr(con, "target", None) in copies:
                        con.target = copies[con.target]
        if dup.type == "MESH":
            for slot in dup.material_slots:
                if slot.material is not None:
                    if slot.material not in materials:
                        materials[slot.material] = slot.material.copy()
                    slot.material = materials[slot.material]
    return copies[root]
