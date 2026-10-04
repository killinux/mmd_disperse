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


def _mesh_object(_self, ob):
    return ob.type == "MESH"


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
        description="Model revealed by the transformation (root, armature or mesh). "
                    "Leave empty to make the old outfit vanish")
    follow_base: BoolProperty(
        name="Follow Old Armature", default=True,
        description="Bind the new outfit to the old model's armature so both move together "
                    "(needs the same MMD skeleton)")

    # --- mask / timing (used when building)
    path: EnumProperty(
        name="Wave Path",
        items=(("SPHERE", "Sphere Growth", "A noisy sphere grows from the start point (the tutorial's method)"),
               ("SURFACE", "Along the Body",
                "The wave flows over the body from the start point(s), like a nanotech suit"),
               ("UP", "Sweep Up", "Scan from the feet up to the head"),
               ("DOWN", "Sweep Down", "Scan from the head down to the feet")),
        default="SPHERE")
    seeds: EnumProperty(
        name="Flow From",
        items=(("ORIGIN", "Start Point Only", "Flow from the start point only"),
               ("ORIGIN_LIMBS", "Start + Hands & Feet",
                "Flow from the start point and both wrists and ankles at the same time"),
               ("LIMBS", "Hands & Feet Only", "Flow from both wrists and ankles; the chest and face change last")),
        default="ORIGIN")
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
    inner_glow: BoolProperty(name="Inner Glow", default=False, update=_sync,
                             description="Back faces near the edge glow, so where an outfit is cut open its inside "
                                         "looks lit and solid instead of hollow (uses the glow color)")
    inner_glow_strength: FloatProperty(name="Inner Glow Strength", default=2.0, min=0.0, soft_max=20.0,
                                       update=_sync)
    inner_depth: _distance("Inner Glow Depth", "How far from the edge the inside glows", 2.0)

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

    # --- how the new outfit arrives
    entrance: EnumProperty(
        name="New Outfit Entrance",
        items=(("GROW", "Grow at the Edge", "The new outfit grows where the edge passes (the tutorial's method)"),
               ("ASSEMBLE", "Fly In", "The new outfit arrives in pieces that fly in and click into place"),
               ("CLAMP", "Front and Back Halves",
                "The new outfit forms in two halves in glowing frames in front of and behind the body, which slide in "
                "and clamp shut with a flash; the old outfit goes at that moment (Kamen Rider Build)"),
               ("GHOSTS", "Converging Ghosts",
                "Copies of the new outfit stand around the body and converge into it; where they meet the outfit is "
                "there and the old one goes (Kamen Rider Decade; see-through with the hologram on)")),
        default="GROW", update=_sync)
    clamp_distance: _distance("Slide Distance", "How far in front of and behind the body the halves form", 5.0,
                              soft_max=50.0)
    ghost_count: IntProperty(name="Ghost Count", default=6, min=1, max=32, update=_sync,
                             description="How many copies of the new outfit converge")
    ghost_distance: _distance("Ghost Distance", "How far from the body the copies stand", 5.0, soft_max=50.0)
    piece_size: _distance("Piece Size", "Size of the pieces the outfits break into (fly in / cast off)", 1.2)
    fly_distance: _distance("Fly Distance", "How far away the pieces start", 5.0, soft_max=50.0)
    fly_range: _distance("Fly Range",
                         "How far ahead of the edge a piece takes off: larger means a longer flight", 1.6)
    chunk_force: _distance("Chunk Force", "How hard the old outfit's chunks are thrown off", 3.0, soft_max=50.0)

    # --- dark undersuit under the new outfit's final look
    layer_enable: BoolProperty(name="Dark Undersuit", default=False, update=_sync,
                               description="The new outfit first forms as a dark undersuit at the edge and takes on "
                                           "its own look a little behind it, along a second glowing seam "
                                           "(Mark 50 style)")
    layer_width: _distance("Undersuit Width", "How far the final look trails behind the edge", 2.0)
    layer_color: FloatVectorProperty(name="Undersuit Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                     default=(0.02, 0.022, 0.026), update=_sync)
    layer_lines: FloatProperty(name="Undersuit Lines", default=1.5, min=0.0, soft_max=20.0, update=_sync,
                               description="Glow of the fine web of lines on the undersuit (glow color; 0 = none)")
    layer_style: EnumProperty(
        name="Undersuit Style",
        items=(("NANO", "Nanotech", "Dark metal with a fine web of glowing lines"),
               ("GOO", "Symbiote Goo", "Wet black goo (the symbiote's goo color); the edge bulges out in lumps")),
        default="NANO", update=_sync)

    # --- symbiote (Venom)
    venom_enable: BoolProperty(name="Symbiote", default=False, update=_sync,
                               description="Black goo takes the outfit over (Venom): tendrils crawl ahead of the edge "
                                           "and sticky strands stretch across gaps. They stick to the body while it "
                                           "dances. Pair it with the undersuit's Symbiote Goo style")
    venom_tendrils: IntProperty(name="Tendril Count", default=160, min=0, soft_max=600, update=_sync,
                                description="About how many tendrils grow over the outfit (each may branch)")
    venom_length: _distance("Tendril Length", "How long a tendril grows", 2.0)
    venom_thickness: _distance("Tendril Thickness", "Radius of the tendrils (strands are thinner)", 0.06,
                               soft_max=0.5)
    venom_speed: FloatProperty(name="Tendril Speed", default=3.0, min=0.5, soft_max=5.0, update=_sync,
                               description="How many times faster than the edge the tendrils crawl, so they run "
                                           "ahead of it")
    venom_strands: IntProperty(name="Strand Count", default=60, min=0, soft_max=400, update=_sync,
                               description="About how many sticky strands stretch across gaps (armpits, between the "
                                           "legs, skirt and legs ...); they sag, thin out and snap")
    venom_color: FloatVectorProperty(name="Goo Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                     default=(0.006, 0.006, 0.009), update=_sync,
                                     description="Color of the tendrils, strands and the goo undersuit")

    # --- the old outfit's surface ahead of the edge
    old_surface: EnumProperty(
        name="Surface Ahead",
        items=(("NONE", "None", "The old outfit stays as it is until the edge reaches it"),
               ("VEINS", "Black Veins", "Black veins spread under the old outfit, which turns black just before the "
                                        "edge reaches it (symbiote)"),
               ("FROST", "Frost", "Frost creeps over the old outfit and freezes it to ice; ice crystals grow out of "
                                  "it"),
               ("CHAR", "Char", "The old outfit chars and smoulders, glowing cracks open just before it burns away "
                                "(uses the glow color)")),
        default="NONE", update=_sync)
    surface_width: _distance("Surface Reach", "How far ahead of the edge the old outfit starts to change", 3.0)
    surface_color: FloatVectorProperty(name="Surface Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                       default=(0.006, 0.006, 0.009), update=_sync,
                                       description="Color of the veins, the ice or the char")
    ice_crystals: IntProperty(name="Ice Crystals", default=600, min=0, soft_max=3000, update=_sync,
                              description="With frost: about how many ice crystals grow out of the old outfit before "
                                          "the edge shatters it (0 = none; they use the particle color)")
    crystal_size: _distance("Crystal Size", "How tall the ice crystals grow", 0.6)

    # --- hologram ahead of the edge
    holo_enable: BoolProperty(name="Hologram", default=False, update=_sync,
                              description="The new outfit first shows up as a see-through hologram ahead of the "
                                          "edge, then turns solid")
    holo_width: _distance("Hologram Width", "How far ahead of the edge the hologram reaches", 2.5)
    holo_opacity: FloatProperty(name="Hologram Opacity", default=0.35, min=0.0, max=1.0, subtype="FACTOR",
                                update=_sync)
    holo_strength: FloatProperty(name="Hologram Glow", default=2.0, min=0.0, soft_max=20.0, update=_sync,
                                 description="Brightness of the scan lines, the rim and the scan ring")

    # --- glitch at the edge
    glitch_enable: BoolProperty(name="Glitch", default=False, update=_sync,
                                description="Near the edge, horizontal slices flicker between the old and the "
                                            "new outfit")
    glitch_width: _distance("Glitch Width", "Width of the flickering zone around the edge", 3.0)
    glitch_slice: _distance("Slice Height", "Height of the flickering slices", 0.25, soft_max=2.0)
    glitch_rate: FloatProperty(name="Flicker Rate", default=0.5, min=0.0, soft_max=2.0, update=_sync,
                               description="How often the slices change, per frame")
    glitch_shift: _distance("Slice Shift", "How far a slice jumps sideways", 0.4)
    glitch_flash: BoolProperty(name="Flashes", default=True, update=_sync,
                               description="Some slices flash in the glow color")
    beat_sync: BoolProperty(name="Sync to Beat", default=False, update=_sync,
                            description="The slices reshuffle on every beat of the music and jump, flash and split "
                                        "most on it (Find Beats first)")
    beat_audio: StringProperty(name="Music", subtype="FILE_PATH",
                               description="Music to find the beats in, starting with the scene; leave empty to use "
                                           "the first sound strip of the Video Sequencer")
    beat_sensitivity: FloatProperty(name="Sensitivity", default=0.3, min=0.0, max=1.0, subtype="FACTOR",
                                    description="Higher finds more (weaker) beats")

    # --- old outfit
    base_shrink: _distance("Shrink", "Pull the old outfit inwards where the new one has formed", 0.08,
                           soft_max=1.0, min_value=-10.0)
    base_delete_offset: _distance("Delete Behind", "Delete the old outfit this far behind the boundary", 0.6)
    exit_style: EnumProperty(
        name="Old Outfit Exit",
        items=(("SHRINK", "Shrink Away", "Sink under the new outfit and disappear (the tutorial's method)"),
               ("FRAGMENTS", "Disintegrate", "Break into flakes that blow away"),
               ("CHUNKS", "Cast Off", "Break into armour-like chunks that are thrown off and fall")),
        default="SHRINK", update=_sync)
    frag_size: FloatProperty(name="Flake Size", default=0.85, min=0.05, max=1.0, subtype="FACTOR", update=_sync,
                             description="Size of each flake relative to the face it breaks from")
    frag_subdivide: IntProperty(name="Flake Subdivide", default=0, min=0, max=2, update=_sync,
                                description="Cut big faces into smaller flakes (slower)")
    frag_life: FloatProperty(name="Flight Time", default=0.2, min=0.01, max=1.0, subtype="FACTOR", update=_sync,
                             description="How long a flake stays in the air, as a share of the transformation")
    frag_burst: _distance("Burst", "How far the flakes pop out from the surface", 0.25, min_value=-10.0)
    frag_wind_dir: FloatVectorProperty(name="Wind Direction", subtype="XYZ", size=3, default=(0.0, 0.4, 1.0),
                                       update=_sync,
                                       description="World direction the flakes drift in (MMD models face -Y)")
    frag_wind: _distance("Wind", "How far the wind carries the flakes", 6.0, soft_max=50.0)
    frag_turbulence: _distance("Turbulence", "How much the flakes swirl around", 1.0)
    frag_spin: FloatProperty(name="Spin", default=4.0, min=0.0, soft_max=20.0, subtype="ANGLE", update=_sync,
                             description="How far the flakes tumble during their flight")
    frag_glow: BoolProperty(name="Glowing Flakes", default=True, update=_sync,
                            description="Flakes light up in the glow color as they break off")
    frag_glow_strength: FloatProperty(name="Flake Glow Strength", default=3.0, min=0.0, soft_max=50.0,
                                      update=_sync)

    leave_behind: BoolProperty(name="Leave Behind", default=False, update=_sync,
                               description="Flakes, chunks and particles fly on from where they broke off, the new "
                                           "outfit's pieces fly in from fixed points and the finale stars stay where "
                                           "they burst out, instead of moving with the body (dancing, or the whole "
                                           "model moving or turning). Building plays the animation once to record "
                                           "it: rebuild after changing the motion or the timing")

    silhouette: BoolProperty(name="Glowing Silhouette", default=False, update=_sync,
                             description="The old outfit lights up just before the edge reaches it, so the body "
                                         "turns into light before it changes (uses the flake glow strength)")
    silhouette_width: _distance("Silhouette Width", "How far ahead of the edge the old outfit starts to glow", 3.0)

    # --- light ribbons around the limbs
    ribbon_enable: BoolProperty(name="Light Ribbons", default=False, update=_sync,
                                description="Glowing ribbons spiral around the arms and legs as they transform "
                                            "(needs an MMD skeleton; uses the glow color)")
    ribbon_turns: FloatProperty(name="Ribbon Turns", default=2.5, min=0.5, soft_max=8.0, update=_sync,
                                description="Turns of the helix around each arm or leg segment")
    ribbon_width: _distance("Ribbon Width", "Width of the ribbons", 0.12, soft_max=1.0)
    ribbon_linger: _distance("Ribbon Linger", "How far the wave moves on before a ribbon fades", 2.5)
    ribbon_strength: FloatProperty(name="Ribbon Glow", default=2.5, min=0.0, soft_max=50.0, update=_sync)

    # --- finale: flash and sparkle burst once the new outfit is complete
    finale: BoolProperty(name="Finale Flash", default=False, update=_sync,
                         description="When the new outfit is complete it flashes with light and stars burst out "
                                     "of it (uses the glow color; the stars use the particle color)")
    finale_style: EnumProperty(
        name="Flash Style",
        items=(("PULSE", "Whole Outfit Flash", "All of the new outfit lights up at once and fades"),
               ("SWEEP", "Light Sweep", "A band of light runs from the start point over the new outfit, along "
                                        "the transformation's path; stars burst out where it passes")),
        default="PULSE", update=_sync)
    finale_length: FloatProperty(name="Flash Time", default=0.15, min=0.02, max=1.0, subtype="FACTOR",
                                 update=_sync,
                                 description="How long the flash and the sparkles last, as a share of the "
                                             "transformation")
    finale_glow: FloatProperty(name="Flash Glow", default=2.0, min=0.0, soft_max=20.0, update=_sync,
                               description="Brightness of the flash")
    finale_width: _distance("Sweep Width", "Half width of the band of light", 0.8, soft_max=5.0)
    finale_white: FloatProperty(name="White Flash", default=0.8, min=0.0, max=1.0, subtype="FACTOR", update=_sync,
                                description="How far the whole picture flashes to white as the finale starts "
                                            "(needs the compositor node: Add White Flash)")
    finale_sparkles: IntProperty(name="Sparkle Count", default=300, min=0, soft_max=3000, update=_sync,
                                 description="About how many stars burst out of the new outfit (0 = none)")
    finale_distance: _distance("Sparkle Distance", "How far the stars fly out", 3.5, soft_max=20.0)

    # --- particles released by the old outfit
    particles: EnumProperty(
        name="Particles",
        items=(("NONE", "None", "No particles"),
               ("PETAL", "Petals", "Cherry-blossom petals"),
               ("BUTTERFLY", "Butterflies", "Butterflies flapping their wings"),
               ("STAR", "Sparkles", "Four-pointed glowing stars"),
               ("CUBE", "Cubes", "Glowing cubes (Tron's derez)"),
               ("COIN", "Coins", "Spinning metal coins (Ready Player One; gold with a gold particle color)"),
               ("SHARD", "Ice Shards", "Splinters of ice"),
               ("EMBER", "Embers", "Small glowing embers (let the wind blow up to make them rise)"),
               ("OBJECT", "Custom Object", "Copies of any mesh object")),
        default="NONE", update=_sync)
    particle_object: PointerProperty(name="Particle Object", type=bpy.types.Object, poll=_mesh_object,
                                     update=_sync, description="Mesh used for every particle")
    particle_count: IntProperty(name="Count", default=600, min=0, soft_max=5000, update=_sync,
                                description="About how many particles the whole old outfit releases")
    particle_size: _distance("Particle Size", "Size of the particles", 0.35)
    particle_life: FloatProperty(name="Particle Flight Time", default=0.35, min=0.01, max=1.0, subtype="FACTOR",
                                 update=_sync,
                                 description="How long a particle stays in the air, as a share of the transformation")
    particle_color: FloatVectorProperty(name="Particle Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                        default=(1.0, 0.62, 0.78), update=_sync)
    particle_glow: FloatProperty(name="Particle Glow", default=1.0, min=0.0, soft_max=20.0, update=_sync)
    flap_speed: FloatProperty(name="Flap Speed", default=1.5, min=0.0, soft_max=6.0, update=_sync,
                              description="Wing poses per frame")

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
