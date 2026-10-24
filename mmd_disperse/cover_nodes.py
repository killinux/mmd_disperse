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
* Chain Show: a mesh shown only from one frame to another (chain.py, the outfits before the old one);
* Print Supports and Print Lasers (1.14, printer.py): the supports under what hangs over, printed with the layers and
  breaking into cubes once the print is done, and the laser heads shooting at the layer being printed.
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
PRINT_SUPPORTS_GROUP = "MMDDisperse Print Supports"
PRINT_LASERS_GROUP = "MMDDisperse Print Lasers"
STREAMER = "MMD Disperse Streamer"
BALLOON = "MMD Disperse Balloon"
SPARK = "MMD Disperse Spark"
SPLAT = "MMD Disperse Splat"
TOKEN = "MMD Disperse Token"
PLUME = "MMD Disperse Plume"
ROD = "MMD Disperse Print Rod"
TIP = "MMD Disperse Print Tip"
BEAM = "MMD Disperse Laser Beam"
CUBE = "MMD Disperse Print Cube"
LASER_HEAD = "MMD Disperse Laser Head"
TOTEM_GROUP = "MMDDisperse Totem Mist"
PUPPET_STRINGS_GROUP = "MMDDisperse Puppet Strings"
FLATTEN_GROUP = "MMDDisperse Shadow Flatten"
RODS_GROUP = "MMDDisperse Shadow Rods"
MIRROR_GROUP = "MMDDisperse Mirror Copy"
PHOTO_GROUP = "MMDDisperse Photo Figure"
PUFF = "MMD Disperse Totem Puff"
REVISION = 10  # bumped when one of these groups changes


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
        ("Floor", "NodeSocketFloat", -1.0e9),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -2000, 0)
    go = b.node("NodeGroupOutput", 2400, 0)
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
    # what falls onto the floor (the slot machine's coins) lies there flat; nothing is below it by default
    px, py, pz = b.split_xyz(b.node("GeometryNodeInputPosition", 400, -150).outputs[0], x=500, y=-150)
    landed = b.compare("LESS_THAN", pz, gi.outputs["Floor"], x=600, y=-250)
    moved = b.store(moved, "mmdd_landed", landed, data_type="BOOLEAN", x=500, y=0)  # (before it is put on it)
    moved = b.set_position(moved, position=b.combine(px, py, b.math("MAXIMUM", pz, gi.outputs["Floor"], x=600,
                                                                     y=-150), x=700, y=-150), x=600, y=100)
    share = b.math("DIVIDE", age, life, x=200, y=-300, clamp=True)
    moved = b.store(moved, "mmdd_age", share, x=700, y=0)
    info = b.node("GeometryNodeObjectInfo", 400, -500)
    b.feed(info.inputs["Object"], gi.outputs["Instance"])
    spin = b.vmath("SCALE", b.vmath("NORMALIZE", axis, x=400, y=-900),
                   scale=b.math("MULTIPLY", b.math("MULTIPLY", age, gi.outputs["Spin"], x=200, y=-1000),
                                b.math("ADD", r, 0.5, x=200, y=-1150), x=400, y=-1050), x=600, y=-900)
    flat = b.combine(0.0, 0.0, b.math("MULTIPLY", r, 6.2832, x=400, y=-750), x=600, y=-750)
    spin = b.switch("VECTOR", b.named_attribute("mmdd_landed", "BOOLEAN", x=600, y=-600)[0], spin, flat, x=800,
                    y=-850)
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


# --------------------------------------------------------------------------- 1.14: the print (printer.py)

def _ring(radius, z, sides):
    return [(radius * math.cos(2.0 * math.pi * k / sides), radius * math.sin(2.0 * math.pi * k / sides), z)
            for k in range(sides)]


