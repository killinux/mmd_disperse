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


CAMERA_BLUR = "MMD Disperse Camera Blur"


def add_camera_blur(scene):
    """Directional Blur before the output for the camera moves (shots.py): smeared sideways in a whip pan, round the
    middle in a roll, outwards in a zoom punch; update_camera_blur() drives it."""
    def setup(node):
        if hasattr(node, "iterations"):  # options are properties before Blender 5.0 ...
            node.iterations = 16
        else:  # ... and sockets afterwards
            _set_socket(node, "Samples", 16)

    return _insert_before_output(scene, CAMERA_BLUR, "CompositorNodeDBlur", setup)


def _blur_target(node, kind):
    """(owner, data path, offset) driving `kind` of the camera blur: shift (sideways, a share of the picture), turn
    (radians round the centre) or zoom (a share outwards); Blender 5.0+ takes a scale (1 = none) for the zoom."""
    if hasattr(node, "distance"):
        return {"shift": (node, "distance", 0.0), "turn": (node, "spin", 0.0), "zoom": (node, "zoom", 0.0)}[kind]
    name = {"shift": "Amount", "turn": "Rotation", "zoom": "Scale"}[kind]
    return node.inputs[name], "default_value", 1.0 if kind == "zoom" else 0.0


def update_camera_blur(scene, expressions, center=(0.5, 0.5)):
    """Drive the camera blur (when the scene has it) with driver expressions on the frame: {"shift" | "turn" | "zoom":
    expression}; what is missing is off. `center` (0 .. 1 across the picture) is where the turn and the zoom go round."""
    tree = _existing_tree(scene)
    node = tree.nodes.get(CAMERA_BLUR) if tree is not None else None
    if node is None:
        return None
    for kind in ("shift", "turn", "zoom"):
        owner, path, offset = _blur_target(node, kind)
        owner.driver_remove(path)
        expression = expressions.get(kind)
        if not expression:
            setattr(owner, path, offset)
            continue
        driver = owner.driver_add(path).driver
        driver.type = "SCRIPTED"
        driver.expression = ("1 + " if offset else "") + expression
    if hasattr(node, "center_x"):
        node.center_x, node.center_y = center
    else:
        sock = node.inputs.get("Center")
        if sock is not None:
            sock.default_value = tuple(center) + (0.0,) * (len(sock.default_value) - 2)
    return node


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


LOOK = "MMD Disperse Look"  # the Mix node that blends the look in; the look's other nodes are named LOOK + " ..."
LOOK_STYLES = ("NONE", "SILHOUETTE", "ACCENT", "SONG")
P_LOOK = "mmd_disperse_look"  # on the Mix node: what its nodes were made for
INK = (0.07, 0.05, 0.04, 1.0)
PAPER = (0.86, 0.76, 0.56, 1.0)  # the old painting's silk, yellowed ...
MARGIN = (0.93, 0.88, 0.74, 1.0)  # ... and its mounting
SEAL = (0.72, 0.06, 0.03, 1.0)


