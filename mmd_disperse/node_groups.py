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
between the two outfits.
"""

import math

import bpy

VERSION = 7

FIELD_GROUP = "MMDDisperse Field"
TARGET_GROUP = "MMDDisperse Target"
BASE_GROUP = "MMDDisperse Base"
RIBBON_GROUP = "MMDDisperse Ribbon"

ATTR_EDGE = "disperse_edge"
ATTR_LOCK = "disperse_lock"
ATTR_REST = "rest_position"
ATTR_ARRIVAL = "disperse_arrival"
ATTR_HOLO = "disperse_holo"
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
    ("Reach", "NodeSocketFloat", 1000.0, 0.0, 1e9, "DISTANCE"),
    ("Glitch", "NodeSocketBool", False, None, None, None),
    ("Glitch Width", "NodeSocketFloat", 3.0, 0.0, 10000.0, "DISTANCE"),
    ("Slice Height", "NodeSocketFloat", 0.25, 0.0, 10000.0, "DISTANCE"),
    ("Glitch Rate", "NodeSocketFloat", 0.5, 0.0, 100.0, None),
    ("Glitch Shift", "NodeSocketFloat", 0.4, 0.0, 10000.0, "DISTANCE"),
    ("Glitch Flash", "NodeSocketBool", True, None, None, None),
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
)

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
    ("Flap Speed", "NodeSocketFloat", 1.5, 0.0, 100.0, None),
    ("Particle Density", "NodeSocketFloat", 1.0, 0.0, 1e9, None),
    ("Particle Size", "NodeSocketFloat", 0.35, 0.0, 10000.0, "DISTANCE"),
    ("Particle Flight", "NodeSocketFloat", 5.0, 0.0, 10000.0, "DISTANCE"),
)

RIBBON_INPUTS = (
    ("Mask", "NodeSocketObject", None, None, None, None),
    ("Start", "NodeSocketFloat", 0.0, -1e9, 1e9, "DISTANCE"),
    ("End", "NodeSocketFloat", 1.0, -1e9, 1e9, "DISTANCE"),
    ("Lead", "NodeSocketFloat", 1.0, 0.0, 10000.0, "DISTANCE"),
    ("Linger", "NodeSocketFloat", 2.0, 0.0, 10000.0, "DISTANCE"),
    ("Width", "NodeSocketFloat", 0.15, 0.0, 10000.0, "DISTANCE"),
    ("Material", "NodeSocketMaterial", None, None, None, None),
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

    def accumulate(self, value, group, data_type="FLOAT", x=0, y=0):
        """Per-group total of a point field (Accumulate Field)."""
        n = self.node("GeometryNodeAccumulateField", x, y, data_type=data_type, domain="POINT")
        self.feed(_enabled(n.inputs, "Value")[0], value)
        self.feed(n.inputs["Group ID"], group)
        return _enabled(n.outputs, "Total")[0]

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
    plus the glitch fields both outfits share (so a slice shows exactly one of them)."""
    ng = _new_group(FIELD_GROUP, is_modifier=False)
    for spec in FIELD_INPUTS:
        _add_socket(ng, spec[0], "INPUT", *spec[1:])
    _add_socket(ng, "Distance", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Radius", "OUTPUT", "NodeSocketFloat")
    _add_socket(ng, "Glitching", "OUTPUT", "NodeSocketBool")
    _add_socket(ng, "New Side", "OUTPUT", "NodeSocketBool")
    _add_socket(ng, "Glitch Offset", "OUTPUT", "NodeSocketVector")
    _add_socket(ng, "Flash", "OUTPUT", "NodeSocketFloat")

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
    dice, dice_color = b.white_noise(b.combine(row, tick, 0.37, x=500, y=-1400), x=700, y=-1400)
    new_side = b.compare("LESS_THAN", dice, share, x=1100, y=-1000)
    jump_x, jump_y, glow_z = b.split_xyz(dice_color, x=900, y=-1400)
    jumping = b.boolean("AND", glitching, b.compare("LESS_THAN", jump_x, 0.35, x=1100, y=-1350), x=1300, y=-1300)
    shift = b.math("MULTIPLY", b.math("MULTIPLY_ADD", jump_y, 2.0, -1.0, x=1100, y=-1500),
                   gi.outputs["Glitch Shift"], x=1300, y=-1500)
    offset = b.combine(b.switch("FLOAT", jumping, 0.0, shift, x=1500, y=-1400), 0.0, 0.0, x=1700, y=-1400)
    flashing = b.boolean("AND", glitching, b.compare("GREATER_THAN", glow_z, 0.85, x=1100, y=-1650),
                         x=1300, y=-1650)
    flashing = b.boolean("AND", flashing, gi.outputs["Glitch Flash"], x=1400, y=-1700)
    flash = b.switch("FLOAT", flashing, 0.0, 1.0, x=1500, y=-1650)

    b.feed(go.inputs["Distance"], distance)
    b.feed(go.inputs["Radius"], radius)
    b.feed(go.inputs["Glitching"], glitching)
    b.feed(go.inputs["New Side"], new_side)
    b.feed(go.inputs["Glitch Offset"], offset)
    b.feed(go.inputs["Flash"], flash)
    return ng


def _field_node(b, field_group, gi, x, y):
    """Outputs of the shared Field group: Distance, Radius, Glitching, New Side, Glitch Offset, Flash."""
    n = b.node("GeometryNodeGroup", x, y)
    n.node_tree = field_group
    for spec in FIELD_INPUTS:
        b.feed(n.inputs[spec[0]], gi.outputs[spec[0]])
    return n.outputs


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

    field = _field_node(b, field_group, gi, -1300, -300)
    d, radius = field["Distance"], field["Radius"]

    # Parts locked to the old model (face, hair ...) never come from the new one.
    lock = b.named_attribute(ATTR_LOCK, "BOOLEAN", x=-1300, y=500)[0]
    geo = b.delete(sub.outputs["Mesh"], lock, "FACE", x=-1000, y=300)

    # --- Suit: 0 keep / 1 delete, then push the edge out along the normals.
    # With the hologram on, the new outfit already shows this far ahead of the edge (growing in from
    # nothing, so it is not there at radius 0).
    holo_width = b.math("MINIMUM", gi.outputs["Hologram Width"],
                        b.math("MULTIPLY", b.math("MAXIMUM", radius, 0.0, x=-1000, y=-550), 2.0, x=-850, y=-550),
                        x=-700, y=-500)
    holo_width = b.switch("FLOAT", gi.outputs["Hologram"], 0.0, holo_width, x=-550, y=-500)
    front = b.math("ADD", radius, holo_width, x=-400, y=-500)
    shown = b.compare("LESS_EQUAL", d, front, x=-700, y=150)
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
    suit = b.store(suit, ATTR_EDGE, rim, x=400, y=350)
    # 0 at the edge .. 1 at the front of the hologram (materials draw a scan ring there).
    holo = b.math("DIVIDE", b.math("SUBTRACT", d, radius, x=150, y=-650),
                  b.math("MAXIMUM", holo_width, 1e-4, x=150, y=-800), x=350, y=-700, clamp=True)
    holo = b.switch("FLOAT", gi.outputs["Hologram"], 0.0, holo, x=550, y=-700)
    suit = b.store(suit, ATTR_HOLO, holo, x=600, y=350)

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
    flying = b.math("SUBTRACT", 1.0, landed, x=2200, y=1150)
    rnd, rnd_color = b.white_noise(b.vmath("SCALE", rest_center, scale=5.31, x=2200, y=900), x=2400, y=900)
    jitter = b.vmath("SCALE", b.vmath("SUBTRACT", rnd_color, (0.5, 0.5, 0.5), x=2600, y=900), scale=1.2,
                     x=2800, y=900)
    heading = b.vmath("NORMALIZE", b.vmath("ADD", b.vmath("ADD", piece_normal, jitter, x=3000, y=950),
                                           (0.0, 0.0, 0.5), x=3200, y=950), x=3400, y=950)
    away = b.vmath("SCALE", heading, scale=b.math("MULTIPLY", gi.outputs["Fly Distance"],
                                                   b.math("MULTIPLY", flying, flying, x=2400, y=1100),
                                                   x=2600, y=1100), x=3600, y=1000)
    turn = b.math("MULTIPLY", b.math("MULTIPLY", gi.outputs["Spin"], flying, x=2600, y=750),
                  b.math("MULTIPLY_ADD", rnd, 2.0, -1.0, x=2600, y=600), x=2800, y=700)
    turned = b.rotate(position, center, b.vmath("SUBTRACT", rnd_color, (0.5, 0.5, 0.5), x=2800, y=550), turn,
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
    suit = b.switch("GEOMETRY", gi.outputs["Assemble"], suit, pieces, x=4400, y=1000)

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
    tube = b.curve_to_mesh(curve_out, profile.outputs["Curve"], x=1750, y=-450)
    mat = b.node("GeometryNodeSetMaterial", 1950, -450)
    b.feed(mat.inputs["Geometry"], tube)
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

    field = _field_node(b, field_group, gi, -1700, -300)
    d, radius = field["Distance"], field["Radius"]
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
    chunk_pos = b.vmath("ADD", b.vmath("ADD", chunk_pos, blast, x=3600, y=2600),
                        b.combine(0.0, 0.0, drop, x=3400, y=2500), x=3800, y=2600)
    chunks = b.set_position(chunks, selection=moving, position=chunk_pos, x=4000, y=2200)
    chunks = b.delete(chunks, b.boolean("AND", b.compare("GREATER_EQUAL", ct, 0.999, x=3800, y=2100), free,
                                        x=4000, y=2050), "POINT", x=4200, y=2200)
    chunk_glow = b.math("POWER", b.math("SUBTRACT", 1.0, ct, x=3800, y=1900), 0.25, x=4000, y=1900)
    chunk_glow = b.switch("FLOAT", moving, 0.0, chunk_glow, x=4200, y=1900)
    chunks = b.store(chunks, ATTR_EDGE, b.switch("FLOAT", gi.outputs["Flake Glow"], 0.0, chunk_glow, x=4400, y=1900),
                     x=4400, y=2200)
    old = b.switch("GEOMETRY", gi.outputs["Chunks"], old, chunks, x=4600, y=600)

    # --- Glitch: outside the band the old outfit is simply gone behind the edge; inside it, a slice
    # shows the old outfit whenever the dice did not pick the new one. Slices jump and flash together.
    hidden = b.switch("BOOLEAN", field["Glitching"], b.compare("LESS_EQUAL", d, radius, x=2800, y=900),
                      field["New Side"], x=3000, y=900)
    glitched = b.delete(geometry, b.boolean("AND", hidden, free, x=3000, y=750), "POINT", x=3200, y=900)
    glitched = b.set_position(glitched, field["Glitch Offset"], x=3400, y=900)
    glitched = b.store(glitched, ATTR_EDGE, field["Flash"], x=3600, y=900)
    old = b.switch("GEOMETRY", gi.outputs["Glitch"], old, glitched, x=3600, y=500)

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

    # --- Silhouette: ahead of the edge the old outfit turns into glowing light (magical-girl style);
    # brightest right at the edge. Stored as glow^(1/8) because the material raises it to the 8th power.
    lit = b.map_range(d, b.math("ADD", radius, gi.outputs["Silhouette Width"], x=3600, y=-300), radius,
                      x=3800, y=-300, smooth=True)
    lit = b.switch("FLOAT", gi.outputs["Silhouette"], 0.0, b.math("POWER", lit, 0.125, x=4000, y=-300),
                   x=4200, y=-300)
    current = b.named_attribute(ATTR_EDGE, "FLOAT", x=3800, y=-500)[0]
    old = b.store(old, ATTR_EDGE, b.math("MAXIMUM", current, lit, x=4200, y=-500), x=4400, y=0)
    b.feed(go.inputs["Geometry"], b.join([old, particles], x=4600, y=0))
    return ng


def build_ribbon_group():
    """Modifier for a ribbon curve (a helix around one limb): draw it along the limb as the transformation
    passes from Start to End (mask radius), then let it thin out and vanish."""
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
    gone = b.math("DIVIDE", b.math("SUBTRACT", radius, gi.outputs["End"], x=-600, y=-100),
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
