"""Morph (形变, 1.24): at the big moment the new outfit does not just appear as it is:
- From the Old Shape (Willow's MORF, Black or White's faces): it comes in the old outfit's shape and settles into its
  own, a little past it and back: a skirt out of tight trousers, a vest's long tails out of a tight suit;
- Skirt Drop (裙摆落下绽开, its simplest case: Cinderella's turn): its skirt comes gathered up at her waist and drops,
  flaring out and settling.

What we put on the new outfit's meshes: a small geometry nodes modifier BEFORE their armature (it moves them at rest;
the armature then takes them as she dances), cover_nodes' morph group; on their mesh data where each point comes from
(ATTR_MORPH: to the nearest point of the old outfit's cloth at rest, worked out once for a pair of outfits) and which
points are the skirt (ATTR_SKIRT, by material name).
"""

import fnmatch

import bpy
import numpy as np

from . import model as mdl

P_MORPH = "mmd_disperse_morph"  # on the new outfit's meshes we put the modifier on: the mask of their effect
P_MORPH_KEY = "mmd_disperse_morph_key"  # on their mesh data: which old outfit ATTR_MORPH was worked out for
NAME = "MMD Disperse Morph"
STYLES = ("SHAPE", "SKIRT")
GATHER = 0.12  # Skirt Drop: how long the gathered skirt is (a share of its own length)
WAIST = ("下半身", "LowerBody", "lower body", "Hips", "hips", "pelvis", "J_Bip_C_Hips")


def clear(meshes):
    from .cover_nodes import ATTR_MORPH, ATTR_SKIRT

    for ob in meshes:
        if ob.type != "MESH":
            continue
        mod = ob.modifiers.get(NAME)
        if mod is not None:
            ob.modifiers.remove(mod)
        for name in (ATTR_MORPH, ATTR_SKIRT):
            if ob.data.attributes.get(name) is not None:
                ob.data.attributes.remove(ob.data.attributes[name])
        if P_MORPH_KEY in ob.data:
            del ob.data[P_MORPH_KEY]
        if P_MORPH in ob:
            del ob[P_MORPH]


def remove(mask, models=()):
    clear([ob for ob in bpy.data.objects if ob.get(P_MORPH) == mask] + [ob for model in models for ob in model.meshes])
    if not any(ob.get(P_MORPH) is not None for ob in bpy.data.objects):
        from .cover_nodes import MORPH_GROUP

        ng = bpy.data.node_groups.get(MORPH_GROUP)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)


def _faces_matching(ob, patterns, matching):
    """Per face of `ob`: True where its material matches one of `patterns` (`matching`) or matches none of them."""
    me = ob.data
    hit = np.array([s.material is not None and (any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                    for p in patterns) == matching) for s in ob.material_slots]
                   or [False], dtype=bool)
    index = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", index)
    return hit[np.clip(index, 0, len(hit) - 1)]