class _Look:
    """Builds the nodes of a look, each named after LOOK and placed in a column."""

    def __init__(self, tree, x, y):
        self.tree, self.x, self.y, self.count = tree, x, y, 0

    def node(self, idname):
        self.count += 1
        n = self.tree.nodes.new(idname)
        n.name = n.label = "%s %d" % (LOOK, self.count)
        n.location = (self.x - 200 * (self.count % 6), self.y - 220 * (self.count // 6))
        return n

    def feed(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.tree.links.new(value, socket)
        elif value is not None:
            socket.default_value = value

    def mix(self, blend, fac, a, b):
        if hasattr(bpy.types, "CompositorNodeMixRGB"):
            n = self.node("CompositorNodeMixRGB")
            n.use_clamp = True
            sockets = n.inputs[0], n.inputs[1], n.inputs[2], n.outputs[0]
        else:  # Blender 5.0+
            n = self.node("ShaderNodeMix")
            n.data_type = "RGBA"
            n.clamp_result = True
            sockets = (next(s for s in n.inputs if s.identifier == "Factor_Float"),
                       next(s for s in n.inputs if s.identifier == "A_Color"),
                       next(s for s in n.inputs if s.identifier == "B_Color"),
                       next(s for s in n.outputs if s.identifier == "Result_Color"))
        n.blend_type = blend
        for sock, value in zip(sockets[:3], (fac, a, b)):
            self.feed(sock, value)
        return sockets[3]

    def grey(self, image):
        n = self.node("CompositorNodeRGBToBW")
        self.feed(n.inputs[0], image)
        return n.outputs[0]

    def edges(self, image):
        """How strongly the picture changes there (a Sobel filter), as a grey value."""
        n = self.node("CompositorNodeFilter")
        if hasattr(n, "filter_type"):
            n.filter_type = "SOBEL"
        else:  # Blender 5.0+: a menu socket
            _set_socket(n, "Type", "Sobel")
        self.feed(n.inputs["Image"], image)
        return self.grey(n.outputs["Image"])

    def box(self, x, y, width, height):
        """1 inside a rectangle centred at (x, y), 0 outside; both sizes a share of the picture's width (as Blender's
        Box Mask has them)."""
        n = self.node("CompositorNodeBoxMask")
        if hasattr(n, "mask_width"):  # Blender 4.x (its own width and height are the node's)
            n.mask_type = "ADD"
            n.x, n.y, n.mask_width, n.mask_height = x, y, width, height
        elif hasattr(n, "mask_type"):  # Blender 3.x: its width and height hide the node's
            n.mask_type = "ADD"
            n.x, n.y, n.width, n.height = x, y, width, height
        else:  # Blender 5.0+: sockets
            _set_socket(n, "Operation", "Add")
            n.inputs["Position"].default_value = (x, y)
            n.inputs["Size"].default_value = (width, height)
        n.inputs["Value"].default_value = 1.0
        return n.outputs["Mask"]

    def dilated(self, matte, step):
        """`matte` grown by `step` pixels (shrunk when it is negative)."""
        n = self.node("CompositorNodeDilateErode")
        if hasattr(n, "mode"):
            n.mode = "STEP"
            n.distance = step
        else:  # Blender 5.0+: sockets
            _set_socket(n, "Type", "Steps")
            n.inputs["Size"].default_value = step
        self.feed(n.inputs["Mask"], matte)
        return n.outputs["Mask"]

    def closed(self, matte, pixels):
        """`matte` with the holes up to about `pixels` across filled (grown, then shrunk back)."""
        return self.dilated(self.dilated(matte, pixels), -pixels)

    def matte(self, scene, objects):
        """The coverage of `objects` in the picture (Cryptomatte, turned on for the view layer)."""
        layer = next((vl for vl in scene.view_layers if vl.use), scene.view_layers[0])
        layer.use_pass_cryptomatte_object = True
        n = self.node("CompositorNodeCryptomatteV2")
        n.source = "RENDER"
        n.scene = scene
        try:
            n.layer_name = layer.name + ".CryptoObject"
        except TypeError:
            pass
        n.matte_id = ",".join(ob.name for ob in objects)
        # (see-through parts can add up to more than full coverage in EEVEE Next: kept to 0 .. 1)
        return self.mix("MIX", 1.0, (0.0, 0.0, 0.0, 1.0), n.outputs["Matte"])


def _look_nodes(tree):
    return [n for n in tree.nodes if n.name.startswith(LOOK)]


def remove_look(scene):
    """Take the look out of the compositor, joining up what it was spliced between."""
    tree = _existing_tree(scene)
    node = tree.nodes.get(LOOK) if tree is not None else None
    if node is None:
        return
    image_in, image_out = _sockets(node)
    source = image_in.links[0].from_socket if image_in.links else None
    targets = [link.to_socket for link in image_out.links]
    for n in _look_nodes(tree):
        tree.nodes.remove(n)
    if source is not None:
        for target in targets:
            tree.links.new(source, target)


def look_expression(first, last):
    """Driver expression on the frame: the look is on from frame `first` up to `last` (a cut in and a cut out)."""
    return "(frame >= {f}) * (frame < {l})".format(f=int(first), l=int(last))


def update_look(scene, style, first, last, dancer=(), color=(1.0, 0.08, 0.03)):
    """Splice the look `style` into the compositor (or take it out with NONE), on from frame `first` to `last`:
    SILHOUETTE the `dancer` objects black with a white rim on a flat `color`; ACCENT the picture black and white but
    for the `dancer` objects; SONG an old Chinese painting: the `dancer` objects painted in ink on yellowed silk, ink
    lines round them, a mounting and a red seal."""
    if style == "NONE" or first is None:
        remove_look(scene)
        return None
    render = scene.render
    key = "%s:%s:%s:%dx%d" % (style, ",".join(sorted(ob.name for ob in dancer)), ",".join("%.3f" % c for c in color),
                              render.resolution_x, render.resolution_y)
    tree = _existing_tree(scene)
    node = tree.nodes.get(LOOK) if tree is not None else None
    if node is not None and node.get(P_LOOK) != key:
        remove_look(scene)
        node = None
    if node is None:
        idname = "CompositorNodeMixRGB" if hasattr(bpy.types, "CompositorNodeMixRGB") else "ShaderNodeMix"

        def setup(n):
            if n.bl_idname == "ShaderNodeMix":
                n.data_type = "RGBA"
            n.blend_type = "MIX"
            _flash_factor(n).default_value = 0.0

        node = _insert_before_output(scene, LOOK, idname, setup)
        node[P_LOOK] = key
        tree = node.id_data
        image_in = _sockets(node)[0]
        source = image_in.links[0].from_socket
        b = _Look(tree, node.location.x - 300, node.location.y - 300)
        if style == "SILHOUETTE":
            matte = b.closed(b.matte(scene, dancer), max(2, int(round(0.004 * scene.render.resolution_x))))
            shape = b.mix("MIX", matte, tuple(color) + (1.0,), (0.0, 0.0, 0.0, 1.0))
            look = b.mix("ADD", b.edges(matte), shape, (1.0, 0.95, 0.85, 1.0))
        elif style == "ACCENT":
            look = b.mix("MIX", b.matte(scene, dancer), b.grey(source), source)
        else:  # SONG: the dancer painted in ink on blank silk, ink lines round her
            pixels = max(2, int(round(0.004 * scene.render.resolution_x)))
            matte = b.closed(b.matte(scene, dancer), pixels)
            value = b.grey(source)
            light = b.mix("SCREEN", 1.0, value, value)
            light = b.mix("SCREEN", 1.0, light, light)  # (1 - (1 - v)^4: skin near the silk, dark cloth in ink)
            figure = b.mix("MIX", light, INK, PAPER)
            ground = b.mix("MIX", 0.12, PAPER, b.mix("MULTIPLY", 1.0, PAPER, value))  # the scene a faint shadow
            aged = b.mix("MIX", matte, ground, figure)
            lines = b.mix("MULTIPLY", 1.0, b.edges(source), b.dilated(matte, 3 * pixels))
            inked = b.mix("MIX", lines, aged, INK)
            render = scene.render
            tall = render.resolution_y / max(render.resolution_x, 1)  # the picture's height in widths
            mounted = b.mix("MIX", b.box(0.5, 0.5, 0.88, 0.88 * tall + 0.02), MARGIN, inked)
            seal = min(0.06, 0.06 * tall)
            look = b.mix("MIX", b.box(0.94 - seal, 0.1, seal, seal), mounted, SEAL)
        tree.links.new(look, next(s for s in node.inputs if s.identifier in ("B_Color", "Image_001")))
    socket = _flash_factor(node)
    socket.driver_remove("default_value")
    driver = socket.driver_add("default_value").driver
    driver.type = "SCRIPTED"
    driver.expression = look_expression(first, last)
    return node