def _tube(name, rings, sides=6, cap_bottom=True, cap_top=True):
    """A mesh of `rings` ((radius, z) from the bottom up) joined side by side, closed at either end."""
    verts, faces = [], []
    for radius, z in rings:
        verts += _ring(radius, z, sides)
    for i in range(len(rings) - 1):
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    if cap_bottom:
        faces.append(tuple(reversed(range(sides))))
    if cap_top:
        top = (len(rings) - 1) * sides
        faces.append(tuple(range(top, top + sides)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _rod_mesh():
    """The column of a support of the print: 1 long up Z from 0, radius 1."""
    return _tube(ROD, ((1.0, 0.0), (1.0, 1.0)))


def _tip_mesh():
    """The tip of a support where it holds the outfit up: 1 long up Z from 0, narrowing from radius 1 to 0.3."""
    return _tube(TIP, ((1.0, 0.0), (0.3, 1.0)))


def _beam_mesh():
    """A laser beam: 1 long up Z from 0, radius 1, open at the ends."""
    return _tube(BEAM, ((1.0, 0.0), (1.0, 1.0)), sides=8, cap_bottom=False, cap_top=False)


def _cube_mesh():
    """A cube 1 across about its middle."""
    verts = [(x * 0.5, y * 0.5, z * 0.5) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me = bpy.data.meshes.new(CUBE)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _laser_head_mesh():
    """A laser head: a box 1 across and 1.6 long behind its lens (looking up +Z from 0), mmdd_lens 1 on the lens."""
    box = [(x * 0.5, y * 0.5, z) for x in (-1, 1) for y in (-1, 1) for z in (-1.6, 0.0)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    lens = _ring(0.32, 0.0, 12) + _ring(0.3, 0.12, 12)
    verts = box + lens
    for k in range(12):
        a, b = 8 + k, 8 + (k + 1) % 12
        faces.append((a, b, b + 12, a + 12))
    faces.append(tuple(range(20, 32)))
    me = bpy.data.meshes.new(LASER_HEAD)
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new("mmdd_lens", "FLOAT", "POINT")
    attr.data.foreach_set("value", [0.0] * 8 + [1.0] * 24)
    me.update()
    return me


def ensure_rod_object(scene):
    return _asset(ROD, _rod_mesh, scene)


def ensure_tip_object(scene):
    return _asset(TIP, _tip_mesh, scene)


def ensure_beam_object(scene):
    return _asset(BEAM, _beam_mesh, scene)


def ensure_cube_object(scene):
    return _asset(CUBE, _cube_mesh, scene)


def ensure_laser_head_object(scene):
    return _asset(LASER_HEAD, _laser_head_mesh, scene)


def _layer_radius(b, gi, x, y):
    info = b.node("GeometryNodeObjectInfo", x, y, transform_space="RELATIVE")
    b.feed(info.inputs["Object"], gi.outputs["Mask"])
    return b.vmath("DOT_PRODUCT", info.outputs["Scale"], (1 / 3, 1 / 3, 1 / 3), x=x + 200, y=y)


def _instances(b, points, shape, rotation, scale, x, y):
    n = b.node("GeometryNodeInstanceOnPoints", x, y)
    b.feed(n.inputs["Points"], points)
    b.feed(n.inputs["Instance"], shape)
    b.feed(n.inputs["Rotation"], rotation)
    b.feed(n.inputs["Scale"], scale)
    return n.outputs["Instances"]


def _realize(b, geometry, x, y):
    n = b.node("GeometryNodeRealizeInstances", x, y)
    b.feed(n.inputs["Geometry"], geometry)
    return n.outputs["Geometry"]


def _aim(b, vector, x, y):
    n = b.node("FunctionNodeAlignEulerToVector", x, y, axis="Z")
    b.feed(n.inputs["Vector"], vector)
    return n.outputs["Rotation"]


def _shape(b, gi, name, x, y):
    n = b.node("GeometryNodeObjectInfo", x, y)
    b.feed(n.inputs["Object"], gi.outputs[name])
    return n.outputs["Geometry"]


def build_print_supports_group():
    """The supports of the print (printer.py): each of our points is a support from mmdd_bottom (three vertices of
    Twin, mmdd_bottom_w their weights) up to mmdd_top (the same), where those points of the dancing body are now. It
    is printed from its foot as the front (the Mask's size) goes from mmdd_a0 to mmdd_a1, glowing hot (mmdd_heat 1)
    and cooling over the next four layers; at Snap + mmdd_r * Spread it snaps off and breaks into cubes that fall
    (Gravity: units a frame squared) and shrink away over Crumble frames. Rod and Cube are the shapes, Size the
    support's radius."""
    ng, b = _group(PRINT_SUPPORTS_GROUP, (
        ("Twin", "NodeSocketObject"),
        ("Mask", "NodeSocketObject"),
        ("Layer", "NodeSocketFloat", 0.1),
        ("Size", "NodeSocketFloat", 0.01),
        ("Snap", "NodeSocketFloat", 100.0),
        ("Spread", "NodeSocketFloat", 10.0),
        ("Crumble", "NodeSocketFloat", 20.0),
        ("Gravity", "NodeSocketFloat", 0.01),
        ("Rod", "NodeSocketObject"),
        ("Tip", "NodeSocketObject"),
        ("Cube", "NodeSocketObject"),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -3200, 0)
    go = b.node("NodeGroupOutput", 2800, 0)
    frame = b.node("GeometryNodeInputSceneTime", -3200, -300).outputs["Frame"]
    radius = _layer_radius(b, gi, -3200, 400)
    twin = b.node("GeometryNodeObjectInfo", -3200, -2000, transform_space="RELATIVE")
    b.feed(twin.inputs["Object"], gi.outputs["Twin"])
    position = b.node("GeometryNodeInputPosition", -3200, -2200).outputs[0]

    def at(name, x, y):
        """The point of the twin three of its vertices (mmdd_<name>) make with their weights (mmdd_<name>_w)."""
        ix, iy, iz = b.split_xyz(b.named_attribute("mmdd_" + name, "FLOAT_VECTOR", x=x, y=y)[0], x=x + 200, y=y)
        wx, wy, wz = b.split_xyz(b.named_attribute("mmdd_%s_w" % name, "FLOAT_VECTOR", x=x, y=y - 200)[0],
                                 x=x + 200, y=y - 200)
        total = None
        for k, (index, weight) in enumerate(((ix, wx), (iy, wy), (iz, wz))):
            n = b.node("GeometryNodeSampleIndex", x + 400, y - 200 * k, data_type="FLOAT_VECTOR", domain="POINT")
            b.feed(n.inputs["Geometry"], twin.outputs["Geometry"])
            b.feed(_enabled(n.inputs, "Value")[0], position)
            b.feed(n.inputs["Index"], b.math("ROUND", index, x=x + 300, y=y - 200 * k - 100))
            part = b.vmath("SCALE", _enabled(n.outputs, "Value")[0], scale=weight, x=x + 600, y=y - 200 * k)
            total = part if total is None else b.vmath("ADD", total, part, x=x + 800, y=y - 200 * k)
        return total

    top = at("top", -3000, -1000)
    bottom = at("bottom", -3000, -1700)
    a0 = b.named_attribute("mmdd_a0", "FLOAT", x=-3000, y=-400)[0]
    a1 = b.named_attribute("mmdd_a1", "FLOAT", x=-3000, y=-550)[0]
    r = b.named_attribute("mmdd_r", "FLOAT", x=-3000, y=-700)[0]
    grown = b.math("DIVIDE", b.math("SUBTRACT", radius, a0, x=-2600, y=300),
                   b.math("MAXIMUM", b.math("SUBTRACT", a1, a0, x=-2600, y=150), 1e-4, x=-2400, y=150),
                   x=-2200, y=300, clamp=True)
    t = b.math("SUBTRACT", frame, b.math("MULTIPLY_ADD", r, gi.outputs["Spread"], gi.outputs["Snap"], x=-2600,
                                         y=-300), x=-2400, y=-300)  # frames since it snapped off
    broken = b.compare("GREATER_EQUAL", t, 0.0, x=-2200, y=-300)
    gone = b.boolean("OR", b.compare("LESS_THAN", radius, a0, x=-2200, y=0),
                     b.compare("GREATER_THAN", t, gi.outputs["Crumble"], x=-2200, y=-150), x=-2000, y=0)
    heat = b.math("SUBTRACT", 1.0, b.math("DIVIDE", b.math("SUBTRACT", radius, a1, x=-2400, y=600),
                                          b.math("MULTIPLY", gi.outputs["Layer"], 4.0, x=-2400, y=750),
                                          x=-2200, y=600, clamp=True), x=-2000, y=600)
    way = b.vmath("SUBTRACT", top, bottom, x=-1800, y=-1300)
    length = b.vmath("LENGTH", way, x=-1600, y=-1300)
    aim = _aim(b, way, -1600, -1100)
    alive = b.delete(gi.outputs["Geometry"], gone, "POINT", x=-1800, y=0)
    alive = b.set_position(alive, position=bottom, x=-1600, y=0)
    alive = b.store(alive, "mmdd_heat", heat, x=-1400, y=0)
    alive = b.store(alive, "mmdd_t", t, x=-1200, y=0)
    alive = b.store(alive, "mmdd_way", way, data_type="FLOAT_VECTOR", x=-1000, y=0)
    # standing: the column as far up as it is printed, and its tip (the last stretch, a quarter of it at most) once
    # the print gets there
    standing = b.delete(alive, broken, "POINT", x=-800, y=300)
    size = gi.outputs["Size"]
    tip = b.math("MINIMUM", b.math("MULTIPLY", length, 0.25, x=-1200, y=900), b.math("MULTIPLY", size, 6.0, x=-1200,
                                                                                    y=1050), x=-1000, y=900)
    printed = b.math("MULTIPLY", grown, length, x=-1200, y=450)
    below_tip = b.math("SUBTRACT", length, tip, x=-1000, y=1050)
    rods = _instances(b, standing, _shape(b, gi, "Rod", -1000, 600), aim,
                      b.combine(size, size, b.math("MINIMUM", printed, below_tip, x=-1000, y=450), x=-800, y=450),
                      -600, 300)
    tip_part = b.math("DIVIDE", b.math("SUBTRACT", printed, below_tip, x=-800, y=1200),
                      b.math("MAXIMUM", tip, 1e-6, x=-800, y=1350), x=-600, y=1200, clamp=True)
    tips = b.delete(standing, b.compare("LESS_EQUAL", tip_part, 0.0, x=-600, y=1350), "POINT", x=-400, y=900)
    tips = b.set_position(tips, offset=b.vmath("SCALE", b.vmath("NORMALIZE", way, x=-600, y=1500),
                                               scale=below_tip, x=-400, y=1500), x=-200, y=900)
    tips = _instances(b, tips, _shape(b, gi, "Tip", -200, 1200), aim,
                      b.combine(size, size, b.math("MULTIPLY", tip, tip_part, x=-200, y=1100), x=0, y=1100), 200,
                      900)
    rods = b.join([rods, tips], x=400, y=600)
    # broken: cubes along it, falling, drifting and shrinking
    bits = b.delete(alive, b.boolean("NOT", broken, x=-1000, y=-500), "POINT", x=-800, y=-300)
    line = b.node("GeometryNodeMeshLine", -1000, -700, mode="OFFSET")
    line.inputs["Count"].default_value = 6
    b.feed(line.inputs["Start Location"], (0.0, 0.0, 1.0 / 12.0))
    b.feed(line.inputs["Offset"], (0.0, 0.0, 1.0 / 6.0))
    bits = _realize(b, _instances(b, bits, line.outputs["Mesh"], aim,
                                  b.combine(1.0, 1.0, length, x=-800, y=-650), -600, -300), -400, -300)
    t_bit = b.named_attribute("mmdd_t", "FLOAT", x=-400, y=-600)[0]
    jitter, spin = b.white_noise(b.combine(b.node("GeometryNodeInputIndex", -600, -900).outputs[0], 0.37, 0.71,
                                           x=-400, y=-900), x=-200, y=-900)
    jx, jy, jz = b.split_xyz(spin, x=0, y=-900)
    drop = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", t_bit, t_bit, x=0, y=-600),
                                     gi.outputs["Gravity"], x=200, y=-600),
                  b.math("MULTIPLY_ADD", jitter, 0.6, 0.35, x=200, y=-750), x=400, y=-600)
    drift = b.math("MULTIPLY", t_bit, b.math("MULTIPLY", size, 0.6, x=200, y=-1100), x=400, y=-1100)
    offset = b.combine(b.math("MULTIPLY", b.math("SUBTRACT", jx, 0.5, x=200, y=-1250), drift, x=400, y=-1250),
                       b.math("MULTIPLY", b.math("SUBTRACT", jy, 0.5, x=200, y=-1400), drift, x=400, y=-1400),
                       b.math("MULTIPLY", drop, -1.0, x=600, y=-600), x=800, y=-1000)
    bits = b.set_position(bits, offset=offset, x=1000, y=-300)
    left = b.math("SUBTRACT", 1.0, b.math("DIVIDE", t_bit, b.math("MAXIMUM", gi.outputs["Crumble"], 1.0, x=800,
                                                                   y=-1500), x=1000, y=-1500, clamp=True),
                  x=1200, y=-1500)
    bits = b.store(bits, "mmdd_heat", b.math("MULTIPLY", left, 0.8, x=1200, y=-1650), x=1200, y=-300)
    turn = b.vmath("SCALE", spin, scale=b.math("MULTIPLY", t_bit, 0.25, x=1000, y=-1800), x=1200, y=-1800)
    cube_size = b.math("MULTIPLY", b.math("MULTIPLY", size, 2.4, x=1200, y=-2000), left, x=1400, y=-2000)
    bits = _instances(b, bits, _shape(b, gi, "Cube", 1200, -2200), turn, cube_size, 1400, -300)
    joined = _realize(b, b.join([rods, bits], x=1800, y=0), 2000, 0)
    _finish(b, joined, gi, go, 2400, 0)
    return ng


def ensure_print_supports_group():
    if not _current(PRINT_SUPPORTS_GROUP):
        build_print_supports_group()
    return bpy.data.node_groups[PRINT_SUPPORTS_GROUP]


def build_print_lasers_group():
    """The laser heads of the print (printer.py), one on each of our points, shooting while the front (the Mask's
    size) is between Lead and Lead + Span + Layer: each frame each head aims at a point of the layer being printed at
    random (a vertex of Twin with that layer's disperse_arrival, not locked), its beam stopping where it first meets
    the dancer, a glowing spot there. Beam and Spot are sizes, Head the shape of a head (looking up its +Z), Head Size
    its size; mmdd_part says what is what for the material: 0 a head, 1 a beam, 2 a spot."""
    ng, b = _group(PRINT_LASERS_GROUP, (
        ("Twin", "NodeSocketObject"),
        ("Mask", "NodeSocketObject"),
        ("Lead", "NodeSocketFloat", 0.0),
        ("Layer", "NodeSocketFloat", 0.1),
        ("Span", "NodeSocketFloat", 1.0),
        ("Beam", "NodeSocketFloat", 0.005),
        ("Spot", "NodeSocketFloat", 0.03),
        ("Beam Shape", "NodeSocketObject"),
        ("Head", "NodeSocketObject"),
        ("Head Size", "NodeSocketFloat", 0.1),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -3000, 0)
    go = b.node("NodeGroupOutput", 2600, 0)
    frame = b.node("GeometryNodeInputSceneTime", -3000, -300).outputs["Frame"]
    radius = _layer_radius(b, gi, -3000, 400)
    s = b.math("SUBTRACT", radius, gi.outputs["Lead"], x=-2600, y=400)
    layer = b.math("MAXIMUM", gi.outputs["Layer"], 1e-5, x=-2600, y=250)
    now = b.math("ADD", b.math("MULTIPLY", b.math("FLOOR", b.math("ADD", b.math("DIVIDE", s, layer, x=-2400, y=400),
                                                                  1e-4, x=-2200, y=400), x=-2000, y=400),
                               layer, x=-1800, y=400), gi.outputs["Lead"], x=-1600, y=400)
    printing = b.boolean("AND", b.compare("GREATER_EQUAL", s, 0.0, x=-2400, y=700),
                         b.compare("LESS_EQUAL", s, b.math("ADD", gi.outputs["Span"], layer, x=-2600, y=850),
                                   x=-2400, y=850), x=-2200, y=750)
    twin = b.node("GeometryNodeObjectInfo", -3000, -1200, transform_space="RELATIVE")
    b.feed(twin.inputs["Object"], gi.outputs["Twin"])
    arrival = b.named_attribute("disperse_arrival", "FLOAT", x=-3000, y=-1500)[0]
    lock = b.named_attribute("disperse_lock", "BOOLEAN", x=-3000, y=-1650)[0]
    in_layer = b.boolean("AND", b.compare("LESS_THAN", b.math("ABSOLUTE", b.math("SUBTRACT", arrival, now, x=-2800,
                                                                                  y=-1500), x=-2600, y=-1500),
                                          b.math("MULTIPLY", layer, 0.5, x=-2600, y=-1350), x=-2400, y=-1450),
                         b.boolean("NOT", lock, x=-2600, y=-1650), x=-2200, y=-1500)
    slab = b.separate(twin.outputs["Geometry"], in_layer, "POINT", x=-2000, y=-1300)[0]
    size = b.node("GeometryNodeAttributeDomainSize", -1800, -1500, component="MESH")
    b.feed(size.inputs["Geometry"], slab)
    count = size.outputs["Point Count"]
    pick = b.node("FunctionNodeRandomValue", -1800, -1000, data_type="FLOAT")
    b.feed(pick.inputs["Seed"], frame)
    index = b.math("MINIMUM", b.math("FLOOR", b.math("MULTIPLY", _enabled(pick.outputs, "Value")[0], count, x=-1600,
                                                     y=-1000), x=-1400, y=-1000),
                   b.math("SUBTRACT", count, 1.0, x=-1600, y=-1150), x=-1200, y=-1000)
    sample = b.node("GeometryNodeSampleIndex", -1000, -1200, data_type="FLOAT_VECTOR", domain="POINT")
    b.feed(sample.inputs["Geometry"], slab)
    b.feed(_enabled(sample.inputs, "Value")[0], b.node("GeometryNodeInputPosition", -1200, -1300).outputs[0])
    b.feed(sample.inputs["Index"], index)
    target = _enabled(sample.outputs, "Value")[0]
    head = b.node("GeometryNodeInputPosition", -1000, -600).outputs[0]
    way = b.vmath("SUBTRACT", target, head, x=-800, y=-800)
    ray = b.node("GeometryNodeRaycast", -600, -1000)
    b.feed(ray.inputs["Target Geometry"], twin.outputs["Geometry"])
    b.feed(ray.inputs["Source Position"], head)
    b.feed(ray.inputs["Ray Direction"], way)
    b.feed(ray.inputs["Ray Length"], b.math("ADD", b.vmath("LENGTH", way, x=-800, y=-1100), 0.01, x=-600, y=-1300))
    end = b.switch("VECTOR", ray.outputs["Is Hit"], target, ray.outputs["Hit Position"], x=-400, y=-900)
    beam_way = b.vmath("SUBTRACT", end, head, x=-200, y=-800)
    shooting = b.boolean("AND", printing, b.compare("GREATER_THAN", count, 0.5, x=-1600, y=-1700), x=-200, y=-1600)
    heads = b.delete(gi.outputs["Geometry"], b.boolean("NOT", shooting, x=0, y=-1600), "POINT", x=200, y=0)
    heads = b.store(heads, "mmdd_end", end, data_type="FLOAT_VECTOR", x=400, y=0)
    heads = b.store(heads, "mmdd_way", beam_way, data_type="FLOAT_VECTOR", x=600, y=0)
    stored_way = b.named_attribute("mmdd_way", "FLOAT_VECTOR", x=600, y=-300)[0]
    stored_end = b.named_attribute("mmdd_end", "FLOAT_VECTOR", x=600, y=-450)[0]
    stored_aim = _aim(b, stored_way, 800, -300)
    beam = gi.outputs["Beam"]
    beams = _instances(b, heads, _shape(b, gi, "Beam Shape", 800, 400), stored_aim,
                       b.combine(beam, beam, b.vmath("LENGTH", stored_way, x=800, y=200), x=1000, y=200), 1200, 300)
    beams = b.store(beams, "mmdd_part", 1.0, domain="INSTANCE", x=1400, y=300)
    flicker = b.white_noise(b.combine(frame, b.node("GeometryNodeInputIndex", 800, -900).outputs[0], 0.5, x=1000,
                                      y=-900), x=1200, y=-900)[0]
    sphere = b.node("GeometryNodeMeshIcoSphere", 1000, -1200)
    sphere.inputs["Radius"].default_value = 1.0
    sphere.inputs["Subdivisions"].default_value = 2
    spots = _instances(b, b.set_position(heads, position=stored_end, x=1000, y=-600), sphere.outputs["Mesh"], None,
                       b.math("MULTIPLY", gi.outputs["Spot"], b.math("MULTIPLY_ADD", flicker, 0.6, 0.7, x=1200,
                                                                     y=-1050), x=1400, y=-1050), 1400, -600)
    spots = b.store(spots, "mmdd_part", 2.0, domain="INSTANCE", x=1600, y=-600)
    housings = _instances(b, heads, _shape(b, gi, "Head", 800, 800), stored_aim, gi.outputs["Head Size"], 1200, 800)
    housings = b.store(housings, "mmdd_part", 0.0, domain="INSTANCE", x=1400, y=800)
    joined = _realize(b, b.join([housings, beams, spots], x=1800, y=0), 2000, 0)
    _finish(b, joined, gi, go, 2300, 0)
    return ng


def ensure_print_lasers_group():
    if not _current(PRINT_LASERS_GROUP):
        build_print_lasers_group()
    return bpy.data.node_groups[PRINT_LASERS_GROUP]


# --------------------------------------------------------------------------- 1.15: the totem in the mist (totem.py)

def _puff_mesh():
    """A puff of the totem's mist: a round blob (an icosphere) of radius 1, shaded smooth."""
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    me = bpy.data.meshes.new(PUFF)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()
    return me


def ensure_puff_object(scene):
    return _asset(PUFF, _puff_mesh, scene)


def build_totem_group():
    """The totem's puffs (totem.py's points) by the frame: they turn in their swirl (a vortex in the X/Z plane at
    mmdd_depth, or round the Z axis near the floor: mmdd_ground) from Start, are drawn into their places in the shape
    (mmdd_target) round Gather (each a little earlier or later: mmdd_delay), stir there, and from Release blow away
    along mmdd_way and a noise, growing and fading out over Blow Time. mmdd_fade (how bright each is) for the
    material; a Puff on each, realised."""
    ng, b = _group(TOTEM_GROUP, (
        ("Start", "NodeSocketFloat", 0.0),
        ("Gather", "NodeSocketFloat", 60.0),
        ("Gather Time", "NodeSocketFloat", 12.0),
        ("Release", "NodeSocketFloat", 90.0),
        ("Blow Time", "NodeSocketFloat", 36.0),
        ("Fps", "NodeSocketFloat", 30.0),
        ("Height", "NodeSocketFloat", 1.6),
        ("Puff", "NodeSocketObject"),
        ("Size", "NodeSocketFloat", 0.1),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -2600, 0)
    go = b.node("NodeGroupOutput", 2400, 0)
    frame = b.node("GeometryNodeInputSceneTime", -2600, -300).outputs["Frame"]
    height = gi.outputs["Height"]
    r, lift, phase = b.split_xyz(b.named_attribute("mmdd_orbit", "FLOAT_VECTOR", x=-2600, y=-450)[0], x=-2400,
                                 y=-450)
    speed = b.named_attribute("mmdd_speed", "FLOAT", x=-2600, y=-650)[0]
    depth = b.named_attribute("mmdd_depth", "FLOAT", x=-2600, y=-800)[0]
    ground = b.named_attribute("mmdd_ground", "FLOAT", x=-2600, y=-950)[0]
    delay = b.named_attribute("mmdd_delay", "FLOAT", x=-2600, y=-1100)[0]
    seed = b.named_attribute("mmdd_seed", "FLOAT", x=-2600, y=-1250)[0]
    way = b.named_attribute("mmdd_way", "FLOAT_VECTOR", x=-2600, y=-1400)[0]
    target = b.named_attribute("mmdd_target", "FLOAT_VECTOR", x=-2600, y=-1550)[0]
    gather, span = gi.outputs["Gather"], gi.outputs["Gather Time"]
    # the swirl (mmdd_speed: radians a second), turning on through the gathering, so it spirals in
    seconds = b.math("DIVIDE", b.math("SUBTRACT", frame, gather, x=-2200, y=-600),
                     b.math("MAXIMUM", gi.outputs["Fps"], 1.0, x=-2200, y=-750), x=-2000, y=-600)
    angle = b.math("ADD", phase, b.math("MULTIPLY", speed, seconds, x=-1800, y=-600), x=-1600, y=-500)
    wobble = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY_ADD", frame, 0.077, b.math("MULTIPLY", phase, 3.0,
                                                                                            x=-2000, y=-800),
                                                      x=-1800, y=-800), x=-1600, y=-800),
                    b.math("MULTIPLY", height, 0.04, x=-1600, y=-950), x=-1400, y=-850)
    c, sn = b.math("COSINE", angle, x=-1400, y=-450), b.math("SINE", angle, x=-1400, y=-600)
    rc, rs = b.math("MULTIPLY", r, c, x=-1200, y=-450), b.math("MULTIPLY", r, sn, x=-1200, y=-600)
    vortex = b.combine(rc, depth, b.math("ADD", b.math("ADD", lift, rs, x=-1000, y=-650), wobble, x=-800, y=-650),
                       x=-600, y=-500)
    ring = b.combine(rc, rs, b.math("MULTIPLY_ADD", wobble, 0.3, lift, x=-1000, y=-800), x=-600, y=-750)
    orbit = b.switch("VECTOR", b.compare("GREATER_THAN", ground, 0.5, x=-800, y=-950), vortex, ring, x=-400, y=-600)
    # drawn into the shape round Gather, each in its turn, stirring there
    s0 = b.math("ADD", b.math("SUBTRACT", gather, b.math("MULTIPLY", span, 0.5, x=-1400, y=-1100), x=-1200, y=-1100),
                b.math("MULTIPLY", b.math("SUBTRACT", delay, 0.5, x=-1400, y=-1250), b.math("MULTIPLY", span, 0.6,
                                                                                            x=-1400, y=-1400),
                       x=-1200, y=-1300), x=-1000, y=-1200)
    g = b.map_range(frame, s0, b.math("ADD", s0, span, x=-800, y=-1300), x=-600, y=-1200, smooth=True)
    stir = b.node("ShaderNodeTexNoise", -1200, -1600, noise_dimensions="4D")
    b.feed(stir.inputs["Vector"], b.vmath("SCALE", target, scale=b.math("DIVIDE", 1.5, height, x=-1400, y=-1700),
                                          x=-1400, y=-1600))
    b.feed(stir.inputs["W"], b.math("MULTIPLY", frame, 0.02, x=-1400, y=-1800))
    stir.inputs["Scale"].default_value = 1.0
    held = b.vmath("ADD", target, b.vmath("SCALE", b.vmath("SUBTRACT", stir.outputs["Color"], (0.5, 0.5, 0.5),
                                                           x=-1000, y=-1600),
                                          scale=b.math("MULTIPLY", height, 0.04, x=-1000, y=-1750), x=-800, y=-1600),
                   x=-600, y=-1550)
    here = b.vmath("ADD", orbit, b.vmath("SCALE", b.vmath("SUBTRACT", held, orbit, x=-400, y=-1300), scale=g,
                                         x=-200, y=-1300), x=0, y=-900)
    # blown away from Release on (one side of the shape first: mmdd_delay)
    blow = gi.outputs["Blow Time"]
    b0 = b.math("ADD", gi.outputs["Release"], b.math("MULTIPLY", delay, b.math("MULTIPLY", blow, 0.35, x=-400,
                                                                                y=-2000), x=-200, y=-2000),
                x=0, y=-2000)
    gone = b.map_range(frame, b0, b.math("ADD", b0, blow, x=200, y=-2100), x=400, y=-2000, smooth=True)
    wind = b.node("ShaderNodeTexNoise", 0, -2300)
    b.feed(wind.inputs["Vector"], b.vmath("SCALE", here, scale=b.math("DIVIDE", 0.8, height, x=-200, y=-2400),
                                          x=-200, y=-2300))
    wind.inputs["Scale"].default_value = 1.0
    gust = b.vmath("ADD", b.vmath("ADD", b.vmath("SCALE", way, scale=0.6, x=200, y=-2500),
                                  b.vmath("SUBTRACT", wind.outputs["Color"], (0.5, 0.5, 0.5), x=200, y=-2300), x=400,
                                  y=-2400), (0.7, 0.0, 0.3), x=600, y=-2400)
    away = b.vmath("SCALE", gust, scale=b.math("MULTIPLY", b.math("POWER", gone, 1.4, x=600, y=-2100),
                                               b.math("MULTIPLY", height, 1.3, x=600, y=-2250), x=800, y=-2150),
                   x=1000, y=-2300)
    moved = b.set_position(gi.outputs["Geometry"], position=b.vmath("ADD", here, away, x=1200, y=-1000), x=200, y=0)
    # how bright: coming up from Start, brighter in the shape, fading out as it blows away
    rise = b.map_range(frame, gi.outputs["Start"], b.math("ADD", gi.outputs["Start"], 15.0, x=200, y=-400), x=400,
                       y=-400, smooth=True)
    fade = b.math("MULTIPLY", b.math("MULTIPLY", rise, b.math("SUBTRACT", 1.0, gone, x=400, y=-600), x=600,
                                     y=-500), b.math("MULTIPLY_ADD", g, 0.92, 0.08, x=600, y=-700), x=800, y=-550)
    moved = b.store(moved, "mmdd_fade", fade, x=600, y=0)
    moved = b.delete(moved, b.compare("LESS_THAN", fade, 0.002, x=800, y=-300), "POINT", x=800, y=0)
    size = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Size"], b.math("MULTIPLY_ADD", seed, 0.6, 0.7, x=800,
                                                                             y=-800), x=1000, y=-800),
                  b.math("MULTIPLY", b.math("SUBTRACT", 1.0, b.math("MULTIPLY", g, 0.6, x=800, y=-1000), x=1000,
                                            y=-1000),
                         b.math("MULTIPLY_ADD", gone, 1.5, 1.0, x=1000, y=-1150), x=1200, y=-1050), x=1400, y=-900)
    spin = b.combine(b.math("MULTIPLY", seed, 6.2832, x=1200, y=-1300),
                     b.math("MULTIPLY", b.math("FRACT", b.math("MULTIPLY", seed, 7.13, x=1000, y=-1450), x=1100,
                                               y=-1450), 6.2832, x=1200, y=-1450),
                     b.math("MULTIPLY", b.math("FRACT", b.math("MULTIPLY", seed, 3.71, x=1000, y=-1600), x=1100,
                                               y=-1600), 6.2832, x=1200, y=-1600), x=1400, y=-1400)
    info = b.node("GeometryNodeObjectInfo", 1200, -300)
    b.feed(info.inputs["Object"], gi.outputs["Puff"])
    puffs = b.node("GeometryNodeInstanceOnPoints", 1600, 0)
    b.feed(puffs.inputs["Points"], moved)
    b.feed(puffs.inputs["Instance"], info.outputs["Geometry"])
    b.feed(puffs.inputs["Rotation"], spin)
    b.feed(puffs.inputs["Scale"], size)
    real = b.node("GeometryNodeRealizeInstances", 1800, 0)
    b.feed(real.inputs["Geometry"], puffs.outputs["Instances"])
    _finish(b, real.outputs["Geometry"], gi, go, 2100, 0)
    return ng


