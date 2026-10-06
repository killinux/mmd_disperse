"""Wire, particle and goo materials, and what we inject into the outfits' own materials: the glowing rim, the
hologram, the glowing inside (back faces near the cut), the dark undersuit, the old outfit's surface ahead of the
edge (black veins, frost, char, ink, stone, gold, silk, digital rain) and the husk it leaves behind; the flames, the
lotus, the soul rings and the shockwave."""

import bpy

from .node_groups import (ATTR_ACROSS, ATTR_AHEAD, ATTR_BAND, ATTR_BEAM, ATTR_CARD, ATTR_CUT, ATTR_DIR, ATTR_DOMAIN,
                          ATTR_EDGE, ATTR_FLAME,
                          ATTR_FLAME_CARD, ATTR_FLAME_SEED, ATTR_FRAME, ATTR_GROUND, ATTR_HOLO, ATTR_HUSK, ATTR_LAYER,
                          ATTR_PAINT, ATTR_PETAL, ATTR_REST, ATTR_SCREEN, ATTR_SCREEN_STYLE, ATTR_SHADOW, ATTR_SMOKE,
                          ATTR_SOUL, ATTR_TRAIL, ATTR_WATER)

WIRE_MATERIAL = "MMD Disperse Wire"
RIBBON_MATERIAL = "MMD Disperse Ribbon"
PARTICLE_MATERIAL = "MMD Disperse Particle"
GOO_MATERIAL = "MMD Disperse Goo"
COIN_MATERIAL = "MMD Disperse Coin"
ICE_MATERIAL = "MMD Disperse Ice"
CARD_MATERIAL = "MMD Disperse Card"
BAT_MATERIAL = "MMD Disperse Bat"
INK_MATERIAL = "MMD Disperse Ink"
RING_MATERIAL = "MMD Disperse Ring Glow"
SMOKE_MATERIAL = "MMD Disperse Smoke"
DUST_MATERIAL = "MMD Disperse Dust"  # the shockwave's dust: the smoke's puffs in a dusty grey
OUTLINE_MATERIAL = "MMD Disperse Outline"
SCREEN_MATERIAL = "MMD Disperse Screen"
ARC_MATERIAL = "MMD Disperse Lightning"
BEAM_MATERIAL = "MMD Disperse Beam"
SILK_MATERIAL = "MMD Disperse Silk"
PEBBLE_MATERIAL = "MMD Disperse Pebble"
FLAME_MATERIAL = "MMD Disperse Flame"
LOTUS_MATERIAL = "MMD Disperse Lotus"
SOUL_MATERIAL = "MMD Disperse Soul Ring"
SHOCK_MATERIAL = "MMD Disperse Shockwave"
GLOW = "MMDD Edge"  # prefix of every node we add to a user material
P_GLOW = "mmd_disperse_glow"
HOLO = "MMDD Holo"
P_HOLO = "mmd_disperse_holo"
P_BLEND = "mmd_disperse_blend"  # blend mode to restore (legacy EEVEE needs Hashed for the hologram)
INNER = "MMDD Inner"
P_INNER = "mmd_disperse_inner"
LAYER = "MMDD Layer"
P_LAYER = "mmd_disperse_layer"
SURFACE = "MMDD Surface"
P_SURFACE = "mmd_disperse_surface"  # the style the surface nodes were made for
SURFACE_STYLES = ("VEINS", "FROST", "CHAR", "INK", "STONE", "GOLD", "SILK", "CODE", "PAPERCUT")
P_SURFACE_BLEND = "mmd_disperse_surface_blend"  # blend mode to put back once the paper cut is gone (before 4.2)
CODE_ROW = 1.4  # a glyph of the digital rain is this many times as tall as it is wide
PAINT = "MMDD Paint"
P_PAINT = "mmd_disperse_paint"
P_REFRACT = "mmd_disperse_refract"  # material settings to put back once the clear ice is gone
SHADOW = "MMDD Shadow"
P_SHADOW = "mmd_disperse_shadow"
HUSK = "MMDD Husk"
P_HUSK = "mmd_disperse_husk"
P_HUSK_BLEND = "mmd_disperse_husk_blend"  # blend mode to put back once the husk is gone (it needs Hashed before 4.2)
ICE_IOR = 1.31

# The shader nodes we splice in front of a material output always run in this order, whatever order they are added
# in: the surface ahead of the edge and the undersuit (replace the surface) -> inner glow (replaces it on back faces) ->
# hologram -> the husk -> edge glow (added on top) -> the black shadow (rising from the shadow: replaces everything).
# (name prefix of the node, its pass-through input), first to last.
_CHAIN = ((SURFACE + " Mix", 1), (LAYER + " Mix", 1), (PAINT + " Mix", 1), (INNER + " Mix", 1), (HOLO + " Mix", 1),
          (HUSK + " Mix", 1), (GLOW + " Add", 0), (SHADOW + " Mix", 1))


def _set_input(node, names, value):
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return


def _refraction(mat, on):
    """Let EEVEE refract through `mat` (clear ice): raytraced transmission (4.2+) or screen space refraction with
    alpha-hashed blending (before). Off puts back what the material had."""
    if on and P_REFRACT not in mat:
        if hasattr(mat, "use_raytrace_refraction"):  # EEVEE Next
            mat[P_REFRACT] = {"use_raytrace_refraction": int(mat.use_raytrace_refraction)}
            mat.use_raytrace_refraction = True
        elif hasattr(mat, "use_screen_refraction"):
            mat[P_REFRACT] = {"use_screen_refraction": int(mat.use_screen_refraction), "blend_method": mat.blend_method}
            mat.use_screen_refraction = True
            if mat.blend_method == "OPAQUE":
                mat.blend_method = "HASHED"
    elif not on and P_REFRACT in mat:
        for name, value in mat[P_REFRACT].to_dict().items():
            setattr(mat, name, bool(value) if name.startswith("use_") else value)
        del mat[P_REFRACT]


def enable_refraction(scene):
    """Scene settings EEVEE needs to refract through clear ice: raytracing (4.2+) or screen space reflections with
    refraction (before). Returns True when something was turned on."""
    ee = scene.eevee
    changed = False
    for name in ("use_raytracing", "use_ssr", "use_ssr_refraction"):
        if hasattr(ee, name) and not getattr(ee, name):
            setattr(ee, name, True)
            changed = True
    return changed


def _new(nt, idname, name, x, y, **props):
    node = nt.nodes.new(idname)
    node.name = name
    node.label = name
    node.location = (x, y)
    for key, value in props.items():
        setattr(node, key, value)
    return node


