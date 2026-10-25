"""Tearing the old outfit off (撕开、翻落、扯掉、卷起剥落, 1.19): at the big moment the old outfit does not just vanish;
its clothes come apart over Tear Time round the new outfit, which is already on:
- Rip Open (撕开): split down the middle, the halves swing open round her sides like the flaps of a coat and fly off
  (Superman tearing his shirt open on the S; Rumi's stage outfit torn away in KPop Demon Hunters);
- Flip Down (ぶっ返り): kabuki's basting threads pulled, everything above the waist turns down over it inside out, its
  lining showing, hangs there a while and drops;
- Yank Off (引抜き): kabuki's instant change, the top pulled up and away and the bottom dropping, in a few frames;
- Peel Off (剥落卷起): it comes off in strips that curl down from the top one after another, like a sticker.
Skin, face, hair and whatever Keep On names are not torn (they go with the old model as before); the inside of the
torn cloth shows the lining colour (spliced into its materials, for the twins only). Layer by layer (层层撕回, 1.21:
Agatha All Along's ballad, each verse an earlier age): several layers of it, torn off one after another a Layer Gap
apart, the last at the big moment; under the outer one (her own colours) each is in the colour of an earlier age (the
70s, black and white, an old photo ...).

Our objects: a twin of each mesh of the old outfit (the same mesh data, P_PEEL = the mask), its modifiers its
armature's and then our geometry nodes (cover_nodes' peel group), which tell the pieces apart by where they are at
rest and move them as she is posed now, rigidly round hinges that go with her body: two empties for each twin
following her upper and lower body (Child Of their bones; at rest where the twin is). A face attribute on the old
meshes (cover_nodes.ATTR_TEAR) marks what tears.
"""

import fnmatch

import bpy
import numpy as np

from . import materials
from . import model as mdl

P_PEEL = "mmd_disperse_peel"  # on our twins: the mask of their effect ...
P_SOURCE = "mmd_disperse_peel_source"  # ... the mesh it is of ...
P_KIND = "mmd_disperse_peel_kind"  # ... TWIN, UPPER or LOWER ...
P_LAYER = "mmd_disperse_peel_layer"  # ... and a twin's layer (0 the outer one)
AGES = ((0.95, 0.62, 0.35), (0.86, 0.86, 0.86), (0.8, 0.6, 0.36), (0.55, 0.85, 1.0))  # the 70s, black and white,
# an old photo, a faded blue print: the colours of the layers under the outer one
NAME = "MMD Disperse Peel"
STYLES = ("RIP", "FLIP", "YANK", "STRIPS")
WAIST = ("下半身", "LowerBody", "lower body", "Hips", "hips", "pelvis", "J_Bip_C_Hips")
CHEST = ("上半身2", "上半身", "UpperBody2", "UpperBody", "upper body 2", "upper body", "Chest", "chest", "Spine2",
         "J_Bip_C_Chest")


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_PEEL) == mask and (kind is None or ob.get(P_KIND) == kind)]


def clear_tear(meshes):
    from .cover_nodes import ATTR_TEAR

    for ob in meshes:
        if ob.type == "MESH" and ob.data.attributes.get(ATTR_TEAR) is not None:
            ob.data.attributes.remove(ob.data.attributes[ATTR_TEAR])


def remove(mask, models=()):
    sources = [bpy.data.objects.get(ob.get(P_SOURCE, "")) for ob in objects(mask)]
    for ob in objects(mask):
        bpy.data.objects.remove(ob)
    clear_tear([ob for ob in sources if ob is not None] + [ob for model in models for ob in model.meshes])
    if not any(ob.get(P_PEEL) is not None for ob in bpy.data.objects):
        from .cover_nodes import PEEL_GROUP

        ng = bpy.data.node_groups.get(PEEL_GROUP)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
        mat = bpy.data.materials.get(materials.THREAD_MATERIAL)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
        for mat in [m for m in bpy.data.materials if m.get(materials.P_LINING)]:
            materials.remove_lining(mat)


def _patterns(settings):
    """Material name patterns that are not torn: the face, hair and the like always, Keep On, and the shared parts."""
    out = mdl.split_patterns(mdl.DEFAULT_LOCK_PATTERNS) + mdl.split_patterns(settings.peel_keep)
    if settings.use_lock:
        out += mdl.split_patterns(settings.lock_patterns)
    return out