def ensure_totem_group():
    if not _current(TOTEM_GROUP):
        build_totem_group()
    return bpy.data.node_groups[TOTEM_GROUP]


def remove_totem_assets():
    """The totem's puff and group (totem.py), once no totem uses them (and no ghost the puff: ghost.py's mist)."""
    ob = bpy.data.objects.get(PUFF)
    if ob is not None and not any(o.get("mmd_disperse_totem") is not None or o.get("mmd_disperse_ghost") is not None
                                  for o in bpy.data.objects):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    ng = bpy.data.node_groups.get(TOTEM_GROUP)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)


# --------------------------------------------------------------------------- 1.16: the marionette's strings (puppet.py)

PUPPET_STRINGS = 5


def build_puppet_strings_group():
    """The marionette's strings: one from each Attach point of the Bar (in the bar's own space) down to its Hook. From
    Show (a little later for each) it drops down to the hook over Grow, sagging a little as it goes taut; at its Snap
    frame its lower end whips up to the bar over Whip, curling, and it thins away; none after Gone. Tubes of Radius."""
    inputs = [("Bar", "NodeSocketObject")]
    for k in range(PUPPET_STRINGS):
        inputs += [("Hook %d" % k, "NodeSocketObject"), ("Attach %d" % k, "NodeSocketVector", (0.0, 0.0, 0.0)),
                   ("Snap %d" % k, "NodeSocketFloat", 100.0)]
    inputs += [("Show", "NodeSocketFloat", 0.0), ("Grow", "NodeSocketFloat", 10.0), ("Whip", "NodeSocketFloat", 6.0),
               ("Radius", "NodeSocketFloat", 0.002), ("Sag", "NodeSocketFloat", 0.03), ("Gone", "NodeSocketFloat", 1e6),
               ("Material", "NodeSocketMaterial")]
    ng, b = _group(PUPPET_STRINGS_GROUP, inputs)
    gi = b.node("NodeGroupInput", -2400, 0)
    go = b.node("NodeGroupOutput", 1600, 0)
    frame = b.node("GeometryNodeInputSceneTime", -2400, -300).outputs["Frame"]
    bar = b.node("GeometryNodeObjectInfo", -2200, 300)
    bar.transform_space = "RELATIVE"
    b.feed(bar.inputs["Object"], gi.outputs["Bar"])
    alive = b.compare("LESS_THAN", frame, gi.outputs["Gone"], x=-2200, y=-450)
    tubes = []
    for k in range(PUPPET_STRINGS):
        y = -900 * k
        hook = b.node("GeometryNodeObjectInfo", -2200, y - 200)
        hook.transform_space = "RELATIVE"
        b.feed(hook.inputs["Object"], gi.outputs["Hook %d" % k])
        # where it hangs from: the attach point turned and scaled with the bar
        turned = b.node("ShaderNodeVectorRotate", -2000, y)
        turned.rotation_type = "EULER_XYZ"
        b.feed(turned.inputs["Vector"], b.vmath("MULTIPLY", gi.outputs["Attach %d" % k], bar.outputs["Scale"],
                                                x=-2200, y=y + 100))
        b.feed(turned.inputs["Rotation"], bar.outputs["Rotation"])
        top = b.vmath("ADD", turned.outputs[0], bar.outputs["Location"], x=-1800, y=y)
        show = b.math("ADD", gi.outputs["Show"], 2.0 * k, x=-2000, y=y - 400)
        grow = b.map_range(frame, show, b.math("ADD", show, gi.outputs["Grow"], x=-1800, y=y - 450), x=-1600,
                           y=y - 400, smooth=True)
        snap = gi.outputs["Snap %d" % k]
        snapped = b.map_range(frame, snap, b.math("ADD", snap, gi.outputs["Whip"], x=-1800, y=y - 600), x=-1600,
                              y=y - 600, smooth=True)
        down = b.vmath("ADD", top, b.vmath("SCALE", b.vmath("SUBTRACT", hook.outputs["Location"], top, x=-1600,
                                                            y=y - 150), scale=grow, x=-1400, y=y - 150),
                       x=-1200, y=y - 100)
        end = b.vmath("ADD", down, b.vmath("SCALE", b.vmath("SUBTRACT", top, down, x=-1200, y=y - 300),
                                           scale=b.math("POWER", snapped, 0.6, x=-1200, y=y - 600), x=-1000,
                                           y=y - 300), x=-800, y=y - 200)
        line = b.node("GeometryNodeCurvePrimitiveLine", -600, y)
        b.feed(line.inputs["Start"], top)
        b.feed(line.inputs["End"], end)
        dense = b.node("GeometryNodeResampleCurve", -400, y)
        b.feed(dense.inputs["Curve"], line.outputs["Curve"])
        dense.inputs["Count"].default_value = 16
        # a little sag while it drops, a curl while it whips up (across the picture: X of the bar)
        t = b.node("GeometryNodeSplineParameter", -600, y - 300).outputs["Factor"]
        arc = b.math("SINE", b.math("MULTIPLY", t, 3.14159, x=-400, y=y - 300), x=-200, y=y - 300)
        sway = b.math("ADD", b.math("MULTIPLY", gi.outputs["Sag"], b.math("SUBTRACT", 1.0, grow, x=-400, y=y - 500),
                                    x=-200, y=y - 500),
                      b.math("MULTIPLY", b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY_ADD", t, 11.0, b.math(
                          "MULTIPLY", frame, 0.7, x=-600, y=y - 750), x=-400, y=y - 700), x=-200, y=y - 700),
                          b.math("MULTIPLY", snapped, b.math("SUBTRACT", 1.0, snapped, x=-400, y=y - 850), x=-200,
                                 y=y - 850), x=0, y=y - 750), b.math("MULTIPLY", gi.outputs["Sag"], 4.0, x=0,
                                                                      y=y - 900), x=200, y=y - 800),
                      x=400, y=y - 600)
        across = b.node("ShaderNodeVectorRotate", -200, y - 150)
        across.rotation_type = "EULER_XYZ"
        across.inputs["Vector"].default_value = (1.0, 0.0, 0.0)
        b.feed(across.inputs["Rotation"], bar.outputs["Rotation"])
        bent = b.set_position(dense.outputs["Curve"], offset=b.vmath("SCALE", across.outputs[0],
                                                                     scale=b.math("MULTIPLY", arc, sway, x=600,
                                                                                  y=y - 400), x=800, y=y - 300),
                              x=800, y=y)
        # (its own profile, as thick as the string is: Curve to Mesh does not scale by the curve radius in 5.x)
        profile = b.node("GeometryNodeCurvePrimitiveCircle", 1000, y - 400)
        profile.inputs["Resolution"].default_value = 5
        b.feed(profile.inputs["Radius"], b.math("MAXIMUM", b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Radius"], b.math(
            "SUBTRACT", 1.0, snapped, x=800, y=y - 550), x=1000, y=y - 500), alive, x=1000, y=y - 650), 0.0,
            x=1000, y=y - 750))
        tube = b.node("GeometryNodeCurveToMesh", 1200, y)
        b.feed(tube.inputs["Curve"], bent)
        b.feed(tube.inputs["Profile Curve"], profile.outputs["Curve"])
        tubes.append(tube.outputs["Mesh"])
    joined = b.join(tubes, x=1400, y=0)
    _finish(b, joined, gi, go, 1500, 0)
    return ng


