"""The front's decoration for the sweeps and the spiral: a magic circle, a ring of sparks, a glowing panel or a sheet of
TV static the body passes through, a ring of light, or a comet of sparkles or a band of toon water circling it.

One mesh object with no vertices of its own and a Geometry Nodes modifier (node_groups.build_ring_group) that draws the
decoration where the front is (the mask radius). It is made at the start of a sweep (where build() put the mask) in
world space and follows the model when it moves or turns as a whole, like the mask; it does not bend with the dance.
"""

import bpy
from mathutils import Matrix

from . import materials, particles
from .node_groups import RING_GROUP, RING_STYLES, ensure_ring_group, input_identifiers

NAME = "MMD Disperse Ring"
P_RING = "mmd_disperse_ring"  # on the ring object: the mask of its effect
FOLLOW = "MMD Disperse Follow"
LINE_WIDTH = 0.005  # tube radius of the circles and frames, fraction of the model height


def ring_objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_RING) == mask]


def create(mask, layout, root, collection):
    """The ring object of the effect of `mask` (a sweep or the spiral, `layout` from arrival.front_layout)."""
    me = bpy.data.meshes.new(NAME)
    ob = bpy.data.objects.new(NAME, me)
    collection.objects.link(ob)
    if root is not None:  # follow the model's own motion (its loc / rot), like the mask
        con = ob.constraints.new("CHILD_OF")
        con.name = FOLLOW
        con.target = root
        con.use_scale_x = con.use_scale_y = con.use_scale_z = False
        loc, rot, _scale = root.matrix_world.decompose()
        con.inverse_matrix = Matrix.LocRotScale(loc, rot, None).inverted()
    ob[P_RING] = mask
    mod = ob.modifiers.new(NAME, "NODES")
    mod.node_group = ensure_ring_group()
    return ob


def sync(settings, mask, layout, beat):
    """Push the style, sizes and timing to the ring modifiers and the colour to their materials."""
    ring_mat = materials.ensure_ring_material()
    screen_mat = materials.ensure_screen_material()
    water_mat = materials.ensure_water_ring_material() if settings.ring_style == "WATER" else None
    materials.update_ring_materials(settings)
    materials.update_water_ring_material(settings.ring_strength)
    star = particles.ensure_asset("STAR", settings.id_data)
    height = max(settings.size_reference, 1e-3)
    pitch = float(mask.get("mmd_disperse_pitch", settings.spiral_pitch))  # as the spiral was built
    span = layout["span"] + (pitch if mask.get("mmd_disperse_path") == "SPIRAL" else 0.0)
    values = {
        "Mask": mask,
        "Style": RING_STYLES.index(settings.ring_style),
        "Start": tuple(layout["start"]),
        "Axis": tuple(layout["axis"]),
        "U": tuple(layout["u"]),
        "V": tuple(layout["v"]),
        "Half U": layout["half_u"],
        "Half V": layout["half_v"],
        "Span": span,
        "Lead": layout["lead"],
        "Mirror": bool(layout.get("mirror", 0.0)),  # (split from the waist: a second ring going the other way ...
        "Span Back": float(layout.get("span_back", 0.0)),  # ... as far as its own front goes)
        "Size": settings.ring_size,
        "Pitch": pitch,
        "Line Width": LINE_WIDTH * height,
        "Star Size": settings.particle_size,
        "Beat Sync": beat is not None,
        "Beat Object": beat,
        "Ring Material": ring_mat,
        "Screen Material": screen_mat,
        "Star Object": star,
        "Water Material": water_mat,
    }
    for ob in ring_objects(mask):
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group and mod.node_group.name == RING_GROUP:
                ids = input_identifiers(mod.node_group)
                for name, value in values.items():
                    if ids.get(name) is not None and value is not None:
                        mod[ids[name]] = value
        ob.update_tag()


def remove(mask):
    for ob in ring_objects(mask):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    for name in (materials.RING_MATERIAL, materials.SCREEN_MATERIAL, materials.WATER_RING_MATERIAL):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
