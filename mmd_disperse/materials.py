"""Wire and particle materials, and what we inject into the outfits' own materials: the glowing rim, the hologram,
the glowing inside (back faces near the cut) and the dark undersuit."""

import bpy

from .node_groups import ATTR_CUT, ATTR_EDGE, ATTR_HOLO, ATTR_LAYER, ATTR_REST

WIRE_MATERIAL = "MMD Disperse Wire"
RIBBON_MATERIAL = "MMD Disperse Ribbon"
PARTICLE_MATERIAL = "MMD Disperse Particle"
GLOW = "MMDD Edge"  # prefix of every node we add to a user material
P_GLOW = "mmd_disperse_glow"
HOLO = "MMDD Holo"
P_HOLO = "mmd_disperse_holo"
P_BLEND = "mmd_disperse_blend"  # blend mode to restore (legacy EEVEE needs Hashed for the hologram)
INNER = "MMDD Inner"
P_INNER = "mmd_disperse_inner"
LAYER = "MMDD Layer"
P_LAYER = "mmd_disperse_layer"

# The shader nodes we splice in front of a material output always run in this order, whatever order they are added
# in: undersuit (replaces the surface) -> inner glow (replaces it on back faces) -> hologram -> edge glow (added on
# top). (name prefix of the node, its pass-through input), first to last.
_CHAIN = ((LAYER + " Mix", 1), (INNER + " Mix", 1), (HOLO + " Mix", 1), (GLOW + " Add", 0))


def _set_input(node, names, value):
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return


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


def update_particle_material(settings):
    mat = bpy.data.materials.get(PARTICLE_MATERIAL)
    if mat is None or mat.node_tree is None:
        return
    color = tuple(settings.particle_color) + (1.0,)
    bsdf = mat.node_tree.nodes.get("MMDD_BSDF")
    if bsdf is not None:
        _set_input(bsdf, ("Base Color",), color)
        _set_input(bsdf, ("Emission Color", "Emission"), color)
    strength = mat.node_tree.nodes.get("MMDD_Strength")
    if strength is not None:
        strength.outputs[0].default_value = settings.particle_glow
    mat.diffuse_color = color


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
    on the rest position, so they stick to the body)."""
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
    alpha = _alpha_source(nt)
    if alpha is not None:  # lace and other cut-outs keep their holes
        nt.links.new(alpha, bsdf.inputs["Alpha"])
    for i, out in enumerate(outputs):
        mix = _new(nt, "ShaderNodeMixShader", "%s Mix %d" % (LAYER, i), out.location.x - 180, out.location.y + 450)
        nt.links.new(attr.outputs[2], mix.inputs[0])
        nt.links.new(bsdf.outputs[0], mix.inputs[2])
        _splice(nt, out, mix)
    mat[P_LAYER] = 1


def update_layer(mat, color, glow_color, lines, cell):
    """Undersuit colour, colour and brightness of its lines, cell size in object units."""
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


def remove_layer(mat):
    nt = mat.node_tree
    if nt is None or not mat.get(P_LAYER):
        return
    _unsplice(nt, LAYER + " Mix")
    for node in [n for n in nt.nodes if n.name.startswith(LAYER)]:
        nt.nodes.remove(node)
    del mat[P_LAYER]
