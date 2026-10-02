import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import effect
from .model import DEFAULT_LOCK_PATTERNS


def _sync(self, _context):
    effect.sync(self)


def _not_effect_object(_self, ob):
    return ob.type in {"EMPTY", "ARMATURE", "MESH"} and not ob.name.startswith(effect.MASK_NAME)


def _distance(name, description, default, soft_max=10.0, min_value=0.0):
    return FloatProperty(name=name, description=description, default=default, min=min_value,
                         soft_max=soft_max, subtype="DISTANCE", precision=3, update=_sync)


class MMDDisperseSettings(bpy.types.PropertyGroup):
    # --- models
    base: PointerProperty(
        name="Old Outfit", type=bpy.types.Object, poll=_not_effect_object,
        description="Model shown before the transformation (root, armature or mesh). Optional")
    target: PointerProperty(
        name="New Outfit", type=bpy.types.Object, poll=_not_effect_object,
        description="Model revealed by the transformation (root, armature or mesh)")
    follow_base: BoolProperty(
        name="Follow Old Armature", default=True,
        description="Bind the new outfit to the old model's armature so both move together "
                    "(needs the same MMD skeleton)")

    # --- mask / timing (used when building)
    origin_mode: EnumProperty(
        name="Start From",
        items=(("BONE", "Bone", "Start at a bone of the old model (upper body by default)"),
               ("CURSOR", "3D Cursor", "Start at the 3D cursor"),
               ("CENTER", "Model Center", "Start at the center of the model")),
        default="BONE")
    origin_bone: StringProperty(name="Bone", description="Leave empty to pick the upper body automatically")
    space: EnumProperty(
        name="Space",
        items=(("REST", "Rest Pose", "Measure on the undeformed body: the wave sticks to the skin while dancing"),
               ("POSED", "Posed", "Measure on the animated body; the sphere follows the start bone")),
        default="REST")
    frame_start: IntProperty(name="Start", default=1)
    frame_end: IntProperty(name="End", default=100)
    direction: EnumProperty(
        name="Direction",
        items=(("GROW", "Suit Up", "Old outfit turns into the new one"),
               ("SHRINK", "Suit Down", "New outfit retracts back to the old one")),
        default="GROW")
    easing: EnumProperty(
        name="Easing",
        items=(("EASE", "Ease In/Out", ""), ("LINEAR", "Linear", "")),
        default="EASE")

    # --- sizes
    auto_size: BoolProperty(
        name="Auto Size", default=True,
        description="Scale all sizes to the model height when a new model is built")
    size_reference: FloatProperty(name="Size Reference", default=0.0, options={"HIDDEN"})

    # --- edge (tutorial: "Displacing Edge")
    noise_scale: FloatProperty(name="Noise Scale", default=0.3, min=0.0, soft_max=10.0, precision=3,
                               update=_sync, description="Frequency of the noise that breaks up the boundary")
    noise_detail: FloatProperty(name="Noise Detail", default=2.0, min=0.0, max=15.0, update=_sync)
    noise_amount: _distance("Noise Amount", "How far the noise pushes the boundary in and out", 1.0)
    edge_width: _distance("Edge Width", "Width of the gradient behind the boundary", 1.0)
    edge_push: _distance("Edge Push", "How far the new outfit's edge bulges out along the normals", 0.2,
                         min_value=-100.0)
    edge_glow: BoolProperty(name="Edge Glow", default=True, update=_sync,
                            description="Add a glowing rim to the new outfit's materials at the boundary")
    edge_glow_strength: FloatProperty(name="Edge Glow Strength", default=4.0, min=0.0, soft_max=50.0,
                                      update=_sync)
    subdivide: IntProperty(name="Subdivide", default=0, min=0, max=3, update=_sync,
                           description="Subdivide low-poly outfits for a smoother edge (slow)")

    # --- wire layer
    wire_enable: BoolProperty(name="Wire Layer", default=True, update=_sync)
    wire_hex: BoolProperty(name="Hexagons", default=True, update=_sync,
                           description="Triangulate + Dual Mesh to turn the wires into hexagons")
    wire_inner: _distance("Behind Edge", "How far the wires reach back over the new outfit", 0.6)
    wire_outer: _distance("Ahead of Edge", "How far the wires crawl ahead over the old outfit", 0.3)
    wire_radius: _distance("Wire Radius", "Thickness of the wire tubes", 0.017, soft_max=0.5)
    wire_lift: _distance("Wire Lift", "Offset of the wires above the surface", 0.03, soft_max=1.0,
                         min_value=-10.0)
    wire_resolution: IntProperty(name="Wire Sides", default=4, min=3, max=16, update=_sync)
    wire_color: FloatVectorProperty(name="Wire Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                    default=(0.03, 0.03, 0.035), update=_sync)
    glow_color: FloatVectorProperty(name="Glow Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                    default=(0.1, 0.75, 1.0), update=_sync)
    glow_strength: FloatProperty(name="Glow Strength", default=4.0, min=0.0, soft_max=50.0, update=_sync)

    # --- old outfit
    base_shrink: _distance("Shrink", "Pull the old outfit inwards where the new one has formed", 0.08,
                           soft_max=1.0, min_value=-10.0)
    base_delete_offset: _distance("Delete Behind", "Delete the old outfit this far behind the boundary", 0.6)

    # --- shared parts
    use_lock: BoolProperty(
        name="Keep Shared Parts", default=False,
        description="Parts whose material matches the patterns always come from the old model "
                    "(e.g. face and hair that both models share)")
    lock_patterns: StringProperty(
        name="Materials", default=DEFAULT_LOCK_PATTERNS,
        description="Material name patterns separated by ';' (wildcards allowed, case-insensitive)")

    mask: PointerProperty(name="Mask", type=bpy.types.Object,
                          description="Sphere empty of the current effect; its scale is the reveal radius")


def register():
    bpy.utils.register_class(MMDDisperseSettings)
    bpy.types.Scene.mmd_disperse = PointerProperty(type=MMDDisperseSettings)


def unregister():
    del bpy.types.Scene.mmd_disperse
    bpy.utils.unregister_class(MMDDisperseSettings)