def ensure_wire_material(settings):
    mat = bpy.data.materials.get(WIRE_MATERIAL)
    if mat is None:
        mat = bpy.data.materials.new(WIRE_MATERIAL)
        if mat.node_tree is None:  # Blender 5.0+ always has a node tree
            mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = _new(nt, "ShaderNodeOutputMaterial", "Output", 600, 0)
        bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 250, 0)
        attr = _new(nt, "ShaderNodeAttribute", "Edge", -500, -250,
                    attribute_type="GEOMETRY", attribute_name=ATTR_EDGE)
        # Brightest where the wire is thickest, i.e. right at the boundary.
        falloff = _new(nt, "ShaderNodeMath", "Falloff", -300, -250, operation="POWER")
        falloff.inputs[1].default_value = 3.0
        floor = _new(nt, "ShaderNodeMath", "Floor", -100, -250, operation="MULTIPLY_ADD")
        floor.inputs[1].default_value = 0.9
        floor.inputs[2].default_value = 0.1
        strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", -100, -450)
        glow = _new(nt, "ShaderNodeMath", "Glow", 80, -300, operation="MULTIPLY")
        # outputs[2] is "Fac" before Blender 5.0 and "Factor" after.
        nt.links.new(attr.outputs[2], falloff.inputs[0])
        nt.links.new(falloff.outputs[0], floor.inputs[0])
        nt.links.new(floor.outputs[0], glow.inputs[0])
        nt.links.new(strength.outputs[0], glow.inputs[1])
        nt.links.new(glow.outputs[0], bsdf.inputs["Emission Strength"])
        # The wires are light, not matter: keep them out of shadow rays, or they print a
        # dark lace onto the skin next to the glowing band.
        light_path = _new(nt, "ShaderNodeLightPath", "Light Path", 250, 300)
        clear = _new(nt, "ShaderNodeBsdfTransparent", "Shadow Clear", 250, 150)
        mix = _new(nt, "ShaderNodeMixShader", "No Shadow", 450, 0)
        nt.links.new(light_path.outputs["Is Shadow Ray"], mix.inputs[0])
        nt.links.new(bsdf.outputs[0], mix.inputs[1])
        nt.links.new(clear.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        out.location = (650, 0)
        if hasattr(mat, "use_transparent_shadow"):  # EEVEE (4.2+) honours it per material
            mat.use_transparent_shadow = True
        if bpy.app.version < (4, 2, 0):  # legacy EEVEE ignores "Is Shadow Ray"
            mat.shadow_method = "NONE"
        _set_input(bsdf, ("Metallic",), 1.0)
        _set_input(bsdf, ("Roughness",), 0.25)
    update_wire_material(mat, settings)
    return mat


def update_wire_material(mat, settings):
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("MMDD_BSDF")
    if bsdf is not None:
        _set_input(bsdf, ("Base Color",), tuple(settings.wire_color) + (1.0,))
        _set_input(bsdf, ("Emission Color", "Emission"), tuple(settings.glow_color) + (1.0,))
    strength = nodes.get("MMDD_Strength")
    if strength is not None:
        strength.outputs[0].default_value = settings.glow_strength
    mat.diffuse_color = tuple(settings.glow_color) + (1.0,)


def ensure_ribbon_material():
    """Light ribbons: pure glow in the glow colour, invisible to shadow rays."""
    mat = bpy.data.materials.get(RIBBON_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(RIBBON_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 600, 0)
    emission = _new(nt, "ShaderNodeEmission", "MMDD_Emission", 100, 0)
    light_path = _new(nt, "ShaderNodeLightPath", "Light Path", 100, 300)
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Shadow Clear", 100, 150)
    mix = _new(nt, "ShaderNodeMixShader", "No Shadow", 350, 0)
    nt.links.new(light_path.outputs["Is Shadow Ray"], mix.inputs[0])
    nt.links.new(emission.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True
    if bpy.app.version < (4, 2, 0):
        mat.shadow_method = "NONE"
    return mat


def update_ribbon_material(settings):
    mat = bpy.data.materials.get(RIBBON_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    emission = mat.node_tree.nodes.get("MMDD_Emission")
    if emission is not None:
        emission.inputs["Color"].default_value = tuple(settings.glow_color) + (1.0,)
        emission.inputs["Strength"].default_value = settings.ribbon_strength
    mat.diffuse_color = tuple(settings.glow_color) + (1.0,)


def _no_shadow(mat):
    """Light, not matter: keep a glowing material out of the shadows."""
    if hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True
    if bpy.app.version < (4, 2, 0):
        mat.shadow_method = "NONE"


def ensure_ring_material():
    """The front's decoration (magic circle, sparks, comet): pure glow in the glow colour, as bright as the stored
    disperse_edge says (it fades in and out with the front), invisible to shadow rays."""
    return _glow_material(RING_MATERIAL)


def ensure_arc_material():
    """Lightning (the arcs and the strike): pure glow like the ring's, as bright as the arcs' disperse_edge says."""
    return _glow_material(ARC_MATERIAL)


def update_arc_material(settings):
    mat = bpy.data.materials.get(ARC_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    nodes["MMDD_Emission"].inputs["Color"].default_value = tuple(settings.glow_color) + (1.0,)
    nodes["MMDD_Strength"].outputs[0].default_value = settings.arc_strength
    mat.diffuse_color = tuple(settings.glow_color) + (1.0,)


def _glow_material(name):
    """Pure glow (the value MMDD_Emission's colour) as bright as disperse_edge times the value MMDD_Strength,
    invisible to shadow rays."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 600, 0)
    attr = _new(nt, "ShaderNodeAttribute", "Glow", -400, -150, attribute_type="GEOMETRY", attribute_name=ATTR_EDGE)
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", -400, -350)
    amount = _new(nt, "ShaderNodeMath", "Amount", -150, -200, operation="MULTIPLY")
    nt.links.new(attr.outputs[2], amount.inputs[0])  # "Fac" / "Factor"
    nt.links.new(strength.outputs[0], amount.inputs[1])
    emission = _new(nt, "ShaderNodeEmission", "MMDD_Emission", 100, 0)
    nt.links.new(amount.outputs[0], emission.inputs["Strength"])
    light_path = _new(nt, "ShaderNodeLightPath", "Light Path", 100, 300)
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Shadow Clear", 100, 150)
    mix = _new(nt, "ShaderNodeMixShader", "No Shadow", 350, 0)
    nt.links.new(light_path.outputs["Is Shadow Ray"], mix.inputs[0])
    nt.links.new(emission.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    _no_shadow(mat)
    return mat


def ensure_screen_material():
    """The front's glowing panel and TV static (mmdd_screen: x, y across the sheet in -1 .. 1, z the frame;
    mmdd_screen_style: 0 panel, 1 static). The panel: a faint see-through screen with a grid and a scan band rolling
    down it. The static: grey snow changing every frame over scan lines, tinted a little in the glow colour. Both fade
    out towards their borders and with disperse_edge."""
    mat = bpy.data.materials.get(SCREEN_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(SCREEN_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 1600, 0)

    def math(op, a, b=None, c=None, x=0, y=0, clamp=False):
        n = _new(nt, "ShaderNodeMath", "%s %d %d" % (op, x, y), x, y, operation=op, use_clamp=clamp)
        for sock, value in ((n.inputs[0], a), (n.inputs[1], b), (n.inputs[2], c)):
            if isinstance(value, bpy.types.NodeSocket):
                nt.links.new(value, sock)
            elif value is not None:
                sock.default_value = value
        return n.outputs[0]

    screen = _new(nt, "ShaderNodeAttribute", "Screen", -1400, 0, attribute_type="GEOMETRY",
                  attribute_name=ATTR_SCREEN)
    style = _new(nt, "ShaderNodeAttribute", "Style", -1400, -300, attribute_type="GEOMETRY",
                 attribute_name=ATTR_SCREEN_STYLE).outputs[2]
    glow = _new(nt, "ShaderNodeAttribute", "Glow", -1400, -500, attribute_type="GEOMETRY",
                attribute_name=ATTR_EDGE).outputs[2]
    xyz = _new(nt, "ShaderNodeSeparateXYZ", "Across", -1200, 0)
    nt.links.new(screen.outputs["Vector"], xyz.inputs[0])
    sx, sy, t = xyz.outputs[0], xyz.outputs[1], xyz.outputs[2]
    # fade towards the border
    border = math("MAXIMUM", math("ABSOLUTE", sx, x=-1000, y=200), math("ABSOLUTE", sy, x=-1000, y=50), x=-800, y=150)
    soft = math("SUBTRACT", 1.0, math("POWER", math("MINIMUM", border, 1.0, x=-600, y=150), 6.0, x=-400, y=150),
                x=-200, y=150)

    def grid_line(value, count, x, y):
        cell = math("FRACT", math("MULTIPLY", value, count, x=x, y=y), x=x + 200, y=y)
        return math("GREATER_THAN", math("ABSOLUTE", math("SUBTRACT", cell, 0.5, x=x + 400, y=y), x=x + 600, y=y),
                    0.475, x=x + 800, y=y)

    grid = math("MAXIMUM", grid_line(sx, 4.0, -1000, -800), grid_line(sy, 9.0, -1000, -950), x=0, y=-850)
    # one bright band rolling down the panel (y runs -1 .. 1, so fract(y/2 - t) passes 0.5 once)
    roll = math("FRACT", math("ADD", math("MULTIPLY", sy, 0.5, x=-1000, y=-1300), math("MULTIPLY", t, -0.015, x=-1000,
                                                                                         y=-1450), x=-800, y=-1350),
                x=-600, y=-1350)
    band = math("SUBTRACT", 1.0, math("MULTIPLY", math("ABSOLUTE", math("SUBTRACT", roll, 0.5, x=-400, y=-1350),
                                                      x=-200, y=-1350), 12.0, x=0, y=-1350, clamp=True), x=200,
                y=-1350, clamp=True)
    panel_alpha = math("ADD", math("MULTIPLY_ADD", grid, 0.3, 0.06, x=200, y=-850), math("MULTIPLY", band, 0.2,
                                                                                         x=200, y=-1000), x=400,
                       y=-900)
    panel_light = math("ADD", math("MULTIPLY_ADD", grid, 1.0, 0.25, x=200, y=-1150), math("MULTIPLY", band, 1.2, x=200,
                                                                                         y=-1500), x=400, y=-1200)
    # static: snow on cells of the sheet, new every frame, over scan lines
    cells = _new(nt, "ShaderNodeCombineXYZ", "Cells", -800, -1800)
    nt.links.new(math("FLOOR", math("MULTIPLY", sx, 90.0, x=-1200, y=-1700), x=-1000, y=-1700), cells.inputs[0])
    nt.links.new(math("FLOOR", math("MULTIPLY", sy, 160.0, x=-1200, y=-1900), x=-1000, y=-1900), cells.inputs[1])
    snow = _new(nt, "ShaderNodeTexWhiteNoise", "Snow", -600, -1800, noise_dimensions="4D")
    nt.links.new(cells.outputs[0], snow.inputs["Vector"])
    nt.links.new(t, snow.inputs["W"])
    lines = math("MULTIPLY_ADD", math("SINE", math("MULTIPLY", sy, 420.0, x=-600, y=-2100), x=-400, y=-2100), 0.2, 0.8,
                 x=-200, y=-2100)
    static_alpha = math("MULTIPLY_ADD", snow.outputs[0], 0.3, 0.08, x=0, y=-1800)
    static_light = math("MULTIPLY", math("MULTIPLY_ADD", snow.outputs[0], 0.8, 0.15, x=0, y=-1950), lines, x=200,
                        y=-2000)
    alpha = math("ADD", panel_alpha, math("MULTIPLY", math("SUBTRACT", static_alpha, panel_alpha, x=600, y=-1600),
                                          style, x=800, y=-1600), x=1000, y=-1500)
    light = math("ADD", panel_light, math("MULTIPLY", math("SUBTRACT", static_light, panel_light, x=600, y=-1900),
                                          style, x=800, y=-1900), x=1000, y=-1800)
    alpha = math("MULTIPLY", math("MULTIPLY", alpha, soft, x=1200, y=-1400), glow, x=1400, y=-1400, clamp=True)
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", 1000, -2100)
    light = math("MULTIPLY", math("MULTIPLY", light, glow, x=1200, y=-1900), strength.outputs[0], x=1400, y=-1950)
    tint = _new(nt, "ShaderNodeRGB", "MMDD_Color", 600, -2300)
    color = _lerp(nt, tint.outputs[0], (0.85, 0.87, 0.9), math("MULTIPLY", style, 0.7, x=800, y=-2400), "Tint",
                  1000, -2300)
    emission = _new(nt, "ShaderNodeEmission", "Emission", 1300, -2200)
    nt.links.new(color, emission.inputs["Color"])
    nt.links.new(light, emission.inputs["Strength"])
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Clear", 1300, -2400)
    mix = _new(nt, "ShaderNodeMixShader", "Cover", 1450, -2300)
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(emission.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if bpy.app.version < (4, 2, 0):  # legacy EEVEE ignores transparency otherwise
        mat.blend_method = "HASHED"
    _no_shadow(mat)
    return mat


def ensure_beam_material():
    """The transporter beam's column (ATTR_BEAM: x, y round it, z up it): see-through light in the glow colour, in
    streaks up it that shimmer (a noise round it and up it, changing with the frame), brighter towards its sides,
    where you look through more of it, and fading out at the top and the bottom; as bright as disperse_edge says (it
    fades in and out). Invisible to shadow rays."""
    mat = bpy.data.materials.get(BEAM_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(BEAM_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 1400, 0)
    beam = _new(nt, "ShaderNodeAttribute", "Beam", -1400, 0, attribute_type="GEOMETRY", attribute_name=ATTR_BEAM)
    frame = _new(nt, "ShaderNodeAttribute", "Frame", -1400, -250, attribute_type="GEOMETRY",
                 attribute_name=ATTR_FRAME).outputs[2]
    glow = _new(nt, "ShaderNodeAttribute", "Glow", -1400, -450, attribute_type="GEOMETRY",
                attribute_name=ATTR_EDGE).outputs[2]
    xyz = _new(nt, "ShaderNodeSeparateXYZ", "Round", -1200, 0)
    nt.links.new(beam.outputs["Vector"], xyz.inputs[0])
    around = _new(nt, "ShaderNodeCombineXYZ", "Around", -1000, 100)
    for i, k in enumerate((2.5, 2.5, 0.5)):
        nt.links.new(_math(nt, "Beam", "MULTIPLY", xyz.outputs[i], k, x=-1100, y=100 - 150 * i), around.inputs[i])
    streak = _new(nt, "ShaderNodeTexNoise", "Streaks", -800, 100, noise_dimensions="4D")
    nt.links.new(around.outputs[0], streak.inputs["Vector"])
    nt.links.new(_math(nt, "Beam", "MULTIPLY", frame, 0.03, x=-1000, y=-150), streak.inputs["W"])
    streak.inputs["Scale"].default_value = 1.0
    streak.inputs["Detail"].default_value = 1.0
    streaks = _new(nt, "ShaderNodeMapRange", "Streak Level", -600, 100, interpolation_type="SMOOTHSTEP")
    nt.links.new(streak.outputs[0], streaks.inputs[0])
    streaks.inputs[1].default_value = 0.4
    streaks.inputs[2].default_value = 0.68
    h = xyz.outputs[2]
    rise = _new(nt, "ShaderNodeMapRange", "Bottom", -800, -350, interpolation_type="SMOOTHSTEP")
    nt.links.new(h, rise.inputs[0])
    rise.inputs[2].default_value = 0.1
    fall = _new(nt, "ShaderNodeMapRange", "Top", -800, -600, interpolation_type="SMOOTHSTEP")
    nt.links.new(h, fall.inputs[0])
    fall.inputs[1].default_value = 0.6
    fall.inputs[3].default_value = 1.0
    fall.inputs[4].default_value = 0.0
    # clear where you look straight through it, glowing towards its sides
    facing = _new(nt, "ShaderNodeLayerWeight", "Sides", -800, -850)
    facing.inputs["Blend"].default_value = 0.5
    sides = _math(nt, "Beam", "MULTIPLY_ADD", _math(nt, "Beam", "POWER", facing.outputs["Facing"], 1.5, x=-700,
                                                    y=-850), 0.92, 0.08, x=-600, y=-850)
    alpha = _math(nt, "Beam", "MULTIPLY", glow, _math(nt, "Beam", "MULTIPLY", rise.outputs[0], fall.outputs[0], x=-600,
                                                      y=-450), x=-400, y=-400)
    alpha = _math(nt, "Beam", "MULTIPLY", alpha, _math(nt, "Beam", "MULTIPLY_ADD", streaks.outputs[0], 0.8, 0.2,
                                                       x=-400, y=100), x=-200, y=-200)
    alpha = _math(nt, "Beam", "MULTIPLY", alpha, _math(nt, "Beam", "MULTIPLY", sides, 0.3, x=-400, y=-850), x=0,
                  y=-300, clamp=True)
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", 0, -600)
    emission = _new(nt, "ShaderNodeEmission", "MMDD_Emission", 400, -300)
    nt.links.new(_math(nt, "Beam", "MULTIPLY", strength.outputs[0], 1.5, x=200, y=-400), emission.inputs["Strength"])
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Clear", 400, -100)
    mix = _new(nt, "ShaderNodeMixShader", "Light", 800, -200)
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(emission.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    # blended, not dithered: a smooth haze of light (it casts no shadow, so nothing needs sorting against it)
    if hasattr(mat, "surface_render_method"):  # EEVEE Next
        mat.surface_render_method = "BLENDED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
    _no_shadow(mat)
    return mat


def update_beam_material(settings):
    mat = bpy.data.materials.get(BEAM_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    nodes["MMDD_Emission"].inputs["Color"].default_value = tuple(settings.glow_color) + (1.0,)
    nodes["MMDD_Strength"].outputs[0].default_value = settings.beam_strength
    mat.diffuse_color = tuple(settings.glow_color) + (1.0,)


def ensure_silk_material():
    """The silk threads of the cocoon: soft, sheeny silk that glows faintly (so it reads on a dark stage)."""
    mat = bpy.data.materials.get(SILK_MATERIAL)
    if mat is not None:
        return mat
    mat = _plain_material(SILK_MATERIAL, (0.93, 0.91, 0.86), 0.4)
    bsdf = mat.node_tree.nodes["MMDD_BSDF"]
    _set_input(bsdf, ("Sheen Weight", "Sheen"), 1.0)
    _set_input(bsdf, ("Emission Strength",), 0.35)
    return mat


def update_silk_material(color):
    mat = bpy.data.materials.get(SILK_MATERIAL)
    bsdf = mat.node_tree.nodes.get("MMDD_BSDF") if mat is not None and mat.node_tree else None
    if bsdf is not None:
        _set_input(bsdf, ("Base Color",), tuple(color) + (1.0,))
        _set_input(bsdf, ("Emission Color", "Emission"), tuple(color) + (1.0,))
        mat.diffuse_color = tuple(color) + (1.0,)


def update_ring_materials(settings):
    """Colour and brightness of the front's decoration."""
    for name in (RING_MATERIAL, SCREEN_MATERIAL):
        mat = bpy.data.materials.get(name)
        if mat is None or mat.node_tree is None:
            continue
        nodes = mat.node_tree.nodes
        emission = nodes.get("MMDD_Emission")
        if emission is not None:
            emission.inputs["Color"].default_value = tuple(settings.glow_color) + (1.0,)
        tint = nodes.get("MMDD_Color")
        if tint is not None:
            tint.outputs[0].default_value = tuple(settings.glow_color) + (1.0,)
        strength = nodes.get("MMDD_Strength")
        if strength is not None:
            strength.outputs[0].default_value = settings.ring_strength
        mat.diffuse_color = tuple(settings.glow_color) + (1.0,)


def ensure_particle_material():
    """Petals / butterflies: flat colour that glows, brighter towards the tips (UV x)."""
    mat = bpy.data.materials.get(PARTICLE_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(PARTICLE_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 500, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 150, 0)
    coord = _new(nt, "ShaderNodeTexCoord", "Coordinates", -650, -200)
    xyz = _new(nt, "ShaderNodeSeparateXYZ", "UV", -450, -200)
    tips = _new(nt, "ShaderNodeMapRange", "Tips", -250, -200)
    tips.inputs[3].default_value = 0.3
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", -250, -450)
    glow = _new(nt, "ShaderNodeMath", "Glow", -50, -250, operation="MULTIPLY")
    nt.links.new(coord.outputs["UV"], xyz.inputs[0])
    nt.links.new(xyz.outputs[0], tips.inputs[0])
    nt.links.new(tips.outputs[0], glow.inputs[0])
    nt.links.new(strength.outputs[0], glow.inputs[1])
    nt.links.new(glow.outputs[0], bsdf.inputs["Emission Strength"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    _set_input(bsdf, ("Roughness",), 0.45)
    return mat


def ensure_coin_material():
    """Coins: polished metal in the particle colour (gold by default in the coin preset)."""
    mat = bpy.data.materials.get(COIN_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(COIN_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 400, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 100, 0)
    _set_input(bsdf, ("Metallic",), 1.0)
    _set_input(bsdf, ("Roughness",), 0.22)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def ensure_ice_material():
    """Ice shards and crystals: clear ice like glass (it refracts what is behind it), tinted in the particle colour,
    with a faint cold glow so it still reads against a dark background."""
    mat = bpy.data.materials.get(ICE_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(ICE_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 400, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 100, 0)
    _set_input(bsdf, ("Roughness",), 0.05)
    _set_input(bsdf, ("IOR",), ICE_IOR)
    _set_input(bsdf, ("Transmission Weight", "Transmission"), 1.0)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 1.0)
    _set_input(bsdf, ("Emission Strength",), 0.3)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    _refraction(mat, True)
    if hasattr(mat, "shadow_method"):  # legacy EEVEE: a light, see-through shadow
        mat.shadow_method = "HASHED"
    return mat


def _lerp(nt, a, b, fac, name, x, y):
    """a + (b - a) * fac on colours (vector math, the same in every Blender version)."""
    span = _new(nt, "ShaderNodeVectorMath", name + " Span", x, y, operation="SUBTRACT")
    for sock, value in ((span.inputs[0], b), (span.inputs[1], a)):
        if isinstance(value, bpy.types.NodeSocket):
            nt.links.new(value, sock)
        else:
            sock.default_value = value
    mix = _new(nt, "ShaderNodeVectorMath", name, x + 180, y, operation="MULTIPLY_ADD")
    nt.links.new(span.outputs[0], mix.inputs[0])
    nt.links.new(fac, mix.inputs[1])
    if isinstance(a, bpy.types.NodeSocket):
        nt.links.new(a, mix.inputs[2])
    else:
        mix.inputs[2].default_value = a
    return mix.outputs[0]


def _plain_material(name, color, roughness, coat=0.0):
    """A plain Principled material (bats, ink drops): `color`, `roughness`, a clear coat for a wet look."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 400, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 100, 0)
    _set_input(bsdf, ("Base Color",), tuple(color) + (1.0,))
    _set_input(bsdf, ("Roughness",), roughness)
    _set_input(bsdf, ("Coat Weight", "Clearcoat"), coat)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    mat.diffuse_color = tuple(color) + (1.0,)
    return mat


PAPER_MATERIAL = "MMD Disperse Paper"


def ensure_paper_material():
    """Red paper (the paper birds): matte, glowing a little so it reads on a dark stage."""
    mat = _plain_material(PAPER_MATERIAL, (0.75, 0.05, 0.035), 0.85)
    bsdf = mat.node_tree.nodes.get("MMDD_BSDF")
    if bsdf is not None:
        _set_input(bsdf, ("Emission Color", "Emission"), (0.75, 0.05, 0.035, 1.0))
        _set_input(bsdf, ("Emission Strength",), 0.12)
    return mat


def ensure_bat_material():
    """Bats: dull black, a dark red light along their outline so they read against a dark background."""
    mat = bpy.data.materials.get(BAT_MATERIAL)
    if mat is not None:
        return mat
    mat = _plain_material(BAT_MATERIAL, (0.012, 0.01, 0.012), 0.6)
    nt = mat.node_tree
    bsdf = nt.nodes["MMDD_BSDF"]
    facing = _new(nt, "ShaderNodeLayerWeight", "Outline", -500, -300)
    facing.inputs["Blend"].default_value = 0.4
    glow = _new(nt, "ShaderNodeMath", "Outline Glow", -300, -300, operation="POWER")
    nt.links.new(facing.outputs["Facing"], glow.inputs[0])
    glow.inputs[1].default_value = 3.0
    strength = _new(nt, "ShaderNodeMath", "Outline Strength", -100, -300, operation="MULTIPLY")
    nt.links.new(glow.outputs[0], strength.inputs[0])
    strength.inputs[1].default_value = 3.0
    _set_input(bsdf, ("Emission Color", "Emission"), (0.8, 0.03, 0.06, 1.0))
    nt.links.new(strength.outputs[0], bsdf.inputs["Emission Strength"])
    return mat


def ensure_ink_material():
    """Ink drops: wet black ink."""
    return _plain_material(INK_MATERIAL, (0.004, 0.004, 0.005), 0.12, coat=0.6)


def ensure_pebble_material():
    """Pebbles: dull stone in the particle colour."""
    return _plain_material(PEBBLE_MATERIAL, (0.45, 0.43, 0.4), 0.85)


def ensure_card_material():
    """Playing cards: the face white with a red border line and a red diamond in the middle, the back red with a white
    border (UV across the card; the back is the face seen from behind). A faint glow keeps them readable."""
    mat = bpy.data.materials.get(CARD_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(CARD_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 900, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 600, 0)
    coord = _new(nt, "ShaderNodeTexCoord", "Coordinates", -1300, 0)
    uv = _new(nt, "ShaderNodeSeparateXYZ", "UV", -1100, 0)
    nt.links.new(coord.outputs["UV"], uv.inputs[0])
    axes = []
    for i, name in enumerate(("U", "V")):
        off = _new(nt, "ShaderNodeMath", "Off " + name, -900, 100 - 200 * i, operation="SUBTRACT")
        nt.links.new(uv.outputs[i], off.inputs[0])
        off.inputs[1].default_value = 0.5
        far = _new(nt, "ShaderNodeMath", "Far " + name, -700, 100 - 200 * i, operation="ABSOLUTE")
        nt.links.new(off.outputs[0], far.inputs[0])
        axes.append(far.outputs[0])
    # m: 0 in the middle .. 1 at the edge of the card (square measure); the diamond in the middle
    edge = _new(nt, "ShaderNodeMath", "Edge", -500, 200, operation="MAXIMUM")
    nt.links.new(axes[0], edge.inputs[0])
    nt.links.new(axes[1], edge.inputs[1])
    m = _new(nt, "ShaderNodeMath", "M", -300, 200, operation="MULTIPLY")
    nt.links.new(edge.outputs[0], m.inputs[0])
    m.inputs[1].default_value = 2.0
    line_in = _new(nt, "ShaderNodeMath", "Line In", -100, 300, operation="GREATER_THAN")
    nt.links.new(m.outputs[0], line_in.inputs[0])
    line_in.inputs[1].default_value = 0.8
    line_out = _new(nt, "ShaderNodeMath", "Line Out", -100, 150, operation="LESS_THAN")
    nt.links.new(m.outputs[0], line_out.inputs[0])
    line_out.inputs[1].default_value = 0.87
    line = _new(nt, "ShaderNodeMath", "Line", 100, 250, operation="MULTIPLY")
    nt.links.new(line_in.outputs[0], line.inputs[0])
    nt.links.new(line_out.outputs[0], line.inputs[1])
    du = _new(nt, "ShaderNodeMath", "Diamond U", -500, -100, operation="DIVIDE")
    nt.links.new(axes[0], du.inputs[0])
    du.inputs[1].default_value = 0.17
    dv = _new(nt, "ShaderNodeMath", "Diamond V", -500, -250, operation="DIVIDE")
    nt.links.new(axes[1], dv.inputs[0])
    dv.inputs[1].default_value = 0.24
    dsum = _new(nt, "ShaderNodeMath", "Diamond Sum", -300, -150, operation="ADD")
    nt.links.new(du.outputs[0], dsum.inputs[0])
    nt.links.new(dv.outputs[0], dsum.inputs[1])
    diamond = _new(nt, "ShaderNodeMath", "Diamond", -100, -150, operation="LESS_THAN")
    nt.links.new(dsum.outputs[0], diamond.inputs[0])
    diamond.inputs[1].default_value = 1.0
    red_face = _new(nt, "ShaderNodeMath", "Red Face", 100, 50, operation="MAXIMUM")
    nt.links.new(line.outputs[0], red_face.inputs[0])
    nt.links.new(diamond.outputs[0], red_face.inputs[1])
    white, red = (0.92, 0.92, 0.9), (0.72, 0.03, 0.05)
    face = _lerp(nt, white, red, red_face.outputs[0], "Face", 250, 100)
    rim = _new(nt, "ShaderNodeMath", "Back Rim", 100, -350, operation="GREATER_THAN")
    nt.links.new(m.outputs[0], rim.inputs[0])
    rim.inputs[1].default_value = 0.86
    back = _lerp(nt, (0.5, 0.03, 0.05), white, rim.outputs[0], "Back", 250, -300)
    geometry = _new(nt, "ShaderNodeNewGeometry", "Geometry", 250, -550)
    color = _lerp(nt, face, back, geometry.outputs["Backfacing"], "Color", 450, -100)
    nt.links.new(color, bsdf.inputs["Base Color"])
    emission = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    nt.links.new(color, emission)
    _set_input(bsdf, ("Emission Strength",), 0.25)
    _set_input(bsdf, ("Roughness",), 0.35)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    mat.diffuse_color = white + (1.0,)
    return mat


def update_particle_material(settings):
    color = tuple(settings.particle_color) + (1.0,)
    for name in (COIN_MATERIAL, ICE_MATERIAL, PEBBLE_MATERIAL):
        shiny = bpy.data.materials.get(name)
        bsdf = shiny.node_tree.nodes.get("MMDD_BSDF") if shiny is not None and shiny.node_tree else None
        if bsdf is not None:
            # clear ice tinted the colour, a faint glow (coins do not glow; 3.x's Emission is a colour)
            if name == ICE_MATERIAL:
                _set_input(bsdf, ("Base Color",), color)
                _set_input(bsdf, ("Emission Color", "Emission"), color)
            else:
                _set_input(bsdf, ("Base Color",), color)
            shiny.diffuse_color = color
    mat = bpy.data.materials.get(PARTICLE_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    bsdf = mat.node_tree.nodes.get("MMDD_BSDF")
    if bsdf is not None:
        _set_input(bsdf, ("Base Color",), color)
        _set_input(bsdf, ("Emission Color", "Emission"), color)
    strength = mat.node_tree.nodes.get("MMDD_Strength")
    if strength is not None:
        strength.outputs[0].default_value = settings.particle_glow
    mat.diffuse_color = color


def _goo_shader(nt, prefix, coord, x, y):
    """Wet black goo: a Principled BSDF (`prefix` + " BSDF") under a clear coat, its roughness smeared by a noise on
    `coord` with a matching bump, so it is not equally wet everywhere (DNEG's "semi-dry" symbiote). Returns the BSDF;
    the noise (`prefix` + " Smear") gets its scale from _set_goo()."""
    smear = _new(nt, "ShaderNodeTexNoise", prefix + " Smear", x - 700, y - 200, noise_dimensions="3D")
    nt.links.new(coord, smear.inputs["Vector"])
    smear.inputs["Detail"].default_value = 3.0
    wet = _new(nt, "ShaderNodeMapRange", prefix + " Wet", x - 500, y - 100)
    for i, value in ((1, 0.35), (2, 0.65), (3, 0.04), (4, 0.45)):
        wet.inputs[i].default_value = value
    nt.links.new(smear.outputs[0], wet.inputs[0])  # "Fac" / "Factor"
    bump = _new(nt, "ShaderNodeBump", prefix + " Bump", x - 500, y - 400)
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.05
    nt.links.new(smear.outputs[0], bump.inputs["Height"])
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", prefix + " BSDF", x - 250, y - 200)
    _set_input(bsdf, ("Metallic",), 0.0)
    _set_input(bsdf, ("Coat Weight", "Clearcoat"), 1.0)
    _set_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.03)
    nt.links.new(wet.outputs[0], bsdf.inputs["Roughness"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return bsdf


def _set_goo(nodes, prefix, color, cell, metallic=0.0):
    """Goo colour, the size of its wet / dry smears (`cell`, in the units of the noise's coordinates) and how metallic
    it is (liquid metal: polished, with only faint smears)."""
    bsdf = nodes.get(prefix + " BSDF")
    if bsdf is not None:
        _set_input(bsdf, ("Base Color",), tuple(color) + (1.0,))
        _set_input(bsdf, ("Metallic",), metallic)
    smear = nodes.get(prefix + " Smear")
    if smear is not None:
        smear.inputs["Scale"].default_value = 1.0 / max(cell, 1e-6)
    wet = nodes.get(prefix + " Wet")
    if wet is not None:  # roughness range of the smears (metal: brushed enough to catch the lights)
        wet.inputs[3].default_value = 0.04 + 0.08 * metallic
        wet.inputs[4].default_value = 0.45 - 0.17 * metallic


def ensure_goo_material():
    """The symbiote's tendrils and strands: wet black goo (smears on the object coordinates)."""
    mat = bpy.data.materials.get(GOO_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(GOO_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 400, 0)
    coord = _new(nt, "ShaderNodeTexCoord", "Coordinates", -1000, -200)
    bsdf = _goo_shader(nt, "MMDD Goo", coord.outputs["Object"], 200, 0)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def update_goo_material(color, cell, metallic=0.0):
    mat = bpy.data.materials.get(GOO_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    _set_goo(mat.node_tree.nodes, "MMDD Goo", color, cell, metallic)
    mat.diffuse_color = tuple(color) + (1.0,)
    mat.metallic = metallic


def _alpha_source(nt):
    """Texture alpha of the material, so cut-out texels (lace, hair cards) do not glow."""
    tex = nt.nodes.get("mmd_base_tex")  # mmd_tools base texture
    if tex is not None and tex.bl_idname == "ShaderNodeTexImage" and tex.image is not None:
        return tex.outputs["Alpha"]
    for node in nt.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            alpha = node.inputs.get("Alpha")
            if alpha is not None and alpha.links:
                return alpha.links[0].from_socket
    return None


def _place(node):
    """(position in _CHAIN, pass-through input) of one of our spliced nodes; None for any other node."""
    for rank, (prefix, through) in enumerate(_CHAIN):
        if node.name.startswith(prefix):
            return rank, through
    return None


def _splice(nt, out, node):
    """Put `node` (a spliced node of ours, see _CHAIN) between the surface and the material output `out`, after
    those of ours that come before it and in front of those that come after."""
    rank, through = _place(node)
    socket = out.inputs["Surface"]
    while socket.links:
        found = _place(socket.links[0].from_node)
        if found is None or found[0] < rank:
            break
        socket = socket.links[0].from_node.inputs[found[1]]
    if socket.links:
        nt.links.new(socket.links[0].from_socket, node.inputs[through])
    nt.links.new(node.outputs[0], socket)


def _unsplice(nt, prefix):
    """Remove our spliced nodes whose names start with `prefix`, reconnecting what ran through them."""
    for node in [n for n in nt.nodes if n.name.startswith(prefix)]:
        place = _place(node)
        through = node.inputs[place[1]] if place is not None else None
        source = through.links[0].from_socket if through is not None and through.links else None
        targets = [link.to_socket for link in node.outputs[0].links]
        nt.nodes.remove(node)
        if source is not None:
            for socket in targets:
                nt.links.new(source, socket)


def add_edge_glow(mat):
    """Add `surface + emission * disperse_edge^8` in front of every material output."""
    nt = mat.node_tree
    if nt is None or mat.get(P_GLOW):
        return
    outputs = [n for n in nt.nodes
               if n.bl_idname == "ShaderNodeOutputMaterial" and n.inputs["Surface"].links]
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 200
    y = min(n.location.y for n in outputs) - 300
    attr = _new(nt, "ShaderNodeAttribute", GLOW + " Attribute", x - 800, y,
                attribute_type="GEOMETRY", attribute_name=ATTR_EDGE)
    # outputs[2] is "Fac" before Blender 5.0 and "Factor" after.
    falloff = _new(nt, "ShaderNodeMath", GLOW + " Falloff", x - 600, y, operation="POWER")
    nt.links.new(attr.outputs[2], falloff.inputs[0])
    falloff.inputs[1].default_value = 8.0  # only the last ~15% of the edge width lights up
    strength = _new(nt, "ShaderNodeValue", GLOW + " Strength", x - 600, y - 200)
    amount = _new(nt, "ShaderNodeMath", GLOW + " Amount", x - 400, y, operation="MULTIPLY")
    nt.links.new(falloff.outputs[0], amount.inputs[0])
    nt.links.new(strength.outputs[0], amount.inputs[1])
    alpha = _alpha_source(nt)
    if alpha is not None:
        masked = _new(nt, "ShaderNodeMath", GLOW + " Alpha", x - 250, y, operation="MULTIPLY")
        nt.links.new(amount.outputs[0], masked.inputs[0])
        nt.links.new(alpha, masked.inputs[1])
        amount = masked
    emission = _new(nt, "ShaderNodeEmission", GLOW + " Emission", x - 50, y)
    nt.links.new(amount.outputs[0], emission.inputs["Strength"])
    for i, out in enumerate(outputs):
        add = _new(nt, "ShaderNodeAddShader", "%s Add %d" % (GLOW, i), out.location.x - 180, out.location.y - 120)
        nt.links.new(emission.outputs[0], add.inputs[1])
        _splice(nt, out, add)
    mat[P_GLOW] = 1


def update_edge_glow(mat, color, strength):
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    emission = nodes.get(GLOW + " Emission")
    if emission is not None:
        emission.inputs["Color"].default_value = tuple(color) + (1.0,)
    value = nodes.get(GLOW + " Strength")
    if value is not None:
        value.outputs[0].default_value = strength


def remove_edge_glow(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_GLOW):
        return
    _unsplice(nt, GLOW + " Add")
    for node in [n for n in nt.nodes if n.name.startswith(GLOW)]:
        nt.nodes.remove(node)
    del mat[P_GLOW]


def _outputs(nt):
    return [n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.inputs["Surface"].links]


HOLO_STYLES = ("SCAN", "STARS", "SHADOW", "ICE")


def add_hologram(mat, style="SCAN"):
    """Where `disperse_holo` > 0 (ahead of the edge) the surface turns into a see-through veil, then turns solid at the
    edge: SCAN a glowing hologram with horizontal scan lines; STARS a dark veil of night sky full of stars (a starry
    veil first, the outfit after); SHADOW a black silhouette with a thin glowing rim; ICE pale clear ice with frost.
    All with a bright rim and a scan ring at the front of the veil."""
    nt = mat.node_tree
    if nt is None:
        return
    if mat.get(P_HOLO):
        if mat[P_HOLO] == style or (mat[P_HOLO] == 1 and style == "SCAN"):
            return
        remove_hologram(mat)  # (made in another style)
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 250
    y = min(n.location.y for n in outputs) - 700
    attr = _new(nt, "ShaderNodeAttribute", HOLO + " Attribute", x - 1300, y,
                attribute_type="GEOMETRY", attribute_name=ATTR_HOLO)
    # outputs[2] is "Fac" before Blender 5.0 and "Factor" after.
    switch = _new(nt, "ShaderNodeMath", HOLO + " On", x - 1100, y + 200, operation="MULTIPLY", use_clamp=True)
    switch.inputs[1].default_value = 50.0
    nt.links.new(attr.outputs[2], switch.inputs[0])
    ring = _new(nt, "ShaderNodeMath", HOLO + " Ring", x - 1100, y, operation="POWER")
    ring.inputs[1].default_value = 24.0
    nt.links.new(attr.outputs[2], ring.inputs[0])
    math = _shader_math(nt, HOLO)
    geometry = _new(nt, "ShaderNodeNewGeometry", HOLO + " Geometry", x - 1500, y - 300)
    tint = _new(nt, "ShaderNodeRGB", HOLO + " Tint", x - 700, y - 1100)  # the glow colour
    rim = _new(nt, "ShaderNodeLayerWeight", HOLO + " Rim", x - 900, y - 550)
    rim.inputs["Blend"].default_value = 0.35
    strength = _new(nt, "ShaderNodeValue", HOLO + " Strength", x - 700, y - 750)
    opacity = _new(nt, "ShaderNodeValue", HOLO + " Opacity", x - 700, y - 900)
    color = tint.outputs[0]
    if style == "STARS":
        # stars: a few cells of a Voronoi pattern, a bright dot in each ("Lines": update_hologram sizes it)
        cells = _new(nt, "ShaderNodeTexVoronoi", HOLO + " Lines", x - 1300, y - 300)
        nt.links.new(geometry.outputs["Position"], cells.inputs["Vector"])
        pick = _new(nt, "ShaderNodeSeparateXYZ", HOLO + " Pick", x - 1100, y - 500)
        nt.links.new(cells.outputs["Color"], pick.inputs[0])
        dot = math("POWER", math("SUBTRACT", 1.0, math("DIVIDE", cells.outputs["Distance"], 0.3, x=x - 1100,
                                                       y=y - 300, clamp=True), x=x - 900, y=y - 300), 2.0, x=x - 700,
                   y=y - 300)
        stars = math("MULTIPLY", dot, math("GREATER_THAN", pick.outputs[0], 0.35, x=x - 900, y=y - 500), x=x - 500,
                     y=y - 300)
        level = math("MULTIPLY_ADD", stars, 4.0, 0.08, x=x - 400, y=y - 200)  # (the night itself glows faintly)
        color = _lerp(nt, (0.05, 0.04, 0.2), (1.0, 1.0, 1.0), stars, HOLO + " Night", x - 400, y - 1100)
        cover = math("ADD", math("MULTIPLY", opacity.outputs[0], 2.0, x=x - 500, y=y - 700), stars, x=x - 300,
                     y=y - 700)
    elif style == "SHADOW":
        level = 0.0  # no light of its own but the rim ...
        cover = math("ADD", opacity.outputs[0], 0.55, x=x - 500, y=y - 700)  # ... and nearly solid: a black shape
    elif style == "ICE":
        frost = _new(nt, "ShaderNodeTexNoise", HOLO + " Lines", x - 1300, y - 300)
        frost.inputs["Detail"].default_value = 8.0
        nt.links.new(geometry.outputs["Position"], frost.inputs["Vector"])
        level = math("MULTIPLY_ADD", math("POWER", frost.outputs[0], 3.0, x=x - 1100, y=y - 300), 1.2, 0.15,
                     x=x - 900, y=y - 300)
        icy = _new(nt, "ShaderNodeRGB", HOLO + " Ice", x - 700, y - 1300)
        icy.outputs[0].default_value = (0.55, 0.85, 1.0, 1.0)
        color = icy.outputs[0]
        cover = math("MULTIPLY_ADD", level, opacity.outputs[0], 0.1, x=x - 500, y=y - 700)
    else:  # SCAN
        lines = _new(nt, "ShaderNodeTexWave", HOLO + " Lines", x - 1100, y - 300, wave_type="BANDS",
                     bands_direction="Z")
        nt.links.new(geometry.outputs["Position"], lines.inputs["Vector"])
        sharp = _new(nt, "ShaderNodeMath", HOLO + " Sharpen", x - 900, y - 300, operation="POWER")
        sharp.inputs[1].default_value = 4.0
        nt.links.new(lines.outputs[1], sharp.inputs[0])  # "Fac" / "Factor"
        level = math("MULTIPLY_ADD", sharp.outputs[0], 0.7, 0.3, x=x - 700, y=y - 300)
        cover = math("MULTIPLY", level, opacity.outputs[0], x=x - 500, y=y - 700)

    # Light: (pattern + 1.5 * rim) * strength + ring * 6 * strength (the silhouette's rim is a thin line)
    rim_light = math("POWER", rim.outputs["Facing"], 6.0, x=x - 700, y=y - 450) if style == "SHADOW" else \
        rim.outputs["Facing"]
    lit = math("MULTIPLY_ADD", rim_light, 1.5 if style != "SHADOW" else 3.0, level, x=x - 500, y=y - 400)
    glow = math("MULTIPLY", math("MULTIPLY_ADD", ring.outputs[0], 6.0, lit, x=x - 500, y=y - 150), strength.outputs[0],
                x=x - 300, y=y - 200)
    emission = _new(nt, "ShaderNodeEmission", HOLO + " Emission", x - 100, y - 200)
    nt.links.new(color, emission.inputs["Color"])
    nt.links.new(glow, emission.inputs["Strength"])

    # Cover: the pattern's own + 0.4 * rim + ring, times the texture alpha (lace stays see-through).
    cover_ring = math("ADD", math("MULTIPLY_ADD", rim.outputs["Facing"], 0.4, cover, x=x - 300, y=y - 650),
                      ring.outputs[0], x=x - 100, y=y - 650, clamp=True)
    alpha = cover_ring
    texture_alpha = _alpha_source(nt)
    if texture_alpha is not None:
        alpha = math("MULTIPLY", cover_ring, texture_alpha, x=x + 50, y=y - 650)
    clear = _new(nt, "ShaderNodeBsdfTransparent", HOLO + " Clear", x + 50, y - 400)
    hologram = _new(nt, "ShaderNodeMixShader", HOLO + " Shader", x + 200, y - 300)
    nt.links.new(alpha, hologram.inputs[0])
    nt.links.new(clear.outputs[0], hologram.inputs[1])
    nt.links.new(emission.outputs[0], hologram.inputs[2])

    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (HOLO, i), out.location.x - 180, out.location.y + 150)
        nt.links.new(switch.outputs[0], mix.inputs[0])
        nt.links.new(hologram.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    if bpy.app.version < (4, 2, 0) and mat.blend_method == "OPAQUE":  # legacy EEVEE ignores transparency
        mat[P_BLEND] = mat.blend_method
        mat.blend_method = "HASHED"
    mat[P_HOLO] = style


def update_hologram(mat, color, strength, opacity, line_spacing):
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    tint = nodes.get(HOLO + " Tint")
    if tint is not None:
        tint.outputs[0].default_value = tuple(color) + (1.0,)
    for name, value in ((" Strength", strength), (" Opacity", opacity)):
        node = nodes.get(HOLO + name)
        if node is not None:
            node.outputs[0].default_value = value
    lines = nodes.get(HOLO + " Lines")
    if lines is not None:  # scan bands repeat every 2*pi/20 texture units; a star every few line spacings
        scale = {"ShaderNodeTexWave": 0.31416, "ShaderNodeTexVoronoi": 0.2, "ShaderNodeTexNoise": 0.12}
        lines.inputs["Scale"].default_value = scale.get(lines.bl_idname, 0.31416) / max(line_spacing, 1e-6)


def remove_hologram(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_HOLO):
        return
    _unsplice(nt, HOLO + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(HOLO)]:
        nt.nodes.remove(node)
    if P_BLEND in mat:
        mat.blend_method = mat[P_BLEND]
        del mat[P_BLEND]
    del mat[P_HOLO]


def add_inner_glow(mat):
    """Back faces near the cut (`disperse_cut`) turn into flat glow: where an outfit is cut open its inside looks
    lit and solid instead of hollow. Front faces and the rest of the inside keep the surface."""
    nt = mat.node_tree
    if nt is None or mat.get(P_INNER):
        return
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 250
    y = min(n.location.y for n in outputs) - 1700
    attr = _new(nt, "ShaderNodeAttribute", INNER + " Attribute", x - 900, y,
                attribute_type="GEOMETRY", attribute_name=ATTR_CUT)
    # Fully lit over the first half of the depth, fading over the rest. outputs[2] is "Fac" / "Factor".
    near = _new(nt, "ShaderNodeMath", INNER + " Near", x - 700, y, operation="MULTIPLY", use_clamp=True)
    near.inputs[1].default_value = 2.0
    nt.links.new(attr.outputs[2], near.inputs[0])
    geometry = _new(nt, "ShaderNodeNewGeometry", INNER + " Geometry", x - 900, y - 250)
    back = _new(nt, "ShaderNodeMath", INNER + " Back", x - 500, y, operation="MULTIPLY")
    nt.links.new(near.outputs[0], back.inputs[0])
    nt.links.new(geometry.outputs["Backfacing"], back.inputs[1])
    fac = back
    alpha = _alpha_source(nt)
    if alpha is not None:  # cut-out texels stay see-through
        fac = _new(nt, "ShaderNodeMath", INNER + " Alpha", x - 300, y, operation="MULTIPLY")
        nt.links.new(back.outputs[0], fac.inputs[0])
        nt.links.new(alpha, fac.inputs[1])
    emission = _new(nt, "ShaderNodeEmission", INNER + " Emission", x - 300, y - 250)
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (INNER, i), out.location.x - 180, out.location.y + 300)
        nt.links.new(fac.outputs[0], mix.inputs[0])
        nt.links.new(emission.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_INNER] = 1


def update_inner_glow(mat, color, strength):
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    emission = nodes.get(INNER + " Emission")
    if emission is not None:
        emission.inputs["Color"].default_value = tuple(color) + (1.0,)
        emission.inputs["Strength"].default_value = strength


def remove_inner_glow(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_INNER):
        return
    _unsplice(nt, INNER + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(INNER)]:
        nt.nodes.remove(node)
    del mat[P_INNER]


def add_layer(mat):
    """Where `disperse_layer` > 0 the surface is a dark, glossy undersuit with a fine web of glowing lines (cells
    on the rest position, so they stick to the body), or the symbiote's wet black goo."""
    nt = mat.node_tree
    if nt is None or mat.get(P_LAYER):
        return
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 250
    y = min(n.location.y for n in outputs) - 2300
    attr = _new(nt, "ShaderNodeAttribute", LAYER + " Attribute", x - 300, y + 200,
                attribute_type="GEOMETRY", attribute_name=ATTR_LAYER)
    rest = _new(nt, "ShaderNodeAttribute", LAYER + " Rest", x - 1100, y - 200,
                attribute_type="GEOMETRY", attribute_name=ATTR_REST)
    cells = _new(nt, "ShaderNodeTexVoronoi", LAYER + " Cells", x - 900, y - 200, voronoi_dimensions="3D",
                 feature="DISTANCE_TO_EDGE")
    nt.links.new(rest.outputs["Vector"], cells.inputs["Vector"])
    lines = _new(nt, "ShaderNodeMapRange", LAYER + " Lines", x - 700, y - 200)
    lines.inputs[2].default_value = 0.06  # line width, in cells
    lines.inputs[3].default_value = 1.0
    lines.inputs[4].default_value = 0.0
    nt.links.new(cells.outputs["Distance"], lines.inputs[0])
    strength = _new(nt, "ShaderNodeValue", LAYER + " Strength", x - 700, y - 450)
    glow = _new(nt, "ShaderNodeMath", LAYER + " Glow", x - 500, y - 250, operation="MULTIPLY")
    nt.links.new(lines.outputs[0], glow.inputs[0])
    nt.links.new(strength.outputs[0], glow.inputs[1])
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", LAYER + " BSDF", x - 300, y - 200)
    _set_input(bsdf, ("Metallic",), 0.8)
    _set_input(bsdf, ("Roughness",), 0.32)
    nt.links.new(glow.outputs[0], bsdf.inputs["Emission Strength"])
    # The symbiote's style: wet black goo instead (Style 1).
    goo = _goo_shader(nt, LAYER + " Goo", rest.outputs["Vector"], x - 300, y - 800)
    alpha = _alpha_source(nt)
    if alpha is not None:  # lace and other cut-outs keep their holes
        nt.links.new(alpha, bsdf.inputs["Alpha"])
        nt.links.new(alpha, goo.inputs["Alpha"])
    style = _new(nt, "ShaderNodeValue", LAYER + " Style", x - 300, y - 500)
    pick = _new(nt, "ShaderNodeMixShader", LAYER + " Pick", x - 50, y - 300)
    nt.links.new(style.outputs[0], pick.inputs[0])
    nt.links.new(bsdf.outputs[0], pick.inputs[1])
    nt.links.new(goo.outputs[0], pick.inputs[2])
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (LAYER, i), out.location.x - 180, out.location.y + 450)
        nt.links.new(attr.outputs[2], mix.inputs[0])
        nt.links.new(pick.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_LAYER] = 1


def update_layer(mat, color, glow_color, lines, cell, goo=None):
    """Undersuit colour, colour and brightness of its lines, cell size in object units; `goo` = (colour, smear size,
    metallic) for the symbiote's goo instead."""
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    bsdf = nodes.get(LAYER + " BSDF")
    if bsdf is not None:
        _set_input(bsdf, ("Base Color",), tuple(color) + (1.0,))
        _set_input(bsdf, ("Emission Color", "Emission"), tuple(glow_color) + (1.0,))
    strength = nodes.get(LAYER + " Strength")
    if strength is not None:
        strength.outputs[0].default_value = lines
    cells = nodes.get(LAYER + " Cells")
    if cells is not None:
        cells.inputs["Scale"].default_value = 1.0 / max(cell, 1e-6)
    style = nodes.get(LAYER + " Style")
    if style is not None:
        style.outputs[0].default_value = 0.0 if goo is None else 1.0
    if goo is not None:
        _set_goo(nodes, LAYER + " Goo", *goo)


def remove_layer(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_LAYER):
        return
    _unsplice(nt, LAYER + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(LAYER)]:
        nt.nodes.remove(node)
    del mat[P_LAYER]


def _base_color(nt):
    """The material's own base colour (its texture), for drawings of it: the mmd_tools base texture, else whatever
    feeds a Principled BSDF's Base Color, else that colour itself."""
    tex = nt.nodes.get("mmd_base_tex")
    if tex is not None and tex.bl_idname == "ShaderNodeTexImage" and tex.image is not None:
        return tex.outputs["Color"]
    for node in nt.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled" and not node.name.startswith("MMDD"):
            sock = node.inputs["Base Color"]
            if sock.links:
                return sock.links[0].from_socket
            return tuple(sock.default_value)
    return (0.8, 0.8, 0.8, 1.0)


def _feed(nt, socket, value):
    if isinstance(value, bpy.types.NodeSocket):
        nt.links.new(value, socket)
    else:
        socket.default_value = value


def _math(nt, prefix, op, a, b=None, c=None, x=0, y=0, clamp=False):
    n = _new(nt, "ShaderNodeMath", "%s %s %d %d" % (prefix, op, x, y), x, y, operation=op, use_clamp=clamp)
    for sock, value in ((n.inputs[0], a), (n.inputs[1], b), (n.inputs[2], c)):
        if value is not None:
            _feed(nt, sock, value)
    return n.outputs[0]


def _drawing(nt, prefix, color, rest, x, y):
    """A drawing of the surface in `color` (its texture), unlit: (line art colour, ink wash colour). Line art: paper
    with ink lines along the silhouette and screentone dots where the colour is dark. Ink wash: the colour's darkness
    as shades of ink on paper, the forms modelled by the facing, in uneven blotches, the silhouette stroked. Paper and
    ink colours are the values `prefix` + " Paper" / " Ink"."""
    gray = _new(nt, "ShaderNodeRGBToBW", prefix + " Gray", x, y)
    _feed(nt, gray.inputs[0], color)
    lum = gray.outputs[0]
    paper = _new(nt, "ShaderNodeRGB", prefix + " Paper", x, y - 800).outputs[0]
    ink = _new(nt, "ShaderNodeRGB", prefix + " Ink", x, y - 1000).outputs[0]
    facing = _new(nt, "ShaderNodeLayerWeight", prefix + " Facing", x, y - 300)
    facing.inputs["Blend"].default_value = 0.45
    rim = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SUBTRACT", facing.outputs["Facing"], 0.5, x=x + 200,
                                               y=y - 300), 4.0, x=x + 400, y=y - 300, clamp=True)
    # screentone: dots on the body (cells of the rest position), bigger where the colour is darker
    dots = _new(nt, "ShaderNodeTexVoronoi", prefix + " Hatch", x, y - 500, voronoi_dimensions="3D", feature="F1")
    nt.links.new(rest, dots.inputs["Vector"])
    dots.inputs["Randomness"].default_value = 0.35
    dark = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SUBTRACT", 0.65, lum, x=x + 200, y=y - 650), 1.8,
                 x=x + 400, y=y - 650, clamp=True)
    size = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SQRT", dark, x=x + 600, y=y - 650), 0.42, x=x + 800,
                 y=y - 650)
    dot = _math(nt, prefix, "LESS_THAN", dots.outputs["Distance"], size, x=x + 600, y=y - 500)
    lines = _math(nt, prefix, "MAXIMUM", rim, dot, x=x + 800, y=y - 400)
    line_art = _lerp(nt, paper, ink, lines, prefix + " Line Art", x + 1000, y - 600)
    # ink wash: dark colour -> dense ink, the forms modelled by the facing (diluted where the surface faces the eye,
    # denser towards the silhouette, so dark clothes show washes too), in uneven blotches, the silhouette stroked
    wash = _new(nt, "ShaderNodeTexNoise", prefix + " Wash", x, y - 1200, noise_dimensions="3D")
    nt.links.new(rest, wash.inputs["Vector"])
    wash.inputs["Detail"].default_value = 3.0
    tone = _math(nt, prefix, "SUBTRACT", 1.0, lum, x=x + 200, y=y - 1100)
    soft = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SUBTRACT", facing.outputs["Facing"], 0.15, x=x + 200,
                                                y=y - 1400), 1.6, x=x + 400, y=y - 1400, clamp=True)
    uneven = _math(nt, prefix, "MULTIPLY_ADD", wash.outputs[0], 0.6, -0.3, x=x + 200, y=y - 1250)
    body = _math(nt, prefix, "MULTIPLY_ADD", tone, 0.7, _math(nt, prefix, "MULTIPLY_ADD", soft, 0.35, uneven,
                                                               x=x + 400, y=y - 1300), x=x + 600, y=y - 1150)
    density = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SUBTRACT", body, 0.05, x=x + 800, y=y - 1150), 1.25,
                    x=x + 1000, y=y - 1150, clamp=True)
    density = _math(nt, prefix, "MAXIMUM", _math(nt, prefix, "POWER", density, 0.9, x=x + 1200, y=y - 1150), rim,
                    x=x + 1400, y=y - 1150)
    ink_wash = _lerp(nt, paper, ink, _math(nt, prefix, "MULTIPLY", density, 0.94, x=x + 1600, y=y - 1150),
                     prefix + " Ink Wash", x + 1800, y - 1150)
    return line_art, ink_wash


def _code(nt, prefix, rest, frame, x, y):
    """The digital rain (The Matrix) on the body, as a colour: columns of glyphs on the rest position, a column a cell
    across and a glyph CODE_ROW cells tall (across a column runs x on faces looking to the front or the back, y on the
    sides). A bright head rains down each column at its own speed with a fading trail behind it, and every glyph is a
    random 5 x 7 dot pattern that changes now and then. The trail is in the value prefix + " Code Color", the heads
    white, bright enough to glow; a cell is 1 / prefix + " Code Scale" across. `frame` scrolls it."""
    scale = _new(nt, "ShaderNodeValue", prefix + " Code Scale", x, y + 200).outputs[0]
    cells = _new(nt, "ShaderNodeVectorMath", prefix + " Code Cells", x + 200, y, operation="SCALE")
    _feed(nt, cells.inputs[0], rest)
    nt.links.new(scale, cells.inputs[3])
    xyz = _new(nt, "ShaderNodeSeparateXYZ", prefix + " Code XYZ", x + 400, y)
    nt.links.new(cells.outputs[0], xyz.inputs[0])
    qx, qy, qz = xyz.outputs[0], xyz.outputs[1], xyz.outputs[2]
    looks = _new(nt, "ShaderNodeSeparateXYZ", prefix + " Code Normal", x + 400, y - 300)
    nt.links.new(_new(nt, "ShaderNodeTexCoord", prefix + " Code Coords", x + 200, y - 300).outputs["Normal"],
                 looks.inputs[0])
    side = _math(nt, prefix, "GREATER_THAN", _math(nt, prefix, "ABSOLUTE", looks.outputs[0], x=x + 600, y=y - 300),
                 _math(nt, prefix, "ABSOLUTE", looks.outputs[1], x=x + 600, y=y - 450), x=x + 800, y=y - 350)
    u = _math(nt, prefix, "MULTIPLY_ADD", _math(nt, prefix, "SUBTRACT", qy, qx, x=x + 800, y=y - 150), side, qx,
              x=x + 1000, y=y - 200)
    rows = _math(nt, prefix, "DIVIDE", qz, CODE_ROW, x=x + 600, y=y + 100)
    col_x = _math(nt, prefix, "FLOOR", qx, x=x + 600, y=y + 300)
    col_y = _math(nt, prefix, "FLOOR", qy, x=x + 600, y=y + 450)
    k = _math(nt, prefix, "FLOOR", rows, x=x + 800, y=y + 100)

    def noise(a, b_, c, name, xx, yy):
        combined = _new(nt, "ShaderNodeCombineXYZ", prefix + " Code " + name + " At", xx, yy)
        for sock, value in zip(combined.inputs, (a, b_, c)):
            _feed(nt, sock, value)
        n = _new(nt, "ShaderNodeTexWhiteNoise", prefix + " Code " + name, xx + 200, yy, noise_dimensions="3D")
        nt.links.new(combined.outputs[0], n.inputs["Vector"])
        return n

    column = noise(col_x, col_y, 0.5, "Column", x + 1000, y + 400)
    speeds = _new(nt, "ShaderNodeSeparateXYZ", prefix + " Code Speeds", x + 1400, y + 400)
    nt.links.new(column.outputs["Color"], speeds.inputs[0])
    r1, r2, r3 = speeds.outputs[0], speeds.outputs[1], speeds.outputs[2]
    speed = _math(nt, prefix, "MULTIPLY_ADD", r1, 0.5, 0.25, x=x + 1600, y=y + 500)
    head = _math(nt, prefix, "MULTIPLY_ADD", _math(nt, prefix, "MULTIPLY", frame, speed, x=x + 1800, y=y + 500), -1.0,
                 _math(nt, prefix, "MULTIPLY", r2, 97.0, x=x + 1800, y=y + 350), x=x + 2000, y=y + 450)
    period = _math(nt, prefix, "MULTIPLY_ADD", r3, 18.0, 18.0, x=x + 1600, y=y + 250)
    # rows above the head (0 at the head), the trail fading over 60% of the column's period
    behind = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "FRACT", _math(
        nt, prefix, "DIVIDE", _math(nt, prefix, "SUBTRACT", k, head, x=x + 2200, y=y + 300), period, x=x + 2400,
        y=y + 300), x=x + 2600, y=y + 300), period, x=x + 2800, y=y + 300)
    trail = _math(nt, prefix, "SUBTRACT", 1.0, _math(nt, prefix, "DIVIDE", behind, _math(
        nt, prefix, "MULTIPLY", period, 0.6, x=x + 2800, y=y + 150), x=x + 3000, y=y + 200), x=x + 3200, y=y + 200,
        clamp=True)
    trail = _math(nt, prefix, "MULTIPLY", trail, trail, x=x + 3400, y=y + 200)
    at_head = _math(nt, prefix, "LESS_THAN", behind, 1.0, x=x + 3000, y=y + 400)
    # the glyph: a 5 x 7 dot pattern picked by the cell and changing every few frames
    flips = _math(nt, prefix, "FLOOR", _math(nt, prefix, "MULTIPLY", frame, _math(
        nt, prefix, "MULTIPLY_ADD", r1, 0.1, 0.06, x=x + 1600, y=y - 600), x=x + 1800, y=y - 600), x=x + 2000,
        y=y - 600)
    which = _math(nt, prefix, "ADD", _math(nt, prefix, "FLOOR", _math(nt, prefix, "MULTIPLY", noise(
        col_x, col_y, k, "Glyph", x + 1000, y - 800).outputs[0], 50.0, x=x + 1400, y=y - 800), x=x + 1600, y=y - 800),
        flips, x=x + 2200, y=y - 700)
    fu = _math(nt, prefix, "FRACT", u, x=x + 1200, y=y - 200)
    fv = _math(nt, prefix, "FRACT", rows, x=x + 1000, y=y + 100)
    ix = _math(nt, prefix, "FLOOR", _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SUBTRACT", fu, 0.12, x=x + 1400,
                                                                          y=y - 1000), 6.25, x=x + 1600, y=y - 1000),
               x=x + 1800, y=y - 1000)
    iy = _math(nt, prefix, "FLOOR", _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "SUBTRACT", fv, 0.08, x=x + 1400,
                                                                          y=y - 1150), 8.33, x=x + 1600, y=y - 1150),
               x=x + 1800, y=y - 1150)
    dot = _math(nt, prefix, "GREATER_THAN", noise(ix, iy, which, "Dots", x + 2200, y - 1000).outputs[0], 0.45,
                x=x + 2600, y=y - 1000)
    # the dots stay off the cell's border, so the glyphs stand apart
    off_u = _math(nt, prefix, "ABSOLUTE", _math(nt, prefix, "SUBTRACT", fu, 0.5, x=x + 1400, y=y - 1300), x=x + 1600,
                  y=y - 1300)
    off_v = _math(nt, prefix, "ABSOLUTE", _math(nt, prefix, "SUBTRACT", fv, 0.5, x=x + 1400, y=y - 1450), x=x + 1600,
                  y=y - 1450)
    inside = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "LESS_THAN", off_u, 0.38, x=x + 1800, y=y - 1300),
                   _math(nt, prefix, "LESS_THAN", off_v, 0.42, x=x + 1800, y=y - 1450), x=x + 2000, y=y - 1350)
    lit = _math(nt, prefix, "MULTIPLY", dot, inside, x=x + 2800, y=y - 1100)
    tint = _new(nt, "ShaderNodeRGB", prefix + " Code Color", x + 3000, y - 300).outputs[0]
    body = _new(nt, "ShaderNodeVectorMath", prefix + " Code Trail", x + 3600, y - 300, operation="SCALE")
    nt.links.new(tint, body.inputs[0])
    nt.links.new(_math(nt, prefix, "MULTIPLY", _math(nt, prefix, "MULTIPLY", lit, trail, x=x + 3400, y=y - 500), 4.0,
                       x=x + 3600, y=y - 500), body.inputs[3])
    heads = _new(nt, "ShaderNodeVectorMath", prefix + " Code Heads", x + 3800, y - 100, operation="ADD")
    nt.links.new(body.outputs[0], heads.inputs[0])
    white = _math(nt, prefix, "MULTIPLY", _math(nt, prefix, "MULTIPLY", lit, at_head, x=x + 3400, y=y + 100), 6.0,
                  x=x + 3600, y=y + 100)
    nt.links.new(white, heads.inputs[1])  # a value into a vector: white, as bright as the value
    return heads.outputs[0]


