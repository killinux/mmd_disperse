"""The world change (领域展开, Jujutsu Kaisen's domain expansion): from the dancer a sphere opens out and, once it has
swallowed the camera, all of the picture is another world: a starry void (Infinite Void), a crimson wasteland under a
dark sun (Honkai: Star Rail's Phainon, Malevolent Shrine), a field of flowers, a sky mirrored in still water with white
feathers falling (Precure, Wuthering Waves), or a dark concert hall with beams of light and a crowd of light sticks.
Swords, crystals, flowers ... rise where its floor reaches. After the big moment it shatters (or closes back).

One mesh object with no vertices of its own and a Geometry Nodes modifier (node_groups.build_domain_group), in world
space at the origin; the world stays where it opened while the dancer moves in it. Seen from outside, the sphere shows
only its far inner wall: a round window onto the new world behind the body.
"""

import bpy
from mathutils import Vector

from . import materials, particles
from .node_groups import DOMAIN_GROUP, DOMAIN_STYLES, ensure_domain_group, input_identifiers

NAME = "MMD Disperse World"
P_WORLD = "mmd_disperse_world"  # on the world object: the mask of its effect
P_REACH = "mmd_disperse_world_reach"  # on the mask: how far the sphere opens (round the camera) ...
P_REACH_KEY = "mmd_disperse_world_key"  # ... measured for this camera, these frames and this centre
SAMPLES = 24  # camera positions looked at when the camera moves
MARGIN = 1.25  # how much further than the camera the sphere opens
MIN_REACH = 3.0  # ... and at least this many model heights


def world_objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_WORLD) == mask]


def create(mask, collection):
    """The world object of the effect of `mask`."""
    me = bpy.data.meshes.new(NAME)
    ob = bpy.data.objects.new(NAME, me)
    collection.objects.link(ob)
    ob[P_WORLD] = mask
    # a backdrop: it casts no shadow and keeps the light of the scene's own world on the dancer (not in the diffuse
    # rays); still seen in reflections
    for flag in ("visible_shadow", "visible_diffuse", "visible_volume_scatter", "visible_transmission"):
        if hasattr(ob, flag):
            setattr(ob, flag, False)
    mod = ob.modifiers.new(NAME, "NODES")
    mod.node_group = ensure_domain_group()
    return ob


def _moves(ob):
    """True when `ob` or one of its parents is animated or constrained (its place changes with the frame)."""
    while ob is not None:
        ad = ob.animation_data
        if ob.constraints or (ad is not None and (ad.action is not None or len(ad.drivers) or len(ad.nla_tracks))):
            return True
        ob = ob.parent
    return False


def camera_reach(scene, mask, centre, first, last, height):
    """How far the sphere opens: past the scene camera, wherever it is from frame `first` to `last` (looked at in a
    few frames when it moves), with room to spare, and at least MIN_REACH model heights. Kept on the mask until the
    camera, the frames or the centre change."""
    camera = scene.camera
    least = MIN_REACH * height
    if camera is None:
        return least
    key = "%s:%d:%d:%.3f:%.3f:%.3f" % (camera.name, first, last, centre.x, centre.y, centre.z)
    if mask.get(P_REACH_KEY) == key and P_REACH in mask:
        return float(mask[P_REACH])
    spots = [camera.matrix_world.translation.copy()]
    if _moves(camera) and last > first:
        current = scene.frame_current
        try:
            for i in range(SAMPLES + 1):
                scene.frame_set(int(round(first + (last - first) * i / SAMPLES)))
                spots.append(camera.matrix_world.translation.copy())
        finally:
            scene.frame_set(current)
    reach = max(least, MARGIN * max((spot - centre).length for spot in spots))
    mask[P_REACH] = reach
    mask[P_REACH_KEY] = key
    return reach


def sync(settings, mask, centre, floor, height, open_end, close_start, close_end, reach):
    """Push the style, its materials, where it opens and its timing (mask radii) to the world's modifier."""
    style = settings.domain_style
    made = materials.ensure_domain_materials(style)
    scene = settings.id_data
    camera = scene.camera
    back = Vector((0.0, 1.0, 0.0))  # level, from the camera through the centre: what is behind the dancer
    if camera is not None:
        away = centre - camera.matrix_world.translation
        away.z = 0.0
        if away.length > 1e-6:
            back = away.normalized()
    # the crimson world's dark sun hangs behind the dancer and up
    materials.update_domain_materials(style, tuple((back + Vector((0.0, 0.0, 0.55))).normalized()))
    values = {
        "Mask": mask,
        "Center": tuple(centre),
        "Back": tuple(back),
        "Floor": floor,
        "Reach": reach,
        "Height": height,
        "Open End": open_end,
        "Close Start": close_start,
        "Close End": max(close_end, close_start + 1e-4),
        "Shatter": settings.domain_close == "SHATTER",
        "Style": DOMAIN_STYLES.index(style),
        "Prop Count": settings.domain_props,
        "Prop Object": (particles.ensure_asset({"WATER": "FEATHER", "FLOWERS": "PETAL"}[style], scene)
                        if style in ("WATER", "FLOWERS") else None),
        "Sky Material": made["sky"],
        "Ground Material": made["floor"],
        "Prop Material": made["props"],
        "Rim Material": made["rim"],
    }
    for ob in world_objects(mask):
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group and mod.node_group.name == DOMAIN_GROUP:
                ids = input_identifiers(mod.node_group)
                for name, value in values.items():
                    if ids.get(name) is not None and value is not None:
                        mod[ids[name]] = value
        ob.update_tag()


def remove(mask):
    for ob in world_objects(mask):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    for key in (P_REACH, P_REACH_KEY):
        if mask is not None and key in mask:
            del mask[key]
    materials.remove_domain_materials()
