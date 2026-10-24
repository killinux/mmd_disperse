"""The shadow play (皮影, 1.16): the lights go down and a glowing screen stands behind her; she is pressed flat onto it
as a shadow-play figure, her colours turned to translucent dyed leather with flowers cut out of it (the screen's light
comes through), two thin rods on her hands, dancing on twos (Time: On Twos); the outfits swap in that state, then the
screen rises away and she steps out of it, round again. 朱铁雄's 皮影 transformation (2026-07); 「哈基米也会玩皮影戏」.

Our objects: the plane she is pressed onto (an empty: its Y axis looks the way the camera does when she goes flat),
the screen behind it (a mesh of ours), the rods (cover_nodes' rods group, from her wrists down out of the picture);
on every mesh of both outfits a modifier of ours at the end of the stack (cover_nodes' flatten group) presses her
onto the plane as much as its Flat input says (a driver on the frame). The leather is spliced into their materials
(materials.add_leather), timed by the same driver.
"""

import math

import bpy
from mathutils import Matrix, Vector

from . import materials

P_SHADOW = "mmd_disperse_shadowplay"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_shadowplay_kind"  # ... PLANE, SCREEN, RODS, HOOK_L, HOOK_R
P_FLAT = "mmd_disperse_shadowplay_flat"  # on an outfit's mesh: the mask whose flatten modifier it carries
MOD = "MMD Disperse Shadow Play"
NAME = "MMD Disperse Shadow Play"
PRESS = 0.35  # seconds she takes to be pressed flat ...
AFTER = (0.35, 0.8)  # ... after the big moment she steps out of the screen between these times
BEHIND = 0.22  # the screen stands this far behind her (model heights) ...
SCREEN = (1.05, 1.35)  # ... this wide and tall (model heights)
PAINTING = (0.7, 1.12)  # the painting's canvas (model heights: in a tall picture its gilded frame shows all round)


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_SHADOW) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _materials(meshes):
    seen = []
    for ob in meshes:
        for slot in ob.material_slots:
            if slot.material is not None and slot.material.node_tree is not None and slot.material not in seen:
                seen.append(slot.material)
    return seen


def _unflatten(mask, keep=()):
    for ob in [o for o in bpy.data.objects if o.get(P_FLAT) == mask and o not in keep]:
        mod = ob.modifiers.get(MOD)
        if mod is not None:
            ob.modifiers.remove(mod)
        del ob[P_FLAT]


def remove(mask, meshes=()):
    _unflatten(mask)
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    for mat in [m for m in bpy.data.materials if m.get(materials.P_LEATHER) or m.get(materials.P_OIL)]:
        if not meshes or mat in _materials(meshes):
            materials.remove_leather(mat)
            materials.remove_oil(mat)
    if not any(ob.get(P_SHADOW) is not None or ob.get(P_FLAT) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_shadow_assets()
        for kind in ("SCREEN", "ROD"):
            mat = bpy.data.materials.get(materials._cover_name(kind))
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def flat_expression(first, moment, fps):
    """0 .. 1: how flat she is at the frame (simple math only): pressed over PRESS before `first`, out again after the
    moment."""
    return "smoothstep({a}, {b}, frame) * (1 - smoothstep({c}, {d}, frame))".format(
        a=float(first - PRESS * fps), b=float(first), c=float(moment + AFTER[0] * fps), d=float(moment + AFTER[1] * fps))


def screen_mesh(name):
    """The screen: a unit square in X/Z (its front at -Y), a thin dark border round it (mmdd_frame 1 on the border)
    and a UV across it."""
    import bmesh

    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    border = 0.03
    frame_vals = []

    def quad(x0, z0, x1, z1, is_frame, y=0.0):
        vs = [bm.verts.new((x, y, z)) for x, z in ((x0, z0), (x1, z0), (x1, z1), (x0, z1))]
        f = bm.faces.new(vs)
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.x + 0.5, loop.vert.co.z + 0.5)
        frame_vals.append(is_frame)

    quad(-0.5, -0.5, 0.5, 0.5, False)
    for x0, z0, x1, z1 in ((-0.5 - border, -0.5 - border, 0.5 + border, -0.5), (-0.5 - border, 0.5, 0.5 + border,
                                                                                 0.5 + border),
                           (-0.5 - border, -0.5, -0.5, 0.5), (0.5, -0.5, 0.5 + border, 0.5)):
        quad(x0, z0, x1, z1, True, y=-0.002)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    attr = me.attributes.new("mmdd_frame", "FLOAT", "FACE")
    attr.data.foreach_set("value", [1.0 if v else 0.0 for v in frame_vals])
    me.update()
    return me


