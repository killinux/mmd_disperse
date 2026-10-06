"""Procedural Geometry Nodes trees for the suit-up effect.

Mirrors the Hell FX "Spider-Man suit-up" tutorial:

* a sphere mask (an empty) whose scale is the reveal radius,
* the boundary is broken up with a noise texture,
* the new outfit is deleted outside the sphere and its edge is pushed out
  along the normals with a Map Range gradient,
* a hexagonal wire layer (Triangulate -> Dual Mesh -> Mesh to Curve ->
  Curve to Mesh) crawls along the boundary,
* the old outfit is shrunk inwards and then deleted behind the boundary.

Beyond the tutorial, the distance can come from a precomputed arrival field (the wave flows over the body
or sweeps up / down, see arrival.py), the old outfit can break into flakes and particles instead, the new
outfit can show up as a hologram ahead of the edge, and the edge can glitch: horizontal slices flicker
between the two outfits. Once the new outfit is complete it can flash (all at once, or a band of light sweeps
over it) and burst into sparkles (finale). The new outfit can first form as a dark undersuit with its final look
trailing behind, and both outfits mark how close each vertex is to the cut so materials can light up the inside
seen through it. Both outfits can also break into scales that turn over as the edge passes, the old outfit on one
side of every scale and the new one on the other (Mystique), and the wires, the rim, the finale and the particles
can pulse on the beats of the music. Arcs of lightning can crackle along the edge after a bolt strikes the start
point, and a transporter beam can shimmer one outfit away and the other in inside a column of light.
"""

import math

import bpy

VERSION = 15

FIELD_GROUP = "MMDDisperse Field"
TARGET_GROUP = "MMDDisperse Target"
BASE_GROUP = "MMDDisperse Base"
RIBBON_GROUP = "MMDDisperse Ribbon"
PROBE_GROUP = "MMDDisperse Probe"
VENOM_GROUP = "MMDDisperse Venom"
RING_GROUP = "MMDDisperse Ring"

ATTR_EDGE = "disperse_edge"
ATTR_LOCK = "disperse_lock"
ATTR_REST = "rest_position"
ATTR_ARRIVAL = "disperse_arrival"
ATTR_HOLO = "disperse_holo"
# Leave behind (see launch.py): world position of each vertex at its moment, when it broke off (old outfit) or when
# its finale star was born (new outfit) ...
ATTR_LAUNCH = "disperse_launch"
# ... and per face corner when its whole piece broke off (old outfit) or took off to fly in (new outfit).
ATTR_CHUNK_LAUNCH = "disperse_chunk_launch"
ATTR_CUT = "disperse_cut"  # 1 at the edge, fading with the distance from it: back faces there glow (inner glow)
ATTR_LAYER = "disperse_layer"  # new outfit: 1 where it still shows the dark undersuit
# Old outfit: 0 far ahead of the edge .. 1 at it (and behind): materials draw black veins, frost or char there.
ATTR_AHEAD = "disperse_ahead"
ATTR_AGE = "mmdd_age"  # mask radius minus the noisy distance; scratch attribute of the Base group and the probe
ATTR_PIECE_AGE = "mmdd_piece_age"  # probe: the age a whole piece is timed by
ATTR_VERTEX = "mmdd_vertex"  # probe: original vertex index of a vertex of the cut mesh
ATTR_CORNER = "mmdd_corner"  # probe: original face corner index
ATTR_ISLAND = "mmdd_island"  # probe: chunk of a vertex of the cut mesh
ATTR_NORMAL = "mmdd_normal"  # scratch attribute of the particle emitters, removed again
ATTR_PICK = "mmdd_pick"  # scratch: faces that release a finale star
ATTR_HELD = "mmdd_held"  # scratch: positions put aside while the recorded spots of the fly-in pieces are measured
ATTR_START = "mmdd_start"  # scratch: centre of a fly-in piece where it took off ...
ATTR_START_NORMAL = "mmdd_start_normal"  # ... and its normal there
ATTR_FLIP = "mmdd_flip"  # scratch: how far the scale of a face has turned over (0 .. 1)
ATTR_CELL = "mmdd_cell"  # scratch: the scale a face belongs to
ATTR_PAINT = "disperse_paint"  # new outfit, line art / ink wash: 1 still a drawing .. 0 in its own colours
ATTR_SHADOW = "disperse_shadow"  # rising from the shadow: 1 where the outfit is (flattened into) its black shadow
ATTR_SCREEN = "mmdd_screen"  # the front's panel / TV static (rings.py): x, y across it (-1 .. 1), z the frame
ATTR_SCREEN_STYLE = "mmdd_screen_style"  # ... 0 the glowing panel, 1 the static
ATTR_SMOKE = "mmdd_smoke_clear"  # smoke puff (on its instances): 0 dense .. 1 cleared (0 when missing: still dense)
ATTR_FRAME = "mmdd_frame"  # the frame, on what the materials animate: the digital rain, the transporter beam's column
ATTR_BEAM = "mmdd_beam"  # the beam's column: x, y round it (cosine, sine), z up it (0 at the bottom .. 1 at the top)
ATTR_VARIANT = "mmdd_variant"  # particle shapes made of several (the code glyphs): which one a face belongs to
ATTR_FLAME = "mmdd_flame"  # flames: how strongly the shell round the body burns (0 .. 1)
ATTR_FLAME_CARD = "mmdd_flame_card"  # ... a tongue of flame: x across it (-1 .. 1), y up it (0 .. 1), z 1
ATTR_FLAME_SEED = "mmdd_flame_seed"  # ... each tongue's own random number (on the instances)
ATTR_PETAL = "mmdd_petal"  # the lotus: x across a petal (-1 .. 1), y up it (0 .. 1), z 0 outer / 1 inner petals
ATTR_BAND = "mmdd_band"  # rings drawn as bands (soul rings, the shockwave): across the band, -1 .. 1
ATTR_SOUL = "mmdd_soul"  # soul rings (on the instances): x which ring (its colour), y how bright
ATTR_HUSK = "disperse_husk"  # the old outfit's husk left behind: 1 solid .. 0 gone (0 elsewhere)
_ARC_DIR = "mmdd_arc_dir"  # scratch: the way the distance grows over the surface, where the arcs crackle
_ARC_ATTRS = ("mmdd_arc_normal", "mmdd_arc_side", "mmdd_arc_len", "mmdd_arc_rnd")  # scratch: each arc's own values

# Wing angles (degrees) of the poses a butterfly cycles through.
FLAP_ANGLES = (70.0, 45.0, 15.0, -10.0, 15.0, 45.0)
# Share of the finale the light sweep takes to cross the outfit; the last sparkles fade in the rest.
SWEEP_SHARE = 0.7
GLYPHS = 12  # code glyphs in the glyph particle shape (particles.py)
ARC_POINTS = 14  # points along an arc of lightning
STRIKE_POINTS = 120  # ... and along the bolt of the strike

