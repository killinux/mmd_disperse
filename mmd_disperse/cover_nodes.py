"""Geometry Nodes groups of the covers (cover.py, 1.13). Kept out of node_groups.py: that module's checksum keys the
cache of the main groups (a new one takes a couple of minutes to build), and these small groups are quick to make
whenever they are missing or out of date.

* Shatter: the glass's shards slide apart along the slash just before the moment and then fly at the camera,
  tumbling (camera space);
* Ripple: a cloth's waves running across it;
* Pieces: points that each set off at their own frame (mmdd_t0) at their own speed (mmdd_v, units a frame), slowed
  by the air (Drag), pulled by Gravity (falling no faster than the air lets them), fluttering and tumbling, an
  instance of an object each (confetti, petals, feathers);
* Balloons: the balloon cloud (cover.balloon_at's formula);
* Fan Feathers: a feather fan on a single point (the hand), its feathers spread by Open;
* Curtain: a curtain's folds, dropping (Drop: 1 its whole height) and piling up on the floor;
* Eras: the copies of the dancer of every era (tint.py), coming one after another and flying into her;
* Origin Flights: sparks, blobs of paint and tokens flying onto the dancer, each landing where a point of her body
  is now (origins.py);
* Chain Show: a mesh shown only from one frame to another (chain.py, the outfits before the old one).
"""

import math

import bpy

from . import cover
from .node_groups import ATTR_REST, _add_socket, _Builder, _enabled, _new_group, VERSION

SHATTER_GROUP = "MMDDisperse Cover Shatter"
RIPPLE_GROUP = "MMDDisperse Cover Ripple"
PIECES_GROUP = "MMDDisperse Cover Pieces"
BALLOONS_GROUP = "MMDDisperse Cover Balloons"
FAN_GROUP = "MMDDisperse Cover Fan Feathers"
CURTAIN_GROUP = "MMDDisperse Cover Curtain"
ERAS_GROUP = "MMDDisperse Eras"
ORIGINS_GROUP = "MMDDisperse Origin Flights"
CHAIN_GROUP = "MMDDisperse Chain Show"
STREAMER = "MMD Disperse Streamer"
BALLOON = "MMD Disperse Balloon"
SPARK = "MMD Disperse Spark"
SPLAT = "MMD Disperse Splat"
TOKEN = "MMD Disperse Token"
PLUME = "MMD Disperse Plume"
REVISION = 1  # bumped when one of these groups changes


def _current(name):
    ng = bpy.data.node_groups.get(name)
    return (ng is not None and ng.get("mmd_disperse_version") == VERSION
            and ng.get("mmd_disperse_cover_revision") == REVISION)


def _group(name, inputs):
    ng = _new_group(name, is_modifier=True)
    ng["mmd_disperse_cover_revision"] = REVISION
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in inputs:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")
    return ng, _Builder(ng)


def _finish(b, geometry, gi, go, x, y):
    shaded = b.node("GeometryNodeSetMaterial", x, y)
    b.feed(shaded.inputs["Geometry"], geometry)
    b.feed(shaded.inputs["Material"], gi.outputs["Material"])
    b.feed(go.inputs["Geometry"], shaded.outputs["Geometry"])


# --------------------------------------------------------------------------- the glass