def ensure_puppet_strings_group():
    if not _current(PUPPET_STRINGS_GROUP):
        build_puppet_strings_group()
    return bpy.data.node_groups[PUPPET_STRINGS_GROUP]


def remove_puppet_assets():
    """The marionette's strings group (puppet.py), once no marionette uses it."""
    ng = bpy.data.node_groups.get(PUPPET_STRINGS_GROUP)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)


# --------------------------------------------------------------------------- 1.16: the shadow play (shadowplay.py)

def build_flatten_group():
    """Pressed flat onto a Plane (an empty: through its origin, across its Y axis) as much as Flat says (0 .. 1),
    keeping Keep of the depth (so what is in front stays in front)."""
    ng, b = _group(FLATTEN_GROUP, (
        ("Plane", "NodeSocketObject"),
        ("Flat", "NodeSocketFloat", 0.0),
        ("Keep", "NodeSocketFloat", 0.004),
    ))
    gi = b.node("NodeGroupInput", -1200, 0)
    go = b.node("NodeGroupOutput", 600, 0)
    plane = b.node("GeometryNodeObjectInfo", -1200, -300)
    plane.transform_space = "RELATIVE"
    b.feed(plane.inputs["Object"], gi.outputs["Plane"])
    normal = b.node("ShaderNodeVectorRotate", -1000, -400)
    normal.rotation_type = "EULER_XYZ"
    normal.inputs["Vector"].default_value = (0.0, 1.0, 0.0)
    b.feed(normal.inputs["Rotation"], plane.outputs["Rotation"])
    position = b.node("GeometryNodeInputPosition", -1200, -600).outputs[0]
    depth = b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", position, plane.outputs["Location"], x=-1000, y=-600),
                    normal.outputs[0], x=-800, y=-600)
    squeeze = b.math("MULTIPLY", gi.outputs["Flat"], b.math("SUBTRACT", 1.0, gi.outputs["Keep"], x=-800, y=-800),
                     x=-600, y=-800)
    moved = b.set_position(gi.outputs["Geometry"], offset=b.vmath("SCALE", normal.outputs[0], scale=b.math(
        "MULTIPLY", b.math("MULTIPLY", depth, squeeze, x=-400, y=-700), -1.0, x=-200, y=-700), x=0, y=-500), x=200,
                           y=0)
    b.feed(go.inputs["Geometry"], moved)
    return ng


