"""The fumble (变身翻车, 1.20): a little after she has changed, a few loose parts of the new outfit (an arm guard, a
belt, a pad: whatever Loose Parts names) come off, tumble to the floor, bounce twice and go in a puff of smoke, like
the paper armour of a home-made tokusatsu skit (にじさんじ 花畑チャイカ's new outfit stream: the armour on, the
change, the armour falling off).

Our objects: a still copy of her armature (posed as she is the moment they come off: its action's channels
evaluated at that frame, its keys gone; not in her hierarchy) and a twin of each mesh of the new outfit that has loose
parts (the same mesh data, posed by the still armature, then cover_nodes' fumble group: the parts fall); on her own
meshes a small modifier (the fumble hide group) takes the parts away as they come off. A face attribute on the new
meshes (cover_nodes.ATTR_LOOSE) marks the loose parts.
"""

import fnmatch

import bpy
import numpy as np

from . import materials
from . import model as mdl

P_FUMBLE = "mmd_disperse_fumble"  # on our objects: the mask of their effect ...
P_SOURCE = "mmd_disperse_fumble_source"  # ... the mesh (or the armature) it is of ...
P_KIND = "mmd_disperse_fumble_kind"  # ... TWIN or STILL
NAME = "MMD Disperse Fumble"
HIDE = NAME + " Hide"  # the modifier on her meshes


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_FUMBLE) == mask and (kind is None or ob.get(P_KIND) == kind)]


def clear_loose(meshes):
    from .cover_nodes import ATTR_LOOSE

    for ob in meshes:
        if ob.type != "MESH":
            continue
        mod = ob.modifiers.get(HIDE)
        if mod is not None:
            ob.modifiers.remove(mod)
        if ob.data.attributes.get(ATTR_LOOSE) is not None:
            ob.data.attributes.remove(ob.data.attributes[ATTR_LOOSE])


def remove(mask, models=()):
    sources = [bpy.data.objects.get(ob.get(P_SOURCE, "")) for ob in objects(mask, "TWIN")]
    for ob in objects(mask):
        bpy.data.objects.remove(ob)
    clear_loose([ob for ob in sources if ob is not None] + [ob for model in models for ob in model.meshes])
    if not any(ob.get(P_FUMBLE) is not None for ob in bpy.data.objects):
        from .cover_nodes import FUMBLE_GROUP, FUMBLE_HIDE_GROUP

        for name in (FUMBLE_GROUP, FUMBLE_HIDE_GROUP):
            ng = bpy.data.node_groups.get(name)
            if ng is not None and ng.users == 0:
                bpy.data.node_groups.remove(ng)
        mat = bpy.data.materials.get(materials.PUFF_MATERIAL)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)


def write_loose(ob, patterns):
    """Mark the faces of `ob` whose material matches one of `patterns` (ATTR_LOOSE); how many."""
    from .cover_nodes import ATTR_LOOSE

    me = ob.data
    if me.attributes.get(ATTR_LOOSE) is not None:
        me.attributes.remove(me.attributes[ATTR_LOOSE])
    loose = np.array([s.material is not None and any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                     for p in patterns) for s in ob.material_slots] or [False],
                     dtype=bool)
    index = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", index)
    values = loose[np.clip(index, 0, len(loose) - 1)]
    if not values.any():
        return 0
    attr = me.attributes.new(ATTR_LOOSE, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", values)
    return int(values.sum())


def _still(armature, mask, collection, frame):
    """The still copy of `armature`: its action's channels as they are at `frame`, no keys, not in her hierarchy."""
    from . import sampling

    ob = next(iter(objects(mask, "STILL")), None)
    if ob is None or ob.data != armature.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = armature.copy()
        collection.objects.link(ob)
        ob.name = "%s Still %s" % (NAME, armature.name)
        ob[P_FUMBLE], ob[P_SOURCE], ob[P_KIND] = mask, armature.name, "STILL"
        ob.hide_select = True
        ob.hide_render = True
    ob.animation_data_clear()
    ob.parent = None
    ob.matrix_world = sampling.matrix_at(armature, frame)
    action = armature.animation_data.action if armature.animation_data else None
    for fc in (action.fcurves if action is not None else []):
        if not fc.data_path.startswith("pose.bones"):
            continue
        try:
            prop = ob.path_resolve(fc.data_path)
            prop[fc.array_index] = fc.evaluate(frame)
        except (ValueError, TypeError, IndexError, AttributeError):
            continue
    try:
        ob.hide_set(True)
    except RuntimeError:  # (not in the view layer: hidden there anyway)
        pass
    return ob


def _twin(source, still, mask, collection, group):
    """The twin of mesh `source`: its mesh data where it is, posed by `still`, then our group."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_FUMBLE], ob[P_SOURCE], ob[P_KIND] = mask, source.name, "TWIN"
        ob.hide_select = True
    ob.parent = None
    ob.matrix_world = source.matrix_world.copy()
    for mod in list(ob.modifiers):
        ob.modifiers.remove(mod)
    for theirs in source.modifiers:
        if theirs.type != "ARMATURE":
            continue
        twin = ob.modifiers.new(theirs.name, "ARMATURE")
        for prop in ("use_vertex_groups", "use_bone_envelopes", "use_deform_preserve_volume", "use_multi_modifier",
                     "vertex_group", "invert_vertex_group"):
            setattr(twin, prop, getattr(theirs, prop))
        twin.object = still
    mod = ob.modifiers.new(NAME, "NODES")
    mod.node_group = group
    return ob, mod


def _drive(mod, path, expression):
    mod.driver_remove(path)
    driver = mod.driver_add(path).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def sync(settings, mask, models, moment):
    """The fumble as the panel says, Loose Delay after the big moment at frame `moment`; all of it taken away when
    it is off."""
    from . import cover_nodes
    from .node_groups import input_identifiers

    if mask is None:
        return
    if not getattr(settings, "fumble_enable", False) or moment is None or len(models) < 2 or models[1].armature is None:
        remove(mask, models)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    off = float(moment) + settings.fumble_delay * fps
    new = models[1]
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    group = cover_nodes.ensure_fumble_group()
    hide_group = cover_nodes.ensure_fumble_hide_group()
    ids, hide_ids = input_identifiers(group), input_identifiers(hide_group)
    patterns = mdl.split_patterns(settings.fumble_parts)
    still = None
    keep = []
    puff = materials.ensure_puff_material() if settings.fumble_smoke else None
    for ob in new.meshes:
        if not write_loose(ob, patterns):
            clear_loose([ob])
            continue
        hide = ob.modifiers.get(HIDE)
        if hide is None:
            hide = ob.modifiers.new(HIDE, "NODES")
            hide.node_group = hide_group
        _drive(hide, '["%s"]' % hide_ids["Time"], "frame - %.2f" % off)
        if still is None:
            still = _still(new.armature, mask, collection, off)
            keep.append(still)
        twin, mod = _twin(ob, still, mask, collection, group)
        keep.append(twin)
        me = ob.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        floor = float(co.reshape(-1, 3)[:, 2].min()) if len(co) else 0.0
        height = float(np.ptp(co.reshape(-1, 3)[:, 2])) if len(co) else 1.6
        for name, value in (("Floor", floor), ("Height", height), ("Seed", 11), ("Smoke", settings.fumble_smoke),
                            ("Puff Material", puff)):
            if name in ids:
                mod[ids[name]] = value
        _drive(mod, '["%s"]' % ids["Time"], "(frame - %.2f) / %.3f" % (off, fps))
        twin.update_tag()
    for ob in objects(mask):
        if ob not in keep:
            bpy.data.objects.remove(ob)