def add_paint(mat):
    """New outfit, line art / ink wash / digital rain: where `disperse_paint` is high the surface is a drawing of itself
    (line art, ink wash or the digital rain, by the value MMDD Paint Style: 0, 1, 2); the colour comes in where it
    falls, unevenly like watercolour, with a darker tide line at its edge."""
    nt = mat.node_tree
    if nt is None or mat.get(P_PAINT):
        return
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 250
    y = min(n.location.y for n in outputs) - 5000
    attr = _new(nt, "ShaderNodeAttribute", PAINT + " Attribute", x - 2600, y + 400,
                attribute_type="GEOMETRY", attribute_name=ATTR_PAINT)
    rest = _new(nt, "ShaderNodeAttribute", PAINT + " Rest", x - 2600, y - 200,
                attribute_type="GEOMETRY", attribute_name=ATTR_REST).outputs["Vector"]
    line_art, ink_wash = _drawing(nt, PAINT, _base_color(nt), rest, x - 2400, y)
    frame = _new(nt, "ShaderNodeAttribute", PAINT + " Frame", x - 2600, y - 2400, attribute_type="GEOMETRY",
                 attribute_name=ATTR_FRAME).outputs[2]
    code = _code(nt, PAINT, rest, frame, x - 6400, y - 2400)
    style = _new(nt, "ShaderNodeValue", PAINT + " Style", x - 800, y - 1400).outputs[0]
    drawn = _lerp(nt, line_art, ink_wash, _math(nt, PAINT, "MINIMUM", style, 1.0, x=x - 800, y=y - 1550),
                  PAINT + " Drawn", x - 600, y - 900)
    drawn = _lerp(nt, drawn, code, _math(nt, PAINT, "SUBTRACT", style, 1.0, x=x - 800, y=y - 1700, clamp=True),
                  PAINT + " Coded", x - 400, y - 1100)
    # watercolour: the paint value shifted by a noise on the body, a darker line where the colour stops
    bleed = _new(nt, "ShaderNodeTexNoise", PAINT + " Bleed", x - 1400, y + 200, noise_dimensions="3D")
    nt.links.new(rest, bleed.inputs["Vector"])
    bleed.inputs["Detail"].default_value = 4.0
    shifted = _math(nt, PAINT, "ADD", attr.outputs[2], _math(nt, PAINT, "MULTIPLY_ADD", bleed.outputs[0], 0.6, -0.3,
                                                             x=x - 1200, y=y + 200), x=x - 1000, y=y + 300)
    fac = _new(nt, "ShaderNodeMapRange", PAINT + " Fac", x - 800, y + 300, interpolation_type="SMOOTHSTEP")
    nt.links.new(shifted, fac.inputs[0])
    fac.inputs[1].default_value = 0.3
    fac.inputs[2].default_value = 0.7
    tide = _math(nt, PAINT, "SUBTRACT", 1.0, _math(nt, PAINT, "ABSOLUTE", _math(nt, PAINT, "MULTIPLY_ADD",
                                                                                fac.outputs[0], 2.0, -1.0, x=x - 600,
                                                                                y=y + 100), x=x - 400, y=y + 100),
                 x=x - 200, y=y + 100)
    edged = _new(nt, "ShaderNodeVectorMath", PAINT + " Tide", x - 300, y - 700, operation="SCALE")
    nt.links.new(drawn, edged.inputs[0])
    nt.links.new(_math(nt, PAINT, "MULTIPLY_ADD", tide, -0.45, 1.0, x=x - 300, y=y - 900), edged.inputs[3])
    emission = _new(nt, "ShaderNodeEmission", PAINT + " Emission", x - 100, y - 700)
    nt.links.new(edged.outputs[0], emission.inputs["Color"])
    shader = emission
    alpha = _alpha_source(nt)
    if alpha is not None:  # cut-outs stay see-through
        clear = _new(nt, "ShaderNodeBsdfTransparent", PAINT + " Clear", x - 100, y - 900)
        cover = _new(nt, "ShaderNodeMixShader", PAINT + " Cover", x + 50, y - 800)
        nt.links.new(alpha, cover.inputs[0])
        nt.links.new(clear.outputs[0], cover.inputs[1])
        nt.links.new(emission.outputs[0], cover.inputs[2])
        shader = cover
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (PAINT, i), out.location.x - 180, out.location.y + 900)
        nt.links.new(fac.outputs[0], mix.inputs[0])
        nt.links.new(shader.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_PAINT] = 1