def sync(settings, mask, models, start, moment):
    """The shadow play as the panel says: she is pressed flat Shadow Time before the big moment (frame `moment`), or
    at the start of the transformation (frame `start`) when that is later, and steps out after it; all of it taken
    away when it is off."""
    from . import cover_nodes, motion, sampling
    from .cover import _clear_keys, _key, _shown
    from .model import rest_bounds
    from .node_groups import input_identifiers

    if mask is None:
        return
    meshes = [ob for m in models for ob in m.meshes] if models else []
    arm = next((m.armature for m in models if m.armature is not None), None) if models else None
    if not getattr(settings, "shadow_enable", False) or moment is None or not meshes:
        remove(mask, meshes)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    height = max(settings.size_reference, 1e-3)
    first = max(float(moment) - settings.shadow_length * fps, float(start) if start is not None else -1e9)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    lo, hi = rest_bounds(meshes)
    centre = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), 0.5 * (lo.z + hi.z)))
    camera = sampling.camera_at(scene, first)
    look = Vector((0.0, 1.0, 0.0))
    if camera is not None:
        away = centre - sampling.matrix_at(camera, first).translation
        away.z = 0.0
        if away.length > 1e-6:
            look = away.normalized()
    side = look.cross(Vector((0.0, 0.0, 1.0)))
    turn = Matrix((side, look, Vector((0.0, 0.0, 1.0)))).transposed().to_quaternion()
    # the plane she is pressed onto: through her middle, facing the camera (its Y axis away from it)
    plane = next(iter(objects(mask, "PLANE")), None)
    if plane is None:
        plane = bpy.data.objects.new(NAME + " Plane", None)
        plane.empty_display_type, plane.empty_display_size = "ARROWS", 0.1 * height
        plane.hide_render = plane.hide_select = True
        collection.objects.link(plane)
        plane[P_SHADOW], plane[P_KIND] = mask, "PLANE"
    plane.rotation_mode = "QUATERNION"
    plane.rotation_quaternion = turn
    plane.location = centre
    flat = flat_expression(first, moment, fps)
    group = cover_nodes.ensure_flatten_group()
    ids = input_identifiers(group)
    for ob in meshes:
        mod = ob.modifiers.get(MOD)
        if mod is None:
            mod = ob.modifiers.new(MOD, "NODES")
        if mod.node_group != group:
            mod.node_group = group
        ob[P_FLAT] = mask
        mod[ids["Plane"]] = plane
        mod[ids["Keep"]] = 0.004
        path = '["%s"]' % ids["Flat"]
        mod.driver_remove(path)
        driver = mod.driver_add(path).driver
        driver.type = "SCRIPTED"
        driver.expression = flat
        here = ob.modifiers.find(mod.name)
        if here != len(ob.modifiers) - 1:  # (last: after the armature and the transformation)
            ob.modifiers.move(here, len(ob.modifiers) - 1)
    _unflatten(mask, keep=meshes)
    painting = settings.shadow_style == "PAINTING"
    for mat in _materials(meshes):
        if painting:
            materials.remove_leather(mat)
            materials.add_oil(mat)
            materials.update_oil(mat, flat, 1.0 / height)
        else:
            materials.remove_oil(mat)
            materials.add_leather(mat)
            materials.update_leather(mat, flat, 14.0 / height)  # (small flowers, as cut into leather)
    for mat in [m for m in bpy.data.materials if (m.get(materials.P_LEATHER) or m.get(materials.P_OIL))
                and m not in _materials(meshes)]:
        materials.remove_leather(mat)
        materials.remove_oil(mat)
    for kind in (("SCREEN", "HOOK_L", "HOOK_R", "RODS") if painting else ("CANVAS", "FRAME")):
        for ob in objects(mask, kind):
            data = ob.data
            bpy.data.objects.remove(ob)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
    if painting:
        _painting(settings, mask, collection, turn, look, centre, lo, height, first, moment, fps)
        return
    # the screen behind her, rising away once she has stepped out
    screen = next(iter(objects(mask, "SCREEN")), None)
    if screen is None:
        screen = bpy.data.objects.new(NAME + " Screen", screen_mesh(NAME + " Screen"))
        collection.objects.link(screen)
        screen[P_SHADOW], screen[P_KIND] = mask, "SCREEN"
        screen.hide_select = True
        screen.data.materials.append(materials.ensure_cover_material("SCREEN"))
        if hasattr(screen, "visible_shadow"):
            screen.visible_shadow = False
    _clear_keys(screen)
    screen.rotation_mode = "QUATERNION"
    screen.rotation_quaternion = turn
    screen.scale = (SCREEN[0] * height, 1.0, SCREEN[1] * height)
    screen["mmdd_color"] = tuple(settings.shadow_color)
    stand = Vector((centre.x, centre.y, lo.z + 0.5 * SCREEN[1] * height)) + look * (BEHIND * height)
    up = stand + Vector((0.0, 0.0, 1.6 * height))
    rise0, rise1 = moment + AFTER[0] * fps, moment + (AFTER[1] + 0.4) * fps
    _key(screen, "location", ((first - PRESS * fps - 1.0, up), (first - PRESS * fps, up), (first, stand),
                              (rise0, stand), (rise1, up)), interpolation="BEZIER")
    _shown(screen, int(math.floor(first - PRESS * fps)), int(math.ceil(rise1)) + 1)
    # the rods: from her wrists down out of the picture, while she is flat
    hooks = []
    for k, side_name in enumerate(motion.SIDES):
        kind = "HOOK_" + side_name
        ob = next(iter(objects(mask, kind)), None)
        if ob is None:
            ob = bpy.data.objects.new("%s Hook %s" % (NAME, side_name), None)
            ob.empty_display_type, ob.empty_display_size = "PLAIN_AXES", 0.02 * height
            ob.hide_render = ob.hide_select = True
            collection.objects.link(ob)
            ob[P_SHADOW], ob[P_KIND] = mask, kind
        for c in list(ob.constraints):
            ob.constraints.remove(c)
        wrist = motion._hand(arm, side_name)[0] if arm is not None else None
        if wrist is not None:
            con = ob.constraints.new("COPY_LOCATION")
            con.target, con.subtarget = arm, wrist.name
        hooks.append(ob)
    rods = next(iter(objects(mask, "RODS")), None)
    if rods is None:
        rods = bpy.data.objects.new(NAME + " Rods", bpy.data.meshes.new(NAME + " Rods"))
        collection.objects.link(rods)
        rods[P_SHADOW], rods[P_KIND] = mask, "RODS"
        rods.hide_select = True
    rods_group = cover_nodes.ensure_rods_group()
    mod = next((m for m in rods.modifiers if m.type == "NODES"), None) or rods.modifiers.new(NAME, "NODES")
    if mod.node_group != rods_group:
        mod.node_group = rods_group
    rid = input_identifiers(rods_group)
    for name, value in (("Plane", plane), ("Hook L", hooks[0]), ("Hook R", hooks[1]), ("Floor", lo.z - 0.6 * height),
                        ("Spread", 0.35 * height), ("Radius", 0.004 * height),
                        ("Material", materials.ensure_cover_material("ROD"))):
        if name in rid:
            mod[rid[name]] = value
    path = '["%s"]' % rid["Flat"]
    mod.driver_remove(path)
    driver = mod.driver_add(path).driver
    driver.type = "SCRIPTED"
    driver.expression = flat
    rods.update_tag()


