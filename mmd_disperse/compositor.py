"""Optional bloom so the emissive wires glow.

Legacy EEVEE (before 4.2) has its own bloom; newer EEVEE and Cycles need a compositor Glare node."""

import bpy

GROUP_NAME = "MMD Disperse Compositing"
GLARE_NAME = "MMD Disperse Bloom"


def _set_socket(node, name, value):
    for sock in node.inputs:
        if sock.name == name:
            sock.default_value = value
            return True
    return False


def _configure(glare, threshold, strength):
    if hasattr(glare, "glare_type"):  # options are properties before Blender 5.0
        types = glare.bl_rna.properties["glare_type"].enum_items.keys()
        glare.glare_type = "BLOOM" if "BLOOM" in types else "FOG_GLOW"  # Bloom type is 4.2+
        glare.quality = "MEDIUM"
    else:  # ... and menu sockets afterwards
        _set_socket(glare, "Type", "Bloom")
        _set_socket(glare, "Quality", "Medium")
    if not _set_socket(glare, "Threshold", threshold):  # a property before Blender 4.4
        glare.threshold = threshold
    _set_socket(glare, "Strength", strength)


def _tree_and_output(scene):
    if hasattr(scene, "compositing_node_group"):  # Blender 5.0+
        tree = scene.compositing_node_group
        if tree is None:
            tree = bpy.data.node_groups.new(GROUP_NAME, "CompositorNodeTree")
            tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            layers = tree.nodes.new("CompositorNodeRLayers")
            layers.location = (-300, 0)
            out = tree.nodes.new("NodeGroupOutput")
            out.location = (300, 0)
            tree.links.new(layers.outputs["Image"], out.inputs["Image"])
            scene.compositing_node_group = tree
        out = next((n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"), None)
    else:
        scene.use_nodes = True
        tree = scene.node_tree
        out = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeComposite"), None)
        if out is None:
            out = tree.nodes.new("CompositorNodeComposite")
    return tree, out


def add_bloom(scene, threshold=0.8, strength=0.6):
    """Turn on bloom; returns "EEVEE" or "COMPOSITOR" depending on how it was done."""
    if bpy.app.version < (4, 2, 0) and scene.render.engine == "BLENDER_EEVEE":
        scene.eevee.use_bloom = True
        scene.eevee.bloom_threshold = threshold
        return "EEVEE"
    tree, out = _tree_and_output(scene)
    if out is None or not out.inputs:
        raise RuntimeError("Compositor has no output node")
    glare = tree.nodes.get(GLARE_NAME)
    if glare is None:
        target = out.inputs[0]
        if target.links:
            source = target.links[0].from_socket
        else:
            layers = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
            if layers is None:
                layers = tree.nodes.new("CompositorNodeRLayers")
            source = layers.outputs["Image"]
        glare = tree.nodes.new("CompositorNodeGlare")
        glare.name = GLARE_NAME
        glare.location = (out.location.x - 250, out.location.y)
        tree.links.new(source, glare.inputs["Image"])
        tree.links.new(glare.outputs["Image"], target)
    _configure(glare, threshold, strength)
    scene.render.use_compositing = True
    return "COMPOSITOR"
