"""Outfits before the old one (服装链, 1.13): the dancer goes through several outfits on one dance, the cheapest way.
Each outfit of the chain is a model of its own that follows the old model like the new outfit does (its root copies
the old root, its meshes deform with the old armature, effect.build binds them); it shows from the cut before it to
its own cut, the first from the start, and the old outfit from the last cut on, a little before the transformation,
which brings the new outfit with all its front. Each cut is a hard cut hidden behind a flash of white (or a black
frame) on a card in front of the camera. The cuts come every beat, bar or four bars (on the beats with beat sync, the
last one Lead before the start).

Showing and hiding is a small Geometry Nodes modifier at the end of each mesh (cover_nodes' Chain Show: its geometry
only between From and To), so it works the same in the viewport and the render, with nothing driven. Removing the
effect takes it all off and puts the outfits back as they were."""

import bpy

from . import beats, materials, shots
from . import model as mdl

P_CHAIN = "mmd_disperse_chain"  # on the meshes we show and hide: the mask
P_MODELS = "mmd_disperse_chain_models"  # on the mask: the roots of the chain's outfits, in order
P_CARD = "mmd_disperse_chain_card"  # on the card: the mask
MOD = "MMD Disperse Chain"
CARD = "MMD Disperse Chain Cut"
BEATS_APART = {"BEAT": 1, "BAR": 4, "PHRASE": 16}  # beats between two cuts ...
SECONDS_APART = {"BEAT": 0.45, "BAR": 1.8, "PHRASE": 7.2}  # ... or seconds without beats
LEAD = 0.5  # the last cut (to the old outfit) this many seconds before the transformation starts
FADE = {"FLASH": 4, "BLACK": 2}  # frames the card takes to clear after a cut
FOREVER = 1.0e6


def models(settings):
    """The outfits of the panel's chain that can be used (a model with meshes, not the old or the new outfit, each
    once), in order."""
    taken = {m.root for m in (mdl.resolve(settings.base) if settings.base else None,
                              mdl.resolve(settings.target) if settings.target else None) if m is not None}
    out, seen = [], set()
    for item in settings.chain:
        if item.outfit is None:
            continue
        m = mdl.resolve(item.outfit)
        if not m.meshes or m.root is None or m.root in taken or m.root.name in seen:
            continue
        seen.add(m.root.name)
        out.append(m)
    return out


def attach(mask, links):
    """Remember the chain's outfits on the mask and mark their meshes (after the build bound them)."""
    mask[P_MODELS] = [m.root.name for m in links]
    for m in links:
        for ob in m.meshes:
            ob[P_CHAIN] = mask


def cut_frames(settings, count):
    """The frames of the `count` cuts: the last LEAD before the start, the others BEATS_APART beats (with beat sync
    and enough beats) or SECONDS_APART before each other."""
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    last = settings.frame_start - LEAD * fps
    found = [b for b in beats.beat_frames() if b <= last] if settings.beat_sync else []
    step = BEATS_APART[settings.chain_pace]
    if len(found) > step * (count - 1):
        return [float(found[len(found) - 1 - step * (count - 1 - k)]) for k in range(count)]
    gap = SECONDS_APART[settings.chain_pace] * fps
    return [float(round(last - gap * (count - 1 - k))) for k in range(count)]


def _show(ob, mask, start, end):
    """Show the mesh only from frame `start` to before `end` (the modifier at the end of its stack)."""
    from . import cover_nodes
    from .node_groups import input_identifiers

    mod = ob.modifiers.get(MOD)
    if mod is None:
        mod = ob.modifiers.new(MOD, "NODES")
    mod.node_group = cover_nodes.ensure_chain_group()
    ids = input_identifiers(mod.node_group)
    mod[ids["From"]] = float(start)
    mod[ids["To"]] = float(end)
    ob[P_CHAIN] = mask
    ob.update_tag()