def _painting(settings, mask, collection, turn, look, centre, lo, height, first, moment, fps):
    """Into the painting: the canvas just behind her plane and a gilded frame round it, rising away once she has
    stepped out."""
    from .cover import _clear_keys, _frame_mesh, _key, _shown

    wide, tall, moulding = PAINTING[0] * height, PAINTING[1] * height, 0.07 * height
    canvas = next(iter(objects(mask, "CANVAS")), None)
    if canvas is None:
        canvas = bpy.data.objects.new(NAME + " Canvas", screen_mesh(NAME + " Canvas"))
        collection.objects.link(canvas)
        canvas[P_SHADOW], canvas[P_KIND] = mask, "CANVAS"
        canvas.hide_select = True
        canvas.data.materials.append(materials.ensure_cover_material("OIL_CANVAS"))
        canvas.data.materials.append(materials.ensure_cover_material("FRAME"))
    key = "frame:%.4f:%.4f:%.4f" % (wide, tall, moulding)
    frame = next(iter(objects(mask, "FRAME")), None)
    if frame is not None and frame.get("mmdd_key") != key:
        data = frame.data
        bpy.data.objects.remove(frame)
        bpy.data.meshes.remove(data)
        frame = None
    if frame is None:
        frame = bpy.data.objects.new(NAME + " Frame", _frame_mesh(wide, tall, moulding))
        collection.objects.link(frame)
        frame[P_SHADOW], frame[P_KIND], frame["mmdd_key"] = mask, "FRAME", key
        frame.hide_select = True
        frame.data.materials.append(materials.ensure_cover_material("FRAME"))
    side = turn.to_matrix().col[0]
    up_axis = Vector((0.0, 0.0, 1.0))
    facing = Matrix((side, up_axis, -look)).transposed().to_quaternion()  # (the frame's +Z at the camera)
    stand = Vector((centre.x, centre.y, lo.z + 0.5 * tall + 0.02 * height)) + look * (0.06 * height)
    above = stand + Vector((0.0, 0.0, 1.6 * height))
    rise0, rise1 = moment + AFTER[0] * fps, moment + (AFTER[1] + 0.4) * fps
    for ob, rotation, scale in ((canvas, turn, (wide, 1.0, tall)), (frame, facing, (1.0, 1.0, 1.0))):
        _clear_keys(ob)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = rotation
        ob.scale = scale
        _key(ob, "location", ((first - PRESS * fps - 1.0, above), (first - PRESS * fps, above), (first, stand),
                              (rise0, stand), (rise1, above)), interpolation="BEZIER")
        _shown(ob, int(math.floor(first - PRESS * fps)), int(math.ceil(rise1)) + 1)
