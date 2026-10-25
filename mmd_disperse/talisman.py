"""The talismans burning away (符箓燃尽, 1.21): on the way to the big moment paper talismans fly one after another from
her fingertip, swirl round her and stick to her all over, their vermilion runes glowing; at the moment they catch fire
together, curl and burn away from their feet up, ashes rising, and she stands there in the new outfit. A Taoist
priest's charms (朱砂符箓 on yellow paper).

Our objects: a twin of each mesh of the old outfit (the same mesh data, its armature first, then cover_nodes'
talisman group: the talismans and their ashes are all it puts out), and an empty at her fingertip (Child Of its bone,
at rest where the fingertip is) they fly from.
"""

import fnmatch

import bpy
import numpy as np
from mathutils import Matrix

from . import materials
from . import model as mdl

P_TALISMAN = "mmd_disperse_talisman"  # on our objects: the mask of their effect ...
P_SOURCE = "mmd_disperse_talisman_source"  # ... the mesh it is a twin of (twins) ...
P_KIND = "mmd_disperse_talisman_kind"  # ... TWIN or HAND
NAME = "MMD Disperse Talisman"
FLY = 0.45  # seconds a talisman takes from her hand to its place
SIZE = 0.095  # a talisman's height, a share of hers
FINGERTIPS = (("人指３.R", "右人指３", "index3.R", "Index3_R", "RightHandIndex3", "J_Bip_R_Index3"),
              ("手首.R", "右手首", "wrist.R", "Wrist_R", "RightHand", "hand.R"))


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects
            if ob.get(P_TALISMAN) == mask and (kind is None or ob.get(P_KIND) == kind)]


def clear_stick(meshes):
    from .cover_nodes import ATTR_STICK

    for ob in meshes:
        if ob.type == "MESH" and ob.data.attributes.get(ATTR_STICK) is not None:
            ob.data.attributes.remove(ob.data.attributes[ATTR_STICK])


def write_stick(ob, patterns):
    """Mark the faces of `ob` the talismans may stick to (ATTR_STICK): those whose material matches none of
    `patterns` (her hair, face and the like); how many."""
    from .cover_nodes import ATTR_STICK

    me = ob.data
    if me.attributes.get(ATTR_STICK) is not None:
        me.attributes.remove(me.attributes[ATTR_STICK])
    ok = np.array([s.material is not None and not any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                      for p in patterns) for s in ob.material_slots] or [False],
                  dtype=bool)
    index = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", index)
    values = ok[np.clip(index, 0, len(ok) - 1)]
    if not values.any():
        return 0
    attr = me.attributes.new(ATTR_STICK, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", values)
    return int(values.sum())


def remove(mask, models=()):
    sources = [bpy.data.objects.get(ob.get(P_SOURCE, "")) for ob in objects(mask, "TWIN")]
    for ob in objects(mask):
        bpy.data.objects.remove(ob)
    clear_stick([ob for ob in sources if ob is not None] + [ob for model in models for ob in model.meshes])
    if not any(ob.get(P_TALISMAN) is not None for ob in bpy.data.objects):
        from .cover_nodes import TALISMAN_GROUP

        ng = bpy.data.node_groups.get(TALISMAN_GROUP)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
        for kind in ("TALISMAN", "ASH"):
            mat = bpy.data.materials.get(materials._cover_name(kind))
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def _hand(mask, collection, armature):
    """The empty at her fingertip (the first bone of FINGERTIPS she has: its tail), following it."""
    bone = None
    for names in FINGERTIPS:
        bone = next((armature.data.bones[n] for n in names if n in armature.data.bones), None)
        if bone is not None:
            break
    ob = next(iter(objects(mask, "HAND")), None)
    if bone is None:
        if ob is not None:
            bpy.data.objects.remove(ob)
        return None
    if ob is None:
        ob = bpy.data.objects.new(NAME + " Hand", None)
        collection.objects.link(ob)
        ob[P_TALISMAN], ob[P_KIND] = mask, "HAND"
        ob.hide_select = True
        ob.hide_render = True
        ob.empty_display_size = 0.05
    for c in list(ob.constraints):
        ob.constraints.remove(c)
    ob.parent = None
    ob.matrix_basis = Matrix.Translation(armature.matrix_world @ bone.tail_local)
    con = ob.constraints.new("CHILD_OF")
    con.target, con.subtarget = armature, bone.name
    con.inverse_matrix = (armature.matrix_world @ bone.matrix_local).inverted()
    try:
        ob.hide_set(True)
    except RuntimeError:  # (not in the view layer: hidden there anyway)
        pass
    return ob


def _twin(source, mask, collection, group):
    """The twin of mesh `source`: its mesh data where it is, its armature, then our group."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_TALISMAN], ob[P_SOURCE], ob[P_KIND] = mask, source.name, "TWIN"
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
    """The talismans as the panel says, burning at the big moment at frame `moment`; all taken away when off."""
    from . import cover_nodes, peel
    from .node_groups import input_identifiers

    if mask is None:
        return
    if (not getattr(settings, "talisman_enable", False) or moment is None or not models
            or models[0].armature is None):
        remove(mask, models)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    lead = max(settings.talisman_time, FLY + 0.3) * fps
    start = m - lead
    old = models[0]
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    group = cover_nodes.ensure_talisman_group()
    ids = input_identifiers(group)
    hand = _hand(mask, collection, old.armature)
    keep = [hand] if hand is not None else []
    paper = materials.ensure_cover_material("TALISMAN")
    ash = materials.ensure_cover_material("ASH")
    patterns = mdl.split_patterns(mdl.DEFAULT_LOCK_PATTERNS) + ["-*"]  # (this model pack's hidden variants)
    if settings.use_lock:
        patterns += mdl.split_patterns(settings.lock_patterns)
    per_mesh = max(1, int(round(settings.talisman_count / max(len(old.meshes), 1))))
    for k, ob in enumerate(old.meshes):
        if not ob.data.polygons or not write_stick(ob, patterns):
            continue
        twin, mod = _twin(ob, mask, collection, group)
        keep.append(twin)
        _centre, size, shoulder = peel.measure(ob, old.armature)
        height = size.z
        for name, value in (("Start", start), ("Spread", max(lead - (FLY + 0.25) * fps, 1.0)), ("Fly", FLY * fps),
                            ("Burn", m), ("Burn Time", max(settings.talisman_burn * fps, 1.0)),
                            ("Count", per_mesh), ("Hand", hand), ("Size", SIZE * height), ("Height", height),
                            ("Top", shoulder + 0.03 * height), ("Seed", 3 + k), ("Paper Material", paper),
                            ("Ash Material", ash)):
            if name in ids:
                mod[ids[name]] = value
        twin.update_tag()
    for ob in objects(mask):
        if ob not in keep:
            bpy.data.objects.remove(ob)
