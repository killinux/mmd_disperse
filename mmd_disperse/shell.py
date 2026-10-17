"""A shell round the dancer for the big moment (1.12): a barrier dome rising over her (结界, KPop Demon Hunters' Honmoon),
a soap bubble (Glinda's), a shield of hexagons that shrinks into her, a candy wrapper twisted shut round her, or a ball
of water. It forms on the way to the big moment (the swap, or the new outfit complete) and goes then: the dome
shatters, the bubble pops, the shield has shrunk into her, the wrapper untwists and falls open, the water bursts.

One mesh object with no vertices of its own and a Geometry Nodes modifier (node_groups.build_shell_group), in world
space at the origin; it goes with the dancer across the floor (an empty of ours follows her centre bone, its height
kept on the floor).
"""

import bpy

from . import materials
from .node_groups import SHELL_GROUP, SHELL_STYLES, ensure_shell_group, input_identifiers
from .toon import CENTER_BONES

NAME = "MMD Disperse Shell"
FOLLOW = "MMD Disperse Shell Follow"
P_SHELL = "mmd_disperse_shell"  # on the shell object and its empty: the mask of their effect
P_KIND = "mmd_disperse_shell_kind"  # ... SHELL or FOLLOW


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_SHELL) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _shell(mask, collection):
    ob = next(iter(objects(mask, "SHELL")), None)
    if ob is None:
        me = bpy.data.meshes.new(NAME)
        ob = bpy.data.objects.new(NAME, me)
        collection.objects.link(ob)
        ob[P_SHELL] = mask
        ob[P_KIND] = "SHELL"
        for flag in ("visible_shadow",):
            if hasattr(ob, flag):
                setattr(ob, flag, False)
        mod = ob.modifiers.new(NAME, "NODES")
        mod.node_group = ensure_shell_group()
    return ob


def _follow(mask, collection, armature, spot):
    """The empty the shell goes with: at `spot`, on the floor wherever the dancer's centre bone goes."""
    ob = next(iter(objects(mask, "FOLLOW")), None)
    if ob is None:
        ob = bpy.data.objects.new(FOLLOW, None)
        ob.empty_display_type = "PLAIN_AXES"
        ob.hide_render = True
        ob.hide_select = True
        collection.objects.link(ob)
        ob[P_SHELL] = mask
        ob[P_KIND] = "FOLLOW"
    ob.location = spot
    for con in list(ob.constraints):
        ob.constraints.remove(con)
    bone = next((name for name in CENTER_BONES if armature is not None and name in armature.data.bones), None)
    if bone is not None:
        con = ob.constraints.new("COPY_LOCATION")
        con.target = armature
        con.subtarget = bone
        con.use_z = False
    return ob


def sync(settings, mask, spot, floor, height, form_end, moment, go_end, armature=None):
    """Create / update / remove the shell as the panel says: its style, size and timing (mask radii)."""
    if not settings.shell_enable:
        remove(mask)
        return
    scene = settings.id_data
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    ob = _shell(mask, collection)
    follow = _follow(mask, collection, armature, spot)
    style = settings.shell_style
    mat = materials.ensure_shell_material(style)
    materials.update_shell_material(style, settings.shell_color, settings.shell_glow)
    values = {
        "Mask": mask,
        "Follow": follow,
        "Style": SHELL_STYLES.index(style),
        "Height": height,
        "Floor": floor,
        "Size": settings.shell_size,
        "Form End": form_end,
        "Moment": moment,
        "Go End": max(go_end, moment + 1e-4),
        "Material": mat,
    }
    for mod in ob.modifiers:
        if mod.type == "NODES" and mod.node_group and mod.node_group.name == SHELL_GROUP:
            ids = input_identifiers(mod.node_group)
            for name, value in values.items():
                if ids.get(name) is not None and value is not None:
                    mod[ids[name]] = value
    ob.update_tag()


def remove(mask):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    for name in [m.name for m in bpy.data.materials if m.name.startswith(materials.SHELL_MATERIAL)]:
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