def update_paint(mat, style, paper, ink, cell, glow=(0.2, 1.0, 0.4), code_cell=1.0):
    """Line art (0), ink wash (1) or the digital rain (2), paper and ink colours, the size of the washes / hatching in
    object units, the digital rain's colour and cell size (object units)."""
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    for prefix in (PAINT, SURFACE):
        node = nodes.get(prefix + " Style")
        if node is not None:
            node.outputs[0].default_value = style
        for name, color in ((" Paper", paper), (" Ink", ink)):
            node = nodes.get(prefix + name)
            if node is not None:
                node.outputs[0].default_value = tuple(color) + (1.0,)
        for name, scale in ((" Hatch", 1.0), (" Wash", 0.25), (" Bleed", 0.2)):
            node = nodes.get(prefix + name)
            if node is not None:
                node.inputs["Scale"].default_value = scale / max(cell, 1e-6)
    _set_code(nodes, PAINT, glow, code_cell)


def _set_code(nodes, prefix, glow, cell):
    """Colour and cell size (object units) of the digital rain drawn with `prefix`."""
    tint = nodes.get(prefix + " Code Color")
    if tint is not None:
        tint.outputs[0].default_value = tuple(glow) + (1.0,)
    scale = nodes.get(prefix + " Code Scale")
    if scale is not None:
        scale.outputs[0].default_value = 1.0 / max(cell, 1e-6)


def remove_paint(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_PAINT):
        return
    _unsplice(nt, PAINT + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(PAINT)]:
        nt.nodes.remove(node)
    del mat[P_PAINT]


def ensure_outline_material():
    """The inverted hull of line art / ink wash: flat ink, only its back faces drawn (backface culling), so it shows as
    a line around the outfit; no shadow."""
    mat = bpy.data.materials.get(OUTLINE_MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(OUTLINE_MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 600, 0)
    emission = _new(nt, "ShaderNodeEmission", "MMDD_Emission", 100, 0)
    emission.inputs["Strength"].default_value = 1.0
    light_path = _new(nt, "ShaderNodeLightPath", "Light Path", 100, 300)
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Shadow Clear", 100, 150)
    mix = _new(nt, "ShaderNodeMixShader", "No Shadow", 350, 0)
    nt.links.new(light_path.outputs["Is Shadow Ray"], mix.inputs[0])
    nt.links.new(emission.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = True
    _no_shadow(mat)
    return mat


def update_outline_material(color):
    mat = bpy.data.materials.get(OUTLINE_MATERIAL)
    emission = mat.node_tree.nodes.get("MMDD_Emission") if mat is not None and mat.node_tree else None
    if emission is not None:
        emission.inputs["Color"].default_value = tuple(color) + (1.0,)
        mat.diffuse_color = tuple(color) + (1.0,)


def _ink(nt, near, rest, x, y):
    """Ink wash creeps over the surface in patches (a drawing of the texture in shades of ink on paper); right at the
    edge the ink soaks it dark. Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.25, 0.7, x, y + 400)
    _line_art, wash = _drawing(nt, SURFACE, _base_color(nt), rest, x - 2200, y - 200)
    soak = _new(nt, "ShaderNodeMapRange", SURFACE + " Soak", x - 500, y - 600, interpolation_type="SMOOTHSTEP")
    nt.links.new(near, soak.inputs[0])
    soak.inputs[1].default_value = 0.82
    soak.inputs[4].default_value = 0.75
    ink = nt.nodes.get(SURFACE + " Ink").outputs[0]
    soaked = _lerp(nt, wash, ink, soak.outputs[0], SURFACE + " Soaked", x - 300, y - 500)
    emission = _new(nt, "ShaderNodeEmission", SURFACE + " Ink Emission", x - 100, y - 200)
    nt.links.new(soaked, emission.inputs["Color"])
    # (an Emission has no Alpha input: wrap it so the cut-outs can be kept)
    shader = _new(nt, "ShaderNodeMixShader", SURFACE + " Ink Shader", x + 100, y - 200)
    clear = _new(nt, "ShaderNodeBsdfTransparent", SURFACE + " Ink Clear", x - 100, y - 400)
    shader.inputs[0].default_value = 1.0
    nt.links.new(clear.outputs[0], shader.inputs[1])
    nt.links.new(emission.outputs[0], shader.inputs[2])
    return fac, shader


def add_shadow(mat):
    """Where `disperse_shadow` > 0 the surface turns into a flat black shadow (rising from the shadow)."""
    nt = mat.node_tree
    if nt is None or mat.get(P_SHADOW):
        return
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 250
    y = min(n.location.y for n in outputs) - 4300
    attr = _new(nt, "ShaderNodeAttribute", SHADOW + " Attribute", x - 500, y + 200,
                attribute_type="GEOMETRY", attribute_name=ATTR_SHADOW)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SHADOW + " BSDF", x - 300, y - 100)
    _set_input(bsdf, ("Base Color",), (0.002, 0.002, 0.003, 1.0))
    _set_input(bsdf, ("Roughness",), 1.0)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.0)
    alpha = _alpha_source(nt)
    if alpha is not None:  # lace and other cut-outs keep their holes
        nt.links.new(alpha, bsdf.inputs["Alpha"])
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (SHADOW, i), out.location.x - 180, out.location.y + 750)
        nt.links.new(attr.outputs[2], mix.inputs[0])  # "Fac" / "Factor"
        nt.links.new(bsdf.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_SHADOW] = 1


def remove_shadow(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_SHADOW):
        return
    _unsplice(nt, SHADOW + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(SHADOW)]:
        nt.nodes.remove(node)
    del mat[P_SHADOW]


def ensure_smoke_material():
    """Smoke puff: soft, bright white cotton balls that fade as the smoke clears (ATTR_SMOKE on the instances, or on
    the mesh if they were realized)."""
    return _puffs(SMOKE_MATERIAL, (0.8, 0.81, 0.84, 1.0), (1.0, 1.0, 1.0, 1.0), 0.12)


def ensure_dust_material():
    """The shockwave's dust: the smoke's puffs, dusty grey-brown, hardly glowing, soft and cloudy (thinning out towards
    their outline and in patches, or they look like pebbles)."""
    return _puffs(DUST_MATERIAL, (0.36, 0.33, 0.3, 1.0), (0.5, 0.45, 0.4, 1.0), 0.03, soft=True)


def _puffs(name, color, glow, strength, soft=False):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = _new(nt, "ShaderNodeOutputMaterial", "Output", 400, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", 100, 0)
    _set_input(bsdf, ("Base Color",), color)
    _set_input(bsdf, ("Roughness",), 1.0)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.05)
    _set_input(bsdf, ("Emission Color", "Emission"), glow)
    _set_input(bsdf, ("Emission Strength",), strength)
    cleared = []
    for i, kind in enumerate(("GEOMETRY", "INSTANCER")):
        attr = _new(nt, "ShaderNodeAttribute", "Cleared " + kind.title(), -500, -300 - 200 * i, attribute_type=kind,
                    attribute_name=ATTR_SMOKE)
        cleared.append(attr.outputs["Fac"])
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Clear", 100, -300)
    mix = _new(nt, "ShaderNodeMixShader", "Fade", 300, -100)
    gone = _new(nt, "ShaderNodeMath", "Gone", -300, -350, operation="MAXIMUM")
    nt.links.new(cleared[0], gone.inputs[0])
    nt.links.new(cleared[1], gone.inputs[1])
    if soft:  # see-through = 1 - (1 - gone) * (1 - facing)^2 * patches
        facing = _new(nt, "ShaderNodeLayerWeight", "Outline", -900, -700)
        facing.inputs["Blend"].default_value = 0.5
        dense = _new(nt, "ShaderNodeMath", "Dense", -700, -700, operation="POWER")
        inner = _new(nt, "ShaderNodeMath", "Inner", -800, -850, operation="SUBTRACT")
        inner.inputs[0].default_value = 1.0
        nt.links.new(facing.outputs["Facing"], inner.inputs[1])
        nt.links.new(inner.outputs[0], dense.inputs[0])
        dense.inputs[1].default_value = 2.0
        coords = _new(nt, "ShaderNodeTexCoord", "Coords", -1300, -1000)
        noise = _new(nt, "ShaderNodeTexNoise", "Patches", -1100, -1000, noise_dimensions="3D")
        noise.inputs["Scale"].default_value = 2.5
        nt.links.new(coords.outputs["Generated"], noise.inputs["Vector"])
        patches = _new(nt, "ShaderNodeMapRange", "Patchy", -900, -1000)
        nt.links.new(noise.outputs["Fac"], patches.inputs[0])
        patches.inputs[1].default_value = 0.35
        patches.inputs[2].default_value = 0.65
        patches.inputs[3].default_value = 0.15
        there = _new(nt, "ShaderNodeMath", "There", -500, -800, operation="MULTIPLY")
        nt.links.new(dense.outputs[0], there.inputs[0])
        nt.links.new(patches.outputs[0], there.inputs[1])
        kept = _new(nt, "ShaderNodeMath", "Kept", -500, -500, operation="SUBTRACT")
        kept.inputs[0].default_value = 1.0
        nt.links.new(gone.outputs[0], kept.inputs[1])
        opacity = _new(nt, "ShaderNodeMath", "Opacity", -300, -600, operation="MULTIPLY")
        nt.links.new(kept.outputs[0], opacity.inputs[0])
        nt.links.new(there.outputs[0], opacity.inputs[1])
        clear_by = _new(nt, "ShaderNodeMath", "See Through", -100, -500, operation="SUBTRACT")
        clear_by.inputs[0].default_value = 1.0
        nt.links.new(opacity.outputs[0], clear_by.inputs[1])
        nt.links.new(clear_by.outputs[0], mix.inputs[0])
    else:
        nt.links.new(gone.outputs[0], mix.inputs[0])
    nt.links.new(bsdf.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    out.location.x = 550
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if bpy.app.version < (4, 2, 0):  # legacy EEVEE ignores transparency otherwise
        mat.blend_method = "HASHED"
        mat.shadow_method = "HASHED"
    mat.diffuse_color = color
    return mat


def _veins(nt, near, rest, x, y):
    """Black veins: two webs of warped cells on the rest position (so they stick to the body) that spread and thicken
    as the edge comes, until right at the edge all of it has turned to goo. Returns (factor, shader)."""
    warp = _new(nt, "ShaderNodeTexNoise", SURFACE + " Warp", x - 1700, y - 300, noise_dimensions="3D")
    nt.links.new(rest, warp.inputs["Vector"])
    centered = _new(nt, "ShaderNodeVectorMath", SURFACE + " Center", x - 1500, y - 300, operation="SUBTRACT")
    centered.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(warp.outputs["Color"], centered.inputs[0])
    amount = _new(nt, "ShaderNodeVectorMath", SURFACE + " Amount", x - 1300, y - 300, operation="SCALE")
    nt.links.new(centered.outputs[0], amount.inputs[0])
    coord = _new(nt, "ShaderNodeVectorMath", SURFACE + " Coord", x - 1100, y - 150, operation="ADD")
    nt.links.new(rest, coord.inputs[0])
    nt.links.new(amount.outputs[0], coord.inputs[1])

    def web(name, width, top, yy):
        cells = _new(nt, "ShaderNodeTexVoronoi", SURFACE + " " + name, x - 900, yy, voronoi_dimensions="3D",
                     feature="DISTANCE_TO_EDGE")
        nt.links.new(coord.outputs[0], cells.inputs["Vector"])
        wide = _new(nt, "ShaderNodeMath", SURFACE + " " + name + " Width", x - 900, yy - 250, operation="MULTIPLY")
        nt.links.new(near, wide.inputs[0])
        wide.inputs[1].default_value = width  # in cells, right at the edge
        line = _new(nt, "ShaderNodeMapRange", SURFACE + " " + name + " Line", x - 700, yy)
        nt.links.new(cells.outputs["Distance"], line.inputs[0])
        nt.links.new(wide.outputs[0], line.inputs[2])
        line.inputs[3].default_value = top
        line.inputs[4].default_value = 0.0
        return line

    big = web("Cells", 0.14, 1.0, y)
    fine = web("Fine", 0.08, 0.8, y - 500)
    veins = _new(nt, "ShaderNodeMath", SURFACE + " Veins", x - 500, y - 200, operation="MAXIMUM")
    nt.links.new(big.outputs[0], veins.inputs[0])
    nt.links.new(fine.outputs[0], veins.inputs[1])
    # Only part of the cell walls are veins (a noise picks them), more of them as the edge comes, so they branch
    # and join up instead of drawing closed cells.
    patches = _new(nt, "ShaderNodeTexNoise", SURFACE + " Patches", x - 900, y + 700, noise_dimensions="3D")
    nt.links.new(rest, patches.inputs["Vector"])
    patches.inputs["Detail"].default_value = 2.0
    level = _new(nt, "ShaderNodeMapRange", SURFACE + " Level", x - 900, y + 450)
    nt.links.new(near, level.inputs[0])
    level.inputs[3].default_value = 0.6
    level.inputs[4].default_value = 0.25
    level_top = _new(nt, "ShaderNodeMath", SURFACE + " Level Top", x - 700, y + 450, operation="ADD")
    nt.links.new(level.outputs[0], level_top.inputs[0])
    level_top.inputs[1].default_value = 0.06
    picked = _new(nt, "ShaderNodeMapRange", SURFACE + " Picked", x - 500, y + 600)
    nt.links.new(patches.outputs[0], picked.inputs[0])  # "Fac" / "Factor"
    nt.links.new(level.outputs[0], picked.inputs[1])
    nt.links.new(level_top.outputs[0], picked.inputs[2])
    show = _new(nt, "ShaderNodeMapRange", SURFACE + " Show", x - 700, y + 300)
    nt.links.new(near, show.inputs[0])
    show.inputs[2].default_value = 0.3
    grown = _new(nt, "ShaderNodeMath", SURFACE + " Grown", x - 300, y + 400, operation="MULTIPLY")
    nt.links.new(show.outputs[0], grown.inputs[0])
    nt.links.new(picked.outputs[0], grown.inputs[1])
    shown = _new(nt, "ShaderNodeMath", SURFACE + " Shown", x - 300, y - 100, operation="MULTIPLY")
    nt.links.new(veins.outputs[0], shown.inputs[0])
    nt.links.new(grown.outputs[0], shown.inputs[1])
    # The last stretch before the edge turns black all over.
    dark = _new(nt, "ShaderNodeMath", SURFACE + " Dark", x - 500, y + 300, operation="POWER")
    nt.links.new(near, dark.inputs[0])
    dark.inputs[1].default_value = 6.0
    fac = _new(nt, "ShaderNodeMath", SURFACE + " Fac", x - 100, y + 100, operation="MAXIMUM", use_clamp=True)
    nt.links.new(shown.outputs[0], fac.inputs[0])
    nt.links.new(dark.outputs[0], fac.inputs[1])
    goo = _goo_shader(nt, SURFACE + " Goo", rest, x - 100, y - 900)
    return fac.outputs[0], goo


def _creeping(nt, near, rest, low, high, x, y):
    """A front that creeps in patches: 0 .. 1 as `near` rises from `low` to `high`, shifted by a noise on the rest
    position (the noise is SURFACE + " Noise")."""
    noise = _new(nt, "ShaderNodeTexNoise", SURFACE + " Noise", x - 900, y, noise_dimensions="3D")
    nt.links.new(rest, noise.inputs["Vector"])
    noise.inputs["Detail"].default_value = 4.0
    shifted = _new(nt, "ShaderNodeMath", SURFACE + " Shifted", x - 700, y, operation="MULTIPLY_ADD")
    nt.links.new(noise.outputs[0], shifted.inputs[0])  # "Fac" / "Factor"
    shifted.inputs[1].default_value = 0.6
    shifted.inputs[2].default_value = -0.3
    front = _new(nt, "ShaderNodeMath", SURFACE + " Front", x - 500, y, operation="ADD")
    nt.links.new(near, front.inputs[0])
    nt.links.new(shifted.outputs[0], front.inputs[1])
    fac = _new(nt, "ShaderNodeMapRange", SURFACE + " Fac", x - 300, y, interpolation_type="SMOOTHSTEP")
    nt.links.new(front.outputs[0], fac.inputs[0])
    fac.inputs[1].default_value = low
    fac.inputs[2].default_value = high
    return fac.outputs[0]


def _frost(nt, near, rest, x, y):
    """Frost creeps over the surface in patches and freezes it to ice: clear, glossy, deep-coloured ice with white
    frost grown over it in feathery patches (a fine noise on the rest position), a faint cold glow and a few sparkling
    facets. Between the frost the ice is as clear as SURFACE + " Clarity" says: glass that refracts what is under it.
    Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.35, 0.7, x, y + 400)
    feathers = _new(nt, "ShaderNodeTexNoise", SURFACE + " Feathers", x - 900, y + 100, noise_dimensions="3D")
    nt.links.new(rest, feathers.inputs["Vector"])
    feathers.inputs["Detail"].default_value = 8.0
    feathers.inputs["Roughness"].default_value = 0.65
    white = _new(nt, "ShaderNodeMapRange", SURFACE + " White", x - 700, y + 100, interpolation_type="SMOOTHSTEP")
    nt.links.new(feathers.outputs[0], white.inputs[0])  # "Fac" / "Factor"
    white.inputs[1].default_value = 0.47
    white.inputs[2].default_value = 0.62
    clarity = _new(nt, "ShaderNodeValue", SURFACE + " Clarity", x - 900, y - 650)
    # deep ice is the colour darkened to a quarter, frost the colour itself (the colour goes into Shade's vector); clear
    # ice lets the light through, so it takes the colour itself too
    lighter = _new(nt, "ShaderNodeMath", SURFACE + " Lighter", x - 700, y - 50, operation="MAXIMUM")
    nt.links.new(white.outputs[0], lighter.inputs[0])
    nt.links.new(clarity.outputs[0], lighter.inputs[1])
    tint = _new(nt, "ShaderNodeMath", SURFACE + " Tint", x - 500, y + 100, operation="MULTIPLY_ADD")
    nt.links.new(lighter.outputs[0], tint.inputs[0])
    tint.inputs[1].default_value = 0.75
    tint.inputs[2].default_value = 0.25
    # light goes through the ice between the frost
    open_ice = _new(nt, "ShaderNodeMath", SURFACE + " Open", x - 700, y - 650, operation="SUBTRACT")
    open_ice.inputs[0].default_value = 1.0
    nt.links.new(white.outputs[0], open_ice.inputs[1])
    through = _new(nt, "ShaderNodeMath", SURFACE + " Through", x - 500, y - 650, operation="MULTIPLY")
    nt.links.new(open_ice.outputs[0], through.inputs[0])
    nt.links.new(clarity.outputs[0], through.inputs[1])
    shade = _new(nt, "ShaderNodeVectorMath", SURFACE + " Shade", x - 300, y + 100, operation="SCALE")
    nt.links.new(tint.outputs[0], shade.inputs[3])
    rough = _new(nt, "ShaderNodeMapRange", SURFACE + " Rough", x - 500, y - 100)
    nt.links.new(white.outputs[0], rough.inputs[0])
    rough.inputs[3].default_value = 0.03
    rough.inputs[4].default_value = 0.55
    # one facet in forty sparkles
    facets = _new(nt, "ShaderNodeTexVoronoi", SURFACE + " Facets", x - 900, y - 300, voronoi_dimensions="3D",
                  feature="F1")
    nt.links.new(rest, facets.inputs["Vector"])
    lucky = _new(nt, "ShaderNodeSeparateColor" if bpy.app.version >= (3, 3, 0) else "ShaderNodeSeparateRGB",
                 SURFACE + " Lucky", x - 700, y - 450)
    nt.links.new(facets.outputs["Color"], lucky.inputs[0])
    sparkle = _new(nt, "ShaderNodeMath", SURFACE + " Sparkle", x - 500, y - 450, operation="GREATER_THAN")
    nt.links.new(lucky.outputs[0], sparkle.inputs[0])
    sparkle.inputs[1].default_value = 0.975
    glow = _new(nt, "ShaderNodeMath", SURFACE + " Glow", x - 300, y - 450, operation="MULTIPLY_ADD")
    nt.links.new(sparkle.outputs[0], glow.inputs[0])
    glow.inputs[1].default_value = 6.0
    glow.inputs[2].default_value = 0.06
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SURFACE + " Ice BSDF", x - 100, y - 200)
    _set_input(bsdf, ("Metallic",), 0.0)
    _set_input(bsdf, ("Coat Weight", "Clearcoat"), 1.0)
    _set_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.02)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.9)
    _set_input(bsdf, ("IOR",), ICE_IOR)
    nt.links.new(shade.outputs[0], bsdf.inputs["Base Color"])
    nt.links.new(rough.outputs[0], bsdf.inputs["Roughness"])
    nt.links.new(glow.outputs[0], bsdf.inputs["Emission Strength"])
    transmission = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
    nt.links.new(through.outputs[0], transmission)
    return fac, bsdf


