"""Wire and particle materials, and the glowing rim injected into the outfits' own materials."""

import bpy

from .node_groups import ATTR_EDGE

WIRE_MATERIAL = "MMD Disperse Wire"
PARTICLE_MATERIAL = "MMD Disperse Particle"
GLOW = "MMDD Edge"  # prefix of every node we add to a user material
P_GLOW = "mmd_disperse_glow"


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
        source = out.inputs["Surface"].links[0].from_socket
        add = _new(nt, "ShaderNodeAddShader", "%s Add %d" % (GLOW, i), out.location.x - 180, out.location.y - 120)
        nt.links.new(source, add.inputs[0])
        nt.links.new(emission.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
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
    for node in [n for n in nt.nodes if n.name.startswith(GLOW + " Add")]:
        source = node.inputs[0].links[0].from_socket if node.inputs[0].links else None
        targets = [link.to_socket for link in node.outputs[0].links]
        nt.nodes.remove(node)
        if source is not None:
            for socket in targets:
                nt.links.new(source, socket)
    for node in [n for n in nt.nodes if n.name.startswith(GLOW)]:
        nt.nodes.remove(node)
    del mat[P_GLOW]
