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
               ("DOWN", "Sweep Down", "Scan from the head down to the feet"),
               ("LEFT_RIGHT", "Sweep Left to Right",
                "A flat front crosses the body from the left of the picture to the right, seen from the front (like a "
                "magic circle passing through it)"),
               ("RIGHT_LEFT", "Sweep Right to Left", "A flat front crosses the body from the right of the picture "
                                                     "to the left, seen from the front"),
               ("FRONT_BACK", "Sweep Front to Back", "A flat front passes through the body from the front to the back "
                                                     "(like walking through a barrier)"),
               ("BACK_FRONT", "Sweep Back to Front", "A flat front passes through the body from the back to the "
                                                     "front"),
               ("SPIRAL", "Spiral Up", "The change winds up around the body from the feet, a turn per Spiral Pitch, "
                                       "as if something circling it changes what it passes over (Cinderella)"),
               ("MIDDLE", "Split from the Waist", "Two flat fronts set off from the waist, one up the body and one "
                                                  "down (Danny Phantom's two rings)"),
               ("GARMENTS", "Garment by Garment",
                "One garment of the new outfit after the other (each of its materials), each swept over in its own "
                "turn, like an idol anime's card-by-card outfit change; the old outfit goes where the garment over it "
                "comes"),
               ("HAND", "Where the Hands Sweep",
                "The outfit changes where the dancing hands sweep over the body, then from there over the rest of it "
                "(the hand-swipe outfit change of short videos). Building plays the dance to find where they go; the "
                "front keeps their pace (linear), so the end frame follows")),
        default="SPHERE")
    spiral_pitch: _distance("Spiral Pitch", "How far up the body the change climbs per turn around it", 2.0)
    garment_order: EnumProperty(
        name="Garment Order",
        items=(("DOWN", "From the Top", "From the garments at the top of the body down to the shoes"),
               ("UP", "From the Feet", "From the shoes up to the garments at the top"),
               ("RANDOM", "Random", "In a random order (the same every build)")),
        default="DOWN")
    hand_side: EnumProperty(
        name="Hands",
        items=(("BOTH", "Both Hands", "Wherever either hand sweeps"),
               ("LEFT", "Left Hand", "Only the model's left hand"),
               ("RIGHT", "Right Hand", "Only the model's right hand")),
        default="BOTH")
    hand_reach: _distance("Hand Reach", "How close a hand has to come to change a spot", 1.4)
    trigger: EnumProperty(
        name="Start On",
        items=(("NONE", "Start Frame", "Start at the start frame"),
               ("CLAP", "Clap", "Start on the first clap of the dance from the start frame on, from both hands "
                                "(#拍手变装)"),
               ("KISS", "Blown Kiss", "Start when a hand blows a kiss (from the lips, then away), from that hand"),
               ("SALUTE", "Salute", "Start when a hand is held to the brow, from that hand"),
               ("FLIP", "Hair Flip", "Start on a quick toss of the head, from the head"),
               ("TURN", "Turn Away", "Swap as the dancer's back is turned to the camera (Wonder Woman's spin): the "
                                     "moment the outfits swap all at once, or the middle of the wave, comes then"),
               ("SQUAT", "Squat", "Swap at the bottom of the first squat (the Buss It change: down in the old outfit, "
                                  "up in the new one)"),
               ("JUMP", "Jump", "Swap at the top of the first jump, both feet off the floor"),
               ("LAND", "Landing", "Swap as the feet land after a jump or a high kick (pair it with the shockwave)"),
               ("STEP", "Footfall", "Start from the foot that first comes down (with Flowers Underfoot every step "
                                    "blooms)"),
               ("RAISE", "Hand to the Sky", "Start from a hand thrown up over the head (I have the power!)"),
               ("HEART", "Finger Heart", "Start when the thumb and forefinger make a heart (one hand, or both "
                                         "together)"),
               ("WINK", "Wink", "Start from the eye that winks (read off the facial expressions of the dance)"),
               ("PULL", "Pull the Cord", "Start when a hand pulls at the chest or the neck and snaps away (Chainsaw "
                                         "Man)")),
        default="NONE",
        description="Start the transformation on a move of the dance: building looks for it in the old model's motion "
                    "from the start frame on and moves the transformation there (the start and end frames follow; with "
                    "beat sync onto the nearest beat)")
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

    # --- the front's decoration (sweeps and the spiral)
    ring_enable: BoolProperty(name="Front Ring", default=False, update=_sync,
                              description="Something you can see moves with the front of a sweep or the spiral: a "
                                          "magic circle, a ring of sparks, a glowing panel, a sheet of TV static, or a "
                                          "comet of sparkles circling the body (uses the glow color)")
    ring_style: EnumProperty(
        name="Ring Style",
        items=(("MAGIC", "Magic Circle", "A glowing magic circle with runes, turning as it passes through the body "
                                         "(Kamen Rider Wizard)"),
               ("SPARKS", "Spark Ring", "A fiery ring throwing off sparks as it spins (Doctor Strange's portal)"),
               ("PANEL", "Glowing Panel", "A glowing frame around a see-through screen with a grid (Kamen Rider "
                                          "Ex-Aid)"),
               ("STATIC", "TV Static", "A sheet of TV static the body passes through (WandaVision)"),
               ("COMET", "Sparkle Comet", "A comet of sparkles circling the body at the front, a turn per Spiral "
                                          "Pitch (with Spiral Up or the up / down sweeps: Cinderella)"),
               ("HALO", "Ring of Light", "A plain ring of light (with Split from the Waist: Danny Phantom's two "
                                         "rings)"),
               ("WATER", "Toon Water", "A band of cartoon water winds round the body at the front, flowing lines and "
                                       "white foam like an ukiyo-e print, a turn per Spiral Pitch (Demon Slayer's "
                                       "Water Breathing; with Spiral Up or the up / down sweeps)")),
        default="MAGIC", update=_sync)
    ring_size: FloatProperty(name="Ring Size", default=1.0, min=0.1, soft_max=3.0, update=_sync,
                             description="Size of the ring (1 fits around the body); the comet's distance from it")
    ring_strength: FloatProperty(name="Ring Glow", default=6.0, min=0.0, soft_max=50.0, update=_sync)

    # --- toon flames
    flame_enable: BoolProperty(name="Toon Flames", default=False, update=_sync,
                               description="Cartoon flames, no simulation: a shell of flame over the body and tongues "
                                           "of flame licking up from it (Persona 5's blue flames, Kamen Rider Hibiki, "
                                           "a Super Saiyan's aura)")
    flame_mode: EnumProperty(
        name="Flames",
        items=(("EDGE", "Along the Edge", "A band of fire runs over the body with the edge"),
               ("AURA", "Whole Body", "The whole body is wreathed in flames, strongest at the big moment (the swap, or "
                                      "the new outfit complete), then they die down")),
        default="EDGE", update=_sync)
    flame_color: FloatVectorProperty(name="Flame Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                     default=(1.0, 0.35, 0.05), update=_sync,
                                     description="Colour of the flames (deeper at the edges, a white-hot core)")
    flame_strength: FloatProperty(name="Flame Glow", default=4.0, min=0.0, soft_max=50.0, update=_sync)
    flame_height: _distance("Flame Height", "How tall the tongues of flame are", 2.5)
    flame_width: _distance("Flame Width", "How far to either side of the edge the band of fire burns", 2.0)
    flame_count: IntProperty(name="Tongues", default=500, min=0, soft_max=3000, update=_sync,
                             description="About how many tongues of flame when the whole outfit burns")

    # --- impact frames
    impact_enable: BoolProperty(name="Impact Frames", default=False, update=_sync,
                                description="Anime impact frames at the big moment (or as a move of the dance starts "
                                            "it): a few frames drained of colour, every other one inverted (needs the "
                                            "compositor nodes: Add Impact Frames)")
    impact_frames: IntProperty(name="Frames", default=3, min=1, max=12, update=_sync,
                               description="How many impact frames")
    speed_lines: BoolProperty(name="Speed Lines", default=True, update=_sync,
                              description="Lines rush in from the edges of the picture towards the character during "
                                          "the impact frames (a sheet in front of the scene camera)")
    shockwave: BoolProperty(name="Shockwave", default=True, update=_sync,
                            description="A ring of light spreads over the floor from the feet with puffs of dust (uses "
                                        "the glow color)")
    shock_size: _distance("Shockwave Size", "How far the shockwave spreads", 12.0, soft_max=100.0)

    # --- soul rings
    soul_enable: BoolProperty(name="Soul Rings", default=False, update=_sync,
                              description="Rings of light rise from the floor one after another and float round the "
                                          "body, coloured by their age as in Soul Land (斗罗大陆): yellow, purple, "
                                          "black, red")
    soul_count: IntProperty(name="Ring Count", default=7, min=1, max=9, update=_sync, description="How many soul rings")
    soul_strength: FloatProperty(name="Ring Brightness", default=5.0, min=0.0, soft_max=50.0, update=_sync)

    # --- 1.11: the world change
    domain_enable: BoolProperty(name="World Change", default=False, update=_sync,
                                description="Another world opens out from the dancer (Jujutsu Kaisen's domain "
                                            "expansion): first a round window onto it behind the body, then, once it "
                                            "has swallowed the camera, the whole picture; it stays a while after the "
                                            "big moment and then shatters or closes back")
    domain_style: EnumProperty(
        name="World",
        items=(("VOID", "Starry Void", "Deep space full of stars and nebulae over a dark mirror floor (Infinite Void); "
                                       "crystals of light float in it"),
               ("CRIMSON", "Crimson Wasteland", "A red sky with a dark sun and black clouds over cracked, glowing "
                                                "ground, swords rising out of it (Honkai: Star Rail's Phainon, "
                                                "Malevolent Shrine)"),
               ("FLOWERS", "Flower Field", "A pastel sky over a meadow full of flowers that open as it spreads"),
               ("WATER", "Sky Mirror", "A blue sky with white clouds over still water that ripples, white feathers "
                                       "falling (Precure, Wuthering Waves)"),
               ("STAGE", "Concert", "A dark concert hall: beams of light sweep from the stage, a crowd of light "
                                    "sticks waves all round, a pool of light where the dancer stands")),
        default="VOID", update=_sync)
    domain_open: FloatProperty(name="Opens Over", default=0.35, min=0.02, max=1.0, subtype="FACTOR", update=_sync,
                               description="How long the world takes to open round the dancer, as a share of the time "
                                           "to the big moment (the swap, or the new outfit complete)")
    domain_hold: FloatProperty(name="Stays For", default=0.35, min=0.0, max=3.0, subtype="FACTOR", update=_sync,
                               description="How long the world stays after the big moment, as a share of the "
                                           "transformation")
    domain_close: EnumProperty(
        name="Then",
        items=(("SHATTER", "Shatter", "The world breaks into pieces that fly off, its floor drawing in"),
               ("SHRINK", "Close Back", "The world closes back into the dancer the way it opened")),
        default="SHATTER", update=_sync)
    domain_props: IntProperty(name="Props", default=60, min=0, soft_max=400, update=_sync,
                              description="How many crystals, swords, flowers or feathers (the concert has its ten "
                                          "beams of light)")

    # --- 1.11: the camera and time at the big moment
    shot_enable: BoolProperty(name="Camera Move", default=False, update=_sync,
                              description="The camera moves at the big moment (the swap, or the new outfit complete): "
                                          "a camera of the add-on rides on the scene camera or circles the dancer and "
                                          "timeline markers switch to it just for the move; the scene camera's own "
                                          "animation is not touched")
    shot_style: EnumProperty(
        name="Move",
        items=(("WHIP", "Whip Pan", "The camera swings away fast, the picture smears and swings back in: the outfits "
                                    "swap in the blur (the whip pan of outfit change videos)"),
               ("ROLL", "Roll", "The picture spins away round its middle and back in, the outfits swapping in the "
                                "spin"),
               ("PUNCH", "Zoom Punch", "A sudden zoom in on the dancer at the moment, smeared outwards, then back"),
               ("DOLLY", "Dolly Zoom", "The camera backs away while it zooms in, so the dancer stays the same size and "
                                       "the world behind stretches away, then comes back (Vertigo)"),
               ("ORBIT", "Orbit", "The camera circles the dancer round the moment and comes back where it was (with "
                                  "Freeze: bullet time)"),
               ("CUTS", "Ultimate Cuts", "Quick cuts round the moment, like a game's ultimate: a low angle pushing in, "
                                         "the eyes close up (riding on the head), then a wide shot from above as the "
                                         "outfits swap, and back to the scene camera")),
        default="WHIP", update=_sync)
    shot_length: FloatProperty(name="Move Time", default=2.0, min=0.2, soft_max=10.0, update=_sync,
                               description="How long the dolly zoom, the orbit and the cuts take, in seconds")
    shot_angle: FloatProperty(name="Orbit Angle", default=360.0, min=-1080.0, max=1080.0, update=_sync,
                              description="How far the camera goes round the dancer, in degrees (a whole turn comes "
                                          "back to where it started)")
    time_warp: EnumProperty(
        name="Time",
        items=(("NONE", "As It Is", "The dance goes on as it is"),
               ("FREEZE", "Freeze", "The dance stands still round the moment (hair and skirts hang in the air) while "
                                    "the transformation goes on, then catches up with the music (bullet time)"),
               ("SLOW", "Slow Motion", "The dance slows to a quarter round the moment, then speeds up to catch up with "
                                       "the music (the velocity edit of short videos)"),
               ("TWOS", "On Twos", "Round the moment every pose is held for two frames, like stop motion")),
        default="NONE", update=_sync,
        description="Freeze or slow the dance round the big moment: its motion is put into an NLA strip whose time is "
                    "keyed (removing the effect puts it back); the rigid bodies are slowed with it")
    warp_length: FloatProperty(name="Time Span", default=1.2, min=0.1, soft_max=6.0, update=_sync,
                               description="How long the dance stands still, slows or goes on twos, in seconds")

    # --- 1.11: cartoon physics
    toon_style: EnumProperty(
        name="Cartoon Physics",
        items=(("NONE", "None", "The body keeps its shape"),
               ("SQUASH", "Squash and Bounce", "At the big moment the body squashes flat as if pressed from above, the "
                                               "outfits swap when it is flattest, and it bounces back up, wobbling "
                                               "(Pika's Squish; pair it with All at Once)"),
               ("PAPER", "Paper Flip", "The body presses into a sheet of paper facing the camera that turns over, the "
                                       "old outfit on one side and the new one on the other, and puffs back out "
                                       "(Paper Mario; pair it with All at Once)"),
               ("CARD", "Card Flip", "The same on a magic card, which turns over with the dancer (a tarot or trading "
                                     "card; pair it with All at Once)")),
        default="NONE", update=_sync)
    float_up: BoolProperty(name="Float Up", default=False, update=_sync,
                           description="The dancer floats up off the floor while the transformation runs, bobbing, "
                                       "and lands at the big moment (a magical girl's transformation; a driver lifts "
                                       "the old model's armature, removed with the effect)")
    float_height: FloatProperty(name="Float Height", default=0.12, min=0.0, soft_max=1.0, subtype="FACTOR",
                                update=_sync, description="How high the dancer floats, a share of the model height")

    # --- 1.11: the picture's look round the big moment
    look_style: EnumProperty(
        name="Picture Look",
        items=(("NONE", "None", "The picture stays as it is"),
               ("SILHOUETTE", "Silhouette", "The dancer turns into a black silhouette with a bright rim against a flat "
                                            "colour, and the outfits swap inside it (as in magical girl anime)"),
               ("ACCENT", "Only the Dancer in Colour", "The picture drains to black and white, all but the dancer "
                                                       "(a colour splash on the drop; Honkai: Star Rail's Acheron)"),
               ("SONG", "Old Painting", "The picture turns into an old Chinese painting: the dancer painted in ink on "
                                        "blank yellowed silk, ink lines round her, a mounting and a red seal (pair "
                                        "it with On Twos)")),
        default="NONE", update=_sync,
        description="A look the picture takes round the big moment, made in the compositor (each turns on Cryptomatte "
                    "for the view layer to find the dancer); removing the effect takes it out")
    look_length: FloatProperty(name="Look Time", default=1.0, min=0.1, soft_max=6.0, update=_sync,
                               description="How long the look lasts, in seconds (a little of it before the moment)")
    look_color: FloatVectorProperty(name="Backdrop", subtype="COLOR", size=3, min=0.0, max=1.0,
                                    default=(1.0, 0.08, 0.03), update=_sync,
                                    description="The flat colour behind the silhouette")

    # --- 1.11: the dance drawn in the air
    trail_enable: BoolProperty(name="Dance Ribbons", default=False, update=_sync,
                               description="Ribbons trail from the dancing hands while the transformation runs. Building "
                                           "plays the dance and records where the hands go, so the ribbons follow every "
                                           "move (build again after moving the model). With the path Where the Hands "
                                           "Sweep, silk changes the outfit wherever it sweeps")
    trail_style: EnumProperty(
        name="Ribbons",
        items=(("LIGHT", "Trails of Light", "Thin lines of light in the glow color, like light sticks in a long "
                                            "exposure"),
               ("SLEEVE", "Water Sleeves", "Long white silk sleeves of Chinese opera (水袖) that hang, sway and "
                                           "flutter"),
               ("SASH", "Red Silk Sash", "Red silk with gold hems, like Ne Zha's sash (混天绫)"),
               ("PETALS", "Petals", "Petals strewn along the way the hands go, drifting down")),
        default="LIGHT", update=_sync)
    trail_feet: BoolProperty(name="Feet Too", default=False, update=_sync,
                             description="Ribbons trail from the feet as well")
    trail_length: FloatProperty(name="Ribbon Length", default=0.6, min=0.05, soft_max=3.0, update=_sync,
                                description="How much of the way the hands went the ribbons show, in seconds")
    trail_width: _distance("Trail Width", "How wide the silk is at the hand, from its middle to a hem (a trail of "
                                           "light is far thinner)", 1.0)
    trail_strength: FloatProperty(name="Ribbon Brightness", default=4.0, min=0.0, soft_max=30.0, update=_sync,
                                  description="How brightly the trails of light shine (the silk glows a little with "
                                              "it)")
    step_flowers: BoolProperty(name="Flowers Underfoot", default=False, update=_sync,
                               description="Wherever a foot comes down while the transformation runs, a lotus opens on "
                                           "the floor and a ripple spreads (步步生莲)")
    step_style: EnumProperty(
        name="Underfoot",
        items=(("LOTUS", "Lotus", "A lotus opens at every step and closes again after a while"),
               ("SEAL", "Seal of Light", "A star in two rings of light lights up at every step")),
        default="LOTUS", update=_sync)

    # --- lightning
    arc_enable: BoolProperty(name="Lightning Arcs", default=False, update=_sync,
                             description="Jagged arcs of electricity crackle along the edge, new ones every frame "
                                         "(Thor, Shazam; uses the glow color)")
    arc_count: IntProperty(name="Arc Count", default=40, min=0, soft_max=300, update=_sync,
                           description="About how many arcs crackle at a time where the edge crosses the body")
    arc_length: _distance("Arc Length", "How long an arc is", 1.0)
    arc_reach: _distance("Arc Reach", "How far to either side of the edge the arcs crackle", 0.6)
    arc_thickness: _distance("Arc Thickness", "Radius of the arcs", 0.015, soft_max=0.2)
    arc_strength: FloatProperty(name="Arc Glow", default=12.0, min=0.0, soft_max=100.0, update=_sync)
    arc_strike: BoolProperty(name="Lightning Bolt", default=True, update=_sync,
                             description="A bolt of lightning comes down on the start point as the transformation "
                                         "begins; with the compositor's white flash the picture flashes white then "
                                         "(as bright as the finale's White Flash)")

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
                "there and the old one goes (Kamen Rider Decade; see-through with the hologram on)"),
               ("SCALES", "Flipping Scales",
                "Both outfits break into scales that turn over in a wave where the edge passes, the old outfit on one "
                "side of every scale and the new one on the other (Mystique); the old outfit leaves this way too"),
               ("EVOLVE", "Evolution Flash",
                "No edge: the body glows up and the two outfits show in turn, faster and faster and brighter and "
                "brighter until they are pure light, then the new one stays (Pokemon's evolution; uses the glow color "
                "and the edge glow strength)"),
               ("POOF", "Smoke Puff", "No edge: a puff of white smoke bursts out of the body and hides it while the "
                                      "outfits swap, then drifts up and thins out (a ninja's transformation)"),
               ("SHADOW", "Rise from the Shadow",
                "No edge: the body sinks into its own black shadow on the floor, head first, and the new outfit stands "
                "up out of it, feet first"),
               ("BEAM", "Transporter Beam",
                "No edge: a column of light comes down round the body with sparkles drifting up and down in it; the "
                "old outfit shimmers away and the new one shimmers in (Star Trek; uses the glow color, the sparkles "
                "the particle color)"),
               ("SWAP", "All at Once", "No edge: the outfits swap all at once at the moment (pair it with a flash, "
                                       "flames, impact frames or Start On: Turn Away)"),
               ("LOTUS", "Lotus Bud",
                "No edge: big petals grow up from the floor and close into a bud round the body, the outfits swap "
                "inside it with a flash, then it opens out and sinks away (Ne Zha 2's lotus; the petals use the "
                "particle color, their rim the glow color)")),
        default="GROW", update=_sync)
    lotus_petals: IntProperty(name="Petal Count", default=8, min=3, max=32, update=_sync,
                              description="How many petals in each of the lotus's two rings")
    beam_sparkles: IntProperty(name="Beam Sparkles", default=250, min=0, soft_max=2000, update=_sync,
                               description="How many sparkles drift up and down in the column of light")
    beam_strength: FloatProperty(name="Beam Glow", default=2.0, min=0.0, soft_max=20.0, update=_sync,
                                 description="Brightness of the column of light")
    smoke_count: IntProperty(name="Smoke Puffs", default=120, min=1, soft_max=2000, update=_sync,
                             description="About how many balls of smoke the puff is made of")
    smoke_size: _distance("Smoke Size", "How big the balls of smoke are", 1.8)
    shadow_dir: FloatVectorProperty(name="Light Direction", subtype="XYZ", size=3, default=(0.35, 0.55, -1.0),
                                    update=_sync,
                                    description="World direction the light falls in, which casts the shadow the body "
                                                "sinks into (it must point down)")
    reactor: BoolProperty(name="Reactor Start", default=False, update=_sync,
                          description="The suit around the start point(s) is there first, glowing and pulsing like an "
                                      "arc reactor, and the rest flows out of it (Mark 50; uses the glow color)")
    reactor_size: _distance("Reactor Size", "How big the glowing patch at each start point is", 0.6)
    plates: BoolProperty(name="Armor Plates", default=False, update=_sync,
                         description="Behind the edge the new outfit's plates rise off the body one by one and settle "
                                     "back into place (Mark 50)")
    plate_size: _distance("Plate Size", "How big the plates are", 0.7)
    plate_lift: _distance("Plate Lift", "How far a plate rises", 0.25, min_value=-10.0)
    plate_width: _distance("Plate Width", "How far the edge moves on while a plate rises and settles", 1.6)
    scale_size: _distance("Scale Size", "How big the scales are", 0.5)
    flip_width: _distance("Flip Width", "How far the edge moves while one scale turns over: wider means slower, "
                                        "with more scales turning at once", 1.5)
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
    venom_webs: BoolProperty(name="Webbing", default=True, update=_sync,
                             description="A web of goo fills the fork where a tendril branches")
    venom_color: FloatVectorProperty(name="Goo Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                     default=(0.006, 0.006, 0.009), update=_sync,
                                     description="Color of the tendrils, strands and the goo undersuit")
    venom_metallic: FloatProperty(name="Goo Metallic", default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=_sync,
                                  description="Turns the goo (tendrils, strands, goo undersuit, black veins) into "
                                              "liquid metal: 1 with a silver color is the T-1000")

    # --- the old outfit's surface ahead of the edge
    old_surface: EnumProperty(
        name="Surface Ahead",
        items=(("NONE", "None", "The old outfit stays as it is until the edge reaches it"),
               ("VEINS", "Black Veins", "Black veins spread under the old outfit, which turns black just before the "
                                        "edge reaches it (symbiote)"),
               ("FROST", "Frost", "Frost creeps over the old outfit and freezes it to ice; ice crystals grow out of "
                                  "it"),
               ("CHAR", "Char", "The old outfit chars and smoulders, glowing cracks open just before it burns away "
                                "(uses the glow color)"),
               ("INK", "Ink Wash", "Ink spreads over the old outfit in patches and turns it into an ink wash painting "
                                   "of itself, soaking it dark right at the edge (uses the drawing's paper and ink "
                                   "colors)"),
               ("STONE", "Turn to Stone", "The old outfit turns to grey stone in patches and cracks open just before "
                                          "the edge reaches it (Medusa; with Cast Off and Together at the End the "
                                          "statue crumbles)"),
               ("GOLD", "Turn to Gold", "Liquid gold spreads over the old outfit and turns it into polished gold, a "
                                        "molten line where it spreads (King Midas; the surface color is the gold)"),
               ("SILK", "Silk Cocoon", "White silk spreads over the old outfit and swells it into a cocoon, threads "
                                       "of silk winding round the body (with Cast Off and Together at the End the "
                                       "cocoon breaks open)"),
               ("CODE", "Digital Rain", "Columns of glowing code rain down the old outfit (The Matrix; uses the glow "
                                        "color)"),
               ("PAPERCUT", "Paper Cut", "The old outfit turns into a paper cut in patches, see-through where flowers "
                                         "are cut out of it (Chinese paper window flowers, 窗花; a red surface color "
                                         "for the red paper; pair it with Paper Birds)")),
        default="NONE", update=_sync)
    surface_width: _distance("Surface Reach", "How far ahead of the edge the old outfit starts to change", 3.0)
    surface_color: FloatVectorProperty(name="Surface Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                       default=(0.006, 0.006, 0.009), update=_sync,
                                       description="Color of the veins, the ice, the char, the stone, the gold or the "
                                                   "silk")
    silk_swell: _distance("Silk Swell", "With the silk cocoon: how far the silk swells the old outfit out", 0.15,
                          min_value=-10.0)
    silk_threads: BoolProperty(name="Silk Threads", default=True, update=_sync,
                               description="With the silk cocoon: threads of silk wind round the body, arms and legs "
                                           "as the silk spreads, and snap when the old outfit goes (needs an MMD "
                                           "skeleton)")
    thread_turns: FloatProperty(name="Thread Turns", default=9.0, min=0.5, soft_max=20.0, update=_sync,
                                description="Turns of the silk threads round each part of the body")
    ice_crystals: IntProperty(name="Ice Crystals", default=600, min=0, soft_max=3000, update=_sync,
                              description="With frost: about how many ice crystals grow out of the old outfit before "
                                          "the edge shatters it (0 = none; they use the particle color)")
    crystal_size: _distance("Crystal Size", "How tall the ice crystals grow", 0.6)
    ice_clarity: FloatProperty(name="Ice Clarity", default=0.5, min=0.0, max=1.0, subtype="FACTOR", update=_sync,
                               description="With frost: how clear the ice is between the white frost, like glass that "
                                           "shows what is under it (EEVEE needs raytracing or screen space refraction)")

    # --- line art / ink wash
    paint_style: EnumProperty(
        name="Drawing Style",
        items=(("NONE", "None", "The new outfit appears in its own colours"),
               ("LINEART", "Sketch Then Color", "The new outfit first shows ahead of the edge as a line drawing on "
                                                      "paper (outlined, screentone where it is dark), then its colours "
                                                      "flood in behind the edge like watercolour"),
               ("INK", "Ink Wash", "The new outfit appears at the edge as an ink wash painting, then its colours bloom "
                                   "behind it (pair it with the old outfit's Ink Wash surface and ink drops)"),
               ("CODE", "Digital Rain", "The new outfit appears at the edge as columns of glowing code raining down "
                                        "it, then its colours come in behind it (The Matrix; uses the glow color)")),
        default="NONE", update=_sync)
    paint_width: _distance("Color Bleed", "How far behind the edge the colours have filled in", 2.5)
    sketch_width: _distance("Sketch Ahead", "Line art: how far ahead of the edge the drawing shows", 3.0)
    outline_width: _distance("Outline Width", "Thickness of the drawing's outline (0 = none)", 0.025, soft_max=0.3)
    paper_color: FloatVectorProperty(name="Paper Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                     default=(0.95, 0.93, 0.88), update=_sync)
    ink_color: FloatVectorProperty(name="Ink Color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                   default=(0.02, 0.02, 0.025), update=_sync)

    # --- hologram ahead of the edge
    holo_enable: BoolProperty(name="Hologram", default=False, update=_sync,
                              description="The new outfit first shows up ahead of the edge as a see-through veil "
                                          "(a hologram, a starry veil, a black silhouette or ice), then turns solid")
    holo_style: EnumProperty(
        name="Veil",
        items=(("SCAN", "Hologram", "A see-through glowing hologram with scan lines"),
               ("STARS", "Starry Veil", "A dark veil of night sky full of stars: the outfit shows as a starry sky "
                                        "first (a magical girl's starry dress before it is real)"),
               ("SHADOW", "Black Silhouette", "A black shape with a thin glowing rim, which then turns into the outfit"),
               ("ICE", "Ice", "Pale clear ice with frost, which then turns into the outfit")),
        default="SCAN", update=_sync)
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
                            description="Follow the beats of the music (Find Beats first): the glitch slices "
                                        "reshuffle, jump and flash on them, the wires and the rim flare, the particles "
                                        "pop, and the finale, the halves clamping shut, the ghosts meeting and the old "
                                        "outfit shattering all at once land on a beat")
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
               ("CHUNKS", "Cast Off", "Break into armour-like chunks that are thrown off and fall"),
               ("SUCK", "Sucked In", "Break into flakes that spiral into the start point on the chest, like a magical "
                                     "girl's brooch taking the old clothes in; the particles follow them"),
               ("HUSK", "Leave a Husk",
                "The whole old model is left behind at the moment as a husk, holding still while the dancer goes on "
                "in the new outfit, then it crumbles away or floats off (Black Myth's 聚形散气, a cicada's shell). "
                "Building plays the animation once to record it")),
        default="SHRINK", update=_sync)
    husk_style: EnumProperty(
        name="Husk",
        items=(("AMBER", "Cicada Shell", "A see-through amber shell, like a cicada's"),
               ("PVC", "Glossy Figure", "Its own colours under a glossy coat, like a painted figure (for the "
                                        "figurine)"),
               ("GHOST", "Ghostly", "A see-through ghost of the old self, glowing towards its outline (uses the glow "
                                  "color)"),
               ("ASIS", "As It Is", "It looks just like the old outfit (with the surface on it: stone, gold, "
                                    "ice ...)")),
        default="AMBER", update=_sync)
    husk_away: EnumProperty(
        name="Then",
        items=(("CRUMBLE", "Crumble", "It crumbles away from the top, the pieces blowing off with the wind"),
               ("FLOAT", "Float Away", "It floats up and fades out (the soul leaving the body)"),
               ("FIGURINE", "Becomes a Figurine", "It shrinks to a figurine a seventh as tall on a clear stand beside "
                                                  "the dancer and stays there (the AI figurine craze of 2025)")),
        default="CRUMBLE", update=_sync)
    husk_motion: EnumProperty(
        name="Husk Pose",
        items=(("STILL", "Holds Still", "It stands still where it was at the moment (building records it there)"),
               ("DANCE", "Dances Beside", "It steps out beside the dancer and dances on, the old self and the new one "
                                          "side by side (Lady Gaga's Abracadabra), until it goes")),
        default="STILL", update=_sync)
    split_side: EnumProperty(
        name="Steps Out",
        items=(("RIGHT", "To the Right", "To the right of the picture"),
               ("LEFT", "To the Left", "To the left of the picture")),
        default="RIGHT", update=_sync)
    split_mirror: BoolProperty(name="Mirror Image", default=True, update=_sync,
                               description="It dances as the dancer's mirror image, so the two face each other's way")
    split_distance: _distance("Step Out", "How far beside the dancer it dances", 8.0, soft_max=50.0)
    husk_hold: FloatProperty(name="Husk Holds", default=0.35, min=0.0, max=2.0, subtype="FACTOR", update=_sync,
                             description="How long the husk stands still before it goes, as a share of the "
                                         "transformation")
    husk_time: FloatProperty(name="Husk Goes", default=0.3, min=0.02, max=2.0, subtype="FACTOR", update=_sync,
                             description="How long it takes to crumble or float away, as a share of the "
                                         "transformation")
    suck_turns: FloatProperty(name="Spiral Turns", default=1.5, min=-10.0, max=10.0, update=_sync,
                              description="How many times the flakes circle the brooch on their way in")
    exit_timing: EnumProperty(
        name="Exit Timing",
        items=(("EDGE", "With the Edge", "Each part of the old outfit goes where the edge passes"),
               ("AT_ONCE", "Together at the End",
                "The old outfit stays while the wave crosses it and goes all at once when the wave is done: freeze, "
                "then shatter. Under clear ice the new outfit forms as the wave passes; under a surface you cannot see "
                "through (stone, gold, silk ...) it is there when the old outfit goes")),
        default="EDGE", update=_sync)
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
                                description="How far the whole picture flashes to white as the finale starts, and as "
                                            "the lightning bolt strikes (needs the compositor node: Add White Flash)")
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
               ("NOTE", "Music Notes", "Glowing music notes that stand facing the front and sway as they float off "
                                       "(for dancing)"),
               ("CARD", "Playing Cards", "Playing cards that tumble in the wind (X-Men's Gambit)"),
               ("FEATHER", "Feathers", "Feathers that drift off (the particle color tints them: white for an angel, "
                                       "black for a black swan)"),
               ("BAT", "Bats", "Black bats flapping their wings (vampire)"),
               ("INK", "Ink Drops", "Splashes of black ink (ink wash)"),
               ("GLYPH", "Code Glyphs", "Glowing glyphs of code that fall and change as they go (The Matrix; let the "
                                        "wind blow down)"),
               ("PEBBLE", "Pebbles", "Small stones that tumble down (crumbling stone; the particle color tints them)"),
               ("PAPER_BIRD", "Paper Birds", "Red folded paper birds that flap away (with the paper cut)"),
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