def _char(nt, near, rest, x, y):
    """The surface chars in patches (dark, dull) and right before the edge smoulders: glowing cracks (cell walls on the
    rest position) in the glow colour, then all of it glows. Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.2, 0.55, x, y + 400)
    cracks = _new(nt, "ShaderNodeTexVoronoi", SURFACE + " Cracks", x - 900, y - 200, voronoi_dimensions="3D",
                  feature="DISTANCE_TO_EDGE")
    nt.links.new(rest, cracks.inputs["Vector"])
    line = _new(nt, "ShaderNodeMapRange", SURFACE + " Crack Line", x - 700, y - 200)
    nt.links.new(cracks.outputs["Distance"], line.inputs[0])
    line.inputs[2].default_value = 0.07
    line.inputs[3].default_value = 1.0
    line.inputs[4].default_value = 0.0
    hot = _new(nt, "ShaderNodeMapRange", SURFACE + " Hot", x - 700, y - 450, interpolation_type="SMOOTHSTEP")
    nt.links.new(near, hot.inputs[0])
    hot.inputs[1].default_value = 0.7
    embers = _new(nt, "ShaderNodeMath", SURFACE + " Embers", x - 500, y - 300, operation="MULTIPLY")
    nt.links.new(line.outputs[0], embers.inputs[0])
    nt.links.new(hot.outputs[0], embers.inputs[1])
    burning = _new(nt, "ShaderNodeMapRange", SURFACE + " Burning", x - 500, y - 500, interpolation_type="SMOOTHSTEP")
    nt.links.new(near, burning.inputs[0])
    burning.inputs[1].default_value = 0.92
    burning.inputs[4].default_value = 0.4
    heat = _new(nt, "ShaderNodeMath", SURFACE + " Heat", x - 300, y - 400, operation="MAXIMUM")
    nt.links.new(embers.outputs[0], heat.inputs[0])
    nt.links.new(burning.outputs[0], heat.inputs[1])
    glow = _new(nt, "ShaderNodeMath", SURFACE + " Glow", x - 300, y - 600, operation="MULTIPLY")
    nt.links.new(heat.outputs[0], glow.inputs[0])
    glow.inputs[1].default_value = 6.0
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SURFACE + " Char BSDF", x - 100, y - 200)
    _set_input(bsdf, ("Roughness",), 0.85)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.2)
    nt.links.new(glow.outputs[0], bsdf.inputs["Emission Strength"])
    return fac, bsdf


def _tinted(nt, name, factor, x, y):
    """The colour value `name` (set by update_surface) times `factor`: a vector for a colour input."""
    color = _new(nt, "ShaderNodeRGB", name, x, y).outputs[0]
    shade = _new(nt, "ShaderNodeVectorMath", name + " Shade", x + 200, y, operation="SCALE")
    nt.links.new(color, shade.inputs[0])
    _feed(nt, shade.inputs[3], factor)
    return shade.outputs[0]


def _stone(nt, near, rest, x, y):
    """The surface turns to stone in patches: grey, rough and grainy; as the edge comes cracks open in it (cell walls on
    the rest position), widest right before it. Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.3, 0.7, x, y + 400)
    grain = _new(nt, "ShaderNodeTexNoise", SURFACE + " Grain", x - 900, y - 100, noise_dimensions="3D")
    nt.links.new(rest, grain.inputs["Vector"])
    grain.inputs["Detail"].default_value = 8.0
    cracks = _new(nt, "ShaderNodeTexVoronoi", SURFACE + " Cracks", x - 900, y - 400, voronoi_dimensions="3D",
                  feature="DISTANCE_TO_EDGE")
    nt.links.new(rest, cracks.inputs["Vector"])
    opening = _new(nt, "ShaderNodeMapRange", SURFACE + " Opening", x - 900, y - 700, interpolation_type="SMOOTHSTEP")
    nt.links.new(near, opening.inputs[0])
    opening.inputs[1].default_value = 0.55
    opening.inputs[3].default_value = 0.004
    opening.inputs[4].default_value = 0.07  # crack width, in cells
    line = _new(nt, "ShaderNodeMapRange", SURFACE + " Crack Line", x - 700, y - 400)
    nt.links.new(cracks.outputs["Distance"], line.inputs[0])
    nt.links.new(opening.outputs[0], line.inputs[2])
    line.inputs[3].default_value = 1.0
    line.inputs[4].default_value = 0.0
    tone = _math(nt, SURFACE, "MULTIPLY", _math(nt, SURFACE, "MULTIPLY_ADD", grain.outputs[0], 0.5, 0.62, x=x - 700,
                                                y=y - 100),
                 _math(nt, SURFACE, "MULTIPLY_ADD", line.outputs[0], -0.9, 1.0, x=x - 500, y=y - 400), x=x - 500,
                 y=y - 150)
    bump = _new(nt, "ShaderNodeBump", SURFACE + " Stone Bump", x - 500, y - 650)
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(grain.outputs[0], bump.inputs["Height"])
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SURFACE + " Stone BSDF", x - 100, y - 200)
    nt.links.new(_tinted(nt, SURFACE + " Stone Color", tone, x - 500, y + 100), bsdf.inputs["Base Color"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set_input(bsdf, ("Roughness",), 0.9)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.3)
    return fac, bsdf


def _gold(nt, near, rest, x, y):
    """Liquid gold spreads over the surface in patches, a bright molten line where it is spreading, and turns it to
    polished gold, a little hammered (the colour is the value SURFACE + " Gold BSDF"'s). Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.25, 0.6, x, y + 400)
    ripple = _new(nt, "ShaderNodeTexNoise", SURFACE + " Ripple", x - 900, y - 100, noise_dimensions="3D")
    nt.links.new(rest, ripple.inputs["Vector"])
    ripple.inputs["Detail"].default_value = 3.0
    rough = _new(nt, "ShaderNodeMapRange", SURFACE + " Gold Rough", x - 700, y - 100)
    nt.links.new(ripple.outputs[0], rough.inputs[0])
    for i, value in ((1, 0.3), (2, 0.7), (3, 0.12), (4, 0.32)):
        rough.inputs[i].default_value = value
    molten = _math(nt, SURFACE, "MULTIPLY", _math(nt, SURFACE, "MULTIPLY", fac, _math(nt, SURFACE, "SUBTRACT", 1.0, fac,
                                                                                      x=x - 700, y=y - 400),
                                                  x=x - 500, y=y - 400), 10.0, x=x - 300, y=y - 400)
    bump = _new(nt, "ShaderNodeBump", SURFACE + " Gold Bump", x - 500, y - 650)
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(ripple.outputs[0], bump.inputs["Height"])
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SURFACE + " Gold BSDF", x - 100, y - 200)
    _set_input(bsdf, ("Metallic",), 1.0)
    nt.links.new(rough.outputs[0], bsdf.inputs["Roughness"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(molten, bsdf.inputs["Emission Strength"])
    return fac, bsdf


def _silk(nt, near, rest, x, y):
    """White silk spreads over the surface in patches: soft and sheeny, fine fibres wound round the body (wavy bands
    up the rest position), glowing faintly. Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.2, 0.6, x, y + 400)
    fibres = _new(nt, "ShaderNodeTexWave", SURFACE + " Fibres", x - 900, y - 100, wave_type="BANDS",
                  bands_direction="Z")
    nt.links.new(rest, fibres.inputs["Vector"])
    fibres.inputs["Distortion"].default_value = 6.0
    fibres.inputs["Detail"].default_value = 3.0
    tone = _math(nt, SURFACE, "MULTIPLY_ADD", fibres.outputs[1], 0.16, 0.84, x=x - 700, y=y - 100)
    color = _tinted(nt, SURFACE + " Silk Color", tone, x - 500, y + 100)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SURFACE + " Silk BSDF", x - 100, y - 200)
    nt.links.new(color, bsdf.inputs["Base Color"])
    nt.links.new(color, bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission"))
    _set_input(bsdf, ("Roughness",), 0.45)
    _set_input(bsdf, ("Sheen Weight", "Sheen"), 1.0)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.4)
    _set_input(bsdf, ("Emission Strength",), 0.12)
    return fac, bsdf


def _papercut(nt, near, rest, x, y):
    """A paper cut (窗花, a paper window flower) spreads over the surface in patches: matte paper in the surface
    colour with eight-fold cut-outs in square tiles across the body (seen from the front: the rest position's x and
    z), see-through where they are cut: a hole in the middle, eight pointed petals round it, a ring of dots. Returns
    (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.2, 0.6, x, y + 400)
    math = _shader_math(nt, SURFACE)
    split = _new(nt, "ShaderNodeSeparateXYZ", SURFACE + " Paper Rest", x - 1500, y - 100)
    nt.links.new(rest, split.inputs[0])
    rx, rz = split.outputs[0], split.outputs[2]
    flat = _new(nt, "ShaderNodeCombineXYZ", SURFACE + " Paper Flat", x - 1300, y - 100)
    nt.links.new(rx, flat.inputs[0])
    nt.links.new(rz, flat.inputs[1])
    tiles = _new(nt, "ShaderNodeVectorMath", SURFACE + " Paper Tiles", x - 1100, y - 100, operation="SCALE")
    nt.links.new(flat.outputs[0], tiles.inputs[0])
    tile = _new(nt, "ShaderNodeVectorMath", SURFACE + " Paper Tile", x - 900, y - 100, operation="FRACTION")
    nt.links.new(tiles.outputs[0], tile.inputs[0])
    local = _new(nt, "ShaderNodeVectorMath", SURFACE + " Paper Local", x - 700, y - 100, operation="SUBTRACT")
    nt.links.new(tile.outputs[0], local.inputs[0])
    local.inputs[1].default_value = (0.5, 0.5, 0.0)
    length = _new(nt, "ShaderNodeVectorMath", SURFACE + " Paper Radius", x - 500, y - 100, operation="LENGTH")
    nt.links.new(local.outputs[0], length.inputs[0])
    r = length.outputs["Value"]
    axes = _new(nt, "ShaderNodeSeparateXYZ", SURFACE + " Paper Axes", x - 500, y - 300)
    nt.links.new(local.outputs[0], axes.inputs[0])
    lx, ly = axes.outputs[0], axes.outputs[1]
    c8 = math("COSINE", math("MULTIPLY", math("ARCTAN2", ly, lx, x=x - 300, y=y - 300), 8.0, x=x - 100, y=y - 300),
              x=x + 100, y=y - 300)
    middle = math("LESS_THAN", r, 0.06, x=x - 300, y=y - 100)
    # pointed petals: wide halfway out, narrowing to their ends
    petals = math("GREATER_THAN", math("SUBTRACT", c8, math("MULTIPLY_ADD", math("ABSOLUTE", math(
        "SUBTRACT", r, 0.29, x=x - 300, y=y - 500), x=x - 100, y=y - 500), 3.2, 0.3, x=x + 100, y=y - 500), x=x + 300,
        y=y - 400), 0.0, x=x + 500, y=y - 400)
    petals = math("MULTIPLY", petals, math("LESS_THAN", r, 0.42, x=x + 300, y=y - 600), x=x + 700, y=y - 450)
    dots = math("MULTIPLY", math("LESS_THAN", c8, -0.85, x=x + 300, y=y - 700),
                math("LESS_THAN", math("ABSOLUTE", math("SUBTRACT", r, 0.45, x=x + 100, y=y - 800), x=x + 300,
                                       y=y - 800), 0.03, x=x + 500, y=y - 800), x=x + 700, y=y - 750)
    paper = math("SUBTRACT", 1.0, math("MAXIMUM", math("MAXIMUM", middle, petals, x=x + 900, y=y - 300), dots,
                                       x=x + 1100, y=y - 400), x=x + 1300, y=y - 400)
    color = _new(nt, "ShaderNodeRGB", SURFACE + " Paper Color", x - 300, y + 150)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", SURFACE + " Paper BSDF", x + 1500, y - 200)
    nt.links.new(color.outputs[0], bsdf.inputs["Base Color"])
    nt.links.new(color.outputs[0], bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission"))
    _set_input(bsdf, ("Roughness",), 0.9)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.2)
    _set_input(bsdf, ("Emission Strength",), 0.15)  # (paper in the light: it reads on a dark stage)
    nt.links.new(paper, bsdf.inputs["Alpha"])
    return fac, bsdf


def _code_rain(nt, near, rest, x, y):
    """The digital rain spreads over the surface in patches, brighter right at the edge (the frame comes from
    ATTR_FRAME, which the Base group stores). Returns (factor, shader)."""
    fac = _creeping(nt, near, rest, 0.25, 0.6, x, y + 400)
    frame = _new(nt, "ShaderNodeAttribute", SURFACE + " Frame", x - 1100, y - 800, attribute_type="GEOMETRY",
                 attribute_name=ATTR_FRAME).outputs[2]
    color = _code(nt, SURFACE, rest, frame, x - 4900, y - 300)
    boost = _new(nt, "ShaderNodeVectorMath", SURFACE + " Code Boost", x - 300, y - 300, operation="SCALE")
    nt.links.new(color, boost.inputs[0])
    nt.links.new(_math(nt, SURFACE, "MULTIPLY_ADD", near, 0.9, 0.5, x=x - 500, y=y - 450), boost.inputs[3])
    emission = _new(nt, "ShaderNodeEmission", SURFACE + " Code Emission", x - 100, y - 300)
    nt.links.new(boost.outputs[0], emission.inputs["Color"])
    # (an Emission has no Alpha input: wrap it so the cut-outs can be kept)
    shader = _new(nt, "ShaderNodeMixShader", SURFACE + " Code Shader", x + 100, y - 200)
    clear = _new(nt, "ShaderNodeBsdfTransparent", SURFACE + " Code Clear", x - 100, y - 500)
    shader.inputs[0].default_value = 1.0
    nt.links.new(clear.outputs[0], shader.inputs[1])
    nt.links.new(emission.outputs[0], shader.inputs[2])
    return fac, shader


def add_surface(mat, style):
    """Ahead of the edge (`disperse_ahead`: 0 far ahead .. 1 at the edge, also behind it) the old outfit's surface
    changes: black veins spread under it (VEINS, the symbiote), frost creeps over it (FROST), it chars and smoulders
    (CHAR), turns into an ink wash painting (INK), to stone (STONE) or gold (GOLD), silk wraps it (SILK), the digital
    rain runs down it (CODE) or it turns into a paper cut (PAPERCUT)."""
    nt = mat.node_tree
    if nt is None or mat.get(P_SURFACE) == style:
        return
    remove_surface(mat)
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 250
    y = min(n.location.y for n in outputs) - 3300
    attr = _new(nt, "ShaderNodeAttribute", SURFACE + " Attribute", x - 1100, y + 400,
                attribute_type="GEOMETRY", attribute_name=ATTR_AHEAD)
    near = attr.outputs[2]  # "Fac" / "Factor"
    rest = _new(nt, "ShaderNodeAttribute", SURFACE + " Rest", x - 1900, y - 100,
                attribute_type="GEOMETRY", attribute_name=ATTR_REST).outputs["Vector"]
    make = {"VEINS": _veins, "FROST": _frost, "CHAR": _char, "INK": _ink, "STONE": _stone, "GOLD": _gold,
            "SILK": _silk, "CODE": _code_rain, "PAPERCUT": _papercut}[style]
    fac, shader = make(nt, near, rest, x, y)
    alpha = _alpha_source(nt)
    if alpha is not None:  # cut-outs stay see-through
        target = shader.inputs["Alpha"] if "Alpha" in shader.inputs else shader.inputs[0]
        if target.links:  # (the surface cuts holes of its own: both)
            alpha = _math(nt, SURFACE, "MULTIPLY", target.links[0].from_socket, alpha, x=x - 300, y=y - 900)
        nt.links.new(alpha, target)
    if style == "PAPERCUT" and bpy.app.version < (4, 2, 0) and mat.blend_method == "OPAQUE":
        mat[P_SURFACE_BLEND] = mat.blend_method  # (legacy EEVEE ignores transparency otherwise)
        mat.blend_method = "HASHED"
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (SURFACE, i), out.location.x - 180, out.location.y + 600)
        nt.links.new(fac, mix.inputs[0])
        nt.links.new(shader.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_SURFACE] = style


def update_surface(mat, color, glow_color, cell, metallic=0.0, clarity=0.0, code_cell=1.0):
    """Colour of the veins / ice / char / stone / gold / silk, the glow colour of the smouldering char and the digital
    rain, the cell size (object units), how metallic the veins' goo is, how clear the ice is (clear ice lets EEVEE
    refract through the material) and the digital rain's cell size (object units)."""
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    clear = nodes.get(SURFACE + " Clarity")
    if clear is not None:
        clear.outputs[0].default_value = clarity
    _refraction(mat, clear is not None and clarity > 0.0)
    for name, scale in ((" Cells", 1.0), (" Fine", 2.6), (" Warp", 0.8), (" Patches", 0.7), (" Noise", 0.5),
                        (" Facets", 2.0), (" Feathers", 1.2), (" Cracks", 1.5), (" Grain", 4.0), (" Ripple", 0.9),
                        (" Fibres", 1.3), (" Paper Tiles", 0.45)):
        node = nodes.get(SURFACE + name)
        if node is not None:
            node.inputs["Scale"].default_value = scale / max(cell, 1e-6)
    for name in (" Stone Color", " Silk Color", " Paper Color"):
        node = nodes.get(SURFACE + name)
        if node is not None:
            node.outputs[0].default_value = tuple(color) + (1.0,)
    gold = nodes.get(SURFACE + " Gold BSDF")
    if gold is not None:
        _set_input(gold, ("Base Color",), tuple(color) + (1.0,))
        _set_input(gold, ("Emission Color", "Emission"), tuple(color) + (1.0,))
    _set_code(nodes, SURFACE, glow_color, code_cell)
    amount = nodes.get(SURFACE + " Amount")
    if amount is not None:
        amount.inputs[3].default_value = 0.6 * cell
    _set_goo(nodes, SURFACE + " Goo", color, cell * 0.5, metallic)
    ice = nodes.get(SURFACE + " Ice BSDF")
    if ice is not None:
        _set_input(ice, ("Emission Color", "Emission"), tuple(color) + (1.0,))
    shade = nodes.get(SURFACE + " Shade")
    if shade is not None:  # (a vector: the Base Color socket takes it as RGB)
        shade.inputs[0].default_value = tuple(color)
    char = nodes.get(SURFACE + " Char BSDF")
    if char is not None:
        _set_input(char, ("Base Color",), tuple(color) + (1.0,))
        _set_input(char, ("Emission Color", "Emission"), tuple(glow_color) + (1.0,))


def remove_surface(mat):
    _refraction(mat, False)
    nt = mat.node_tree
    if nt is None or not mat.get(P_SURFACE):
        return
    _unsplice(nt, SURFACE + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(SURFACE)]:
        nt.nodes.remove(node)
    if P_SURFACE_BLEND in mat:
        mat.blend_method = mat[P_SURFACE_BLEND]
        del mat[P_SURFACE_BLEND]
    del mat[P_SURFACE]


# --------------------------------------------------------------------------- 1.10


def _shader_math(nt, prefix):
    """A math(op, a, b, c, x, y, clamp) helper that names its nodes after `prefix`."""
    def math(op, a, b=None, c=None, x=0, y=0, clamp=False):
        return _math(nt, prefix, op, a, b, c, x=x, y=y, clamp=clamp)
    return math


def _fresh(name):
    """A new material `name` with an empty node tree and an output node; None when it exists already."""
    if bpy.data.materials.get(name) is not None:
        return None, None, None
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return mat, nt, _new(nt, "ShaderNodeOutputMaterial", "Output", 1800, 0)


def _blended(mat):
    """See-through by blending (a smooth haze, no dither): EEVEE Next's Blended render method, or Blend before 4.2."""
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True


def _ramp_stops(ramp, stops):
    """Set a colour ramp to `stops`: (position, (r, g, b, a)) in order (it keeps as many elements)."""
    elements = ramp.color_ramp.elements
    while len(elements) < len(stops):
        elements.new(0.5)
    while len(elements) > len(stops):
        elements.remove(elements[-1])
    for element, (position, color) in zip(elements, stops):
        element.position = position
        element.color = color


