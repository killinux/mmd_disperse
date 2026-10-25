"""The multiple exposure (迷幻多重曝光, 1.18): on the way to the big moment copies of her in the old outfit swell out of
her one after another, each larger and turned a little, each in its own colour of 1960s psychedelia (or the glow
colour), like a print exposed again and again; at the moment they are copies of her in the new outfit, far out, and
they gather back into her. The Fantastic Four: First Steps' (2025) look for the Invisible Woman.

Our objects: a twin of every mesh of both outfits (the same mesh data posed by its armature only: she as she dances,
the whole outfit; in materials of its own, slot by slot the echo light cut out as her material there is), an empty at
her centre bone, and for each twin an object carrying cover_nodes' echo group: Count copies of the twin (instances of
it, so they show in its materials) round the empty, scaled by Spread and turned, each with its number and how much it
shows for the material. Spread and Fade are driven by the frame (simple expressions).
"""

import bpy

from . import materials

P_ECHO = "mmd_disperse_echo"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_echo_kind"  # ... TWIN, COPIES, ANCHOR
P_SOURCE = "mmd_disperse_echo_source"  # ... on a twin / copies: the mesh it is of
P_OUTFIT = "mmd_disperse_echo_outfit"  # ... OLD or NEW
NAME = "MMD Disperse Echo"
GATHER = 0.7  # the new outfit's copies gather back into her over this share of Echo Time after the moment
TURN = 0.06  # each copy turned this much (radians) further than the one inside it, at the widest ...
PUSH = 0.12  # ... and this much (model heights) further back from the camera
APPEAR = 0.25  # the old outfit's copies come up over this share of Echo Time


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_ECHO) == mask and (kind is None or ob.get(P_KIND) == kind)]


def remove(mask):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    if not any(ob.get(P_ECHO) is not None for ob in bpy.data.objects):
        from .cover_nodes import ECHO_GROUP

        ng = bpy.data.node_groups.get(ECHO_GROUP)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
        for mat in materials.echo_materials():
            if mat.users == 0:
                bpy.data.materials.remove(mat)


def _twin(source, mask, collection, outfit):
    """The hidden twin of a mesh: its mesh data, posed by its armature only, in materials of its own (linked to the
    object: hers stay as they are), the echo light cut out as hers are."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s Twin %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_ECHO], ob[P_KIND], ob[P_SOURCE], ob[P_OUTFIT] = mask, "TWIN", source.name, outfit
        ob.hide_select = True
        ob.hide_render = True  # (its copies show, drawn as it is)
        for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
            if hasattr(ob, flag):
                setattr(ob, flag, False)
    for slot, hers in zip(ob.material_slots, source.material_slots):
        if slot.link != "OBJECT":
            slot.link = "OBJECT"
        mat = materials.echo_material(hers.material)
        if slot.material != mat:
            slot.material = mat
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


def _anchor(mask, collection, models):
    """The empty the copies swell round: her centre, following her centre bone."""
    from .model import rest_bounds
    from .spirit import CENTRE

    ob = next(iter(objects(mask, "ANCHOR")), None)
    if ob is None:
        ob = bpy.data.objects.new(NAME + " Anchor", None)
        collection.objects.link(ob)
        ob[P_ECHO], ob[P_KIND] = mask, "ANCHOR"
        ob.hide_select = True
        ob.hide_render = True
    for c in list(ob.constraints):
        ob.constraints.remove(c)
    meshes = [m for model in models for m in model.meshes]
    lo, hi = rest_bounds(meshes)
    ob.location = (0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z + 0.5 * (hi.z - lo.z))
    arm = models[0].armature
    bone = next((n for n in CENTRE if arm is not None and n in arm.data.bones), None)
    if bone is not None:
        con = ob.constraints.new("COPY_LOCATION")
        con.target, con.subtarget = arm, bone
        con.use_offset = True
        rest = arm.matrix_world @ arm.data.bones[bone].head_local
        ob.location = ob.location - rest
    return ob


def _drive(mod, ids, name, expression):
    path = '["%s"]' % ids[name]
    mod.driver_remove(path)
    driver = mod.driver_add(path).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def sync(settings, mask, models, moment):
    """The copies as the panel says, round the big moment at frame `moment`; all of them taken away when it is off."""
    from . import cover_nodes
    from .node_groups import input_identifiers

    if mask is None:
        return
    if not getattr(settings, "echo_enable", False) or moment is None or not models:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    length = max(settings.echo_length * fps, 2.0)
    start, appear = m - length, m - length + APPEAR * length
    gather = m + GATHER * length
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    anchor = _anchor(mask, collection, models)
    # away from the camera as it is when they swell out: each copy behind the one inside it
    from . import sampling
    from mathutils import Vector

    centre = anchor.matrix_world.translation.copy()
    camera = sampling.camera_at(scene, start)
    back = Vector((0.0, 1.0, 0.0))
    if camera is not None:
        away = centre - sampling.matrix_at(camera, start).translation
        away.z = 0.0
        if away.length > 1e-6:
            back = away.normalized()
    height = max(settings.size_reference, 1e-3)
    group = cover_nodes.ensure_echo_group()
    ids = input_identifiers(group)
    keep = [anchor]
    outfits = ("OLD", "NEW") if len(models) > 1 else ("NEW",)
    for model, outfit in zip(models, outfits):
        for ob in model.meshes:
            if not ob.material_slots:  # (a copy without materials would show plain grey)
                continue
            twin = _twin(ob, mask, collection, outfit)
            keep.append(twin)
            copies = next((o for o in objects(mask, "COPIES") if o.get(P_SOURCE) == ob.name), None)
            if copies is None:
                copies = bpy.data.objects.new("%s Copies %s" % (NAME, ob.name), bpy.data.meshes.new(NAME))
                collection.objects.link(copies)
                copies[P_ECHO], copies[P_KIND], copies[P_SOURCE], copies[P_OUTFIT] = mask, "COPIES", ob.name, outfit
                copies.hide_select = True
                for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
                    if hasattr(copies, flag):
                        setattr(copies, flag, False)
            keep.append(copies)
            mod = next((x for x in copies.modifiers if x.type == "NODES"), None) or copies.modifiers.new(NAME, "NODES")
            if mod.node_group != group:
                mod.node_group = group
            for name, value in (("Twin", twin), ("Anchor", anchor), ("Count", int(settings.echo_count)),
                                ("Size", float(settings.echo_spread)), ("Turn", TURN), ("Back", tuple(back)),
                                ("Push", PUSH * height)):
                if name in ids:
                    mod[ids[name]] = value
            if outfit == "OLD":  # swelling out of her up to the moment, gone as she changes
                _drive(mod, ids, "Spread", "smoothstep(%.2f, %.2f, frame)" % (start, m))
                _drive(mod, ids, "Fade", "smoothstep(%.2f, %.2f, frame) * (1 - smoothstep(%.2f, %.2f, frame))"
                       % (start, appear, m - 2.0, m))
            else:  # far out at the moment, gathering back into her
                _drive(mod, ids, "Spread", "1 - smoothstep(%.2f, %.2f, frame)" % (m, gather))
                _drive(mod, ids, "Fade", "smoothstep(%.2f, %.2f, frame) * (1 - smoothstep(%.2f, %.2f, frame))"
                       % (m - 2.0, m, gather - 0.25 * (gather - m), gather))
            copies.update_tag()
    materials.update_echo(settings.echo_style, tuple(settings.glow_color))
    for ob in objects(mask):
        if ob not in keep:
            data = ob.data
            bpy.data.objects.remove(ob)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
