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
        bpy.ops.mmd_tools.import_vmd(directory=folder, files=[{"name": name}], scale=scale,
                                     update_scene_settings=False)
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise RuntimeError("no motion was imported from " + path)
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
    with bpy.data.libraries.load(args.target_blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith(args.target_root)]
    coll = bpy.data.collections.new("New Outfit")
    bpy.context.scene.collection.children.link(coll)
    for ob in dst.objects:
        if ob is not None:
            coll.objects.link(ob)
    return bpy.data.objects[args.base_root], bpy.data.objects[args.target_root]
