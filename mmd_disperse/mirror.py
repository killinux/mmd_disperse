"""The mirror first (倒影先换, 1.16): a tall mirror in a gilded frame stands beside her, turned so the camera sees her in
it; her reflection dances along in the old outfit, then, a little before the big moment, the glass flashes and the
reflection is in the new outfit already; at the moment she changes to match, and the mirror goes. The Little
Mermaid's mirror (1989); Wicked: For Good's walk through the looking glass.

Our objects: the glass (a unit square of ours across X and Z, its front at -Y, scaled to the mirror: the plane the
reflections are mirrored in), its frame, a twin of every mesh of both outfits (the same mesh data posed by its armature
only: the whole outfit as it is when complete), and a reflection of each twin (cover_nodes' mirror group: mirrored in
the glass, kept only where the camera sees it through it), shown in turn by a driver on the frame.
"""

import math

import bpy
from mathutils import Matrix, Vector

from . import materials

P_MIRROR = "mmd_disperse_mirror"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_mirror_kind"  # ... GLASS, FRAME, TWIN, REFLECTION
P_SOURCE = "mmd_disperse_mirror_source"  # ... on a twin / reflection: the mesh it is of
P_OUTFIT = "mmd_disperse_mirror_outfit"  # ... OLD or NEW
NAME = "MMD Disperse Mirror"
POP = 0.25  # seconds the mirror takes to stand up ...
FLASH = 0.12  # ... the glass flashes this long as the reflection changes ...
GO = (0.8, 1.2)  # ... after the moment it shrinks away between these times
SIZE = (0.42, 1.12)  # the glass: wide and tall (model heights) ...
BESIDE = (0.45, 0.25)  # ... standing this far to her side and behind her (model heights: in the picture beside her,
# her arms passing in front of it)


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_MIRROR) == mask and (kind is None or ob.get(P_KIND) == kind)]