def build_shatter_group():
    ng, b = _group(SHATTER_GROUP, (
        ("Moment", "NodeSocketFloat", 0.0),
        ("Rate", "NodeSocketFloat", 30.0),
        ("Slide", "NodeSocketFloat", 0.01),
        ("Spread", "NodeSocketFloat", 0.6),
        ("Slash Angle", "NodeSocketFloat", 0.0),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -1800, 0)
    go = b.node("NodeGroupOutput", 1600, 0)
    frame = b.node("GeometryNodeInputSceneTime", -1800, -300).outputs["Frame"]
    c = b.named_attribute("mmdd_c", "FLOAT_VECTOR", x=-1800, y=-450)[0]
    r = b.named_attribute("mmdd_r", "FLOAT", x=-1800, y=-600)[0]
    side = b.named_attribute("mmdd_side", "FLOAT", x=-1800, y=-750)[0]
    position = b.node("GeometryNodeInputPosition", -1800, -900).outputs[0]
    t = b.math("SUBTRACT", frame, gi.outputs["Moment"], x=-1600, y=-300)  # frames after the moment
    s = b.math("DIVIDE", t, b.math("MAXIMUM", gi.outputs["Rate"], 1.0, x=-1600, y=-450), x=-1400, y=-300)
    after = b.math("MAXIMUM", s, 0.0, x=-1200, y=-300)
    # just before the moment the two sides of the slash slide apart along it (错开)
    slide = b.map_range(s, -0.25, 0.0, 0.0, 1.0, x=-1200, y=-600, smooth=True)
    along = b.combine(b.math("COSINE", gi.outputs["Slash Angle"], x=-1400, y=-1100),
                      b.math("SINE", gi.outputs["Slash Angle"], x=-1400, y=-1250), 0.0, x=-1200, y=-1100)
    shift = b.vmath("SCALE", along, scale=b.math("MULTIPLY", b.math("MULTIPLY", slide, side, x=-1000, y=-600),
                                                 gi.outputs["Slide"], x=-800, y=-600), x=-600, y=-1000)
    # then each shard flies out from the middle and at the camera (+Z), falling a little, tumbling about its middle
    fly = b.math("MULTIPLY", after, b.math("MULTIPLY_ADD", r, 0.8, 0.8, x=-1000, y=-1400), x=-800, y=-1400)
    cx, cy, cz = b.split_xyz(c, x=-1400, y=-1600)
    out = b.combine(b.math("MULTIPLY", b.math("MULTIPLY", cx, fly, x=-1000, y=-1600), gi.outputs["Spread"], x=-800,
                           y=-1600),
                    b.math("SUBTRACT", b.math("MULTIPLY", b.math("MULTIPLY", cy, fly, x=-1000, y=-1750),
                                              gi.outputs["Spread"], x=-800, y=-1750),
                           b.math("MULTIPLY", b.math("MULTIPLY", after, after, x=-1000, y=-1900),
                                  b.math("MULTIPLY", cz, 0.25, x=-1000, y=-2050), x=-800, y=-1900), x=-600, y=-1750),
                    b.math("MULTIPLY", b.math("MULTIPLY", cz, -0.9, x=-1000, y=-2200), fly, x=-800, y=-2200),
                    x=-400, y=-1700)
    axis = b.vmath("NORMALIZE", b.combine(b.math("SINE", b.math("MULTIPLY", r, 7.3, x=-1200, y=-2400), x=-1000,
                                                 y=-2400),
                                          b.math("COSINE", b.math("MULTIPLY", r, 13.1, x=-1200, y=-2550), x=-1000,
                                                 y=-2550), 0.6, x=-800, y=-2450), x=-600, y=-2450)
    angle = b.math("MULTIPLY", after, b.math("MULTIPLY_ADD", r, 6.0, 4.0, x=-800, y=-2650), x=-600, y=-2650)
    turned = b.rotate(position, c, axis, angle, x=-400, y=-2200)
    moved = b.vmath("ADD", b.vmath("ADD", turned, out, x=-200, y=-1900), shift, x=0, y=-1500)
    geometry = b.set_position(gi.outputs["Geometry"], position=moved, x=200, y=0)
    _finish(b, geometry, gi, go, 400, 0)
    return ng


def ensure_shatter_group():
    if not _current(SHATTER_GROUP):
        build_shatter_group()
    return bpy.data.node_groups[SHATTER_GROUP]


# --------------------------------------------------------------------------- the cloth

def build_ripple_group():
    ng, b = _group(RIPPLE_GROUP, (
        ("Moment", "NodeSocketFloat", 0.0),
        ("Rate", "NodeSocketFloat", 30.0),
        ("Amount", "NodeSocketFloat", 0.06),
        ("Waves", "NodeSocketFloat", 2.5),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -1400, 0)
    go = b.node("NodeGroupOutput", 1000, 0)
    frame = b.node("GeometryNodeInputSceneTime", -1400, -300).outputs["Frame"]
    uv = b.named_attribute("mmdd_uv", "FLOAT_VECTOR", x=-1400, y=-450)[0]
    u, v, _w = b.split_xyz(uv, x=-1200, y=-450)
    seconds = b.math("DIVIDE", frame, b.math("MAXIMUM", gi.outputs["Rate"], 1.0, x=-1200, y=-300), x=-1000, y=-300)
    phase = b.math("SUBTRACT", b.math("MULTIPLY", b.math("MULTIPLY_ADD", u, gi.outputs["Waves"],
                                                         b.math("MULTIPLY", v, 0.7, x=-1000, y=-600), x=-800,
                                                         y=-500), 2.0 * math.pi, x=-600, y=-500),
                   b.math("MULTIPLY", seconds, 9.0, x=-800, y=-300), x=-400, y=-400)
    edge = b.math("MULTIPLY_ADD", b.math("ABSOLUTE", b.math("SUBTRACT", u, 0.5, x=-800, y=-800), x=-600, y=-800),
                  1.4, 0.3, x=-400, y=-800)
    curl = b.math("MULTIPLY", b.math("MULTIPLY", b.math("SUBTRACT", v, 0.5, x=-800, y=-1000),
                                     b.math("SUBTRACT", v, 0.5, x=-800, y=-1150), x=-600, y=-1050), 0.8, x=-400,
                  y=-1050)
    z = b.math("MULTIPLY", gi.outputs["Amount"], b.math("ADD", b.math("MULTIPLY", b.math("SINE", phase, x=-200, y=-400),
                                                                       edge, x=0, y=-500), curl, x=200, y=-600),
               x=400, y=-500)
    geometry = b.set_position(gi.outputs["Geometry"], offset=b.combine(0.0, 0.0, z, x=600, y=-500), x=600, y=0)
    _finish(b, geometry, gi, go, 800, 0)
    return ng


def ensure_ripple_group():
    if not _current(RIPPLE_GROUP):
        build_ripple_group()
    return bpy.data.node_groups[RIPPLE_GROUP]


# --------------------------------------------------------------------------- pieces in the air

def build_pieces_group():
    ng, b = _group(PIECES_GROUP, (
        ("Instance", "NodeSocketObject"),
        ("Size", "NodeSocketFloat", 0.1),
        ("Gravity", "NodeSocketVector", (0.0, 0.0, -0.01)),
        ("Drag", "NodeSocketFloat", 0.05),
        ("Flutter", "NodeSocketFloat", 0.05),
        ("Spin", "NodeSocketFloat", 0.2),
        ("Life", "NodeSocketFloat", 60.0),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -2000, 0)
    go = b.node("NodeGroupOutput", 2200, 0)
    frame = b.node("GeometryNodeInputSceneTime", -2000, -300).outputs["Frame"]
    t0 = b.named_attribute("mmdd_t0", "FLOAT", x=-2000, y=-450)[0]
    vel = b.named_attribute("mmdd_v", "FLOAT_VECTOR", x=-2000, y=-600)[0]
    r = b.named_attribute("mmdd_r", "FLOAT", x=-2000, y=-750)[0]
    axis = b.named_attribute("mmdd_axis", "FLOAT_VECTOR", x=-2000, y=-900)[0]
    life = b.math("MAXIMUM", gi.outputs["Life"], 1.0, x=-1800, y=-1050)
    age = b.math("SUBTRACT", frame, t0, x=-1800, y=-300)
    gone = b.boolean("OR", b.compare("LESS_THAN", age, 0.0, x=-1600, y=-300),
                     b.compare("GREATER_THAN", age, life, x=-1600, y=-450), x=-1400, y=-350)
    alive = b.delete(gi.outputs["Geometry"], gone, "POINT", x=-1400, y=0)
    k = b.math("MAXIMUM", gi.outputs["Drag"], 1e-4, x=-1600, y=-1200)
    slow = b.math("SUBTRACT", 1.0, b.math("EXPONENT", b.math("MULTIPLY", b.math("MULTIPLY", age, k, x=-1400, y=-1200),
                                                             -1.0, x=-1200, y=-1200), x=-1000, y=-1200),
                  x=-800, y=-1200)  # 1 - e^(-k age)
    flown = b.vmath("SCALE", vel, scale=b.math("DIVIDE", slow, k, x=-600, y=-1200), x=-400, y=-1000)
    # gravity with the air's drag: g / k (age - (1 - e^(-k age)) / k), falling no faster than g / k at last
    fall = b.vmath("SCALE", gi.outputs["Gravity"], scale=b.math(
        "DIVIDE", b.math("SUBTRACT", age, b.math("DIVIDE", slow, k, x=-600, y=-1400), x=-400, y=-1400), k, x=-200,
        y=-1400), x=0, y=-1300)
    ramp = b.math("MINIMUM", b.math("DIVIDE", age, 12.0, x=-800, y=-1650), 1.0, x=-600, y=-1650)
    wobble = b.vmath("SCALE", b.combine(b.math("SINE", b.math("MULTIPLY_ADD", age, 0.31, b.math("MULTIPLY", r, 6.28,
                                                                                               x=-800, y=-1800),
                                                             x=-600, y=-1800), x=-400, y=-1800),
                                        b.math("COSINE", b.math("MULTIPLY_ADD", age, 0.27, b.math("MULTIPLY", r, 3.1,
                                                                                                 x=-800, y=-1950),
                                                               x=-600, y=-1950), x=-400, y=-1950), 0.0,
                                        x=-200, y=-1850),
                     scale=b.math("MULTIPLY", gi.outputs["Flutter"], ramp, x=-200, y=-1650), x=0, y=-1700)
    moved = b.set_position(alive, offset=b.vmath("ADD", b.vmath("ADD", flown, fall, x=200, y=-1100), wobble, x=400,
                                                 y=-1300), x=400, y=0)
    share = b.math("DIVIDE", age, life, x=200, y=-300, clamp=True)
    moved = b.store(moved, "mmdd_age", share, x=600, y=0)
    info = b.node("GeometryNodeObjectInfo", 400, -500)
    b.feed(info.inputs["Object"], gi.outputs["Instance"])
    spin = b.vmath("SCALE", b.vmath("NORMALIZE", axis, x=400, y=-900),
                   scale=b.math("MULTIPLY", b.math("MULTIPLY", age, gi.outputs["Spin"], x=200, y=-1000),
                                b.math("ADD", r, 0.5, x=200, y=-1150), x=400, y=-1050), x=600, y=-900)
    grow = b.math("MULTIPLY", b.math("MINIMUM", b.math("DIVIDE", age, 3.0, x=400, y=-1300), 1.0, x=600, y=-1300),
                  b.map_range(share, 0.8, 1.0, 1.0, 0.0, x=600, y=-1450), x=800, y=-1350)
    pieces = b.node("GeometryNodeInstanceOnPoints", 800, 0)
    b.feed(pieces.inputs["Points"], moved)
    b.feed(pieces.inputs["Instance"], info.outputs["Geometry"])
    b.feed(pieces.inputs["Rotation"], spin)
    b.feed(pieces.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Size"], grow, x=1000, y=-1300))
    real = b.node("GeometryNodeRealizeInstances", 1000, 0)
    b.feed(real.inputs["Geometry"], pieces.outputs["Instances"])
    _finish(b, real.outputs["Geometry"], gi, go, 1200, 0)
    return ng


def ensure_pieces_group():
    if not _current(PIECES_GROUP):
        build_pieces_group()
    return bpy.data.node_groups[PIECES_GROUP]


def _asset(name, make, scene):
    """An object of ours to instance (in the particles' hidden collection), made on first use."""
    from . import particles

    ob = bpy.data.objects.get(name)
    if ob is not None and ob.type == "MESH":
        return ob
    ob = bpy.data.objects.new(name, make())
    particles.asset_collection(scene).objects.link(ob)
    return ob


def _streamer_mesh():
    """A strip of foil confetti: 1 long along X, a quarter of that wide, curled a little; mmdd_part 0."""
    verts, faces = [], []
    steps = 6
    for i in range(steps + 1):
        u = i / float(steps)
        x = u - 0.5
        z = 0.12 * math.sin(math.pi * u)
        verts += [(x, -0.125, z), (x, 0.125, z)]
    for i in range(steps):
        a = 2 * i
        faces.append((a, a + 2, a + 3, a + 1))
    me = bpy.data.meshes.new(STREAMER)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def ensure_streamer_object(scene):
    return _asset(STREAMER, _streamer_mesh, scene)


def ensure_balloon_object(scene):
    return _asset(BALLOON, cover._balloon_shape, scene)


def _spark_mesh():
    """A streak of a spark: 1 long along Z (its head at +Z), a tenth of that thick, a double cone."""
    verts = [(0.0, 0.0, 0.5), (0.0, 0.0, -0.5)]
    sides = 6
    for k in range(sides):
        a = 2.0 * math.pi * k / sides
        verts.append((0.05 * math.cos(a), 0.05 * math.sin(a), 0.3))
    faces = []
    for k in range(sides):
        a, b = 2 + k, 2 + (k + 1) % sides
        faces += [(0, a, b), (1, b, a)]
    me = bpy.data.meshes.new(SPARK)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _splat_mesh():
    """A splat of paint lying in the XY plane, about 1 across: a blob with lobes and a few drops round it (UV x 0 in
    the middle, 1 at the rim)."""
    verts, faces, rim = [(0.0, 0.0, 0.0)], [], []
    steps = 28
    for k in range(steps):
        a = 2.0 * math.pi * k / steps
        r = 0.42 + 0.08 * math.sin(5.0 * a + 0.7) + 0.05 * math.sin(9.0 * a + 2.1)
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
        rim.append(len(verts) - 1)
    for k in range(steps):
        faces.append((0, rim[k], rim[(k + 1) % steps]))
    for a, r, size in ((0.5, 0.62, 0.06), (1.9, 0.58, 0.045), (3.3, 0.66, 0.05), (4.6, 0.6, 0.04), (5.6, 0.7, 0.035)):
        middle = len(verts)
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
        ring = []
        for j in range(8):
            b = 2.0 * math.pi * j / 8
            verts.append((r * math.cos(a) + size * math.cos(b), r * math.sin(a) + size * math.sin(b), 0.0))
            ring.append(len(verts) - 1)
        faces += [(middle, ring[j], ring[(j + 1) % 8]) for j in range(8)]
    me = bpy.data.meshes.new(SPLAT)
    me.from_pydata(verts, [], faces)
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        x, y, _z = verts[loop.vertex_index]
        layer.data[loop.index].uv = (min(math.hypot(x, y) / 0.5, 1.0), 0.0)
    me.update()
    return me


def _token_mesh():
    """A puffy five-pointed star lying in the XY plane, 1 across, a fifth of that thick (its faces at +-Z)."""
    rim = []
    for k in range(10):
        a = 0.5 * math.pi + math.pi * k / 5.0
        r = 0.5 if k % 2 == 0 else 0.21
        rim.append((r * math.cos(a), r * math.sin(a)))
    verts = [(0.0, 0.0, 0.1), (0.0, 0.0, -0.1)] + [(x, y, 0.0) for x, y in rim]
    faces = []
    for k in range(10):
        a, b = 2 + k, 2 + (k + 1) % 10
        faces += [(0, a, b), (1, b, a)]
    me = bpy.data.meshes.new(TOKEN)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _plume_mesh(length=1.3, rows=16):
    """An ostrich plume for the feather fans, `length` long along Y (the quill at -Y, like particles' feather): a bare
    quill, then a vane widening to a broad rounded end. UV x is 1 along the shaft and 0.3 at the rim (as on the
    feather), UV y 0 .. 1 from the quill to the tip."""
    verts, uvs, faces = [], [], []
    across = (-1.0, -0.5, 0.0, 0.5, 1.0)
    for i in range(rows + 1):
        t = i / float(rows)
        if t < 0.16:
            half = 0.006
        elif t < 0.82:
            half = 0.006 + 0.19 * math.sin(0.5 * math.pi * (t - 0.16) / 0.66) ** 0.7
        else:  # the rounded end
            half = 0.196 * math.sqrt(max(1.0 - ((t - 0.82) / 0.18) ** 2, 0.0)) + 0.004
        bend = 0.03 * math.sin(math.pi * t)
        for a in across:
            verts.append(((bend + a * half) * length, (t - 0.5) * length, 0.015 * abs(a) * length))
            uvs.append((1.0 - 0.7 * abs(a), t))
    width = len(across)
    for i in range(rows):
        for j in range(width - 1):
            a = i * width + j
            faces.append((a, a + 1, a + width + 1, a + width))
    me = bpy.data.meshes.new(PLUME)
    me.from_pydata(verts, [], faces)
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        layer.data[loop.index].uv = uvs[loop.vertex_index]
    me.update()
    return me


def ensure_plume_object(scene):
    return _asset(PLUME, _plume_mesh, scene)


def ensure_token_object(scene):
    return _asset(TOKEN, _token_mesh, scene)


def ensure_spark_object(scene):
    return _asset(SPARK, _spark_mesh, scene)


def ensure_splat_object(scene):
    return _asset(SPLAT, _splat_mesh, scene)


# --------------------------------------------------------------------------- the balloons

def build_balloons_group():
    ng, b = _group(BALLOONS_GROUP, (
        ("Start", "NodeSocketFloat", 0.0),
        ("Rate", "NodeSocketFloat", 30.0),
        ("Height", "NodeSocketFloat", 1.0),
        ("Size", "NodeSocketFloat", 0.08),
        ("Life", "NodeSocketFloat", 80.0),
        ("Side", "NodeSocketVector", (1.0, 0.0, 0.0)),
        ("Balloon", "NodeSocketObject"),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -2000, 0)
    go = b.node("NodeGroupOutput", 2000, 0)
    frame = b.node("GeometryNodeInputSceneTime", -2000, -300).outputs["Frame"]
    off = b.named_attribute("mmdd_off", "FLOAT_VECTOR", x=-2000, y=-450)[0]
    speed = b.named_attribute("mmdd_k", "FLOAT", x=-2000, y=-600)[0]
    phase = b.named_attribute("mmdd_phase", "FLOAT", x=-2000, y=-750)[0]
    r = b.named_attribute("mmdd_r", "FLOAT", x=-2000, y=-900)[0]
    age = b.math("SUBTRACT", frame, gi.outputs["Start"], x=-1800, y=-300)
    gone = b.boolean("OR", b.compare("LESS_THAN", age, 0.0, x=-1600, y=-300),
                     b.compare("GREATER_THAN", age, gi.outputs["Life"], x=-1600, y=-450), x=-1400, y=-350)
    alive = b.delete(gi.outputs["Geometry"], gone, "POINT", x=-1400, y=0)
    t = b.math("DIVIDE", b.math("MAXIMUM", age, 0.0, x=-1600, y=-600),
               b.math("MAXIMUM", gi.outputs["Rate"], 1.0, x=-1600, y=-750), x=-1400, y=-650)  # seconds
    # (cover.balloon_at's formula)
    early = b.math("MINIMUM", b.math("DIVIDE", t, 0.25, x=-1200, y=-800), 1.0, x=-1000, y=-800)
    spread = b.math("MULTIPLY_ADD", b.math("MULTIPLY", early, b.math("SUBTRACT", 2.0, early, x=-800, y=-900), x=-600,
                                           y=-850), 0.65, 0.35, x=-400, y=-850)
    lift = b.math("MULTIPLY", b.math("ADD", b.math("MULTIPLY", t, cover.BALLOON_UP[0], x=-1000, y=-1050),
                                     b.math("MULTIPLY", b.math("MULTIPLY", t, t, x=-1200, y=-1200),
                                            0.5 * cover.BALLOON_UP[1], x=-1000, y=-1200), x=-800, y=-1100),
                  speed, x=-600, y=-1100)
    sway = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", b.math("MULTIPLY_ADD", t, 0.7, phase, x=-1000,
                                                                       y=-1400), 2.0 * math.pi, x=-800, y=-1400),
                                     x=-600, y=-1400), 0.03, x=-400, y=-1400)
    h = gi.outputs["Height"]
    moved = b.vmath("ADD", b.vmath("ADD", b.vmath("SCALE", off, scale=b.math("MULTIPLY", h, spread, x=-200, y=-850),
                                                  x=0, y=-800),
                                   b.combine(0.0, 0.0, b.math("MULTIPLY", h, lift, x=-200, y=-1100), x=0, y=-1050),
                                   x=200, y=-900),
                    b.vmath("SCALE", gi.outputs["Side"], scale=b.math("MULTIPLY", h, sway, x=0, y=-1400), x=200,
                            y=-1300), x=400, y=-1000)
    alive = b.set_position(alive, offset=moved, x=600, y=0)
    alive = b.store(alive, "mmdd_r", r, x=800, y=0)
    info = b.node("GeometryNodeObjectInfo", 600, -500)
    b.feed(info.inputs["Object"], gi.outputs["Balloon"])
    wobble = b.combine(b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY_ADD", t, 2.1, b.math("MULTIPLY", r, 6.28,
                                                                                              x=400, y=-1700),
                                                                x=600, y=-1700), x=800, y=-1700), 0.12, x=1000,
                              y=-1700),
                       b.math("MULTIPLY", b.math("COSINE", b.math("MULTIPLY_ADD", t, 1.7, phase, x=600, y=-1850),
                                                 x=800, y=-1850), 0.12, x=1000, y=-1850),
                       b.math("MULTIPLY", r, 6.28, x=1000, y=-2000), x=1200, y=-1800)
    grow = b.math("MINIMUM", b.math("DIVIDE", t, 0.12, x=800, y=-1200), 1.0, x=1000, y=-1200)
    pieces = b.node("GeometryNodeInstanceOnPoints", 1000, 0)
    b.feed(pieces.inputs["Points"], alive)
    b.feed(pieces.inputs["Instance"], info.outputs["Geometry"])
    b.feed(pieces.inputs["Rotation"], wobble)
    b.feed(pieces.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Size"], grow, x=1200, y=-1200))
    real = b.node("GeometryNodeRealizeInstances", 1400, 0)
    b.feed(real.inputs["Geometry"], pieces.outputs["Instances"])
    _finish(b, real.outputs["Geometry"], gi, go, 1600, 0)
    return ng


def ensure_balloons_group():
    if not _current(BALLOONS_GROUP):
        build_balloons_group()
    return bpy.data.node_groups[BALLOONS_GROUP]


# --------------------------------------------------------------------------- the feather fans

def build_fan_group():
    ng, b = _group(FAN_GROUP, (
        ("Feather", "NodeSocketObject"),
        ("Radius", "NodeSocketFloat", 1.0),
        ("Count", "NodeSocketInt", 22),
        ("Spread", "NodeSocketFloat", 1.6),
        ("Lean", "NodeSocketFloat", 0.0),
        ("Open", "NodeSocketFloat", 1.0),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -1600, 0)
    go = b.node("NodeGroupOutput", 1800, 0)
    line = b.node("GeometryNodeMeshLine", -1400, 0)
    b.feed(line.inputs["Count"], gi.outputs["Count"])
    index = b.node("GeometryNodeInputIndex", -1400, -300).outputs[0]
    share = b.math("DIVIDE", index, b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["Count"], 1.0, x=-1200, y=-450),
                                           1.0, x=-1000, y=-450), x=-800, y=-300)  # 0 .. 1 across the fan
    theta = b.math("ADD", b.math("ADD", 0.5 * math.pi, gi.outputs["Lean"], x=-800, y=-600),
                   b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Open"], gi.outputs["Spread"], x=-800, y=-750),
                          b.math("MULTIPLY_ADD", share, 2.0, -1.0, x=-800, y=-900), x=-600, y=-800), x=-400, y=-700)
    radius = gi.outputs["Radius"]
    half = b.math("MULTIPLY", radius, 0.5, x=-400, y=-1000)
    # each feather's middle half a radius out from the hand along its own way, a hair nearer the camera than the last
    place = b.combine(b.math("MULTIPLY", b.math("COSINE", theta, x=-200, y=-700), half, x=0, y=-700),
                      b.math("MULTIPLY", b.math("SINE", theta, x=-200, y=-850), half, x=0, y=-850),
                      b.math("MULTIPLY", share, b.math("MULTIPLY", radius, 0.01, x=-200, y=-1050), x=0, y=-1000),
                      x=200, y=-800)
    points = b.set_position(line.outputs["Mesh"], position=place, x=200, y=0)
    info = b.node("GeometryNodeObjectInfo", 200, -400)
    b.feed(info.inputs["Object"], gi.outputs["Feather"])
    turn = b.combine(0.0, 0.0, b.math("SUBTRACT", theta, 0.5 * math.pi, x=200, y=-1200), x=400, y=-1200)
    pieces = b.node("GeometryNodeInstanceOnPoints", 600, 0)
    b.feed(pieces.inputs["Points"], points)
    b.feed(pieces.inputs["Instance"], info.outputs["Geometry"])
    b.feed(pieces.inputs["Rotation"], turn)
    b.feed(pieces.inputs["Scale"], b.math("DIVIDE", radius, 1.3, x=400, y=-1400))  # (the feather is 1.3 long)
    real = b.node("GeometryNodeRealizeInstances", 900, 0)
    b.feed(real.inputs["Geometry"], pieces.outputs["Instances"])
    _finish(b, real.outputs["Geometry"], gi, go, 1200, 0)
    return ng


