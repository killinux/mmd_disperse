"""The world change (领域展开, Jujutsu Kaisen's domain expansion): from the dancer a sphere opens out and, once it has
swallowed the camera, all of the picture is another world: a starry void (Infinite Void), a crimson wasteland under a
dark sun (Honkai: Star Rail's Phainon, Malevolent Shrine), a field of flowers, a sky mirrored in still water with white
feathers falling (Precure, Wuthering Waves), or a dark concert hall with beams of light and a crowd of light sticks.
Swords, crystals, flowers ... rise where its floor reaches. After the big moment it shatters (or closes back).

One mesh object with no vertices of its own and a Geometry Nodes modifier (node_groups.build_domain_group), in world
space at the origin; the world stays where it opened while the dancer moves in it. Seen from outside, the sphere shows
only its far inner wall: a round window onto the new world behind the body. Only the concert's spotlight goes with
the dancer: it follows an empty of ours on her hips, on the floor (Copy Location of the centre bone, its height kept).

1.17, the world folding round her (世界折叠): instead of opening out of her the new world comes rolling in from the
horizon, its ground curling up all round and over her head into a closed ball at the big moment, and opens out flat
again. A second modifier after the world's own (cover_nodes.build_fold_group) makes the ground a sheet that rolls and
bends, and holds back the sky and the props until the ball has closed.
"""

import bpy
from mathutils import Vector

from . import materials, particles
from .node_groups import DOMAIN_GROUP, DOMAIN_STYLES, ensure_domain_group, input_identifiers
from .toon import CENTER_BONES

NAME = "MMD Disperse World"
FOLLOW = "MMD Disperse Follow Spot"
P_WORLD = "mmd_disperse_world"  # on the world object: the mask of its effect
P_FOLLOW = "mmd_disperse_world_follow"  # on the empty the spotlight follows: the mask of its effect
P_REACH = "mmd_disperse_world_reach"  # on the mask: how far the sphere opens (round the camera) ...
P_REACH_KEY = "mmd_disperse_world_key"  # ... measured for this camera, these frames and this centre
FOLD = "MMD Disperse World Fold"  # the second modifier: the world folding round her (1.17)
LIDS = "MMD Disperse World Eyelids"  # 1.18: the eyelids of the blink, in front of the camera ...
P_LIDS = "mmd_disperse_world_lids"  # ... with the mask of their effect
BLINK = (5, 2, 6)  # frames the eyelids take to shut, stay shut on either side of the change, take to open
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


def _follow(mask, collection, armature, centre):
    """The empty the spotlight follows: at `centre`, on the floor plane wherever the dancer's centre bone goes (it
    stays at `centre` without one)."""
    ob = next((o for o in bpy.data.objects if o.get(P_FOLLOW) == mask), None)
    if ob is None:
        ob = bpy.data.objects.new(FOLLOW, None)
        ob.empty_display_type = "PLAIN_AXES"
        ob.hide_render = True
        collection.objects.link(ob)
        ob[P_FOLLOW] = mask
    ob.location = centre
    for con in list(ob.constraints):
        ob.constraints.remove(con)
    bone = next((name for name in CENTER_BONES if armature is not None and name in armature.data.bones), None)
    if bone is not None:
        con = ob.constraints.new("COPY_LOCATION")
        con.target = armature
        con.subtarget = bone
        con.use_z = False
    return ob


def _unfollow(mask):
    for ob in [o for o in bpy.data.objects if o.get(P_FOLLOW) == mask]:
        bpy.data.objects.remove(ob)