def remove(mask):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    if not any(ob.get(P_MIRROR) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_mirror_assets()
        for kind in ("MIRROR_GLASS",):
            mat = bpy.data.materials.get(materials._cover_name(kind))
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def _twin(source, mask, collection, outfit):
    """The hidden twin of a mesh: its mesh data, posed by its armature only."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s Twin %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_MIRROR], ob[P_KIND], ob[P_SOURCE], ob[P_OUTFIT] = mask, "TWIN", source.name, outfit
        ob.hide_select = True
        ob.hide_render = True
        ob.display_type = "WIRE"
    ob.parent = source.parent
    ob.parent_type = source.parent_type
    ob.parent_bone = source.parent_bone
    ob.matrix_parent_inverse = source.matrix_parent_inverse.copy()
    ob.matrix_basis = source.matrix_basis.copy()
    for mod in list(ob.modifiers):
        ob.modifiers.remove(mod)
    for mod in source.modifiers:
        if mod.type != "ARMATURE":
            continue
        twin = ob.modifiers.new(mod.name, "ARMATURE")
        for prop in ("object", "use_vertex_groups", "use_bone_envelopes", "use_deform_preserve_volume",
                     "use_multi_modifier", "vertex_group", "invert_vertex_group"):
            setattr(twin, prop, getattr(mod, prop))
    try:
        ob.hide_set(True)
    except RuntimeError:  # (not in the view layer: hidden there anyway)
        pass
    return ob


def glass_mesh(name):
    """A unit square across X and Z, its front at -Y, with a UV over it."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-0.5, 0.0, -0.5), (0.5, 0.0, -0.5), (0.5, 0.0, 0.5), (-0.5, 0.0, 0.5)], [], [(0, 1, 2, 3)])
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = (co.x + 0.5, co.z + 0.5)
    me.update()
    return me


def sync(settings, mask, models, moment):
    """The mirror as the panel says, for the big moment at frame `moment`; all of it taken away when it is off."""
    from . import cover_nodes, sampling
    from .cover import _clear_keys, _frame_mesh, _key, _shown
    from .model import rest_bounds
    from .node_groups import input_identifiers

    if mask is None:
        return
    if not getattr(settings, "mirror_enable", False) or moment is None or not models:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    height = max(settings.size_reference, 1e-3)
    m = float(moment)
    show = m - settings.mirror_length * fps
    first = m - settings.mirror_first * fps
    gone0, gone1 = m + GO[0] * fps, m + GO[1] * fps
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    meshes = [ob for model in models for ob in model.meshes]
    lo, hi = rest_bounds(meshes)
    centre = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z + 0.5 * (hi.z - lo.z)))
    camera = sampling.camera_at(scene, first)
    eye = sampling.matrix_at(camera, first).translation if camera is not None else centre + Vector((0, -3 * height, 0))
    look = centre - eye
    look.z = 0.0
    look = look.normalized() if look.length > 1e-6 else Vector((0.0, 1.0, 0.0))
    side = look.cross(Vector((0.0, 0.0, 1.0)))
    wide, tall = SIZE[0] * height, SIZE[1] * height
    middle = Vector((centre.x, centre.y, lo.z + 0.5 * tall + 0.03 * height)) + side * (BESIDE[0] * height) + look * (
        BESIDE[1] * height)
    # turned so the camera sees her in it: its front halfway between the ways to the camera and to her
    to_eye, to_her = (eye - middle), (centre - middle)
    to_eye.z = to_her.z = 0.0
    front = (to_eye.normalized() + to_her.normalized())
    front = front.normalized() if front.length > 1e-6 else -look
    up = Vector((0.0, 0.0, 1.0))
    turn = Matrix(((-front).cross(up), -front, up)).transposed().to_quaternion()
    glass = next(iter(objects(mask, "GLASS")), None)
    if glass is None:
        glass = bpy.data.objects.new(NAME + " Glass", glass_mesh(NAME + " Glass"))
        collection.objects.link(glass)
        glass[P_MIRROR], glass[P_KIND] = mask, "GLASS"
        glass.hide_select = True
        glass.data.materials.append(materials.ensure_cover_material("MIRROR_GLASS"))
        if hasattr(glass, "visible_shadow"):
            glass.visible_shadow = False
    key = "frame:%.4f:%.4f" % (wide, tall)
    frame = next(iter(objects(mask, "FRAME")), None)
    if frame is not None and frame.get("mmdd_key") != key:
        data = frame.data
        bpy.data.objects.remove(frame)
        bpy.data.meshes.remove(data)
        frame = None
    if frame is None:
        frame = bpy.data.objects.new(NAME + " Frame", _frame_mesh(wide, tall, 0.06 * height))
        collection.objects.link(frame)
        frame[P_MIRROR], frame[P_KIND], frame["mmdd_key"] = mask, "FRAME", key
        frame.hide_select = True
        frame.data.materials.append(materials.ensure_cover_material("FRAME"))
    facing = Matrix(((-front).cross(up), up, front)).transposed().to_quaternion()  # (the frame's +Z at its front)
    for ob, rotation, scale in ((glass, turn, Vector((wide, 1.0, tall))), (frame, facing, Vector((1.0, 1.0, 1.0)))):
        _clear_keys(ob)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = rotation
        ob.location = middle
        _key(ob, "scale", ((show - 1.0, scale * 0.0), (show, scale * 0.0), (show + 0.8 * POP * fps, scale * 1.05),
                           (show + POP * fps, scale), (gone0, scale), (gone1, scale * 0.0)), interpolation="BEZIER")
        _shown(ob, int(math.floor(show)), int(math.ceil(gone1)))
    glass["mmdd_flash"] = 0.0
    _key(glass, '["mmdd_flash"]', ((first - FLASH * fps, 0.0), (first, 1.0), (first + FLASH * fps, 0.0)),
         interpolation="LINEAR")
    # her reflections: the old outfit till `first`, the new one from then on (while the mirror stands)
    group = cover_nodes.ensure_mirror_group()
    ids = input_identifiers(group)
    keep = []
    for k, (model, outfit) in enumerate(zip(models, ("OLD", "NEW") if len(models) > 1 else ("NEW",))):
        for ob in model.meshes:
            twin = _twin(ob, mask, collection, outfit)
            keep.append(twin)
            copy = next((o for o in objects(mask, "REFLECTION") if o.get(P_SOURCE) == ob.name), None)
            if copy is None:
                copy = bpy.data.objects.new("%s Reflection %s" % (NAME, ob.name), bpy.data.meshes.new(NAME))
                collection.objects.link(copy)
                copy[P_MIRROR], copy[P_KIND], copy[P_SOURCE], copy[P_OUTFIT] = mask, "REFLECTION", ob.name, outfit
                copy.hide_select = True
            keep.append(copy)
            mod = next((x for x in copy.modifiers if x.type == "NODES"), None) or copy.modifiers.new(NAME, "NODES")
            if mod.node_group != group:
                mod.node_group = group
            for name, value in (("Twin", twin), ("Mirror", glass), ("Camera", camera), ("Width", wide),
                                ("Height", tall)):
                if name in ids and value is not None:
                    mod[ids[name]] = value
            a, b = (show + POP * fps, first) if outfit == "OLD" else (first, gone0)
            path = '["%s"]' % ids["Show"]
            mod.driver_remove(path)
            driver = mod.driver_add(path).driver
            driver.type = "SCRIPTED"
            driver.expression = "(frame >= %.2f) * (frame < %.2f)" % (a, b)
            copy.update_tag()
    for ob in objects(mask):
        if ob.get(P_KIND) in ("TWIN", "REFLECTION") and ob not in keep:
            data = ob.data
            bpy.data.objects.remove(ob)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