def ensure_flatten_group():
    if not _current(FLATTEN_GROUP):
        build_flatten_group()
    return bpy.data.node_groups[FLATTEN_GROUP]


def build_rods_group():
    """The shadow play's two rods: from each Hook (her wrists), pressed onto the Plane as much as Flat says, down to
    Floor and Spread out to her sides along the plane; tubes of Radius, only while she is flat."""
    ng, b = _group(RODS_GROUP, (
        ("Plane", "NodeSocketObject"),
        ("Hook L", "NodeSocketObject"),
        ("Hook R", "NodeSocketObject"),
        ("Floor", "NodeSocketFloat", -1.0),
        ("Spread", "NodeSocketFloat", 0.5),
        ("Radius", "NodeSocketFloat", 0.005),
        ("Flat", "NodeSocketFloat", 0.0),
        ("Material", "NodeSocketMaterial"),
    ))
    gi = b.node("NodeGroupInput", -1600, 0)
    go = b.node("NodeGroupOutput", 1200, 0)
    plane = b.node("GeometryNodeObjectInfo", -1600, -300)
    plane.transform_space = "RELATIVE"
    b.feed(plane.inputs["Object"], gi.outputs["Plane"])
    normal = b.node("ShaderNodeVectorRotate", -1400, -400)
    normal.rotation_type = "EULER_XYZ"
    normal.inputs["Vector"].default_value = (0.0, 1.0, 0.0)
    b.feed(normal.inputs["Rotation"], plane.outputs["Rotation"])
    across = b.node("ShaderNodeVectorRotate", -1400, -600)
    across.rotation_type = "EULER_XYZ"
    across.inputs["Vector"].default_value = (1.0, 0.0, 0.0)
    b.feed(across.inputs["Rotation"], plane.outputs["Rotation"])
    profile = b.node("GeometryNodeCurvePrimitiveCircle", 400, -600)  # (as thick as a rod while she is flat)
    profile.inputs["Resolution"].default_value = 6
    b.feed(profile.inputs["Radius"], b.math("MULTIPLY", gi.outputs["Radius"], b.compare(
        "GREATER_THAN", gi.outputs["Flat"], 0.98, x=200, y=-700), x=300, y=-650))
    tubes = []
    for k, (name, way) in enumerate((("Hook L", 1.0), ("Hook R", -1.0))):
        y = -900 * k
        hook = b.node("GeometryNodeObjectInfo", -1400, y + 200)
        hook.transform_space = "RELATIVE"
        b.feed(hook.inputs["Object"], gi.outputs[name])
        depth = b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", hook.outputs["Location"], plane.outputs["Location"],
                                                x=-1200, y=y + 200), normal.outputs[0], x=-1000, y=y + 200)
        top = b.vmath("SUBTRACT", hook.outputs["Location"], b.vmath("SCALE", normal.outputs[0], scale=b.math(
            "MULTIPLY", depth, gi.outputs["Flat"], x=-800, y=y + 300), x=-600, y=y + 300), x=-400, y=y + 200)
        tx, ty, _tz = b.split_xyz(top, x=-200, y=y + 100)
        foot = b.vmath("ADD", b.combine(tx, ty, gi.outputs["Floor"], x=0, y=y + 100),
                       b.vmath("SCALE", across.outputs[0], scale=b.math("MULTIPLY", gi.outputs["Spread"], way, x=-200,
                                                                         y=y - 100), x=0, y=y - 100), x=200, y=y)
        line = b.node("GeometryNodeCurvePrimitiveLine", 400, y)
        b.feed(line.inputs["Start"], top)
        b.feed(line.inputs["End"], foot)
        tube = b.node("GeometryNodeCurveToMesh", 800, y)
        b.feed(tube.inputs["Curve"], line.outputs["Curve"])
        b.feed(tube.inputs["Profile Curve"], profile.outputs["Curve"])
        tubes.append(tube.outputs["Mesh"])
    _finish(b, b.join(tubes, x=1000, y=0), gi, go, 1100, 0)
    return ng