# (name, socket type, default, min, max, subtype)
FIELD_INPUTS = (
    ("Mask", "NodeSocketObject", None, None, None, None),
    ("Use Rest Position", "NodeSocketBool", True, None, None, None),
    ("Use Arrival", "NodeSocketBool", False, None, None, None),
    ("Noise Scale", "NodeSocketFloat", 0.3, 0.0, 10000.0, None),
    ("Noise Detail", "NodeSocketFloat", 2.0, 0.0, 15.0, None),
    ("Noise Amount", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
    ("Reach", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Glitch", "NodeSocketBool", False, None, None, None),
    ("Glitch Width", "NodeSocketFloat", 3.0, 0.0, 10000.0, "DISTANCE"),
    ("Slice Height", "NodeSocketFloat", 0.25, 0.0, 10000.0, "DISTANCE"),
    ("Glitch Rate", "NodeSocketFloat", 0.5, 0.0, 100.0, None),
    ("Glitch Shift", "NodeSocketFloat", 0.4, 0.0, 10000.0, "DISTANCE"),
    ("Glitch Flash", "NodeSocketBool", True, None, None, None),
    ("Beat Sync", "NodeSocketBool", False, None, None, None),
    ("Beat Object", "NodeSocketObject", None, None, None, None),
)

# Symbiote (venom.py): tendrils and strands of the outfit carrying the skeleton (the old one, or the new one alone).
VENOM_INPUTS = (
    ("Venom", "NodeSocketBool", False, None, None, None),
    ("Venom Skeleton", "NodeSocketObject", None, None, None, None),
    ("Tendril Radius", "NodeSocketFloat", 0.06, 0.0, 10000.0, "DISTANCE"),
    ("Tendril Speed", "NodeSocketFloat", 2.0, 0.0, 100.0, None),
    ("Tendril Absorb", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Strand Life", "NodeSocketFloat", 3.0, 0.0, 1e9, "DISTANCE"),
    ("Venom Material", "NodeSocketMaterial", None, None, None, None),
)

# Entrances without a front, timed by the mask radius against Clamp Distance (the moment): the evolution flash
# (the outfits flash in turn, faster and faster), rising from the shadow (the body sinks into its shadow, the new
# outfit stands up out of it) and the transporter beam (the outfits shimmer out and in inside a column of light).
TIMELINE_INPUTS = (
    ("Evolve", "NodeSocketBool", False, None, None, None),
    ("Shadow", "NodeSocketBool", False, None, None, None),
    ("Shadow Direction", "NodeSocketVector", (0.35, 0.55, -1.0), None, None, None),
    ("Beam", "NodeSocketBool", False, None, None, None),
)

# Both outfits. Lightning: arcs crackling along the edge over the new outfit (over the old one when there is no new
# one) and the bolt that strikes the start point first. One mesh of the effect (Main) draws what there is once: the
# strike and the transporter beam's column with its sparkles. Code: store the frame for the digital rain.
EXTRA_INPUTS = (
    ("Main", "NodeSocketBool", False, None, None, None),
    ("Arcs", "NodeSocketBool", False, None, None, None),
    ("Arc Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Arc Length", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Arc Reach", "NodeSocketFloat", 0.8, 0.0, 1e9, "DISTANCE"),
    ("Arc Thickness", "NodeSocketFloat", 0.015, 0.0, 1e9, "DISTANCE"),
    ("Arc Material", "NodeSocketMaterial", None, None, None, None),
    ("Strike", "NodeSocketBool", False, None, None, None),
    ("Strike Until", "NodeSocketFloat", 0.0, 0.0, 1e9, "DISTANCE"),
    ("Strike Height", "NodeSocketFloat", 30.0, 0.0, 1e9, "DISTANCE"),
    ("Beam Count", "NodeSocketInt", 250, 0, 100000, None),
    ("Beam Material", "NodeSocketMaterial", None, None, None, None),
    ("Star Object", "NodeSocketObject", None, None, None, None),
    ("Star Size", "NodeSocketFloat", 0.35, 0.0, 1e9, "DISTANCE"),
    ("Code", "NodeSocketBool", False, None, None, None),
    # 1.10: the new outfit is there all at once (Swap), or inside a lotus bud that closes and opens again (Lotus)
    ("Swap", "NodeSocketBool", False, None, None, None),
    ("Lotus", "NodeSocketBool", False, None, None, None),
    ("Lotus Petals", "NodeSocketInt", 8, 3, 32, None),
    ("Lotus Material", "NodeSocketMaterial", None, None, None, None),
    # flames along the edge or round the whole body (Flame Aura: up from Start to Peak, down by End)
    ("Flames", "NodeSocketBool", False, None, None, None),
    ("Flame Aura", "NodeSocketBool", False, None, None, None),
    ("Flame Width", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Flame Height", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Flame Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Flame Start", "NodeSocketFloat", 0.0, -1e9, 1e9, "DISTANCE"),
    ("Flame Peak", "NodeSocketFloat", 1.0, -1e9, 1e9, "DISTANCE"),
    ("Flame End", "NodeSocketFloat", 2.0, -1e9, 1e9, "DISTANCE"),
    ("Flame Material", "NodeSocketMaterial", None, None, None, None),
    ("Camera", "NodeSocketObject", None, None, None, None),
    # a shockwave on the floor (from Shock Start to Shock End of the mask radius) and soul rings rising round the body
    ("Shock", "NodeSocketBool", False, None, None, None),
    ("Shock Start", "NodeSocketFloat", 0.0, -1e9, 1e9, "DISTANCE"),
    ("Shock End", "NodeSocketFloat", 1.0, -1e9, 1e9, "DISTANCE"),
    ("Shock Size", "NodeSocketFloat", 10.0, 0.0, 1e9, "DISTANCE"),
    ("Shock Material", "NodeSocketMaterial", None, None, None, None),
    ("Dust Material", "NodeSocketMaterial", None, None, None, None),
    ("Soul Rings", "NodeSocketInt", 0, 0, 9, None),
    ("Soul Start", "NodeSocketFloat", 0.0, -1e9, 1e9, "DISTANCE"),
    ("Soul Peak", "NodeSocketFloat", 1.0, -1e9, 1e9, "DISTANCE"),
    ("Soul End", "NodeSocketFloat", 2.0, -1e9, 1e9, "DISTANCE"),
    ("Soul Material", "NodeSocketMaterial", None, None, None, None),
)

# Scales (Mystique): both outfits break into scales that turn over where the edge passes.
SCALE_INPUTS = (
    ("Scales", "NodeSocketBool", False, None, None, None),
    ("Scale Size", "NodeSocketFloat", 0.5, 0.0, 10000.0, "DISTANCE"),
    ("Flip Width", "NodeSocketFloat", 1.5, 0.0, 1e9, "DISTANCE"),
)

TARGET_INPUTS = FIELD_INPUTS + (
    ("Subdivide", "NodeSocketInt", 0, 0, 3, None),
    ("Edge Width", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
    ("Edge Push", "NodeSocketFloat", 0.4, -10000.0, 10000.0, "DISTANCE"),
    ("Wire", "NodeSocketBool", True, None, None, None),
    ("Hex Wire", "NodeSocketBool", True, None, None, None),
    ("Wire Inner", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
    ("Wire Outer", "NodeSocketFloat", 0.5, 0.0, 10000.0, "DISTANCE"),
    ("Wire Radius", "NodeSocketFloat", 0.03, 0.0, 10000.0, "DISTANCE"),
    ("Wire Lift", "NodeSocketFloat", 0.04, -10000.0, 10000.0, "DISTANCE"),
    ("Wire Resolution", "NodeSocketInt", 4, 3, 32, None),
    ("Wire Material", "NodeSocketMaterial", None, None, None, None),
    ("Edge Glow", "NodeSocketBool", True, None, None, None),
    ("Hologram", "NodeSocketBool", False, None, None, None),
    ("Hologram Width", "NodeSocketFloat", 2.5, 0.0, 10000.0, "DISTANCE"),
    ("Assemble", "NodeSocketBool", False, None, None, None),
    ("Piece Size", "NodeSocketFloat", 1.2, 0.0, 10000.0, "DISTANCE"),
    ("Fly Distance", "NodeSocketFloat", 5.0, 0.0, 10000.0, "DISTANCE"),
    ("Fly Range", "NodeSocketFloat", 1.6, 0.0, 10000.0, "DISTANCE"),
    ("Spin", "NodeSocketFloat", 4.0, -1000.0, 1000.0, "ANGLE"),
    ("Finale", "NodeSocketBool", False, None, None, None),
    ("Finale Start", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Finale Length", "NodeSocketFloat", 3.0, 0.0, 1e9, "DISTANCE"),
    ("Finale Glow", "NodeSocketFloat", 0.5, 0.0, 1000.0, None),
    ("Sparkles", "NodeSocketBool", False, None, None, None),
    ("Sparkle Object", "NodeSocketObject", None, None, None, None),
    ("Sparkle Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Sparkle Size", "NodeSocketFloat", 0.35, 0.0, 10000.0, "DISTANCE"),
    ("Sparkle Distance", "NodeSocketFloat", 3.0, 0.0, 10000.0, "DISTANCE"),
    ("Finale Sweep", "NodeSocketBool", False, None, None, None),
    ("Sweep Width", "NodeSocketFloat", 0.8, 0.0, 10000.0, "DISTANCE"),
    ("Undersuit", "NodeSocketBool", False, None, None, None),
    ("Undersuit Width", "NodeSocketFloat", 2.0, 0.0, 1e9, "DISTANCE"),
    ("Inner Glow", "NodeSocketBool", False, None, None, None),
    ("Inner Depth", "NodeSocketFloat", 2.0, 0.0, 1e9, "DISTANCE"),
    ("Leave Behind", "NodeSocketBool", False, None, None, None),
    ("Launch Space", "NodeSocketObject", None, None, None, None),
    ("Goo", "NodeSocketBool", False, None, None, None),
    ("Clamp", "NodeSocketBool", False, None, None, None),
    ("Clamp Distance", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Clamp Offset", "NodeSocketFloat", 5.0, 0.0, 1e9, "DISTANCE"),
    ("Ghosts", "NodeSocketBool", False, None, None, None),
    ("Ghost Count", "NodeSocketInt", 6, 1, 64, None),
    ("Ghost Distance", "NodeSocketFloat", 5.0, 0.0, 1e9, "DISTANCE"),
    ("Reactor", "NodeSocketBool", False, None, None, None),
    ("Reactor Size", "NodeSocketFloat", 0.6, 0.0, 1e9, "DISTANCE"),
    ("Plates", "NodeSocketBool", False, None, None, None),
    ("Plate Size", "NodeSocketFloat", 0.7, 0.0, 1e9, "DISTANCE"),
    ("Plate Lift", "NodeSocketFloat", 0.25, -1e9, 1e9, "DISTANCE"),
    ("Plate Width", "NodeSocketFloat", 1.6, 0.0, 1e9, "DISTANCE"),
    ("Paint Style", "NodeSocketInt", 0, 0, 3, None),
    ("Paint Width", "NodeSocketFloat", 2.0, 0.0, 1e9, "DISTANCE"),
    ("Sketch Width", "NodeSocketFloat", 3.0, 0.0, 1e9, "DISTANCE"),
    ("Outline Width", "NodeSocketFloat", 0.03, 0.0, 1e9, "DISTANCE"),
    ("Outline Material", "NodeSocketMaterial", None, None, None, None),
    ("Hold Until", "NodeSocketFloat", 0.0, 0.0, 1e9, "DISTANCE"),
    ("Poof", "NodeSocketBool", False, None, None, None),
    ("Smoke Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Smoke Size", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Smoke Material", "NodeSocketMaterial", None, None, None, None),
) + VENOM_INPUTS + SCALE_INPUTS + TIMELINE_INPUTS + EXTRA_INPUTS

BASE_INPUTS = FIELD_INPUTS + (
    ("Shrink", "NodeSocketFloat", 0.08, -10000.0, 10000.0, "DISTANCE"),
    ("Delete Offset", "NodeSocketFloat", 0.6, 0.0, 10000.0, "DISTANCE"),
    ("Fragments", "NodeSocketBool", False, None, None, None),
    ("Chunks", "NodeSocketBool", False, None, None, None),
    ("Piece Size", "NodeSocketFloat", 1.2, 0.0, 10000.0, "DISTANCE"),
    ("Chunk Force", "NodeSocketFloat", 3.0, 0.0, 10000.0, "DISTANCE"),
    ("Silhouette", "NodeSocketBool", False, None, None, None),
    ("Silhouette Width", "NodeSocketFloat", 3.0, 0.0, 10000.0, "DISTANCE"),
    ("Flake Size", "NodeSocketFloat", 0.85, 0.0, 1.0, "FACTOR"),
    ("Flake Subdivide", "NodeSocketInt", 0, 0, 2, None),
    ("Flight", "NodeSocketFloat", 2.5, 0.0, 10000.0, "DISTANCE"),
    ("Burst", "NodeSocketFloat", 0.25, -10000.0, 10000.0, "DISTANCE"),
    ("Wind", "NodeSocketVector", (0.0, 2.0, 5.0), None, None, "TRANSLATION"),
    ("Turbulence", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
    ("Spin", "NodeSocketFloat", 4.0, -1000.0, 1000.0, "ANGLE"),
    ("Flake Glow", "NodeSocketBool", True, None, None, None),
    ("Particles", "NodeSocketBool", False, None, None, None),
    ("Particle Object", "NodeSocketObject", None, None, None, None),
    ("Flap", "NodeSocketBool", False, None, None, None),
    ("Upright", "NodeSocketBool", False, None, None, None),
    ("Flap Speed", "NodeSocketFloat", 1.5, 0.0, 100.0, None),
    ("Particle Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Particle Size", "NodeSocketFloat", 0.35, 0.0, 10000.0, "DISTANCE"),
    ("Particle Flight", "NodeSocketFloat", 5.0, 0.0, 10000.0, "DISTANCE"),
    ("Leave Behind", "NodeSocketBool", False, None, None, None),
    ("Launch Space", "NodeSocketObject", None, None, None, None),
    ("Inner Glow", "NodeSocketBool", False, None, None, None),
    ("Inner Depth", "NodeSocketFloat", 2.0, 0.0, 1e9, "DISTANCE"),
    ("Surface Ahead", "NodeSocketBool", False, None, None, None),
    ("Surface Reach", "NodeSocketFloat", 3.0, 0.0, 1e9, "DISTANCE"),
    ("Crystals", "NodeSocketBool", False, None, None, None),
    ("Crystal Object", "NodeSocketObject", None, None, None, None),
    ("Crystal Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Crystal Size", "NodeSocketFloat", 0.6, 0.0, 10000.0, "DISTANCE"),
    ("Clamp", "NodeSocketBool", False, None, None, None),
    ("Clamp Distance", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Edge Glow", "NodeSocketBool", True, None, None, None),
    ("Suck", "NodeSocketBool", False, None, None, None),
    ("Suck Target", "NodeSocketVector", (0.0, 0.0, 0.0), None, None, None),
    ("Suck Turns", "NodeSocketFloat", 1.5, -100.0, 100.0, None),
    ("Brooch Object", "NodeSocketObject", None, None, None, None),
    ("Swell", "NodeSocketFloat", 0.0, -1e9, 1e9, "DISTANCE"),
    ("Glyphs", "NodeSocketBool", False, None, None, None),
    # 1.10: the old outfit left behind as a husk at the moment it goes (recorded where it was then), which holds for
    # Husk Hold and then crumbles away (or floats up, fading) over Husk Span
    ("Husk", "NodeSocketBool", False, None, None, None),
    ("Husk Hold", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Husk Span", "NodeSocketFloat", 1.0, 0.0, 1e9, "DISTANCE"),
    ("Husk Float", "NodeSocketBool", False, None, None, None),
    ("Husk Rise", "NodeSocketFloat", 3.0, -1e9, 1e9, "DISTANCE"),
    ("Clamp Jitter", "NodeSocketFloat", 0.04, 0.0, 1.0, None),
) + VENOM_INPUTS + SCALE_INPUTS + TIMELINE_INPUTS + EXTRA_INPUTS

# The probe takes these from the modifier it stands in for (the new outfit's finale and fly-in settings are
# missing on the old outfit's, which does not use them).
PROBE_INPUTS = FIELD_INPUTS + (
    ("Pieces", "NodeSocketBool", False, None, None, None),
    ("Piece Size", "NodeSocketFloat", 1.2, 0.0, 10000.0, "DISTANCE"),
    ("Target", "NodeSocketBool", False, None, None, None),
    ("Finale Start", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Finale Length", "NodeSocketFloat", 3.0, 0.0, 1e9, "DISTANCE"),
    ("Finale Sweep", "NodeSocketBool", False, None, None, None),
    ("Sweep Width", "NodeSocketFloat", 0.8, 0.0, 10000.0, "DISTANCE"),
    ("Fly Range", "NodeSocketFloat", 1.6, 0.0, 10000.0, "DISTANCE"),
    ("Clamp", "NodeSocketBool", False, None, None, None),
    ("Clamp Distance", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Clamp Jitter", "NodeSocketFloat", 0.04, 0.0, 1.0, None),
)

RING_STYLES = ("MAGIC", "SPARKS", "PANEL", "STATIC", "COMET", "HALO")
# The front's decoration (rings.py), in world units: the ring object is not scaled.
RING_INPUTS = (
    ("Mask", "NodeSocketObject", None, None, None, None),
    ("Style", "NodeSocketInt", 0, 0, len(RING_STYLES) - 1, None),
    ("Start", "NodeSocketVector", (0.0, 0.0, 0.0), None, None, None),
    ("Axis", "NodeSocketVector", (0.0, 0.0, 1.0), None, None, None),
    ("U", "NodeSocketVector", (1.0, 0.0, 0.0), None, None, None),
    ("V", "NodeSocketVector", (0.0, 1.0, 0.0), None, None, None),
    ("Half U", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Half V", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Span", "NodeSocketFloat", 10.0, 0.0, 1e9, None),
    ("Lead", "NodeSocketFloat", 0.0, -1e9, 1e9, None),
    ("Size", "NodeSocketFloat", 1.0, 0.0, 100.0, None),
    ("Pitch", "NodeSocketFloat", 2.0, 0.0, 1e9, None),
    ("Line Width", "NodeSocketFloat", 0.05, 0.0, 1e9, None),
    ("Star Size", "NodeSocketFloat", 0.35, 0.0, 1e9, None),
    ("Beat Sync", "NodeSocketBool", False, None, None, None),
    ("Beat Object", "NodeSocketObject", None, None, None, None),
    ("Ring Material", "NodeSocketMaterial", None, None, None, None),
    ("Screen Material", "NodeSocketMaterial", None, None, None, None),
    ("Star Object", "NodeSocketObject", None, None, None, None),
    ("Mirror", "NodeSocketBool", False, None, None, None),
    ("Span Back", "NodeSocketFloat", 0.0, 0.0, 1e9, None),  # how far the mirrored front goes (0: as far as Span)
)

RIBBON_INPUTS = (
    ("Mask", "NodeSocketObject", None, None, None, None),
    ("Start", "NodeSocketFloat", 0.0, -1e9, 1e9, "DISTANCE"),
    ("End", "NodeSocketFloat", 1.0, -1e9, 1e9, "DISTANCE"),
    ("Lead", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
    ("Fade From", "NodeSocketFloat", 1.0, -1e9, 1e9, "DISTANCE"),
    ("Linger", "NodeSocketFloat", 2.0, 0.0, 10000.0, "DISTANCE"),
    ("Width", "NodeSocketFloat", 0.15, 0.0, 10000.0, "DISTANCE"),
    ("Material", "NodeSocketMaterial", None, None, None, None),
)

# Inputs measured in object space: the add-on's sizes are world units, divided by the object's scale.
DISTANCE_INPUTS = frozenset(spec[0] for spec in FIELD_INPUTS + TARGET_INPUTS + BASE_INPUTS if spec[5] == "DISTANCE")

# Blender 3.x has no socket subtypes on group interfaces; the subtype is part of the socket type.
_TYPED_3X = {
    ("NodeSocketFloat", "DISTANCE"): "NodeSocketFloatDistance",
    ("NodeSocketFloat", "FACTOR"): "NodeSocketFloatFactor",
    ("NodeSocketFloat", "ANGLE"): "NodeSocketFloatAngle",
    ("NodeSocketVector", "TRANSLATION"): "NodeSocketVectorTranslation",
}


def _add_socket(ng, name, in_out, socket_type, default=None, min_value=None, max_value=None, subtype=None):
    if hasattr(ng, "interface"):  # Blender 4.0+
        sock = ng.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
        if subtype is not None:
            sock.subtype = subtype
    else:
        socket_type = _TYPED_3X.get((socket_type, subtype), socket_type)
        sock = (ng.inputs if in_out == "INPUT" else ng.outputs).new(socket_type, name)
    if default is not None:
        sock.default_value = default
    if min_value is not None:
        sock.min_value = min_value
    if max_value is not None:
        sock.max_value = max_value
    return sock


def _new_group(name, is_modifier):
    ng = bpy.data.node_groups.get(name)
    if ng is None or ng.bl_idname != "GeometryNodeTree":
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    else:
        ng.nodes.clear()
        if hasattr(ng, "interface"):
            ng.interface.clear()
        else:
            ng.inputs.clear()
            ng.outputs.clear()
    if hasattr(ng, "is_modifier"):
        ng.is_modifier = is_modifier
    ng["mmd_disperse_version"] = VERSION
    return ng


def _enabled(sockets, name=None):
    """Sockets in use. Blender 3.x nodes keep one hidden socket per data type (Switch, Store ...)."""
    return [s for s in sockets if s.enabled and (name is None or s.name == name)]


class _Builder:
    """Tiny helper so the trees below read like the node graphs in the video."""

    def __init__(self, ng):
        self.ng = ng

    def node(self, idname, x, y, **props):
        n = self.ng.nodes.new(idname)
        n.location = (x, y)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def feed(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.ng.links.new(value, socket)
        elif value is not None:
            socket.default_value = value

    def math(self, op, a, b=None, c=None, x=0, y=0, clamp=False):
        n = self.node("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        self.feed(n.inputs[2], c)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None, x=0, y=0):
        n = self.node("ShaderNodeVectorMath", x, y, operation=op)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        if scale is not None:
            self.feed(n.inputs[3], scale)
        out = "Value" if op in {"DOT_PRODUCT", "DISTANCE", "LENGTH"} else "Vector"
        return n.outputs[out]

    def compare(self, op, a, b, x=0, y=0):
        n = self.node("FunctionNodeCompare", x, y, data_type="FLOAT", operation=op)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        return n.outputs[0]

    def boolean(self, op, a, b=None, x=0, y=0):
        n = self.node("FunctionNodeBooleanMath", x, y, operation=op)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        return n.outputs[0]

    def map_range(self, value, from_min, from_max, to_min=0.0, to_max=1.0, x=0, y=0, smooth=False):
        n = self.node("ShaderNodeMapRange", x, y, data_type="FLOAT", clamp=True,
                      interpolation_type="SMOOTHSTEP" if smooth else "LINEAR")
        for i, v in enumerate((value, from_min, from_max, to_min, to_max)):
            self.feed(n.inputs[i], v)
        return n.outputs[0]

    def switch(self, input_type, cond, false, true, x=0, y=0):
        n = self.node("GeometryNodeSwitch", x, y, input_type=input_type)
        switch, if_false, if_true = _enabled(n.inputs)
        self.feed(switch, cond)
        self.feed(if_false, false)
        self.feed(if_true, true)
        return _enabled(n.outputs)[0]

    def named_attribute(self, name, data_type, x=0, y=0):
        """(attribute, exists) sockets of a Named Attribute node."""
        n = self.node("GeometryNodeInputNamedAttribute", x, y, data_type=data_type)
        n.inputs["Name"].default_value = name
        return _enabled(n.outputs, "Attribute")[0], n.outputs["Exists"]

    def store(self, geometry, name, value, data_type="FLOAT", domain="POINT", x=0, y=0):
        n = self.node("GeometryNodeStoreNamedAttribute", x, y, data_type=data_type, domain=domain)
        self.feed(n.inputs["Geometry"], geometry)
        n.inputs["Name"].default_value = name
        self.feed(_enabled(n.inputs, "Value")[0], value)
        return n.outputs["Geometry"]

    def delete(self, geometry, selection, domain, x=0, y=0):
        n = self.node("GeometryNodeDeleteGeometry", x, y, domain=domain, mode="ALL")
        self.feed(n.inputs["Geometry"], geometry)
        self.feed(n.inputs["Selection"], selection)
        return n.outputs["Geometry"]

    def set_position(self, geometry, offset=None, selection=None, position=None, x=0, y=0):
        n = self.node("GeometryNodeSetPosition", x, y)
        self.feed(n.inputs["Geometry"], geometry)
        self.feed(n.inputs["Selection"], selection)
        self.feed(n.inputs["Position"], position)
        self.feed(n.inputs["Offset"], offset)
        return n.outputs["Geometry"]

    def on_domain(self, value, domain, data_type="FLOAT", x=0, y=0):
        """Evaluate a field on another domain, e.g. the average of a point field over each face."""
        n = self.node("GeometryNodeFieldOnDomain", x, y, domain=domain, data_type=data_type)
        self.feed(_enabled(n.inputs)[0], value)
        return _enabled(n.outputs)[0]

    def separate(self, geometry, selection, domain, x=0, y=0):
        """(selected, inverted) geometry of a Separate Geometry node."""
        n = self.node("GeometryNodeSeparateGeometry", x, y, domain=domain)
        self.feed(n.inputs["Geometry"], geometry)
        self.feed(n.inputs["Selection"], selection)
        return n.outputs["Selection"], n.outputs["Inverted"]

    def join(self, geometries, x=0, y=0):
        n = self.node("GeometryNodeJoinGeometry", x, y)
        for geometry in geometries:
            self.ng.links.new(geometry, n.inputs["Geometry"])
        return n.outputs["Geometry"]

    def combine(self, vx, vy, vz, x=0, y=0):
        n = self.node("ShaderNodeCombineXYZ", x, y)
        for sock, value in zip(n.inputs, (vx, vy, vz)):
            self.feed(sock, value)
        return n.outputs[0]

    def split_xyz(self, vector, x=0, y=0):
        n = self.node("ShaderNodeSeparateXYZ", x, y)
        self.feed(n.inputs[0], vector)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def white_noise(self, vector, x=0, y=0):
        """(value, color) of a White Noise texture: stable pseudo-random numbers for a position."""
        n = self.node("ShaderNodeTexWhiteNoise", x, y, noise_dimensions="3D")
        self.feed(n.inputs["Vector"], vector)
        return n.outputs[0], n.outputs[1]

    def accumulate(self, value, group, data_type="FLOAT", x=0, y=0, domain="POINT", output="Total"):
        """Per-group total of a point (or `domain`) field (Accumulate Field); `output` "Leading" for the running total
        up to and including each element."""
        n = self.node("GeometryNodeAccumulateField", x, y, data_type=data_type, domain=domain)
        self.feed(_enabled(n.inputs, "Value")[0], value)
        self.feed(n.inputs["Group ID"], group)
        return _enabled(n.outputs, output)[0]

    def curve_to_mesh(self, curve, profile, x=0, y=0):
        """Curve to Mesh scaled by the curve radius. Blender 4.2+ has a Scale input and no longer uses the
        radius by itself; 3.x always does."""
        n = self.node("GeometryNodeCurveToMesh", x, y)
        self.feed(n.inputs["Curve"], curve)
        self.feed(n.inputs["Profile Curve"], profile)
        scale = n.inputs.get("Scale")
        if scale is not None:
            self.feed(scale, self.node("GeometryNodeInputRadius", x - 200, y - 250).outputs[0])
        return n.outputs["Mesh"]

    def rotate(self, vector, center, axis, angle, x=0, y=0):
        n = self.node("ShaderNodeVectorRotate", x, y, rotation_type="AXIS_ANGLE")
        for name, value in (("Vector", vector), ("Center", center), ("Axis", axis), ("Angle", angle)):
            self.feed(n.inputs[name], value)
        return n.outputs[0]


def build_field_group():
    """Distance to the (noisy) sphere mask - or the precomputed arrival distance - and the mask radius,
    plus the glitch fields both outfits share (so a slice shows exactly one of them), the clean distance
    along the path (Path, without the edge noise) and the beat (1 on a beat of the music, fading; 0 without beat
    sync)."""
    ng = _new_group(FIELD_GROUP, is_modifier=False)
    for spec in FIELD_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    # Probe: the distance at a given point of the rest pose (with the arrival distance there) instead of the
    # element's own (the scales time a whole scale by its site).
    _add_socket(ng, "Probe", "INPUT", "NodeSocketBool", False)
    _add_socket(ng, "Probe Point", "INPUT", "NodeSocketVector", (0.0, 0.0, 0.0))
    _add_socket(ng, "Probe Arrival", "INPUT", "NodeSocketFloat", 0.0)
    _add_socket(ng, "Distance", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Radius", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Glitching", "OUTPUT", "NodeSocketBool")
    _add_socket(ng, "New Side", "OUTPUT", "NodeSocketBool")
    _add_socket(ng, "Glitch Offset", "OUTPUT", "NodeSocketVector")
    _add_socket(ng, "Flash", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Path", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Beat", "OUTPUT", "NodeSocketFloat")

    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -1100, 0)
    go = b.node("NodeGroupOutput", 900, 0)

    # Object Info (Relative) of the mask empty: location = sphere centre, scale = radius.
    info = b.node("GeometryNodeObjectInfo", -800, 300, transform_space="RELATIVE")
    b.feed(info.inputs["Object"], gi.outputs["Mask"])
    radius = b.vmath("DOT_PRODUCT", info.outputs["Scale"], (1 / 3, 1 / 3, 1 / 3), x=-550, y=300)

    # Measure in rest space when available so the reveal sticks to the body while it dances.
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-1100, y=-250)
    position = b.node("GeometryNodeInputPosition", -1100, -420).outputs[0]
    use_rest = b.boolean("AND", gi.outputs["Use Rest Position"], has_rest, x=-850, y=-150)
    coord = b.switch("VECTOR", use_rest, position, rest, x=-600, y=-150)
    noise_coord = b.switch("VECTOR", has_rest, position, rest, x=-600, y=-400)
    coord = b.switch("VECTOR", gi.outputs["Probe"], coord, gi.outputs["Probe Point"], x=-500, y=-150)
    noise_coord = b.switch("VECTOR", gi.outputs["Probe"], noise_coord, gi.outputs["Probe Point"], x=-500, y=-400)
    sphere = b.vmath("DISTANCE", coord, info.outputs["Location"], x=-350, y=-50)

    # Other paths (along the body, sweeps): distance precomputed per vertex at build time.
    arrival, has_arrival = b.named_attribute(ATTR_ARRIVAL, "FLOAT", x=-600, y=150)
    arrival = b.switch("FLOAT", gi.outputs["Probe"], arrival, gi.outputs["Probe Arrival"], x=-500, y=250)
    use_arrival = b.boolean("AND", gi.outputs["Use Arrival"], has_arrival, x=-350, y=150)
    dist = b.switch("FLOAT", use_arrival, sphere, arrival, x=-150, y=0)

    # "Displacing Edge": noise texture breaks up the sphere boundary.
    noise = b.node("ShaderNodeTexNoise", -350, -350, noise_dimensions="3D")
    b.feed(noise.inputs["Vector"], noise_coord)
    b.feed(noise.inputs["Scale"], gi.outputs["Noise Scale"])
    b.feed(noise.inputs["Detail"], gi.outputs["Noise Detail"])
    noise.inputs["Roughness"].default_value = 0.5
    # outputs[0] is "Fac" before Blender 5.0 and "Factor" after.
    signed = b.math("MULTIPLY_ADD", noise.outputs[0], 2.0, -1.0, x=-100, y=-350)
    # Fade the noise in while the sphere is still small, otherwise points near the
    # centre would already be revealed at radius 0.
    amount = gi.outputs["Noise Amount"]
    ramp = b.math("DIVIDE", radius, b.math("MULTIPLY", amount, 2.0, x=-100, y=-550), x=150, y=-500, clamp=True)
    amp = b.math("MULTIPLY", amount, ramp, x=350, y=-450)
    distance = b.math("MULTIPLY_ADD", signed, amp, dist, x=600, y=-150)

    # --- Glitch: in a band around the front, horizontal slices flicker between the outfits. The band
    # opens after the start and closes before the mask stops, so nothing flickers at either end.
    half = b.math("MINIMUM", b.math("MULTIPLY", gi.outputs["Glitch Width"], 0.5, x=-100, y=-800),
                  b.math("MAXIMUM", radius, 0.0, x=-100, y=-950), x=100, y=-850)
    left = b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["Reach"], radius, x=-100, y=-1100), 0.0,
                  x=100, y=-1100)
    half = b.math("MINIMUM", half, left, x=300, y=-950)
    ahead = b.math("SUBTRACT", distance, radius, x=300, y=-750)
    in_band = b.compare("LESS_THAN", b.math("ABSOLUTE", ahead, x=500, y=-750), half, x=700, y=-800)
    glitching = b.boolean("AND", gi.outputs["Glitch"], in_band, x=900, y=-800)
    # Chance that a slice shows the new outfit: 1 at the inner side of the band, 0 at the outer side.
    share = b.math("DIVIDE", b.math("SUBTRACT", half, ahead, x=500, y=-950),
                   b.math("MAXIMUM", b.math("MULTIPLY", half, 2.0, x=500, y=-1100), 1e-4, x=700, y=-1100),
                   x=900, y=-1000, clamp=True)
    height = b.split_xyz(position, x=-100, y=-1300)[2]
    row = b.math("FLOOR", b.math("DIVIDE", height, b.math("MAXIMUM", gi.outputs["Slice Height"], 1e-4,
                                                           x=-100, y=-1450), x=100, y=-1350), x=300, y=-1350)
    frame = b.node("GeometryNodeInputSceneTime", -100, -1600).outputs["Frame"]
    tick = b.math("FLOOR", b.math("MULTIPLY", frame, gi.outputs["Glitch Rate"], x=100, y=-1550), x=300, y=-1550)
    # On the beat (beats.py: the empty's X is a pulse, 1 on a beat; its Y counts the beats): the slices reshuffle on
    # every beat instead of at the rate, and jump, shift and flash most right on it.
    beat = b.node("GeometryNodeObjectInfo", -100, -1900, transform_space="ORIGINAL")
    b.feed(beat.inputs["Object"], gi.outputs["Beat Object"])
    pulse, beat_count, _beat_z = b.split_xyz(beat.outputs["Location"], x=100, y=-1900)
    on_beat = b.boolean("AND", gi.outputs["Beat Sync"],
                        b.compare("GREATER_THAN", b.vmath("LENGTH", beat.outputs["Scale"], x=100, y=-2100), 0.0,
                                  x=300, y=-2100), x=500, y=-2050)
    tick = b.switch("FLOAT", on_beat, tick, beat_count, x=500, y=-1600)
    dice, dice_color = b.white_noise(b.combine(row, tick, 0.37, x=500, y=-1400), x=700, y=-1400)
    new_side = b.compare("LESS_THAN", dice, share, x=1100, y=-1000)
    jump_x, jump_y, glow_z = b.split_xyz(dice_color, x=900, y=-1400)
    jump_chance = b.switch("FLOAT", on_beat, 0.35, b.math("MULTIPLY_ADD", pulse, 0.8, 0.08, x=700, y=-2200),
                           x=900, y=-2150)
    jumping = b.boolean("AND", glitching, b.compare("LESS_THAN", jump_x, jump_chance, x=1100, y=-1350),
                        x=1300, y=-1300)
    shift_scale = b.switch("FLOAT", on_beat, 1.0, b.math("ADD", pulse, 0.5, x=700, y=-2350), x=900, y=-2300)
    shift = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY_ADD", jump_y, 2.0, -1.0, x=1100, y=-1500),
                                      gi.outputs["Glitch Shift"], x=1300, y=-1500), shift_scale, x=1400, y=-1550)
    offset = b.combine(b.switch("FLOAT", jumping, 0.0, shift, x=1500, y=-1400), 0.0, 0.0, x=1700, y=-1400)
    flash_level = b.switch("FLOAT", on_beat, 0.85, b.math("MULTIPLY_ADD", pulse, -0.4, 0.97, x=700, y=-2500),
                           x=900, y=-2450)
    flashing = b.boolean("AND", glitching, b.compare("GREATER_THAN", glow_z, flash_level, x=1100, y=-1650),
                         x=1300, y=-1650)
    flashing = b.boolean("AND", flashing, gi.outputs["Glitch Flash"], x=1400, y=-1700)
    flash = b.switch("FLOAT", flashing, 0.0, 1.0, x=1500, y=-1650)

    b.feed(go.inputs["Distance"], distance)
    b.feed(go.inputs["Radius"], radius)
    b.feed(go.inputs["Glitching"], glitching)
    b.feed(go.inputs["New Side"], new_side)
    b.feed(go.inputs["Glitch Offset"], offset)
    b.feed(go.inputs["Flash"], flash)
    b.feed(go.inputs["Path"], dist)
    b.feed(go.inputs["Beat"], b.switch("FLOAT", on_beat, 0.0, pulse, x=700, y=-2700))
    return ng


def _field_node(b, field_group, gi, x, y):
    """Outputs of the shared Field group: Distance, Radius, Glitching, New Side, Glitch Offset, Flash, Path, Beat."""
    n = b.node("GeometryNodeGroup", x, y)
    n.node_tree = field_group
    for spec in FIELD_INPUTS:
        b.feed(n.inputs[spec[0]], gi.outputs[spec[0]])
    return n.outputs


def _self_info(b, x, y):
    """Object Info of the modified object itself: its world rotation and scale, to work with world directions."""
    info = b.node("GeometryNodeObjectInfo", x, y, transform_space="ORIGINAL")
    b.feed(info.inputs["Object"], b.node("GeometryNodeSelfObject", x - 200, y).outputs[0])
    return info


def _unrotate(b, info, vector, x, y):
    """A world direction in the object space of `info`'s object: its rotation undone (the length stays)."""
    turn = b.node("ShaderNodeVectorRotate", x, y, rotation_type="EULER_XYZ", invert=True)
    b.feed(turn.inputs["Vector"], vector)
    b.feed(turn.inputs["Rotation"], info.outputs["Rotation"])
    return turn.outputs[0]


def _launch_space(b, gi, x, y):
    """(Object Info of the Launch Space empty, whether one is set). The empty replays the object's motion as it was
    recorded (launch.py), which brings recorded world positions back into object space."""
    space = b.node("GeometryNodeObjectInfo", x, y, transform_space="ORIGINAL")
    b.feed(space.inputs["Object"], gi.outputs["Launch Space"])
    has_space = b.compare("GREATER_THAN", b.vmath("LENGTH", space.outputs["Scale"], x=x + 200, y=y - 150), 0.0,
                          x=x + 400, y=y - 150)
    return space, has_space


def _recorded(b, space, has_space, name, x, y):
    """(object-space position, exists) of a recorded world position attribute."""
    world, exists = b.named_attribute(name, "FLOAT_VECTOR", x=x, y=y)
    turned = _unrotate(b, space, b.vmath("SUBTRACT", world, space.outputs["Location"], x=x + 200, y=y), x + 400, y)
    local = b.vmath("DIVIDE", turned, space.outputs["Scale"], x=x + 600, y=y)
    return local, b.boolean("AND", exists, has_space, x=x + 600, y=y - 150)


def _world_instances(b, instances, info, x, y):
    """Instances turned back by the object's own rotation (Z, then Y, then X: the inverse of its XYZ Euler), each
    about its own position, so they keep their orientation in the world when the whole model turns."""
    angles = b.split_xyz(info.outputs["Rotation"], x, y - 250)
    for i, axis in enumerate((2, 1, 0)):
        turn = [0.0, 0.0, 0.0]
        turn[axis] = b.math("MULTIPLY", angles[axis], -1.0, x=x + 200 + 200 * i, y=y - 400)
        n = b.node("GeometryNodeRotateInstances", x + 200 + 200 * i, y)
        b.feed(n.inputs["Instances"], instances)
        b.feed(n.inputs["Rotation"], b.combine(*turn, x=x + 200 + 200 * i, y=y - 250))
        b.feed(n.inputs["Pivot Point"], b.node("GeometryNodeInputPosition", x + 200 * i, y - 550).outputs[0])
        n.inputs["Local Space"].default_value = False
        instances = n.outputs["Instances"]
    return instances


def _remove_attributes(b, geometry, names, x, y):
    for i, name in enumerate(names):
        n = b.node("GeometryNodeRemoveAttribute", x + 200 * i, y)
        b.feed(n.inputs["Geometry"], geometry)
        n.inputs["Name"].default_value = name
        geometry = n.outputs["Geometry"]
    return geometry


# Point attributes of the symbiote's skeleton (venom.py). End A, end B: three vertex indices and their weights.
VENOM_ENDS = (("mmdd_a0", "mmdd_a1", "mmdd_a2", "mmdd_aw"), ("mmdd_b0", "mmdd_b1", "mmdd_b2", "mmdd_bw"))
VENOM_ATTRS = tuple(name for end in VENOM_ENDS for name in end) + (
    "mmdd_t", "mmdd_kind", "mmdd_s", "mmdd_len", "mmdd_root", "mmdd_rnd")
_VENOM_AGE = "mmdd_venom_age"  # scratch: age of the bound point
_VENOM_RADIUS = "mmdd_venom_radius"  # scratch: tube radius


def build_venom_group():
    """Tendrils and strands of the symbiote, rebuilt every frame from the skeleton (venom.py) on the deformed outfit
    `Mesh`, which carries the age of every vertex (ATTR_AGE: mask radius minus its noisy distance).

    A tendril grows out of its root once the edge has passed the root, faster than the edge (Tendril Speed), so it
    runs ahead; once the edge is Tendril Absorb past the root the goo swallows it again from the root on. A strand
    forms where the edge has passed both its ends, sags, thins as the body pulls it longer, snaps at three times its
    length and is gone after Strand Life."""
    ng = _new_group(VENOM_GROUP, is_modifier=False)
    _add_socket(ng, "Mesh", "INPUT", "NodeSocketGeometry")
    for spec in VENOM_INPUTS[1:]:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")

    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -2200, 0)
    go = b.node("NodeGroupOutput", 4200, 0)
    info = b.node("GeometryNodeObjectInfo", -2000, 600, transform_space="ORIGINAL")
    b.feed(info.inputs["Object"], gi.outputs["Venom Skeleton"])
    skel = info.outputs["Geometry"]
    position = b.node("GeometryNodeInputPosition", -2000, -100).outputs[0]
    normal = b.node("GeometryNodeInputNormal", -2000, -250).outputs[0]
    age = b.named_attribute(ATTR_AGE, "FLOAT", x=-2000, y=-400)[0]

    def sample(geometry, value, data_type, index, x, y):
        n = b.node("GeometryNodeSampleIndex", x, y, data_type=data_type, domain="POINT")
        b.feed(n.inputs["Geometry"], geometry)
        b.feed(_enabled(n.inputs, "Value")[0], value)
        b.feed(n.inputs["Index"], index)
        return _enabled(n.outputs, "Value")[0]

    def end(names, x, y):
        """Position, normal and age of a bound point: the corners of its triangle, weighted."""
        weights = b.split_xyz(b.named_attribute(names[3], "FLOAT_VECTOR", x=x, y=y + 200)[0], x=x + 200, y=y + 200)
        pos = nor = ag = None
        for i in range(3):
            index = b.named_attribute(names[i], "INT", x=x, y=y - 500 * i)[0]
            p = b.vmath("SCALE", sample(gi.outputs["Mesh"], position, "FLOAT_VECTOR", index, x + 300, y - 500 * i),
                        scale=weights[i], x=x + 500, y=y - 500 * i)
            q = b.vmath("SCALE", sample(gi.outputs["Mesh"], normal, "FLOAT_VECTOR", index, x + 300, y - 500 * i - 150),
                        scale=weights[i], x=x + 500, y=y - 500 * i - 150)
            a = b.math("MULTIPLY", sample(gi.outputs["Mesh"], age, "FLOAT", index, x + 300, y - 500 * i - 300),
                       weights[i], x=x + 500, y=y - 500 * i - 300)
            pos = p if pos is None else b.vmath("ADD", pos, p, x=x + 700, y=y - 500 * i)
            nor = q if nor is None else b.vmath("ADD", nor, q, x=x + 700, y=y - 500 * i - 150)
            ag = a if ag is None else b.math("ADD", ag, a, x=x + 700, y=y - 500 * i - 300)
        return pos, nor, ag

    pa, na, age_a = end(VENOM_ENDS[0], -1800, 2400)
    pb, nb, age_b = end(VENOM_ENDS[1], -1800, 800)
    t = b.named_attribute("mmdd_t", "FLOAT", x=-900, y=-500)[0]
    kind = b.named_attribute("mmdd_kind", "FLOAT", x=-900, y=-650)[0]
    s = b.named_attribute("mmdd_s", "FLOAT", x=-900, y=-800)[0]
    length = b.named_attribute("mmdd_len", "FLOAT", x=-900, y=-950)[0]
    rnd = b.named_attribute("mmdd_rnd", "FLOAT", x=-900, y=-1100)[0]
    root = b.named_attribute("mmdd_root", "INT", x=-900, y=-1250)[0]
    point = b.vmath("ADD", pa, b.vmath("SCALE", b.vmath("SUBTRACT", pb, pa, x=-700, y=1400), scale=t, x=-500, y=1400),
                    x=-300, y=1400)
    up = b.vmath("NORMALIZE", b.vmath("ADD", na, b.vmath("SCALE", b.vmath("SUBTRACT", nb, na, x=-700, y=1200),
                                                         scale=t, x=-500, y=1200), x=-300, y=1200), x=-100, y=1200)
    # kind: 0 tendril, 1 strand, 2 web (a membrane of goo in the fork of a tendril, timed like the tendril)
    web = b.compare("GREATER_THAN", kind, 1.5, x=-700, y=-500)
    strand = b.boolean("AND", b.compare("GREATER_THAN", kind, 0.5, x=-700, y=-650), b.boolean("NOT", web, x=-500,
                                                                                               y=-600), x=-500, y=-700)
    thick = b.math("MULTIPLY", gi.outputs["Tendril Radius"], b.math("MULTIPLY_ADD", rnd, 0.8, 0.6, x=-700, y=-1100),
                   x=-500, y=-1100)

    # --- Tendrils: the whole tendril is timed by the age at its root.
    aged = b.store(skel, _VENOM_AGE, age_a, x=-700, y=600)
    root_age = sample(aged, b.named_attribute(_VENOM_AGE, "FLOAT", x=-700, y=300)[0], "FLOAT", root, -500, 300)
    speed = b.math("MULTIPLY", gi.outputs["Tendril Speed"], b.math("MULTIPLY_ADD", rnd, 0.5, 0.75, x=-300, y=150),
                   x=-100, y=150)
    tip = b.math("MINIMUM", b.math("MULTIPLY", root_age, speed, x=100, y=300), length, x=300, y=300)
    absorb = b.math("MULTIPLY", gi.outputs["Tendril Absorb"], b.math("MULTIPLY_ADD", rnd, 0.6, 0.7, x=-300, y=0),
                    x=-100, y=0)
    tail = b.math("SUBTRACT", root_age, absorb, x=100, y=50)
    taper = b.math("MAXIMUM", b.math("MULTIPLY", length, 0.3, x=100, y=-150), 1e-4, x=300, y=-150)
    to_tip = b.math("SUBTRACT", tip, s, x=500, y=300)
    from_tail = b.math("SUBTRACT", s, tail, x=500, y=50)
    tip_fade = b.map_range(to_tip, 0.0, taper, x=700, y=300, smooth=True)
    fade = b.math("MULTIPLY", tip_fade,
                  b.map_range(from_tail, 0.0, b.math("MULTIPLY", taper, 0.5, x=500, y=-150), x=700, y=50, smooth=True),
                  x=900, y=200)
    # thickest where it comes out of the goo, 1.8 times as thick as from halfway on
    swell = b.math("MULTIPLY_ADD", b.math("SUBTRACT", 1.0, b.math("DIVIDE", s, b.math("MULTIPLY", length, 0.5, x=700,
                                                                                         y=-300), x=900, y=-300),
                                          x=1100, y=-300, clamp=True), 0.8, 1.0, x=1300, y=-300)
    tendril_radius = b.math("MULTIPLY", b.math("MULTIPLY", thick, fade, x=1100, y=200), swell, x=1300, y=200)
    tendril_shown = b.boolean("AND", b.compare("GREATER_EQUAL", to_tip, 0.0, x=700, y=500),
                              b.compare("GREATER_EQUAL", from_tail, 0.0, x=700, y=650), x=900, y=550)
    # The tip rises off the body and sways, feeling its way.
    frame = b.node("GeometryNodeInputSceneTime", 700, 900).outputs["Frame"]
    sway = b.math("MULTIPLY_ADD", b.math("SINE", b.math("MULTIPLY_ADD", frame, 0.22,
                                                         b.math("MULTIPLY", rnd, 2.0 * math.pi, x=700, y=1050),
                                                         x=900, y=950), x=1100, y=950), 0.5, 0.5, x=1300, y=950)
    tipness = b.math("SUBTRACT", 1.0, tip_fade, x=900, y=750)
    rise = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", tipness, tipness, x=1100, y=750), sway,
                                     x=1300, y=750), b.math("MULTIPLY", length, 0.12, x=1300, y=600), x=1500, y=700)

    # --- Strands: timed by the later of their two ends.
    strand_age = b.math("MINIMUM", age_a, age_b, x=-300, y=-1500)
    life = b.math("MAXIMUM", gi.outputs["Strand Life"], 1e-4, x=-300, y=-1650)
    span = b.vmath("DISTANCE", pa, pb, x=-300, y=-1800)
    stretch = b.math("DIVIDE", span, b.math("MAXIMUM", length, 1e-6, x=-300, y=-1950), x=-100, y=-1850)
    form = b.map_range(strand_age, 0.0, b.math("MULTIPLY", life, 0.12, x=-100, y=-1650), x=100, y=-1550, smooth=True)
    snap = b.map_range(strand_age, b.math("MULTIPLY", life, 0.6, x=-100, y=-2100), life, 1.0, 0.0, x=100, y=-1750,
                       smooth=True)
    thin = b.math("MINIMUM", b.math("POWER", b.math("MAXIMUM", stretch, 1e-3, x=100, y=-1950), -0.5, x=300, y=-1950),
                  1.0, x=500, y=-1950)
    # thick where it clings, thin in the middle
    neck = b.math("MULTIPLY_ADD", b.math("ABSOLUTE", b.math("MULTIPLY_ADD", t, 2.0, -1.0, x=100, y=-2150),
                                         x=300, y=-2150), 0.55, 0.45, x=500, y=-2150)
    strand_radius = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", thick, 0.5, x=300, y=-1400),
                                              b.math("MULTIPLY", form, snap, x=300, y=-1600), x=500, y=-1500),
                           b.math("MULTIPLY", thin, neck, x=700, y=-2000), x=900, y=-1700)
    strand_shown = b.boolean("AND", b.boolean("AND", b.compare("GREATER_THAN", strand_age, 0.0, x=300, y=-2350),
                                              b.compare("LESS_THAN", strand_age, life, x=300, y=-2500), x=500, y=-2400),
                             b.compare("LESS_THAN", stretch, 3.0, x=500, y=-2550), x=700, y=-2450)
    # It sags down in the world, deepest in the middle and more as it ages.
    me = _self_info(b, -300, -2800)
    down = b.vmath("NORMALIZE", _unrotate(b, me, (0.0, 0.0, -1.0), -100, -2800), x=100, y=-2800)
    middle = b.math("MULTIPLY", b.math("MULTIPLY", t, b.math("SUBTRACT", 1.0, t, x=100, y=-3000), x=300, y=-3000), 4.0,
                    x=500, y=-3000)
    droop = b.math("MULTIPLY_ADD", b.math("DIVIDE", strand_age, life, x=300, y=-3150, clamp=True), 0.2, 0.08,
                   x=500, y=-3150)
    sag = b.vmath("SCALE", down, scale=b.math("MULTIPLY", b.math("MULTIPLY", span, droop, x=700, y=-3100), middle,
                                                x=900, y=-3050), x=1100, y=-2900)

    radius = b.switch("FLOAT", strand, tendril_radius, strand_radius, x=1300, y=-500)
    shown = b.switch("BOOLEAN", strand, tendril_shown, strand_shown, x=1300, y=-700)
    # Tendrils lie on the surface, mostly above it; webs lie under their middle.
    lift = b.math("MULTIPLY_ADD", radius, 0.7, rise, x=1300, y=-900)
    offset = b.switch("VECTOR", strand, b.vmath("SCALE", up, scale=lift, x=1500, y=-900), sag, x=1700, y=-800)
    offset = b.switch("VECTOR", web, offset, b.vmath("SCALE", up, scale=b.math("MULTIPLY", thick, 0.45, x=1500,
                                                                               y=-1100), x=1700, y=-1100),
                      x=1900, y=-900)
    placed = b.set_position(aged, position=b.vmath("ADD", point, offset, x=1700, y=-600), x=1900, y=600)
    placed = b.store(placed, _VENOM_RADIUS, radius, x=2100, y=600)
    placed = b.delete(placed, b.boolean("NOT", shown, x=2100, y=400), "POINT", x=2300, y=600)
    webs, placed = b.separate(placed, web, "POINT", x=2400, y=800)
    placed = _remove_attributes(b, placed, VENOM_ATTRS + (_VENOM_AGE,), 2500, 600)
    webs = _remove_attributes(b, webs, VENOM_ATTRS + (_VENOM_AGE, _VENOM_RADIUS), 2600, 1000)

    curve = b.node("GeometryNodeMeshToCurve", 2500, 200)
    b.feed(curve.inputs["Mesh"], placed)
    smooth = b.node("GeometryNodeCurveSplineType", 2700, 200, spline_type="CATMULL_ROM")
    b.feed(smooth.inputs["Curve"], curve.outputs["Curve"])
    res = b.node("GeometryNodeSetSplineResolution", 2900, 200)
    b.feed(res.inputs["Geometry"], smooth.outputs["Curve"])
    res.inputs["Resolution"].default_value = 3
    width = b.node("GeometryNodeSetCurveRadius", 3100, 200)
    b.feed(width.inputs["Curve"], res.outputs["Geometry"])
    b.feed(width.inputs["Radius"], b.named_attribute(_VENOM_RADIUS, "FLOAT", x=2900, y=0)[0])
    curves = _remove_attributes(b, width.outputs["Curve"], (_VENOM_RADIUS,), 3300, 200)
    profile = b.node("GeometryNodeCurvePrimitiveCircle", 3300, -100, mode="RADIUS")
    profile.inputs["Resolution"].default_value = 6
    profile.inputs["Radius"].default_value = 1.0
    tube = b.curve_to_mesh(curves, profile.outputs["Curve"], x=3500, y=200)
    shade = b.node("GeometryNodeSetShadeSmooth", 3700, 200)
    b.feed(shade.inputs["Geometry"], b.join([tube, webs], x=3600, y=400))
    mat = b.node("GeometryNodeSetMaterial", 3900, 200)
    b.feed(mat.inputs["Geometry"], shade.outputs["Geometry"])
    b.feed(mat.inputs["Material"], gi.outputs["Venom Material"])
    b.feed(go.inputs["Geometry"], mat.outputs["Geometry"])
    return ng


def _venom(b, gi, venom_group, mesh, x, y):
    """The symbiote's tendrils and strands on `mesh` (which carries ATTR_AGE) when Venom is on; lazily evaluated."""
    n = b.node("GeometryNodeGroup", x, y)
    n.node_tree = venom_group
    b.feed(n.inputs["Mesh"], mesh)
    for spec in VENOM_INPUTS[1:]:
        b.feed(n.inputs[spec[0]], gi.outputs[spec[0]])
    return b.switch("GEOMETRY", gi.outputs["Venom"], None, n.outputs["Geometry"], x=x + 200, y=y)


def build_target_group(field_group, venom_group):
    """Modifier for the NEW outfit: reveal inside the sphere + glowing hex wire at the edge."""
    ng = _new_group(TARGET_GROUP, is_modifier=True)
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in TARGET_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")

    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -1600, 0)
    go = b.node("NodeGroupOutput", 2200, 0)

    sub = b.node("GeometryNodeSubdivideMesh", -1300, 300)
    b.feed(sub.inputs["Mesh"], gi.outputs["Geometry"])
    b.feed(sub.inputs["Level"], gi.outputs["Subdivide"])

    field = _field_node(b, field_group, gi, -1300, -300)
    d, radius, beat = field["Distance"], field["Radius"], field["Beat"]

    # Parts locked to the old model (face, hair ...) never come from the new one.
    lock = b.named_attribute(ATTR_LOCK, "BOOLEAN", x=-1300, y=500)[0]
    geo = b.delete(sub.outputs["Mesh"], lock, "FACE", x=-1000, y=300)
    # The object's own rotation (world directions) and, with leave behind, the motion it was recorded with.
    me = _self_info(b, -1300, -5000)
    space, has_space = _launch_space(b, gi, -1300, -5300)

    # --- Suit: 0 keep / 1 delete, then push the edge out along the normals.
    # With the hologram on, the new outfit already shows this far ahead of the edge (growing in from
    # nothing, so it is not there at radius 0).
    holo_width = b.math("MINIMUM", gi.outputs["Hologram Width"],
                        b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=-1000, y=-550), 2.0, x=-850, y=-550),
                        x=-700, y=-500)
    holo_width = b.switch("FLOAT", gi.outputs["Hologram"], 0.0, holo_width, x=-550, y=-500)
    # ... and as a line drawing with line art
    sketch_width = b.math("MINIMUM", gi.outputs["Sketch Width"],
                          b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=-1000, y=-750), 2.0, x=-850, y=-750),
                          x=-700, y=-700)
    line_art = b.compare("EQUAL", gi.outputs["Paint Style"], 1.0, x=-700, y=-850)
    sketch_width = b.switch("FLOAT", line_art, 0.0, sketch_width, x=-550, y=-700)
    front = b.math("ADD", radius, b.math("MAXIMUM", holo_width, sketch_width, x=-450, y=-600), x=-400, y=-500)
    shown = b.compare("LESS_EQUAL", d, front, x=-700, y=150)
    # Under an opaque shell of the old outfit that goes all at once (stone, gold, silk ...) the new outfit waits for
    # that moment instead of showing through it as it grows (Hold Until: 0 = no waiting).
    shown = b.boolean("AND", shown, b.compare("GREATER_EQUAL", radius, gi.outputs["Hold Until"], x=-700, y=300),
                      x=-650, y=200)
    # Reactor (Mark 50): the patch of the suit around the start point(s) is there first, glowing and pulsing, and the
    # suit flows out of it. Its glow fades once the wave is a few patch sizes on.
    reactor_stat = b.node("GeometryNodeAttributeStatistic", -1300, 1800, data_type="FLOAT", domain="POINT")
    b.feed(reactor_stat.inputs["Geometry"], geo)
    b.feed(_enabled(reactor_stat.inputs, "Attribute")[0], field["Path"])
    core = b.boolean("AND", gi.outputs["Reactor"], b.compare("LESS_THAN", b.math("SUBTRACT", field["Path"],
                                                                                 reactor_stat.outputs["Min"], x=-1100,
                                                                                 y=1800),
                                                             gi.outputs["Reactor Size"], x=-900, y=1800), x=-700,
                     y=1800)
    core = b.boolean("AND", core, b.compare("GREATER_THAN", radius, 0.0, x=-900, y=1650), x=-700, y=1650)
    shown = b.boolean("OR", shown, core, x=-600, y=250)
    reactor_frame = b.node("GeometryNodeInputSceneTime", -1300, 1500).outputs["Frame"]
    throb = b.math("MULTIPLY_ADD", b.math("SINE", b.math("MULTIPLY", reactor_frame, 0.8, x=-1100, y=1500), x=-900,
                                          y=1500), 0.45, 0.55, x=-700, y=1500)
    reactor_on = b.math("MULTIPLY", b.map_range(radius, 0.0, b.math("MULTIPLY", gi.outputs["Reactor Size"], 0.15,
                                                                    x=-1100, y=1350), x=-900, y=1350, smooth=True),
                        b.map_range(radius, b.math("MULTIPLY", gi.outputs["Reactor Size"], 4.0, x=-1100, y=1200),
                                    b.math("MULTIPLY", gi.outputs["Reactor Size"], 8.0, x=-1100, y=1050), 1.0, 0.0,
                                    x=-900, y=1150, smooth=True), x=-700, y=1300)
    reactor_glow = b.switch("FLOAT", core, 0.0, b.math("POWER", b.math("MULTIPLY", throb, reactor_on, x=-500, y=1400),
                                                       0.125, x=-300, y=1400), x=-100, y=1400)
    # Glitching slices show whichever outfit the dice picked.
    shown = b.switch("BOOLEAN", field["Glitching"], shown, field["New Side"], x=-550, y=150)
    suit = b.delete(geo, b.boolean("NOT", shown, x=-450, y=150), "POINT", x=-450, y=350)
    edge_start = b.math("SUBTRACT", radius, gi.outputs["Edge Width"], x=-700, y=-50)
    edge = b.map_range(d, edge_start, radius, x=-450, y=-50)
    grad = b.map_range(edge, 0.0, 1.0, x=-450, y=-200, smooth=True)
    normal = b.node("GeometryNodeInputNormal", -450, -350).outputs[0]
    push = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", grad, gi.outputs["Edge Push"], x=-250, y=-150),
                   x=-50, y=-150)
    push = b.vmath("ADD", push, field["Glitch Offset"], x=50, y=-250)
    suit = b.set_position(suit, push, x=150, y=350)
    # Linear 0..1 towards the boundary; materials turn it into a thin glowing rim. Nothing glows ahead of
    # the edge (hologram) except the glitch flashes.
    rim = b.switch("FLOAT", b.compare("GREATER_THAN", d, radius, x=150, y=-50), edge, 0.0, x=300, y=-50)
    rim = b.switch("FLOAT", gi.outputs["Edge Glow"], 0.0, rim, x=450, y=-50)
    rim = b.math("MAXIMUM", rim, field["Flash"], x=600, y=-50)
    rim = b.math("MAXIMUM", rim, reactor_glow, x=650, y=50)
    # Finale: once the outfit is complete all of it flashes (quick rise, slow fade). finale_t runs 0 -> 1
    # while the mask grows from Finale Start over Finale Length. Stored as flash^(1/8) like the silhouette.
    finale_t = b.math("DIVIDE", b.math("SUBTRACT", radius, gi.outputs["Finale Start"], x=-700, y=-1900),
                      b.math("MAXIMUM", gi.outputs["Finale Length"], 1e-4, x=-700, y=-2050), x=-500, y=-1950)
    attack = b.math("DIVIDE", finale_t, 0.1, x=-300, y=-1900, clamp=True)
    decay = b.math("POWER", b.math("SUBTRACT", 1.0, finale_t, x=-300, y=-2050, clamp=True), 2.0, x=-100, y=-2050)
    pulse = b.math("MULTIPLY", attack, decay, x=100, y=-1950)
    # ... and on the beat it flashes again, less as the finale goes on
    again = b.math("MULTIPLY", b.math("MULTIPLY", beat, 0.8, x=-100, y=-1750), decay, x=100, y=-1750)
    again = b.switch("FLOAT", b.compare("GREATER_THAN", finale_t, 0.0, x=100, y=-1600), 0.0, again, x=300, y=-1700)
    pulse = b.math("MAXIMUM", pulse, again, x=300, y=-1900)
    # ... or a band of light runs out from the start point along the wave's own path (the clean distance, no
    # edge noise) and has crossed the whole outfit after SWEEP_SHARE of the finale.
    sweep_span = b.math("ADD", gi.outputs["Finale Start"], gi.outputs["Sweep Width"], x=-700, y=-2250)
    front = b.math("MULTIPLY", b.math("DIVIDE", finale_t, SWEEP_SHARE, x=-500, y=-2200), sweep_span,
                   x=-300, y=-2250)
    off_band = b.math("ABSOLUTE", b.math("SUBTRACT", field["Path"], front, x=-100, y=-2250), x=100, y=-2250)
    band = b.map_range(off_band, 0.0, b.math("MAXIMUM", gi.outputs["Sweep Width"], 1e-4, x=100, y=-2400), 1.0, 0.0,
                       x=300, y=-2250, smooth=True)
    band = b.math("MULTIPLY", band, b.math("DIVIDE", finale_t, 0.03, x=300, y=-2450, clamp=True), x=500, y=-2300)
    band = b.math("MULTIPLY", band, b.math("ADD", beat, 1.0, x=500, y=-2450), x=600, y=-2350)  # brighter on a beat
    flash = b.math("MULTIPLY", b.switch("FLOAT", gi.outputs["Finale Sweep"], pulse, band, x=500, y=-2050),
                   gi.outputs["Finale Glow"], x=700, y=-2000)
    flash = b.switch("FLOAT", gi.outputs["Finale"], 0.0, b.math("POWER", flash, 0.125, x=900, y=-2000),
                     x=1100, y=-2000)
    rim = b.math("MAXIMUM", rim, flash, x=750, y=-50)
    # Dark undersuit (Mark 50 style): within Undersuit Width behind the edge the new outfit still shows as a dark
    # undersuit (materials draw it from disperse_layer), its final look forms behind that along a second glowing seam.
    layer_front = b.math("SUBTRACT", radius, gi.outputs["Undersuit Width"], x=-700, y=-2700)
    soft = b.math("MAXIMUM", b.math("MULTIPLY", gi.outputs["Undersuit Width"], 0.3, x=-700, y=-2850), 1e-4,
                  x=-500, y=-2850)
    under = b.map_range(d, layer_front, b.math("ADD", layer_front, soft, x=-300, y=-2800), x=-100, y=-2750,
                        smooth=True)
    under = b.switch("FLOAT", gi.outputs["Undersuit"], 0.0, under, x=100, y=-2750)
    # nothing ahead of the edge (the hologram shows there)
    suit_layer = b.switch("FLOAT", b.compare("GREATER_THAN", d, radius, x=100, y=-2900), under, 0.0, x=300, y=-2800)
    seam = b.map_range(d, b.math("SUBTRACT", layer_front, gi.outputs["Edge Width"], x=-300, y=-3000), layer_front,
                       x=-100, y=-3000)
    seam = b.switch("FLOAT", b.compare("GREATER_THAN", d, layer_front, x=-100, y=-3150), seam, 0.0, x=100, y=-3050)
    seam_on = b.boolean("AND", gi.outputs["Undersuit"], gi.outputs["Edge Glow"], x=100, y=-3200)
    rim = b.math("MAXIMUM", rim, b.switch("FLOAT", seam_on, 0.0, seam, x=300, y=-3050), x=850, y=-50)
    # on a beat of the music the rim flares (2.5 times as bright once the material raises it to the 8th power)
    rim = b.math("MULTIPLY", rim, b.math("MULTIPLY_ADD", beat, 0.12, 1.0, x=850, y=-250), x=1000, y=-100)
    suit = b.store(suit, ATTR_EDGE, rim, x=400, y=350)
    # 0 at the edge .. 1 at the front of the hologram (materials draw a scan ring there).
    holo = b.math("DIVIDE", b.math("SUBTRACT", d, radius, x=150, y=-650),
                  b.math("MAXIMUM", holo_width, 1e-4, x=150, y=-800), x=350, y=-700, clamp=True)
    holo = b.switch("FLOAT", gi.outputs["Hologram"], 0.0, holo, x=550, y=-700)
    suit = b.store(suit, ATTR_HOLO, holo, x=600, y=350)
    suit = b.switch("GEOMETRY", gi.outputs["Undersuit"], suit, b.store(suit, ATTR_LAYER, suit_layer, x=700, y=500),
                    x=800, y=350)
    # Symbiote goo: the edge bulges out in lumps and the goo coat (the undersuit) stands a little proud of the suit.
    goo_rest, goo_has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-100, y=-3700)
    lumps = b.node("ShaderNodeTexNoise", 300, -3700, noise_dimensions="3D")
    b.feed(lumps.inputs["Vector"], b.switch("VECTOR", goo_has_rest,
                                            b.node("GeometryNodeInputPosition", -100, -3850).outputs[0], goo_rest,
                                            x=100, y=-3750))
    b.feed(lumps.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Noise Scale"], 4.0, x=100, y=-3900))
    lumps.inputs["Detail"].default_value = 1.0
    lumpy = b.map_range(lumps.outputs[0], 0.3, 0.7, 0.2, 2.2, x=500, y=-3700)
    swell = b.math("ADD", b.math("MULTIPLY", grad, b.math("SUBTRACT", lumpy, 1.0, x=700, y=-3700), x=900, y=-3650),
                   b.math("MULTIPLY", suit_layer, 0.4, x=700, y=-3850), x=1100, y=-3700)
    goo = b.set_position(suit, b.vmath("SCALE", normal, scale=b.math("MULTIPLY", swell, gi.outputs["Edge Push"],
                                                                     x=1300, y=-3700), x=1500, y=-3600),
                         x=1000, y=500)
    suit = b.switch("GEOMETRY", gi.outputs["Goo"], suit, goo, x=1100, y=350)
    # Inner glow: 1 at the edge, fading over Inner Depth; materials light up the back faces there, the inside of the
    # outfit seen through the cut.
    cut = b.math("SUBTRACT", 1.0, b.math("DIVIDE", b.math("ABSOLUTE", b.math("SUBTRACT", d, radius, x=-700, y=-3400),
                                                          x=-500, y=-3400),
                                         b.math("MAXIMUM", gi.outputs["Inner Depth"], 1e-4, x=-500, y=-3550),
                                         x=-300, y=-3450, clamp=True), x=-100, y=-3450)

    def mark_cut(geometry, x, y):
        return b.switch("GEOMETRY", gi.outputs["Inner Glow"], geometry, b.store(geometry, ATTR_CUT, cut, x=x, y=y + 150),
                        x=x + 200, y=y)

    suit = mark_cut(suit, 900, 350)

    # --- Assemble: the new outfit arrives in pieces that fly in from around the body and click into
    # place where the front passes (instead of growing at the front).
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-1300, y=1200)
    position = b.node("GeometryNodeInputPosition", -1300, 1050).outputs[0]
    anchor = b.switch("VECTOR", has_rest, position, rest, x=-1100, y=1100)
    pieces, island, count, center, rest_center, piece_normal = _pieces(
        b, geo, anchor, gi.outputs["Piece Size"], 0.0, -1000, 1500)
    piece_d = b.math("DIVIDE", b.accumulate(d, island, x=1200, y=1200), count, x=1400, y=1200)
    lead = b.math("MINIMUM", gi.outputs["Fly Range"], b.math("MAXIMUM", radius, 0.0, x=1200, y=1050),
                  x=1400, y=1050)
    # 0 when a piece shows up (lead ahead of the front) .. 1 once it is in place
    landed = b.math("DIVIDE", b.math("ADD", b.math("SUBTRACT", radius, piece_d, x=1600, y=1200), lead,
                                     x=1800, y=1200),
                    b.math("MAXIMUM", lead, 1e-4, x=1600, y=1050), x=2000, y=1150, clamp=True)
    pieces = b.delete(pieces, b.compare("LESS_EQUAL", landed, 0.0, x=2000, y=1350), "POINT", x=2200, y=1500)
    # Leave behind: a piece takes off from a fixed point in the world, given by where the body was when it showed up
    # (recorded per face corner, launch.py). Put the piece there for a moment to measure its centre and normal, then
    # back; on a still model that is where it is anyway.
    chunk_launch, has_chunk_launch = _recorded(b, space, has_space, ATTR_CHUNK_LAUNCH, 1200, 2700)
    held = b.store(pieces, ATTR_HELD, position, "FLOAT_VECTOR", x=2400, y=2000)
    moved = b.set_position(held, selection=has_chunk_launch, position=chunk_launch, x=2600, y=2000)
    moved = b.store(moved, ATTR_START, b.vmath("DIVIDE", b.accumulate(position, island, "FLOAT_VECTOR", x=2600, y=2300),
                                              count, x=2800, y=2300), "FLOAT_VECTOR", x=2800, y=2000)
    piece_normal_now = b.node("GeometryNodeInputNormal", 2800, 2600).outputs[0]
    moved = b.store(moved, ATTR_START_NORMAL,
                    b.vmath("NORMALIZE", b.accumulate(piece_normal_now, island, "FLOAT_VECTOR", x=3000, y=2600),
                            x=3200, y=2600), "FLOAT_VECTOR", x=3000, y=2000)
    back = b.set_position(moved, position=b.named_attribute(ATTR_HELD, "FLOAT_VECTOR", x=3000, y=2300)[0],
                          x=3200, y=2000)
    pieces = b.switch("GEOMETRY", gi.outputs["Leave Behind"], pieces, back, x=3400, y=2000)
    start_center = b.switch("VECTOR", gi.outputs["Leave Behind"], center,
                            b.named_attribute(ATTR_START, "FLOAT_VECTOR", x=3200, y=2800)[0], x=3400, y=2800)
    start_normal = b.switch("VECTOR", gi.outputs["Leave Behind"], piece_normal,
                            b.named_attribute(ATTR_START_NORMAL, "FLOAT_VECTOR", x=3200, y=3000)[0], x=3400, y=3000)
    flying = b.math("SUBTRACT", 1.0, landed, x=2200, y=1150)
    rnd, rnd_color = b.white_noise(b.vmath("SCALE", rest_center, scale=5.31, x=2200, y=900), x=2400, y=900)
    jitter = b.vmath("SCALE", b.vmath("SUBTRACT", rnd_color, (0.5, 0.5, 0.5), x=2600, y=900), scale=1.2,
                     x=2800, y=900)
    # Random spread and the lift are world directions, so a piece in the air does not swing round with a turning model.
    lift = _unrotate(b, me, b.vmath("ADD", jitter, (0.0, 0.0, 0.5), x=3000, y=900), 3200, 900)
    heading = b.vmath("NORMALIZE", b.vmath("ADD", start_normal, lift, x=3400, y=950), x=3600, y=950)
    # It flies from its starting point (centre + heading * distance) to its place on the body, which moves along.
    start = b.vmath("ADD", start_center, b.vmath("SCALE", heading, scale=gi.outputs["Fly Distance"], x=3800, y=950),
                    x=4000, y=950)
    away = b.vmath("SCALE", b.vmath("SUBTRACT", start, center, x=4000, y=1100),
                   scale=b.math("MULTIPLY", flying, flying, x=2400, y=1100), x=4200, y=1000)
    turn = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Spin"], flying, x=2600, y=750),
                  b.math("MULTIPLY_ADD", rnd, 2.0, -1.0, x=2600, y=600), x=2800, y=700)
    # Leave behind: in the air a piece keeps the shape and the orientation it had in the world when it took off (the
    # recorded spots, brought into object space the way the object has moved since), so it does not bend and turn with
    # a dancing, turning body; over the last part of its flight it takes on the body's current shape.
    here = b.vmath("SUBTRACT", position, center, x=2600, y=450)
    then = b.vmath("SUBTRACT", chunk_launch, start_center, x=2600, y=300)
    settle = b.map_range(landed, 0.6, 1.0, x=2600, y=150, smooth=True)
    kept = b.vmath("ADD", then, b.vmath("SCALE", b.vmath("SUBTRACT", here, then, x=2800, y=300), scale=settle,
                                        x=3000, y=300), x=3200, y=300)
    keep = b.boolean("AND", gi.outputs["Leave Behind"], has_chunk_launch, x=2800, y=150)
    shape = b.vmath("ADD", center, b.switch("VECTOR", keep, here, kept, x=3400, y=350), x=3600, y=400)
    turned = b.rotate(shape, center, b.vmath("SUBTRACT", rnd_color, (0.5, 0.5, 0.5), x=2800, y=550), turn,
                      x=3000, y=650)
    grow = b.math("MULTIPLY_ADD", landed, 0.75, 0.25, x=3000, y=500)
    placed = b.vmath("ADD", center, b.vmath("SCALE", b.vmath("SUBTRACT", turned, center, x=3200, y=650),
                                            scale=grow, x=3400, y=650), x=3600, y=650)
    pieces = b.set_position(pieces, position=b.vmath("ADD", placed, away, x=3800, y=800), x=4000, y=1500)
    # Pieces glow softly while flying (0.9^8 in the material, the texture still shows); landed ones get
    # the usual rim at the front.
    piece_rim = b.math("MAXIMUM", rim, b.switch("FLOAT", b.compare("GREATER_THAN", flying, 0.001,
                                                                     x=3800, y=400), 0.0, 0.9, x=4000, y=400),
                       x=4200, y=400)
    pieces = b.store(pieces, ATTR_EDGE, piece_rim, x=4200, y=1500)
    # With the undersuit the pieces come in dark too and take on the final look behind the edge.
    pieces = b.switch("GEOMETRY", gi.outputs["Undersuit"], pieces, b.store(pieces, ATTR_LAYER, under, x=4400, y=1700),
                      x=4600, y=1500)
    pieces = mark_cut(pieces, 4800, 1500)
    pieces = _remove_attributes(b, pieces, (ATTR_HELD, ATTR_START, ATTR_START_NORMAL), 5200, 1500)
    suit = b.switch("GEOMETRY", gi.outputs["Assemble"], suit, pieces, x=5800, y=1000)

    # --- Clamp (Kamen Rider Build): the new outfit forms in two halves, front and back, printed from the feet up in
    # glowing frames out in front of and behind the body; they slide in and clamp shut with a flash. Progress p runs
    # 0 -> 1 while the mask grows to Clamp Distance (MMD models face -Y).
    p = b.math("DIVIDE", radius, b.math("MAXIMUM", gi.outputs["Clamp Distance"], 1e-4, x=-1000, y=6250), x=-800, y=6200)
    _rx, ry, rz = b.split_xyz(anchor, x=-1000, y=6000)

    def statistic(value, x, y):
        n = b.node("GeometryNodeAttributeStatistic", x, y, data_type="FLOAT", domain="POINT")
        b.feed(n.inputs["Geometry"], geo)
        b.feed(_enabled(n.inputs, "Attribute")[0], value)
        return n.outputs

    plane = statistic(ry, -800, 5800)["Mean"]
    heights = statistic(rz, -800, 5500)
    # Faces behind the plane through the middle (by their centre) make the back half; the mesh is cut between them.
    back = b.on_domain(b.switch("FLOAT", b.compare("GREATER_THAN", b.on_domain(ry, "FACE", x=-600, y=6000), plane,
                                                   x=-400, y=6000), 0.0, 1.0, x=-200, y=6000), "FACE", x=0, y=6000)
    border = b.on_domain(back, "EDGE", x=200, y=6100)
    split = b.node("GeometryNodeSplitEdges", 400, 6400)
    b.feed(split.inputs["Mesh"], geo)
    b.feed(split.inputs["Selection"], b.boolean("AND", b.compare("GREATER_THAN", border, 0.001, x=400, y=6150),
                                                b.compare("LESS_THAN", border, 0.999, x=400, y=6000), x=600, y=6100))
    # printed from the feet up over the first 30%, sliding in over the rest
    scan = b.map_range(p, 0.0, 0.3, x=-600, y=5300)
    slide = b.map_range(p, 0.35, 1.0, x=-600, y=5100)
    gap = b.math("MULTIPLY", b.math("SUBTRACT", 1.0, b.math("MULTIPLY", slide, slide, x=-400, y=5100), x=-200, y=5100),
                 gi.outputs["Clamp Offset"], x=0, y=5100)
    rise = b.math("DIVIDE", b.math("SUBTRACT", rz, heights["Min"], x=-600, y=5600),
                  b.math("MAXIMUM", heights["Range"], 1e-4, x=-600, y=5450), x=-400, y=5550)
    halves = b.delete(split.outputs["Mesh"], b.boolean("OR", b.compare("GREATER_THAN", rise, scan, x=600, y=5700),
                                                       b.compare("LESS_EQUAL", p, 0.0, x=600, y=5550), x=800, y=5650),
                      "POINT", x=800, y=6400)
    sign = b.math("MULTIPLY_ADD", back, 2.0, -1.0, x=200, y=5300)
    halves = b.set_position(halves, b.combine(0.0, b.math("MULTIPLY", sign, gap, x=400, y=5200), 0.0, x=600, y=5200),
                            x=1000, y=6400)
    # The printing line and, while they slide, the cut through the middle glow; it flares up as they close (the
    # finale, when it is on, flashes the whole outfit and bursts into stars at that moment).
    printing = b.math("MULTIPLY", b.map_range(rise, b.math("SUBTRACT", scan, 0.04, x=600, y=5000), scan, 0.0, 0.92,
                                               x=800, y=5000),
                      b.switch("FLOAT", b.compare("LESS_THAN", scan, 1.0, x=800, y=4850), 0.0, 1.0, x=1000, y=4850),
                      x=1200, y=4950)
    sliding = b.boolean("AND", b.compare("GREATER_THAN", p, 0.35, x=800, y=4700),
                        b.compare("LESS_THAN", p, 1.0, x=800, y=4550), x=1000, y=4650)
    seam = b.map_range(b.math("ABSOLUTE", b.math("SUBTRACT", ry, plane, x=600, y=4400), x=800, y=4400),
                       b.math("MULTIPLY", gi.outputs["Edge Width"], 0.3, x=800, y=4250), 0.0, x=1000, y=4400)
    after = b.math("DIVIDE", b.math("SUBTRACT", p, 1.0, x=600, y=4100), 0.1, x=800, y=4100)
    flare = b.math("MULTIPLY", b.math("DIVIDE", after, 0.1, x=1000, y=4150, clamp=True),
                   b.math("SUBTRACT", 1.0, after, x=1000, y=4000, clamp=True), x=1200, y=4100)
    seam = b.math("MULTIPLY", seam, b.math("MAXIMUM", b.switch("FLOAT", sliding, 0.0, 0.92, x=1200, y=4600),
                                           b.math("POWER", flare, 0.125, x=1400, y=4100), x=1400, y=4500),
                  x=1600, y=4450)
    clamp_rim = b.math("MAXIMUM", printing, seam, x=1800, y=4500)
    clamp_rim = b.switch("FLOAT", gi.outputs["Edge Glow"], 0.0, clamp_rim, x=2000, y=4500)
    halves = b.store(halves, ATTR_EDGE, b.math("MAXIMUM", clamp_rim, flash, x=2200, y=4500), x=1200, y=6400)
    # With the hologram on, the halves are holograms until they close.
    halves = b.store(halves, ATTR_HOLO, b.switch("FLOAT", gi.outputs["Hologram"], 0.0,
                                                 b.math("MULTIPLY", b.math("SUBTRACT", 1.0, slide, x=1200, y=6700),
                                                        0.6, x=1400, y=6700), x=1600, y=6700), x=1400, y=6400)
    suit = b.switch("GEOMETRY", gi.outputs["Clamp"], suit, halves, x=6000, y=1000)

    # The frames: a glowing rectangle around each half, sliding in with it and fading after the clamp.
    box = b.node("GeometryNodeBoundBox", 1000, 7200)
    b.feed(box.inputs["Geometry"], geo)
    lo, hi = box.outputs["Min"], box.outputs["Max"]
    lo_x, lo_y, lo_z = b.split_xyz(lo, x=1200, y=7300)
    hi_x, hi_y, hi_z = b.split_xyz(hi, x=1200, y=7100)
    margin = b.math("MULTIPLY", b.math("SUBTRACT", hi_z, lo_z, x=1400, y=7400), 0.04, x=1600, y=7400)
    quad = b.node("GeometryNodeCurvePrimitiveQuadrilateral", 1800, 7400, mode="RECTANGLE")
    b.feed(quad.inputs["Width"], b.math("MULTIPLY_ADD", margin, 2.0, b.math("SUBTRACT", hi_x, lo_x, x=1600, y=7600),
                                         x=1800, y=7600))
    # (standing on the floor rather than through it)
    b.feed(quad.inputs["Height"], b.math("MULTIPLY_ADD", margin, 0.9, b.math("SUBTRACT", hi_z, lo_z, x=1600, y=7800),
                                          x=1800, y=7800))
    mid_x = b.math("MULTIPLY", b.math("ADD", lo_x, hi_x, x=1400, y=7000), 0.5, x=1600, y=7000)
    mid_z = b.math("MULTIPLY_ADD", margin, 0.55, b.math("MULTIPLY", b.math("ADD", lo_z, hi_z, x=1400, y=6850), 0.5,
                                                        x=1600, y=6850), x=1800, y=6850)
    away = b.math("ADD", gap, margin, x=1600, y=6700)
    frames = []
    for i, (edge_y, sign_y) in enumerate(((lo_y, -1.0), (hi_y, 1.0))):
        n = b.node("GeometryNodeTransform", 2200, 7400 - 300 * i)
        b.feed(n.inputs["Geometry"], quad.outputs["Curve"])
        b.feed(n.inputs["Translation"], b.combine(mid_x, b.math("MULTIPLY_ADD", away, sign_y, edge_y,
                                                                x=2000, y=7000 - 300 * i), mid_z,
                                                  x=2200, y=7000 - 300 * i))
        n.inputs["Rotation"].default_value = (math.pi / 2, 0.0, 0.0)
        frames.append(n.outputs["Geometry"])
    shown_frame = b.math("MULTIPLY", b.map_range(p, 0.0, 0.05, x=2200, y=6500),
                         b.map_range(p, 0.97, 1.05, 1.0, 0.0, x=2200, y=6300), x=2400, y=6400)
    frame_curve = b.node("GeometryNodeSetCurveRadius", 2400, 7300)
    b.feed(frame_curve.inputs["Curve"], b.join(frames, x=2400, y=7500))
    b.feed(frame_curve.inputs["Radius"], b.math("MULTIPLY", shown_frame, 2.0, x=2600, y=6400))
    frame_profile = b.node("GeometryNodeCurvePrimitiveCircle", 2600, 7600, mode="RADIUS")
    b.feed(frame_profile.inputs["Resolution"], gi.outputs["Wire Resolution"])
    b.feed(frame_profile.inputs["Radius"], gi.outputs["Wire Radius"])
    frame_tube = b.curve_to_mesh(b.store(frame_curve.outputs["Curve"], ATTR_EDGE, 0.85, x=2600, y=7300),
                                 frame_profile.outputs["Curve"], x=2800, y=7300)
    frame_mat = b.node("GeometryNodeSetMaterial", 3000, 7300)
    b.feed(frame_mat.inputs["Geometry"], frame_tube)
    b.feed(frame_mat.inputs["Material"], gi.outputs["Wire Material"])
    framing = b.boolean("AND", gi.outputs["Clamp"], b.boolean("AND", b.compare("GREATER_THAN", p, 0.0, x=3000, y=7000),
                                                             b.compare("LESS_THAN", p, 1.05, x=3000, y=6850),
                                                             x=3200, y=6950), x=3400, y=7000)
    frames = b.switch("GEOMETRY", framing, None, frame_mat.outputs["Geometry"], x=3600, y=7300)

    # --- Ghosts (Kamen Rider Decade): see-through copies of the new outfit stand around the body, printed from the feet
    # up, and converge into it, each turning a little; where they meet (p = 1) the outfit is there with a flash.
    whole = b.store(geo, ATTR_EDGE, b.math("MAXIMUM", b.switch("FLOAT", gi.outputs["Edge Glow"], 0.0,
                                                                b.math("POWER", flare, 0.125, x=1400, y=8600),
                                                                x=1600, y=8600), flash, x=1800, y=8600),
                    x=1800, y=8800)
    merged = b.compare("GREATER_EQUAL", p, 1.0, x=1600, y=8400)
    real = b.switch("GEOMETRY", merged, None, whole, x=2000, y=8800)
    ghost = b.delete(geo, b.compare("GREATER_THAN", rise, scan, x=1400, y=9200), "POINT", x=1600, y=9400)
    ghost = b.store(ghost, ATTR_EDGE, printing, x=1800, y=9400)
    ghost = b.store(ghost, ATTR_HOLO, b.switch("FLOAT", gi.outputs["Hologram"], 0.0, 0.5, x=1800, y=9200),
                    x=2000, y=9400)
    index = b.node("GeometryNodeInputIndex", 1400, 10000).outputs[0]
    g_rnd, g_color = b.white_noise(b.combine(index, 0.37, 0.71, x=1600, y=10000), x=1800, y=10000)
    count = gi.outputs["Ghost Count"]
    # spread around the sides and the back: the 70 degrees in front of the model (-Y) stay clear
    gap = math.radians(70.0)
    angle = b.math("MULTIPLY_ADD", b.math("DIVIDE", b.math("ADD", index, 0.5, x=1600, y=10400),
                                          b.math("MAXIMUM", count, 1.0, x=1600, y=10300), x=1800, y=10300),
                   2.0 * math.pi - gap, -0.5 * math.pi + 0.5 * gap, x=2000, y=10300)
    # converging over the last 80%, faster and faster
    gather = b.map_range(p, 0.2, 1.0, x=1800, y=10600)
    out = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", gather, gather, x=2000, y=10600), x=2200, y=10600)
    reach_out = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Ghost Distance"],
                                          b.math("MULTIPLY_ADD", g_rnd, 0.5, 0.75, x=2000, y=10800), x=2200, y=10800),
                       out, x=2400, y=10700)
    _gx, _gy, g_lift = b.split_xyz(g_color, x=1800, y=10450)
    spot = b.vmath("SCALE", b.combine(b.math("COSINE", angle, x=2200, y=10350), b.math("SINE", angle, x=2200, y=10200),
                                      b.math("MULTIPLY_ADD", g_lift, 0.3, -0.15, x=2200, y=10050), x=2400, y=10300),
                   scale=reach_out, x=2600, y=10400)
    points = b.node("GeometryNodePoints", 2600, 10000)
    b.feed(points.inputs["Count"], count)
    b.feed(points.inputs["Position"], spot)
    copies = b.node("GeometryNodeInstanceOnPoints", 2800, 9600)
    b.feed(copies.inputs["Points"], points.outputs["Geometry"])
    b.feed(copies.inputs["Instance"], ghost)
    # each turns about its own middle (the body's middle, carried out with it), back to facing the front as it arrives
    centre = b.vmath("SCALE", b.vmath("ADD", lo, hi, x=2600, y=9200), scale=0.5, x=2800, y=9200)
    turn = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY_ADD", g_rnd, 1.2, -0.6, x=2800, y=9000), out,
                                     x=3000, y=9000), 1.0, x=3200, y=9000)
    spun = b.node("GeometryNodeRotateInstances", 3000, 9600)
    b.feed(spun.inputs["Instances"], copies.outputs["Instances"])
    b.feed(spun.inputs["Rotation"], b.combine(0.0, 0.0, turn, x=3200, y=9200))
    b.feed(spun.inputs["Pivot Point"], b.vmath("ADD", centre, b.node("GeometryNodeInputPosition", 2800, 8900).outputs[0],
                                               x=3000, y=8900))
    spun.inputs["Local Space"].default_value = False
    gathering = b.boolean("AND", b.compare("GREATER_THAN", p, 0.0, x=3000, y=8700),
                          b.compare("LESS_THAN", p, 1.0, x=3000, y=8550), x=3200, y=8650)
    ghosts = b.switch("GEOMETRY", gathering, None, spun.outputs["Instances"], x=3400, y=9600)
    suit = b.switch("GEOMETRY", gi.outputs["Ghosts"], suit, b.join([real, ghosts], x=3600, y=9000), x=6200, y=1000)

    # --- Evolution flash: no front; the outfits show in turn (the old one by the Base group), faster and faster,
    # glowing brighter until they are pure light, and from the moment the new one stays.
    evolve_new, evolve_glow = _evolve(b, p, 4000, 10600)
    evolved = b.switch("GEOMETRY", evolve_new, None, b.store(geo, ATTR_EDGE, evolve_glow, x=5800, y=10400),
                       x=6000, y=10400)
    suit = b.switch("GEOMETRY", gi.outputs["Evolve"], suit, evolved, x=6250, y=1000)
    # --- Smoke puff: the new outfit is there at the moment, hidden by a puff of smoke.
    suit = b.switch("GEOMETRY", gi.outputs["Poof"], suit, real, x=6300, y=1000)
    # --- Swap (all at once at the moment) and the lotus (inside the shut bud): the same.
    suit = b.switch("GEOMETRY", b.boolean("OR", gi.outputs["Swap"], gi.outputs["Lotus"], x=6200, y=1300), suit, real,
                    x=6325, y=1000)
    smoke = _smoke(b, gi, geo, p, me, 4000, 11400)
    # --- Rising from the shadow: the new outfit stands up out of the black shadow the old one sank into.
    risen = b.delete(geo, b.compare("LESS_THAN", p, 0.5, x=4000, y=12600), "POINT", x=4200, y=12800)
    risen = _shadow_place(b, gi, me, risen, geo, anchor, _shadow_amount(b, geo, anchor, p, True, 4000, 13200), 4400,
                          12800)
    suit = b.switch("GEOMETRY", gi.outputs["Shadow"], suit, risen, x=6350, y=1000)
    # --- Transporter beam: the new outfit shimmers in a few faces at a time, glowing, inside a column of light.
    beam_shown, beam_glow = _beam_faces(b, gi, anchor, p, 4000, 22000)[1]
    beamed = b.delete(geo, b.boolean("NOT", beam_shown, x=6400, y=22000), "FACE", x=6600, y=22000)
    beamed = b.store(beamed, ATTR_EDGE, b.math("MAXIMUM", b.on_domain(beam_glow, "FACE", x=6600, y=21800), flash,
                                               x=6800, y=21800), x=6800, y=22000)
    suit = b.switch("GEOMETRY", gi.outputs["Beam"], suit, beamed, x=6375, y=1000)
    column = _beam_column(b, gi, geo, p, me, 4000, 24000)

    # --- Scales (Mystique): the new outfit turns in scale by scale, each scale the second half of its turn (the old
    # outfit shows the first): edge-on to flat, glinting as it goes.
    scales = _flip(b, gi, field_group, geo, d, field["Path"], radius, None, True, gi.outputs["Edge Glow"], -1000,
                   12000)
    scales = b.store(scales, ATTR_EDGE, b.math("MAXIMUM", b.named_attribute(ATTR_EDGE, "FLOAT", x=6200, y=11700)[0],
                                               flash, x=6400, y=11700), x=6600, y=12000)
    scales = b.switch("GEOMETRY", gi.outputs["Undersuit"], scales, b.store(scales, ATTR_LAYER, under, x=6800,
                                                                          y=12200), x=7000, y=12000)
    scales = mark_cut(scales, 7200, 12000)
    suit = b.switch("GEOMETRY", gi.outputs["Scales"], suit, scales, x=6400, y=1000)

    # --- Armour plates (Mark 50): behind the edge the suit's plates rise and settle back one by one.
    plated = _flip(b, gi, field_group, suit, d, field["Path"], radius, None, True, gi.outputs["Edge Glow"], 6000,
                   16000, plates=True)
    suit = b.switch("GEOMETRY", gi.outputs["Plates"], suit, plated, x=6450, y=1000)

    # --- Line art / ink wash: the new outfit shows as a drawing (with line art also ahead of the edge) and takes on its
    # colours behind the edge like watercolour (materials draw it from disperse_paint: 1 a drawing .. 0 its colours),
    # outlined by an inverted hull (a copy pushed out along the normals, faces flipped; its material hides front faces)
    # that thins out as the colour comes.
    paint = b.map_range(d, b.math("SUBTRACT", radius, gi.outputs["Paint Width"], x=6400, y=13800), radius, x=6600,
                        y=13800)
    painted = b.store(suit, ATTR_PAINT, paint, x=6800, y=13600)
    hull = b.separate(painted, b.compare("GREATER_THAN", b.on_domain(paint, "FACE", x=6800, y=14000), 0.02, x=7000,
                                         y=14000), "FACE", x=7000, y=13800)[0]
    hull = b.set_position(hull, b.vmath("SCALE", normal, scale=b.math(
        "MULTIPLY", gi.outputs["Outline Width"], b.math("MULTIPLY", paint, 3.0, x=7000, y=14400, clamp=True), x=7200,
        y=14300), x=7400, y=14200), x=7600, y=13800)
    flip = b.node("GeometryNodeFlipFaces", 7800, 13800)
    b.feed(flip.inputs["Mesh"], hull)
    inked = b.node("GeometryNodeSetMaterial", 8000, 13800)
    b.feed(inked.inputs["Geometry"], flip.outputs["Mesh"])
    b.feed(inked.inputs["Material"], gi.outputs["Outline Material"])
    # (drawings only: the digital rain has no outline)
    drawn = b.boolean("AND", b.compare("GREATER_THAN", gi.outputs["Outline Width"], 0.0, x=8000, y=14100),
                      b.compare("LESS_THAN", gi.outputs["Paint Style"], 2.5, x=8000, y=14250), x=8200, y=14150)
    outlined = b.switch("GEOMETRY", drawn, painted, b.join([painted, inked.outputs["Geometry"]], x=8200, y=13700),
                        x=8400, y=13600)
    suit = b.switch("GEOMETRY", b.compare("GREATER_THAN", gi.outputs["Paint Style"], 0.5, x=6400, y=1300), suit,
                    outlined, x=6500, y=1000)
    # The digital rain scrolls with the frame (the material reads it).
    suit = b.switch("GEOMETRY", gi.outputs["Code"], suit, b.store(suit, ATTR_FRAME, b.node(
        "GeometryNodeInputSceneTime", 6400, 1500).outputs["Frame"], x=6500, y=1500), x=6550, y=1000)

    # --- Wire layer: keep a band around the boundary.
    t = b.math("SUBTRACT", d, radius, x=-700, y=-500)
    too_deep = b.compare("LESS_THAN", t, b.math("MULTIPLY", gi.outputs["Wire Inner"], -1.0, x=-700, y=-700),
                         x=-450, y=-550)
    too_far = b.compare("GREATER_THAN", t, gi.outputs["Wire Outer"], x=-450, y=-750)
    band = b.delete(geo, b.boolean("OR", too_deep, too_far, x=-250, y=-600), "FACE", x=-50, y=-450)
    tri = b.node("GeometryNodeTriangulate", 150, -350)
    b.feed(tri.inputs["Mesh"], band)
    dual = b.node("GeometryNodeDualMesh", 350, -350)
    b.feed(dual.inputs["Mesh"], tri.outputs["Mesh"])
    band = b.switch("GEOMETRY", gi.outputs["Hex Wire"], band, dual.outputs["Dual Mesh"], x=550, y=-450)

    # Thickest at the boundary, tapering to both ends of the band.
    bump_in = b.map_range(t, b.math("MULTIPLY", gi.outputs["Wire Inner"], -1.0, x=150, y=-900), 0.0,
                          x=350, y=-850)
    bump_out = b.map_range(t, 0.0, gi.outputs["Wire Outer"], 1.0, 0.0, x=350, y=-1100)
    bump = b.math("MINIMUM", bump_in, bump_out, x=550, y=-950)
    # Ride on top of the suit lip, then fall back onto the old outfit ahead of it.
    flare = b.math("MINIMUM", grad, bump_out, x=550, y=-1150)
    lift = b.math("MULTIPLY_ADD", flare, gi.outputs["Edge Push"], gi.outputs["Wire Lift"], x=750, y=-1100)
    band = b.set_position(band, b.vmath("SCALE", normal, scale=lift, x=950, y=-1000), x=950, y=-450)

    curve = b.node("GeometryNodeMeshToCurve", 1150, -450)
    b.feed(curve.inputs["Mesh"], band)
    radius_node = b.node("GeometryNodeSetCurveRadius", 1350, -450)
    b.feed(radius_node.inputs["Curve"], curve.outputs["Curve"])
    # On a beat the wires swell and flare.
    b.feed(radius_node.inputs["Radius"], b.math("MULTIPLY", bump, b.math("MULTIPLY_ADD", beat, 0.6, 1.0, x=1150,
                                                                         y=-650), x=1350, y=-650))
    curve_out = b.store(radius_node.outputs["Curve"], ATTR_EDGE,
                        b.math("MULTIPLY", bump, b.math("MULTIPLY_ADD", beat, 0.5, 1.0, x=1350, y=-800),
                               x=1550, y=-800), x=1550, y=-450)
    profile = b.node("GeometryNodeCurvePrimitiveCircle", 1550, -750, mode="RADIUS")
    b.feed(profile.inputs["Resolution"], gi.outputs["Wire Resolution"])
    b.feed(profile.inputs["Radius"], gi.outputs["Wire Radius"])
    tube = b.curve_to_mesh(curve_out, profile.outputs["Curve"], x=1750, y=-450)
    mat = b.node("GeometryNodeSetMaterial", 1950, -450)
    b.feed(mat.inputs["Geometry"], tube)
    b.feed(mat.inputs["Material"], gi.outputs["Wire Material"])
    timeline = b.boolean("OR", b.boolean("OR", gi.outputs["Evolve"], gi.outputs["Poof"], x=1150, y=100),
                         b.boolean("OR", gi.outputs["Shadow"], gi.outputs["Beam"], x=1150, y=250), x=1350, y=100)
    timeline = b.boolean("OR", timeline, b.boolean("OR", gi.outputs["Swap"], gi.outputs["Lotus"], x=1150, y=400),
                         x=1400, y=250)
    wire_on = b.boolean("AND", gi.outputs["Wire"], b.boolean("NOT", timeline, x=1550, y=100), x=1750, y=150)
    wire_on = b.boolean("AND", wire_on, b.boolean("NOT", b.boolean("OR", gi.outputs["Clamp"],
                                                                                gi.outputs["Ghosts"], x=1550, y=-50),
                                                             x=1750, y=-50), x=1950, y=-50)
    wire = b.switch("GEOMETRY", wire_on, None, mat.outputs["Geometry"], x=1950, y=-150)

    # --- Sparkle burst with the finale: stars shoot out of the whole outfit (or where the light sweep passes),
    # twinkle and fade. The switch condition is a single value, so none of this is evaluated outside the finale.
    window = b.boolean("AND", b.compare("GREATER_THAN", finale_t, 0.0, x=900, y=-2450),
                       b.compare("LESS_THAN", finale_t, 1.0, x=900, y=-2600), x=1100, y=-2500)
    bursting = b.boolean("AND", b.boolean("AND", gi.outputs["Finale"], gi.outputs["Sparkles"], x=1100, y=-2350),
                         window, x=1300, y=-2400)
    chance = b.math("MULTIPLY", b.node("GeometryNodeInputMeshFaceArea", 900, -2800).outputs[0],
                    gi.outputs["Sparkle Density"], x=1100, y=-2800)
    face_seed = b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=900, y=-3000)
    lottery = b.white_noise(b.vmath("ADD", b.vmath("SCALE", face_seed, scale=2.93, x=1100, y=-3000),
                                    (5.0, 11.0, 23.0), x=1300, y=-3000), x=1500, y=-3000)[0]
    src = b.store(geo, ATTR_PICK, b.compare("LESS_THAN", lottery, chance, x=1500, y=-2850), "BOOLEAN", "FACE",
                  x=1100, y=-2600)
    # Leave behind: a star bursts out of where the body was when it was born (recorded per vertex, launch.py), along
    # the normal it had there; the faces are picked before they move, so the same stars come out.
    star_launch, has_star_launch = _recorded(b, space, has_space, ATTR_LAUNCH, 300, -5600)
    src = b.switch("GEOMETRY", gi.outputs["Leave Behind"], src,
                   b.set_position(src, selection=has_star_launch, position=star_launch, x=1200, y=-2450),
                   x=1300, y=-2550)
    src = b.store(src, ATTR_NORMAL, normal, "FLOAT_VECTOR", "FACE", x=1500, y=-2600)
    to_points = b.node("GeometryNodeMeshToPoints", 1700, -2700, mode="FACES")
    b.feed(to_points.inputs["Mesh"], src)
    b.feed(to_points.inputs["Selection"], b.named_attribute(ATTR_PICK, "BOOLEAN", x=1500, y=-3150)[0])
    # Each star's own time: all of them start with the flash; with the sweep a star starts when the light
    # reaches it and lives for the rest of the finale.
    birth = b.math("MULTIPLY", b.math("DIVIDE", field["Path"], sweep_span, x=1700, y=-2400, clamp=True), SWEEP_SHARE,
                   x=1900, y=-2400)
    birth = b.switch("FLOAT", gi.outputs["Finale Sweep"], 0.0, birth, x=2100, y=-2400)
    life = b.switch("FLOAT", gi.outputs["Finale Sweep"], 1.0, 1.0 - SWEEP_SHARE, x=2100, y=-2550)
    star_t = b.math("DIVIDE", b.math("SUBTRACT", finale_t, birth, x=2300, y=-2400), life, x=2500, y=-2450)
    unborn = b.boolean("OR", b.compare("LESS_EQUAL", star_t, 0.0, x=2700, y=-2350),
                       b.compare("GREATER_EQUAL", star_t, 1.0, x=2700, y=-2500), x=2900, y=-2400)
    born = b.delete(to_points.outputs["Points"], unborn, "POINT", x=2000, y=-2700)
    burst_t = b.math("MULTIPLY", star_t, 1.0, x=2700, y=-2650, clamp=True)
    # On the points: rest position and the stored normal came along from the faces.
    point_normal = b.named_attribute(ATTR_NORMAL, "FLOAT_VECTOR", x=1700, y=-3200)[0]
    srnd, srnd_color = b.white_noise(b.vmath("SCALE", anchor, scale=4.17, x=1700, y=-3400), x=1900, y=-3400)
    spread = b.vmath("SCALE", b.vmath("SUBTRACT", srnd_color, (0.5, 0.5, 0.5), x=2100, y=-3400), scale=1.4,
                     x=2300, y=-3400)
    # spread and lift are world directions (a turning model does not swing the stars round)
    lift = _unrotate(b, me, b.vmath("ADD", spread, (0.0, 0.0, 0.35), x=2500, y=-3450), 2700, -3450)
    heading = b.vmath("NORMALIZE", b.vmath("ADD", point_normal, lift, x=2700, y=-3300), x=2900, y=-3300)
    shot = b.math("SUBTRACT", 1.0, b.math("POWER", b.math("SUBTRACT", 1.0, burst_t, x=2100, y=-3600), 3.0,
                                          x=2300, y=-3600), x=2500, y=-3600)
    travel = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Sparkle Distance"], shot, x=2700, y=-3600),
                    b.math("ADD", srnd, 0.5, x=2700, y=-3750), x=2900, y=-3650)
    pts = b.set_position(born, b.vmath("SCALE", heading, scale=travel, x=3100, y=-3400), x=3300, y=-2700)
    stars = _remove_attributes(b, pts, (ATTR_NORMAL, ATTR_PICK), 3500, -2700)
    # Stars face the front (MMD models and cameras look along Y; the world's, also when the model turns), each spun on
    # its own.
    cx, cy, _cz = b.split_xyz(srnd_color, x=2900, y=-3900)
    rotation = b.combine(b.math("MULTIPLY_ADD", cx, 0.6, math.pi / 2 - 0.3, x=3100, y=-3850),
                         b.math("MULTIPLY_ADD", srnd, 2.0 * math.pi, b.math("MULTIPLY", burst_t, 3.0, x=2900, y=-4100),
                                x=3100, y=-4000),
                         b.math("MULTIPLY_ADD", cy, 0.6, -0.3, x=3100, y=-4150), x=3300, y=-3950)
    frame = b.node("GeometryNodeInputSceneTime", 2900, -4300).outputs["Frame"]
    phase = b.math("MULTIPLY_ADD", frame, 1.1, b.math("MULTIPLY", srnd, 2.0 * math.pi, x=2900, y=-4450),
                   x=3100, y=-4350)
    twinkle = b.math("MULTIPLY_ADD", b.math("SINE", phase, x=3300, y=-4350), 0.3, 0.7, x=3500, y=-4350)
    grow = b.math("MULTIPLY", b.map_range(burst_t, 0.0, 0.06, x=3300, y=-4550),
                  b.math("POWER", b.math("SUBTRACT", 1.0, burst_t, x=3300, y=-4750), 1.5, x=3500, y=-4750),
                  x=3700, y=-4600)
    size = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Sparkle Size"], grow, x=3700, y=-4400), twinkle,
                  x=3900, y=-4400)
    size = b.math("MULTIPLY", size, b.math("MULTIPLY_ADD", srnd, 0.8, 0.6, x=3900, y=-4600), x=4100, y=-4450)
    size = b.math("MULTIPLY", size, b.math("MULTIPLY_ADD", beat, 0.5, 1.0, x=4100, y=-4650), x=4300, y=-4500)
    info = b.node("GeometryNodeObjectInfo", 3500, -3000, transform_space="ORIGINAL")
    b.feed(info.inputs["Object"], gi.outputs["Sparkle Object"])
    on_points = b.node("GeometryNodeInstanceOnPoints", 3800, -2700)
    b.feed(on_points.inputs["Points"], stars)
    b.feed(on_points.inputs["Instance"], info.outputs["Geometry"])
    b.feed(on_points.inputs["Rotation"], rotation)
    b.feed(on_points.inputs["Scale"], size)
    sparkles = b.switch("GEOMETRY", bursting, None, _world_instances(b, on_points.outputs["Instances"], me, 4000, -2700),
                        x=4900, y=-2500)

    # Symbiote: with no old outfit the tendrils run over the new one (the skeleton is bound to its original vertices).
    aged = b.store(gi.outputs["Geometry"], ATTR_AGE, b.math("SUBTRACT", radius, d, x=1300, y=-4300), x=1500, y=-4200)
    venom = _venom(b, gi, venom_group, aged, 1700, -4200)
    # Lightning: arcs crackling along the edge, the strike at the start.
    arcs = _arcs(b, gi, geo, d, radius, beat, 4000, 27000)
    strike = _strike(b, gi, radius, me, 4000, 30000)
    # 1.10: the lotus round the body, flames on the new outfit, the shockwave on the floor, the soul rings (the lotus,
    # the shockwave and the rings are sized by the whole model at rest, its locked parts too: head to toe)
    lotus = _lotus(b, gi, gi.outputs["Geometry"], p, beat, 4000, 34000)
    flames = _flames(b, gi, suit, d, radius, me, 4000, 42000)
    shock = _shockwave(b, gi, gi.outputs["Geometry"], radius, 4000, 46000)
    soul = _soul_rings(b, gi, gi.outputs["Geometry"], radius, beat, 4000, 50000)

    join = b.node("GeometryNodeJoinGeometry", 2000, 250)
    for part in (wire, suit, sparkles, venom, frames, smoke, column, arcs, strike, lotus, flames, shock, soul):
        b.feed(join.inputs["Geometry"], part)
    b.feed(go.inputs["Geometry"], join.outputs["Geometry"])
    return ng


