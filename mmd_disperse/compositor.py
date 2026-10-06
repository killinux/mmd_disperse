"""Optional compositor effects: bloom so the emissive wires glow, an RGB split for the glitch and a white flash
for the finale.

Legacy EEVEE (before 4.2) has its own bloom; newer EEVEE and Cycles need a compositor Glare node."""

import bpy

GROUP_NAME = "MMD Disperse Compositing"
GLARE_NAME = "MMD Disperse Bloom"
GLITCH_NAME = "MMD Disperse Glitch"
FLASH_NAME = "MMD Disperse White Flash"
WHITE = 6.0  # scene-linear level the frame flashes to: far above 1, so it is white after the view transform


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


def _existing_tree(scene):
    if hasattr(scene, "compositing_node_group"):  # Blender 5.0+
        return scene.compositing_node_group
    return getattr(scene, "node_tree", None)


def _sockets(node):
    """(image input, image output) of a node we splice in; the Mix node of Blender 5.0+ names them by type."""
    if node.bl_idname == "ShaderNodeMix":
        return (next(s for s in node.inputs if s.identifier == "A_Color"),
                next(s for s in node.outputs if s.identifier == "Result_Color"))
    return node.inputs["Image"], node.outputs["Image"]


def _insert_before_output(scene, name, idname, setup=None):
    """Our compositor node `name`, spliced in once between the image and the output (`setup(node)` runs on a
    new node before it is linked)."""
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
        if setup is not None:
            setup(node)
        image_in, image_out = _sockets(node)
        tree.links.new(source, image_in)
        tree.links.new(image_out, target)
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


def glitch_expression(start, end, rate, amount, beat=False):
    """Driver expression: random RGB-split spikes between `start` and `end`, changing `rate` times per frame, or
    with `beat` a spike on every beat (the variable `b`, the beat pulse) and only small ones between. Only built-in
    math on `frame`, so Blender runs it as a simple expression even with Python scripts off."""
    spikes = "max(0.0, fmod(abs(sin(floor(frame * {r:.4f}) * 12.9898) * 43758.5453), 1.0) - 0.55) / 0.45"
    if beat:
        spikes = "max(b, 0.25 * " + spikes + ")"
    return ("{a:.4f} * " + spikes + " * (frame >= {s}) * (frame <= {e})").format(a=amount, r=rate, s=int(start),
                                                                              e=int(end))


def add_glitch(scene, start, end, rate=0.5, amount=0.06, beat=None):
    """Lens Distortion with a flickering dispersion (RGB split) while the transformation runs; on the beats of the
    `beat` empty (beats.py) when given."""
    node = _insert_before_output(scene, GLITCH_NAME, "CompositorNodeLensdist")
    update_glitch(scene, start, end, rate, amount, beat)
    return node


def update_glitch(scene, start, end, rate=0.5, amount=0.06, beat=None):
    """Drive the RGB split (when the scene has one) for the transformation from `start` to `end`."""
    tree = _existing_tree(scene)
    node = tree.nodes.get(GLITCH_NAME) if tree is not None else None
    if node is None:
        return None
    socket = node.inputs["Dispersion"]
    socket.driver_remove("default_value")
    driver = socket.driver_add("default_value").driver
    driver.type = "SCRIPTED"
    if beat is not None:
        var = driver.variables.new()
        var.name = "b"
        var.type = "TRANSFORMS"
        var.targets[0].id = beat
        var.targets[0].transform_type = "LOC_X"
        var.targets[0].transform_space = "WORLD_SPACE"
    driver.expression = glitch_expression(start, end, rate, amount, beat is not None)
    return node


def flash_expression(wave, rise, fall, amount, strike=None):
    """Driver expression on the mask radius `r`: the frame flashes white where the finale starts (the radius
    passes `wave`), up within `rise` and gone after `fall` more radius. It runs on the radius like the finale
    itself, so it follows retimed mask keys; only built-in math, so Blender runs it as a simple expression even
    with Python scripts off. `strike` = (rise, fall, amount): it also flashes as the mask sets off (lightning strikes
    the start point), up within that rise and gone after that fall."""
    text = ("{a:.4f} * clamp((r - {w:.5f}) / {rise:.5f}, 0, 1) * pow(clamp(1 - (r - {w:.5f}) / {fall:.5f}, 0, 1), 2)"
            .format(a=amount, w=wave, rise=max(rise, 1e-5), fall=max(fall, 1e-5)))
    if strike is not None:
        text += (" + {a:.4f} * clamp(r / {rise:.6f}, 0, 1) * pow(clamp(1 - r / {fall:.5f}, 0, 1), 2)"
                 .format(a=strike[2], rise=max(strike[0], 1e-6), fall=max(strike[1], 1e-5)))
    return text


def _flash_factor(node):
    if node.bl_idname == "ShaderNodeMix":
        return next(s for s in node.inputs if s.identifier == "Factor_Float")
    return next(s for s in node.inputs if s.identifier == "Fac")  # (shown as "Factor" in Blender 5.0+)