def ensure_rods_group():
    if not _current(RODS_GROUP):
        build_rods_group()
    return bpy.data.node_groups[RODS_GROUP]


def remove_shadow_assets():
    """The shadow play's groups (shadowplay.py), once nothing uses them."""
    for name in (FLATTEN_GROUP, RODS_GROUP):
        ng = bpy.data.node_groups.get(name)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)


# --------------------------------------------------------------------------- 1.16: the mirror first (mirror.py)

def build_mirror_group():
    """A reflection: the Twin (a mesh posed by its armature only) mirrored in the Mirror (an object: a plane through its
    origin, its front at -Y), kept only where the Camera sees it through the glass (Width across X, Height up Z, round
    the mirror's origin) and behind it; nothing while Show is off."""
    ng, b = _group(MIRROR_GROUP, (
        ("Twin", "NodeSocketObject"),
        ("Mirror", "NodeSocketObject"),
        ("Camera", "NodeSocketObject"),
        ("Width", "NodeSocketFloat", 0.5),
        ("Height", "NodeSocketFloat", 1.0),
        ("Show", "NodeSocketFloat", 0.0),
    ))
    gi = b.node("NodeGroupInput", -2000, 0)
    go = b.node("NodeGroupOutput", 1400, 0)
    twin = b.node("GeometryNodeObjectInfo", -1800, 200)
    twin.transform_space = "RELATIVE"
    b.feed(twin.inputs["Object"], gi.outputs["Twin"])
    glass = b.node("GeometryNodeObjectInfo", -1800, -200)
    glass.transform_space = "RELATIVE"
    b.feed(glass.inputs["Object"], gi.outputs["Mirror"])
    eye = b.node("GeometryNodeObjectInfo", -1800, -500)
    eye.transform_space = "RELATIVE"
    b.feed(eye.inputs["Object"], gi.outputs["Camera"])
    axes = []
    for k, v in enumerate(((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))):
        turned = b.node("ShaderNodeVectorRotate", -1600, -300 - 150 * k)
        turned.rotation_type = "EULER_XYZ"
        turned.inputs["Vector"].default_value = v
        b.feed(turned.inputs["Rotation"], glass.outputs["Rotation"])
        axes.append(turned.outputs[0])
    front, across, up = axes
    centre = glass.outputs["Location"]
    position = b.node("GeometryNodeInputPosition", -1600, 400).outputs[0]
    depth = b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", position, centre, x=-1400, y=400), front, x=-1200, y=400)
    mirrored = b.set_position(twin.outputs["Geometry"], offset=b.vmath("SCALE", front, scale=b.math(
        "MULTIPLY", depth, -2.0, x=-1000, y=400), x=-800, y=400), x=-600, y=200)
    flipped = b.node("GeometryNodeFlipFaces", -400, 200)
    b.feed(flipped.inputs["Mesh"], mirrored)
    # where the ray from the camera to each point crosses the glass
    p = b.node("GeometryNodeInputPosition", -1200, -800).outputs[0]
    ray = b.vmath("SUBTRACT", p, eye.outputs["Location"], x=-1000, y=-800)
    t = b.math("DIVIDE", b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", centre, eye.outputs["Location"], x=-1000,
                                                         y=-950), front, x=-800, y=-950),
               b.vmath("DOT_PRODUCT", ray, front, x=-800, y=-800), x=-600, y=-850)
    cross = b.vmath("ADD", eye.outputs["Location"], b.vmath("SCALE", ray, scale=t, x=-400, y=-800), x=-200, y=-800)
    off = b.vmath("SUBTRACT", cross, centre, x=0, y=-800)
    qx = b.math("ABSOLUTE", b.vmath("DOT_PRODUCT", off, across, x=200, y=-750), x=400, y=-750)
    qz = b.math("ABSOLUTE", b.vmath("DOT_PRODUCT", off, up, x=200, y=-900), x=400, y=-900)
    ahead = b.compare("GREATER_THAN", b.vmath("DOT_PRODUCT", b.vmath("SUBTRACT", p, centre, x=0, y=-1100), front,
                                               x=200, y=-1100), 0.0, x=400, y=-1100)
    inside = b.boolean("AND", b.boolean("AND", b.compare("LESS_THAN", qx, b.math("MULTIPLY", gi.outputs["Width"], 0.5,
                                                                                   x=400, y=-600), x=600, y=-700),
                                        b.compare("LESS_THAN", qz, b.math("MULTIPLY", gi.outputs["Height"], 0.5,
                                                                           x=400, y=-1000), x=600, y=-900),
                                        x=800, y=-800), b.boolean("NOT", ahead, x=600, y=-1100), x=1000, y=-900)
    shown = b.boolean("AND", inside, b.compare("GREATER_THAN", gi.outputs["Show"], 0.5, x=800, y=-1250), x=1100,
                      y=-1000)
    kept = b.delete(flipped.outputs["Mesh"], b.boolean("NOT", shown, x=1200, y=-900), "POINT", x=1200, y=0)
    b.feed(go.inputs["Geometry"], kept)
    return ng