def _evolve(b, p, x, y):
    """Evolution flash, p running 0 -> 1 up to the moment: (whether the new outfit shows, the glow stored as
    glow^(1/8)). After glowing up the outfits show in turn, faster and faster (eleven times), brighter and brighter
    until both are pure light; from the moment the new one stays and its glow fades. The glow stays soft while the
    first turns come, so that the outfits' own looks flicker, and only near the end becomes pure light."""
    u = b.map_range(p, 0.05, 1.0, x=x, y=y)
    phase = b.math("MULTIPLY_ADD", u, 4.0, b.math("MULTIPLY", b.math("POWER", u, 3.0, x=x, y=y - 300), 7.0, x=x + 200,
                                                  y=y - 300), x=x + 400, y=y - 150)
    flips = b.math("FLOOR", phase, x=x + 600, y=y - 150)
    odd = b.compare("GREATER_THAN", b.math("FRACT", b.math("MULTIPLY", flips, 0.5, x=x + 800, y=y - 150), x=x + 1000,
                                           y=y - 150), 0.25, x=x + 1200, y=y - 150)
    turn = b.boolean("AND", b.compare("GREATER_THAN", u, 0.0, x=x + 1000, y=y), odd, x=x + 1400, y=y)
    new = b.boolean("OR", b.compare("GREATER_EQUAL", p, 1.0, x=x + 1400, y=y + 150), turn, x=x + 1600, y=y)
    rising = b.math("MULTIPLY_ADD", b.math("POWER", b.map_range(p, 0.1, 1.0, x=x, y=y - 500, smooth=True), 3.0,
                                           x=x + 200, y=y - 500), 0.97, 0.03, x=x + 400, y=y - 500)
    glow = b.math("MINIMUM", b.math("MINIMUM", rising, b.map_range(p, 0.0, 0.12, x=x + 400, y=y - 700, smooth=True),
                                    x=x + 600, y=y - 600),
                  b.map_range(p, 1.0, 1.15, 1.0, 0.0, x=x + 600, y=y - 800, smooth=True), x=x + 800, y=y - 650)
    return new, b.math("POWER", glow, 0.125, x=x + 1000, y=y - 650)


