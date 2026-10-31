"""Feathers and flowers (长出羽毛和花, 1.24): on the way to the big moment something grows out of her old outfit and
covers it: black feathers (the Black Swan: goosebumps first, then feathers pushing out of her and growing, lying down
along her body and her arms) or flowers opening all over her (a red spider lily's field); at the moment they all blow
off her in a flurry and she stands there in the new outfit.

Our objects: a twin of each mesh of the old outfit (the same mesh data, its armature first, then cover_nodes'
plumage group: the feathers or flowers are all it puts out). A face attribute on the old meshes (cover_nodes.ATTR_GROW)
marks where they may grow (not her hair, face and the like).
"""

import fnmatch

import bpy
import numpy as np

from . import materials
from . import model as mdl

P_PLUMAGE = "mmd_disperse_plumage"  # on our objects: the mask of their effect ...
P_SOURCE = "mmd_disperse_plumage_source"  # ... the mesh it is a twin of
NAME = "MMD Disperse Plumage"
STYLES = ("FEATHERS", "FLOWERS")
SPROUT = 0.35  # seconds one of them takes to grow out
BLOW = 0.9  # seconds they take to blow away
SIZES = {"FEATHERS": 0.07, "FLOWERS": 0.075}  # a feather's length, a flower's width: shares of her height
SHARE = {"FEATHERS": 1.0, "FLOWERS": 0.3}  # how many of Count (flowers are wider)
BACK = ("上半身2", "上半身", "UpperBody2", "UpperBody", "upper body 2", "upper body", "Chest", "chest", "Spine2",
        "J_Bip_C_Chest")  # where it starts: behind her chest (the Black Swan's back)


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_PLUMAGE) == mask]


def clear_grow(meshes):
    from .cover_nodes import ATTR_GROW

    for ob in meshes:
        if ob.type == "MESH" and ob.data.attributes.get(ATTR_GROW) is not None:
            ob.data.attributes.remove(ob.data.attributes[ATTR_GROW])


def write_grow(ob, patterns):
    """Mark the faces of `ob` they may grow on (ATTR_GROW): those whose material matches none of `patterns` (her
    hair, face and the like); how many."""
    from .cover_nodes import ATTR_GROW

    me = ob.data
    if me.attributes.get(ATTR_GROW) is not None:
        me.attributes.remove(me.attributes[ATTR_GROW])
    ok = np.array([s.material is not None and not any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                      for p in patterns) for s in ob.material_slots] or [False],
                  dtype=bool)
    index = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", index)
    values = ok[np.clip(index, 0, len(ok) - 1)]
    if not values.any():
        return 0
    attr = me.attributes.new(ATTR_GROW, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", values)
    return int(values.sum())


def remove(mask, models=()):
    sources = [bpy.data.objects.get(ob.get(P_SOURCE, "")) for ob in objects(mask)]
    for ob in objects(mask):
        bpy.data.objects.remove(ob)
    clear_grow([ob for ob in sources if ob is not None] + [ob for model in models for ob in model.meshes])
    if not any(ob.get(P_PLUMAGE) is not None for ob in bpy.data.objects):
        from .cover_nodes import PLUMAGE_GROUP

        ng = bpy.data.node_groups.get(PLUMAGE_GROUP)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
        for kind in ("PLUMAGE", "BLOSSOM"):
            mat = bpy.data.materials.get(materials._cover_name(kind))
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def _twin(source, mask, collection, group):
    """The twin of mesh `source`: its mesh data where it is, its armature, then our group."""
    ob = next((o for o in objects(mask) if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_PLUMAGE], ob[P_SOURCE] = mask, source.name
        ob.hide_select = True
    ob.add_rest_position_attribute = True
    ob.parent = source.parent
    ob.parent_type = source.parent_type
    ob.parent_bone = source.parent_bone
    ob.matrix_parent_inverse = source.matrix_parent_inverse.copy()
    ob.matrix_basis = source.matrix_basis.copy()
    for mod in list(ob.modifiers):
        ob.modifiers.remove(mod)
    for theirs in source.modifiers:
        if theirs.type != "ARMATURE":
            continue
        twin = ob.modifiers.new(theirs.name, "ARMATURE")
        for prop in ("object", "use_vertex_groups", "use_bone_envelopes", "use_deform_preserve_volume",
                     "use_multi_modifier", "vertex_group", "invert_vertex_group"):
            setattr(twin, prop, getattr(theirs, prop))
    mod = ob.modifiers.new(NAME, "NODES")
    mod.node_group = group
    return ob, mod


def sync(settings, mask, models, moment):
    """The feathers or flowers as the panel says, blowing away at the big moment at frame `moment`; all taken away when
    off."""
    from . import cover_nodes, particles, peel
    from .node_groups import input_identifiers

    if mask is None:
        return
    if (not getattr(settings, "plume_enable", False) or moment is None or not models
            or models[0].armature is None):
        remove(mask, models)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    lead = max(settings.plume_time, SPROUT + 0.2) * fps
    style = settings.plume_style
    old = models[0]
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    group = cover_nodes.ensure_plumage_group()
    ids = input_identifiers(group)
    feather = particles.ensure_asset("FEATHER", scene)
    flower = particles.ensure_asset("BLOSSOM", scene)
    material = materials.ensure_cover_material("PLUMAGE" if style == "FEATHERS" else "BLOSSOM")
    patterns = mdl.split_patterns(mdl.DEFAULT_LOCK_PATTERNS) + ["-*"]  # (this model pack's hidden variants)
    if settings.use_lock:
        patterns += mdl.split_patterns(settings.lock_patterns)
    areas = {ob: write_grow(ob, patterns) for ob in old.meshes if ob.data.polygons}
    total = max(sum(areas.values()), 1)
    count = settings.plume_count * SHARE[style]
    keep = []
    for k, ob in enumerate(old.meshes):
        if not areas.get(ob):
            continue
        twin, mod = _twin(ob, mask, collection, group)
        keep.append(twin)
        twin["mmdd_color"] = tuple(settings.plume_color)
        twin["mmdd_glow"] = 0.15 if style == "FLOWERS" else 0.0
        centre, size, _shoulder = peel.measure(ob, old.armature)
        height = size.z
        start = peel._bone_head(old.armature, BACK, ob)
        start = (start.x, start.y + 0.6 * size.y, start.z) if start is not None else (centre.x, centre.y + size.y,
                                                                                         centre.z + 0.3 * height)
        for name, value in (("Start", m - lead), ("Grow", lead - SPROUT * fps), ("Sprout", SPROUT * fps),
                            ("Moment", m), ("Blow", BLOW * fps),
                            ("Count", max(1, int(round(count * areas[ob] / total)))),
                            ("Size", SIZES[style] * height), ("Height", height), ("From", start),
                            ("Centre", tuple(centre)), ("Width", size.x), ("Style", STYLES.index(style)),
                            ("Feather", feather), ("Flower", flower), ("Material", material), ("Seed", 5 + k)):
            if name in ids:
                mod[ids[name]] = value
        twin.update_tag()
    for ob in objects(mask):
        if ob not in keep:
            bpy.data.objects.remove(ob)
