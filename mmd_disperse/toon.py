"""Cartoon physics at the big moment (卡通物理): the dancer squashes flat and bounces back up, or presses into a sheet
of paper (or a card) that turns over with the new outfit on its other side (Pika's Squish, Paper Mario); or floats up
off the floor while the transformation runs and lands at the big moment.

Squash and paper happen in both outfits' Geometry Nodes (node_groups._toon) about an anchor of ours: an empty under
the hips, on the floor, that follows the dancer (Copy Location of the centre bone, its height kept). Floating keys
nothing: a driver lifts the old model's armature (its delta location), so both outfits and the rigid bodies hanging
from its bones go up together.
"""

import bpy

from . import materials
from .model import rest_bounds

ANCHOR = "MMD Disperse Toon Anchor"
P_TOON = "mmd_disperse_toon"  # on the anchor: the mask of its effect
P_FLOAT = "mmd_disperse_float"  # on the armature we lift: the mask, and ...
P_FLOAT_Z = "mmd_disperse_float_z"  # ... its delta location's height before
CENTER_BONES = ("センター", "center", "Center", "下半身", "lower body", "Hips", "hips", "pelvis", "J_Bip_C_Hips")
SHAPES = {"NONE": 0, "SQUASH": 1, "PAPER": 2, "CARD": 3}
GAP = 0.004  # how far off the card the paper is, a share of the model height
RISE = 0.5  # seconds the dancer takes to float up ...
FALL = 0.35  # ... and to come down, landing at the big moment
BOB = 0.012  # how far it bobs while it floats, a share of the model height


def anchors(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_TOON) == mask]


def _anchor(mask, model, collection):
    """The empty the squash and the paper turn about: under the hips on the floor, following the centre bone."""
    ob = next(iter(anchors(mask)), None)
    if ob is None:
        ob = bpy.data.objects.new(ANCHOR, None)
        ob.empty_display_type = "PLAIN_AXES"
        ob.hide_render = True
        collection.objects.link(ob)
        ob[P_TOON] = mask
    lo, hi = rest_bounds(model.meshes)
    ob.location = ((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z)
    for con in list(ob.constraints):
        ob.constraints.remove(con)
    arm = model.armature
    bone = next((name for name in CENTER_BONES if arm is not None and name in arm.data.bones), None)
    if bone is not None:
        con = ob.constraints.new("COPY_LOCATION")
        con.target = arm
        con.subtarget = bone
        con.use_z = False  # (on the floor)
    return ob


def _unfloat(mask):
    for ob in [o for o in bpy.data.objects if o.get(P_FLOAT) == mask]:
        ob.driver_remove("delta_location", 2)
        ob.delta_location[2] = float(ob.get(P_FLOAT_Z, 0.0))
        for key in (P_FLOAT, P_FLOAT_Z):
            if key in ob:
                del ob[key]


def float_expression(base, height, start, up, down, land, bob):
    """Driver expression on the frame: from `base` up by `height` from `start` over `up` frames, bobbing by `bob`, down
    again over the `down` frames before `land` (simple math only, so Blender runs it even with Python scripts off)."""
    there = "smoothstep({s}, {u}, frame) * (1 - smoothstep({d}, {l}, frame))".format(
        s=float(start), u=float(start + up), d=float(land - down), l=float(land))
    return "{z:.5f} + ({h:.5f} + {b:.5f} * sin(frame * 0.2)) * {t}".format(z=base, h=height, b=bob, t=there)


def sync(settings, mask, model, start, land):
    """Set up the cartoon physics of the panel for the old (or only) `model`: the anchor (returned, None when there is
    no squash or paper) and the float from frame `start` landing at frame `land`."""
    scene = settings.id_data
    _unfloat(mask)
    anchor = None
    if settings.toon_style != "NONE" and model:
        collection = mask.users_collection[0] if mask.users_collection else scene.collection
        anchor = _anchor(mask, model, collection)
    else:
        for ob in anchors(mask):
            bpy.data.objects.remove(ob)
    if settings.toon_style == "CARD":
        materials.ensure_toon_card_material()
    arm = model.armature if model else None
    if settings.float_up and arm is not None and land is not None and start is not None:
        fps = scene.render.fps / scene.render.fps_base
        lo, hi = rest_bounds(model.meshes)
        tall = hi.z - lo.z
        unit = arm.parent.matrix_world.to_scale().z if arm.parent is not None else 1.0  # (in the parent's space)
        up = max(min(RISE * fps, 0.45 * (land - start)), 1.0)
        down = max(min(FALL * fps, 0.45 * (land - start)), 1.0)
        arm[P_FLOAT] = mask
        arm[P_FLOAT_Z] = arm.delta_location[2]
        driver = arm.driver_add("delta_location", 2).driver
        driver.type = "SCRIPTED"
        driver.expression = float_expression(arm[P_FLOAT_Z], settings.float_height * tall / unit, start, up, down,
                                             land, BOB * tall / unit)
    return anchor


def remove(mask):
    _unfloat(mask)
    for ob in anchors(mask):
        bpy.data.objects.remove(ob)