def _shadow_amount(b, geometry, anchor, p, new, x, y):
    """Rising from the shadow: how far a vertex is in its shadow (0 standing .. 1 flat on the floor). The old outfit
    sinks in over the first half of the timeline, the head first; the new one stands up over the second half, the feet
    first."""
    rest_z = b.split_xyz(anchor, x=x, y=y)[2]
    stat = b.node("GeometryNodeAttributeStatistic", x, y - 300, data_type="FLOAT", domain="POINT")
    b.feed(stat.inputs["Geometry"], geometry)
    b.feed(_enabled(stat.inputs, "Attribute")[0], rest_z)
    h = b.math("DIVIDE", b.math("SUBTRACT", rest_z, stat.outputs["Min"], x=x + 200, y=y),
               b.math("MAXIMUM", stat.outputs["Range"], 1e-4, x=x + 200, y=y - 150), x=x + 400, y=y)
    if new:
        start = b.math("MULTIPLY_ADD", h, 0.3, 0.5, x=x + 600, y=y)
    else:
        start = b.math("MULTIPLY", b.math("SUBTRACT", 1.0, h, x=x + 600, y=y - 150), 0.3, x=x + 800, y=y - 150)
    t_ = b.map_range(b.math("DIVIDE", b.math("SUBTRACT", p, start, x=x + 1000, y=y), 0.2, x=x + 1200, y=y), 0.0, 1.0,
                     x=x + 1400, y=y, smooth=True)
    return b.math("SUBTRACT", 1.0, t_, x=x + 1600, y=y) if new else t_


def _shadow_place(b, gi, me, geometry, whole, anchor, amount, x, y):
    """`geometry` moved `amount` of the way into its shadow: each vertex slides along the light (Shadow Direction, in
    the world) down onto the floor (the lowest point of the whole outfit `whole` on the rest pose), and turns black
    (ATTR_SHADOW)."""
    rest_z = b.split_xyz(anchor, x=x, y=y)[2]
    stat = b.node("GeometryNodeAttributeStatistic", x, y - 300, data_type="FLOAT", domain="POINT")
    b.feed(stat.inputs["Geometry"], whole)
    b.feed(_enabled(stat.inputs, "Attribute")[0], rest_z)
    floor = b.math("MULTIPLY_ADD", stat.outputs["Range"], 0.0015, stat.outputs["Min"], x=x + 200, y=y - 300)
    light = b.vmath("NORMALIZE", _unrotate(b, me, gi.outputs["Shadow Direction"], x, y - 600), x=x + 200, y=y - 600)
    lx, ly, lz = b.split_xyz(light, x=x + 400, y=y - 600)
    lz = b.math("MINIMUM", lz, -0.05, x=x + 600, y=y - 700)
    position = b.node("GeometryNodeInputPosition", x, y - 900).outputs[0]
    px, py, pz = b.split_xyz(position, x=x + 200, y=y - 900)
    along = b.math("DIVIDE", b.math("SUBTRACT", floor, pz, x=x + 600, y=y - 900), lz, x=x + 800, y=y - 900)
    shadow = b.combine(b.math("MULTIPLY_ADD", lx, along, px, x=x + 1000, y=y - 800),
                       b.math("MULTIPLY_ADD", ly, along, py, x=x + 1000, y=y - 950), floor, x=x + 1200, y=y - 900)
    spot = b.vmath("ADD", position, b.vmath("SCALE", b.vmath("SUBTRACT", shadow, position, x=x + 1400, y=y - 900),
                                            scale=amount, x=x + 1600, y=y - 900), x=x + 1800, y=y - 900)
    moved = b.set_position(geometry, position=spot, x=x + 2000, y=y)
    moved = b.store(moved, ATTR_SHADOW, amount, x=x + 2200, y=y)
    sliding = b.math("POWER", b.math("SINE", b.math("MULTIPLY", amount, math.pi, x=x + 2000, y=y - 1200), x=x + 2200,
                                     y=y - 1200), 0.25, x=x + 2400, y=y - 1200)
    return b.store(moved, ATTR_EDGE, b.math("MAXIMUM", sliding, b.named_attribute(ATTR_EDGE, "FLOAT", x=x + 2200,
                                                                                   y=y - 1400)[0], x=x + 2600,
                                           y=y - 1300), x=x + 2400, y=y)


def _smoke(b, gi, geometry, p, me, x, y):
    """Smoke puff (the ninja transformation): balls of white smoke burst out of the body from the feet up, each by its
    height on the rest pose, so the cloud has wrapped the body by the moment, when the outfits swap; then it drifts up
    and spreads out, fading away (the material reads ATTR_SMOKE). Each puff's start and size come from the rest
    position (an attribute the points carry along), so they stay put while the body dances."""
    spread = b.node("GeometryNodeDistributePointsOnFaces", x, y, distribute_method="RANDOM")
    b.feed(spread.inputs["Mesh"], geometry)
    b.feed(spread.inputs["Density"], gi.outputs["Smoke Density"])
    spread.inputs["Seed"].default_value = 7
    size = gi.outputs["Smoke Size"]
    up = _unrotate(b, me, (0.0, 0.0, 1.0), x + 400, y - 800)
    box = b.node("GeometryNodeBoundBox", x, y + 300)
    b.feed(box.inputs["Geometry"], geometry)
    middle = b.vmath("SCALE", b.vmath("ADD", box.outputs["Min"], box.outputs["Max"], x=x + 200, y=y + 300), scale=0.5,
                     x=x + 400, y=y + 300)
    here = b.node("GeometryNodeInputPosition", x + 400, y + 150).outputs[0]
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=x, y=y - 1100)
    still = b.switch("VECTOR", has_rest, here, rest, x=x + 200, y=y - 1100)
    rnd = b.white_noise(b.vmath("SCALE", still, scale=3.1, x=x + 400, y=y - 1250), x=x + 600, y=y - 1250)[0]
    late = b.white_noise(b.vmath("SCALE", still, scale=7.7, x=x + 400, y=y - 1400), x=x + 600, y=y - 1400)[0]
    height = b.math("DIVIDE", b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", still, box.outputs["Min"], x=x + 400,
                                                             y=y - 1550), up, x=x + 600, y=y - 1550),
                    b.math("MAXIMUM", b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", box.outputs["Max"], box.outputs["Min"],
                                                                     x=x + 400, y=y - 1700), up, x=x + 600,
                                              y=y - 1700), 1e-4, x=x + 800, y=y - 1700), x=x + 1000, y=y - 1600,
                    clamp=True)
    birth = b.math("MULTIPLY_ADD", height, 0.5, b.math("MULTIPLY_ADD", late, 0.15, 0.1, x=x + 1000, y=y - 1400),
                   x=x + 1200, y=y - 1500)
    grow = b.map_range(p, birth, b.math("ADD", birth, 0.22, x=x + 1400, y=y - 1550), x=x + 1600, y=y - 1450,
                       smooth=True)
    fade = b.map_range(p, 1.02, 1.32, x=x + 400, y=y - 450, smooth=True)
    rise = b.map_range(p, 0.99, 1.32, x=x + 400, y=y - 600, smooth=True)
    away = b.vmath("SCALE", b.vmath("SUBTRACT", here, middle, x=x + 600, y=y + 200),
                   scale=b.math("MULTIPLY_ADD", fade, 0.3, b.math("MULTIPLY", grow, 0.35, x=x + 400, y=y + 50),
                                x=x + 600, y=y + 50), x=x + 800, y=y + 150)
    out = b.vmath("ADD", b.vmath("SCALE", spread.outputs["Normal"], scale=b.math(
        "MULTIPLY", b.math("MULTIPLY", size, 1.1, x=x + 600, y=y - 300), grow, x=x + 800, y=y - 300), x=x + 1000,
        y=y - 300), b.vmath("SCALE", up, scale=b.math("MULTIPLY", size, rise, x=x + 800, y=y - 600), x=x + 1000,
                            y=y - 600), x=x + 1200, y=y - 450)
    out = b.vmath("ADD", out, away, x=x + 1300, y=y - 300)
    puffs = b.set_position(spread.outputs["Points"], out, x=x + 1400, y=y)
    scale = b.math("MULTIPLY", b.math("MULTIPLY", size, b.math("MULTIPLY_ADD", rnd, 1.0, 0.6, x=x + 1600, y=y - 900),
                                      x=x + 1800, y=y - 800),
                   b.math("MULTIPLY", grow, b.math("MULTIPLY_ADD", fade, 0.5, 1.0, x=x + 1400, y=y - 650), x=x + 1600,
                          y=y - 600), x=x + 2000, y=y - 700)
    ball = b.node("GeometryNodeMeshIcoSphere", x + 1400, y + 300)
    ball.inputs["Radius"].default_value = 1.0
    ball.inputs["Subdivisions"].default_value = 2
    smooth = b.node("GeometryNodeSetShadeSmooth", x + 1600, y + 300)
    b.feed(smooth.inputs[0], ball.outputs["Mesh"])
    material = b.node("GeometryNodeSetMaterial", x + 1800, y + 300)
    b.feed(material.inputs["Geometry"], smooth.outputs[0])
    b.feed(material.inputs["Material"], gi.outputs["Smoke Material"])
    cloud = b.node("GeometryNodeInstanceOnPoints", x + 2200, y)
    b.feed(cloud.inputs["Points"], puffs)
    b.feed(cloud.inputs["Instance"], material.outputs["Geometry"])
    b.feed(cloud.inputs["Scale"], scale)
    puffing = b.boolean("AND", gi.outputs["Poof"], b.boolean("AND", b.compare("GREATER_THAN", p, 0.1, x=x + 2000,
                                                                              y=y + 300),
                                                             b.compare("LESS_THAN", p, 1.32, x=x + 2000, y=y + 150),
                                                             x=x + 2200, y=y + 250), x=x + 2400, y=y + 250)
    clearing = b.store(cloud.outputs["Instances"], ATTR_SMOKE, fade, domain="INSTANCE", x=x + 2400, y=y)
    return b.switch("GEOMETRY", puffing, None, clearing, x=x + 2600, y=y)


def _beam_faces(b, gi, anchor, p, x, y):
    """Transporter beam (Star Trek), face fields ((old shown, old glow), (new shown, new glow)), p running 0 -> 1 up
    to the moment: a flickering noise on each face (its rest position, changing with the frame) against a threshold
    that sweeps through, so an outfit shimmers away or in a few faces at a time. The old outfit goes over 0.08 .. 0.5
    of the timeline, the new one comes over 0.45 .. 0.95. Faces about to go or just come glow (stored as
    glow^(1/8))."""
    face = b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=x, y=y)
    frame = b.node("GeometryNodeInputSceneTime", x, y - 200).outputs["Frame"]
    shimmer = b.node("ShaderNodeTexNoise", x + 200, y, noise_dimensions="4D")
    b.feed(shimmer.inputs["Vector"], face)
    b.feed(shimmer.inputs["W"], b.math("MULTIPLY", frame, 0.07, x=x + 200, y=y - 300))
    b.feed(shimmer.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Noise Scale"], 3.0, x=x, y=y - 400))
    shimmer.inputs["Detail"].default_value = 2.0
    # the noise sits around 0.5: spread it out, half of it each face's own
    spread = b.math("MULTIPLY_ADD", shimmer.outputs[0], 2.2, -0.6, x=x + 400, y=y, clamp=True)
    own = b.white_noise(b.vmath("SCALE", face, scale=11.3, x=x + 200, y=y - 550), x=x + 400, y=y - 550)[0]
    n = b.math("MULTIPLY_ADD", spread, 0.55, b.math("MULTIPLY", own, 0.45, x=x + 600, y=y - 550), x=x + 800, y=y)
    sides = []
    for i, (lo, hi, gone_at, there) in enumerate(((0.08, 0.5, -0.05, 1.05), (0.45, 0.95, 1.05, -0.05))):
        yy = y - 800 - 700 * i
        threshold = b.map_range(p, lo, hi, gone_at, there, x=x + 600, y=yy, smooth=True)
        shown = b.compare("GREATER_THAN", n, threshold, x=x + 1000, y=yy)
        edge = b.math("SUBTRACT", 1.0, b.math("DIVIDE", b.math("ABSOLUTE", b.math("SUBTRACT", n, threshold, x=x + 800,
                                                                               y=yy - 150), x=x + 1000, y=yy - 150),
                                                0.07, x=x + 1200, y=yy - 150), x=x + 1400, y=yy - 150, clamp=True)
        # (no glow over the rest of it: on dark clothes even a faint one washes them out)
        glow = b.math("MULTIPLY", edge, 0.9, x=x + 1600, y=yy - 150)
        sides.append((shown, b.math("POWER", glow, 0.125, x=x + 2000, y=yy - 250)))
    return sides


def _beam_column(b, gi, geometry, p, me, x, y):
    """Transporter beam: a column of light round the body (from its rest pose, so it stays put while the body moves)
    with sparkles drifting up and down in it (Star Object, in the particle colour), there from just before the old
    outfit starts to shimmer away until a little after the new one is in. The column carries ATTR_BEAM (round it and
    up it), ATTR_FRAME and how bright it is (ATTR_EDGE) for its material."""
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=x, y=y)
    still = b.switch("VECTOR", has_rest, b.node("GeometryNodeInputPosition", x, y - 150).outputs[0], rest, x=x + 200,
                     y=y)
    stat = b.node("GeometryNodeAttributeStatistic", x + 400, y, data_type="FLOAT_VECTOR", domain="POINT")
    b.feed(stat.inputs["Geometry"], geometry)
    b.feed(_enabled(stat.inputs, "Attribute")[0], still)
    lo, hi = _enabled(stat.outputs, "Min")[0], _enabled(stat.outputs, "Max")[0]
    lo_x, lo_y, lo_z = b.split_xyz(lo, x=x + 600, y=y)
    hi_x, hi_y, hi_z = b.split_xyz(hi, x=x + 600, y=y - 200)
    # round the body, but no wider than a quarter of its height (arms held out reach through it)
    tall = b.math("MULTIPLY", b.math("SUBTRACT", hi_z, lo_z, x=x + 800, y=y - 300), 1.08, x=x + 1000, y=y - 300)
    radius = b.math("MINIMUM", b.math("MULTIPLY", b.math("MAXIMUM", b.math("SUBTRACT", hi_x, lo_x, x=x + 800, y=y),
                                                         b.math("SUBTRACT", hi_y, lo_y, x=x + 800, y=y - 150),
                                                         x=x + 1000, y=y), 0.62, x=x + 1100, y=y),
                    b.math("MULTIPLY", tall, 0.22, x=x + 1100, y=y - 150), x=x + 1200, y=y)
    bottom = b.math("MULTIPLY_ADD", tall, -0.02, lo_z, x=x + 1200, y=y - 300)
    mid_x = b.math("MULTIPLY", b.math("ADD", lo_x, hi_x, x=x + 800, y=y - 450), 0.5, x=x + 1000, y=y - 450)
    mid_y = b.math("MULTIPLY", b.math("ADD", lo_y, hi_y, x=x + 800, y=y - 600), 0.5, x=x + 1000, y=y - 600)
    # fades in as the outfit starts to shimmer, out after the new one is there
    vis = b.math("MINIMUM", b.map_range(p, 0.0, 0.08, x=x + 1200, y=y - 750, smooth=True),
                 b.map_range(p, 1.0, 1.15, 1.0, 0.0, x=x + 1200, y=y - 900, smooth=True), x=x + 1400, y=y - 800)
    frame = b.node("GeometryNodeInputSceneTime", x + 1200, y - 1050).outputs["Frame"]

    tube = b.node("GeometryNodeMeshCylinder", x + 1400, y, fill_type="NONE")
    tube.inputs["Vertices"].default_value = 48
    tube.inputs["Side Segments"].default_value = 1
    b.feed(tube.inputs["Radius"], radius)
    b.feed(tube.inputs["Depth"], tall)
    centre = b.combine(mid_x, mid_y, b.math("MULTIPLY_ADD", tall, 0.5, bottom, x=x + 1400, y=y - 300), x=x + 1600,
                       y=y - 300)
    column = b.set_position(tube.outputs["Mesh"], centre, x=x + 1600, y=y)
    cx, cy, cz = b.split_xyz(b.node("GeometryNodeInputPosition", x + 1600, y - 500).outputs[0], x=x + 1800, y=y - 500)
    across = b.combine(b.math("DIVIDE", b.math("SUBTRACT", cx, mid_x, x=x + 2000, y=y - 450), radius, x=x + 2200,
                              y=y - 450),
                       b.math("DIVIDE", b.math("SUBTRACT", cy, mid_y, x=x + 2000, y=y - 600), radius, x=x + 2200,
                              y=y - 600),
                       b.math("DIVIDE", b.math("SUBTRACT", cz, bottom, x=x + 2000, y=y - 750), tall, x=x + 2200,
                              y=y - 750), x=x + 2400, y=y - 600)
    column = b.store(column, ATTR_BEAM, across, "FLOAT_VECTOR", x=x + 1800, y=y)
    column = b.store(column, ATTR_FRAME, frame, x=x + 2000, y=y)
    column = b.store(column, ATTR_EDGE, vis, x=x + 2200, y=y)
    shaded = b.node("GeometryNodeSetMaterial", x + 2400, y)
    b.feed(shaded.inputs["Geometry"], column)
    b.feed(shaded.inputs["Material"], gi.outputs["Beam Material"])

    # sparkles inside it, each rising or falling at its own speed, wrapping round at the top / bottom
    dots = b.node("GeometryNodePoints", x + 1400, y - 1300)
    b.feed(dots.inputs["Count"], gi.outputs["Beam Count"])
    index = b.node("GeometryNodeInputIndex", x + 1000, y - 1500).outputs[0]
    rnd, rnd_color = b.white_noise(b.combine(index, 0.61, 0.23, x=x + 1200, y=y - 1500), x=x + 1400, y=y - 1500)
    r1, r2, r3 = b.split_xyz(rnd_color, x=x + 1600, y=y - 1500)
    angle = b.math("MULTIPLY", r1, 2.0 * math.pi, x=x + 1800, y=y - 1400)
    out = b.math("MULTIPLY", radius, b.math("MULTIPLY", b.math("SQRT", r2, x=x + 1800, y=y - 1550), 0.9, x=x + 2000,
                                            y=y - 1550), x=x + 2200, y=y - 1550)
    way = b.math("MULTIPLY_ADD", b.math("GREATER_THAN", r3, 0.5, x=x + 1800, y=y - 1700), 2.0, -1.0, x=x + 2000,
                 y=y - 1700)
    speed = b.math("MULTIPLY", way, b.math("MULTIPLY_ADD", rnd, 0.012, 0.004, x=x + 2000, y=y - 1850), x=x + 2200,
                   y=y - 1750)
    climb = b.math("FRACT", b.math("MULTIPLY_ADD", frame, speed, b.math("MULTIPLY", rnd, 7.13, x=x + 2200, y=y - 1950),
                                   x=x + 2400, y=y - 1850), x=x + 2600, y=y - 1850)
    spot = b.combine(b.math("MULTIPLY_ADD", b.math("COSINE", angle, x=x + 2000, y=y - 1300), out, mid_x, x=x + 2400,
                            y=y - 1300),
                     b.math("MULTIPLY_ADD", b.math("SINE", angle, x=x + 2000, y=y - 1450), out, mid_y, x=x + 2400,
                            y=y - 1450),
                     b.math("MULTIPLY_ADD", climb, tall, bottom, x=x + 2800, y=y - 1700), x=x + 3000, y=y - 1400)
    b.feed(dots.inputs["Position"], spot)
    twinkle = b.math("MULTIPLY_ADD", b.math("SINE", b.math("MULTIPLY_ADD", frame, 0.9, b.math(
        "MULTIPLY", rnd, 2.0 * math.pi, x=x + 2600, y=y - 2150), x=x + 2800, y=y - 2100), x=x + 3000, y=y - 2100),
                         0.4, 0.6, x=x + 3200, y=y - 2100)
    # (thinner near the top and the bottom, where the column fades)
    ends = b.math("MULTIPLY", b.map_range(climb, 0.0, 0.1, x=x + 3000, y=y - 1950),
                  b.map_range(climb, 0.85, 1.0, 1.0, 0.0, x=x + 3000, y=y - 2250), x=x + 3200, y=y - 2250)
    size = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Star Size"], b.math("MULTIPLY_ADD", r2, 0.5, 0.25,
                                                                                     x=x + 3200, y=y - 2400),
                                     x=x + 3400, y=y - 2350),
                  b.math("MULTIPLY", b.math("MULTIPLY", twinkle, vis, x=x + 3400, y=y - 2100), ends, x=x + 3600,
                         y=y - 2200), x=x + 3800, y=y - 2300)
    star = b.node("GeometryNodeObjectInfo", x + 3000, y - 900, transform_space="ORIGINAL")
    b.feed(star.inputs["Object"], gi.outputs["Star Object"])
    stars = b.node("GeometryNodeInstanceOnPoints", x + 3400, y - 1300)
    b.feed(stars.inputs["Points"], dots.outputs["Geometry"])
    b.feed(stars.inputs["Instance"], star.outputs["Geometry"])
    b.feed(stars.inputs["Rotation"], b.combine(math.pi / 2, b.math("MULTIPLY", r3, 2.0 * math.pi, x=x + 3200,
                                                                   y=y - 1100), 0.0, x=x + 3400, y=y - 1100))
    b.feed(stars.inputs["Scale"], size)
    sparkles = _world_instances(b, stars.outputs["Instances"], me, x + 3600, y - 1300)
    there = b.boolean("AND", b.boolean("AND", gi.outputs["Beam"], gi.outputs["Main"], x=x + 3800, y=y + 300),
                      b.boolean("AND", b.compare("GREATER_THAN", p, 0.0, x=x + 3800, y=y + 150),
                                b.compare("LESS_THAN", p, 1.15, x=x + 3800, y=y), x=x + 4000, y=y + 100),
                      x=x + 4200, y=y + 200)
    return b.switch("GEOMETRY", there, None, b.join([shaded.outputs["Geometry"], sparkles], x=x + 4200, y=y),
                    x=x + 4400, y=y)


def _arcs(b, gi, geometry, d, radius, beat, x, y):
    """Lightning: jagged arcs of electricity crackle along the edge, new ones every frame (Arc Density per area of
    the faces within Arc Reach of it, a new seed every frame). An arc lies along the edge, across the way the wave
    runs: the gradient of the distance `d`, estimated per vertex from its edges (the mean of (d2 - d1)(p2 - p1) /
    |p2 - p1|^2). It bows out of the surface and is broken into a zigzag: a big bend and small kinks, its ends on the
    surface. In the arc material; ATTR_EDGE carries how bright each arc is (flaring on a beat)."""
    reach = b.math("MAXIMUM", gi.outputs["Arc Reach"], 1e-4, x=x, y=y - 200)
    off = b.on_domain(b.math("ABSOLUTE", b.math("SUBTRACT", d, radius, x=x, y=y), x=x + 200, y=y), "FACE", x=x + 400,
                      y=y)
    band = b.separate(geometry, b.compare("LESS_THAN", off, reach, x=x + 600, y=y), "FACE", x=x + 800, y=y)[0]
    ends = b.node("GeometryNodeInputMeshEdgeVertices", x, y - 400)

    def d_at(index, yy):
        n = b.node("GeometryNodeFieldAtIndex", x + 200, yy, data_type="FLOAT", domain="POINT")
        b.feed(n.inputs["Index"], index)
        b.feed(_enabled(n.inputs, "Value")[0], d)
        return _enabled(n.outputs, "Value")[0]

    step = b.vmath("SUBTRACT", ends.outputs["Position 2"], ends.outputs["Position 1"], x=x + 200, y=y - 300)
    rise = b.math("SUBTRACT", d_at(ends.outputs["Vertex Index 2"], y - 500),
                  d_at(ends.outputs["Vertex Index 1"], y - 650), x=x + 400, y=y - 550)
    slope = b.vmath("SCALE", step, scale=b.math("DIVIDE", rise, b.math(
        "MAXIMUM", b.vmath("DOT_PRODUCT", step, step, x=x + 400, y=y - 750), 1e-12, x=x + 600, y=y - 750), x=x + 800,
        y=y - 650), x=x + 1000, y=y - 400)
    band = b.store(band, _ARC_DIR, b.on_domain(slope, "EDGE", "FLOAT_VECTOR", x=x + 1200, y=y - 400), "FLOAT_VECTOR",
                   x=x + 1000, y=y)
    frame = b.node("GeometryNodeInputSceneTime", x + 1000, y + 300).outputs["Frame"]
    spots = b.node("GeometryNodeDistributePointsOnFaces", x + 1200, y, distribute_method="RANDOM")
    b.feed(spots.inputs["Mesh"], band)
    b.feed(spots.inputs["Density"], gi.outputs["Arc Density"])
    b.feed(spots.inputs["Seed"], frame)
    normal = spots.outputs["Normal"]
    index = b.node("GeometryNodeInputIndex", x + 1200, y - 1000).outputs[0]
    rnd, rnd_color = b.white_noise(b.combine(index, frame, 0.37, x=x + 1400, y=y - 1000), x=x + 1600, y=y - 1000)
    twist = b.split_xyz(rnd_color, x=x + 1800, y=y - 1000)[0]
    across = b.vmath("CROSS_PRODUCT", normal, b.named_attribute(_ARC_DIR, "FLOAT_VECTOR", x=x + 1400, y=y - 700)[0],
                     x=x + 1600, y=y - 700)
    # (where the distance does not change along the surface any way will do)
    flat = b.compare("LESS_THAN", b.vmath("LENGTH", across, x=x + 1800, y=y - 800), 1e-9, x=x + 2000, y=y - 800)
    across = b.switch("VECTOR", flat, across, b.vmath("CROSS_PRODUCT", normal, (0.31, 0.53, 0.79), x=x + 1800,
                                                      y=y - 650), x=x + 2000, y=y - 700)
    # along the edge, give or take 25 degrees
    along = b.rotate(b.vmath("NORMALIZE", across, x=x + 2200, y=y - 700), (0.0, 0.0, 0.0), normal,
                     b.math("MULTIPLY_ADD", twist, 0.9, -0.45, x=x + 2000, y=y - 1000), x=x + 2400, y=y - 700)
    side = b.vmath("NORMALIZE", b.vmath("CROSS_PRODUCT", along, normal, x=x + 2600, y=y - 850), x=x + 2800, y=y - 850)
    length = b.math("MULTIPLY", gi.outputs["Arc Length"], b.math("ADD", rnd, 0.5, x=x + 1800, y=y - 1150), x=x + 2000,
                    y=y - 1150)
    spots_out = b.set_position(spots.outputs["Points"], b.vmath("SCALE", normal, scale=b.math(
        "MULTIPLY", gi.outputs["Arc Thickness"], 2.0, x=x + 1400, y=y + 200), x=x + 1600, y=y + 200), x=x + 1800, y=y)
    for name, value, kind in zip(_ARC_ATTRS, (normal, side, length, rnd),
                                 ("FLOAT_VECTOR", "FLOAT_VECTOR", "FLOAT", "FLOAT")):
        spots_out = b.store(spots_out, name, value, kind, x=x + 2000, y=y)
    first = b.node("FunctionNodeAlignEulerToVector", x + 2600, y - 400, axis="X")
    b.feed(first.inputs["Vector"], along)
    turned = b.node("FunctionNodeAlignEulerToVector", x + 2800, y - 400, axis="Z", pivot_axis="X")
    b.feed(turned.inputs["Rotation"], first.outputs[0])
    b.feed(turned.inputs["Vector"], normal)
    line = b.node("GeometryNodeCurvePrimitiveLine", x + 2400, y + 400)
    line.inputs["Start"].default_value = (-0.5, 0.0, 0.0)
    line.inputs["End"].default_value = (0.5, 0.0, 0.0)
    points = b.node("GeometryNodeResampleCurve", x + 2600, y + 400)
    b.feed(points.inputs["Curve"], line.outputs["Curve"])
    points.inputs["Count"].default_value = ARC_POINTS
    laid = b.node("GeometryNodeInstanceOnPoints", x + 3000, y)
    b.feed(laid.inputs["Points"], spots_out)
    b.feed(laid.inputs["Instance"], points.outputs["Curve"])
    b.feed(laid.inputs["Rotation"], turned.outputs[0])
    b.feed(laid.inputs["Scale"], b.named_attribute("mmdd_arc_len", "FLOAT", x=x + 2800, y=y - 200)[0])
    curves = b.node("GeometryNodeRealizeInstances", x + 3200, y)
    b.feed(curves.inputs["Geometry"], laid.outputs["Instances"])
    # each arc's own values, by the curve it is (the n-th point became the n-th curve)
    which = b.on_domain(b.node("GeometryNodeInputIndex", x + 3200, y - 300).outputs[0], "CURVE", "INT", x=x + 3400,
                        y=y - 300)

    def own(name, data_type, yy):
        n = b.node("GeometryNodeSampleIndex", x + 3600, yy, data_type=data_type, domain="POINT")
        b.feed(n.inputs["Geometry"], spots_out)
        b.feed(_enabled(n.inputs, "Value")[0], b.named_attribute(name, data_type, x=x + 3400, y=yy)[0])
        b.feed(n.inputs["Index"], which)
        return _enabled(n.outputs, "Value")[0]

    arc_normal = own("mmdd_arc_normal", "FLOAT_VECTOR", y - 500)
    arc_side = own("mmdd_arc_side", "FLOAT_VECTOR", y - 700)
    arc_len = own("mmdd_arc_len", "FLOAT", y - 900)
    arc_rnd = own("mmdd_arc_rnd", "FLOAT", y - 1100)
    t = b.node("GeometryNodeSplineParameter", x + 3600, y - 1300).outputs["Factor"]
    bump = b.math("SINE", b.math("MULTIPLY", t, math.pi, x=x + 3800, y=y - 1300), x=x + 4000, y=y - 1300)
    kink = b.white_noise(b.combine(b.node("GeometryNodeInputIndex", x + 3600, y - 1500).outputs[0],
                                   b.math("MULTIPLY", frame, 1.37, x=x + 3600, y=y - 1650), 0.71, x=x + 3800,
                                   y=y - 1550), x=x + 4000, y=y - 1550)[1]
    bend = b.node("ShaderNodeTexNoise", x + 4000, y - 1800, noise_dimensions="3D")
    b.feed(bend.inputs["Vector"], b.combine(b.math("MULTIPLY_ADD", t, 1.8, b.math("MULTIPLY", arc_rnd, 17.0, x=x + 3600,
                                                                                    y=y - 1850), x=x + 3800,
                                                   y=y - 1800),
                                            b.math("MULTIPLY", arc_rnd, 31.0, x=x + 3600, y=y - 2000),
                                            b.math("MULTIPLY", frame, 0.43, x=x + 3600, y=y - 2150), x=x + 3800,
                                            y=y - 2000))
    bend.inputs["Scale"].default_value = 1.0
    bend.inputs["Detail"].default_value = 1.0
    kx, ky, _kz = b.split_xyz(kink, x=x + 4200, y=y - 1550)
    bx, by, _bz = b.split_xyz(bend.outputs[1], x=x + 4200, y=y - 1800)
    sideways = b.math("ADD", b.math("MULTIPLY_ADD", bx, 2.0, -1.0, x=x + 4400, y=y - 1800),
                      b.math("MULTIPLY_ADD", kx, 0.7, -0.35, x=x + 4400, y=y - 1550), x=x + 4600, y=y - 1700)
    outward = b.math("ADD", b.math("MULTIPLY_ADD", by, 1.0, -0.2, x=x + 4400, y=y - 2000),
                     b.math("MULTIPLY_ADD", ky, 0.5, -0.25, x=x + 4400, y=y - 2150), x=x + 4600, y=y - 2050)
    amount = b.math("MULTIPLY", b.math("MULTIPLY", arc_len, bump, x=x + 4600, y=y - 1300), 0.3, x=x + 4800, y=y - 1300)
    zigzag = b.vmath("ADD", b.vmath("SCALE", arc_side, scale=sideways, x=x + 4800, y=y - 1700),
                     b.vmath("SCALE", arc_normal, scale=outward, x=x + 4800, y=y - 2000), x=x + 5000, y=y - 1850)
    curves = b.set_position(curves.outputs["Geometry"], b.vmath("SCALE", zigzag, scale=amount, x=x + 5200, y=y - 1600),
                            x=x + 5200, y=y)
    width = b.node("GeometryNodeSetCurveRadius", x + 5400, y)
    b.feed(width.inputs["Curve"], curves)
    b.feed(width.inputs["Radius"], b.math("MULTIPLY", b.math("MULTIPLY_ADD", b.math("POWER", bump, 0.6, x=x + 5200,
                                                                                    y=y - 200), 0.7, 0.3,
                                                             x=x + 5400, y=y - 200),
                                          b.math("MULTIPLY_ADD", beat, 0.4, 1.0, x=x + 5400, y=y - 350), x=x + 5600,
                                          y=y - 250))
    bright = b.math("MULTIPLY", b.math("MULTIPLY_ADD", arc_rnd, 0.9, 0.55, x=x + 5400, y=y - 500),
                    b.math("MULTIPLY_ADD", beat, 0.8, 1.0, x=x + 5400, y=y - 650), x=x + 5600, y=y - 550)
    lit = b.store(width.outputs["Curve"], ATTR_EDGE, bright, x=x + 5600, y=y)
    lit = _remove_attributes(b, lit, _ARC_ATTRS + (_ARC_DIR,), x + 5800, y)
    tube = b.curve_to_mesh(lit, _circle(b, gi.outputs["Arc Thickness"], 4, x + 6400, y - 300), x=x + 6600, y=y)
    shaded = b.node("GeometryNodeSetMaterial", x + 6800, y)
    b.feed(shaded.inputs["Geometry"], tube)
    b.feed(shaded.inputs["Material"], gi.outputs["Arc Material"])
    on = b.boolean("AND", gi.outputs["Arcs"], b.compare("GREATER_THAN", radius, 0.0, x=x + 6800, y=y + 300),
                   x=x + 7000, y=y + 300)
    return b.switch("GEOMETRY", on, None, shaded.outputs["Geometry"], x=x + 7200, y=y)