def write_tear(ob, patterns):
    """Mark the faces of `ob` that tear (ATTR_TEAR, a boolean face attribute): those whose material matches none of
    `patterns`. The number of them."""
    from .cover_nodes import ATTR_TEAR

    me = ob.data
    if me.attributes.get(ATTR_TEAR) is not None:
        me.attributes.remove(me.attributes[ATTR_TEAR])
    torn = np.array([s.material is not None and not any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                        for p in patterns) for s in ob.material_slots] or [False],
                    dtype=bool)
    index = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", index)
    values = torn[np.clip(index, 0, len(torn) - 1)]
    if not values.any():
        return 0
    attr = me.attributes.new(ATTR_TEAR, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", values)
    return int(values.sum())


def _bone_head(armature, names, ob):
    """Head of the first of `names` in `armature`, in the local space of mesh `ob` (rest pose); None if none."""
    if armature is None:
        return None
    bone = next((armature.data.bones[n] for n in names if n in armature.data.bones), None)
    if bone is None:
        return None
    return ob.matrix_world.inverted() @ (armature.matrix_world @ bone.head_local)


def measure(ob, armature):
    """(centre (x, y of her middle line, z of the waist), size (half width at the shoulders, half depth, height),
    shoulder height) of mesh `ob` in its own rest space."""
    from mathutils import Vector

    from .spirit import ARMS

    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    if not len(co):
        return Vector((0.0, 0.0, 1.0)), Vector((0.2, 0.12, 1.6)), 1.4
    lo, hi = co.min(axis=0), co.max(axis=0)
    height = float(hi[2] - lo[2]) or 1.0
    left, right = _bone_head(armature, ARMS[0], ob), _bone_head(armature, ARMS[1], ob)
    waist = _bone_head(armature, WAIST, ob)
    if left is not None and right is not None:
        x0, width, shoulder = 0.5 * (left.x + right.x), max(0.5 * abs(left.x - right.x), 0.04 * height), \
            0.5 * (left.z + right.z)
    else:
        x0, width, shoulder = 0.5 * float(lo[0] + hi[0]), 0.11 * height, float(lo[2]) + 0.82 * height
    zw = waist.z if waist is not None else float(lo[2]) + 0.53 * height
    # her depth at the chest, from what is not her hair (long hair hangs down her back)
    keep = mdl.split_patterns(mdl.DEFAULT_LOCK_PATTERNS)
    body = np.array([s.material is None or not any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                  for p in keep) for s in ob.material_slots] or [True], dtype=bool)
    index = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", index)
    starts = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    loops = np.zeros(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    totals = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", totals)
    face_ok = body[np.clip(index, 0, len(body) - 1)]
    used = np.zeros(len(co), dtype=bool)
    used[loops[np.repeat(face_ok, totals)]] = True
    zc0, zc1 = zw + 0.3 * (shoulder - zw), shoulder - 0.1 * (shoulder - zw)
    chest = used & (np.abs(co[:, 0] - x0) < 0.5 * width) & (co[:, 2] > zc0) & (co[:, 2] < zc1)
    if chest.sum() > 10:
        ys = co[chest, 1]
        y_lo, y_hi = np.percentile(ys, 2), np.percentile(ys, 98)
        y0, depth = 0.5 * (y_lo + y_hi), max(0.5 * (y_hi - y_lo), 0.02 * height)
    else:
        y0, depth = 0.5 * float(lo[1] + hi[1]), 0.6 * width
    return Vector((x0, y0, zw)), Vector((width, depth, height)), float(shoulder)


def _frame(twin, mask, collection, armature, names, kind, world):
    """The empty that goes with her body part (the first of bones `names`): Child Of the bone, at rest where `twin`
    is (`world`, the matrix of the mesh it is a twin of), so that seen from the twin it carries the bone's move since
    rest (None without such a bone)."""
    bone = next((armature.data.bones[n] for n in names if armature is not None and n in armature.data.bones), None)
    ob = next((o for o in objects(mask, kind) if o.get(P_SOURCE) == twin.get(P_SOURCE)), None)
    if bone is None:
        if ob is not None:
            bpy.data.objects.remove(ob)
        return None
    if ob is None:
        ob = bpy.data.objects.new("%s %s %s" % (NAME, kind.title(), twin.get(P_SOURCE)), None)
        collection.objects.link(ob)
        ob[P_PEEL], ob[P_SOURCE], ob[P_KIND] = mask, twin.get(P_SOURCE), kind
        ob.hide_select = True
        ob.hide_render = True
        ob.empty_display_size = 0.05
    for c in list(ob.constraints):
        ob.constraints.remove(c)
    ob.parent = None
    ob.matrix_basis = world.copy()
    con = ob.constraints.new("CHILD_OF")
    con.target, con.subtarget = armature, bone.name
    con.inverse_matrix = (armature.matrix_world @ bone.matrix_local).inverted()
    try:
        ob.hide_set(True)
    except RuntimeError:  # (not in the view layer: hidden there anyway)
        pass
    return ob


def _twin(source, mask, collection, group, layer=0):
    """The twin of mesh `source` (of layer `layer`): its mesh data, its armature first, then our group."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name and o.get(P_LAYER, 0) == layer),
              None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s %s%s" % (NAME, source.name, " %d" % layer if layer else ""), source.data)
        collection.objects.link(ob)
        ob[P_PEEL], ob[P_SOURCE], ob[P_KIND], ob[P_LAYER] = mask, source.name, "TWIN", layer
        ob[materials.LINING_ON] = 1.0  # (its materials show the lining inside)
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
    """The tearing as the panel says, from the big moment at frame `moment`; all of it taken away when it is off."""
    from . import cover_nodes
    from .node_groups import input_identifiers

    if mask is None:
        return
    if not getattr(settings, "peel_enable", False) or moment is None or len(models) < 2:
        remove(mask, models)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    span = max(settings.peel_time * fps, 1.0)
    old = models[0]
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    group = cover_nodes.ensure_peel_group()
    ids = input_identifiers(group)
    patterns = _patterns(settings)
    layers = max(1, int(getattr(settings, "peel_layers", 1)))
    gap = max(getattr(settings, "peel_layer_gap", 0.5), 0.05) * fps
    keep, torn = [], set()
    thread = materials.ensure_thread_material(tuple(settings.peel_thread_color)) \
        if settings.peel_threads > 0.0 else None
    for ob in old.meshes:
        if not write_tear(ob, patterns):
            continue
        torn |= {s.material for s, on in zip(ob.material_slots, _torn_slots(ob, patterns)) if on}
        centre, size, shoulder = measure(ob, old.armature)
        upper = lower = None
        for layer in range(layers):  # (0 the outer one, torn first; the last at the big moment)
            twin, mod = _twin(ob, mask, collection, group, layer)
            if not layer:
                upper = _frame(twin, mask, collection, old.armature, CHEST, "UPPER", ob.matrix_world)
                lower = _frame(twin, mask, collection, old.armature, WAIST, "LOWER", ob.matrix_world)
                keep += [o for o in (upper, lower) if o is not None]
            keep.append(twin)
            twin[materials.LINING_SCALE] = 40.0 / max(size.z, 1e-3)
            twin[materials.LINING_ERA] = 1.0 if layer else 0.0
            twin[materials.LINING_ERA_COLOR] = AGES[(layer - 1) % len(AGES)] if layer else (1.0, 1.0, 1.0)
            start = float(moment) - (layers - 1 - layer) * gap
            for name, value in (("Upper", upper or lower), ("Lower", lower or upper),
                                ("Style", STYLES.index(settings.peel_style)), ("Centre", tuple(centre)),
                                ("Size", tuple(size)), ("Shoulder", shoulder), ("Strips", int(settings.peel_strips)),
                                ("Hold", settings.peel_hold / max(settings.peel_time, 0.01)), ("Seed", 7 + layer),
                                ("Threads", float(settings.peel_threads)), ("Thread Material", thread),
                                ("Show From", -layer * gap / span), ("Push", float(layers - layer))):
                if name in ids:
                    mod[ids[name]] = value
            path = '["%s"]' % ids["Time"]
            mod.driver_remove(path)
            driver = mod.driver_add(path).driver
            driver.type = "SCRIPTED"
            driver.expression = "(frame - %.2f) / %.2f" % (start, span)
            twin.update_tag()
    for ob in objects(mask):
        if ob not in keep:
            bpy.data.objects.remove(ob)
    for mat in [m for m in bpy.data.materials if m.get(materials.P_LINING) and m not in torn]:
        materials.remove_lining(mat)
    for mat in torn:
        materials.add_lining(mat, tuple(settings.peel_lining))


def _torn_slots(ob, patterns):
    return [s.material is not None and not any(fnmatch.fnmatchcase(mdl.material_key(s.material), p) for p in patterns)
            for s in ob.material_slots]