def ensure_fan_feathers_group():
    if not _current(FAN_GROUP):
        build_fan_group()
    return bpy.data.node_groups[FAN_GROUP]


# --------------------------------------------------------------------------- the curtain

def build_curtain_group():
    ng, b = _group(CURTAIN_GROUP, (
        ("Drop", "NodeSocketFloat", 0.0),
        ("Folds", "NodeSocketFloat", 9.0),
        ("Depth", "NodeSocketFloat", 0.03),
        ("Floor", "NodeSocketFloat", -0.5),
        ("Aspect", "NodeSocketFloat", 1.0),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -1600, 0)
    go = b.node("NodeGroupOutput", 1600, 0)
    position = b.node("GeometryNodeInputPosition", -1600, -300).outputs[0]
    uv = b.named_attribute("mmdd_uv", "FLOAT_VECTOR", x=-1600, y=-450)[0]
    u, _v, _w = b.split_xyz(uv, x=-1400, y=-450)
    px, py, _pz = b.split_xyz(position, x=-1400, y=-300)
    folds = b.math("MULTIPLY", gi.outputs["Depth"], b.math("SINE", b.math("MULTIPLY", u, b.math(
        "MULTIPLY", gi.outputs["Folds"], 2.0 * math.pi, x=-1200, y=-700), x=-1000, y=-650), x=-800, y=-650),
        x=-600, y=-650)
    low = b.math("SUBTRACT", py, gi.outputs["Drop"], x=-1200, y=-300)
    floor = gi.outputs["Floor"]
    under = b.math("MAXIMUM", b.math("SUBTRACT", floor, low, x=-1000, y=-400), 0.0, x=-800, y=-400)  # how far past
    # the floor, in its own heights: laid down in front of where it stood, in heaps
    y = b.math("ADD", b.math("MAXIMUM", low, floor, x=-600, y=-300),
               b.math("MULTIPLY", b.math("MINIMUM", under, 0.05, x=-600, y=-500), 0.4, x=-400, y=-500), x=-200, y=-350)
    heap = b.math("MULTIPLY", b.math("ABSOLUTE", b.math("SINE", b.math("MULTIPLY", under, 23.0, x=-600, y=-900),
                                                        x=-400, y=-900), x=-200, y=-900),
                  b.math("MULTIPLY", gi.outputs["Depth"], 1.5, x=-400, y=-1050), x=0, y=-950)
    z = b.math("ADD", b.math("ADD", folds, b.math("MULTIPLY", b.math("MULTIPLY", under, gi.outputs["Aspect"], x=-400,
                                                                     y=-1200), 0.35, x=-200, y=-1200), x=0, y=-700),
               b.math("MULTIPLY", heap, b.math("MINIMUM", b.math("MULTIPLY", under, 40.0, x=-200, y=-1350), 1.0,
                                               x=0, y=-1350), x=200, y=-1100), x=400, y=-800)
    geometry = b.set_position(gi.outputs["Geometry"], position=b.combine(px, y, z, x=600, y=-400), x=800, y=0)
    _finish(b, geometry, gi, go, 1000, 0)
    return ng


def ensure_curtain_group():
    if not _current(CURTAIN_GROUP):
        build_curtain_group()
    return bpy.data.node_groups[CURTAIN_GROUP]


# --------------------------------------------------------------------------- the dancers of every era (tint.py)

def build_eras_group():
    """Copies of the Dancer (its geometry as it is now, posed, in our object's space) on our points (each an offset
    from her, mmdd_era its age 1 .., mmdd_t0 the frame it comes): each fades in from its frame over Fade frames,
    from Converge Start to Converge End they all fly into her, and then they are gone. The copies carry mmdd_era and
    mmdd_era_fade (how much of them shows), which the tint turns into the colours of their age."""
    ng, b = _group(ERAS_GROUP, (
        ("Dancer", "NodeSocketObject"),
        ("Converge Start", "NodeSocketFloat", 0.0),
        ("Converge End", "NodeSocketFloat", 10.0),
        ("Fade", "NodeSocketFloat", 8.0),
    ))
    gi = b.node("NodeGroupInput", -1600, 0)
    go = b.node("NodeGroupOutput", 1400, 0)
    frame = b.node("GeometryNodeInputSceneTime", -1600, -300).outputs["Frame"]
    t0 = b.named_attribute("mmdd_t0", "FLOAT", x=-1600, y=-450)[0]
    position = b.node("GeometryNodeInputPosition", -1600, -600).outputs[0]
    age = b.math("SUBTRACT", frame, t0, x=-1400, y=-300)
    gone = b.boolean("OR", b.compare("LESS_THAN", age, 0.0, x=-1200, y=-300),
                     b.compare("GREATER_EQUAL", frame, gi.outputs["Converge End"], x=-1200, y=-450), x=-1000, y=-350)
    alive = b.delete(gi.outputs["Geometry"], gone, "POINT", x=-1000, y=0)
    together = b.map_range(frame, gi.outputs["Converge Start"], gi.outputs["Converge End"], 0.0, 1.0, x=-1200,
                           y=-700, smooth=True)
    moved = b.set_position(alive, position=b.vmath("SCALE", position, scale=b.math("SUBTRACT", 1.0, together,
                                                                                   x=-1000, y=-700),
                                                   x=-800, y=-650), x=-600, y=0)
    shown = b.math("MULTIPLY", b.math("DIVIDE", age, b.math("MAXIMUM", gi.outputs["Fade"], 1.0, x=-1000, y=-950),
                                      x=-800, y=-900, clamp=True),
                   b.math("MULTIPLY_ADD", together, -0.6, 1.0, x=-800, y=-1050), x=-600, y=-950)
    moved = b.store(moved, "mmdd_era_fade", shown, x=-400, y=0)
    info = b.node("GeometryNodeObjectInfo", -400, -500, transform_space="RELATIVE")
    b.feed(info.inputs["Object"], gi.outputs["Dancer"])
    copies = b.node("GeometryNodeInstanceOnPoints", 0, 0)
    b.feed(copies.inputs["Points"], moved)
    b.feed(copies.inputs["Instance"], info.outputs["Geometry"])
    real = b.node("GeometryNodeRealizeInstances", 400, 0)
    b.feed(real.inputs["Geometry"], copies.outputs["Instances"])
    b.feed(go.inputs["Geometry"], real.outputs["Geometry"])
    return ng


def ensure_eras_group():
    if not _current(ERAS_GROUP):
        build_eras_group()
    return bpy.data.node_groups[ERAS_GROUP]


# --------------------------------------------------------------------------- the flights onto her (origins.py)

def build_origins_group():
    """Things flying onto the dancer: our points each set off at mmdd_t0 from mmdd_from and land at mmdd_t1 on her
    body, on the vertex of Dancer nearest to mmdd_rest (its rest position, in Dancer's own space) where it is now (it
    moves with the dance). Each is shown Appear frames before it sets off (growing in), flies in an arc Arc high head
    first, sits on her skin when it lands and pops (Burst times bigger at the peak of Pop frames), and is gone mmdd_stay
    frames after landing (shrinking away over the last Pop frames of them). An instance of Shape each, Size big;
    mmdd_age (0 .. 1 over the pop) for the material, which With Material sets (else the shape keeps its own)."""
    ng, b = _group(ORIGINS_GROUP, (
        ("Dancer", "NodeSocketObject"),
        ("Shape", "NodeSocketObject"),
        ("Size", "NodeSocketFloat", 0.05),
        ("Arc", "NodeSocketFloat", 0.2),
        ("Appear", "NodeSocketFloat", 6.0),
        ("Pop", "NodeSocketFloat", 6.0),
        ("Burst", "NodeSocketFloat", 1.5),
        ("With Material", "NodeSocketBool", True),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -2600, 0)
    go = b.node("NodeGroupOutput", 2000, 0)
    frame = b.node("GeometryNodeInputSceneTime", -2600, -300).outputs["Frame"]
    t0 = b.named_attribute("mmdd_t0", "FLOAT", x=-2600, y=-450)[0]
    t1 = b.named_attribute("mmdd_t1", "FLOAT", x=-2600, y=-600)[0]
    start = b.named_attribute("mmdd_from", "FLOAT_VECTOR", x=-2600, y=-750)[0]
    rest = b.named_attribute("mmdd_rest", "FLOAT_VECTOR", x=-2600, y=-900)[0]
    stay = b.named_attribute("mmdd_stay", "FLOAT", x=-2600, y=-1050)[0]
    age = b.math("SUBTRACT", frame, t1, x=-2400, y=-600)  # frames since it landed
    shown = b.math("SUBTRACT", t0, gi.outputs["Appear"], x=-2400, y=-450)
    gone = b.boolean("OR", b.compare("LESS_THAN", frame, shown, x=-2200, y=-450),
                     b.compare("GREATER_THAN", age, stay, x=-2200, y=-600), x=-2000, y=-500)
    alive = b.delete(gi.outputs["Geometry"], gone, "POINT", x=-2000, y=0)
    # the spot on her body: the vertex nearest to the rest position, where it is now
    info = b.node("GeometryNodeObjectInfo", -2400, -1200, transform_space="RELATIVE")
    b.feed(info.inputs["Object"], gi.outputs["Dancer"])
    on_rest = b.set_position(info.outputs["Geometry"],
                             position=b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-2400, y=-1400)[0],
                             x=-2200, y=-1200)
    nearest = b.node("GeometryNodeSampleNearest", -2000, -1200, domain="POINT")
    b.feed(nearest.inputs["Geometry"], on_rest)
    b.feed(nearest.inputs["Sample Position"], rest)

    def now(value, x, y):
        n = b.node("GeometryNodeSampleIndex", x, y, data_type="FLOAT_VECTOR", domain="POINT")
        b.feed(n.inputs["Geometry"], info.outputs["Geometry"])
        b.feed(_enabled(n.inputs, "Value")[0], value)
        b.feed(n.inputs["Index"], nearest.outputs["Index"])
        return _enabled(n.outputs, "Value")[0]

    spot = now(b.node("GeometryNodeInputPosition", -2000, -1500).outputs[0], -1800, -1300)
    normal = b.vmath("NORMALIZE", now(b.node("GeometryNodeInputNormal", -2000, -1700).outputs[0], -1800, -1600),
                     x=-1600, y=-1600)
    # the flight: from the start to the spot in an arc, a little off her skin at the end
    u = b.math("DIVIDE", b.math("SUBTRACT", frame, t0, x=-1800, y=-300),
               b.math("MAXIMUM", b.math("SUBTRACT", t1, t0, x=-1800, y=-450), 1.0, x=-1600, y=-450),
               x=-1600, y=-300, clamp=True)
    bump = b.math("MULTIPLY", b.math("MULTIPLY", u, b.math("SUBTRACT", 1.0, u, x=-1400, y=-400), x=-1200, y=-350),
                  4.0, x=-1000, y=-350)
    way = b.vmath("SUBTRACT", spot, start, x=-1400, y=-800)
    line = b.vmath("ADD", start, b.vmath("SCALE", way, scale=u, x=-1200, y=-800), x=-1000, y=-800)
    lift = b.combine(0.0, 0.0, b.math("MULTIPLY", bump, gi.outputs["Arc"], x=-800, y=-500), x=-600, y=-500)
    off = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Size"], 0.3, x=-1000,
                                                                   y=-1100), u, x=-800, y=-1100), x=-600, y=-1100)
    position = b.vmath("ADD", b.vmath("ADD", line, lift, x=-400, y=-700), off, x=-200, y=-800)
    moved = b.set_position(alive, position=position, x=0, y=0)
    # head first while it flies (along the line, rising then falling with the arc), on her skin once it has landed
    rise = b.math("MULTIPLY", b.math("MULTIPLY_ADD", u, -8.0, 4.0, x=-800, y=-1300), gi.outputs["Arc"], x=-600,
                  y=-1300)
    heading = b.vmath("ADD", way, b.combine(0.0, 0.0, rise, x=-400, y=-1300), x=-200, y=-1300)
    landed = b.compare("GREATER_EQUAL", age, 0.0, x=-400, y=-1500)
    aim = b.switch("VECTOR", landed, heading, normal, x=0, y=-1400)
    align = b.node("FunctionNodeAlignEulerToVector", 200, -1400, axis="Z")
    b.feed(align.inputs["Vector"], aim)
    pop_frames = b.math("MAXIMUM", gi.outputs["Pop"], 1.0, x=-400, y=-1800)
    pop = b.math("DIVIDE", age, pop_frames, x=-200, y=-1700, clamp=True)
    grow = b.math("DIVIDE", b.math("SUBTRACT", frame, shown, x=-400, y=-2000),
                  b.math("MAXIMUM", gi.outputs["Appear"], 1.0, x=-400, y=-2150), x=-200, y=-2000, clamp=True)
    peak = b.math("MULTIPLY", b.math("MULTIPLY", pop, b.math("SUBTRACT", 1.0, pop, x=0, y=-1850), x=200, y=-1800),
                  4.0, x=400, y=-1800)
    burst = b.math("MULTIPLY_ADD", peak, gi.outputs["Burst"], 1.0, x=600, y=-1800)
    late = b.math("SUBTRACT", age, b.math("SUBTRACT", stay, pop_frames, x=0, y=-2300), x=200, y=-2250)
    fade = b.math("SUBTRACT", 1.0, b.math("DIVIDE", late, pop_frames, x=400, y=-2250, clamp=True), x=600, y=-2250)
    scale = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Size"], grow, x=800, y=-2000), burst,
                                      x=1000, y=-1900), fade, x=1200, y=-2000)
    moved = b.store(moved, "mmdd_age", pop, x=400, y=0)
    shape = b.node("GeometryNodeObjectInfo", 400, -500)
    b.feed(shape.inputs["Object"], gi.outputs["Shape"])
    flights = b.node("GeometryNodeInstanceOnPoints", 800, 0)
    b.feed(flights.inputs["Points"], moved)
    b.feed(flights.inputs["Instance"], shape.outputs["Geometry"])
    b.feed(flights.inputs["Rotation"], align.outputs["Rotation"])
    b.feed(flights.inputs["Scale"], scale)
    real = b.node("GeometryNodeRealizeInstances", 1000, 0)
    b.feed(real.inputs["Geometry"], flights.outputs["Instances"])
    shaded = b.node("GeometryNodeSetMaterial", 1200, -200)
    b.feed(shaded.inputs["Geometry"], real.outputs["Geometry"])
    b.feed(shaded.inputs["Material"], gi.outputs["Material"])
    b.feed(go.inputs["Geometry"], b.switch("GEOMETRY", gi.outputs["With Material"], real.outputs["Geometry"],
                                           shaded.outputs["Geometry"], x=1500, y=0))
    return ng


