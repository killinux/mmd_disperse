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
or sweeps up / down, see arrival.py), and the old outfit can break into flakes and particles instead.
"""

import math

import bpy

VERSION = 3

FIELD_GROUP = "MMDDisperse Field"
TARGET_GROUP = "MMDDisperse Target"
BASE_GROUP = "MMDDisperse Base"

ATTR_EDGE = "disperse_edge"
ATTR_LOCK = "disperse_lock"
ATTR_REST = "rest_position"
ATTR_ARRIVAL = "disperse_arrival"
ATTR_NORMAL = "mmdd_normal"  # scratch attribute of the particle emitters, removed again

# Wing angles (degrees) of the poses a butterfly cycles through.
FLAP_ANGLES = (70.0, 45.0, 15.0, -10.0, 15.0, 45.0)

# (name, socket type, default, min, max, subtype)
FIELD_INPUTS = (
    ("Mask", "NodeSocketObject", None, None, None, None),
    ("Use Rest Position", "NodeSocketBool", True, None, None, None),
    ("Use Arrival", "NodeSocketBool", False, None, None, None),
    ("Noise Scale", "NodeSocketFloat", 0.3, 0.0, 10000.0, None),
    ("Noise Detail", "NodeSocketFloat", 2.0, 0.0, 15.0, None),
    ("Noise Amount", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
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
)

BASE_INPUTS = FIELD_INPUTS + (
    ("Shrink", "NodeSocketFloat", 0.08, -10000.0, 10000.0, "DISTANCE"),
    ("Delete Offset", "NodeSocketFloat", 0.6, 0.0, 10000.0, "DISTANCE"),
    ("Fragments", "NodeSocketBool", False, None, None, None),
    ("Reach", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
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
    ("Flap Speed", "NodeSocketFloat", 1.5, 0.0, 100.0, None),
    ("Particle Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Particle Size", "NodeSocketFloat", 0.35, 0.0, 10000.0, "DISTANCE"),
    ("Particle Flight", "NodeSocketFloat", 5.0, 0.0, 10000.0, "DISTANCE"),
)

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

    def rotate(self, vector, center, axis, angle, x=0, y=0):
        n = self.node("ShaderNodeVectorRotate", x, y, rotation_type="AXIS_ANGLE")
        for name, value in (("Vector", vector), ("Center", center), ("Axis", axis), ("Angle", angle)):
            self.feed(n.inputs[name], value)
        return n.outputs[0]


def build_field_group():
    """Distance to the (noisy) sphere mask - or the precomputed arrival distance - and the mask radius."""
    ng = _new_group(FIELD_GROUP, is_modifier=False)
    for spec in FIELD_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Distance", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Radius", "OUTPUT", "NodeSocketFloat")

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
    sphere = b.vmath("DISTANCE", coord, info.outputs["Location"], x=-350, y=-50)

    # Other paths (along the body, sweeps): distance precomputed per vertex at build time.
    arrival, has_arrival = b.named_attribute(ATTR_ARRIVAL, "FLOAT", x=-600, y=150)
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

    b.feed(go.inputs["Distance"], distance)
    b.feed(go.inputs["Radius"], radius)
    return ng


def _field_node(b, field_group, gi, x, y):
    n = b.node("GeometryNodeGroup", x, y)
    n.node_tree = field_group
    for spec in FIELD_INPUTS:
        b.feed(n.inputs[spec[0]], gi.outputs[spec[0]])
    return n.outputs["Distance"], n.outputs["Radius"]


def build_target_group(field_group):
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

    d, radius = _field_node(b, field_group, gi, -1300, -300)

    # Parts locked to the old model (face, hair ...) never come from the new one.
    lock = b.named_attribute(ATTR_LOCK, "BOOLEAN", x=-1300, y=500)[0]
    geo = b.delete(sub.outputs["Mesh"], lock, "FACE", x=-1000, y=300)

    # --- Suit: 0 keep / 1 delete, then push the edge out along the normals.
    outside = b.compare("GREATER_THAN", d, radius, x=-700, y=150)
    suit = b.delete(geo, outside, "POINT", x=-450, y=350)
    edge_start = b.math("SUBTRACT", radius, gi.outputs["Edge Width"], x=-700, y=-50)
    edge = b.map_range(d, edge_start, radius, x=-450, y=-50)
    grad = b.map_range(edge, 0.0, 1.0, x=-450, y=-200, smooth=True)
    normal = b.node("GeometryNodeInputNormal", -450, -350).outputs[0]
    push = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", grad, gi.outputs["Edge Push"], x=-250, y=-150),
                   x=-50, y=-150)
    suit = b.set_position(suit, push, x=150, y=350)
    # Linear 0..1 towards the boundary; materials turn it into a thin glowing rim.
    suit = b.store(suit, ATTR_EDGE, edge, x=400, y=350)

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
    b.feed(radius_node.inputs["Radius"], bump)
    curve_out = b.store(radius_node.outputs["Curve"], ATTR_EDGE, bump, x=1550, y=-450)
    profile = b.node("GeometryNodeCurvePrimitiveCircle", 1550, -750, mode="RADIUS")
    b.feed(profile.inputs["Resolution"], gi.outputs["Wire Resolution"])
    b.feed(profile.inputs["Radius"], gi.outputs["Wire Radius"])
    tube = b.node("GeometryNodeCurveToMesh", 1750, -450)
    b.feed(tube.inputs["Curve"], curve_out)
    b.feed(tube.inputs["Profile Curve"], profile.outputs["Curve"])
    mat = b.node("GeometryNodeSetMaterial", 1950, -450)
    b.feed(mat.inputs["Geometry"], tube.outputs["Mesh"])
    b.feed(mat.inputs["Material"], gi.outputs["Wire Material"])
    wire = b.switch("GEOMETRY", gi.outputs["Wire"], None, mat.outputs["Geometry"], x=1950, y=-150)

    join = b.node("GeometryNodeJoinGeometry", 2000, 250)
    b.feed(join.inputs["Geometry"], wire)
    b.feed(join.inputs["Geometry"], suit)
    b.feed(go.inputs["Geometry"], join.outputs["Geometry"])
    return ng


def _fly(b, gi, t, normal, seed, rnd, x, y):
    """Offset of a piece that has left the surface, t going 0 -> 1 over its flight: it pops out along
    the normal, drifts with the wind (accelerating, each piece at its own speed) and swirls in a noise."""
    inv = b.math("SUBTRACT", 1.0, t, x=x, y=y)
    pop = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", inv, inv, x=x + 150, y=y), x=x + 300, y=y)
    burst = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", pop, gi.outputs["Burst"], x=x + 450, y=y),
                    x=x + 600, y=y)
    speed = b.math("ADD", rnd, 0.5, x=x, y=y - 200)
    drift = b.math("MULTIPLY", b.math("MULTIPLY", t, t, x=x + 150, y=y - 200), speed, x=x + 300, y=y - 200)
    gust = b.vmath("SCALE", gi.outputs["Wind"], scale=drift, x=x + 600, y=y - 200)
    noise = b.node("ShaderNodeTexNoise", x, y - 400, noise_dimensions="4D")
    b.feed(noise.inputs["Vector"], seed)
    b.feed(noise.inputs["W"], b.math("MULTIPLY", t, 1.5, x=x - 200, y=y - 450))
    b.feed(noise.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Noise Scale"], 0.6, x=x - 200, y=y - 600))
    noise.inputs["Detail"].default_value = 1.0
    # Noise colour channels wander around 0.5; recentre and amplify to roughly -1..1.
    swirl = b.vmath("SUBTRACT", noise.outputs[1], (0.5, 0.5, 0.5), x=x + 200, y=y - 400)
    amount = b.math("MULTIPLY", gi.outputs["Turbulence"], b.math("MULTIPLY", t, 4.0, x=x + 200, y=y - 600),
                    x=x + 400, y=y - 600)
    swirl = b.vmath("SCALE", swirl, scale=amount, x=x + 600, y=y - 400)
    return b.vmath("ADD", b.vmath("ADD", burst, gust, x=x + 800, y=y - 100), swirl, x=x + 1000, y=y - 250)


def build_base_group(field_group):
    """Modifier for the OLD outfit: shrink away under the new one, or break into flakes and particles."""
    ng = _new_group(BASE_GROUP, is_modifier=True)
    _add_socket(ng, "Geometry", "INPUT", "NodeSocketGeometry")
    for spec in BASE_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Geometry", "OUTPUT", "NodeSocketGeometry")

    b = _Builder(ng)
    gi = b.node("NodeGroupInput", -2000, 0)
    go = b.node("NodeGroupOutput", 3600, 0)
    geometry = gi.outputs["Geometry"]

    d, radius = _field_node(b, field_group, gi, -1700, -300)
    lock = b.named_attribute(ATTR_LOCK, "BOOLEAN", x=-1700, y=-600)[0]
    free = b.boolean("NOT", lock, x=-1500, y=-600)
    normal = b.node("GeometryNodeInputNormal", -1500, -800).outputs[0]
    position = b.node("GeometryNodeInputPosition", -1500, -950).outputs[0]
    # Rest position seeds the per-piece random numbers, so they do not flicker while the body moves.
    rest, has_rest = b.named_attribute(ATTR_REST, "FLOAT_VECTOR", x=-1700, y=-1100)
    anchor = b.switch("VECTOR", has_rest, position, rest, x=-1500, y=-1100)

    # --- Shrink away (tutorial): sink under the new outfit, then delete behind the edge.
    inside = b.compare("LESS_EQUAL", d, radius, x=-1200, y=600)
    shrink = b.vmath("SCALE", normal, scale=b.math("MULTIPLY", gi.outputs["Shrink"], -1.0, x=-1200, y=450),
                     x=-1000, y=450)
    shrunk = b.set_position(geometry, shrink, b.boolean("AND", inside, free, x=-1000, y=600), x=-800, y=700)
    deep = b.compare("LESS_THAN", d, b.math("SUBTRACT", radius, gi.outputs["Delete Offset"], x=-1000, y=300),
                     x=-800, y=350)
    shrunk = b.delete(shrunk, b.boolean("AND", deep, free, x=-600, y=350), "POINT", x=-400, y=700)

    # --- Disintegrate: behind the front, faces break into flakes that fly off and shrink to nothing.
    age = b.math("SUBTRACT", radius, d, x=-1200, y=0)
    room = b.math("MAXIMUM", b.math("SUBTRACT", gi.outputs["Reach"], d, x=-1200, y=-150), 1e-4, x=-1000, y=-150)

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

    # Everything below is per flake: face averages on the split mesh.
    tf = b.on_domain(t, "FACE", x=600, y=-500)
    center = b.on_domain(position, "FACE", "FLOAT_VECTOR", x=600, y=-650)
    face_normal = b.on_domain(normal, "FACE", "FLOAT_VECTOR", x=600, y=-800)
    seed = b.on_domain(anchor, "FACE", "FLOAT_VECTOR", x=600, y=-950)
    rnd, rnd_color = b.white_noise(b.vmath("SCALE", seed, scale=7.31, x=800, y=-950), x=1000, y=-950)

    scale = b.node("GeometryNodeScaleElements", 1000, 0, domain="FACE")
    b.feed(scale.inputs["Geometry"], split.outputs["Mesh"])
    shrinking = b.math("POWER", b.math("SUBTRACT", 1.0, tf, x=800, y=-300), 0.6, x=1000, y=-300)
    b.feed(scale.inputs["Scale"], b.math("MULTIPLY", gi.outputs["Flake Size"], shrinking, x=1200, y=-300))
    b.feed(scale.inputs["Center"], center)

    axis = b.vmath("SUBTRACT", rnd_color, (0.5, 0.5, 0.5), x=1200, y=-1100)
    turn = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Spin"], tf, x=1200, y=-1250),
                  b.math("MULTIPLY_ADD", rnd, 2.0, -1.0, x=1200, y=-1400), x=1400, y=-1300)
    turned = b.rotate(position, center, axis, turn, x=1600, y=-1100)
    flown = b.vmath("ADD", turned, _fly(b, gi, tf, face_normal, seed, rnd, x=1200, y=-1600), x=2600, y=-1100)
    flakes = b.set_position(scale.outputs["Geometry"], position=flown, x=2800, y=0)
    # Bright as they break off, fading out; the injected material glow raises this to the 8th power.
    fade = b.math("POWER", b.math("SUBTRACT", 1.0, tf, x=2600, y=-300), 0.25, x=2800, y=-300)
    flakes = b.store(flakes, ATTR_EDGE, b.switch("FLOAT", gi.outputs["Flake Glow"], 0.0, fade, x=3000, y=-300),
                     x=3000, y=0)
    broken = b.join([intact, flakes], x=3200, y=200)
    old = b.switch("GEOMETRY", gi.outputs["Fragments"], shrunk, broken, x=3400, y=400)

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
    src = b.store(geometry, ATTR_NORMAL, normal, "FLOAT_VECTOR", "FACE", x=0, y=-1600)
    to_points = b.node("GeometryNodeMeshToPoints", 400, -1600, mode="FACES")
    b.feed(to_points.inputs["Mesh"], src)
    b.feed(to_points.inputs["Selection"], emit)

    # On the points: rest position, arrival and the stored normal came along from the faces.
    point_normal = b.named_attribute(ATTR_NORMAL, "FLOAT_VECTOR", x=400, y=-1900)[0]
    prnd, prnd_color = b.white_noise(b.vmath("SCALE", anchor, scale=5.13, x=400, y=-2400), x=600, y=-2400)
    pts = b.set_position(to_points.outputs["Points"], _fly(b, gi, tp, point_normal, anchor, prnd, x=600, y=-2700),
                         x=1800, y=-1600)
    remove = b.node("GeometryNodeRemoveAttribute", 2000, -1600)
    b.feed(remove.inputs["Geometry"], pts)
    remove.inputs["Name"].default_value = ATTR_NORMAL

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
    rotation = b.switch("VECTOR", gi.outputs["Flap"], tumble, upright, x=2200, y=-2200)
    grow = b.math("MINIMUM", b.map_range(tp, 0.0, 0.05, 0.2, 1.0, x=1800, y=-2900),
                  b.map_range(tp, 0.7, 1.0, 1.0, 0.0, x=1800, y=-3100), x=2000, y=-3000)
    size = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Particle Size"], grow, x=2200, y=-3000),
                  b.math("MULTIPLY_ADD", prnd, 0.6, 0.7, x=2200, y=-3200), x=2400, y=-3000)

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

    on_points = b.node("GeometryNodeInstanceOnPoints", 3200, -1600)
    b.feed(on_points.inputs["Points"], remove.outputs["Geometry"])
    b.feed(on_points.inputs["Instance"], instance)
    b.feed(on_points.inputs["Pick Instance"], gi.outputs["Flap"])
    b.feed(on_points.inputs["Instance Index"], pose_index)
    b.feed(on_points.inputs["Rotation"], rotation)
    b.feed(on_points.inputs["Scale"], size)
    particles = b.switch("GEOMETRY", gi.outputs["Particles"], None, on_points.outputs["Instances"],
                         x=3400, y=-1400)

    b.feed(go.inputs["Geometry"], b.join([old, particles], x=3500, y=0))
    return ng


def _is_current(name):
    ng = bpy.data.node_groups.get(name)
    return ng is not None and ng.get("mmd_disperse_version") == VERSION


def ensure_node_groups():
    """Return (target_group, base_group), (re)building them if missing or outdated."""
    if not (_is_current(FIELD_GROUP) and _is_current(TARGET_GROUP) and _is_current(BASE_GROUP)):
        field = build_field_group()
        build_target_group(field)
        build_base_group(field)
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
