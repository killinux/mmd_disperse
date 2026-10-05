"""Wire, particle and goo materials, and what we inject into the outfits' own materials: the glowing rim, the
hologram, the glowing inside (back faces near the cut), the dark undersuit and the old outfit's surface ahead of the
edge (black veins, frost, char)."""

import bpy

from .node_groups import ATTR_AHEAD, ATTR_CUT, ATTR_EDGE, ATTR_HOLO, ATTR_LAYER, ATTR_REST

WIRE_MATERIAL = "MMD Disperse Wire"
RIBBON_MATERIAL = "MMD Disperse Ribbon"
PARTICLE_MATERIAL = "MMD Disperse Particle"
GOO_MATERIAL = "MMD Disperse Goo"
COIN_MATERIAL = "MMD Disperse Coin"
ICE_MATERIAL = "MMD Disperse Ice"
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
SURFACE_STYLES = ("VEINS", "FROST", "CHAR")
P_REFRACT = "mmd_disperse_refract"  # material settings to put back once the clear ice is gone
ICE_IOR = 1.31

# The shader nodes we splice in front of a material output always run in this order, whatever order they are added
# in: the surface ahead of the edge and the undersuit (replace the surface) -> inner glow (replaces it on back faces) ->
# hologram -> edge glow (added on top). (name prefix of the node, its pass-through input), first to last.
_CHAIN = ((SURFACE + " Mix", 1), (LAYER + " Mix", 1), (INNER + " Mix", 1), (HOLO + " Mix", 1), (GLOW + " Add", 0))


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


def update_particle_material(settings):
    color = tuple(settings.particle_color) + (1.0,)
    for name in (COIN_MATERIAL, ICE_MATERIAL):
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


def add_hologram(mat):
    """Where `disperse_holo` > 0 (ahead of the edge) the surface turns into a see-through, glowing hologram
    with horizontal scan lines, a bright rim and a scan ring at the hologram's front."""
    nt = mat.node_tree
    if nt is None or mat.get(P_HOLO):
        return
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

    geometry = _new(nt, "ShaderNodeNewGeometry", HOLO + " Geometry", x - 1300, y - 300)
    lines = _new(nt, "ShaderNodeTexWave", HOLO + " Lines", x - 1100, y - 300, wave_type="BANDS",
                 bands_direction="Z")
    nt.links.new(geometry.outputs["Position"], lines.inputs["Vector"])
    sharp = _new(nt, "ShaderNodeMath", HOLO + " Sharpen", x - 900, y - 300, operation="POWER")
    sharp.inputs[1].default_value = 4.0
    nt.links.new(lines.outputs[1], sharp.inputs[0])  # "Fac" / "Factor"
    level = _new(nt, "ShaderNodeMath", HOLO + " Level", x - 700, y - 300, operation="MULTIPLY_ADD")
    level.inputs[1].default_value = 0.7
    level.inputs[2].default_value = 0.3
    nt.links.new(sharp.outputs[0], level.inputs[0])
    rim = _new(nt, "ShaderNodeLayerWeight", HOLO + " Rim", x - 900, y - 550)
    rim.inputs["Blend"].default_value = 0.35
    strength = _new(nt, "ShaderNodeValue", HOLO + " Strength", x - 700, y - 750)
    opacity = _new(nt, "ShaderNodeValue", HOLO + " Opacity", x - 700, y - 900)

    # Light: (lines + 1.5 * rim) * strength + ring * 6 * strength
    lit = _new(nt, "ShaderNodeMath", HOLO + " Lit", x - 500, y - 400, operation="MULTIPLY_ADD")
    lit.inputs[1].default_value = 1.5
    nt.links.new(rim.outputs["Facing"], lit.inputs[0])
    nt.links.new(level.outputs[0], lit.inputs[2])
    ring_lit = _new(nt, "ShaderNodeMath", HOLO + " Ring Lit", x - 500, y - 150, operation="MULTIPLY_ADD")
    ring_lit.inputs[1].default_value = 6.0
    nt.links.new(ring.outputs[0], ring_lit.inputs[0])
    nt.links.new(lit.outputs[0], ring_lit.inputs[2])
    glow = _new(nt, "ShaderNodeMath", HOLO + " Glow", x - 300, y - 200, operation="MULTIPLY")
    nt.links.new(ring_lit.outputs[0], glow.inputs[0])
    nt.links.new(strength.outputs[0], glow.inputs[1])
    emission = _new(nt, "ShaderNodeEmission", HOLO + " Emission", x - 100, y - 200)
    nt.links.new(glow.outputs[0], emission.inputs["Strength"])

    # Cover: opacity * lines + 0.4 * rim + ring, times the texture alpha (lace stays see-through).
    cover = _new(nt, "ShaderNodeMath", HOLO + " Cover", x - 500, y - 700, operation="MULTIPLY")
    nt.links.new(level.outputs[0], cover.inputs[0])
    nt.links.new(opacity.outputs[0], cover.inputs[1])
    cover_rim = _new(nt, "ShaderNodeMath", HOLO + " Cover Rim", x - 300, y - 650, operation="MULTIPLY_ADD")
    cover_rim.inputs[1].default_value = 0.4
    nt.links.new(rim.outputs["Facing"], cover_rim.inputs[0])
    nt.links.new(cover.outputs[0], cover_rim.inputs[2])
    cover_ring = _new(nt, "ShaderNodeMath", HOLO + " Cover Ring", x - 100, y - 650, operation="ADD", use_clamp=True)
    nt.links.new(cover_rim.outputs[0], cover_ring.inputs[0])
    nt.links.new(ring.outputs[0], cover_ring.inputs[1])
    alpha = cover_ring
    texture_alpha = _alpha_source(nt)
    if texture_alpha is not None:
        alpha = _new(nt, "ShaderNodeMath", HOLO + " Alpha", x + 50, y - 650, operation="MULTIPLY")
        nt.links.new(cover_ring.outputs[0], alpha.inputs[0])
        nt.links.new(texture_alpha, alpha.inputs[1])
    clear = _new(nt, "ShaderNodeBsdfTransparent", HOLO + " Clear", x + 50, y - 400)
    hologram = _new(nt, "ShaderNodeMixShader", HOLO + " Shader", x + 200, y - 300)
    nt.links.new(alpha.outputs[0], hologram.inputs[0])
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
    mat[P_HOLO] = 1