def ensure_origins_group():
    if not _current(ORIGINS_GROUP):
        build_origins_group()
    return bpy.data.node_groups[ORIGINS_GROUP]


# --------------------------------------------------------------------------- the outfits of the chain (chain.py)

def build_chain_group():
    """The geometry as it is from frame From to before frame To, nothing at other frames."""
    ng = _new_group(CHAIN_GROUP, is_modifier=True)
    ng["mmd_disperse_cover_revision"] = REVISION
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    _add_socket(ng, "From", "INPUT", "NodeSocketFloat", 0.0)
    _add_socket(ng, "To", "INPUT", "NodeSocketFloat", 1.0e6)
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")
    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -600, 0)
    go = b.node("NodeGroupOutput", 400, 0)
    frame = b.node("GeometryNodeInputSceneTime", -600, -300).outputs["Frame"]
    hidden = b.boolean("OR", b.compare("LESS_THAN", frame, gi.outputs["From"], x=-400, y=-300),
                       b.compare("GREATER_EQUAL", frame, gi.outputs["To"], x=-400, y=-450), x=-200, y=-350)
    b.feed(go.inputs["Geometry"], b.switch("GEOMETRY", hidden, gi.outputs["Geometry"], None, x=0, y=0))
    return ng


def ensure_chain_group():
    if not _current(CHAIN_GROUP):
        build_chain_group()
    return bpy.data.node_groups[CHAIN_GROUP]


def remove_unused():
    """Our shapes to instance and our groups, once no cover uses them."""
    for name in (STREAMER, BALLOON, SPARK, SPLAT, TOKEN, PLUME):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            me = ob.data
            bpy.data.objects.remove(ob)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    for name in (SHATTER_GROUP, RIPPLE_GROUP, PIECES_GROUP, BALLOONS_GROUP, FAN_GROUP, CURTAIN_GROUP, ERAS_GROUP,
                 ORIGINS_GROUP, CHAIN_GROUP):
        ng = bpy.data.node_groups.get(name)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