def _points_of(ob, faces):
    """Per point of `ob`: True when it is a corner of one of `faces` (a bool per face)."""
    me = ob.data
    starts = np.zeros(len(me.polygons), dtype=np.int32)
    totals = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    loops = np.zeros(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    used = np.zeros(len(me.vertices), dtype=bool)
    used[loops[np.repeat(faces, totals)]] = True
    return used


def _world(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    return co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3], mw


def _old_surface(old_meshes, patterns):
    """A BVH tree of the old outfit's cloth (the faces matching none of `patterns`) at rest, in world space."""
    from mathutils.bvhtree import BVHTree

    verts, polys = [], []
    for ob in old_meshes:
        faces = _faces_matching(ob, patterns, False)
        if not faces.any():
            continue
        world, _mw = _world(ob)
        base = len(verts)
        verts += [tuple(v) for v in world]
        polys += [[base + i for i in p.vertices] for p, on in zip(ob.data.polygons, faces) if on]
    return BVHTree.FromPolygons(verts, polys) if polys else None


def _write_shape(ob, tree, cloth, key, push):
    """ATTR_MORPH on `ob`: from each point of its cloth (`cloth`, a bool per point) to the nearest point of the old
    outfit (`tree`, world space) and `push` out from it (on it, the new outfit's cloth would be in her skin), in its own
    space; nothing for the rest. Kept when made for the same `key`."""
    from .cover_nodes import ATTR_MORPH

    me = ob.data
    if me.attributes.get(ATTR_MORPH) is not None and me.get(P_MORPH_KEY) == key:
        return True
    world, mw = _world(ob)
    offsets = np.zeros((len(world), 3), dtype=np.float64)
    from mathutils import Vector
    for i in np.flatnonzero(cloth):
        found = tree.find_nearest(Vector(world[i]))
        if found[0] is not None:
            offsets[i] = np.array(found[0] + found[1] * push) - world[i]
    local = offsets @ np.linalg.inv(mw[:3, :3]).T
    if me.attributes.get(ATTR_MORPH) is not None:
        me.attributes.remove(me.attributes[ATTR_MORPH])
    attr = me.attributes.new(ATTR_MORPH, "FLOAT_VECTOR", "POINT")
    attr.data.foreach_set("vector", local.astype(np.float32).ravel())
    me[P_MORPH_KEY] = key
    return bool(cloth.any())


def _write_skirt(ob, skirt):
    """ATTR_SKIRT on `ob`: 1 on the points of its skirt (`skirt`, a bool per point)."""
    from .cover_nodes import ATTR_SKIRT

    me = ob.data
    if me.attributes.get(ATTR_SKIRT) is not None:
        me.attributes.remove(me.attributes[ATTR_SKIRT])
    attr = me.attributes.new(ATTR_SKIRT, "FLOAT", "POINT")
    attr.data.foreach_set("value", skirt.astype(np.float32))
    return bool(skirt.any())


def _before_armature(ob, mod):
    """Our modifier right before the first Armature modifier (it moves the mesh at rest)."""
    mods = list(ob.modifiers)
    arm = [i for i, m in enumerate(mods) if m.type == "ARMATURE"]
    target = arm[0] if arm else 0
    current = mods.index(mod)
    if current > target:
        ob.modifiers.move(current, target)


def sync(settings, mask, models, moment):
    """The morph as the panel says, from the big moment at frame `moment`; all taken away when it is off."""
    from . import cover_nodes, peel
    from .node_groups import input_identifiers

    if mask is None:
        return
    if not getattr(settings, "morph_enable", False) or moment is None or len(models) < 2:
        remove(mask, models)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    span = max(settings.morph_time * fps, 1.0)
    old, new = models[0], models[1]
    style = settings.morph_style
    group = cover_nodes.ensure_morph_group()
    ids = input_identifiers(group)
    patterns = peel._patterns(settings)  # (her skin, face, hair and the like do not morph)
    skirts = mdl.split_patterns(settings.morph_parts)
    push = 0.003 * max(settings.size_reference, 1e-3)
    key = "|".join(sorted("%s:%d" % (o.name, len(o.data.vertices)) for o in old.meshes)) + "|%s|%.5f" % (
        ";".join(patterns), push)
    tree = _old_surface(old.meshes, patterns) if style == "SHAPE" else None
    done = []
    for ob in new.meshes:
        if not ob.data.polygons:
            continue
        if style == "SHAPE":
            moved = tree is not None and _write_shape(ob, tree, _points_of(ob, _faces_matching(ob, patterns, False)),
                                                      key, push)
        else:
            moved = _write_skirt(ob, _points_of(ob, _faces_matching(ob, skirts, True)))
        if not moved:
            clear([ob])
            continue
        mod = ob.modifiers.get(NAME)
        if mod is None:
            mod = ob.modifiers.new(NAME, "NODES")
        mod.node_group = group
        _before_armature(ob, mod)
        ob[P_MORPH] = mask
        centre, size, _shoulder = peel.measure(ob, old.armature)
        waist = peel._bone_head(old.armature, WAIST, ob)
        for name, value in (("Style", STYLES.index(style)), ("Waist", waist.z if waist is not None else centre.z),
                            ("Centre", tuple(centre)), ("Height", size.z), ("Gather", GATHER)):
            if name in ids:
                mod[ids[name]] = value
        path = '["%s"]' % ids["Time"]
        mod.driver_remove(path)
        driver = mod.driver_add(path).driver
        driver.type = "SCRIPTED"
        driver.expression = "(frame - %.2f) / %.2f" % (float(moment), span)
        done.append(ob)
    for ob in [o for o in bpy.data.objects if o.get(P_MORPH) == mask and o not in done]:
        clear([ob])