def sync(settings, mask, centre, floor, height, open_end, close_start, close_end, reach, armature=None, fold=None,
         blink=None, seen=None):
    """Push the style, its materials, where it opens and its timing (mask radii) to the world's modifier; the
    spotlight follows the centre bone of `armature` (the dancing model's). With `fold` (its "start", "close" and "end"
    in mask radii, the ball's radius "shell" and the sky's size "sky") the world folds round her (the second
    modifier); without, that modifier goes. With `blink` (two frames) the world shows only between them, eyelids
    shutting over the picture at both. The sky's sun (or moon) hangs behind her as the camera sees her at frame `seen`
    (the big moment; as it is now without it)."""
    style = settings.domain_style
    made = materials.ensure_domain_materials(style)
    scene = settings.id_data
    worlds = world_objects(mask)
    collection = worlds[0].users_collection[0] if worlds and worlds[0].users_collection else scene.collection
    follow = None
    if style == "STAGE":
        follow = _follow(mask, collection, armature, centre)
    else:
        _unfollow(mask)
    camera = scene.camera
    back = Vector((0.0, 1.0, 0.0))  # level, from the camera through the centre: what is behind the dancer
    if camera is not None:
        away = centre - camera.matrix_world.translation
        away.z = 0.0
        if away.length > 1e-6:
            back = away.normalized()
    # the crimson world's dark sun hangs behind the dancer and up; the dream's moon low over the horizon (a long lens
    # sees little of the sky): behind her as the camera sees her at the big moment
    from . import sampling

    sky = back
    shot = sampling.camera_at(scene, seen) if seen is not None else None
    if shot is not None:
        away = centre - sampling.matrix_at(shot, seen).translation
        away.z = 0.0
        if away.length > 1e-6:
            sky = away.normalized()
    materials.update_domain_materials(style, tuple((sky + Vector((0.0, 0.0, 0.2 if style == "DREAM" else 0.55)))
                                                   .normalized()))
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
        "Follow": follow,
    }
    for ob in worlds:
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group and mod.node_group.name == DOMAIN_GROUP:
                ids = input_identifiers(mod.node_group)
                for name, value in values.items():
                    if ids.get(name) is not None and value is not None:
                        mod[ids[name]] = value
        _blink_world(ob, blink)
        _fold(ob, None if fold is None else {
            "Mask": mask, "Center": tuple(centre), "Floor": floor, "Height": height, "Reach": reach,
            "Shell": fold["shell"], "Sky": fold["sky"], "Fold Start": fold["start"], "Fold Close": fold["close"],
            "Fold End": fold["end"], "Close Start": close_start, "Close End": max(close_end, close_start + 1e-4),
            "Follow": follow, "Ground Material": made["floor"], "Sky Material": made["sky"],
            "Rim Material": made["rim"]})
        ob.update_tag()
    _lids(scene, mask, collection, blink)


def _blink_world(ob, blink):
    """The world shown only between the frames of `blink` (shut eyelids hide the change), or always."""
    from .cover import _clear_keys, _shown

    _clear_keys(ob)
    ob.hide_render = ob.hide_viewport = False
    if blink is not None:
        _shown(ob, int(round(blink[0])), int(round(blink[1])))


def _lids(scene, mask, collection, blink):
    """The eyelids in front of the camera, shut at each frame of `blink` (or none)."""
    from . import shots
    from .cover import _clear_keys, _key, _shown
    from .picture import _frame

    ob = next((o for o in bpy.data.objects if o.get(P_LIDS) == mask), None)
    camera = shots.carrier(scene, mask)
    if blink is None or camera is None:
        if ob is not None:
            data = ob.data
            bpy.data.objects.remove(ob)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        return
    if ob is not None and ob.parent != camera:
        data = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(data)
        ob = None
    if ob is None:
        centre, width, tall = _frame(scene, camera, 1.0)
        half_w, half_h = 0.55 * width, 0.55 * tall
        me = bpy.data.meshes.new(LIDS)
        me.from_pydata([(centre.x + sx * half_w, centre.y + sy * half_h, -1.0)
                        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))], [], [(0, 1, 2, 3)])
        layer = me.uv_layers.new(name="UVMap")
        for loop in me.loops:
            layer.data[loop.index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
        me.materials.append(materials.ensure_cover_material("EYELID"))
        ob = bpy.data.objects.new(LIDS, me)
        collection.objects.link(ob)
        ob[P_LIDS] = mask
        ob.hide_select = True
        ob.parent = camera
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
    _clear_keys(ob)
    depth = 1.002 * camera.data.clip_start
    ob.scale = (depth, depth, depth)
    shut, held, opening = BLINK
    keys = []
    for at in blink:
        keys += [(at - shut - held, 0.0), (at - held, 1.0), (at + held, 1.0), (at + held + opening, 0.0)]
    ob["mmdd_lid"] = 0.0
    _key(ob, '["mmdd_lid"]', keys, interpolation="BEZIER")
    _shown(ob, int(blink[0] - shut - held) - 1, int(blink[1] + held + opening) + 1)


def _fold(ob, values):
    """The world folding round her: the second modifier on `ob` with `values`, or none."""
    from .cover_nodes import ensure_fold_group

    mod = next((m for m in ob.modifiers if m.type == "NODES" and m.name == FOLD), None)
    if values is None:
        if mod is not None:
            ob.modifiers.remove(mod)
        return
    group = ensure_fold_group()
    if mod is None:
        mod = ob.modifiers.new(FOLD, "NODES")
    if mod.node_group != group:
        mod.node_group = group
    ids = input_identifiers(group)
    for name, value in values.items():
        if ids.get(name) is not None and value is not None:
            mod[ids[name]] = value


def remove(mask):
    for ob in world_objects(mask):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    for ob in [o for o in bpy.data.objects if o.get(P_LIDS) == mask]:
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    _unfollow(mask)
    for key in (P_REACH, P_REACH_KEY):
        if mask is not None and key in mask:
            del mask[key]
    materials.remove_domain_materials()
    from .cover_nodes import FOLD_GROUP

    ng = bpy.data.node_groups.get(FOLD_GROUP)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)