def _strike(b, gi, radius, me, x, y):
    """The lightning strike: while the mask grows to Strike Until (the first few frames) a bolt comes down from Strike
    Height above the start point (the mask's centre) onto it, with three forks, a new shape every other frame and
    flickering like lightning does; in the arc material."""
    info = b.node("GeometryNodeObjectInfo", x, y, transform_space="RELATIVE")
    b.feed(info.inputs["Object"], gi.outputs["Mask"])
    hit = info.outputs["Location"]
    up = b.vmath("NORMALIZE", _unrotate(b, me, (0.0, 0.0, 1.0), x, y - 200), x=x + 200, y=y - 200)
    frame = b.node("GeometryNodeInputSceneTime", x, y - 400).outputs["Frame"]
    shape = b.math("FLOOR", b.math("MULTIPLY", frame, 0.5, x=x + 200, y=y - 400), x=x + 400, y=y - 400)
    height = gi.outputs["Strike Height"]

    def level(vector, xx, yy):
        """`vector` without its part along up (sideways)."""
        along = b.vmath("DOT_PRODUCT", vector, up, x=xx, y=yy - 150)
        return b.vmath("SUBTRACT", vector, b.vmath("SCALE", up, scale=along, x=xx + 200, y=yy - 150), x=xx + 400,
                       y=yy)

    lean = b.vmath("SUBTRACT", b.white_noise(b.combine(shape, 0.53, 0.29, x=x + 600, y=y - 600), x=x + 800,
                                             y=y - 600)[1], (0.5, 0.5, 0.5), x=x + 1000, y=y - 600)
    top = b.vmath("ADD", b.vmath("ADD", hit, b.vmath("SCALE", up, scale=height, x=x + 1000, y=y - 200), x=x + 1200,
                                 y=y - 200),
                  b.vmath("SCALE", level(lean, x + 1200, y - 600), scale=b.math("MULTIPLY", height, 0.5, x=x + 1400,
                                                                                    y=y - 750), x=x + 1800, y=y - 600),
                  x=x + 2000, y=y - 300)

    def jagged(start, end, size, pin_start, pin_end, count, salt, xx, yy):
        """A line from `start` to `end` broken into a zigzag `size` wide (a big bend and small kinks, sideways), held
        still at the pinned ends."""
        line = b.node("GeometryNodeCurvePrimitiveLine", xx, yy)
        points = b.node("GeometryNodeResampleCurve", xx + 200, yy)
        b.feed(points.inputs["Curve"], line.outputs["Curve"])
        points.inputs["Count"].default_value = count
        t = b.node("GeometryNodeSplineParameter", xx, yy - 200).outputs["Factor"]
        straight = b.vmath("ADD", start, b.vmath("SCALE", b.vmath("SUBTRACT", end, start, x=xx + 200, y=yy - 300),
                                                 scale=t, x=xx + 400, y=yy - 300), x=xx + 600, y=yy - 300)
        kink = b.white_noise(b.combine(b.node("GeometryNodeInputIndex", xx, yy - 500).outputs[0], shape, salt,
                                       x=xx + 200, y=yy - 500), x=xx + 400, y=yy - 500)[1]
        # a few big bends, finer crackle on them and a small kink at every point, like a real bolt
        wiggle = b.vmath("SCALE", b.vmath("SUBTRACT", kink, (0.5, 0.5, 0.5), x=xx + 600, y=yy - 500), scale=0.35,
                         x=xx + 800, y=yy - 500)
        for i, (often, how_far) in enumerate(((2.2, 2.4), (11.0, 1.2))):
            bend = b.node("ShaderNodeTexNoise", xx + 400, yy - 700 - 300 * i, noise_dimensions="3D")
            b.feed(bend.inputs["Vector"], b.combine(b.math("MULTIPLY", t, often, x=xx + 200, y=yy - 700 - 300 * i),
                                                    b.math("MULTIPLY_ADD", shape, 0.37, salt + 5.0 * i, x=xx + 200,
                                                           y=yy - 850 - 300 * i),
                                                    salt * 3.1 + 7.0 * i, x=xx + 400, y=yy - 850 - 300 * i))
            bend.inputs["Detail"].default_value = 2.0
            wiggle = b.vmath("ADD", wiggle, b.vmath("SCALE", b.vmath("SUBTRACT", bend.outputs[1], (0.5, 0.5, 0.5),
                                                                     x=xx + 600, y=yy - 700 - 300 * i),
                                                    scale=how_far, x=xx + 800, y=yy - 700 - 300 * i),
                             x=xx + 1000, y=yy - 600 - 300 * i)
        hold = 1.0
        if pin_start:
            hold = b.math("MULTIPLY", t, 6.0, x=xx + 600, y=yy - 1000, clamp=True)
        if pin_end:
            hold = b.math("MULTIPLY", hold, b.math("MULTIPLY", b.math("SUBTRACT", 1.0, t, x=xx + 600, y=yy - 1150), 6.0,
                                                   x=xx + 800, y=yy - 1150, clamp=True), x=xx + 1000, y=yy - 1100)
        moved = b.vmath("SCALE", level(wiggle, xx + 1200, yy - 600), scale=b.math("MULTIPLY", size, hold, x=xx + 1200,
                                                                                   y=yy - 1000), x=xx + 1600,
                        y=yy - 700)
        return b.set_position(points.outputs["Curve"], position=b.vmath("ADD", straight, moved, x=xx + 1800,
                                                                          y=yy - 400), x=xx + 1800, y=yy)

    main = jagged(top, hit, b.math("MULTIPLY", height, 0.06, x=x + 2000, y=y - 1000), False, True, STRIKE_POINTS, 0.11,
                  x + 2200, y)
    bolts = [main]
    for k, (at, salt) in enumerate(((0.3, 1.7), (0.5, 2.9), (0.68, 4.3))):
        yy = y - 1500 - 1500 * k
        start = b.node("GeometryNodeSampleCurve", x + 2200, yy)
        b.feed(start.inputs["Curves"], main)
        start.inputs["Factor"].default_value = at
        way = b.vmath("SUBTRACT", b.white_noise(b.combine(shape, k + 0.5, 0.77, x=x + 2000, y=yy - 300),
                                                x=x + 2200, y=yy - 300)[1], (0.5, 0.5, 0.5), x=x + 2400, y=yy - 300)
        way = b.vmath("SUBTRACT", b.vmath("NORMALIZE", level(way, x + 2600, yy - 300), x=x + 3000, y=yy - 300),
                      b.vmath("SCALE", up, scale=0.7, x=x + 3000, y=yy - 450), x=x + 3200, y=yy - 350)
        reach = b.math("MULTIPLY", height, 0.1 + 0.03 * k, x=x + 3200, y=yy - 550)
        end = b.vmath("ADD", start.outputs["Position"], b.vmath("SCALE", way, scale=reach, x=x + 3400, y=yy - 450),
                      x=x + 3600, y=yy - 350)
        fork = jagged(start.outputs["Position"], end, b.math("MULTIPLY", height, 0.025, x=x + 3600, y=yy - 600), True,
                      False, 30, salt, x + 3800, yy)
        taper = b.node("GeometryNodeSetCurveRadius", x + 5800, yy)
        b.feed(taper.inputs["Curve"], fork)
        b.feed(taper.inputs["Radius"], b.math("MULTIPLY_ADD", b.node("GeometryNodeSplineParameter", x + 5600,
                                                                     yy - 200).outputs["Factor"], -0.35, 0.55,
                                              x=x + 5800, y=yy - 200))
        bolts.append(taper.outputs["Curve"])
    thick = b.node("GeometryNodeSetCurveRadius", x + 5800, y)
    b.feed(thick.inputs["Curve"], main)
    thick.inputs["Radius"].default_value = 1.0
    bolts[0] = thick.outputs["Curve"]
    # lightning flickers: bright on most frames, dim on some
    flicker = b.white_noise(b.combine(frame, 0.91, 0.17, x=x + 5800, y=y + 300), x=x + 6000, y=y + 300)[0]
    bright = b.math("MULTIPLY_ADD", b.math("GREATER_THAN", flicker, 0.3, x=x + 6200, y=y + 300), 1.4, 0.4, x=x + 6400,
                    y=y + 300)
    lit = b.store(b.join(bolts, x=x + 6000, y=y), ATTR_EDGE, bright, x=x + 6400, y=y)
    tube = b.curve_to_mesh(lit, _circle(b, b.math("MULTIPLY", gi.outputs["Arc Thickness"], 2.5, x=x + 6400, y=y - 300),
                                        5, x + 6600, y - 300), x=x + 6800, y=y)
    shaded = b.node("GeometryNodeSetMaterial", x + 7000, y)
    b.feed(shaded.inputs["Geometry"], tube)
    b.feed(shaded.inputs["Material"], gi.outputs["Arc Material"])
    striking = b.boolean("AND", b.boolean("AND", gi.outputs["Strike"], gi.outputs["Main"], x=x + 7000, y=y + 400),
                         b.boolean("AND", b.compare("GREATER_THAN", radius, 0.0, x=x + 7000, y=y + 250),
                                   b.compare("LESS_THAN", radius, gi.outputs["Strike Until"], x=x + 7000, y=y + 100),
                                   x=x + 7200, y=y + 200), x=x + 7400, y=y + 300)
    return b.switch("GEOMETRY", striking, None, shaded.outputs["Geometry"], x=x + 7400, y=y)


def _body_box(b, geometry, x, y):
    """Rest-pose bounds of `geometry`, so what is set up by them stays put while the body dances: (centre x, centre y,
    the floor (its lowest point), its height, its half width (the larger of its half sizes across, no more than a fifth
    of its height: round the body, not the arms held out))."""
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=x, y=y)
    still = b.switch("VECTOR", has_rest, b.node("GeometryNodeInputPosition", x, y - 150).outputs[0], rest, x=x + 200,
                     y=y)
    stat = b.node("GeometryNodeAttributeStatistic", x + 400, y, data_type="FLOAT_VECTOR", domain="POINT")
    b.feed(stat.inputs["Geometry"], geometry)
    b.feed(_enabled(stat.inputs, "Attribute")[0], still)
    lo, hi = _enabled(stat.outputs, "Min")[0], _enabled(stat.outputs, "Max")[0]
    lo_x, lo_y, lo_z = b.split_xyz(lo, x=x + 600, y=y)
    hi_x, hi_y, hi_z = b.split_xyz(hi, x=x + 600, y=y - 200)
    mid_x = b.math("MULTIPLY", b.math("ADD", lo_x, hi_x, x=x + 800, y=y), 0.5, x=x + 1000, y=y)
    mid_y = b.math("MULTIPLY", b.math("ADD", lo_y, hi_y, x=x + 800, y=y - 150), 0.5, x=x + 1000, y=y - 150)
    tall = b.math("SUBTRACT", hi_z, lo_z, x=x + 800, y=y - 300)
    half = b.math("MULTIPLY", b.math("MAXIMUM", b.math("SUBTRACT", hi_x, lo_x, x=x + 800, y=y - 450),
                                     b.math("SUBTRACT", hi_y, lo_y, x=x + 800, y=y - 600), x=x + 1000, y=y - 500),
                  0.5, x=x + 1200, y=y - 500)
    half = b.math("MINIMUM", half, b.math("MULTIPLY", tall, 0.2, x=x + 1200, y=y - 650), x=x + 1400, y=y - 550)
    return mid_x, mid_y, lo_z, tall, half


def _unit_band(b, segments, width, x, y):
    """A flat ring of radius 1 in the XY plane, `width` across, with ATTR_BAND running -1 .. 1 across it."""
    grid = b.node("GeometryNodeMeshGrid", x, y)
    for name, value in (("Size X", 1.0), ("Size Y", 1.0), ("Vertices X", segments + 1), ("Vertices Y", 2)):
        grid.inputs[name].default_value = value
    gx, gy, _gz = b.split_xyz(b.node("GeometryNodeInputPosition", x, y - 200).outputs[0], x=x + 200, y=y - 200)
    band = b.store(grid.outputs["Mesh"], ATTR_BAND, b.math("MULTIPLY", gy, 2.0, x=x + 400, y=y - 300), x=x + 400, y=y)
    angle = b.math("MULTIPLY", b.math("ADD", gx, 0.5, x=x + 400, y=y - 450), 2.0 * math.pi, x=x + 600, y=y - 450)
    r = b.math("MULTIPLY_ADD", gy, width, 1.0, x=x + 600, y=y - 600)
    spot = b.combine(b.math("MULTIPLY", b.math("COSINE", angle, x=x + 800, y=y - 400), r, x=x + 1000, y=y - 400),
                     b.math("MULTIPLY", b.math("SINE", angle, x=x + 800, y=y - 550), r, x=x + 1000, y=y - 550), 0.0,
                     x=x + 1200, y=y - 450)
    return b.set_position(band, position=spot, x=x + 1200, y=y)


def _petal(b, length, half_width, layer, x, y):
    """One lotus petal standing up from the origin along Z, its inside facing -Y: narrow at the foot, widest a third
    of the way up, pointed at the tip, cupped and bowed out a little. ATTR_PETAL: across it, up it, `layer`."""
    grid = b.node("GeometryNodeMeshGrid", x, y)
    for name, value in (("Size X", 1.0), ("Size Y", 1.0), ("Vertices X", 9), ("Vertices Y", 18)):
        grid.inputs[name].default_value = value
    gx, gy, _gz = b.split_xyz(b.node("GeometryNodeInputPosition", x, y - 200).outputs[0], x=x + 200, y=y - 200)
    u = b.math("MULTIPLY", gx, 2.0, x=x + 400, y=y - 200)
    v = b.math("ADD", gy, 0.5, x=x + 400, y=y - 350)
    leaf = b.store(grid.outputs["Mesh"], ATTR_PETAL, b.combine(u, v, float(layer), x=x + 600, y=y - 250),
                   "FLOAT_VECTOR", x=x + 600, y=y)
    swell = b.math("POWER", b.math("SINE", b.math("MULTIPLY", b.math("POWER", v, 0.85, x=x + 600, y=y - 450),
                                                  math.pi, x=x + 800, y=y - 450), x=x + 1000, y=y - 450), 0.8,
                   x=x + 1200, y=y - 450)
    w = b.math("MULTIPLY", b.math("MULTIPLY_ADD", swell, 0.78, 0.22, x=x + 1400, y=y - 450),
               b.math("SUBTRACT", 1.0, b.math("POWER", v, 6.0, x=x + 1200, y=y - 600), x=x + 1400, y=y - 600),
               x=x + 1600, y=y - 500)
    across = b.math("MULTIPLY", b.math("MULTIPLY", u, w, x=x + 1800, y=y - 400), half_width, x=x + 2000, y=y - 400)
    cup = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", u, u, x=x + 1800, y=y - 600), w, x=x + 2000,
                                    y=y - 600), b.math("MULTIPLY", half_width, -0.4, x=x + 1800, y=y - 750),
                 x=x + 2200, y=y - 650)
    arch = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", v, math.pi, x=x + 1600, y=y - 900), x=x + 1800,
                                     y=y - 900), 0.12, x=x + 2000, y=y - 900)
    tip_in = b.math("MULTIPLY", b.math("POWER", v, 3.0, x=x + 1800, y=y - 1050), 0.07, x=x + 2000, y=y - 1050)
    bow = b.math("MULTIPLY", b.math("SUBTRACT", arch, tip_in, x=x + 2200, y=y - 950), length, x=x + 2400, y=y - 950)
    spot = b.combine(across, b.math("ADD", cup, bow, x=x + 2400, y=y - 700),
                     b.math("MULTIPLY", v, length, x=x + 2400, y=y - 1150), x=x + 2600, y=y - 700)
    return b.set_position(leaf, position=spot, x=x + 2600, y=y)


def _lotus(b, gi, geometry, p, beat, x, y):
    """The lotus (Ne Zha 2's seven-colour lotus, Malenia's bloom): two rings of big petals grow up from the floor round
    the body, p running 0 -> 1 up to the moment, close into a bud over the first half (see-through, it glows), stay shut
    (and breathe on a beat) while the outfits swap inside at the moment with a flash, open out after it and sink down
    flat and shrink away. Each petal leans about the tangent at its foot, each on its own a little late. In Lotus
    Material (the particle colour); ATTR_EDGE carries the glow of the flash."""
    mid_x, mid_y, floor, tall, half = _body_box(b, geometry, x, y)
    frame = b.node("GeometryNodeInputSceneTime", x, y - 900).outputs["Frame"]
    count = gi.outputs["Lotus Petals"]
    grow = b.map_range(p, 0.0, 0.25, x=x + 1400, y=y + 300, smooth=True)
    fade = b.map_range(p, 1.38, 1.62, 1.0, 0.0, x=x + 1400, y=y + 150, smooth=True)
    off = b.math("ABSOLUTE", b.math("SUBTRACT", p, 1.0, x=x + 1400, y=y + 600), x=x + 1600, y=y + 600)
    flash = b.math("SUBTRACT", 1.0, b.math("DIVIDE", off, 0.08, x=x + 1800, y=y + 600), x=x + 2000, y=y + 600,
                   clamp=True)
    glow = b.math("MULTIPLY_ADD", flash, 0.65, 0.35, x=x + 2200, y=y + 600)
    foot = b.math("MULTIPLY", half, 1.15, x=x + 1600, y=y - 500)
    layers = []
    for layer, (length_k, width_k, out_k, shut, offset) in enumerate(((1.18, 0.3, 1.0, 0.16, 0.0),
                                                                     (1.06, 0.26, 0.82, 0.08, 0.5))):
        yy = y - 1500 - 3600 * layer
        length = b.math("MULTIPLY", tall, length_k, x=x + 1600, y=yy)
        leaf = _petal(b, length, b.math("MULTIPLY", length, width_k * 0.5, x=x + 1600, y=yy - 150), layer, x + 1800,
                      yy)
        leaf = b.store(leaf, ATTR_EDGE, glow, x=x + 4600, y=yy)
        shaded = b.node("GeometryNodeSetMaterial", x + 4800, yy)
        b.feed(shaded.inputs["Geometry"], leaf)
        b.feed(shaded.inputs["Material"], gi.outputs["Lotus Material"])
        pts = b.node("GeometryNodePoints", x + 1800, yy - 1300)
        b.feed(pts.inputs["Count"], count)
        k = b.node("GeometryNodeInputIndex", x + 1400, yy - 1500).outputs[0]
        angle = b.math("MULTIPLY", b.math("DIVIDE", b.math("ADD", k, offset, x=x + 1600, y=yy - 1500),
                                          b.math("MAXIMUM", count, 1.0, x=x + 1600, y=yy - 1650), x=x + 1800,
                                          y=yy - 1550), 2.0 * math.pi, x=x + 2000, y=yy - 1550)
        out = b.math("MULTIPLY", foot, out_k, x=x + 2000, y=yy - 1700)
        b.feed(pts.inputs["Position"], b.combine(
            b.math("MULTIPLY_ADD", b.math("COSINE", angle, x=x + 2200, y=yy - 1450), out, mid_x, x=x + 2400,
                   y=yy - 1450),
            b.math("MULTIPLY_ADD", b.math("SINE", angle, x=x + 2200, y=yy - 1600), out, mid_y, x=x + 2400, y=yy - 1600),
            floor, x=x + 2600, y=yy - 1500))
        rnd = b.white_noise(b.combine(k, 0.37 + layer, 0.71, x=x + 1600, y=yy - 1900), x=x + 1800, y=yy - 1900)[0]
        late = b.math("MULTIPLY_ADD", rnd, 0.08, 0.05 * layer, x=x + 2000, y=yy - 1900)
        close = b.map_range(p, b.math("ADD", late, 0.1, x=x + 2200, y=yy - 2000),
                            b.math("ADD", late, 0.5, x=x + 2200, y=yy - 2150), x=x + 2400, y=yy - 2050, smooth=True)
        bloom = b.map_range(p, b.math("ADD", late, 1.02, x=x + 2200, y=yy - 2300),
                            b.math("ADD", late, 1.3, x=x + 2200, y=yy - 2450), x=x + 2400, y=yy - 2350, smooth=True)
        # lying open (leaning out) -> shut (leaning in a little) -> flat on the floor; while shut it breathes
        lean = b.math("MULTIPLY_ADD", close, shut + 1.2, -1.2, x=x + 2600, y=yy - 2100)
        lean = b.math("ADD", lean, b.math("MULTIPLY", bloom, b.math("SUBTRACT", -1.5, lean, x=x + 2600, y=yy - 2400),
                                          x=x + 2800, y=yy - 2350), x=x + 3000, y=yy - 2200)
        wave = b.math("SINE", b.math("MULTIPLY_ADD", frame, 0.2, k, x=x + 2600, y=yy - 2800), x=x + 2800, y=yy - 2800)
        breath = b.math("ADD", b.math("MULTIPLY", beat, -0.06, x=x + 2800, y=yy - 2600),
                        b.math("MULTIPLY", wave, -0.015, x=x + 3000, y=yy - 2800), x=x + 3200, y=yy - 2700)
        shut_now = b.math("MULTIPLY", close, b.math("SUBTRACT", 1.0, bloom, x=x + 3000, y=yy - 2950), x=x + 3200,
                          y=yy - 2900)
        lean = b.math("ADD", lean, b.math("MULTIPLY", breath, shut_now, x=x + 3400, y=yy - 2800), x=x + 3600,
                      y=yy - 2300)
        petals = b.node("GeometryNodeInstanceOnPoints", x + 5000, yy - 1300)
        b.feed(petals.inputs["Points"], pts.outputs["Geometry"])
        b.feed(petals.inputs["Instance"], shaded.outputs["Geometry"])
        b.feed(petals.inputs["Rotation"], b.combine(lean, 0.0, b.math("SUBTRACT", angle, math.pi / 2, x=x + 3600,
                                                                      y=yy - 1700), x=x + 3800, y=yy - 1800))
        b.feed(petals.inputs["Scale"], b.math("MULTIPLY", grow, fade, x=x + 3800, y=yy - 1300))
        layers.append(petals.outputs["Instances"])
    there = b.boolean("AND", b.boolean("AND", gi.outputs["Lotus"], gi.outputs["Main"], x=x + 5200, y=y + 300),
                      b.boolean("AND", b.compare("GREATER_THAN", p, 0.0, x=x + 5200, y=y + 150),
                                b.compare("LESS_THAN", p, 1.62, x=x + 5200, y=y), x=x + 5400, y=y + 100),
                      x=x + 5600, y=y + 200)
    return b.switch("GEOMETRY", there, None, b.join(layers, x=x + 5400, y=y - 1500), x=x + 5800, y=y)


def _flames(b, gi, geometry, d, radius, me, x, y):
    """Toon flames (no simulation): a shell of flame just over the surface of `geometry`, burning in a band round the
    edge (`d` is the distance the front measures) or, with Flame Aura, all over the body as the mask passes from Flame
    Start (up) to Flame Peak (strongest) and Flame End (gone); and tongues of flame on it: cards standing up, turned to
    the camera, flickering. In Flame Material: the shell carries ATTR_FLAME (how strongly it burns) and ATTR_FRAME, the
    tongues ATTR_FLAME_CARD and, on their instances, ATTR_FLAME_SEED and ATTR_FRAME."""
    width = b.math("MINIMUM", gi.outputs["Flame Width"], b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=x, y=y),
                                                                 2.0, x=x + 200, y=y), x=x + 400, y=y)
    off = b.math("ABSOLUTE", b.math("SUBTRACT", d, radius, x=x, y=y - 200), x=x + 200, y=y - 200)
    band = b.math("SUBTRACT", 1.0, b.math("DIVIDE", off, b.math("MAXIMUM", width, 1e-4, x=x + 400, y=y - 300),
                                          x=x + 600, y=y - 200), x=x + 800, y=y - 200, clamp=True)
    aura = b.math("MULTIPLY", b.map_range(radius, gi.outputs["Flame Start"], gi.outputs["Flame Peak"], x=x, y=y - 500,
                                          smooth=True),
                  b.map_range(radius, gi.outputs["Flame Peak"], gi.outputs["Flame End"], 1.0, 0.0, x=x, y=y - 700,
                              smooth=True), x=x + 200, y=y - 600)
    amount = b.switch("FLOAT", gi.outputs["Flame Aura"], band, aura, x=x + 1000, y=y - 300)
    frame = b.node("GeometryNodeInputSceneTime", x, y - 900).outputs["Frame"]
    burning = b.separate(geometry, b.compare("GREATER_THAN", b.on_domain(amount, "FACE", x=x + 1000, y=y - 500), 0.02,
                                             x=x + 1200, y=y - 500), "FACE", x=x + 1400, y=y)[0]
    shell = b.store(burning, ATTR_FLAME, amount, x=x + 1600, y=y)
    normal = b.node("GeometryNodeInputNormal", x + 1400, y - 300).outputs[0]
    lift = b.math("MULTIPLY", gi.outputs["Flame Height"], 0.05, x=x + 1600, y=y - 400)
    shell = b.set_position(shell, b.vmath("SCALE", normal, scale=lift, x=x + 1800, y=y - 300), x=x + 1800, y=y)
    shell = b.store(shell, ATTR_FRAME, frame, x=x + 2000, y=y)
    shell_mat = b.node("GeometryNodeSetMaterial", x + 2200, y)
    b.feed(shell_mat.inputs["Geometry"], shell)
    b.feed(shell_mat.inputs["Material"], gi.outputs["Flame Material"])

    # the camera (the front of the scene without one)
    cam = b.node("GeometryNodeObjectInfo", x + 1400, y - 1900, transform_space="RELATIVE")
    b.feed(cam.inputs["Object"], gi.outputs["Camera"])
    has_cam = b.compare("GREATER_THAN", b.vmath("LENGTH", cam.outputs["Scale"], x=x + 1600, y=y - 2100), 0.0,
                        x=x + 1800, y=y - 2100)
    # tongues of flame on the shell, as many as the density says where it burns, most of them along the outline as the
    # camera sees it (there they stand out of the body; over the middle they would only hide it)
    spot = b.node("GeometryNodeInputPosition", x + 1400, y - 1100).outputs[0]
    to_cam = b.switch("VECTOR", has_cam, _unrotate(b, me, (0.0, -1.0, 0.0), x + 1600, y - 1300),
                      b.vmath("SUBTRACT", cam.outputs["Location"], spot, x=x + 1600, y=y - 1100), x=x + 1800,
                      y=y - 1200)
    facing = b.math("ABSOLUTE", b.vmath("DOT_PRODUCT", b.vmath("NORMALIZE", to_cam, x=x + 2000, y=y - 1200),
                                        b.node("GeometryNodeInputNormal", x + 1800, y - 1400).outputs[0],
                                        x=x + 2200, y=y - 1300), x=x + 2400, y=y - 1300)
    side = b.math("SUBTRACT", 1.0, facing, x=x + 2600, y=y - 1300, clamp=True)
    outline = b.math("MULTIPLY_ADD", b.math("POWER", side, 2.0, x=x + 2800, y=y - 1300), 1.9, 0.1, x=x + 3000,
                     y=y - 1300)  # (twice as dense as the panel says at the outline, a twentieth of that in the middle)
    spread = b.node("GeometryNodeDistributePointsOnFaces", x + 2200, y - 600, distribute_method="RANDOM")
    b.feed(spread.inputs["Mesh"], shell)
    b.feed(spread.inputs["Density"], b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Flame Density"],
                                                               b.named_attribute(ATTR_FLAME, "FLOAT", x=x + 2000,
                                                                                 y=y - 800)[0], x=x + 2200,
                                                               y=y - 800), outline, x=x + 3200, y=y - 900))
    spread.inputs["Seed"].default_value = 11
    pts = spread.outputs["Points"]
    on_pt = b.named_attribute(ATTR_FLAME, "FLOAT", x=x + 2400, y=y - 1000)[0]
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=x + 2400, y=y - 1150)
    here = b.node("GeometryNodeInputPosition", x + 2400, y - 1300).outputs[0]
    still = b.switch("VECTOR", has_rest, here, rest, x=x + 2600, y=y - 1200)
    rnd = b.white_noise(b.vmath("SCALE", still, scale=3.7, x=x + 2800, y=y - 1200), x=x + 3000, y=y - 1200)[0]
    phase = b.math("MULTIPLY_ADD", frame, 0.9, b.math("MULTIPLY", rnd, 2.0 * math.pi, x=x + 2800, y=y - 1500),
                   x=x + 3000, y=y - 1500)
    flicker = b.math("MULTIPLY_ADD", b.math("SINE", phase, x=x + 3200, y=y - 1500), 0.15, 0.85, x=x + 3400, y=y - 1500)
    size = b.math("MULTIPLY", gi.outputs["Flame Height"], b.math("MULTIPLY_ADD", rnd, 0.9, 0.55, x=x + 3200,
                                                                  y=y - 1300), x=x + 3400, y=y - 1300)
    tall = b.math("MULTIPLY", size, b.math("MULTIPLY", b.math("MULTIPLY_ADD", on_pt, 0.65, 0.35, x=x + 3200,
                                                               y=y - 1700), flicker, x=x + 3600, y=y - 1600),
                  x=x + 3800, y=y - 1400)
    # turned to face the camera about the upright (the front of the scene without a camera)
    cx, cy, _cz = b.split_xyz(b.vmath("SUBTRACT", cam.outputs["Location"], here, x=x + 2600, y=y - 1900), x=x + 2800,
                              y=y - 1900)
    yaw = b.math("ADD", b.math("ARCTAN2", cy, cx, x=x + 3000, y=y - 1900), math.pi / 2, x=x + 3200, y=y - 1900)
    yaw = b.switch("FLOAT", has_cam, 0.0, yaw, x=x + 3400, y=y - 2000)
    pts = b.store(pts, ATTR_FLAME_SEED, rnd, x=x + 3600, y=y - 600)
    pts = b.store(pts, ATTR_FRAME, frame, x=x + 3800, y=y - 600)
    card = b.node("GeometryNodeMeshGrid", x + 3400, y - 2400)
    for name, value in (("Size X", 1.0), ("Size Y", 1.0), ("Vertices X", 2), ("Vertices Y", 6)):
        card.inputs[name].default_value = value
    gx, gy, _gz = b.split_xyz(b.node("GeometryNodeInputPosition", x + 3400, y - 2600).outputs[0], x=x + 3600,
                              y=y - 2600)
    across_up = b.combine(b.math("MULTIPLY", gx, 2.0, x=x + 3800, y=y - 2600), b.math("ADD", gy, 0.5, x=x + 3800,
                                                                                     y=y - 2750), 1.0, x=x + 4000,
                          y=y - 2650)
    card_mesh = b.store(card.outputs["Mesh"], ATTR_FLAME_CARD, across_up, "FLOAT_VECTOR", x=x + 3800, y=y - 2400)
    stand = b.node("GeometryNodeTransform", x + 4000, y - 2400)
    b.feed(stand.inputs["Geometry"], card_mesh)
    stand.inputs["Rotation"].default_value = (math.pi / 2, 0.0, 0.0)
    stand.inputs["Translation"].default_value = (0.0, 0.0, 0.5)
    card_mat = b.node("GeometryNodeSetMaterial", x + 4200, y - 2400)
    b.feed(card_mat.inputs["Geometry"], stand.outputs["Geometry"])
    b.feed(card_mat.inputs["Material"], gi.outputs["Flame Material"])
    tongues = b.node("GeometryNodeInstanceOnPoints", x + 4400, y - 600)
    b.feed(tongues.inputs["Points"], pts)
    b.feed(tongues.inputs["Instance"], card_mat.outputs["Geometry"])
    b.feed(tongues.inputs["Rotation"], b.combine(0.0, 0.0, yaw, x=x + 3600, y=y - 2000))
    b.feed(tongues.inputs["Scale"], b.combine(b.math("MULTIPLY", tall, 0.45, x=x + 4000, y=y - 1400), 1.0, tall,
                                              x=x + 4200, y=y - 1400))
    flames = b.join([shell_mat.outputs["Geometry"], tongues.outputs["Instances"]], x=x + 4600, y=y)
    lit = b.switch("BOOLEAN", gi.outputs["Flame Aura"], b.compare("GREATER_THAN", radius, 0.0, x=x + 4400, y=y + 300),
                   b.compare("GREATER_THAN", aura, 0.001, x=x + 4400, y=y + 150), x=x + 4600, y=y + 250)
    return b.switch("GEOMETRY", b.boolean("AND", gi.outputs["Flames"], lit, x=x + 4800, y=y + 300), None, flames,
                    x=x + 5000, y=y)


