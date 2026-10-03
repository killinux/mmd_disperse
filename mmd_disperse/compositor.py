"""Optional compositor effects: bloom so the emissive wires glow, and an RGB split for the glitch.

Legacy EEVEE (before 4.2) has its own bloom; newer EEVEE and Cycles need a compositor Glare node."""

import bpy

GROUP_NAME = "MMD Disperse Compositing"
GLARE_NAME = "MMD Disperse Bloom"
GLITCH_NAME = "MMD Disperse Glitch"


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


def _insert_before_output(scene, name, idname):
    """Our compositor node `name`, spliced in once between the image and the output."""
    tree, out = _tree_and_output(scene)
    if out is None or not out.inputs:
        raise RuntimeError("Compositor has no output node")
    node = tree.nodes.get(name)
    if node is None:
        target = out.inputs[0]
        if target.links:
            source = target.links[0].from_socket
        else:
            layers = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
            if layers is None:
                layers = tree.nodes.new("CompositorNodeRLayers")
            source = layers.outputs["Image"]
        node = tree.nodes.new(idname)
        node.name = name
        node.location = (out.location.x - 250, out.location.y - 250 * sum(n.name.startswith("MMD Disperse")
                                                                           for n in tree.nodes))
        tree.links.new(source, node.inputs["Image"])
        tree.links.new(node.outputs["Image"], target)
    scene.render.use_compositing = True
    return node


def add_bloom(scene, threshold=0.8, strength=0.6):
    """Turn on bloom; returns "EEVEE" or "COMPOSITOR" depending on how it was done."""
    if bpy.app.version < (4, 2, 0) and scene.render.engine == "BLENDER_EEVEE":
        scene.eevee.use_bloom = True
        scene.eevee.bloom_threshold = threshold
        return "EEVEE"
    _configure(_insert_before_output(scene, GLARE_NAME, "CompositorNodeGlare"), threshold, strength)
    return "COMPOSITOR"


def glitch_expression(start, end, rate, amount):
    """Driver expression: random RGB-split spikes between `start` and `end`, changing `rate` times per frame.
    Only built-in math on `frame`, so Blender runs it as a simple expression even with Python scripts off."""
    return ("{a:.4f} * max(0.0, fmod(abs(sin(floor(frame * {r:.4f}) * 12.9898) * 43758.5453), 1.0) - 0.55) / 0.45"
            " * (frame >= {s}) * (frame <= {e})").format(a=amount, r=rate, s=int(start), e=int(end))


def add_glitch(scene, start, end, rate=0.5, amount=0.06):
    """Lens Distortion with a flickering dispersion (RGB split) while the transformation runs."""
    node = _insert_before_output(scene, GLITCH_NAME, "CompositorNodeLensdist")
    socket = node.inputs["Dispersion"]
    socket.driver_remove("default_value")
    fcurve = socket.driver_add("default_value")
    fcurve.driver.type = "SCRIPTED"
    fcurve.driver.expression = glitch_expression(start, end, rate, amount)
    return node