def _card(scene, mask, cuts, style):
    """The card in front of the camera that hides each cut: white flashing out, or a black frame."""
    from .cover import _clear_keys, _near_depth, _plane
    from .pyro import _key

    camera = shots.carrier(scene, mask)
    card = next((ob for ob in bpy.data.objects if ob.get(P_CARD) == mask), None)
    if camera is None or camera.type != "CAMERA":
        if card is not None:
            _delete(card)
        return
    if card is None:
        me = bpy.data.meshes.new(CARD)
        me.from_pydata([(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)], [], [(0, 1, 2, 3)])
        me.materials.append(materials.ensure_cover_material("CUT"))
        card = bpy.data.objects.new(CARD, me)
        collection = mask.users_collection[0] if mask.users_collection else scene.collection
        collection.objects.link(card)
        card[P_CARD] = mask
        card.hide_select = True
        if hasattr(card, "visible_shadow"):
            card.visible_shadow = False
    card.parent = camera
    card.matrix_parent_inverse.identity()
    depth = _near_depth(camera)
    centre, width, height = _plane(scene, camera, depth)
    card.location = (centre.x, centre.y, -depth)
    card.rotation_euler = (0.0, 0.0, 0.0)
    card.scale = (width * 1.2, height * 1.2, 1.0)
    card["mmdd_color"] = (1.0, 1.0, 1.0) if style == "FLASH" else (0.0, 0.0, 0.0)
    _clear_keys(card)
    fade = FADE[style]
    keys = [(cuts[0] - 2.0, 0.0)]
    for c in cuts:
        keys += [(c - 1.0, 0.0), (c, 1.0)] + ([(c + 1.0, 1.0)] if style == "BLACK" else []) + [(c + fade, 0.0)]
    _key(card, '["mmdd_fade"]', keys)


def _delete(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def sync(settings, mask, base):
    """Show each outfit of the chain from the cut before it to its own, the old outfit (`base`) from the last cut on,
    and hide the cuts behind the card; nothing without a chain."""
    names = list(mask.get(P_MODELS, [])) if mask is not None else []
    links = [mdl.resolve(bpy.data.objects[n]) for n in names if n in bpy.data.objects]
    links = [m for m in links if m.meshes]
    if not links or base is None or not base.meshes:
        _unshow(mask)
        return
    scene = settings.id_data
    cuts = cut_frames(settings, len(links))
    for k, link in enumerate(links):
        for ob in link.meshes:
            _show(ob, mask, cuts[k - 1] if k > 0 else -FOREVER, cuts[k])
    for ob in base.meshes:
        _show(ob, mask, cuts[-1], FOREVER)
    _card(scene, mask, cuts, settings.chain_cut)


def _unshow(mask):
    """The showing and hiding off every mesh, the card away (the chain's outfits stay bound)."""
    for ob in [o for o in bpy.data.objects if o.get(P_CHAIN) == mask]:
        mod = ob.modifiers.get(MOD)
        if mod is not None:
            ob.modifiers.remove(mod)
    for ob in [o for o in bpy.data.objects if o.get(P_CARD) == mask]:
        _delete(ob)


def remove(mask):
    """Take the showing and hiding off and the card away, and give the chain's outfits their own armatures back (their
    roots and copied poses go back with the effect's own: effect.remove_effect)."""
    from .effect import P_ARM, P_ROLE

    _unshow(mask)
    for ob in [o for o in bpy.data.objects if o.get(P_CHAIN) == mask]:
        if ob.get(P_ARM) and ob.get(P_ROLE) is None:  # (not the old outfit's: the effect puts those back)
            for mod_name, arm_name in ob[P_ARM].to_dict().items():
                arm_mod = ob.modifiers.get(mod_name)
                if arm_mod is not None and arm_mod.type == "ARMATURE":
                    arm_mod.object = bpy.data.objects.get(arm_name) if arm_name else None
            del ob[P_ARM]
        del ob[P_CHAIN]