def ensure_flame_material():
    """Toon flames: the shell over the body (ATTR_FLAME, burning where it is high, in a noise rising through the world
    with the frame, strongest towards the outline) and the tongues of flame (ATTR_FLAME_CARD: a flame shape with a
    wavering outline, each its own by ATTR_FLAME_SEED on its instance), banded into three flat colours like a cartoon
    (deep, the flame colour, a white-hot core) by a constant colour ramp, blended, casting no shadow."""
    mat, nt, out = _fresh(FLAME_MATERIAL)
    if mat is None:
        return bpy.data.materials[FLAME_MATERIAL]
    math = _shader_math(nt, "Flame")
    amount = _new(nt, "ShaderNodeAttribute", "Burn", -1800, 400, attribute_type="GEOMETRY",
                  attribute_name=ATTR_FLAME).outputs[2]
    card = _new(nt, "ShaderNodeAttribute", "Card", -1800, 100, attribute_type="GEOMETRY",
                attribute_name=ATTR_FLAME_CARD)
    seed = _new(nt, "ShaderNodeAttribute", "Seed", -1800, -150, attribute_type="INSTANCER",
                attribute_name=ATTR_FLAME_SEED).outputs[2]
    frames = [_new(nt, "ShaderNodeAttribute", "Frame " + kind.title(), -1800, -350 - 200 * i, attribute_type=kind,
                   attribute_name=ATTR_FRAME).outputs[2] for i, kind in enumerate(("GEOMETRY", "INSTANCER"))]
    frame = math("MAXIMUM", frames[0], frames[1], x=-1600, y=-400)
    xyz = _new(nt, "ShaderNodeSeparateXYZ", "Card XYZ", -1600, 100)
    nt.links.new(card.outputs["Vector"], xyz.inputs[0])
    cx, cv, is_card = xyz.outputs[0], xyz.outputs[1], xyz.outputs[2]
    # a tongue: wide near its foot, narrowing to a tip, its outline wavering in a noise rising up it
    wobble_at = _new(nt, "ShaderNodeCombineXYZ", "Wobble At", -1300, 300)
    nt.links.new(math("MULTIPLY", cx, 1.3, x=-1450, y=350), wobble_at.inputs[0])
    nt.links.new(math("SUBTRACT", math("MULTIPLY", cv, 2.2, x=-1450, y=200), math("MULTIPLY", frame, 0.11, x=-1450,
                                                                                     y=50), x=-1350, y=150),
                 wobble_at.inputs[1])
    nt.links.new(math("MULTIPLY", seed, 7.0, x=-1450, y=-100), wobble_at.inputs[2])
    wobble = _new(nt, "ShaderNodeTexNoise", "Wobble", -1100, 300, noise_dimensions="3D")
    nt.links.new(wobble_at.outputs[0], wobble.inputs["Vector"])
    wobble.inputs["Scale"].default_value = 2.0
    wobble.inputs["Detail"].default_value = 2.0
    n = wobble.outputs[0]
    width = math("MULTIPLY", math("MINIMUM", math("MULTIPLY_ADD", math("POWER", cv, 0.35, x=-1100, y=0), 1.6, 0.25,
                                                  x=-900, y=0), 1.0, x=-700, y=0),
                 math("POWER", math("SUBTRACT", 1.0, cv, x=-1100, y=-150, clamp=True), 0.85, x=-900, y=-150), x=-500,
                 y=-50)
    sway = math("MULTIPLY", math("MULTIPLY", math("SUBTRACT", n, 0.5, x=-900, y=300), 0.9, x=-700, y=300), cv, x=-500,
                y=300)
    across = math("ABSOLUTE", math("ADD", cx, sway, x=-300, y=250), x=-100, y=250)
    shape = math("MULTIPLY", math("DIVIDE", math("SUBTRACT", width, across, x=-100, y=50),
                                  math("MAXIMUM", width, 0.01, x=-100, y=-100), x=100, y=0), 2.5, x=300, y=0,
                 clamp=True)
    # (mostly the flame colour; the white-hot core only in the hottest spots near its foot)
    tongue = math("MULTIPLY", math("MULTIPLY", shape, math("POWER", math("SUBTRACT", 1.0, cv, x=100, y=-250,
                                                                         clamp=True), 0.5, x=300, y=-250), x=500,
                                   y=-100),
                  math("MULTIPLY_ADD", n, 0.45, 0.4, x=300, y=-400), x=700, y=-150, clamp=True)
    # the shell: a noise in the world, stretched up and rising with the frame, burning where it is high, more towards
    # the outline (the body seen through the middle of it)
    where = _new(nt, "ShaderNodeNewGeometry", "Where", -1800, -800)
    scale = _new(nt, "ShaderNodeValue", "MMDD_Scale", -1800, -1050)
    speed = _new(nt, "ShaderNodeValue", "MMDD_Speed", -1800, -1200)
    stretch = _new(nt, "ShaderNodeVectorMath", "Stretch", -1600, -800, operation="MULTIPLY")
    nt.links.new(where.outputs["Position"], stretch.inputs[0])
    stretch.inputs[1].default_value = (1.0, 1.0, 0.55)
    scaled = _new(nt, "ShaderNodeVectorMath", "Scaled", -1400, -800, operation="SCALE")
    nt.links.new(stretch.outputs[0], scaled.inputs[0])
    nt.links.new(scale.outputs[0], scaled.inputs[3])
    rising = _new(nt, "ShaderNodeCombineXYZ", "Rising", -1400, -1100)
    nt.links.new(math("MULTIPLY", frame, speed.outputs[0], x=-1600, y=-1150), rising.inputs[2])
    moved = _new(nt, "ShaderNodeVectorMath", "Moved", -1200, -900, operation="SUBTRACT")
    nt.links.new(scaled.outputs[0], moved.inputs[0])
    nt.links.new(rising.outputs[0], moved.inputs[1])
    licks = _new(nt, "ShaderNodeTexNoise", "Licks", -1000, -900, noise_dimensions="3D")
    nt.links.new(moved.outputs[0], licks.inputs["Vector"])
    licks.inputs["Scale"].default_value = 1.0
    licks.inputs["Detail"].default_value = 3.0
    _set_input(licks, ("Roughness",), 0.55)
    outline = _new(nt, "ShaderNodeLayerWeight", "Outline", -1000, -1250)
    outline.inputs["Blend"].default_value = 0.4
    # burning towards the outline: over the middle of the body only a thin veil, so the body shows through
    rim = math("MULTIPLY_ADD", math("POWER", outline.outputs["Facing"], 1.3, x=-800, y=-1250), 0.8, 0.2, x=-600,
               y=-1200)
    shell = math("MULTIPLY", math("MULTIPLY", amount, math("MULTIPLY", math("SUBTRACT", licks.outputs[0], 0.42, x=-800,
                                                                             y=-900), 3.2, x=-600, y=-900,
                                                            clamp=True), x=-400, y=-900),
                 math("MULTIPLY", rim, 0.85, x=-400, y=-1100), x=-200, y=-1000)
    heat = math("ADD", shell, math("MULTIPLY", math("SUBTRACT", tongue, shell, x=900, y=-400), is_card, x=1000, y=-450),
                x=1100, y=-500)
    ramp = _new(nt, "ShaderNodeValToRGB", "MMDD_Bands", 1200, -500)
    ramp.color_ramp.interpolation = "CONSTANT"
    nt.links.new(heat, ramp.inputs[0])  # "Fac" / "Factor"
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", 1200, -900)
    glow = _new(nt, "ShaderNodeEmission", "Glow", 1500, -500)
    nt.links.new(ramp.outputs["Color"], glow.inputs["Color"])
    # (not so bright that the colour washes out to white)
    nt.links.new(math("MULTIPLY", strength.outputs[0], math("MULTIPLY_ADD", heat, 0.55, 0.15, x=1300, y=-1000), x=1400,
                      y=-950), glow.inputs["Strength"])
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Clear", 1500, -250)
    mix = _new(nt, "ShaderNodeMixShader", "Burn Mix", 1650, -350)
    nt.links.new(ramp.outputs["Alpha"], mix.inputs[0])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(glow.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    _blended(mat)
    _no_shadow(mat)
    return mat


def update_flame_material(color, strength, height):
    """Flame colour (deep at the edges, a white-hot core), brightness, and the size of the shell's licks (a tenth of
    the model `height`), rising a fortieth of it a frame."""
    mat = bpy.data.materials.get(FLAME_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    c = tuple(color)
    deep = tuple(0.5 * v for v in c)
    core = tuple(v + (1.0 - v) * 0.6 for v in c)
    # flat bands like a cartoon: see-through deep colour at the fringe, the flame colour, a small hot core
    _ramp_stops(nodes["MMDD_Bands"], ((0.0, deep + (0.0,)), (0.16, deep + (0.6,)), (0.38, c + (0.92,)),
                                      (0.8, core + (1.0,))))
    nodes["MMDD_Strength"].outputs[0].default_value = strength
    nodes["MMDD_Scale"].outputs[0].default_value = 10.0 / max(height, 1e-4)
    nodes["MMDD_Speed"].outputs[0].default_value = 0.25
    mat.diffuse_color = c + (1.0,)


def ensure_lotus_material():
    """Lotus petals (ATTR_PETAL across and up a petal): the particle colour deepening towards the foot and paling to
    the tip, fine veins up it, a little light of its own so it reads on a dark stage; see-through, more opaque where it
    is seen edge-on and along its rim, which glows in the glow colour as ATTR_EDGE says (the flash at the moment)."""
    mat, nt, out = _fresh(LOTUS_MATERIAL)
    if mat is None:
        return bpy.data.materials[LOTUS_MATERIAL]
    math = _shader_math(nt, "Lotus")
    petal = _new(nt, "ShaderNodeAttribute", "Petal", -1600, 200, attribute_type="GEOMETRY", attribute_name=ATTR_PETAL)
    glow = _new(nt, "ShaderNodeAttribute", "Glow", -1600, -200, attribute_type="GEOMETRY",
                attribute_name=ATTR_EDGE).outputs[2]
    xyz = _new(nt, "ShaderNodeSeparateXYZ", "Across Up", -1400, 200)
    nt.links.new(petal.outputs["Vector"], xyz.inputs[0])
    u, v = xyz.outputs[0], xyz.outputs[1]
    tint = _new(nt, "ShaderNodeRGB", "MMDD_Color", -1400, 500)
    deep = _new(nt, "ShaderNodeVectorMath", "Deep", -1200, 500, operation="SCALE")
    nt.links.new(tint.outputs[0], deep.inputs[0])
    deep.inputs[3].default_value = 0.85
    pale = _new(nt, "ShaderNodeVectorMath", "Pale", -1200, 650, operation="MULTIPLY_ADD")  # 25% of the way to white
    nt.links.new(tint.outputs[0], pale.inputs[0])
    pale.inputs[1].default_value = (0.75, 0.75, 0.75)
    pale.inputs[2].default_value = (0.25, 0.24, 0.23)
    color = _lerp(nt, deep.outputs[0], pale.outputs[0], math("POWER", v, 1.3, x=-1200, y=300), "Up", -900, 500)
    veins = math("MULTIPLY_ADD", math("COSINE", math("MULTIPLY", u, 18.0, x=-1200, y=0), x=-1000, y=0), 0.07, 0.93,
                 x=-800, y=0)
    veined = _new(nt, "ShaderNodeVectorMath", "Veined", -600, 400, operation="SCALE")
    nt.links.new(color, veined.inputs[0])
    nt.links.new(veins, veined.inputs[3])
    side = math("MULTIPLY", math("SUBTRACT", math("ABSOLUTE", u, x=-1200, y=-400), 0.75, x=-1000, y=-400), 4.0,
                x=-800, y=-400, clamp=True)
    tip = math("MULTIPLY", math("SUBTRACT", v, 0.9, x=-1000, y=-600), 10.0, x=-800, y=-600, clamp=True)
    rim = math("MAXIMUM", side, tip, x=-600, y=-500)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", "MMDD_BSDF", -200, 400)
    nt.links.new(veined.outputs[0], bsdf.inputs["Base Color"])
    _set_input(bsdf, ("Roughness",), 0.45)
    emit_in = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    nt.links.new(veined.outputs[0], emit_in)
    _set_input(bsdf, ("Emission Strength",), 0.12)
    shine = _new(nt, "ShaderNodeRGB", "MMDD_Glow", -400, -800)
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", -400, -1000)
    light = _new(nt, "ShaderNodeEmission", "Rim Light", 0, -600)
    nt.links.new(shine.outputs[0], light.inputs["Color"])
    nt.links.new(math("MULTIPLY", math("MULTIPLY", glow, math("MULTIPLY", rim, 1.7, x=-200, y=-700), x=0,
                                       y=-800), strength.outputs[0], x=200, y=-850), light.inputs["Strength"])
    both = _new(nt, "ShaderNodeAddShader", "Lit", 400, 200)
    nt.links.new(bsdf.outputs[0], both.inputs[0])
    nt.links.new(light.outputs[0], both.inputs[1])
    facing = _new(nt, "ShaderNodeLayerWeight", "Edge On", -400, -1200)
    facing.inputs["Blend"].default_value = 0.5
    alpha = math("ADD", math("MULTIPLY_ADD", facing.outputs["Facing"], 0.4, 0.5, x=-200, y=-1200),
                 math("MULTIPLY", rim, 0.4, x=-200, y=-1350), x=0, y=-1250, clamp=True)
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Clear", 400, -100)
    mix = _new(nt, "ShaderNodeMixShader", "See Through", 700, 0)
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(both.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if bpy.app.version < (4, 2, 0):  # legacy EEVEE ignores transparency otherwise
        mat.blend_method = "HASHED"
    _no_shadow(mat)
    return mat


def update_lotus_material(color, glow_color, strength):
    mat = bpy.data.materials.get(LOTUS_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    nodes["MMDD_Color"].outputs[0].default_value = tuple(color) + (1.0,)
    nodes["MMDD_Glow"].outputs[0].default_value = tuple(glow_color) + (1.0,)
    nodes["MMDD_Strength"].outputs[0].default_value = strength
    mat.diffuse_color = tuple(color) + (1.0,)


# The soul rings' colours by their age in Soul Land: yellow (a hundred years), purple (a thousand), black (ten
# thousand), red (a hundred thousand), in a strong order for nine rings.
SOUL_COLORS = ((1.0, 0.8, 0.12), (1.0, 0.8, 0.12), (0.62, 0.2, 1.0), (0.62, 0.2, 1.0), (0.12, 0.02, 0.22),
               (0.12, 0.02, 0.22), (0.12, 0.02, 0.22), (1.0, 0.08, 0.05), (1.0, 0.08, 0.05))


def ensure_soul_material():
    """Soul rings: bands of light (ATTR_BAND across a band), each ring in its colour by ATTR_SOUL.x (which ring) and as
    bright as ATTR_SOUL.y says (both on its instance); brightest along the middle of the band, black rings with a
    violet rim so they read on a dark stage. Blended, no shadow."""
    mat, nt, out = _fresh(SOUL_MATERIAL)
    if mat is None:
        return bpy.data.materials[SOUL_MATERIAL]
    math = _shader_math(nt, "Soul")
    soul = _new(nt, "ShaderNodeAttribute", "Soul", -1400, 200, attribute_type="INSTANCER", attribute_name=ATTR_SOUL)
    band = _new(nt, "ShaderNodeAttribute", "Band", -1400, -200, attribute_type="GEOMETRY",
                attribute_name=ATTR_BAND).outputs[2]
    xyz = _new(nt, "ShaderNodeSeparateXYZ", "Which", -1200, 200)
    nt.links.new(soul.outputs["Vector"], xyz.inputs[0])
    which, bright = xyz.outputs[0], xyz.outputs[1]
    ramp = _new(nt, "ShaderNodeValToRGB", "MMDD_Colors", -800, 300)
    ramp.color_ramp.interpolation = "CONSTANT"
    # (the black rings have alpha 0 in the ramp)
    _ramp_stops(ramp, [(k / 9.0, tuple(c) + (0.0 if max(c) < 0.3 else 1.0,)) for k, c in enumerate(SOUL_COLORS)])
    nt.links.new(math("DIVIDE", math("ADD", which, 0.5, x=-1000, y=300), 9.0, x=-900, y=300), ramp.inputs[0])
    across = math("SUBTRACT", 1.0, math("ABSOLUTE", band, x=-1200, y=-200), x=-1000, y=-200, clamp=True)
    rim = math("MULTIPLY", math("SUBTRACT", 1.0, across, x=-800, y=-400), 0.6, x=-600, y=-400)
    violet = _new(nt, "ShaderNodeVectorMath", "Rim", -600, 100, operation="MULTIPLY_ADD")
    violet.inputs[0].default_value = (0.5, 0.2, 0.9)
    nt.links.new(rim, violet.inputs[1])
    nt.links.new(ramp.outputs["Color"], violet.inputs[2])
    # a black ring stays dark along its middle and glows deep violet only along its edges
    black = math("SUBTRACT", 1.0, ramp.outputs["Alpha"], x=-600, y=500)
    dark_rim = _new(nt, "ShaderNodeRGB", "Dark Rim", -600, 700)
    dark_rim.outputs[0].default_value = (0.22, 0.03, 0.28, 1.0)
    color = _lerp(nt, violet.outputs[0], dark_rim.outputs[0], black, "Black Ring", -400, 300)
    lit = math("MULTIPLY_ADD", across, 0.8, 0.6, x=-600, y=-450)
    edge = math("MULTIPLY", rim, 1.5, x=-600, y=-550)
    level = math("ADD", lit, math("MULTIPLY", math("SUBTRACT", edge, lit, x=-500, y=-500), black, x=-400, y=-500),
                 x=-300, y=-450)
    strength = _new(nt, "ShaderNodeValue", "MMDD_Strength", -600, -700)
    glow = _new(nt, "ShaderNodeEmission", "Glow", -200, 0)
    nt.links.new(color, glow.inputs["Color"])
    nt.links.new(math("MULTIPLY", math("MULTIPLY", bright, strength.outputs[0], x=-400, y=-600), level, x=-200,
                      y=-500), glow.inputs["Strength"])
    alpha = math("MULTIPLY", math("POWER", across, 0.6, x=-400, y=-900),
                 math("MINIMUM", math("MULTIPLY", bright, 2.0, x=-400, y=-1050), 1.0, x=-200, y=-1050), x=0, y=-950)
    clear = _new(nt, "ShaderNodeBsdfTransparent", "Clear", 0, 200)
    mix = _new(nt, "ShaderNodeMixShader", "Band Mix", 300, 0)
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(glow.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    _blended(mat)
    _no_shadow(mat)
    return mat


def update_soul_material(strength):
    mat = bpy.data.materials.get(SOUL_MATERIAL)
    if mat is not None and mat.node_tree is not None:
        mat.node_tree.nodes["MMDD_Strength"].outputs[0].default_value = strength
        mat.diffuse_color = (1.0, 0.8, 0.12, 1.0)


def ensure_shock_material():
    """The shockwave on the floor: glow like the ring's, as bright as its disperse_edge says, brightest along the
    middle of the band (ATTR_BAND), added over the floor (a plain glow is opaque: where it is faint it would cover the
    shiny floor with a black band)."""
    mat = bpy.data.materials.get(SHOCK_MATERIAL)
    if mat is not None:
        return mat
    mat = _glow_material(SHOCK_MATERIAL)
    nt = mat.node_tree
    band = _new(nt, "ShaderNodeAttribute", "Band", -650, -500, attribute_type="GEOMETRY", attribute_name=ATTR_BAND)
    side = _new(nt, "ShaderNodeMath", "Band Side", -450, -500, operation="ABSOLUTE")
    nt.links.new(band.outputs[2], side.inputs[0])
    across = _new(nt, "ShaderNodeMath", "Across", -300, -500, operation="SUBTRACT")
    across.inputs[0].default_value = 1.0
    nt.links.new(side.outputs[0], across.inputs[1])
    profile = _new(nt, "ShaderNodeMath", "Profile", -150, -500, operation="POWER")
    nt.links.new(across.outputs[0], profile.inputs[0])
    profile.inputs[1].default_value = 1.7
    shaped = _new(nt, "ShaderNodeMath", "Shaped", 0, -350, operation="MULTIPLY")
    nt.links.new(nt.nodes["Amount"].outputs[0], shaped.inputs[0])
    nt.links.new(profile.outputs[0], shaped.inputs[1])
    nt.links.new(shaped.outputs[0], nt.nodes["MMDD_Emission"].inputs["Strength"])
    over = _new(nt, "ShaderNodeAddShader", "Over the Floor", 250, -200)
    floor = _new(nt, "ShaderNodeBsdfTransparent", "Floor Through", 100, -300)
    nt.links.new(nt.nodes["MMDD_Emission"].outputs[0], over.inputs[0])
    nt.links.new(floor.outputs[0], over.inputs[1])
    nt.links.new(over.outputs[0], nt.nodes["No Shadow"].inputs[1])
    _blended(mat)
    return mat


def update_shock_material(color, strength):
    mat = bpy.data.materials.get(SHOCK_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    nodes["MMDD_Emission"].inputs["Color"].default_value = tuple(color) + (1.0,)
    nodes["MMDD_Strength"].outputs[0].default_value = strength
    mat.diffuse_color = tuple(color) + (1.0,)


HUSK_STYLES = ("GHOST", "AMBER", "ASIS", "PVC")
STAND_MATERIAL = "MMD Disperse Figure Stand"


def add_husk(mat):
    """Where `disperse_husk` > 0 (the old outfit left behind as a husk) the surface turns into the husk: a see-through
    ghost of itself glowing in the glow colour towards its outline (style 0), a cicada's amber shell (1), or stays as
    it is (2); in all of them it fades out with disperse_husk (floating away). The style and the "as it is" link are
    set by update_husk."""
    nt = mat.node_tree
    if nt is None or mat.get(P_HUSK):
        return
    outputs = _outputs(nt)
    if not outputs:
        return
    x = min(n.location.x for n in outputs) - 300
    y = min(n.location.y for n in outputs) - 5600
    math = _shader_math(nt, HUSK)
    attr = _new(nt, "ShaderNodeAttribute", HUSK + " Attribute", x - 1400, y + 300, attribute_type="GEOMETRY",
                attribute_name=ATTR_HUSK).outputs[2]
    is_husk = math("GREATER_THAN", attr, 0.0001, x=x - 1200, y=y + 300)
    style = _new(nt, "ShaderNodeValue", HUSK + " Style", x - 1400, y + 100)
    amber_on = math("GREATER_THAN", style.outputs[0], 0.5, x=x - 1200, y=y + 100)
    as_is = math("GREATER_THAN", style.outputs[0], 1.5, x=x - 1200, y=y - 50)
    pvc = math("GREATER_THAN", style.outputs[0], 2.5, x=x - 1200, y=y - 1300)
    facing = _new(nt, "ShaderNodeLayerWeight", HUSK + " Outline", x - 1400, y - 200)
    facing.inputs["Blend"].default_value = 0.35
    edge = facing.outputs["Facing"]
    color = _new(nt, "ShaderNodeRGB", HUSK + " Color", x - 1400, y - 450)
    ghost = _new(nt, "ShaderNodeEmission", HUSK + " Ghost", x - 800, y - 300)
    nt.links.new(color.outputs[0], ghost.inputs["Color"])
    nt.links.new(math("MULTIPLY_ADD", math("MULTIPLY", edge, edge, x=x - 1200, y=y - 300), 2.2, 0.35, x=x - 1000,
                      y=y - 300), ghost.inputs["Strength"])
    shell = _new(nt, "ShaderNodeBsdfPrincipled", HUSK + " Shell", x - 800, y - 700)
    _set_input(shell, ("Base Color",), (0.62, 0.34, 0.07, 1.0))
    _set_input(shell, ("Roughness",), 0.22)
    _set_input(shell, ("Coat Weight", "Clearcoat"), 0.6)
    _set_input(shell, ("Emission Color", "Emission"), (0.75, 0.42, 0.1, 1.0))
    _set_input(shell, ("Emission Strength",), 0.25)
    # how solid each style is: the ghost mostly see-through, solid towards its outline; the shell half see-through
    ghost_alpha = math("MULTIPLY_ADD", math("POWER", edge, 1.5, x=x - 1200, y=y - 900), 0.6, 0.18, x=x - 1000,
                       y=y - 900)
    amber_alpha = math("MULTIPLY_ADD", edge, 0.35, 0.6, x=x - 1000, y=y - 1050)
    alpha = math("ADD", ghost_alpha, math("MULTIPLY", math("SUBTRACT", amber_alpha, ghost_alpha, x=x - 800, y=y - 1000),
                                          amber_on, x=x - 600, y=y - 1000), x=x - 400, y=y - 950)
    alpha = math("ADD", alpha, math("MULTIPLY", math("SUBTRACT", 1.0, alpha, x=x - 400, y=y - 1100), as_is, x=x - 200,
                                    y=y - 1100), x=x, y=y - 1000)
    alpha = math("MULTIPLY", alpha, attr, x=x + 200, y=y - 1000, clamp=True)
    texture_alpha = _alpha_source(nt)
    if texture_alpha is not None:
        alpha = math("MULTIPLY", alpha, texture_alpha, x=x + 400, y=y - 1000)
    clear = _new(nt, "ShaderNodeBsdfTransparent", HUSK + " Clear", x, y - 400)
    # the glossy figure: its own look under a clear coat that shines towards the outline
    sheen = _new(nt, "ShaderNodeLayerWeight", HUSK + " Sheen", x - 1400, y - 1450)
    sheen.inputs["Blend"].default_value = 0.3
    coat_amount = math("MULTIPLY", math("MULTIPLY_ADD", sheen.outputs["Fresnel"], 0.6, 0.15, x=x - 1200, y=y - 1450),
                       pvc, x=x - 1000, y=y - 1400)
    gloss = _new(nt, "ShaderNodeBsdfGlossy", HUSK + " Gloss", x - 800, y - 1500)
    _set_input(gloss, ("Roughness",), 0.12)
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (HUSK, i), out.location.x - 180, out.location.y + 900)
        nt.links.new(is_husk, mix.inputs[0])
        _splice(nt, out, mix)
        pick = _new(nt, "ShaderNodeMixShader", "%s Pick %d" % (HUSK, i), x + 200, y - 200 - 200 * i)
        nt.links.new(amber_on, pick.inputs[0])
        nt.links.new(ghost.outputs[0], pick.inputs[1])
        nt.links.new(shell.outputs[0], pick.inputs[2])
        keep = _new(nt, "ShaderNodeMixShader", "%s Keep %d" % (HUSK, i), x + 400, y - 200 - 200 * i)
        nt.links.new(as_is, keep.inputs[0])
        nt.links.new(pick.outputs[0], keep.inputs[1])
        coat = _new(nt, "ShaderNodeMixShader", "%s Coat %d" % (HUSK, i), x + 500, y - 300 - 200 * i)
        nt.links.new(coat_amount, coat.inputs[0])
        nt.links.new(keep.outputs[0], coat.inputs[1])
        nt.links.new(gloss.outputs[0], coat.inputs[2])
        fade = _new(nt, "ShaderNodeMixShader", "%s Fade %d" % (HUSK, i), x + 600, y - 200 - 200 * i)
        nt.links.new(alpha, fade.inputs[0])
        nt.links.new(clear.outputs[0], fade.inputs[1])
        nt.links.new(coat.outputs[0], fade.inputs[2])
        nt.links.new(fade.outputs[0], mix.inputs[2])
    if bpy.app.version < (4, 2, 0) and mat.blend_method == "OPAQUE":  # legacy EEVEE ignores transparency
        mat[P_HUSK_BLEND] = mat.blend_method
        mat.blend_method = "HASHED"
    mat[P_HUSK] = 1


def update_husk(mat, style, color):
    """The husk's style (HUSK_STYLES), the ghost's colour, and "as it is" linked to what reaches the husk (it keeps the
    surface ahead of the edge, the undersuit ... added after it)."""
    nt = mat.node_tree
    if nt is None or not mat.get(P_HUSK):
        return
    nodes = nt.nodes
    nodes[HUSK + " Style"].outputs[0].default_value = float(HUSK_STYLES.index(style))
    nodes[HUSK + " Color"].outputs[0].default_value = tuple(color) + (1.0,)
    for node in [n for n in nodes if n.name.startswith(HUSK + " Mix ")]:
        i = node.name.rsplit(" ", 1)[1]
        keep = nodes.get("%s Keep %s" % (HUSK, i))
        through = node.inputs[1]
        if keep is None:
            continue
        for link in list(keep.inputs[2].links):
            nt.links.remove(link)
        if through.links:
            nt.links.new(through.links[0].from_socket, keep.inputs[2])


def remove_husk(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_HUSK):
        return
    _unsplice(nt, HUSK + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(HUSK)]:
        nt.nodes.remove(node)
    if P_HUSK_BLEND in mat:
        mat.blend_method = mat[P_HUSK_BLEND]
        del mat[P_HUSK_BLEND]
    del mat[P_HUSK]


# --------------------------------------------------------------------------- the world change (domain.py)

DOMAIN_MATERIAL = "MMD Disperse World"  # + " Sky / Floor / Props / Rim " + the style
DOMAIN_STYLES = ("VOID", "CRIMSON", "FLOWERS", "WATER", "STAGE")
# the rim of the window onto each world, and its floor's glowing front
DOMAIN_ACCENTS = {"VOID": (0.45, 0.65, 1.0), "CRIMSON": (1.0, 0.3, 0.05), "FLOWERS": (1.0, 0.6, 0.8),
                  "WATER": (0.75, 0.92, 1.0), "STAGE": (0.85, 0.45, 1.0)}


class _Nodes:
    """A small helper for the shader graphs of the world change (every node gets a name of its own)."""

    def __init__(self, nt):
        self.nt = nt
        self.count = 0

    def node(self, idname, x, y, **props):
        self.count += 1
        return _new(self.nt, idname, "%s %d" % (idname[10:], self.count), x, y, **props)

    def feed(self, socket, value):
        if value is None:
            return
        if isinstance(value, tuple) and len(value) == 3 and socket.type == "RGBA":
            value = value + (1.0,)
        _feed(self.nt, socket, value)

    def math(self, op, a, b=None, c=None, x=0, y=0, clamp=False):
        n = self.node("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        for sock, value in zip(n.inputs, (a, b, c)):
            self.feed(sock, value)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None, x=0, y=0):
        n = self.node("ShaderNodeVectorMath", x, y, operation=op)
        self.feed(n.inputs[0], a)
        self.feed(n.inputs[1], b)
        if scale is not None:
            self.feed(n.inputs[3], scale)
        return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"]

    def attribute(self, name, x, y, kind="GEOMETRY"):
        return self.node("ShaderNodeAttribute", x, y, attribute_type=kind, attribute_name=name)

    def split(self, vector, x, y):
        n = self.node("ShaderNodeSeparateXYZ", x, y)
        self.feed(n.inputs[0], vector)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def combine(self, a, b, c, x, y):
        n = self.node("ShaderNodeCombineXYZ", x, y)
        for sock, value in zip(n.inputs, (a, b, c)):
            self.feed(sock, value)
        return n.outputs[0]

    def lerp(self, a, b, fac, x, y):
        self.count += 1
        return _lerp(self.nt, a, b, fac, "Lerp %d" % self.count, x, y)

    def scaled(self, color, fac, x, y):
        return self.vmath("SCALE", color, scale=fac, x=x, y=y)

    def add(self, a, b, x, y):
        return self.vmath("ADD", a, b, x=x, y=y)

    def ramp(self, fac, stops, x, y, constant=False):
        n = self.node("ShaderNodeValToRGB", x, y)
        n.color_ramp.interpolation = "CONSTANT" if constant else "LINEAR"
        _ramp_stops(n, [(p, tuple(c) + (1.0,) if len(c) == 3 else c) for p, c in stops])
        self.feed(n.inputs[0], fac)
        return n.outputs[0]

    def noise(self, vector, scale, detail, x, y, w=None):
        n = self.node("ShaderNodeTexNoise", x, y, noise_dimensions="4D" if w is not None else "3D")
        self.feed(n.inputs["Vector"], vector)
        if w is not None:
            self.feed(n.inputs["W"], w)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        return n.outputs["Fac"]

    def voronoi(self, vector, scale, x, y, feature="F1", dims="3D"):
        n = self.node("ShaderNodeTexVoronoi", x, y, voronoi_dimensions=dims, feature=feature)
        self.feed(n.inputs["Vector"], vector)
        self.feed(n.inputs["Scale"], scale)
        return n

    def smooth(self, value, low, high, x, y):
        n = self.node("ShaderNodeMapRange", x, y, interpolation_type="SMOOTHSTEP")
        for sock, v in zip(n.inputs, (value, low, high, 0.0, 1.0)):
            self.feed(sock, v)
        return n.outputs[0]

    def emission(self, color, strength, x, y):
        n = self.node("ShaderNodeEmission", x, y)
        self.feed(n.inputs["Color"], color)
        self.feed(n.inputs["Strength"], strength)
        return n.outputs[0]

    def principled(self, x, y, color=None, roughness=0.5, metallic=0.0, emission=None, strength=1.0, normal=None):
        n = self.node("ShaderNodeBsdfPrincipled", x, y)
        if isinstance(color, bpy.types.NodeSocket):
            self.feed(n.inputs["Base Color"], color)
        elif color is not None:
            n.inputs["Base Color"].default_value = tuple(color) + (1.0,)
        self.feed(n.inputs["Roughness"], roughness)
        self.feed(n.inputs["Metallic"], metallic)
        if emission is not None:
            sock = n.inputs.get("Emission Color") or n.inputs.get("Emission")
            if isinstance(emission, bpy.types.NodeSocket):
                self.feed(sock, emission)
            else:
                sock.default_value = tuple(emission) + (1.0,)
            self.feed(n.inputs["Emission Strength"], strength)
        if normal is not None:
            self.feed(n.inputs["Normal"], normal)
        return n.outputs[0]

    def mix_shader(self, fac, a, b, x, y):
        n = self.node("ShaderNodeMixShader", x, y)
        self.feed(n.inputs[0], fac)
        self.feed(n.inputs[1], a)
        self.feed(n.inputs[2], b)
        return n.outputs[0]


def _star_field(s, vector, scale, density, size, bright, frame, x, y):
    """Twinkling stars: a few of the cells of a Voronoi pattern of `vector`, a soft dot at each."""
    cells = s.voronoi(vector, scale, x, y)
    cr, cg, _cb = s.split(cells.outputs["Color"], x + 200, y - 200)
    picked = s.math("GREATER_THAN", cr, 1.0 - density, x=x + 400, y=y - 200)
    dot = s.math("POWER", s.math("SUBTRACT", 1.0, s.math("DIVIDE", cells.outputs["Distance"], size, x=x + 200, y=y,
                                                         clamp=True), x=x + 400, y=y), 3.0, x=x + 600, y=y)
    twinkle = s.math("MULTIPLY_ADD", s.math("SINE", s.math("MULTIPLY_ADD", frame, 0.15, s.math(
        "MULTIPLY", cg, 6.283, x=x + 400, y=y - 400), x=x + 600, y=y - 400), x=x + 800, y=y - 400), 0.35, 0.65,
                       x=x + 1000, y=y - 400)
    return s.math("MULTIPLY", s.math("MULTIPLY", dot, picked, x=x + 800, y=y), s.math("MULTIPLY", twinkle, bright,
                                                                                       x=x + 1200, y=y - 400),
                  x=x + 1400, y=y)


def _sky_color(s, style, d, frame, x, y):
    """The colour of the sky of `style` in the direction `d` (from the centre) at `frame`."""
    dx, dy, dz = s.split(d, x, y - 600)
    up = s.math("MULTIPLY_ADD", dz, 0.5, 0.5, x=x + 200, y=y - 600)  # 0 straight down .. 1 straight up
    if style == "VOID":
        stars = s.math("ADD", _star_field(s, d, 45.0, 0.35, 0.09, 4.0, frame, x, y),
                       _star_field(s, d, 140.0, 0.5, 0.1, 1.5, frame, x, y - 800), x=x + 1600, y=y)
        haze = s.noise(d, 1.6, 6.0, x, y - 1600, w=s.math("MULTIPLY", frame, 0.002, x=x - 200, y=y - 1700))
        nebula = s.ramp(haze, ((0.45, (0.0, 0.0, 0.0)), (0.6, (0.12, 0.02, 0.25)), (0.72, (0.03, 0.12, 0.45)),
                               (0.85, (0.1, 0.5, 0.8))), x + 200, y - 1600)
        twist = s.math("SUBTRACT", dz, s.math("MULTIPLY", s.math("SINE", s.math("ARCTAN2", dy, dx, x=x + 400,
                                                                                y=y - 2000), x=x + 600, y=y - 2000),
                                               0.25, x=x + 800, y=y - 2000), x=x + 1000, y=y - 2000)
        band = s.math("POWER", s.math("SUBTRACT", 1.0, s.math("DIVIDE", s.math("ABSOLUTE", twist, x=x + 1200,
                                                                               y=y - 2000), 0.18, x=x + 1400,
                                                              y=y - 2000, clamp=True), x=x + 1600, y=y - 2000), 2.0,
                       x=x + 1800, y=y - 2000)
        milky = s.scaled((0.35, 0.4, 0.6), s.math("MULTIPLY", band, s.math("MULTIPLY_ADD", haze, 0.6, 0.4, x=x + 1800,
                                                                             y=y - 2200), x=x + 2000, y=y - 2100),
                         x + 2200, y - 2000)
        color = s.add(s.add((0.002, 0.003, 0.012), s.scaled(nebula, 0.8, x + 2200, y - 1600), x + 2400, y - 1600),
                      milky, x + 2600, y - 1800)
        return s.add(color, s.combine(stars, stars, stars, x + 2400, y), x + 2800, y - 600)
    if style == "CRIMSON":
        grad = s.ramp(up, ((0.45, (0.85, 0.12, 0.03)), (0.52, (0.5, 0.05, 0.02)), (0.68, (0.12, 0.01, 0.01)),
                           (0.9, (0.02, 0.0, 0.0))), x + 400, y)
        clouds = s.smooth(s.noise(d, 2.2, 8.0, x, y - 400, w=s.math("MULTIPLY", frame, 0.004, x=x - 200,
                                                                     y=y - 500)), 0.45, 0.7, x + 200, y - 400)
        color = s.scaled(grad, s.math("SUBTRACT", 1.0, s.math("MULTIPLY", clouds, 0.75, x=x + 400, y=y - 400),
                                      x=x + 600, y=y - 400), x + 800, y)
        sun = s.node("ShaderNodeCombineXYZ", x, y - 900)
        sun.name = sun.label = "World Sun"
        sun.inputs[1].default_value = 0.85
        sun.inputs[2].default_value = 0.5
        c = s.vmath("DOT_PRODUCT", d, s.vmath("NORMALIZE", sun.outputs[0], x=x + 200, y=y - 900), x=x + 400, y=y - 900)
        disk = s.smooth(c, 0.9800, 0.9815, x + 600, y - 900)
        corona = s.math("SUBTRACT", s.smooth(c, 0.962, 0.9815, x + 600, y - 1100), disk, x=x + 800, y=y - 1000)
        color = s.scaled(color, s.math("SUBTRACT", 1.0, disk, x=x + 1000, y=y - 900), x + 1200, y)
        return s.add(color, s.scaled((2.0, 0.55, 0.12), s.math("POWER", corona, 1.5, x=x + 1000, y=y - 1100),
                                     x + 1200, y - 1100), x + 1400, y)
    if style == "FLOWERS":
        grad = s.ramp(up, ((0.45, (0.55, 0.22, 0.32)), (0.52, (0.5, 0.3, 0.42)), (0.7, (0.2, 0.28, 0.55)),
                           (1.0, (0.08, 0.16, 0.45))), x + 400, y)
        clouds = s.smooth(s.noise(d, 2.5, 5.0, x, y - 400, w=s.math("MULTIPLY", frame, 0.001, x=x - 200, y=y - 500)),
                          0.5, 0.66, x + 200, y - 400)
        return s.lerp(grad, (0.75, 0.62, 0.68), s.math("MULTIPLY", clouds, 0.7, x=x + 400, y=y - 400), x + 800, y)
    if style == "WATER":
        grad = s.ramp(up, ((0.45, (0.3, 0.45, 0.7)), (0.52, (0.2, 0.36, 0.68)), (0.75, (0.04, 0.14, 0.5)),
                           (1.0, (0.01, 0.06, 0.32))), x + 400, y)
        clouds = s.smooth(s.noise(d, 2.0, 6.0, x, y - 400, w=s.math("MULTIPLY", frame, 0.0015, x=x - 200,
                                                                     y=y - 500)), 0.5, 0.62, x + 200, y - 400)
        above = s.smooth(dz, -0.15, 0.0, x + 200, y - 600)
        return s.lerp(grad, (0.9, 0.92, 0.95), s.math("MULTIPLY", s.math("MULTIPLY", clouds, above, x=x + 400,
                                                                          y=y - 500), 0.9, x=x + 600, y=y - 500),
                      x + 800, y)
    # STAGE: a dark hall, a crowd of light sticks waving round the horizon
    haze = s.ramp(up, ((0.45, (0.02, 0.015, 0.04)), (0.6, (0.006, 0.005, 0.012)), (1.0, (0.0, 0.0, 0.0))), x + 400, y)
    cells = s.voronoi(d, 320.0, x, y - 400)
    cr, _cg, _cb = s.split(cells.outputs["Color"], x + 200, y - 600)
    dot = s.math("SUBTRACT", 1.0, s.smooth(cells.outputs["Distance"], 0.06, 0.2, x + 200, y - 400), x=x + 400,
                 y=y - 400)
    wave = s.math("MULTIPLY_ADD", s.math("SINE", s.math("MULTIPLY_ADD", frame, 0.3, s.math("MULTIPLY", cr, 6.283,
                                                                                           x=x + 200, y=y - 800),
                                                        x=x + 400, y=y - 800), x=x + 600, y=y - 800), 0.5, 0.5,
                  x=x + 800, y=y - 800)
    band = s.math("MULTIPLY", s.smooth(up, 0.38, 0.4, x + 400, y - 1000),
                  s.math("SUBTRACT", 1.0, s.smooth(up, 0.44, 0.46, x + 400, y - 1150), x=x + 600, y=y - 1100),
                  x=x + 800, y=y - 1000)
    tint = s.ramp(cr, ((0.0, (1.0, 0.25, 0.6)), (0.34, (0.25, 0.85, 1.0)), (0.67, (1.0, 0.85, 0.3))), x + 600, y - 600,
                  constant=True)
    sticks = s.scaled(tint, s.math("MULTIPLY", s.math("MULTIPLY", dot, band, x=x + 1000, y=y - 900),
                                   s.math("MULTIPLY_ADD", wave, 2.0, 1.0, x=x + 1000, y=y - 1050), x=x + 1200,
                                   y=y - 950), x + 1400, y - 600)
    return s.add(haze, sticks, x + 1600, y)


def _floor_shader(s, style, g, frame, opened, accent, x, y):
    """The floor of `style` at `g` (ATTR_GROUND: x, y from the centre and the floor's radius now, in Reach), with a
    glowing line at its front while it spreads."""
    gx, gy, gr = s.split(g, x, y)
    flat = s.combine(gx, gy, 0.0, x + 200, y)
    rr = s.vmath("LENGTH", flat, x=x + 400, y=y)
    front = s.math("SUBTRACT", 1.0, s.smooth(s.math("ABSOLUTE", s.math("SUBTRACT", rr, gr, x=x + 600, y=y - 200),
                                                    x=x + 800, y=y - 200), 0.0, 0.012, x + 1000, y - 200),
                   x=x + 1200, y=y - 200)
    front = s.math("MULTIPLY", front, s.math("SUBTRACT", 1.0, opened, x=x + 1000, y=y - 400), x=x + 1400, y=y - 300)
    glow = s.scaled(accent, s.math("MULTIPLY", front, 4.0, x=x + 1600, y=y - 300), x + 1800, y - 300)
    if style == "VOID":
        stars = _star_field(s, s.vmath("SCALE", flat, scale=1.0, x=x + 600, y=y - 600), 400.0, 0.25, 0.12, 2.0, frame,
                            x + 800, y - 600)
        light = s.add(glow, s.combine(stars, stars, stars, x + 2400, y - 600), x + 2600, y - 400)
        return s.principled(x + 2800, y, (0.004, 0.004, 0.008), 0.08, emission=light)
    if style == "CRIMSON":
        cracks = s.voronoi(flat, 35.0, x + 600, y - 600, feature="DISTANCE_TO_EDGE")
        crack = s.math("SUBTRACT", 1.0, s.smooth(cracks.outputs["Distance"], 0.0, 0.035, x + 800, y - 600), x=x + 1000,
                       y=y - 600)
        burn = s.add(glow, s.scaled((1.0, 0.3, 0.05), s.math("MULTIPLY", crack, 4.0, x=x + 1200, y=y - 700),
                                    x + 1400, y - 600), x + 1600, y - 500)
        return s.principled(x + 2800, y, (0.08, 0.012, 0.008), 0.85, emission=burn)
    if style == "FLOWERS":
        cells = s.voronoi(flat, 70.0, x + 600, y - 600)
        cr, _cg, _cb = s.split(cells.outputs["Color"], x + 800, y - 800)
        dot = s.math("SUBTRACT", 1.0, s.smooth(cells.outputs["Distance"], 0.25, 0.4, x + 800, y - 600), x=x + 1000,
                     y=y - 600)
        petal = s.ramp(cr, ((0.0, (1.0, 0.45, 0.65)), (0.45, (1.0, 0.95, 0.95)), (0.8, (1.0, 0.88, 0.45))),
                       x + 1000, y - 800, constant=True)
        grass = s.lerp((0.03, 0.1, 0.025), (0.07, 0.18, 0.04), s.noise(flat, 40.0, 3.0, x + 800, y - 1100), x + 1000,
                       y - 1100)
        color = s.lerp(grass, petal, dot, x + 1400, y - 900)
        return s.principled(x + 2800, y, color, 0.8, emission=s.add(s.scaled(color, 0.15, x + 1600, y - 900), glow,
                                                                    x + 1800, y - 700))
    if style == "WATER":
        ripple = s.math("SINE", s.math("SUBTRACT", s.math("MULTIPLY", rr, 400.0, x=x + 600, y=y - 600),
                                       s.math("MULTIPLY", frame, 0.35, x=x + 600, y=y - 750), x=x + 800, y=y - 650),
                        x=x + 1000, y=y - 650)
        fade = s.math("SUBTRACT", 1.0, s.smooth(rr, 0.0, 0.35, x + 1000, y - 850), x=x + 1200, y=y - 850)
        bump = s.node("ShaderNodeBump", x + 1600, y - 700)
        bump.inputs["Strength"].default_value = 0.25
        s.feed(bump.inputs["Height"], s.math("MULTIPLY", ripple, fade, x=x + 1400, y=y - 700))
        sheen = s.node("ShaderNodeLayerWeight", x + 1600, y - 1000)
        sheen.inputs["Blend"].default_value = 0.35
        sky = s.lerp((0.02, 0.07, 0.22), (0.25, 0.4, 0.7), sheen.outputs["Fresnel"], x + 1800, y - 1000)
        return s.principled(x + 2800, y, (0.004, 0.012, 0.03), 0.02, emission=s.add(s.scaled(sky, 0.35, x + 2000,
                                                                                               y - 1000),
                                                                                      glow, x + 2200, y - 800),
                            normal=bump.outputs["Normal"])
    # STAGE: a glossy black stage, a pool of light where the dancer stands
    pool = s.math("SUBTRACT", 1.0, s.smooth(rr, 0.04, 0.12, x + 600, y - 600), x=x + 800, y=y - 600)
    light = s.add(glow, s.scaled((1.0, 0.85, 0.6), s.math("MULTIPLY", pool, 1.5, x=x + 1000, y=y - 700), x + 1200,
                                 y - 600), x + 1400, y - 500)
    return s.principled(x + 2800, y, (0.006, 0.006, 0.008), 0.18, emission=light)


def _prop_shader(s, style, out, x, y):
    """What the props of `style` are made of (feathers have their own); returns True when it is see-through."""
    if style == "VOID":  # crystals of light
        facing = s.node("ShaderNodeLayerWeight", x, y - 300)
        facing.inputs["Blend"].default_value = 0.4
        shader = s.principled(x + 400, y, (0.05, 0.08, 0.15), 0.1, emission=(0.5, 0.8, 1.0),
                              strength=s.math("MULTIPLY_ADD", facing.outputs["Facing"], 4.0, 1.0, x=x + 200,
                                              y=y - 300))
    elif style == "CRIMSON":  # swords
        shader = s.principled(x + 400, y, (0.3, 0.27, 0.27), 0.28, metallic=1.0)
    elif style == "FLOWERS":  # petals by the flower, a yellow heart
        info = s.node("ShaderNodeObjectInfo", x, y)
        petal = s.ramp(info.outputs["Random"], ((0.0, (1.0, 0.42, 0.62)), (0.45, (1.0, 0.95, 0.96)),
                                                (0.8, (0.9, 0.55, 1.0))), x + 200, y, constant=True)
        coords = s.node("ShaderNodeTexCoord", x, y - 300)
        _cx, _cy, cz = s.split(coords.outputs["Object"], x + 200, y - 300)
        color = s.lerp(petal, (1.0, 0.85, 0.2), s.math("GREATER_THAN", cz, 0.01, x=x + 400, y=y - 300), x + 600, y)
        shader = s.principled(x + 800, y, color, 0.6, emission=color, strength=0.25)
    else:  # STAGE: beams of light, fading up their length and to their sides; the spotlight round the dancer
        # (ATTR_EDGE 1 on its instance) glows on its far wall only, behind the dancer, so it never veils her
        coords = s.node("ShaderNodeTexCoord", x, y)
        _gx, _gy, gz = s.split(coords.outputs["Generated"], x + 200, y)
        facing = s.node("ShaderNodeLayerWeight", x, y - 300)
        facing.inputs["Blend"].default_value = 0.5
        spot = s.attribute(ATTR_EDGE, x - 200, y - 600, kind="INSTANCER").outputs["Fac"]
        side = s.math("POWER", s.math("SUBTRACT", 1.0, facing.outputs["Facing"], x=x + 400, y=y - 300), 2.0, x=x + 600,
                      y=y - 300)
        # (far: the wall is farther from the camera, level, than the cone's axis, so it never comes between them,
        # not even when the camera is inside the cone: a close-up riding on the head)
        geometry = s.node("ShaderNodeNewGeometry", x - 600, y - 800)
        view = s.node("ShaderNodeCameraData", x - 600, y - 1100)
        where = geometry.outputs["Position"]
        camera = s.vmath("ADD", where, s.vmath("SCALE", geometry.outputs["Incoming"], scale=view.outputs["View Distance"],
                                               x=x - 400, y=y - 950), x=x - 200, y=y - 900)
        axis = s.node("ShaderNodeObjectInfo", x - 600, y - 1300).outputs["Location"]
        level = (1.0, 1.0, 0.0)
        to_wall = s.vmath("LENGTH", s.vmath("MULTIPLY", s.vmath("SUBTRACT", where, camera, x=x, y=y - 850), level,
                                            x=x + 200, y=y - 850), x=x + 400, y=y - 850)
        to_axis = s.vmath("LENGTH", s.vmath("MULTIPLY", s.vmath("SUBTRACT", axis, camera, x=x, y=y - 1100), level,
                                            x=x + 200, y=y - 1100), x=x + 400, y=y - 1100)
        far = s.math("MULTIPLY", s.smooth(to_wall, to_axis, s.math("MULTIPLY", to_axis, 1.05, x=x + 400, y=y - 1250),
                                          x + 600, y - 950), 0.8, x=x + 800, y=y - 950)
        profile = s.math("MULTIPLY", side, s.math("ADD", 1.0, s.math("MULTIPLY", spot, s.math(
            "SUBTRACT", far, 1.0, x=x + 400, y=y - 800), x=x + 600, y=y - 700), x=x + 800, y=y - 650), x=x + 1000,
                         y=y - 450)
        amount = s.math("MULTIPLY", s.math("POWER", s.math("SUBTRACT", 1.0, gz, x=x + 400, y=y), 1.5, x=x + 600, y=y),
                        profile, x=x + 800, y=y)
        add = s.node("ShaderNodeAddShader", x + 1200, y)
        s.feed(add.inputs[0], s.emission((0.75, 0.85, 1.0), s.math("MULTIPLY", amount, 4.0, x=x + 1000, y=y),
                                         x + 1000, y + 200))
        s.feed(add.inputs[1], s.node("ShaderNodeBsdfTransparent", x + 1000, y - 200).outputs[0])
        s.nt.links.new(add.outputs[0], out.inputs["Surface"])
        return True
    s.nt.links.new(shader, out.inputs["Surface"])
    return False


def ensure_domain_materials(style):
    """{"sky", "floor", "props", "rim"}: the materials of the world change of `style`, made the first time."""
    title = style.title()
    made = {}
    for key in ("sky", "floor", "props", "rim"):
        name = "%s %s %s" % (DOMAIN_MATERIAL, key.title(), title)
        mat, nt, out = _fresh(name)
        if mat is None:
            made[key] = bpy.data.materials[name]
            continue
        s = _Nodes(nt)
        frame_state = s.attribute(ATTR_DOMAIN, -2400, 600).outputs["Vector"]
        opened, _closed, frame = s.split(frame_state, -2200, 600)
        accent = DOMAIN_ACCENTS[style]
        if key == "sky":
            # emission only; seen from outside only the far inner wall (EEVEE culls the back faces, Cycles needs the
            # mix)
            color = _sky_color(s, style, s.attribute(ATTR_DIR, -2400, 0).outputs["Vector"], frame, -2200, 0)
            geometry = s.node("ShaderNodeNewGeometry", 1200, 300)
            shader = s.mix_shader(geometry.outputs["Backfacing"], s.emission(color, 1.0, 1200, 0),
                                  s.node("ShaderNodeBsdfTransparent", 1200, -200).outputs[0], 1500, 0)
            nt.links.new(shader, out.inputs["Surface"])
            mat.use_backface_culling = True
        elif key == "floor":
            shader = _floor_shader(s, style, s.attribute(ATTR_GROUND, -2400, 0).outputs["Vector"], frame, opened,
                                   accent, -2200, 0)
            nt.links.new(shader, out.inputs["Surface"])
        elif key == "props":
            if _prop_shader(s, style, out, -1200, 0):
                _blended(mat)
        else:  # the window's rim: brightest towards the outline, see-through elsewhere, only from outside
            facing = s.node("ShaderNodeLayerWeight", -800, 0)
            facing.inputs["Blend"].default_value = 0.3
            edge = s.math("POWER", facing.outputs["Facing"], 3.0, x=-600, y=0)
            add = s.node("ShaderNodeAddShader", 600, 0)
            s.feed(add.inputs[0], s.emission(accent, s.math("MULTIPLY", edge, 6.0, x=-400, y=0), 200, 200))
            s.feed(add.inputs[1], s.node("ShaderNodeBsdfTransparent", 200, -200).outputs[0])
            nt.links.new(add.outputs[0], out.inputs["Surface"])
            mat.use_backface_culling = True
            _blended(mat)
        _no_shadow(mat)
        mat.diffuse_color = tuple(accent) + (1.0,)
        made[key] = mat
    return made


def update_domain_materials(style, sun):
    """Point the crimson sky's dark sun the way of the world vector `sun` (from the centre)."""
    mat = bpy.data.materials.get("%s Sky %s" % (DOMAIN_MATERIAL, style.title()))
    node = mat.node_tree.nodes.get("World Sun") if mat is not None and mat.node_tree else None
    if node is not None:
        for i in range(3):
            node.inputs[i].default_value = sun[i]


def ensure_stand_material():
    """The figurine's stand: clear acrylic, a faint blue, catching the light towards its rim."""
    mat, nt, out = _fresh(STAND_MATERIAL)
    if mat is None:
        return bpy.data.materials[STAND_MATERIAL]
    s = _Nodes(nt)
    facing = s.node("ShaderNodeLayerWeight", -800, 0)
    facing.inputs["Blend"].default_value = 0.2
    gloss = s.node("ShaderNodeBsdfGlossy", -400, 200)
    _set_input(gloss, ("Roughness",), 0.04)
    rim = s.emission((0.7, 0.85, 1.0), s.math("MULTIPLY", facing.outputs["Facing"], 0.6, x=-600, y=-200), -400, -200)
    add = s.node("ShaderNodeAddShader", -200, 0)
    s.feed(add.inputs[0], gloss.outputs[0])
    s.feed(add.inputs[1], rim)
    shader = s.mix_shader(s.math("MULTIPLY_ADD", facing.outputs["Fresnel"], 0.5, 0.15, x=-400, y=-400),
                          s.node("ShaderNodeBsdfTransparent", -200, -300).outputs[0], add.outputs[0], 0, 0)
    nt.links.new(shader, out.inputs["Surface"])
    _blended(mat)
    mat.diffuse_color = (0.8, 0.9, 1.0, 0.3)
    return mat


TOON_CARD_MATERIAL = "MMD Disperse Toon Card"


def ensure_toon_card_material():
    """The card the dancer turns over on (cartoon physics, ATTR_CARD across it): a violet field, deeper towards its
    edges, a gold frame and an inner line, a gold ring with a four-pointed star in the middle and sparkles; the same
    on both sides, glowing a little."""
    mat, nt, out = _fresh(TOON_CARD_MATERIAL)
    if mat is None:
        return bpy.data.materials[TOON_CARD_MATERIAL]
    s = _Nodes(nt)
    u, v, _w = s.split(s.attribute(ATTR_CARD, -2400, 0).outputs["Vector"], -2200, 0)
    # across the card in its own units (0.62 wide, 1.15 tall)
    ax = s.math("MULTIPLY", s.math("SUBTRACT", u, 0.5, x=-2000, y=100), 0.62, x=-1800, y=100)
    ay = s.math("MULTIPLY", s.math("SUBTRACT", v, 0.5, x=-2000, y=-100), 1.15, x=-1800, y=-100)
    to_edge = s.math("MINIMUM", s.math("SUBTRACT", 0.31, s.math("ABSOLUTE", ax, x=-1600, y=200), x=-1400, y=200),
                     s.math("SUBTRACT", 0.575, s.math("ABSOLUTE", ay, x=-1600, y=0), x=-1400, y=0), x=-1200, y=100)
    frame = s.math("ADD", s.math("LESS_THAN", to_edge, 0.022, x=-1000, y=300),
                   s.math("MULTIPLY", s.math("GREATER_THAN", to_edge, 0.036, x=-1000, y=150),
                          s.math("LESS_THAN", to_edge, 0.042, x=-1000, y=0), x=-800, y=100), x=-600, y=200)
    r = s.math("SQRT", s.math("ADD", s.math("MULTIPLY", ax, ax, x=-1400, y=-300), s.math("MULTIPLY", ay, ay, x=-1400,
                                                                                          y=-450), x=-1200, y=-350),
               x=-1000, y=-350)
    ring = s.math("LESS_THAN", s.math("ABSOLUTE", s.math("SUBTRACT", r, 0.17, x=-800, y=-350), x=-600, y=-350), 0.008,
                  x=-400, y=-350)
    # a four-pointed star: |x|^0.5 + |y|^0.5 < its size
    star = s.math("LESS_THAN", s.math("ADD", s.math("POWER", s.math("ABSOLUTE", ax, x=-1200, y=-600), 0.5, x=-1000,
                                                    y=-600),
                                      s.math("POWER", s.math("ABSOLUTE", ay, x=-1200, y=-750), 0.5, x=-1000, y=-750),
                                      x=-800, y=-650), 0.33, x=-600, y=-650)
    gold = s.math("MINIMUM", s.math("ADD", s.math("ADD", frame, ring, x=-400, y=100), star, x=-200, y=0), 1.0, x=0,
                  y=0)
    deep = s.smooth(r, 0.05, 0.6, -800, -900)
    field = s.lerp((0.22, 0.06, 0.4), (0.05, 0.01, 0.12), deep, -600, -900)
    sparkle = _star_field(s, s.combine(ax, ay, 0.0, -1200, -1200), 40.0, 0.3, 0.12, 1.5, 0.0, -1000, -1200)
    field = s.add(field, s.combine(sparkle, sparkle, sparkle, 400, -1200), 600, -900)
    color = s.lerp(field, (1.0, 0.72, 0.25), gold, 800, -300)
    shader = s.principled(1200, 0, color, s.math("SUBTRACT", 0.45, s.math("MULTIPLY", gold, 0.3, x=800, y=-600),
                                                 x=1000, y=-600),
                          metallic=0.0, emission=color, strength=s.math("MULTIPLY_ADD", gold, 1.2, 0.35, x=1000,
                                                                        y=-750))
    nt.links.new(shader, out.inputs["Surface"])
    mat.diffuse_color = (0.22, 0.06, 0.4, 1.0)
    return mat


def remove_domain_materials():
    for mat in [m for m in bpy.data.materials if m.name.startswith(DOMAIN_MATERIAL + " ") and m.users == 0]:
        bpy.data.materials.remove(mat)


TRAIL_MATERIAL = "MMD Disperse Ribbons"  # + " " + the style
STEP_MATERIAL = "MMD Disperse Step Glow"


def ensure_trail_material(style):
    """The dance ribbons of `style` (ATTR_TRAIL: x how far back along the ribbon, 0 at the hand .. 1, y how far it is
    shown; ATTR_ACROSS across the silk): LIGHT a line of light in the glow colour, white-hot along its middle, fading
    towards its tail; SLEEVE white silk, half see-through, its hems a little denser; SASH red silk with gold hems."""
    name = "%s %s" % (TRAIL_MATERIAL, style.title())
    mat, nt, out = _fresh(name)
    if mat is None:
        return bpy.data.materials[name]
    s = _Nodes(nt)
    along, shown, _z = s.split(s.attribute(ATTR_TRAIL, -1800, 0).outputs["Vector"], -1600, 0)
    tint = s.node("ShaderNodeRGB", -1600, 400)
    tint.name = tint.label = "MMDD_Color"
    strength = s.node("ShaderNodeValue", -1600, 600)
    strength.name = strength.label = "MMDD_Strength"
    tail = s.math("SUBTRACT", 1.0, along, x=-1400, y=0)
    if style == "LIGHT":
        facing = s.node("ShaderNodeLayerWeight", -1400, -300)
        facing.inputs["Blend"].default_value = 0.3
        core = s.math("POWER", s.math("SUBTRACT", 1.0, facing.outputs["Facing"], x=-1200, y=-300), 2.0, x=-1000,
                      y=-300)
        color = s.lerp(tint.outputs[0], (1.0, 1.0, 1.0), s.math("MULTIPLY", core, 0.7, x=-800, y=-300), -600, 300)
        fade = s.math("MULTIPLY", s.math("POWER", tail, 1.5, x=-1200, y=0), shown, x=-1000, y=0)
        level = s.math("MULTIPLY", s.math("MULTIPLY", fade, s.math("MULTIPLY_ADD", core, 0.65, 0.35, x=-800, y=-150),
                                          x=-600, y=0), strength.outputs[0], x=-400, y=0)
        add = s.node("ShaderNodeAddShader", 0, 0)
        s.feed(add.inputs[0], s.emission(color, level, -200, 200))
        s.feed(add.inputs[1], s.node("ShaderNodeBsdfTransparent", -200, -200).outputs[0])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
        mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    else:
        across = s.attribute(ATTR_ACROSS, -1800, -600).outputs["Fac"]
        hem = s.smooth(s.math("ABSOLUTE", s.math("SUBTRACT", across, 0.5, x=-1600, y=-600), x=-1400, y=-600),
                       0.36, 0.42, -1200, -600)
        if style == "SLEEVE":
            color, gold, rough = (0.9, 0.9, 0.93), None, 0.4
            glow = s.scaled((1.0, 1.0, 1.0), s.math("MULTIPLY", strength.outputs[0], 0.03, x=-800, y=600), -600, 600)
            alpha = s.math("MULTIPLY", s.math("MULTIPLY_ADD", hem, 0.3, 0.55, x=-1000, y=-500), s.math(
                "MULTIPLY", shown, s.math("SUBTRACT", 1.0, s.math("MULTIPLY", s.math("MULTIPLY", along, along, x=-1200,
                                                                                     y=-800), 0.6, x=-1000, y=-800),
                                          x=-800, y=-800), x=-600, y=-700), x=-400, y=-600)
        else:  # SASH
            gold = hem
            color = s.lerp((0.62, 0.02, 0.02), (1.0, 0.7, 0.22), hem, -1000, 300)
            rough = s.math("SUBTRACT", 0.4, s.math("MULTIPLY", hem, 0.15, x=-1000, y=100), x=-800, y=100)
            glow = s.scaled(color, s.math("MULTIPLY", strength.outputs[0], s.math("MULTIPLY_ADD", hem, 0.06, 0.03,
                                                                                    x=-1000, y=700),
                                          x=-800, y=600), -600, 600)
            alpha = s.math("MULTIPLY", shown, s.math("SUBTRACT", 1.0, s.math("MULTIPLY", s.math(
                "MULTIPLY", along, along, x=-1200, y=-800), 0.3, x=-1000, y=-800), x=-800, y=-800), x=-600, y=-700)
        bsdf = s.principled(-200, 200, color, rough, metallic=s.math("MULTIPLY", gold, 0.8, x=-400, y=500)
                            if gold is not None else 0.0, emission=glow, strength=1.0)
        sheen = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
        _set_input(sheen, ("Sheen Weight", "Sheen"), 0.6)
        nt.links.new(s.mix_shader(alpha, s.node("ShaderNodeBsdfTransparent", 0, -200).outputs[0], bsdf, 200, 0),
                     out.inputs["Surface"])
        mat.diffuse_color = (0.9, 0.9, 0.93, 1.0) if style == "SLEEVE" else (0.62, 0.02, 0.02, 1.0)
    _blended(mat)
    _no_shadow(mat)
    return mat


def update_trail_material(style, color, strength):
    mat = bpy.data.materials.get("%s %s" % (TRAIL_MATERIAL, style.title()))
    if mat is None or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    nodes["MMDD_Color"].outputs[0].default_value = tuple(color) + (1.0,)
    nodes["MMDD_Strength"].outputs[0].default_value = strength
    if style == "LIGHT":
        mat.diffuse_color = tuple(color) + (1.0,)


def ensure_step_material():
    """The seals and ripples underfoot: light in the glow colour, as bright as ATTR_EDGE says."""
    mat, nt, out = _fresh(STEP_MATERIAL)
    if mat is None:
        return bpy.data.materials[STEP_MATERIAL]
    s = _Nodes(nt)
    edge = s.attribute(ATTR_EDGE, -1000, -200).outputs["Fac"]
    tint = s.node("ShaderNodeRGB", -1000, 200)
    tint.name = tint.label = "MMDD_Color"
    strength = s.node("ShaderNodeValue", -1000, 400)
    strength.name = strength.label = "MMDD_Strength"
    add = s.node("ShaderNodeAddShader", 0, 0)
    s.feed(add.inputs[0], s.emission(tint.outputs[0], s.math("MULTIPLY", edge, strength.outputs[0], x=-600, y=0),
                                     -300, 200))
    s.feed(add.inputs[1], s.node("ShaderNodeBsdfTransparent", -300, -200).outputs[0])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _blended(mat)
    _no_shadow(mat)
    return mat


def update_step_material(color, strength):
    mat = bpy.data.materials.get(STEP_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    mat.node_tree.nodes["MMDD_Color"].outputs[0].default_value = tuple(color) + (1.0,)
    mat.node_tree.nodes["MMDD_Strength"].outputs[0].default_value = strength
    mat.diffuse_color = tuple(color) + (1.0,)


WATER_RING_MATERIAL = "MMD Disperse Toon Water"


def ensure_water_ring_material():
    """The front's band of toon water (ATTR_WATER: along it from its head, across it, the frame; ATTR_EDGE how much
    it shows): flat colours like an ukiyo-e print, deep blue along its lower side to pale blue along the upper, white
    lines flowing along it, a scalloped white crest of foam, a white rim; it thins out towards its tail."""
    mat, nt, out = _fresh(WATER_RING_MATERIAL)
    if mat is None:
        return bpy.data.materials[WATER_RING_MATERIAL]
    s = _Nodes(nt)
    along, across, frame = s.split(s.attribute(ATTR_WATER, -2400, 0).outputs["Vector"], -2200, 0)
    shown = s.attribute(ATTR_EDGE, -2400, -900).outputs["Fac"]
    up = s.math("MULTIPLY_ADD", across, 0.5, 0.5, x=-2000, y=0)  # 0 its lower side .. 1 the upper
    base = s.ramp(up, ((0.0, (0.004, 0.03, 0.2)), (0.3, (0.01, 0.12, 0.45)), (0.62, (0.04, 0.35, 0.75)),
                       (0.85, (0.3, 0.7, 0.95))), -1800, 300, constant=True)
    flow = s.math("SUBTRACT", s.math("MULTIPLY", along, 26.0, x=-2000, y=-300), s.math("MULTIPLY", frame, 0.3,
                                                                                      x=-2000, y=-450),
                  x=-1800, y=-350)
    wave = s.math("MULTIPLY", s.math("SINE", flow, x=-1600, y=-350), 0.12, x=-1400, y=-350)
    lines = s.math("LESS_THAN", s.math("ABSOLUTE", s.math("SINE", s.math("MULTIPLY", s.math("ADD", up, wave, x=-1200,
                                                                                         y=-350),
                                                                     15.7, x=-1000, y=-350), x=-800, y=-350),
                                       x=-600, y=-350), 0.16, x=-400, y=-350)
    lines = s.math("MULTIPLY", lines, s.math("LESS_THAN", up, 0.8, x=-600, y=-500), x=-200, y=-400)
    crest = s.math("GREATER_THAN", up, s.math("MULTIPLY_ADD", s.math("ABSOLUTE", s.math("SINE", s.math(
        "MULTIPLY", flow, 2.3, x=-1600, y=-700), x=-1400, y=-700), x=-1200, y=-700), 0.09, 0.84, x=-1000, y=-700),
                   x=-800, y=-700)
    rim = s.math("GREATER_THAN", s.math("ABSOLUTE", across, x=-1200, y=-850), 0.96, x=-1000, y=-850)
    white = s.math("MINIMUM", s.math("ADD", s.math("ADD", lines, crest, x=-200, y=-600), rim, x=0, y=-700), 1.0,
                   x=200, y=-700)
    color = s.lerp(base, (0.92, 0.97, 1.0), white, 400, 0)
    # it thins out towards its tail: the white stays longer than the blue
    thin = s.math("SUBTRACT", 1.0, s.smooth(along, 0.55, 1.0, -1200, -1100), x=-1000, y=-1100)
    alpha = s.math("MULTIPLY", s.math("MINIMUM", s.math("ADD", thin, s.math("MULTIPLY", white, 0.35, x=-800, y=-1250),
                                                        x=-600, y=-1150), 1.0, x=-400, y=-1150),
                   s.math("MINIMUM", s.math("MULTIPLY", shown, 2.0, x=-600, y=-950), 1.0, x=-400, y=-950), x=-200,
                   y=-1050)
    strength = s.node("ShaderNodeValue", 200, -400)
    strength.name = strength.label = "MMDD_Strength"
    light = s.emission(color, s.math("MULTIPLY_ADD", strength.outputs[0], 0.08, 0.6, x=400, y=-400), 600, 0)
    nt.links.new(s.mix_shader(alpha, s.node("ShaderNodeBsdfTransparent", 600, -300).outputs[0], light, 900, 0),
                 out.inputs["Surface"])
    _blended(mat)
    _no_shadow(mat)
    mat.diffuse_color = (0.04, 0.35, 0.75, 1.0)
    return mat


def update_water_ring_material(strength):
    mat = bpy.data.materials.get(WATER_RING_MATERIAL)
    if mat is not None and mat.node_tree is not None:
        mat.node_tree.nodes["MMDD_Strength"].outputs[0].default_value = strength