def _shockwave(b, gi, geometry, radius, x, y):
    """A shockwave on the floor at the big moment (the mask passing from Shock Start to Shock End): a bright ring
    spreads from the feet out to Shock Size, a fainter wide one behind it, and puffs of dust are kicked up along it
    (Dust Material, fading with ATTR_SMOKE). The rings glow by ATTR_EDGE in Shock Material, which fades them out
    across the band by ATTR_BAND."""
    mid_x, mid_y, floor, tall, half = _body_box(b, geometry, x, y)
    length = b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["Shock End"], gi.outputs["Shock Start"], x=x, y=y + 150),
                    1e-4, x=x + 200, y=y + 150)
    u = b.math("DIVIDE", b.math("SUBTRACT", radius, gi.outputs["Shock Start"], x=x, y=y + 300), length, x=x + 400,
               y=y + 250)
    t = b.math("MINIMUM", b.math("MAXIMUM", u, 0.0, x=x + 600, y=y + 300), 1.0, x=x + 800, y=y + 300)
    left = b.math("SUBTRACT", 1.0, t, x=x + 1000, y=y + 300)
    ease = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", left, left, x=x + 1200, y=y + 300), x=x + 1400, y=y + 300)
    strength = b.math("MULTIPLY", b.math("POWER", left, 1.3, x=x + 1200, y=y + 500),
                      b.map_range(t, 0.0, 0.04, x=x + 1200, y=y + 650), x=x + 1400, y=y + 500)
    reach = b.math("MULTIPLY_ADD", gi.outputs["Shock Size"], ease, b.math("MULTIPLY", half, 1.2, x=x + 1400, y=y + 100),
                   x=x + 1600, y=y + 200)
    rings = []
    for i, (width, shrink, level) in enumerate(((0.06, 1.0, 1.0), (0.3, 0.85, 0.35))):
        yy = y - 600 - 900 * i
        ring = _unit_band(b, 128, width, x + 1600, yy)
        # (the glow falls off across the band in Shock Material, by ATTR_BAND: the band has vertices only on its rims)
        ring = b.store(ring, ATTR_EDGE, b.math("MULTIPLY", strength, level, x=x + 2800, y=yy - 300), x=x + 3000, y=yy)
        px, py, _pz = b.split_xyz(b.node("GeometryNodeInputPosition", x + 3000, yy - 600).outputs[0], x=x + 3200,
                                  y=yy - 600)
        r = b.math("MULTIPLY", reach, shrink, x=x + 3200, y=yy - 750)
        spot = b.combine(b.math("MULTIPLY_ADD", px, r, mid_x, x=x + 3400, y=yy - 600),
                         b.math("MULTIPLY_ADD", py, r, mid_y, x=x + 3400, y=yy - 750),
                         b.math("MULTIPLY_ADD", tall, 0.003 * (i + 1), floor, x=x + 3400, y=yy - 900), x=x + 3600,
                         y=yy - 700)
        rings.append(b.set_position(ring, position=spot, x=x + 3800, y=yy))
    shaded = b.node("GeometryNodeSetMaterial", x + 4000, y - 600)
    b.feed(shaded.inputs["Geometry"], b.join(rings, x=x + 3900, y=y - 600))
    b.feed(shaded.inputs["Material"], gi.outputs["Shock Material"])
    # dust kicked up along the ring
    dust = b.node("GeometryNodePoints", x + 1600, y - 2400)
    dust.inputs["Count"].default_value = 28
    k = b.node("GeometryNodeInputIndex", x + 1200, y - 2600).outputs[0]
    rnd, rnd_color = b.white_noise(b.combine(k, 0.53, 0.19, x=x + 1400, y=y - 2600), x=x + 1600, y=y - 2600)
    r1, r2, r3 = b.split_xyz(rnd_color, x=x + 1800, y=y - 2600)
    angle = b.math("MULTIPLY_ADD", k, 2.0 * math.pi / 28.0, b.math("MULTIPLY", r1, 0.3, x=x + 1800, y=y - 2800),
                   x=x + 2000, y=y - 2700)
    out = b.math("MULTIPLY", reach, b.math("MULTIPLY_ADD", r2, 0.15, 0.9, x=x + 2000, y=y - 2900), x=x + 2200,
                 y=y - 2900)
    up = b.math("MULTIPLY", r3, b.math("SQRT", t, x=x + 2000, y=y - 3100), x=x + 2200, y=y - 3100)
    lift = b.math("MULTIPLY", tall, b.math("MULTIPLY_ADD", up, 0.07, 0.01, x=x + 2400, y=y - 3100), x=x + 2600,
                  y=y - 3100)
    b.feed(dust.inputs["Position"], b.combine(
        b.math("MULTIPLY_ADD", b.math("COSINE", angle, x=x + 2200, y=y - 2600), out, mid_x, x=x + 2400, y=y - 2600),
        b.math("MULTIPLY_ADD", b.math("SINE", angle, x=x + 2200, y=y - 2750), out, mid_y, x=x + 2400, y=y - 2750),
        b.math("ADD", floor, lift, x=x + 2800, y=y - 3000), x=x + 3000, y=y - 2700))
    ball = b.node("GeometryNodeMeshIcoSphere", x + 2800, y - 2200)
    ball.inputs["Radius"].default_value = 1.0
    ball.inputs["Subdivisions"].default_value = 3  # (round puffs of dust, not faceted stones)
    smooth = b.node("GeometryNodeSetShadeSmooth", x + 3000, y - 2200)
    b.feed(smooth.inputs[0], ball.outputs["Mesh"])
    puff = b.node("GeometryNodeSetMaterial", x + 3200, y - 2200)
    b.feed(puff.inputs["Geometry"], smooth.outputs[0])
    b.feed(puff.inputs["Material"], gi.outputs["Dust Material"])
    puffs = b.node("GeometryNodeInstanceOnPoints", x + 3400, y - 2400)
    b.feed(puffs.inputs["Points"], dust.outputs["Geometry"])
    b.feed(puffs.inputs["Instance"], puff.outputs["Geometry"])
    # kicked up as the ring passes, then shrinking away as they clear (puffs, not stones lying about)
    grown = b.math("MULTIPLY", b.math("ADD", rnd, 0.5, x=x + 3000, y=y - 3450),
                   b.math("MULTIPLY", b.map_range(t, 0.0, 0.15, 0.3, 1.0, x=x + 2800, y=y - 3600),
                          b.math("SUBTRACT", 1.0, b.math("POWER", t, 1.5, x=x + 2800, y=y - 3750), x=x + 3000,
                                 y=y - 3750), x=x + 3200, y=y - 3650), x=x + 3200, y=y - 3500)
    puff_size = b.math("MULTIPLY", b.math("MULTIPLY", tall, 0.02, x=x + 3000, y=y - 3300), grown, x=x + 3400,
                       y=y - 3400)
    b.feed(puffs.inputs["Scale"], b.combine(b.math("MULTIPLY", puff_size, 1.3, x=x + 3600, y=y - 3300),
                                            b.math("MULTIPLY", puff_size, 1.3, x=x + 3600, y=y - 3450),
                                            b.math("MULTIPLY", puff_size, 0.75, x=x + 3600, y=y - 3600),
                                            x=x + 3800, y=y - 3400))
    clearing = b.store(puffs.outputs["Instances"], ATTR_SMOKE, b.math("POWER", t, 1.2, x=x + 3400, y=y - 2700),
                       domain="INSTANCE", x=x + 3600, y=y - 2400)
    there = b.boolean("AND", b.boolean("AND", gi.outputs["Shock"], gi.outputs["Main"], x=x + 3800, y=y + 300),
                      b.boolean("AND", b.compare("GREATER_THAN", u, 0.0, x=x + 3800, y=y + 150),
                                b.compare("LESS_THAN", u, 1.0, x=x + 3800, y=y), x=x + 4000, y=y + 100),
                      x=x + 4200, y=y + 200)
    return b.switch("GEOMETRY", there, None, b.join([shaded.outputs["Geometry"], clearing], x=x + 4200, y=y - 600),
                    x=x + 4400, y=y)


def _soul_rings(b, gi, geometry, radius, beat, x, y):
    """Soul rings (Soul Land, 斗罗大陆): rings of light rise from the floor one after another as the mask grows from Soul
    Start to Soul Peak, each to its own height (from the knees up to above the head), and float round the body, tilting
    and bobbing, until they fade by Soul End. The instances carry ATTR_SOUL: which ring (its colour by the Soul Land
    code: yellow, yellow, purple, purple, black, black, black, red, red) and how bright (flaring on a beat)."""
    mid_x, mid_y, floor, tall, half = _body_box(b, geometry, x, y)
    count = gi.outputs["Soul Rings"]
    frame = b.node("GeometryNodeInputSceneTime", x, y - 900).outputs["Frame"]
    rings = b.node("GeometryNodePoints", x + 1600, y)
    b.feed(rings.inputs["Count"], count)
    k = b.node("GeometryNodeInputIndex", x + 1200, y - 200).outputs[0]
    many = b.math("MAXIMUM", count, 1.0, x=x + 1200, y=y - 400)
    span = b.math("SUBTRACT", gi.outputs["Soul Peak"], gi.outputs["Soul Start"], x=x + 1200, y=y - 550)
    start = b.math("MULTIPLY_ADD", b.math("DIVIDE", k, many, x=x + 1400, y=y - 450), span, gi.outputs["Soul Start"],
                   x=x + 1600, y=y - 500)
    rise_len = b.math("DIVIDE", b.math("MULTIPLY", span, 1.6, x=x + 1600, y=y - 700), many, x=x + 1800, y=y - 700)
    rise = b.map_range(radius, start, b.math("ADD", start, rise_len, x=x + 2000, y=y - 650), x=x + 2200, y=y - 550,
                       smooth=True)
    late = b.math("MULTIPLY", b.math("SUBTRACT", gi.outputs["Soul End"], gi.outputs["Soul Peak"], x=x + 1600,
                                     y=y - 900), 0.35, x=x + 1800, y=y - 900)
    fade = b.map_range(radius, b.math("SUBTRACT", gi.outputs["Soul End"], late, x=x + 2000, y=y - 850),
                       gi.outputs["Soul End"], 1.0, 0.0, x=x + 2200, y=y - 850, smooth=True)
    order = b.math("DIVIDE", k, b.math("MAXIMUM", b.math("SUBTRACT", count, 1.0, x=x + 1400, y=y - 1100), 1.0,
                                       x=x + 1600, y=y - 1100), x=x + 1800, y=y - 1050)
    level = b.math("MULTIPLY_ADD", order, 0.76, 0.12, x=x + 2000, y=y - 1050)
    swing = b.math("MULTIPLY_ADD", frame, 0.07, b.math("MULTIPLY", k, 1.9, x=x + 1800, y=y - 1350), x=x + 2000,
                   y=y - 1300)
    bob = b.math("MULTIPLY", b.math("SINE", swing, x=x + 2200, y=y - 1300), 0.012, x=x + 2400, y=y - 1300)
    climb = b.math("MULTIPLY", b.math("ADD", level, bob, x=x + 2600, y=y - 1150), rise, x=x + 2800, y=y - 1100)
    height = b.math("MULTIPLY_ADD", tall, climb, floor, x=x + 3000, y=y - 1000)
    b.feed(rings.inputs["Position"], b.combine(mid_x, mid_y, height, x=x + 3400, y=y - 900))
    glow = b.math("MULTIPLY", b.math("MULTIPLY", rise, fade, x=x + 2400, y=y - 700),
                  b.math("MULTIPLY_ADD", beat, 0.6, 1.0, x=x + 2400, y=y - 850), x=x + 2600, y=y - 750)
    pts = b.store(rings.outputs["Geometry"], ATTR_SOUL, b.combine(k, glow, 0.0, x=x + 2800, y=y - 750),
                  "FLOAT_VECTOR", x=x + 3600, y=y)
    ring = _unit_band(b, 128, 0.07, x + 1600, y - 1800)
    shaded = b.node("GeometryNodeSetMaterial", x + 2800, y - 1800)
    b.feed(shaded.inputs["Geometry"], ring)
    b.feed(shaded.inputs["Material"], gi.outputs["Soul Material"])
    tip_a = b.math("MULTIPLY_ADD", frame, 0.031, b.math("MULTIPLY", k, 2.3, x=x + 3000, y=y - 2300), x=x + 3200,
                   y=y - 2200)
    tip_b = b.math("MULTIPLY_ADD", frame, 0.027, b.math("MULTIPLY", k, 1.3, x=x + 3000, y=y - 2550), x=x + 3200,
                   y=y - 2450)
    tilt = b.combine(b.math("MULTIPLY", b.math("SINE", tip_a, x=x + 3400, y=y - 2200), 0.1, x=x + 3600, y=y - 2200),
                     b.math("MULTIPLY", b.math("COSINE", tip_b, x=x + 3400, y=y - 2450), 0.1, x=x + 3600, y=y - 2450),
                     b.math("MULTIPLY", frame, 0.01, x=x + 3600, y=y - 2700), x=x + 3800, y=y - 2400)
    size = b.math("MULTIPLY", b.math("MULTIPLY", half, b.math("MULTIPLY_ADD", k, 0.04, 1.35, x=x + 3400, y=y - 2900),
                                     x=x + 3600, y=y - 2900),
                  b.math("MULTIPLY_ADD", rise, 0.2, 0.8, x=x + 3600, y=y - 3050), x=x + 3800, y=y - 2950)
    circling = b.node("GeometryNodeInstanceOnPoints", x + 4000, y)
    b.feed(circling.inputs["Points"], pts)
    b.feed(circling.inputs["Instance"], shaded.outputs["Geometry"])
    b.feed(circling.inputs["Rotation"], tilt)
    b.feed(circling.inputs["Scale"], b.combine(size, size, 1.0, x=x + 4000, y=y - 2950))
    some = b.boolean("AND", b.compare("GREATER_THAN", count, 0.5, x=x + 4000, y=y + 450), gi.outputs["Main"],
                     x=x + 4200, y=y + 400)
    window = b.boolean("AND", b.compare("GREATER_THAN", radius, gi.outputs["Soul Start"], x=x + 4200, y=y + 250),
                       b.compare("LESS_THAN", radius, gi.outputs["Soul End"], x=x + 4200, y=y + 100), x=x + 4400,
                       y=y + 150)
    return b.switch("GEOMETRY", b.boolean("AND", some, window, x=x + 4600, y=y + 300), None,
                    circling.outputs["Instances"], x=x + 4800, y=y)


def _husk(b, gi, geometry, launch, has_launch, radius, anchor, wind, me, x, y):
    """The husk (Black Myth's 聚形散气, a cicada's shell): from the moment the old outfit goes (Clamp Distance), all of
    the old model, its locked parts too, stays behind where it was then (the recorded positions, so it holds still
    while the body dances on), holds for Husk Hold and then over Husk Span either crumbles away from the top, its faces
    breaking off and blowing away like flakes, or with Husk Float rises by Husk Rise and fades out. ATTR_HUSK tells the
    materials it is the husk (1 solid .. 0 gone). Nothing without a recording."""
    age = b.math("SUBTRACT", radius, gi.outputs["Clamp Distance"], x=x, y=y + 300)
    hold, span = gi.outputs["Husk Hold"], gi.outputs["Husk Span"]
    frozen = b.set_position(geometry, selection=has_launch, position=launch, x=x + 200, y=y)
    frozen = b.delete(frozen, b.boolean("NOT", has_launch, x=x + 200, y=y - 200), "POINT", x=x + 400, y=y)
    frozen = b.store(frozen, ATTR_EDGE, 0.0, x=x + 600, y=y)
    frozen = b.store(frozen, ATTR_AHEAD, 1.0, x=x + 800, y=y)
    # floating up and fading
    gone = b.map_range(age, hold, b.math("ADD", hold, span, x=x + 600, y=y - 300), x=x + 800, y=y - 300, smooth=True)
    up = _unrotate(b, me, (0.0, 0.0, 1.0), x + 800, y - 500)
    rise = b.math("MULTIPLY", gi.outputs["Husk Rise"], b.math("MULTIPLY", gone, gone, x=x + 1000, y=y - 650),
                  x=x + 1200, y=y - 600)
    floated = b.set_position(frozen, b.vmath("SCALE", up, scale=rise, x=x + 1400, y=y - 500), x=x + 1400, y=y - 200)
    floated = b.store(floated, ATTR_HUSK, b.math("SUBTRACT", 1.0, gone, x=x + 1400, y=y - 800), x=x + 1600, y=y - 200)
    # crumbling from the top: faces break off one after another and blow away
    rest_z = b.split_xyz(anchor, x=x, y=y - 1100)[2]
    stat = b.node("GeometryNodeAttributeStatistic", x + 200, y - 1300, data_type="FLOAT", domain="POINT")
    b.feed(stat.inputs["Geometry"], frozen)
    b.feed(_enabled(stat.inputs, "Attribute")[0], rest_z)
    up_body = b.math("DIVIDE", b.math("SUBTRACT", rest_z, stat.outputs["Min"], x=x + 400, y=y - 1100),
                     b.math("MAXIMUM", stat.outputs["Range"], 1e-4, x=x + 400, y=y - 1250), x=x + 600, y=y - 1150)
    face_up = b.on_domain(up_body, "FACE", x=x + 800, y=y - 1150)
    seed = b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=x + 800, y=y - 1350)
    rnd = b.white_noise(b.vmath("SCALE", seed, scale=5.7, x=x + 1000, y=y - 1350), x=x + 1200, y=y - 1350)[0]
    order = b.math("MULTIPLY_ADD", b.math("SUBTRACT", 1.0, face_up, x=x + 1000, y=y - 1150), 0.65,
                   b.math("MULTIPLY", rnd, 0.1, x=x + 1200, y=y - 1500), x=x + 1400, y=y - 1200)
    start = b.math("MULTIPLY_ADD", span, order, hold, x=x + 1800, y=y - 1150)
    tf = b.math("DIVIDE", b.math("SUBTRACT", age, start, x=x + 2000, y=y - 1150),
                b.math("MAXIMUM", b.math("MULTIPLY", span, 0.3, x=x + 1800, y=y - 1350), 1e-4, x=x + 2000, y=y - 1350),
                x=x + 2200, y=y - 1200, clamp=True)
    face_t = b.on_domain(tf, "FACE", x=x + 2400, y=y - 1200)
    intact = b.delete(frozen, b.compare("GREATER_THAN", face_t, 0.0, x=x + 2600, y=y - 1000), "FACE", x=x + 2800,
                      y=y - 900)
    breaking = b.boolean("AND", b.compare("GREATER_THAN", face_t, 0.0, x=x + 2600, y=y - 1300),
                         b.compare("LESS_THAN", face_t, 0.999, x=x + 2600, y=y - 1450), x=x + 2800, y=y - 1350)
    moving = b.separate(frozen, breaking, "FACE", x=x + 3000, y=y - 1200)[0]
    split = b.node("GeometryNodeSplitEdges", x + 3200, y - 1200)
    b.feed(split.inputs["Mesh"], moving)
    flake_t = b.on_domain(tf, "FACE", x=x + 3000, y=y - 1600)
    centre = b.on_domain(b.node("GeometryNodeInputPosition", x + 2800, y - 1800).outputs[0], "FACE", "FLOAT_VECTOR",
                         x=x + 3000, y=y - 1800)
    face_normal = b.on_domain(b.node("GeometryNodeInputNormal", x + 2800, y - 2000).outputs[0], "FACE",
                              "FLOAT_VECTOR", x=x + 3000, y=y - 2000)
    scaled = b.node("GeometryNodeScaleElements", x + 3400, y - 1200, domain="FACE")
    b.feed(scaled.inputs["Geometry"], split.outputs["Mesh"])
    b.feed(scaled.inputs["Scale"], b.math("POWER", b.math("SUBTRACT", 1.0, flake_t, x=x + 3200, y=y - 1600), 0.6,
                                          x=x + 3400, y=y - 1600))
    b.feed(scaled.inputs["Center"], centre)
    fly = _fly(b, gi, flake_t, face_normal, seed, rnd, wind, me, x + 3400, y - 2200)
    flown = b.set_position(scaled.outputs["Geometry"], fly, x=x + 4600, y=y - 1200)
    crumbled = b.store(b.join([intact, flown], x=x + 4800, y=y - 1000), ATTR_HUSK, 1.0, x=x + 5000, y=y - 1000)
    husk = b.switch("GEOMETRY", gi.outputs["Husk Float"], crumbled, floated, x=x + 5200, y=y - 500)
    lasting = b.compare("LESS_THAN", age, b.math("ADD", hold, span, x=x + 4800, y=y + 50), x=x + 5000, y=y + 50)
    there = b.boolean("AND", gi.outputs["Husk"], b.boolean("AND", b.compare("GREATER_EQUAL", age, 0.0, x=x + 5000,
                                                                            y=y + 200), lasting, x=x + 5200,
                                                           y=y + 150), x=x + 5400, y=y + 200)
    return b.switch("GEOMETRY", there, None, husk, x=x + 5600, y=y)


def _fly(b, gi, t, normal, seed, rnd, wind, me, x, y):
    """Offset of a piece that has left the surface, t going 0 -> 1 over its flight: it pops out along
    the normal, drifts with the wind (accelerating, each piece at its own speed) and swirls in a noise.
    `wind` is in object space; the swirl is turned by the object's rotation `me`, so it stays put in the world."""
    inv = b.math("SUBTRACT", 1.0, t, x=x, y=y)
    pop = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", inv, inv, x=x + 150, y=y), x=x + 300, y=y)
    burst = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", pop, gi.outputs["Burst"], x=x + 450, y=y),
                    x=x + 600, y=y)
    speed = b.math("ADD", rnd, 0.5, x=x, y=y - 200)
    drift = b.math("MULTIPLY", b.math("MULTIPLY", t, t, x=x + 150, y=y - 200), speed, x=x + 300, y=y - 200)
    gust = b.vmath("SCALE", wind, scale=drift, x=x + 600, y=y - 200)
    noise = b.node("ShaderNodeTexNoise", x, y - 400, noise_dimensions="4D")
    b.feed(noise.inputs["Vector"], seed)
    b.feed(noise.inputs["W"], b.math("MULTIPLY", t, 1.5, x=x - 200, y=y - 450))
    b.feed(noise.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Noise Scale"], 0.6, x=x - 200, y=y - 600))
    noise.inputs["Detail"].default_value = 1.0
    # Noise colour channels wander around 0.5; recentre and amplify to roughly -1..1.
    swirl = b.vmath("SUBTRACT", noise.outputs[1], (0.5, 0.5, 0.5), x=x + 200, y=y - 400)
    amount = b.math("MULTIPLY", gi.outputs["Turbulence"], b.math("MULTIPLY", t, 4.0, x=x + 200, y=y - 600),
                    x=x + 400, y=y - 600)
    swirl = _unrotate(b, me, b.vmath("SCALE", swirl, scale=amount, x=x + 600, y=y - 400), x + 800, y - 400)
    return b.vmath("ADD", b.vmath("ADD", burst, gust, x=x + 800, y=y - 100), swirl, x=x + 1000, y=y - 250)


def _pieces(b, geometry, anchor, size, extra_key, x, y):
    """Cut a mesh into chunks about `size` across: 3D Voronoi cells in rest space (so the cuts stick to
    the body) plus the mesh's own islands. Returns the split mesh and per-piece fields
    (island, count, centre, rest centre, normal); pieces never mix faces with a different `extra_key`."""
    cell = b.node("ShaderNodeTexVoronoi", x, y, voronoi_dimensions="3D", feature="F1")
    b.feed(cell.inputs["Vector"], anchor)
    b.feed(cell.inputs["Scale"], b.math("DIVIDE", 1.0, b.math("MAXIMUM", size, 1e-4, x=x - 200, y=y - 200),
                                        x=x - 100, y=y - 150))
    key = b.vmath("DOT_PRODUCT", cell.outputs["Color"], (1.0, 0.618, 0.381), x=x + 200, y=y)
    key = b.math("MULTIPLY_ADD", extra_key, 3.0, key, x=x + 400, y=y)
    face_key = b.on_domain(key, "FACE", x=x + 600, y=y)
    face_sq = b.on_domain(b.math("MULTIPLY", key, key, x=x + 600, y=y - 150), "FACE", x=x + 800, y=y - 150)
    # An edge is a cut when its faces disagree: mean(key^2) - mean(key)^2 > 0 over the faces of the edge.
    mean = b.on_domain(face_key, "EDGE", x=x + 800, y=y)
    spread = b.math("SUBTRACT", b.on_domain(face_sq, "EDGE", x=x + 1000, y=y - 150),
                    b.math("MULTIPLY", mean, mean, x=x + 1000, y=y), x=x + 1200, y=y)
    split = b.node("GeometryNodeSplitEdges", x + 1400, y)
    b.feed(split.inputs["Mesh"], geometry)
    b.feed(split.inputs["Selection"], b.compare("GREATER_THAN", spread, 1e-7, x=x + 1400, y=y - 200))
    island = b.node("GeometryNodeInputMeshIsland", x + 1400, y - 400).outputs["Island Index"]
    count = b.accumulate(1.0, island, x=x + 1600, y=y - 300)
    center = b.vmath("SCALE", b.accumulate(b.node("GeometryNodeInputPosition", x + 1400, y - 600).outputs[0],
                                           island, "FLOAT_VECTOR", x=x + 1600, y=y - 500),
                     scale=b.math("DIVIDE", 1.0, count, x=x + 1800, y=y - 300), x=x + 2000, y=y - 500)
    rest_center = b.vmath("SCALE", b.accumulate(anchor, island, "FLOAT_VECTOR", x=x + 1600, y=y - 700),
                          scale=b.math("DIVIDE", 1.0, count, x=x + 1800, y=y - 750), x=x + 2000, y=y - 700)
    normal = b.vmath("NORMALIZE", b.accumulate(b.node("GeometryNodeInputNormal", x + 1400, y - 900).outputs[0],
                                               island, "FLOAT_VECTOR", x=x + 1600, y=y - 900),
                     x=x + 2000, y=y - 900)
    return split.outputs["Mesh"], island, count, center, rest_center, normal


def _scale_cells(b, anchor, size, x, y):
    """Scales: 3D Voronoi cells about `size` across on the rest position, each face in the cell of its centre, so both
    outfits are cut into the same scales where they overlap. Returns face fields (key, cell, site): a number that tells
    cells apart on a cut (the Voronoi colour), an integer naming the cell (the unit cube of the scaled space its site
    lies in, 8 bits an axis: exact as a float) and the cell's site (rest space)."""
    scale = b.math("DIVIDE", 1.0, b.math("MAXIMUM", size, 1e-4, x=x - 200, y=y - 250), x=x, y=y - 250)
    voronoi = b.node("ShaderNodeTexVoronoi", x + 200, y, voronoi_dimensions="3D", feature="F1")
    b.feed(voronoi.inputs["Vector"], b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=x, y=y))
    b.feed(voronoi.inputs["Scale"], scale)
    key = b.on_domain(b.vmath("DOT_PRODUCT", voronoi.outputs["Color"], (1.0, 0.618, 0.381), x=x + 400, y=y),
                      "FACE", x=x + 600, y=y)
    site = b.on_domain(voronoi.outputs["Position"], "FACE", "FLOAT_VECTOR", x=x + 400, y=y - 200)
    lattice = b.vmath("FLOOR", b.vmath("SCALE", site, scale=scale, x=x + 600, y=y - 250), x=x + 800, y=y - 250)
    wrapped = b.vmath("MODULO", b.vmath("ADD", lattice, (1024.0, 1024.0, 1024.0), x=x + 1000, y=y - 250),
                      (256.0, 256.0, 256.0), x=x + 1200, y=y - 250)
    cell = b.vmath("DOT_PRODUCT", wrapped, (1.0, 256.0, 65536.0), x=x + 1400, y=y - 250)
    return key, cell, site


def _flip(b, gi, field_group, geometry, d, path, radius, keep, new, glow, x, y, plates=False):
    """Scales (Mystique): `geometry` cut into scales (_scale_cells) that turn over where the edge passes, while it moves
    Flip Width on, about an axis across the way the wave runs (`path`, the clean distance along it), popping up off
    the surface so they clear it. The old outfit shows the first half of the turn (flat to edge-on, then it is gone),
    the new outfit (`new`) the second half (edge-on to flat), so together a scale turns over with the old outfit on
    one side and the new one on the other. `d` is the distance timing a vertex, `keep` (old outfit) faces that never
    turn. Turning scales glint (ATTR_EDGE) when `glow` is on.

    A scale is timed by its site: the Field group probed there (the sphere's distance and the edge noise at the site,
    or the arrival distance of the vertex nearest to it), the same in both outfits whatever else the scale holds.
    Measured on the posed body (Use Rest Position off) it is the mean distance of its faces instead. Scales are only
    timed in a band around the edge (on a copy of it; farther away a face is simply before or behind the edge) and
    only the turning ones are cut out of the mesh.

    With `plates` (armour plates, Mark 50) nothing turns over: behind the edge each plate (Plate Size) rises off the
    surface by Plate Lift, tilting a little, and settles back while the edge moves Plate Width on; nothing goes."""
    size = gi.outputs["Plate Size" if plates else "Scale Size"]
    # (the width grows in with the radius, so nothing turns before the edge sets off)
    width = b.math("MAXIMUM", b.math("MINIMUM", gi.outputs["Plate Width" if plates else "Flip Width"],
                                     b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=x - 400, y=y - 1300), 2.0,
                                            x=x - 200, y=y - 1300), x=x, y=y - 1250), 1e-4, x=x + 200, y=y - 1250)
    # The band: a scale reaches about one and a half scale sizes from its site, so a face farther than this from the
    # edge belongs to a scale that is all before or all behind it. The scales are timed on a copy of the band only.
    face_d = b.on_domain(d, "FACE", x=x, y=y - 400)
    margin = b.math("MULTIPLY_ADD", size, 3.5, b.math("MULTIPLY", width, 0.5, x=x, y=y - 600), x=x + 200, y=y - 550)
    near = b.compare("LESS_THAN", b.math("ABSOLUTE", b.math("SUBTRACT", radius, face_d, x=x + 200, y=y - 400),
                                         x=x + 400, y=y - 400), margin, x=x + 600, y=y - 450)
    band = b.separate(geometry, near, "FACE", x=x + 800, y=y)[0]

    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=x + 800, y=y - 1000)
    anchor = b.switch("VECTOR", has_rest, b.node("GeometryNodeInputPosition", x + 800, y - 1150).outputs[0], rest,
                      x=x + 1000, y=y - 1000)
    key, cell, site = _scale_cells(b, anchor, size, x + 1200, y - 1000)
    # Timing at the site: the arrival distance there is the one of the band's vertex nearest to it on the rest pose.
    on_rest = b.set_position(band, position=anchor, x=x + 1200, y=y - 1600)
    nearest = b.node("GeometryNodeSampleNearest", x + 1400, y - 1600, domain="POINT")
    b.feed(nearest.inputs["Geometry"], on_rest)
    b.feed(nearest.inputs["Sample Position"], site)
    sampled = b.node("GeometryNodeSampleIndex", x + 1600, y - 1600, data_type="FLOAT", domain="POINT")
    b.feed(sampled.inputs["Geometry"], on_rest)
    b.feed(_enabled(sampled.inputs, "Value")[0], b.named_attribute(ATTR_ARRIVAL, "FLOAT", x=x + 1400, y=y - 1800)[0])
    b.feed(sampled.inputs["Index"], nearest.outputs["Index"])
    site_arrival = b.switch("FLOAT", gi.outputs["Use Arrival"], 0.0, _enabled(sampled.outputs, "Value")[0],
                            x=x + 1800, y=y - 1600)
    probe = b.node("GeometryNodeGroup", x + 2000, y - 1400)
    probe.node_tree = field_group
    for spec in FIELD_INPUTS:
        b.feed(probe.inputs[spec[0]], gi.outputs[spec[0]])
    b.feed(probe.inputs["Probe"], True)
    b.feed(probe.inputs["Probe Point"], site)
    b.feed(probe.inputs["Probe Arrival"], site_arrival)
    # ... on the posed body, the mean distance of the scale's faces
    total = b.accumulate(face_d, cell, x=x + 2000, y=y - 1900, domain="FACE")
    faces = b.accumulate(1.0, cell, x=x + 2000, y=y - 2100, domain="FACE")
    timing = b.switch("FLOAT", gi.outputs["Use Rest Position"], b.math("DIVIDE", total, faces, x=x + 2200, y=y - 2000),
                      probe.outputs["Distance"], x=x + 2400, y=y - 1600)
    # a little earlier or later at random, the same in both outfits: random by the site
    jitter = b.math("MULTIPLY", b.math("SUBTRACT", b.white_noise(b.vmath("SCALE", site, scale=1.37, x=x + 2000,
                                                                         y=y - 2300), x=x + 2200, y=y - 2300)[0],
                                       0.5, x=x + 2400, y=y - 2300), b.math("MULTIPLY", size, 0.5, x=x + 2400,
                                                                             y=y - 2450), x=x + 2600, y=y - 2300)
    turned = b.math("MULTIPLY_ADD", b.math("SUBTRACT", radius, b.math("ADD", timing, jitter, x=x + 2600, y=y - 1700),
                                           x=x + 2800, y=y - 1700),
                    b.math("DIVIDE", 1.0, width, x=x + 2800, y=y - 1900), 0.0 if plates else 0.5, x=x + 3000,
                    y=y - 1750, clamp=True)
    timed = b.store(band, ATTR_FLIP, turned, "FLOAT", "FACE", x=x + 3000, y=y + 300)
    # Back on the whole mesh (never cut here: no seams on the faces that do not turn): a band face is the how-manieth
    # band face it is in the copy; the others are wholly before (0) or behind (1) the edge.
    band_index = b.math("SUBTRACT", b.accumulate(b.switch("FLOAT", near, 0.0, 1.0, x=x + 2800, y=y + 600), None,
                                                 x=x + 3000, y=y + 600, domain="FACE", output="Leading"), 1.0,
                        x=x + 3200, y=y + 600)
    from_band = b.node("GeometryNodeSampleIndex", x + 3200, y + 300, data_type="FLOAT", domain="FACE")
    b.feed(from_band.inputs["Geometry"], timed)
    b.feed(_enabled(from_band.inputs, "Value")[0], b.named_attribute(ATTR_FLIP, "FLOAT", x=x + 3000, y=y + 450)[0])
    b.feed(from_band.inputs["Index"], band_index)
    elsewhere = b.switch("FLOAT", b.compare("GREATER_THAN", radius, face_d, x=x + 3000, y=y + 800), 0.0, 1.0,
                         x=x + 3200, y=y + 800)
    staged = b.store(geometry, ATTR_FLIP, b.switch("FLOAT", near, elsewhere, _enabled(from_band.outputs, "Value")[0],
                                                   x=x + 3400, y=y + 500), "FLOAT", "FACE", x=x + 3600, y=y + 200)
    turn = b.named_attribute(ATTR_FLIP, "FLOAT", x=x + 3200, y=y - 300)[0]
    if plates:  # nothing goes; the plates in the band rise and settle
        gone = False
        moving = b.boolean("AND", b.compare("GREATER_THAN", turn, 0.0, x=x + 3400, y=y - 300),
                           b.compare("LESS_THAN", turn, 1.0, x=x + 3400, y=y - 450), x=x + 3600, y=y - 400)
    elif new:  # the second half: edge-on to flat
        gone = b.compare("LESS_EQUAL", turn, 0.5, x=x + 3400, y=y - 300)
        moving = b.compare("LESS_THAN", turn, 1.0, x=x + 3400, y=y - 450)
    else:  # the first half: flat to edge-on
        loose = b.boolean("NOT", keep, x=x + 3200, y=y - 600)
        gone = b.boolean("AND", b.compare("GREATER_EQUAL", turn, 0.5, x=x + 3400, y=y - 300), loose,
                         x=x + 3600, y=y - 300)
        moving = b.boolean("AND", b.compare("GREATER_THAN", turn, 0.0, x=x + 3400, y=y - 450), loose,
                           x=x + 3600, y=y - 450)
    if plates:
        left = staged
    else:
        left = b.delete(staged, gone, "FACE", x=x + 3600, y=y)
        # (loose vertices and edges, without faces, come and go with the edge like the grown outfit's)
        loose = b.compare("LESS_THAN", b.node("GeometryNodeInputMeshVertexNeighbors", x + 3400, y + 500).outputs[
            "Face Count"], 0.5, x=x + 3600, y=y + 500)
        behind = b.compare("GREATER_THAN", radius, d, x=x + 3600, y=y + 650)
        left = b.delete(left, b.boolean("AND", loose, b.boolean("NOT", behind, x=x + 3800, y=y + 650) if new else
                                        behind, x=x + 4000, y=y + 550), "POINT", x=x + 3800, y=y + 300)
    turning, still = b.separate(left, moving, "FACE", x=x + 3800, y=y)
    # The mesh's own seams (PMX splits it at every UV seam) are welded first, so a scale turns as one plate, then the
    # turning part is cut into its scales: an edge is a cut where its faces belong to different cells. Parts that only
    # share a cell (an arm and the side of the body) stay apart and turn on their own.
    weld = b.node("GeometryNodeMergeByDistance", x + 4000, y + 200)
    b.feed(weld.inputs["Geometry"], turning)
    b.feed(weld.inputs["Distance"], b.math("MULTIPLY", size, 0.001, x=x + 3800, y=y + 300))
    face_sq = b.on_domain(b.math("MULTIPLY", key, key, x=x + 3600, y=y - 700), "FACE", x=x + 3800, y=y - 700)
    mean_key = b.on_domain(key, "EDGE", x=x + 3800, y=y - 550)
    spread = b.math("SUBTRACT", b.on_domain(face_sq, "EDGE", x=x + 4000, y=y - 700),
                    b.math("MULTIPLY", mean_key, mean_key, x=x + 4000, y=y - 550), x=x + 4200, y=y - 600)
    split = b.node("GeometryNodeSplitEdges", x + 4200, y)
    b.feed(split.inputs["Mesh"], weld.outputs["Geometry"])
    b.feed(split.inputs["Selection"], b.compare("GREATER_THAN", spread, 1e-7, x=x + 4400, y=y - 600))
    # Each piece turns about its own middle.
    island = b.node("GeometryNodeInputMeshIsland", x + 4400, y - 900).outputs["Island Index"]
    position = b.node("GeometryNodeInputPosition", x + 4400, y - 1050).outputs[0]
    normal = b.node("GeometryNodeInputNormal", x + 4400, y - 1200).outputs[0]
    count = b.accumulate(1.0, island, x=x + 4600, y=y - 900)
    center = b.vmath("SCALE", b.accumulate(position, island, "FLOAT_VECTOR", x=x + 4600, y=y - 1050),
                     scale=b.math("DIVIDE", 1.0, count, x=x + 4800, y=y - 900), x=x + 5000, y=y - 1000)
    up = b.vmath("NORMALIZE", b.accumulate(normal, island, "FLOAT_VECTOR", x=x + 4600, y=y - 1200),
                 x=x + 4800, y=y - 1200)
    # the way the wave runs over the piece: the path distance against the positions (sum of (d - mean) * (p - mean))
    run = b.vmath("SUBTRACT", b.accumulate(b.vmath("SCALE", position, scale=path, x=x + 4400, y=y - 1400), island,
                                           "FLOAT_VECTOR", x=x + 4600, y=y - 1400),
                  b.vmath("SCALE", center, scale=b.accumulate(path, island, x=x + 4600, y=y - 1550),
                          x=x + 4800, y=y - 1550), x=x + 5000, y=y - 1450)
    along = b.vmath("SUBTRACT", run, b.vmath("SCALE", up, scale=b.vmath("DOT_PRODUCT", run, up, x=x + 5000,
                                                                         y=y - 1650), x=x + 5200, y=y - 1650),
                    x=x + 5400, y=y - 1500)
    flat = b.compare("LESS_THAN", b.vmath("LENGTH", along, x=x + 5600, y=y - 1650), 1e-12, x=x + 5800, y=y - 1650)
    along = b.switch("VECTOR", flat, along, b.vmath("CROSS_PRODUCT", up, (0.31, 0.53, 0.79), x=x + 5600,
                                                    y=y - 1800), x=x + 6000, y=y - 1550)
    axis = b.vmath("NORMALIZE", b.vmath("CROSS_PRODUCT", up, along, x=x + 6200, y=y - 1500), x=x + 6400, y=y - 1500)
    # (the trailing side comes up and the scale tips over forwards)
    part = b.named_attribute(ATTR_FLIP, "FLOAT", x=x + 5000, y=y - 1900)[0]
    half_turn = b.math("MULTIPLY", part, math.pi, x=x + 5200, y=y - 1900)
    angle = b.math("SUBTRACT", half_turn, math.pi, x=x + 5400, y=y - 2000) if new else half_turn
    rise = b.math("SINE", half_turn, x=x + 5400, y=y - 1850)
    height = b.math("MULTIPLY", size, 0.5, x=x + 5600, y=y - 2100)
    if plates:  # a slight tilt this way or that and a lift, each plate its own
        plate_rnd = b.white_noise(b.vmath("SCALE", center, scale=2.17, x=x + 5000, y=y - 2300), x=x + 5200,
                                  y=y - 2300)[0]
        angle = b.math("MULTIPLY", rise, b.math("MULTIPLY_ADD", plate_rnd, 0.6, -0.3, x=x + 5400, y=y - 2300),
                       x=x + 5600, y=y - 2250)
        height = b.math("MULTIPLY", gi.outputs["Plate Lift"], b.math("MULTIPLY_ADD", plate_rnd, 0.6, 0.7, x=x + 5400,
                                                                     y=y - 2450), x=x + 5600, y=y - 2400)
    turned_pos = b.rotate(position, center, axis, angle, x=x + 6600, y=y - 1200)
    lift = b.vmath("SCALE", up, scale=b.math("MULTIPLY", rise, height, x=x + 5800, y=y - 2000), x=x + 6000, y=y - 2000)
    moved_plates = b.set_position(split.outputs["Mesh"], position=b.vmath("ADD", turned_pos, lift, x=x + 6800,
                                                                           y=y - 1300), x=x + 7000, y=y)
    # a glint as it stands edge-on
    glint = b.math("MULTIPLY", b.math("POWER", rise, 4.0, x=x + 6600, y=y - 2000), 0.82, x=x + 6800, y=y - 2000)
    glint = b.switch("FLOAT", glow, 0.0, glint, x=x + 7000, y=y - 2000)
    if plates:  # (on top of the rim the outfit already has)
        glint = b.math("MAXIMUM", glint, b.named_attribute(ATTR_EDGE, "FLOAT", x=x + 7000, y=y - 2200)[0], x=x + 7200,
                       y=y - 2100)
    moved = b.store(moved_plates, ATTR_EDGE, glint, x=x + 7200, y=y)
    joined = b.join([still, moved], x=x + 7400, y=y)
    return _remove_attributes(b, joined, (ATTR_FLIP,), x + 7600, y)


