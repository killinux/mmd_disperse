"""Speed lines (集中線) for the impact frames: a sheet just in front of the camera, parented to it, on which lines of
light rush in from the edges of the picture towards the character, new ones every other frame, while the impact frames
run and a few frames after.

The sheet reads from its object (custom properties, through Attribute nodes of type Object): where the character is on
the picture and the picture's shape (`mmdd_focus`, set when the effect syncs), and two values driven every frame,
how strongly the lines show (`mmdd_lines`, on the frame like the compositor's impact frames) and the frame
(`mmdd_tick`). The compositor inverts every other impact frame, which turns the white lines black on those.
"""

import bpy
from bpy_extras.object_utils import world_to_camera_view

NAME = "MMD Disperse Speed Lines"
MATERIAL = "MMD Disperse Speed Lines"
P_LINES = "mmd_disperse_speed_lines"  # on the sheet: the mask of its effect
FOCUS = "mmdd_focus"  # x, y of the character on the picture (-1 .. 1), the picture's width over its height
SHOWN = "mmdd_lines"  # 0 .. 1, driven on the frame
TICK = "mmdd_tick"  # the frame, driven
LINGER = 4  # frames the lines stay after the impact frames, fading


def sheets(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_LINES) == mask]


def _material():
    mat = bpy.data.materials.get(MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MATERIAL)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    def node(idname, x, y, **props):
        n = nt.nodes.new(idname)
        n.location = (x, y)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def math(op, a, b=None, x=0, y=0, clamp=False):
        n = node("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        for sock, value in ((n.inputs[0], a), (n.inputs[1], b)):
            if isinstance(value, bpy.types.NodeSocket):
                nt.links.new(value, sock)
            elif value is not None:
                sock.default_value = value
        return n.outputs[0]

    out = node("ShaderNodeOutputMaterial", 1600, 0)
    uv = node("ShaderNodeTexCoord", -1600, 0).outputs["UV"]
    focus = node("ShaderNodeAttribute", -1600, -300, attribute_type="OBJECT", attribute_name=FOCUS)
    shown = node("ShaderNodeAttribute", -1600, -500, attribute_type="OBJECT", attribute_name=SHOWN).outputs[2]
    tick = node("ShaderNodeAttribute", -1600, -700, attribute_type="OBJECT", attribute_name=TICK).outputs[2]
    sep = node("ShaderNodeSeparateXYZ", -1400, 0)
    nt.links.new(uv, sep.inputs[0])
    fsep = node("ShaderNodeSeparateXYZ", -1400, -300)
    nt.links.new(focus.outputs["Vector"], fsep.inputs[0])
    # from the character on the picture, the picture's own proportions
    sx = math("SUBTRACT", math("MULTIPLY", sep.outputs[0], 2.0, x=-1200, y=100), 1.0, x=-1100, y=100)
    px = math("MULTIPLY", math("SUBTRACT", sx, fsep.outputs[0], x=-1000, y=100), fsep.outputs[2], x=-900, y=100)
    py = math("SUBTRACT", math("SUBTRACT", math("MULTIPLY", sep.outputs[1], 2.0, x=-1200, y=-50), 1.0, x=-1100, y=-50),
              fsep.outputs[1], x=-1000, y=-50)
    angle = math("ARCTAN2", py, px, x=-800, y=50)
    reach = math("SQRT", math("ADD", math("MULTIPLY", px, px, x=-900, y=-200), math("MULTIPLY", py, py, x=-900, y=-350),
                              x=-800, y=-250), x=-700, y=-250)
    lane = math("MULTIPLY", math("ADD", math("DIVIDE", angle, 6.2832, x=-600, y=50), 0.5, x=-500, y=50), 160.0, x=-400,
                y=50)
    which = math("FLOOR", lane, x=-300, y=50)
    across = math("ABSOLUTE", math("SUBTRACT", math("FRACT", lane, x=-300, y=-100), 0.5, x=-200, y=-100), x=-100,
                  y=-100)
    when = math("FLOOR", math("MULTIPLY", tick, 0.5, x=-400, y=-600), x=-300, y=-600)
    dice = []
    for i in range(3):
        at = node("ShaderNodeCombineXYZ", -200, -400 - 150 * i)
        nt.links.new(which, at.inputs[0])
        nt.links.new(when, at.inputs[1])
        at.inputs[2].default_value = 0.37 * (i + 1)
        noise = node("ShaderNodeTexWhiteNoise", 0, -400 - 150 * i, noise_dimensions="3D")
        nt.links.new(at.outputs[0], noise.inputs["Vector"])
        dice.append(noise.outputs[0])
    lit = math("GREATER_THAN", dice[0], 0.5, x=200, y=-400)
    inner = math("ADD", 0.5, math("MULTIPLY", dice[2], 0.45, x=200, y=-700), x=300, y=-700)
    grow = math("DIVIDE", math("SUBTRACT", reach, inner, x=400, y=-300), 0.6, x=500, y=-300, clamp=True)
    width = math("MULTIPLY", math("ADD", 0.15, math("MULTIPLY", dice[1], 0.6, x=400, y=-550), x=500, y=-550),
                 math("MULTIPLY", grow, 0.5, x=600, y=-400), x=700, y=-500)
    line = math("LESS_THAN", across, width, x=800, y=-200)
    fade_in = math("DIVIDE", math("SUBTRACT", reach, inner, x=600, y=-100), 0.15, x=700, y=-100, clamp=True)
    alpha = math("MULTIPLY", math("MULTIPLY", math("MULTIPLY", lit, line, x=900, y=-300), fade_in, x=1000, y=-200),
                 shown, x=1100, y=-300, clamp=True)
    glow = node("ShaderNodeEmission", 1100, 100)
    glow.inputs["Strength"].default_value = 2.5
    clear = node("ShaderNodeBsdfTransparent", 1100, 250)
    mix = node("ShaderNodeMixShader", 1350, 100)
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(clear.outputs[0], mix.inputs[1])
    nt.links.new(glow.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True
    if bpy.app.version < (4, 2, 0):
        mat.shadow_method = "NONE"
    return mat


def create(scene, mask, collection):
    """The sheet of the effect of `mask`, just in front of the scene camera (None without a camera)."""
    camera = scene.camera
    if camera is None or camera.type != "CAMERA":
        return None
    data = camera.data
    corners = [c.copy() for c in data.view_frame(scene=scene)]
    near = max(data.clip_start * 3.0, 1e-3)
    for c in corners:
        if data.type != "ORTHO":  # the frame at that distance (a little larger, so its edges are out of the picture)
            c *= near / max(abs(c.z), 1e-9)
        c.x *= 1.05
        c.y *= 1.05
        c.z = -near
    me = bpy.data.meshes.new(NAME)
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    xs, ys = [c.x for c in corners], [c.y for c in corners]
    for loop in me.loops:
        c = corners[loop.vertex_index]
        uv.data[loop.index].uv = ((c.x - min(xs)) / max(max(xs) - min(xs), 1e-9),
                                  (c.y - min(ys)) / max(max(ys) - min(ys), 1e-9))
    me.materials.append(_material())
    ob = bpy.data.objects.new(NAME, me)
    collection.objects.link(ob)
    ob.parent = camera
    ob.hide_select = True
    if hasattr(ob, "visible_shadow"):
        ob.visible_shadow = False
    ob[P_LINES] = mask
    ob[FOCUS] = (0.0, 0.0, 1.0)
    ob[SHOWN] = 0.0
    ob[TICK] = 0.0
    return ob


def sync(scene, mask, focus, first, frames):
    """Aim the sheet at `focus` (a world point: the character) and drive it on for the `frames` impact frames from
    frame `first`, fading over LINGER more."""
    camera = scene.camera
    for ob in sheets(mask):
        if camera is not None and focus is not None:
            seen = world_to_camera_view(scene, camera, focus)
            render = scene.render
            aspect = (render.resolution_x * render.pixel_aspect_x) / max(render.resolution_y * render.pixel_aspect_y,
                                                                         1e-9)
            ob[FOCUS] = (2.0 * seen.x - 1.0, 2.0 * seen.y - 1.0, aspect)
        last = int(first) + int(frames) + LINGER  # (gone on this frame)
        for prop, expression in ((SHOWN, "clamp(({e} - frame) / {l}, 0, 1) * (frame >= {f})".format(
                                     e=last, l=LINGER + 1, f=int(first))),
                                 (TICK, "frame")):
            ob.driver_remove('["%s"]' % prop)
            driver = ob.driver_add('["%s"]' % prop).driver
            driver.type = "SCRIPTED"
            driver.expression = expression
        ob.update_tag()


def remove(mask):
    for ob in sheets(mask):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    mat = bpy.data.materials.get(MATERIAL)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)