def ensure_mirror_group():
    if not _current(MIRROR_GROUP):
        build_mirror_group()
    return bpy.data.node_groups[MIRROR_GROUP]


def remove_mirror_assets():
    """The mirror's group (mirror.py), once no mirror uses it."""
    ng = bpy.data.node_groups.get(MIRROR_GROUP)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)


# --------------------------------------------------------------------------- 1.16: the polaroid's figure (photo.py)

def build_photo_group():
    """The figure on the photo: the Twin (her new outfit posed by its armature only) moved from round the Anchor (her
    centre) onto the photo of the card this object hangs on (Photo X / Y its middle, Photo Width / Height, in the
    card's own space), as tall as the photo (Height: hers, in the world), pressed flat onto it, cut to its edge."""
    ng, b = _group(PHOTO_GROUP, (
        ("Twin", "NodeSocketObject"),
        ("Anchor", "NodeSocketObject"),
        ("Height", "NodeSocketFloat", 1.6),
        ("Photo Width", "NodeSocketFloat", 0.78),
        ("Photo Height", "NodeSocketFloat", 0.78),
        ("Photo X", "NodeSocketFloat", 0.0),
        ("Photo Y", "NodeSocketFloat", 0.1),
    ))
    gi = b.node("NodeGroupInput", -1800, 0)
    go = b.node("NodeGroupOutput", 1400, 0)
    twin = b.node("GeometryNodeObjectInfo", -1600, 200)
    twin.transform_space = "RELATIVE"
    b.feed(twin.inputs["Object"], gi.outputs["Twin"])
    anchor = b.node("GeometryNodeObjectInfo", -1600, -200)
    anchor.transform_space = "RELATIVE"
    b.feed(anchor.inputs["Object"], gi.outputs["Anchor"])
    me = b.node("GeometryNodeObjectInfo", -1600, -500)
    b.feed(me.inputs["Object"], b.node("GeometryNodeSelfObject", -1800, -500).outputs[0])
    sx, _sy, _sz = b.split_xyz(me.outputs["Scale"], x=-1400, y=-500)
    # how much smaller: the photo's height over hers, both in the card's own space
    shrink = b.math("DIVIDE", b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Photo Height"], 0.86, x=-1300,
                                                        y=-400), sx, x=-1200, y=-450),
                    b.math("MAXIMUM", gi.outputs["Height"], 1e-6, x=-1200, y=-600), x=-1000, y=-500)
    position = b.node("GeometryNodeInputPosition", -1400, 300).outputs[0]
    qx, qy, qz = b.split_xyz(b.vmath("SUBTRACT", position, anchor.outputs["Location"], x=-1200, y=300), x=-1000,
                             y=300)
    mx = b.math("ADD", gi.outputs["Photo X"], b.math("MULTIPLY", qx, shrink, x=-800, y=400), x=-600, y=400)
    my = b.math("ADD", gi.outputs["Photo Y"], b.math("MULTIPLY", qy, shrink, x=-800, y=250), x=-600, y=250)
    # (pressed onto the photo, just in front of it: what is nearer the camera a hair nearer still)
    mz = b.math("ADD", 0.0016, b.math("MULTIPLY", b.math("MINIMUM", b.math("MAXIMUM", b.math("DIVIDE", b.math(
        "MULTIPLY", qz, shrink, x=-900, y=100), gi.outputs["Photo Height"], x=-800, y=100), -0.5, x=-750, y=100), 0.5,
        x=-700, y=100), 0.0016, x=-650, y=100), x=-600, y=100)
    moved = b.set_position(twin.outputs["Geometry"], position=b.combine(mx, my, mz, x=-400, y=300), x=-200, y=200)
    p2 = b.node("GeometryNodeInputPosition", -200, -200).outputs[0]
    px_, py_, _pz = b.split_xyz(p2, x=0, y=-200)
    out_x = b.compare("GREATER_THAN", b.math("ABSOLUTE", b.math("SUBTRACT", px_, gi.outputs["Photo X"], x=200, y=-150),
                                             x=400, y=-150), b.math("MULTIPLY", gi.outputs["Photo Width"], 0.5, x=400,
                                                                    y=-300), x=600, y=-200)
    out_y = b.compare("GREATER_THAN", b.math("ABSOLUTE", b.math("SUBTRACT", py_, gi.outputs["Photo Y"], x=200, y=-450),
                                             x=400, y=-450), b.math("MULTIPLY", gi.outputs["Photo Height"], 0.5, x=400,
                                                                    y=-600), x=600, y=-500)
    kept = b.delete(moved, b.boolean("OR", out_x, out_y, x=800, y=-300), "POINT", x=1000, y=0)
    b.feed(go.inputs["Geometry"], kept)
    return ng


def ensure_photo_group():
    if not _current(PHOTO_GROUP):
        build_photo_group()
    return bpy.data.node_groups[PHOTO_GROUP]


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
                 ORIGINS_GROUP, CHAIN_GROUP, PHOTO_GROUP):
        ng = bpy.data.node_groups.get(name)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)


def remove_print_assets():
    """The shapes of the print (printer.py) and its groups, once no print uses them."""
    for name in (ROD, TIP, BEAM, CUBE, LASER_HEAD):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            me = ob.data
            bpy.data.objects.remove(ob)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    for name in (PRINT_SUPPORTS_GROUP, PRINT_LASERS_GROUP):
        ng = bpy.data.node_groups.get(name)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)