def _old_distance(b, gi, field, x, y):
    """The distance that times the old outfit: the edge's, or with the new outfit clamping shut (Clamp) the same for
    all of it, so it all goes when the halves close (within Clamp Jitter: a few percent, none for the husk)."""
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=x, y=y)
    seed = b.switch("VECTOR", has_rest, b.node("GeometryNodeInputPosition", x, y - 150).outputs[0], rest,
                    x=x + 200, y=y - 50)
    jitter = b.math("MULTIPLY_ADD", b.white_noise(b.vmath("SCALE", seed, scale=3.3, x=x + 400, y=y - 50),
                                                  x=x + 600, y=y - 50)[0], gi.outputs["Clamp Jitter"], 1.0, x=x + 800,
                    y=y - 50)
    return b.switch("FLOAT", gi.outputs["Clamp"], field["Distance"],
                    b.math("MULTIPLY", gi.outputs["Clamp Distance"], jitter, x=x + 800, y=y - 200), x=x + 1000, y=y)


def build_base_group(field_group, venom_group):
    """Modifier for the OLD outfit: shrink away under the new one, or break into flakes, chunks and particles."""
    ng = _new_group(BASE_GROUP, is_modifier=True)
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in BASE_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")

    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -2000, 0)
    go = b.node("NodeGroupOutput", 4800, 0)

    field = _field_node(b, field_group, gi, -1900, -300)
    radius, beat = field["Radius"], field["Beat"]
    distance = _old_distance(b, gi, field, -2300, 500)
    # The age (how far the edge has moved on since it passed) is measured on the body and stored, so pieces that
    # leave behind moves away keep the timing of the vertex they came from (a posed distance would change).
    geometry = b.store(gi.outputs["Geometry"], ATTR_AGE,
                       b.math("SUBTRACT", radius, distance, x=-1700, y=-150), x=-1500, y=0)
    age = b.named_attribute(ATTR_AGE, "FLOAT", x=-1700, y=-450)[0]
    d = b.math("SUBTRACT", radius, age, x=-1500, y=-450)
    lock = b.named_attribute(ATTR_LOCK, "BOOLEAN", x=-1700, y=-600)[0]
    free = b.boolean("NOT", lock, x=-1500, y=-600)
    normal = b.node("GeometryNodeInputNormal", -1500, -800).outputs[0]
    position = b.node("GeometryNodeInputPosition", -1500, -950).outputs[0]
    # Rest position seeds the per-piece random numbers, so they do not flicker while the body moves.
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-1700, y=-1100)
    anchor = b.switch("VECTOR", has_rest, position, rest, x=-1500, y=-1100)
    # The surface ahead of the edge (black veins, frost, char, stone, gold, silk, code: materials draw it from
    # disperse_ahead, 0 far ahead .. 1 at the edge). The zone grows in with the radius, so nothing shows at the very
    # start. It follows the wave also when the old outfit goes all at once (Clamp): it freezes over, then shatters.
    reach = b.math("MINIMUM", gi.outputs["Surface Reach"],
                   b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=-2000, y=-2900), 2.0, x=-1800, y=-2900),
                   x=-1600, y=-2850)
    wave_d = b.switch("FLOAT", gi.outputs["Clamp"], d, field["Distance"], x=-1600, y=-3100)
    ahead = b.map_range(wave_d, b.math("ADD", radius, reach, x=-1400, y=-2950), radius, x=-1200, y=-2950,
                        smooth=True)
    # Silk cocoon: where the silk spreads it swells the old outfit out (locked parts stay).
    puff = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Swell"], ahead, x=-1000, y=-3100),
                  b.switch("FLOAT", free, 0.0, 1.0, x=-1000, y=-3250), x=-800, y=-3150)
    swollen = b.set_position(geometry, b.vmath("SCALE", normal, scale=puff, x=-600, y=-3150), x=-600, y=-2900)
    geometry = b.switch("GEOMETRY", b.compare("NOT_EQUAL", gi.outputs["Swell"], 0.0, x=-600, y=-2700), geometry,
                        swollen, x=-400, y=-2800)
    # Leave behind: flakes, chunks and particles start from where the body was when they broke off (recorded
    # in world space at build time, see launch.py) instead of riding along with the dancing body.
    space, has_space = _launch_space(b, gi, -1700, -1500)
    launch, has_launch = _recorded(b, space, has_space, ATTR_LAUNCH, -1700, -1300)
    # The wind blows in the world: undo the object's own rotation and scale, also while the whole model turns.
    me = _self_info(b, -1700, -1900)
    wind = b.vmath("DIVIDE", _unrotate(b, me, gi.outputs["Wind"], -1500, -1900), me.outputs["Scale"],
                   x=-1300, y=-1900)

    def left_behind(geo, x, y):
        moved = b.set_position(geo, selection=has_launch, position=launch, x=x, y=y - 150)
        return b.switch("GEOMETRY", gi.outputs["Leave Behind"], geo, moved, x=x + 200, y=y)

    # Sucked in (a magical girl's brooch): the target is the body's vertex nearest to Suck Target on the rest pose,
    # where it is now (it moves with the dance). Pieces spiral into it about the world's up, closing in faster and
    # faster.
    on_rest = b.set_position(gi.outputs["Geometry"], position=anchor, x=-1500, y=-2400)
    nearest = b.node("GeometryNodeSampleNearest", -1300, -2400, domain="POINT")
    b.feed(nearest.inputs["Geometry"], on_rest)
    b.feed(nearest.inputs["Sample Position"], gi.outputs["Suck Target"])
    target_now = b.node("GeometryNodeSampleIndex", -1100, -2400, data_type="FLOAT_VECTOR", domain="POINT")
    b.feed(target_now.inputs["Geometry"], gi.outputs["Geometry"])
    b.feed(_enabled(target_now.inputs, "Value")[0], position)
    b.feed(target_now.inputs["Index"], nearest.outputs["Index"])
    target = _enabled(target_now.outputs, "Value")[0]
    up = _unrotate(b, me, (0.0, 0.0, 1.0), -1100, -2650)

    def sucked(start, t, x, y):
        """Where something that set off from `start` is after `t` (0 .. 1) of its flight into the target."""
        close = b.math("MULTIPLY", t, t, x=x, y=y - 150)
        spun = b.rotate(start, target, up, b.math("MULTIPLY", gi.outputs["Suck Turns"],
                                                  b.math("MULTIPLY", close, 2.0 * math.pi, x=x, y=y - 300),
                                                  x=x + 200, y=y - 300), x=x + 400, y=y)
        toward = b.vmath("ADD", target, b.vmath("SCALE", b.vmath("SUBTRACT", spun, target, x=x + 600, y=y),
                                                scale=b.math("SUBTRACT", 1.0, close, x=x + 600, y=y - 150),
                                                x=x + 800, y=y), x=x + 1000, y=y)
        arc = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", t, math.pi, x=x + 600, y=y - 300), x=x + 800,
                                        y=y - 300),
                     b.math("MULTIPLY", b.vmath("LENGTH", b.vmath("SUBTRACT", start, target, x=x + 600, y=y - 450),
                                                x=x + 800, y=y - 450), 0.15, x=x + 1000, y=y - 450),
                     x=x + 1000, y=y - 300)
        return b.vmath("ADD", toward, b.vmath("SCALE", up, scale=arc, x=x + 1200, y=y - 300), x=x + 1200, y=y)

    # --- Shrink away (tutorial): sink under the new outfit, then delete behind the edge.
    inside = b.compare("LESS_EQUAL", d, radius, x=-1200, y=600)
    shrink = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", gi.outputs["Shrink"], -1.0, x=-1200, y=450),
                     x=-1000, y=450)
    shrunk = b.set_position(geometry, shrink, b.boolean("AND", inside, free, x=-1000, y=600), x=-800, y=700)
    deep = b.compare("LESS_THAN", d, b.math("SUBTRACT", radius, gi.outputs["Delete Offset"], x=-1000, y=300),
                     x=-800, y=350)
    shrunk = b.delete(shrunk, b.boolean("AND", deep, free, x=-600, y=350), "POINT", x=-400, y=700)

    # --- Disintegrate: behind the front, faces break into flakes that fly off and shrink to nothing.
    room =b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["Reach"], d, x=-1200, y=-150), 1e-4, x=-1000, y=-150)

    def lifetime(flight, y):
        # 0 at the front, 1 once the piece is gone. Pieces that break off late get a shorter flight so
        # they are gone when the mask stops growing.
        span = b.math("MINIMUM", flight, room, x=-800, y=y)
        return b.math("DIVIDE", age, span, x=-600, y=y, clamp=True)

    t = lifetime(gi.outputs["Flight"], -100)
    started = b.boolean("AND", b.compare("GREATER_THAN", b.on_domain(age, "FACE", x=-1000, y=-400), 0.0,
                                         x=-800, y=-400), free, x=-600, y=-400)
    gone = b.compare("GREATER_EQUAL", b.on_domain(t, "FACE", x=-400, y=-250), 0.999, x=-200, y=-250)
    intact = b.delete(geometry, started, "FACE", x=-200, y=200)
    flakes = b.separate(geometry, b.boolean("AND", started, b.boolean("NOT", gone, x=0, y=-300), x=200, y=-300),
                        "FACE", x=400, y=0)[0]
    sub = b.node("GeometryNodeSubdivideMesh", 600, 0)
    b.feed(sub.inputs["Mesh"], flakes)
    b.feed(sub.inputs["Level"], gi.outputs["Flake Subdivide"])
    split = b.node("GeometryNodeSplitEdges", 800, 0)
    b.feed(split.inputs["Mesh"], sub.outputs["Mesh"])
    split_mesh = left_behind(split.outputs["Mesh"], 800, 250)

    # Everything below is per flake: face averages on the split mesh.
    tf = b.on_domain(t, "FACE", x=600, y=-500)
    center = b.on_domain(position, "FACE", "FLOAT_VECTOR", x=600, y=-650)
    face_normal = b.on_domain(normal, "FACE", "FLOAT_VECTOR", x=600, y=-800)
    seed = b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=600, y=-950)
    rnd, rnd_color = b.white_noise(b.vmath("SCALE", seed, scale=7.31, x=800, y=-950), x=1000, y=-950)

    scale = b.node("GeometryNodeScaleElements", 1000, 0, domain="FACE")
    b.feed(scale.inputs["Geometry"], split_mesh)
    shrinking = b.math("POWER", b.math("SUBTRACT", 1.0, tf, x=800, y=-300), 0.6, x=1000, y=-300)
    b.feed(scale.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Flake Size"], shrinking, x=1200, y=-300))
    b.feed(scale.inputs["Center"], center)

    axis = b.vmath("SUBTRACT", rnd_color, (0.5, 0.5, 0.5), x=1200, y=-1100)
    turn = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Spin"], tf, x=1200, y=-1250),
                  b.math("MULTIPLY_ADD", rnd, 2.0, -1.0, x=1200, y=-1400), x=1400, y=-1300)
    turned = b.rotate(position, center, axis, turn, x=1600, y=-1100)
    flown = b.vmath("ADD", turned, _fly(b, gi, tf, face_normal, seed, rnd, wind, me, x=1200, y=-1600),
                    x=2600, y=-1100)
    # ... or spiralling into the brooch, each flake tumbling about its centre on the way
    into = b.vmath("ADD", sucked(center, tf, 1200, -2400), b.vmath("SUBTRACT", turned, center, x=2400, y=-2200),
                   x=2600, y=-2300)
    flown = b.switch("VECTOR", gi.outputs["Suck"], flown, into, x=2700, y=-1200)
    flakes = b.set_position(scale.outputs["Geometry"], position=flown, x=2800, y=0)
    # Bright as they break off, fading out; the injected material glow raises this to the 8th power.
    fade = b.math("POWER", b.math("SUBTRACT", 1.0, tf, x=2600, y=-300), 0.25, x=2800, y=-300)
    pop = b.math("MULTIPLY_ADD", beat, 0.1, 1.0, x=2800, y=-450)  # twice as bright on a beat (to the 8th power)
    fade = b.math("MULTIPLY", fade, pop, x=2900, y=-350)
    flakes = b.store(flakes, ATTR_EDGE, b.switch("FLOAT", gi.outputs["Flake Glow"], 0.0, fade, x=3000, y=-300),
                     x=3000, y=0)
    broken = b.join([intact, flakes], x=3200, y=200)
    old = b.switch("GEOMETRY", gi.outputs["Fragments"], shrunk, broken, x=3400, y=400)

    # --- Cast off: behind the front the old outfit breaks into armour-like chunks that are thrown out
    # along their normals, tumble, fall and shrink away (locked parts never break).
    chunks, c_island, c_count, c_center, c_rest, c_normal = _pieces(b, geometry, anchor, gi.outputs["Piece Size"],
                                                                     lock, -1200, 2200)
    chunk_d = b.math("DIVIDE", b.accumulate(d, c_island, x=1000, y=2000), c_count, x=1200, y=2000)
    chunk_age = b.math("SUBTRACT", radius, chunk_d, x=1400, y=2000)
    chunk_span = b.math("MINIMUM", gi.outputs["Flight"],
                        b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["Reach"], chunk_d, x=1400, y=1850), 1e-4,
                               x=1600, y=1850), x=1800, y=1850)
    ct = b.math("DIVIDE", chunk_age, chunk_span, x=2000, y=1950, clamp=True)
    moving = b.boolean("AND", b.compare("GREATER_THAN", chunk_age, 0.0, x=1600, y=2150), free, x=1800, y=2150)
    # Leave behind: a chunk is thrown from where the body was when it broke off, all of it at that moment. That
    # is recorded per face corner (a vertex on a cut belongs to two chunks that break at different times); on
    # the cut mesh the corners of a vertex agree. Centre and normal below then come from the frozen chunk.
    chunk_launch, has_chunk_launch = _recorded(b, space, has_space, ATTR_CHUNK_LAUNCH, 1000, 3300)
    frozen = b.set_position(chunks, selection=b.boolean("AND", moving, has_chunk_launch, x=1800, y=3150),
                            position=chunk_launch, x=2000, y=3300)
    chunks = b.switch("GEOMETRY", gi.outputs["Leave Behind"], chunks, frozen, x=2200, y=3300)
    crnd, crnd_color = b.white_noise(b.vmath("SCALE", c_rest, scale=4.77, x=1600, y=2350), x=1800, y=2350)
    thrown = b.math("SUBTRACT", 1.0, b.math("POWER", b.math("SUBTRACT", 1.0, ct, x=2000, y=2300), 2.0,
                                            x=2200, y=2300), x=2400, y=2300)
    blast = b.vmath("SCALE", c_normal, scale=b.math("MULTIPLY", gi.outputs["Chunk Force"], thrown, x=2600, y=2300),
                    x=2800, y=2300)
    drop = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Chunk Force"], -1.5, x=2600, y=2500),
                  b.math("MULTIPLY", ct, ct, x=2600, y=2650), x=2800, y=2550)
    chunk_turn = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Spin"], ct, x=2400, y=2700),
                        b.math("MULTIPLY_ADD", crnd, 2.0, -1.0, x=2400, y=2850), x=2600, y=2800)
    chunk_turned = b.rotate(position, c_center, b.vmath("SUBTRACT", crnd_color, (0.5, 0.5, 0.5), x=2600, y=2950),
                            chunk_turn, x=2800, y=2800)
    shrinking = b.math("SUBTRACT", 1.0, b.math("POWER", ct, 3.0, x=2800, y=3000), x=3000, y=3000)
    chunk_pos = b.vmath("ADD", c_center, b.vmath("SCALE", b.vmath("SUBTRACT", chunk_turned, c_center, x=3000, y=2850),
                                                 scale=shrinking, x=3200, y=2850), x=3400, y=2850)
    # they fall down in the world
    fall = _unrotate(b, me, b.combine(0.0, 0.0, drop, x=3400, y=2500), 3600, 2450)
    chunk_pos = b.vmath("ADD", b.vmath("ADD", chunk_pos, blast, x=3600, y=2600), fall, x=3800, y=2600)
    chunks = b.set_position(chunks, selection=moving, position=chunk_pos, x=4000, y=2200)
    chunks = b.delete(chunks, b.boolean("AND", b.compare("GREATER_EQUAL", ct, 0.999, x=3800, y=2100), free,
                                        x=4000, y=2050), "POINT", x=4200, y=2200)
    chunk_glow = b.math("POWER", b.math("SUBTRACT", 1.0, ct, x=3800, y=1900), 0.25, x=4000, y=1900)
    chunk_glow = b.switch("FLOAT", moving, 0.0, b.math("MULTIPLY", chunk_glow, pop, x=4100, y=1750), x=4200, y=1900)
    chunks = b.store(chunks, ATTR_EDGE, b.switch("FLOAT", gi.outputs["Flake Glow"], 0.0, chunk_glow, x=4400, y=1900),
                     x=4400, y=2200)
    old = b.switch("GEOMETRY", gi.outputs["Chunks"], old, chunks, x=4600, y=600)

    # --- Scales (Mystique): the old outfit turns away scale by scale, the first half of each scale's turn (flat to
    # edge-on); the new outfit turns in on the other side.
    scales = _flip(b, gi, field_group, geometry, d, field["Path"], radius, lock, False, gi.outputs["Edge Glow"],
                   -1200, 5000)
    old = b.switch("GEOMETRY", gi.outputs["Scales"], old, scales, x=4700, y=700)

    # --- Glitch: outside the band the old outfit is simply gone behind the edge; inside it, a slice
    # shows the old outfit whenever the dice did not pick the new one. Slices jump and flash together.
    hidden = b.switch("BOOLEAN", field["Glitching"], b.compare("LESS_EQUAL", d, radius, x=2800, y=900),
                      field["New Side"], x=3000, y=900)
    glitched = b.delete(geometry, b.boolean("AND", hidden, free, x=3000, y=750), "POINT", x=3200, y=900)
    glitched = b.set_position(glitched, field["Glitch Offset"], x=3400, y=900)
    glitched = b.store(glitched, ATTR_EDGE, field["Flash"], x=3600, y=900)
    old = b.switch("GEOMETRY", gi.outputs["Glitch"], old, glitched, x=3600, y=500)

    # --- Timeline entrances. Evolution flash: the old outfit shows whenever the new one does not, glowing (locked parts
    # stay). Rising from the shadow: it sinks into its shadow over the first half; the locked parts (head, hair) stand
    # up again with the new outfit over the second half (the new outfit has none).
    t_p = b.math("DIVIDE", radius, b.math("MAXIMUM", gi.outputs["Clamp Distance"], 1e-4, x=3400, y=6800), x=3600,
                 y=6800)
    evolve_new, evolve_glow = _evolve(b, t_p, 3800, 7000)
    evolved = b.delete(geometry, b.boolean("AND", evolve_new, free, x=5600, y=6800), "FACE", x=5800, y=6800)
    evolved = b.store(evolved, ATTR_EDGE, evolve_glow, x=6000, y=6800)
    old = b.switch("GEOMETRY", gi.outputs["Evolve"], old, evolved, x=4650, y=650)
    sinking = _shadow_amount(b, geometry, anchor, t_p, False, 3800, 7800)
    rising = _shadow_amount(b, geometry, anchor, t_p, True, 3800, 8400)
    late = b.compare("GREATER_EQUAL", t_p, 0.5, x=5600, y=8000)
    amount = b.switch("FLOAT", b.boolean("AND", late, lock, x=5800, y=8100), sinking, rising, x=6000, y=8000)
    sunk = b.delete(geometry, b.boolean("AND", b.compare("GREATER_EQUAL", t_p, 0.55, x=5600, y=8300), free, x=5800,
                                        y=8300), "FACE", x=6000, y=8300)
    sunk = _shadow_place(b, gi, me, sunk, geometry, anchor, amount, 6200, 8000)
    old = b.switch("GEOMETRY", gi.outputs["Shadow"], old, sunk, x=4660, y=600)
    # Transporter beam: it shimmers away a few faces at a time, glowing; the locked parts shimmer away with it and back
    # in with the new outfit.
    (old_shown, old_glow), (new_shown, new_glow) = _beam_faces(b, gi, anchor, t_p, 3800, 9200)
    back_in = b.boolean("AND", b.compare("GREATER_EQUAL", t_p, 0.5, x=5600, y=9200), lock, x=5800, y=9200)
    beam_shown = b.switch("BOOLEAN", back_in, old_shown, new_shown, x=6000, y=9200)
    beamed = b.delete(geometry, b.boolean("NOT", beam_shown, x=6200, y=9200), "FACE", x=6400, y=9200)
    beamed = b.store(beamed, ATTR_EDGE, b.on_domain(b.switch("FLOAT", back_in, old_glow, new_glow, x=6200, y=9000),
                                                     "FACE", x=6400, y=9000), x=6600, y=9200)
    old = b.switch("GEOMETRY", gi.outputs["Beam"], old, beamed, x=4670, y=550)

    # --- Particles: some faces release a petal / butterfly / custom object where the front passes.
    tp = lifetime(gi.outputs["Particle Flight"], -1800)
    chance = b.math("MULTIPLY", b.node("GeometryNodeInputMeshFaceArea", -800, -2000).outputs[0],
                    gi.outputs["Particle Density"], x=-600, y=-2000)
    face_seed = b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=-800, y=-2200)
    shifted = b.vmath("ADD", b.vmath("SCALE", face_seed, scale=3.7, x=-600, y=-2200), (17.0, 3.0, 5.0),
                      x=-400, y=-2200)
    lottery = b.white_noise(shifted, x=-200, y=-2200)[0]
    alive = b.compare("LESS_THAN", b.on_domain(tp, "FACE", x=-400, y=-1800), 0.999, x=-200, y=-1800)
    emit = b.boolean("AND", b.boolean("AND", started, alive, x=0, y=-1900),
                     b.compare("LESS_THAN", lottery, chance, x=0, y=-2100), x=200, y=-2000)
    # Picked before leave behind moves the faces (their areas change a little), so the same faces release.
    src = b.store(geometry, ATTR_PICK, emit, "BOOLEAN", "FACE", x=-600, y=-1500)
    src = b.store(left_behind(src, -400, -1500), ATTR_NORMAL, normal, "FLOAT_VECTOR", "FACE", x=0, y=-1600)
    to_points = b.node("GeometryNodeMeshToPoints", 400, -1600, mode="FACES")
    b.feed(to_points.inputs["Mesh"], src)
    b.feed(to_points.inputs["Selection"], b.named_attribute(ATTR_PICK, "BOOLEAN", x=200, y=-1750)[0])

    # On the points: rest position, arrival and the stored normal came along from the faces.
    point_normal = b.named_attribute(ATTR_NORMAL, "FLOAT_VECTOR", x=400, y=-1900)[0]
    prnd, prnd_color = b.white_noise(b.vmath("SCALE", anchor, scale=5.13, x=400, y=-2400), x=600, y=-2400)
    p_here = b.node("GeometryNodeInputPosition", 1400, -3400).outputs[0]
    p_flown = b.vmath("ADD", p_here, _fly(b, gi, tp, point_normal, anchor, prnd, wind, me, x=600, y=-2700),
                      x=1600, y=-3400)
    pts = b.set_position(to_points.outputs["Points"], position=b.switch(
        "VECTOR", gi.outputs["Suck"], p_flown, sucked(p_here, tp, 200, -3700), x=1700, y=-3500), x=1800, y=-1600)
    pts = _remove_attributes(b, pts, (ATTR_NORMAL, ATTR_PICK), 2000, -1600)

    # Petals tumble; butterflies stay roughly upright and turn slowly.
    two_pi = 2.0 * math.pi
    tumble = b.vmath("ADD", b.vmath("SCALE", prnd_color, scale=two_pi, x=1800, y=-2000),
                     b.combine(0.0, 0.0, b.math("MULTIPLY", gi.outputs["Spin"], tp, x=1600, y=-2200),
                               x=1800, y=-2200), x=2000, y=-2000)
    cx, cy, _cz = b.split_xyz(prnd_color, x=1600, y=-2400)
    # Tilted up to ~50 degrees so the wings face the camera more often than edge-on.
    upright = b.combine(b.math("MULTIPLY_ADD", cx, 1.8, -0.9, x=1800, y=-2400),
                        b.math("MULTIPLY_ADD", cy, 1.8, -0.9, x=1800, y=-2550),
                        b.math("MULTIPLY_ADD", prnd, two_pi,
                               b.math("MULTIPLY", gi.outputs["Spin"],
                                      b.math("MULTIPLY", tp, 0.3, x=1600, y=-2750), x=1700, y=-2700),
                               x=1800, y=-2700), x=2000, y=-2500)
    # Notes stand facing the front and only sway a little (each at its own pace).
    sway_frame = b.node("GeometryNodeInputSceneTime", 1400, -2900).outputs["Frame"]
    sway = b.combine(b.math("MULTIPLY_ADD", cx, 0.5, -0.25, x=1800, y=-2850),
                     b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY_ADD", sway_frame, 0.15,
                                                              b.math("MULTIPLY", prnd, two_pi, x=1400, y=-3050),
                                                              x=1600, y=-3000), x=1700, y=-3000), 0.25,
                            x=1800, y=-3000),
                     b.math("MULTIPLY_ADD", cy, 1.2, -0.6, x=1800, y=-3150), x=2000, y=-2850)
    rotation = b.switch("VECTOR", gi.outputs["Upright"], tumble, sway, x=2100, y=-2050)
    rotation = b.switch("VECTOR", gi.outputs["Flap"], rotation, upright, x=2200, y=-2200)
    grow = b.math("MINIMUM", b.map_range(tp, 0.0, 0.05, 0.2, 1.0, x=1800, y=-2900),
                  b.map_range(tp, 0.7, 1.0, 1.0, 0.0, x=1800, y=-3100), x=2000, y=-3000)
    size = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Particle Size"], grow, x=2200, y=-3000),
                  b.math("MULTIPLY_ADD", prnd, 0.6, 0.7, x=2200, y=-3200), x=2400, y=-3000)
    # they all pop on a beat
    size = b.math("MULTIPLY", size, b.math("MULTIPLY_ADD", beat, 0.5, 1.0, x=2400, y=-3200), x=2600, y=-3100)

    info = b.node("GeometryNodeObjectInfo", 1800, -3400, transform_space="ORIGINAL")
    b.feed(info.inputs["Object"], gi.outputs["Particle Object"])
    shape = info.outputs["Geometry"]
    # Butterflies: one instance per wing pose, picked per point and frame, so each flaps on its own.
    wing_x = b.split_xyz(position, x=1800, y=-3700)[0]
    right, rest_of = b.separate(shape, b.compare("GREATER_THAN", wing_x, 0.02, x=2000, y=-3700), "FACE",
                                x=2200, y=-3500)
    left, body = b.separate(rest_of, b.compare("LESS_THAN", wing_x, -0.02, x=2200, y=-3800), "FACE",
                            x=2400, y=-3600)
    poses = b.node("GeometryNodeGeometryToInstance", 3000, -3500)
    for i, angle in enumerate(FLAP_ANGLES):
        lifted = []
        for wing, sign in ((right, -1.0), (left, 1.0)):
            tr = b.node("GeometryNodeTransform", 2600, -3300 - 300 * i - (150 if sign > 0 else 0))
            b.feed(tr.inputs["Geometry"], wing)
            tr.inputs["Rotation"].default_value = (0.0, sign * math.radians(angle), 0.0)
            lifted.append(tr.outputs["Geometry"])
        b.ng.links.new(b.join(lifted + [body], x=2800, y=-3300 - 300 * i), poses.inputs["Geometry"])
    instance = b.switch("GEOMETRY", gi.outputs["Flap"], shape, poses.outputs["Instances"], x=3200, y=-3400)
    frame = b.node("GeometryNodeInputSceneTime", 2400, -2600).outputs["Frame"]
    pose_index = b.math("MULTIPLY_ADD", frame, gi.outputs["Flap Speed"],
                        b.math("MULTIPLY", prnd, float(len(FLAP_ANGLES)), x=2400, y=-2800), x=2600, y=-2700)
    # Code glyphs: one instance per glyph (its faces carry its number); each particle shows one at a time and changes
    # to another every few frames as it falls.
    variant = b.named_attribute(ATTR_VARIANT, "INT", x=2000, y=-4400)[0]
    glyphs = b.node("GeometryNodeGeometryToInstance", 2800, -4400)
    for k in range(GLYPHS):
        piece = b.separate(shape, b.compare("EQUAL", variant, float(k), x=2200, y=-4400 - 150 * k), "FACE",
                           x=2400, y=-4400 - 150 * k)[0]
        b.ng.links.new(piece, glyphs.inputs["Geometry"])
    instance = b.switch("GEOMETRY", gi.outputs["Glyphs"], instance, glyphs.outputs["Instances"], x=3300, y=-3500)
    glyph_index = b.math("FLOOR", b.math("MULTIPLY_ADD", frame, b.math("MULTIPLY_ADD", prnd, 0.2, 0.15, x=2400,
                                                                       y=-4100),
                                         b.math("MULTIPLY", prnd, float(GLYPHS), x=2400, y=-4250), x=2600, y=-4150),
                         x=2800, y=-4150)

    on_points = b.node("GeometryNodeInstanceOnPoints", 3200, -1600)
    b.feed(on_points.inputs["Points"], pts)
    b.feed(on_points.inputs["Instance"], instance)
    b.feed(on_points.inputs["Pick Instance"], b.boolean("OR", gi.outputs["Flap"], gi.outputs["Glyphs"], x=3000,
                                                        y=-1900))
    b.feed(on_points.inputs["Instance Index"], b.switch("FLOAT", gi.outputs["Glyphs"], pose_index, glyph_index,
                                                        x=3000, y=-2050))
    b.feed(on_points.inputs["Rotation"], rotation)
    b.feed(on_points.inputs["Scale"], size)
    # Upright in the world, also when the model turns.
    particles = b.switch("GEOMETRY", gi.outputs["Particles"], None,
                         _world_instances(b, on_points.outputs["Instances"], me, 3400, -1600), x=4200, y=-1400)

    # --- Silhouette: ahead of the edge the old outfit turns into glowing light (magical-girl style);
    # brightest right at the edge. Stored as glow^(1/8) because the material raises it to the 8th power.
    # The zone grows in with the radius (like the hologram), so nothing glows at the very start.
    sil_width = b.math("MINIMUM", gi.outputs["Silhouette Width"],
                       b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=3200, y=-150), 2.0, x=3400, y=-150),
                       x=3600, y=-150)
    lit = b.map_range(d, b.math("ADD", radius, sil_width, x=3600, y=-300), radius,
                      x=3800, y=-300, smooth=True)
    lit = b.switch("FLOAT", gi.outputs["Silhouette"], 0.0, b.math("POWER", lit, 0.125, x=4000, y=-300),
                   x=4200, y=-300)
    current = b.named_attribute(ATTR_EDGE, "FLOAT", x=3800, y=-500)[0]
    old = b.store(old, ATTR_EDGE, b.math("MAXIMUM", current, lit, x=4200, y=-500), x=4400, y=0)
    # Inner glow: 1 at the edge, fading over Inner Depth; materials light up the back faces there (the inside seen
    # where the outfit is cut open).
    cut = b.math("SUBTRACT", 1.0, b.math("DIVIDE", b.math("ABSOLUTE", age, x=4000, y=-700),
                                         b.math("MAXIMUM", gi.outputs["Inner Depth"], 1e-4, x=4000, y=-850),
                                         x=4200, y=-750, clamp=True), x=4400, y=-750)
    old = b.switch("GEOMETRY", gi.outputs["Inner Glow"], old, b.store(old, ATTR_CUT, cut, x=4500, y=200),
                   x=4600, y=150)
    # The surface ahead of the edge (computed above).
    old = b.switch("GEOMETRY", gi.outputs["Surface Ahead"], old, b.store(old, ATTR_AHEAD, ahead, x=4700, y=350),
                   x=4800, y=150)
    # The digital rain scrolls with the frame (the material reads it).
    old = b.switch("GEOMETRY", gi.outputs["Code"], old, b.store(old, ATTR_FRAME, b.node(
        "GeometryNodeInputSceneTime", 4700, 700).outputs["Frame"], x=4800, y=550), x=4850, y=150)
    venom = _venom(b, gi, venom_group, geometry, 4200, -600)

    # --- Ice crystals (with frost): they grow out of the old outfit ahead of the edge, along the normals, and are gone
    # where the edge has passed (the outfit shatters there).
    c_chance = b.math("MULTIPLY", b.node("GeometryNodeInputMeshFaceArea", 3800, -4000).outputs[0],
                      gi.outputs["Crystal Density"], x=4000, y=-4000)
    c_lottery = b.white_noise(b.vmath("ADD", b.vmath("SCALE", b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=3800,
                                                                            y=-4200), scale=2.71, x=4000, y=-4200),
                                      (3.0, 7.0, 11.0), x=4200, y=-4200), x=4400, y=-4200)[0]
    c_pick = b.boolean("AND", b.boolean("AND", b.compare("LESS_THAN", c_lottery, c_chance, x=4600, y=-4100),
                                        b.compare("GREATER_THAN", b.on_domain(ahead, "FACE", x=4400, y=-4400), 0.2,
                                                  x=4600, y=-4300), x=4800, y=-4200),
                       b.boolean("AND", b.compare("LESS_THAN", b.on_domain(age, "FACE", x=4400, y=-4600), 0.0,
                                                  x=4600, y=-4500), free, x=4800, y=-4400), x=5000, y=-4300)
    c_src = b.store(geometry, ATTR_PICK, c_pick, "BOOLEAN", "FACE", x=4800, y=-3800)
    c_src = b.store(c_src, ATTR_NORMAL, normal, "FLOAT_VECTOR", "FACE", x=5000, y=-3800)
    c_points = b.node("GeometryNodeMeshToPoints", 5200, -3800, mode="FACES")
    b.feed(c_points.inputs["Mesh"], c_src)
    b.feed(c_points.inputs["Selection"], b.named_attribute(ATTR_PICK, "BOOLEAN", x=5000, y=-4000)[0])
    c_rnd = b.white_noise(b.vmath("SCALE", anchor, scale=6.1, x=5000, y=-4600), x=5200, y=-4600)[0]
    c_size = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Crystal Size"],
                                       b.map_range(ahead, 0.2, 0.9, x=5200, y=-4800, smooth=True), x=5400, y=-4800),
                    b.math("ADD", c_rnd, 0.5, x=5400, y=-4650), x=5600, y=-4700)
    # standing along the normal, each turned about it at random
    c_align = b.node("FunctionNodeAlignEulerToVector", 5400, -4400, axis="Z")
    b.feed(c_align.inputs["Rotation"], b.combine(0.0, 0.0, b.math("MULTIPLY", c_rnd, 2.0 * math.pi, x=5200, y=-4450),
                                                 x=5300, y=-4450))
    b.feed(c_align.inputs["Vector"], b.named_attribute(ATTR_NORMAL, "FLOAT_VECTOR", x=5200, y=-4300)[0])
    c_shape = b.node("GeometryNodeObjectInfo", 5400, -3600, transform_space="ORIGINAL")
    b.feed(c_shape.inputs["Object"], gi.outputs["Crystal Object"])
    c_on = b.node("GeometryNodeInstanceOnPoints", 5800, -3800)
    b.feed(c_on.inputs["Points"], c_points.outputs["Points"])
    b.feed(c_on.inputs["Instance"], c_shape.outputs["Geometry"])
    b.feed(c_on.inputs["Rotation"], c_align.outputs[0])
    b.feed(c_on.inputs["Scale"], b.combine(b.math("MULTIPLY", c_size, 0.6, x=5600, y=-4900),
                                           b.math("MULTIPLY", c_size, 0.6, x=5600, y=-5050), c_size, x=5800, y=-4900))
    crystals = _remove_attributes(b, c_on.outputs["Instances"], (ATTR_PICK, ATTR_NORMAL), 6000, -3800)
    crystals = b.switch("GEOMETRY", gi.outputs["Crystals"], None, crystals, x=6400, y=-3800)
    tidy = b.node("GeometryNodeRemoveAttribute", 4600, 0)
    # The brooch twinkles while the old outfit flies into it.
    brooch_pt = b.node("GeometryNodePoints", 5200, -5400)
    brooch_pt.inputs["Count"].default_value = 1
    b.feed(brooch_pt.inputs["Position"], target)
    brooch_shape = b.node("GeometryNodeObjectInfo", 5200, -5700, transform_space="ORIGINAL")
    b.feed(brooch_shape.inputs["Object"], gi.outputs["Brooch Object"])
    twinkle_frame = b.node("GeometryNodeInputSceneTime", 5000, -6000).outputs["Frame"]
    shine = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Particle Size"], 2.5, x=5200, y=-6000),
                   b.math("MULTIPLY_ADD", b.math("SINE", b.math("MULTIPLY", twinkle_frame, 0.7, x=5200, y=-6150),
                                                 x=5400, y=-6150), 0.3, 0.8, x=5600, y=-6150), x=5800, y=-6050)
    shine = b.math("MULTIPLY", shine, b.math("MULTIPLY_ADD", beat, 0.5, 1.0, x=5800, y=-6250), x=6000, y=-6100)
    brooch = b.node("GeometryNodeInstanceOnPoints", 5600, -5400)
    b.feed(brooch.inputs["Points"], brooch_pt.outputs["Geometry"])
    b.feed(brooch.inputs["Instance"], brooch_shape.outputs["Geometry"])
    b.feed(brooch.inputs["Rotation"], b.combine(math.pi / 2, 0.0, 0.0, x=5400, y=-5600))
    b.feed(brooch.inputs["Scale"], shine)
    shining = b.boolean("AND", gi.outputs["Suck"], b.boolean("AND", b.compare("GREATER_THAN", radius, 0.0, x=5600,
                                                                              y=-5900),
                                                             b.compare("LESS_THAN", radius, gi.outputs["Reach"],
                                                                       x=5600, y=-6050), x=5800, y=-5950),
                        x=6000, y=-5900)
    brooch = b.switch("GEOMETRY", shining, None, _world_instances(b, brooch.outputs["Instances"], me, 5800, -5400),
                      x=6800, y=-5400)
    # With no new outfit: the transporter beam's column, the lightning over the old outfit (not its locked parts).
    column = _beam_column(b, gi, geometry, t_p, me, 3800, 10600)
    arcs = _arcs(b, gi, b.delete(geometry, lock, "FACE", x=3600, y=13000), field["Distance"], radius, beat, 3800,
                 13000)
    strike = _strike(b, gi, radius, me, 3800, 16000)
    # 1.10: the husk (it keeps the old outfit's look and materials), flames on the old outfit along the real front (also
    # while it waits to go all at once), and with no new outfit the lotus, the shockwave and the soul rings
    husk = _husk(b, gi, geometry, launch, has_launch, radius, anchor, wind, me, 3800, 19000)
    flames = _flames(b, gi, old, wave_d, radius, me, 3800, 23000)
    lotus = _lotus(b, gi, geometry, t_p, beat, 3800, 27000)
    shock = _shockwave(b, gi, geometry, radius, 3800, 35000)
    soul = _soul_rings(b, gi, geometry, radius, beat, 3800, 39000)
    b.feed(tidy.inputs["Geometry"], b.join([old, particles, venom, crystals, brooch, column, arcs, strike, husk, flames,
                                            lotus, shock, soul], x=4400, y=-150))
    tidy.inputs["Name"].default_value = ATTR_AGE
    b.feed(go.inputs["Geometry"], tidy.outputs["Geometry"])
    return ng