def update_hologram(mat, color, strength, opacity, line_spacing):
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    emission = nodes.get(HOLO + " Emission")
    if emission is not None:
        emission.inputs["Color"].default_value = tuple(color) + (1.0,)
    for name, value in ((" Strength", strength), (" Opacity", opacity)):
        node = nodes.get(HOLO + name)
        if node is not None:
            node.outputs[0].default_value = value
    lines = nodes.get(HOLO + " Lines")
    if lines is not None:  # bands repeat every 2*pi/20 texture units
        lines.inputs["Scale"].default_value = 0.31416 / max(line_spacing, 1e-6)


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


def add_surface(mat, style):
    """Ahead of the edge (`disperse_ahead`: 0 far ahead .. 1 at the edge, also behind it) the old outfit's surface
    changes: black veins spread under it (VEINS, the symbiote), frost creeps over it (FROST) or it chars and
    smoulders (CHAR)."""
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
    make = {"VEINS": _veins, "FROST": _frost, "CHAR": _char}[style]
    fac, shader = make(nt, near, rest, x, y)
    alpha = _alpha_source(nt)
    if alpha is not None:  # cut-outs stay see-through
        nt.links.new(alpha, shader.inputs["Alpha"])
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (SURFACE, i), out.location.x - 180, out.location.y + 600)
        nt.links.new(fac, mix.inputs[0])
        nt.links.new(shader.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_SURFACE] = style


def update_surface(mat, color, glow_color, cell, metallic=0.0, clarity=0.0):
    """Colour of the veins / ice / char, the glow colour of the smouldering char, the cell size (object units), how
    metallic the veins' goo is and how clear the ice is (clear ice lets EEVEE refract through the material)."""
    nodes = mat.node_tree.nodes if mat.node_tree else {}
    clear = nodes.get(SURFACE + " Clarity")
    if clear is not None:
        clear.outputs[0].default_value = clarity
    _refraction(mat, clear is not None and clarity > 0.0)
    for name, scale in ((" Cells", 1.0), (" Fine", 2.6), (" Warp", 0.8), (" Patches", 0.7), (" Noise", 0.5),
                        (" Facets", 2.0), (" Feathers", 1.2), (" Cracks", 1.5)):
        node = nodes.get(SURFACE + name)
        if node is not None:
            node.inputs["Scale"].default_value = scale / max(cell, 1e-6)
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
    del mat[P_SURFACE]