def add_white_flash(scene):
    """Mix node that blends the frame towards white; update_white_flash() drives how far."""
    def setup(node):
        if node.bl_idname == "ShaderNodeMix":
            node.data_type = "RGBA"
            white = next(s for s in node.inputs if s.identifier == "B_Color")
        else:
            white = node.inputs[2]
        node.blend_type = "MIX"
        white.default_value = (WHITE, WHITE, WHITE, 1.0)
        _flash_factor(node).default_value = 0.0

    idname = "CompositorNodeMixRGB" if hasattr(bpy.types, "CompositorNodeMixRGB") else "ShaderNodeMix"
    return _insert_before_output(scene, FLASH_NAME, idname, setup)


IMPACT_GREY = "MMD Disperse Impact Grey"
IMPACT_CONTRAST = "MMD Disperse Impact Contrast"
IMPACT_INVERT = "MMD Disperse Impact Invert"
IMPACT_NODES = ((IMPACT_GREY, False), (IMPACT_CONTRAST, False), (IMPACT_INVERT, True))  # (inverting every other frame)


def _set_b(node, color):
    """The B colour of a Mix node we splice in (MixRGB, or the Mix node of Blender 5.0+)."""
    if node.bl_idname == "ShaderNodeMix":
        node.data_type = "RGBA"
        next(s for s in node.inputs if s.identifier == "B_Color").default_value = color
    else:
        node.inputs[2].default_value = color


def add_impact(scene):
    """Anime impact frames: three nodes before the output, one draining the colour out of the picture (Saturation
    with grey), RGB Curves with a hard S that leaves it black and white, one inverting it (Difference with white);
    update_impact() drives them for a few frames."""
    def grey(node):
        node.blend_type = "SATURATION"
        _set_b(node, (0.5, 0.5, 0.5, 1.0))
        _flash_factor(node).default_value = 0.0

    def stark(node):
        curve = node.mapping.curves[3]  # the combined curve
        for x, y in ((0.3, 0.0), (0.42, 0.04), (0.58, 0.96)):
            curve.points.new(x, y)
        node.mapping.update()
        _flash_factor(node).default_value = 0.0

    def invert(node):
        node.blend_type = "DIFFERENCE"
        _set_b(node, (1.0, 1.0, 1.0, 1.0))
        _flash_factor(node).default_value = 0.0

    idname = "CompositorNodeMixRGB" if hasattr(bpy.types, "CompositorNodeMixRGB") else "ShaderNodeMix"
    return (_insert_before_output(scene, IMPACT_GREY, idname, grey),
            _insert_before_output(scene, IMPACT_CONTRAST, "CompositorNodeCurveRGB", stark),
            _insert_before_output(scene, IMPACT_INVERT, idname, invert))


def impact_expression(first, frames, invert):
    """Driver expression on the frame: on for `frames` frames from frame `first`; the inverting one only on every other
    of them (the first, the third ...). Counted in frames, not in mask radius: the front speeds up as it sets off
    (when a move of the dance starts it), and a frame's worth of radius there would skip frames."""
    text = "(frame >= {f}) * (frame < {e})".format(f=int(first), e=int(first) + int(frames))
    if invert:
        text += " * (fmod(frame - {f}, 2) < 0.5)".format(f=int(first))
    return text


def update_impact(scene, first, frames):
    """Drive the impact frames (when the scene has them) for `frames` frames from frame `first`; off when `first` is
    None or there are no frames."""
    tree = _existing_tree(scene)
    for name, invert in IMPACT_NODES:
        node = tree.nodes.get(name) if tree is not None else None
        if node is None:
            continue
        socket = _flash_factor(node)
        socket.driver_remove("default_value")
        if first is None or frames <= 0:
            socket.default_value = 0.0
            continue
        driver = socket.driver_add("default_value").driver
        driver.type = "SCRIPTED"
        driver.expression = impact_expression(first, frames, invert)


def update_white_flash(scene, mask, wave, rise, fall, amount, strike=None):
    """Drive the white flash from the radius of `mask` (see flash_expression); without a mask it is switched
    off. Nothing happens when the scene has no white flash node."""
    tree = _existing_tree(scene)
    node = tree.nodes.get(FLASH_NAME) if tree is not None else None
    if node is None:
        return None
    socket = _flash_factor(node)
    socket.driver_remove("default_value")
    if mask is None or wave <= 0.0:
        socket.default_value = 0.0
        return node
    driver = socket.driver_add("default_value").driver
    driver.type = "SCRIPTED"
    var = driver.variables.new()
    var.name = "r"
    var.type = "TRANSFORMS"
    var.targets[0].id = mask
    var.targets[0].transform_type = "SCALE_AVG"
    var.targets[0].transform_space = "WORLD_SPACE"
    driver.expression = flash_expression(wave, rise, fall, amount, strike)
    return node