def build_ribbon_group():
    """Modifier for a ribbon curve (a helix around one limb, or a silk thread): draw it along the limb as the
    transformation passes from Start to End (mask radius, Lead ahead of it), then once the mask is past Fade From let it
    thin out and vanish over Linger."""
    ng = _new_group(RIBBON_GROUP, is_modifier=True)
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in RIBBON_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")

    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -1200, 0)
    go = b.node("NodeGroupOutput", 1400, 0)
    info = b.node("GeometryNodeObjectInfo", -1000, 300, transform_space="ORIGINAL")
    b.feed(info.inputs["Object"], gi.outputs["Mask"])
    radius = b.vmath("DOT_PRODUCT", info.outputs["Scale"], (1 / 3, 1 / 3, 1 / 3), x=-800, y=300)
    span = b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["End"], gi.outputs["Start"], x=-800, y=100), 1e-4,
                  x=-600, y=100)
    grow = b.math("DIVIDE", b.math("SUBTRACT", b.math("ADD", radius, gi.outputs["Lead"], x=-600, y=300),
                                   gi.outputs["Start"], x=-400, y=300), span, x=-200, y=250, clamp=True)
    gone = b.math("DIVIDE", b.math("SUBTRACT", radius, gi.outputs["Fade From"], x=-600, y=-100),
                  b.math("MAXIMUM", gi.outputs["Linger"], 1e-4, x=-600, y=-250), x=-400, y=-150, clamp=True)
    fade = b.math("SUBTRACT", 1.0, gone, x=-200, y=-150)

    trim = b.node("GeometryNodeTrimCurve", -200, 0, mode="FACTOR")
    b.feed(trim.inputs["Curve"], gi.outputs["Geometry"])
    b.feed(_enabled(trim.inputs, "Start")[0], 0.0)
    b.feed(_enabled(trim.inputs, "End")[0], grow)
    # Soft ends along the drawn part.
    along = b.node("GeometryNodeSplineParameter", 0, -300).outputs["Factor"]
    taper = b.math("MINIMUM", b.map_range(along, 0.0, 0.12, x=200, y=-250),
                   b.map_range(along, 0.88, 1.0, 1.0, 0.0, x=200, y=-450), x=400, y=-350)
    width = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Width"], fade, x=400, y=-150), taper, x=600, y=-200)
    set_radius = b.node("GeometryNodeSetCurveRadius", 200, 0)
    b.feed(set_radius.inputs["Curve"], trim.outputs["Curve"])
    b.feed(set_radius.inputs["Radius"], width)
    profile = b.node("GeometryNodeCurvePrimitiveLine", 400, 250)
    profile.inputs["Start"].default_value = (-0.5, 0.0, 0.0)
    profile.inputs["End"].default_value = (0.5, 0.0, 0.0)
    strip = b.curve_to_mesh(set_radius.outputs["Curve"], profile.outputs["Curve"], x=600, y=0)
    material = b.node("GeometryNodeSetMaterial", 800, 0)
    b.feed(material.inputs["Geometry"], strip)
    b.feed(material.inputs["Material"], gi.outputs["Material"])
    shown = b.boolean("AND", b.compare("GREATER_THAN", grow, 0.001, x=800, y=300),
                      b.compare("GREATER_THAN", fade, 0.001, x=800, y=450), x=1000, y=350)
    b.feed(go.inputs["Geometry"], b.switch("GEOMETRY", shown, None, material.outputs["Geometry"], x=1200, y=0))
    return ng


def ensure_ribbon_group():
    if not _is_current(RIBBON_GROUP):
        build_ribbon_group()
    return bpy.data.node_groups[RIBBON_GROUP]


def _circle(b, radius, resolution, x, y):
    n = b.node("GeometryNodeCurvePrimitiveCircle", x, y, mode="RADIUS")
    n.inputs["Resolution"].default_value = resolution
    b.feed(n.inputs["Radius"], radius)
    return n.outputs["Curve"]


def _star(b, points, inner, outer, x, y):
    n = b.node("GeometryNodeCurveStar", x, y)
    n.inputs["Points"].default_value = points
    b.feed(n.inputs["Inner Radius"], inner)
    b.feed(n.inputs["Outer Radius"], outer)
    return n.outputs["Curve"]


def _tube(b, curve, radius, material, x, y):
    """A curve as a thin square tube of `radius` with `material`. (The curve's own radius is set to 1 first: curve
    primitives have none, and Blender 4 sweeps a missing radius as a tiny one.)"""
    unit = b.node("GeometryNodeSetCurveRadius", x - 200, y)
    b.feed(unit.inputs["Curve"], curve)
    unit.inputs["Radius"].default_value = 1.0
    profile = _circle(b, radius, 4, x - 200, y - 200)
    n = b.node("GeometryNodeSetMaterial", x + 200, y)
    b.feed(n.inputs["Geometry"], b.curve_to_mesh(unit.outputs["Curve"], profile, x=x, y=y))
    b.feed(n.inputs["Material"], material)
    return n.outputs["Geometry"]


def build_ring_group():
    """Modifier of the front's decoration (rings.py), drawn at the front of a sweep as it crosses the body: a magic
    circle with runes (Kamen Rider Wizard), a ring of spinning sparks (Doctor Strange's portal), a glowing panel
    (Kamen Rider Ex-Aid), a sheet of TV static (WandaVision), or a comet of sparkles circling the body at the front of
    the spiral (Cinderella). Drawn in the plane of the front (u, v) and set at Start + Axis * (mask radius - Lead); it
    comes in as the front sets off and goes once it has crossed the body (Span). Glows in the glow colour (ATTR_EDGE
    carries how much), brighter on a beat."""
    ng = _new_group(RING_GROUP, is_modifier=True)
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in RING_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")
    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -2600, 0)
    go = b.node("NodeGroupOutput", 4600, 0)

    info = b.node("GeometryNodeObjectInfo", -2400, 800, transform_space="RELATIVE")
    b.feed(info.inputs["Object"], gi.outputs["Mask"])
    radius = b.vmath("DOT_PRODUCT", info.outputs["Scale"], (1 / 3, 1 / 3, 1 / 3), x=-2200, y=800)
    s = b.math("SUBTRACT", radius, gi.outputs["Lead"], x=-2000, y=800)
    span = b.math("MAXIMUM", gi.outputs["Span"], 1e-4, x=-2000, y=650)
    fade_in = b.map_range(s, 0.0, b.math("MULTIPLY", span, 0.04, x=-1800, y=600), x=-1600, y=800, smooth=True)
    end = b.math("MULTIPLY", span, 1.06, x=-1800, y=450)
    fade_out = b.map_range(s, span, end, 1.0, 0.0, x=-1600, y=600, smooth=True)
    vis = b.math("MULTIPLY", fade_in, fade_out, x=-1400, y=700)
    # the mirrored ring (split from the waist) goes as far as its own front
    back_span = b.switch("FLOAT", b.compare("GREATER_THAN", gi.outputs["Span Back"], 0.0, x=-2200, y=1100), span,
                         gi.outputs["Span Back"], x=-2000, y=1100)
    back_end = b.math("MULTIPLY", back_span, 1.06, x=-1800, y=1100)
    back_vis = b.math("MULTIPLY", fade_in, b.map_range(s, back_span, back_end, 1.0, 0.0, x=-1600, y=1100, smooth=True),
                      x=-1400, y=1100)
    last = b.switch("FLOAT", gi.outputs["Mirror"], end, b.math("MAXIMUM", end, back_end, x=-1600, y=1300), x=-1400,
                    y=1300)
    on = b.boolean("AND", b.compare("GREATER_THAN", s, 0.0, x=-1400, y=450),
                   b.compare("LESS_THAN", s, last, x=-1400, y=300), x=-1200, y=400)
    beat = b.node("GeometryNodeObjectInfo", -2400, 300, transform_space="ORIGINAL")
    b.feed(beat.inputs["Object"], gi.outputs["Beat Object"])
    pulse = b.switch("FLOAT", gi.outputs["Beat Sync"], 0.0, b.split_xyz(beat.outputs["Location"], x=-2200, y=300)[0],
                     x=-2000, y=300)
    on_beat = b.math("MULTIPLY_ADD", pulse, 0.6, 1.0, x=-1400, y=150)
    glow = b.math("MULTIPLY", vis, on_beat, x=-1200, y=200)
    back_glow = b.math("MULTIPLY", back_vis, on_beat, x=-1200, y=1000)
    big = b.math("MAXIMUM", gi.outputs["Half U"], gi.outputs["Half V"], x=-2200, y=0)
    margin = b.math("MULTIPLY", big, 0.08, x=-2000, y=0)
    size = gi.outputs["Size"]
    grow = b.math("MULTIPLY_ADD", fade_in, 0.3, 0.7, x=-1400, y=0)  # it opens up as it appears
    ring_r = b.math("MULTIPLY", b.math("MULTIPLY", b.math("ADD", big, margin, x=-1800, y=0), size, x=-1600, y=0),
                    grow, x=-1200, y=0)
    hu = b.math("MULTIPLY", b.math("MULTIPLY", b.math("ADD", gi.outputs["Half U"], margin, x=-1800, y=-200), size,
                                   x=-1600, y=-200), grow, x=-1200, y=-200)
    hv = b.math("MULTIPLY", b.math("MULTIPLY", b.math("ADD", gi.outputs["Half V"], margin, x=-1800, y=-400), size,
                                   x=-1600, y=-400), grow, x=-1200, y=-400)
    frame = b.node("GeometryNodeInputSceneTime", -2400, -600).outputs["Frame"]
    width = gi.outputs["Line Width"]
    ring_mat, screen_mat = gi.outputs["Ring Material"], gi.outputs["Screen Material"]
    z_axis = (0.0, 0.0, 1.0)

    # --- Magic circle: four circles, a hexagram, runes between the outer circles; the inner star turns the other way.
    circles = [_circle(b, b.math("MULTIPLY", ring_r, f, x=-800, y=1600 - 200 * i), 128, -600, 1600 - 200 * i)
               for i, f in enumerate((1.0, 0.94, 0.66, 0.6))]
    hexagram = _star(b, 6, b.math("MULTIPLY", ring_r, 0.94 * 0.5774, x=-800, y=800),
                     b.math("MULTIPLY", ring_r, 0.94, x=-800, y=650), -600, 800)
    octagram = _star(b, 8, b.math("MULTIPLY", ring_r, 0.45, x=-800, y=450),
                     b.math("MULTIPLY", ring_r, 0.6, x=-800, y=300), -600, 450)
    ticks = b.node("GeometryNodeMeshCircle", -600, 2400)
    ticks.inputs["Vertices"].default_value = 36
    b.feed(ticks.inputs["Radius"], b.math("MULTIPLY", ring_r, 0.97, x=-800, y=2400))
    glyph_size = b.math("MULTIPLY", ring_r, 0.022, x=-800, y=2200)
    glyph = _star(b, 3, b.math("MULTIPLY", glyph_size, 0.35, x=-600, y=2200), glyph_size, -400, 2200)
    runes = b.node("GeometryNodeInstanceOnPoints", -200, 2400)
    b.feed(runes.inputs["Points"], ticks.outputs["Mesh"])
    b.feed(runes.inputs["Instance"], glyph)
    b.feed(runes.inputs["Rotation"], b.combine(0.0, 0.0, b.math(
        "MULTIPLY", b.node("GeometryNodeInputIndex", -600, 2000).outputs[0], 2.39996, x=-400, y=2000), x=-200, y=2000))
    realized = b.node("GeometryNodeRealizeInstances", 0, 2400)
    b.feed(realized.inputs["Geometry"], runes.outputs["Instances"])
    position = b.node("GeometryNodeInputPosition", 0, 1300).outputs[0]
    outer = b.set_position(b.join(circles + [hexagram, realized.outputs["Geometry"]], x=200, y=1600),
                           position=b.rotate(position, (0.0, 0.0, 0.0), z_axis,
                                             b.math("MULTIPLY", frame, 0.012, x=0, y=1150), x=200, y=1300),
                           x=400, y=1600)
    inner = b.set_position(octagram, position=b.rotate(position, (0.0, 0.0, 0.0), z_axis,
                                                        b.math("MULTIPLY", frame, -0.02, x=0, y=1000), x=200, y=1000),
                           x=400, y=800)
    magic = _tube(b, b.join([outer, inner], x=600, y=1200), width, ring_mat, 800, 1200)

    # --- Spark ring: a fiery rim and sparks thrown off along it as it spins.
    rim = _tube(b, _circle(b, ring_r, 96, -600, -800), b.math("MULTIPLY", width, 1.3, x=-800, y=-1000), ring_mat,
                -400, -800)
    sparks = b.node("GeometryNodePoints", -600, -1400)
    sparks.inputs["Count"].default_value = 320
    k = b.node("GeometryNodeInputIndex", -1200, -1500).outputs[0]
    rnd, rnd_color = b.white_noise(b.combine(k, 0.71, 0.13, x=-1000, y=-1500), x=-800, y=-1500)
    r1, r2, r3 = b.split_xyz(rnd_color, x=-600, y=-1700)
    theta = b.math("MULTIPLY_ADD", k, 2.0 * math.pi / 320.0, b.math("MULTIPLY", frame, 0.05, x=-1000, y=-1800),
                   x=-800, y=-1800)
    age = b.math("FRACT", b.math("MULTIPLY_ADD", frame, 0.07, rnd, x=-1000, y=-2000), x=-800, y=-2000)
    cos_t, sin_t = b.math("COSINE", theta, x=-600, y=-1900), b.math("SINE", theta, x=-600, y=-2050)
    out = b.math("MULTIPLY", ring_r, b.math("ADD", b.math("MULTIPLY_ADD", r1, 0.04, 0.98, x=-600, y=-2200),
                                            b.math("MULTIPLY", age, 0.05, x=-600, y=-2350), x=-400, y=-2250),
                 x=-200, y=-2250)
    travel = b.math("MULTIPLY", b.math("MULTIPLY", age, ring_r, x=-400, y=-2450),
                    b.math("MULTIPLY_ADD", r2, 0.1, 0.05, x=-400, y=-2600), x=-200, y=-2500)
    spot = b.vmath("ADD", b.combine(b.math("MULTIPLY", cos_t, out, x=0, y=-1900), b.math("MULTIPLY", sin_t, out, x=0,
                                                                                         y=-2050),
                                    b.math("MULTIPLY", b.math("SUBTRACT", r3, 0.5, x=-200, y=-2700),
                                           b.math("MULTIPLY", ring_r, 0.03, x=-200, y=-2850), x=0, y=-2750),
                                    x=200, y=-2000),
                   b.vmath("SCALE", b.combine(b.math("MULTIPLY", sin_t, -1.0, x=0, y=-2300), cos_t, 0.0, x=200,
                                              y=-2300), scale=travel, x=400, y=-2300), x=600, y=-2100)
    b.feed(sparks.inputs["Position"], spot)
    streak = b.node("GeometryNodeMeshGrid", -200, -1100)
    for name, value in (("Size X", 1.0), ("Size Y", 1.0), ("Vertices X", 2), ("Vertices Y", 2)):
        streak.inputs[name].default_value = value
    left = b.math("SUBTRACT", 1.0, age, x=200, y=-2600)
    streaks = b.node("GeometryNodeInstanceOnPoints", 800, -1400)
    b.feed(streaks.inputs["Points"], sparks.outputs["Geometry"])
    b.feed(streaks.inputs["Instance"], streak.outputs["Mesh"])
    b.feed(streaks.inputs["Rotation"], b.combine(0.0, 0.0, b.math("ADD", theta, math.pi / 2, x=600, y=-2500),
                                                 x=800, y=-2500))
    b.feed(streaks.inputs["Scale"], b.combine(
        b.math("MULTIPLY", b.math("MULTIPLY", ring_r, 0.05, x=400, y=-2700), b.math("MULTIPLY", left,
                                                                                     b.math("ADD", r2, 0.5, x=400,
                                                                                            y=-2950), x=600, y=-2900),
               x=800, y=-2750),
        b.math("MULTIPLY", b.math("MULTIPLY", width, 1.6, x=600, y=-3100), left, x=800, y=-3050), 1.0,
        x=1000, y=-2800))
    flying = b.node("GeometryNodeRealizeInstances", 1000, -1400)
    b.feed(flying.inputs["Geometry"], streaks.outputs["Instances"])
    spark_mat = b.node("GeometryNodeSetMaterial", 1200, -1400)
    b.feed(spark_mat.inputs["Geometry"], flying.outputs["Geometry"])
    b.feed(spark_mat.inputs["Material"], ring_mat)
    spark_ring = b.join([rim, spark_mat.outputs["Geometry"]], x=1400, y=-1000)

    def sheet(scale, style, x, y):
        """A filled rectangle across the front (the screen material draws on it from ATTR_SCREEN: x and y across it in
        -1 .. 1, z the frame) with its outline."""
        quad = b.node("GeometryNodeCurvePrimitiveQuadrilateral", x, y, mode="RECTANGLE")
        half_u, half_v = (b.math("MULTIPLY", h, scale, x=x - 200, y=y - 200 * i) for i, h in enumerate((hu, hv)))
        b.feed(quad.inputs["Width"], b.math("MULTIPLY", half_u, 2.0, x=x - 100, y=y + 100))
        b.feed(quad.inputs["Height"], b.math("MULTIPLY", half_v, 2.0, x=x - 100, y=y - 100))
        fill = b.node("GeometryNodeFillCurve", x + 200, y)
        b.feed(fill.inputs["Curve"], quad.outputs["Curve"])
        px, py, _pz = b.split_xyz(b.node("GeometryNodeInputPosition", x + 200, y - 300).outputs[0], x=x + 400,
                                  y=y - 300)
        across = b.combine(b.math("DIVIDE", px, b.math("MAXIMUM", half_u, 1e-4, x=x + 400, y=y - 500), x=x + 600,
                                  y=y - 400),
                           b.math("DIVIDE", py, b.math("MAXIMUM", half_v, 1e-4, x=x + 400, y=y - 650), x=x + 600,
                                  y=y - 550), frame, x=x + 800, y=y - 450)
        screen = b.store(fill.outputs["Mesh"], ATTR_SCREEN, across, "FLOAT_VECTOR", x=x + 600, y=y)
        screen = b.store(screen, ATTR_SCREEN_STYLE, style, x=x + 800, y=y)
        mat = b.node("GeometryNodeSetMaterial", x + 1000, y)
        b.feed(mat.inputs["Geometry"], screen)
        b.feed(mat.inputs["Material"], screen_mat)
        return quad.outputs["Curve"], mat.outputs["Geometry"]

    # --- Glowing panel: a frame and a see-through screen with a grid and a scan band.
    outline, screen = sheet(1.0, 0.0, -600, -3600)
    panel = b.join([_tube(b, outline, width, ring_mat, 600, -3400), screen], x=1000, y=-3600)
    # --- TV static: a sheet of static a little larger than the body, no frame.
    _outline, static = sheet(1.12, 1.0, -600, -4400)

    def is_style(k_, y):
        return b.compare("EQUAL", gi.outputs["Style"], float(k_), x=1600, y=y)

    # --- Halo: a plain ring of light, a thin bright line in a soft wider one (Danny Phantom's rings).
    halo = b.join([_tube(b, _circle(b, ring_r, 128, -600, -6400), b.math("MULTIPLY", width, 1.2, x=-800, y=-6600),
                         ring_mat, -400, -6400),
                   _tube(b, _circle(b, b.math("MULTIPLY", ring_r, 1.015, x=-800, y=-6900), 128, -600, -6900),
                         b.math("MULTIPLY", width, 3.0, x=-800, y=-7100), ring_mat, -400, -6900)], x=600, y=-6600)
    flat = b.switch("GEOMETRY", is_style(1, -200), magic, spark_ring, x=1800, y=0)
    flat = b.switch("GEOMETRY", is_style(2, -400), flat, panel, x=2000, y=0)
    flat = b.switch("GEOMETRY", is_style(3, -600), flat, static, x=2200, y=0)
    flat = b.switch("GEOMETRY", is_style(5, -1000), flat, halo, x=2300, y=0)
    # drawn in the plane (x along u, y along v, z along the axis), moved to the front
    centre = b.vmath("ADD", gi.outputs["Start"], b.vmath("SCALE", gi.outputs["Axis"], scale=s, x=1800, y=600),
                     x=2000, y=600)

    def placed(local, x, y, at=None):
        lx, ly, lz = b.split_xyz(local, x=x, y=y)
        spot_ = b.vmath("ADD", b.vmath("SCALE", gi.outputs["U"], scale=lx, x=x + 200, y=y),
                        b.vmath("SCALE", gi.outputs["V"], scale=ly, x=x + 200, y=y - 150), x=x + 400, y=y)
        spot_ = b.vmath("ADD", spot_, b.vmath("SCALE", gi.outputs["Axis"], scale=lz, x=x + 400, y=y - 150), x=x + 600,
                        y=y)
        return b.vmath("ADD", centre if at is None else at, spot_, x=x + 800, y=y)

    here = b.node("GeometryNodeInputPosition", 2000, 300).outputs[0]
    ahead = b.set_position(flat, position=placed(here, 2200, 300), x=2600, y=0)
    ahead = b.store(ahead, ATTR_EDGE, glow, x=2700, y=0)
    ahead_on = b.switch("GEOMETRY", b.compare("LESS_THAN", s, end, x=2600, y=200), None, ahead, x=2800, y=100)
    # ... and with Mirror a second one the other way from the start
    back = b.vmath("SUBTRACT", gi.outputs["Start"], b.vmath("SCALE", gi.outputs["Axis"], scale=s, x=1800, y=900),
                   x=2000, y=900)
    behind = b.set_position(flat, position=placed(here, 2200, 1100, back), x=2600, y=-200)
    behind = b.store(behind, ATTR_EDGE, back_glow, x=2700, y=-200)
    behind_on = b.switch("GEOMETRY", b.compare("LESS_THAN", s, back_end, x=2600, y=-400), None, behind, x=2800,
                         y=-300)
    flat = b.switch("GEOMETRY", gi.outputs["Mirror"], ahead, b.join([ahead_on, behind_on], x=2900, y=-100), x=3000,
                    y=0)

    # --- Comet: a big head and a tight trail of sparkles on the last two thirds of the turn it has just come round (the
    # spiral's front: once round per pitch, starting in front of the body), standing to face the front.
    count = 72
    trail = b.node("GeometryNodePoints", 1600, -5200)
    trail.inputs["Count"].default_value = count
    k = b.node("GeometryNodeInputIndex", 1000, -5400).outputs[0]
    pitch = b.math("MAXIMUM", gi.outputs["Pitch"], 1e-4, x=1000, y=-5600)
    behind = b.math("SUBTRACT", s, b.math("MULTIPLY", k, b.math("DIVIDE", pitch, 110.0, x=1000, y=-5800), x=1200,
                                          y=-5700), x=1400, y=-5600)
    angle = b.math("MULTIPLY", b.math("DIVIDE", behind, pitch, x=1400, y=-5800), 2.0 * math.pi, x=1600, y=-5800)
    c_rnd, c_color = b.white_noise(b.combine(k, 0.29, 0.61, x=1200, y=-6000), x=1400, y=-6000)
    scatter = b.vmath("SCALE", b.vmath("SUBTRACT", c_color, (0.5, 0.5, 0.5), x=1600, y=-6100),
                      scale=b.math("MULTIPLY", b.math("DIVIDE", k, float(count), x=1600, y=-6250),
                                   b.math("MULTIPLY", ring_r, 0.06, x=1600, y=-6400), x=1800, y=-6300), x=1800, y=-6100)
    local = b.vmath("ADD", b.combine(b.math("MULTIPLY", b.math("COSINE", angle, x=1800, y=-5800), ring_r, x=2000,
                                            y=-5800),
                                     b.math("MULTIPLY", b.math("SINE", angle, x=1800, y=-5950), ring_r, x=2000,
                                            y=-5950),
                                     b.math("SUBTRACT", behind, s, x=2000, y=-6100), x=2200, y=-5900),
                    scatter, x=2400, y=-6000)
    b.feed(trail.inputs["Position"], placed(local, 2400, -5400))
    trail_pts = b.delete(trail.outputs["Geometry"], b.compare("LESS_THAN", behind, 0.0, x=2600, y=-5600), "POINT",
                         x=2800, y=-5200)
    twinkle = b.math("MULTIPLY_ADD", b.math("SINE", b.math("MULTIPLY_ADD", frame, 1.3, b.math("MULTIPLY", c_rnd,
                                                                                               2.0 * math.pi, x=2400,
                                                                                               y=-6500),
                                                           x=2600, y=-6500), x=2800, y=-6500), 0.45, 0.55, x=3000,
                         y=-6500)
    tail = b.math("POWER", b.math("SUBTRACT", 1.0, b.math("DIVIDE", k, float(count), x=2600, y=-6700), x=2800,
                                  y=-6700), 1.3, x=3000, y=-6700)
    star_size = b.math("MULTIPLY", gi.outputs["Star Size"], b.switch("FLOAT", b.compare("LESS_THAN", k, 0.5, x=3000,
                                                                                         y=-6900),
                                                                     b.math("MULTIPLY", tail, twinkle, x=3200,
                                                                            y=-6600), 3.0, x=3400, y=-6700),
                       x=3600, y=-6700)
    star = b.node("GeometryNodeObjectInfo", 2800, -4900, transform_space="ORIGINAL")
    b.feed(star.inputs["Object"], gi.outputs["Star Object"])
    stars = b.node("GeometryNodeInstanceOnPoints", 3200, -5200)
    b.feed(stars.inputs["Points"], trail_pts)
    b.feed(stars.inputs["Instance"], star.outputs["Geometry"])
    b.feed(stars.inputs["Rotation"], b.combine(math.pi / 2, b.math("MULTIPLY", c_rnd, 2.0 * math.pi, x=3000, y=-5500),
                                               0.0, x=3200, y=-5500))
    b.feed(stars.inputs["Scale"], b.math("MULTIPLY", star_size, b.math("MAXIMUM", vis, 0.0, x=3400, y=-6900),
                                         x=3600, y=-6850))
    comet = b.node("GeometryNodeRealizeInstances", 3400, -5200)
    b.feed(comet.inputs["Geometry"], stars.outputs["Instances"])
    comet_mat = b.node("GeometryNodeSetMaterial", 3600, -5200)
    b.feed(comet_mat.inputs["Geometry"], comet.outputs["Geometry"])
    b.feed(comet_mat.inputs["Material"], ring_mat)

    comet_lit = b.store(comet_mat.outputs["Geometry"], ATTR_EDGE, glow, x=3700, y=-5200)
    drawn = b.switch("GEOMETRY", is_style(4, -800), flat, comet_lit, x=3800, y=0)  # (the flat rings carry their glow)
    b.feed(go.inputs["Geometry"], b.switch("GEOMETRY", on, None, drawn, x=4200, y=0))
    return ng


def ensure_ring_group():
    if not _is_current(RING_GROUP):
        build_ring_group()
    return bpy.data.node_groups[RING_GROUP]


def build_probe_group(field_group):
    """Modifier used while the launch positions are recorded (leave behind): stores on every vertex the ages
    whose sign change is the moment to record, so Python can tell when it comes. On the old outfit both are the age
    the Base group sees (mask radius minus the noisy distance: a vertex, or on average a chunk, breaks off). On the
    new outfit (Target) the vertex age turns positive when its finale star is born, the piece age (averaged over a
    piece) when the piece takes off to fly in, its lead ahead of the edge.
    With Pieces on it outputs the mesh cut into chunks the way the Base group cuts it instead, every vertex
    and face corner tagged with its original index and every vertex with its chunk."""
    ng = _new_group(PROBE_GROUP, is_modifier=True)
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in PROBE_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")
    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -600, 0)
    go = b.node("NodeGroupOutput", 2600, 0)
    field = _field_node(b, field_group, gi, -300, -200)
    radius = field["Radius"]
    age = b.math("SUBTRACT", radius, _old_distance(b, gi, field, -300, 300), x=0, y=-200)
    # The Target group's timing: star birth (finale_t past the star's own start) and the fly-in lead.
    finale_t = b.math("DIVIDE", b.math("SUBTRACT", radius, gi.outputs["Finale Start"], x=0, y=-500),
                      b.math("MAXIMUM", gi.outputs["Finale Length"], 1e-4, x=0, y=-650), x=200, y=-550)
    span = b.math("ADD", gi.outputs["Finale Start"], gi.outputs["Sweep Width"], x=0, y=-800)
    birth = b.math("MULTIPLY", b.math("DIVIDE", field["Path"], span, x=200, y=-800, clamp=True), SWEEP_SHARE,
                   x=400, y=-800)
    birth = b.switch("FLOAT", gi.outputs["Finale Sweep"], 0.0, birth, x=600, y=-800)
    star_age = b.math("SUBTRACT", finale_t, birth, x=800, y=-600)
    lead = b.math("MINIMUM", gi.outputs["Fly Range"], b.math("MAXIMUM", radius, 0.0, x=0, y=-1000), x=200, y=-1000)
    vertex_age = b.switch("FLOAT", gi.outputs["Target"], age, star_age, x=1000, y=-300)
    piece_age = b.switch("FLOAT", gi.outputs["Target"], age, b.math("ADD", age, lead, x=400, y=-1000),
                         x=1000, y=-500)
    aged = b.store(gi.outputs["Geometry"], ATTR_AGE, vertex_age, x=1200, y=0)
    aged = b.store(aged, ATTR_PIECE_AGE, piece_age, x=1400, y=0)

    index = b.node("GeometryNodeInputIndex", -300, 500).outputs[0]
    tagged = b.store(gi.outputs["Geometry"], ATTR_VERTEX, index, "INT", "POINT", x=0, y=400)
    tagged = b.store(tagged, ATTR_CORNER, index, "INT", "CORNER", x=200, y=400)
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-300, y=900)
    position = b.node("GeometryNodeInputPosition", -300, 750).outputs[0]
    anchor = b.switch("VECTOR", has_rest, position, rest, x=-100, y=850)
    lock = b.named_attribute(ATTR_LOCK, "BOOLEAN", x=-300, y=1050)[0]
    pieces, island = _pieces(b, tagged, anchor, gi.outputs["Piece Size"], lock, 300, 900)[:2]
    pieces = b.store(pieces, ATTR_ISLAND, island, "INT", "POINT", x=2200, y=400)
    b.feed(go.inputs["Geometry"], b.switch("GEOMETRY", gi.outputs["Pieces"], aged, pieces, x=2400, y=0))
    return ng


def ensure_probe_group():
    ensure_node_groups()
    if not _is_current(PROBE_GROUP):
        build_probe_group(bpy.data.node_groups[FIELD_GROUP])
    return bpy.data.node_groups[PROBE_GROUP]


def _is_current(name):
    ng = bpy.data.node_groups.get(name)
    return ng is not None and ng.get("mmd_disperse_version") == VERSION


def ensure_node_groups():
    """Return (target_group, base_group), (re)building them if missing or outdated."""
    if not all(_is_current(name) for name in (FIELD_GROUP, VENOM_GROUP, TARGET_GROUP, BASE_GROUP)):
        field = build_field_group()
        venom = build_venom_group()
        build_target_group(field, venom)
        build_base_group(field, venom)
    return bpy.data.node_groups[TARGET_GROUP], bpy.data.node_groups[BASE_GROUP]


def input_identifiers(ng):
    """Map interface input names to the identifiers used as modifier keys."""
    if not hasattr(ng, "interface"):  # Blender 3.x
        return {sock.name: sock.identifier for sock in ng.inputs}
    return {
        item.name: item.identifier
        for item in ng.interface.items_tree
        if getattr(item, "item_type", "SOCKET") == "SOCKET" and item.in_out == "INPUT"
    }
