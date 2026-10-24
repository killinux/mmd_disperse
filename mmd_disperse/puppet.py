"""The marionette (人偶, 1.16): a wooden control bar comes down above her head and five threads of light hook her head,
wrists and knees; she hangs on them (with Float Up she is lifted, with Time: On Twos she dances like stop motion till
the moment) and the old outfit turns to white porcelain; on the beats before the big moment the strings snap one by one,
the last as the outfits swap in a white flash, and she lands (with Impact: a shockwave). The doll on strings of the
Nikki games (「提线格莱斯」, 「Hop Doll」) and Lady Gaga's "The Dead Dance".

Our objects: the control bar (a mesh of ours, a unit across and scaled to her: it follows her head across, comes down
from above the picture, sways and flies away), an empty on each hooked bone (COPY_LOCATION) and the strings
(cover_nodes' strings group: a thread from each of the bar's ends to its empty, dropping down when they appear and
whipping up to the bar when they snap). The porcelain is spliced into the old outfit's materials
(materials.add_porcelain) and timed by a driver: the locked ones (her head and hair) turn back at the moment.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import beats, materials

P_PUPPET = "mmd_disperse_puppet"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_puppet_kind"  # ... BAR, STRINGS, HOOK_0..4
NAME = "MMD Disperse Marionette"
STRINGS = 5  # the head, the wrists, the knees (left on her left: at +X of the bar, which faces the camera)
ATTACH = ((0.0, 0.0, 0.0), (0.3, 0.08, 0.0), (-0.3, 0.08, 0.0), (0.15, -0.12, 0.0), (-0.15, -0.12, 0.0))
SNAP_ORDER = (1, 2, 3, 4, 0)  # the wrists snap first, then the knees, the head last (at the moment)
DOWN = 0.6  # seconds the bar takes to come down ...
HANG = 1.2  # ... it is there this long before the first string snaps ...
DROP = 0.35  # ... the strings drop down to her in this long, just after it got there
WHIP = 0.22  # a snapped string whips up to the bar in this long
AWAY = (0.15, 0.6)  # after the moment the bar flies up between these times
ABOVE = 0.3  # the bar hangs this far above the top of her head (model heights) ...
BAR = 0.55  # ... and is this wide
GAP = 0.5  # seconds between the snaps without beats


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_PUPPET) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)


def _materials(meshes):
    seen = []
    for ob in meshes:
        for slot in ob.material_slots:
            if slot.material is not None and slot.material.node_tree is not None and slot.material not in seen:
                seen.append(slot.material)
    return seen


def remove(mask, meshes=()):
    for ob in objects(mask):
        _delete(ob)
    for mat in [m for m in bpy.data.materials if m.get(materials.P_PORCELAIN)]:
        if not meshes or mat in _materials(meshes):
            materials.remove_porcelain(mat)
    if not any(ob.get(P_PUPPET) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_puppet_assets()
        for kind in ("PUPPET_BAR", "PUPPET_STRING"):
            mat = bpy.data.materials.get(materials._cover_name(kind))
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def bar_mesh(name):
    """The control bar, a unit across (X), its middle at the origin: a spine front to back joining a bar for the
    hands (behind) and one for the knees (in front), with gold caps where the strings hang (mmdd_gold 1)."""
    bm = bmesh.new()
    gold = []

    def box(centre, size, is_gold=False):
        geom = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(centre) @ Matrix.Diagonal(
            (size[0], size[1], size[2], 1.0)))
        gold.extend([is_gold] * len(geom["verts"]))

    box(Vector((0.0, 0.0, 0.0)), (0.035, 0.32, 0.03))
    box(Vector((0.0, 0.08, 0.0)), (0.62, 0.035, 0.03))
    box(Vector((0.0, -0.12, 0.0)), (0.32, 0.035, 0.03))
    for x, y, _z in ATTACH:
        geom = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.024,
                                         matrix=Matrix.Translation(Vector((x, y, -0.012))))
        gold.extend([True] * len(geom["verts"]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    attr = me.attributes.new("mmdd_gold", "FLOAT", "POINT")
    attr.data.foreach_set("value", [1.0 if g else 0.0 for g in gold])
    me.update()
    return me


def snaps(moment, beat_list, fps):
    """The frames the strings snap at, the last at `moment`: the beats before it (with beats), else GAP apart."""
    from .lights import flash_frames

    out = flash_frames(float(moment), STRINGS, beat_list, fps)
    if beat_list and out[-1] - out[0] > STRINGS * 0.8 * fps:  # (slow music: not on every beat, GAP apart)
        out = [float(moment) - (STRINGS - 1 - k) * GAP * fps for k in range(STRINGS)]
    return out


def sync(settings, mask, models, moment):
    """The marionette as the panel says, its strings snapping up to the big moment at frame `moment`; all of it taken
    away when it is off."""
    from . import cover_nodes, dimension, motion
    from .arrival import KNEE_BONES
    from .model import rest_bounds

    if mask is None:
        return
    meshes = [ob for m in models for ob in m.meshes] if models else []
    arm = next((m.armature for m in models if m.armature is not None), None) if models else None
    if not getattr(settings, "puppet_enable", False) or moment is None or not meshes or arm is None:
        remove(mask, meshes)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    height = max(settings.size_reference, 1e-3)
    lo, hi = rest_bounds(meshes)
    beat_list = beats.beat_frames() if settings.beat_sync else []
    at = snaps(moment, beat_list, fps)
    order = sorted(range(STRINGS), key=lambda k: SNAP_ORDER.index(k))
    snap_of = {k: at[i] for i, k in enumerate(order)}
    arrive = at[0] - HANG * fps
    start = arrive - DOWN * fps
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    # the porcelain: coming over the old outfit once she hangs on the strings; her head and hair turn back at the moment
    base_meshes = [ob for m in models[:1] for ob in m.meshes] if len(models) > 1 else []
    a, b = arrive + 0.2 * fps, arrive + 1.2 * fps
    for mat in _materials(base_meshes):
        materials.add_porcelain(mat)
        locked = dimension._locked(settings, mat)
        expression = ("smoothstep(%.2f, %.2f, frame)" % (a, b) + (" * (1 - smoothstep(%.2f, %.2f, frame))" % (
            moment - 1.0, moment) if locked else ""))
        _drive(mat, expression)
    for mat in [m for m in bpy.data.materials if m.get(materials.P_PORCELAIN) and m not in _materials(base_meshes)]:
        materials.remove_porcelain(mat)
    # the hooks: empties on her head (its top), wrists and knees
    head = motion.find_bone(arm, motion.HEAD)
    wrists = [motion._hand(arm, side)[0] for side in motion.SIDES]
    knees = [motion.find_bone(arm, names) for names in KNEE_BONES]
    bones = [head] + wrists + knees
    hooks = []
    for k, bone in enumerate(bones):
        kind = "HOOK_%d" % k
        ob = next(iter(objects(mask, kind)), None)
        if ob is None:
            ob = bpy.data.objects.new("%s Hook %d" % (NAME, k), None)
            ob.empty_display_type, ob.empty_display_size = "PLAIN_AXES", 0.02 * height
            ob.hide_render = ob.hide_select = True
            collection.objects.link(ob)
            ob[P_PUPPET], ob[P_KIND] = mask, kind
        for c in list(ob.constraints):
            ob.constraints.remove(c)
        if bone is not None:
            con = ob.constraints.new("COPY_LOCATION")
            con.target, con.subtarget = arm, bone.name
            con.head_tail = 1.0 if k == 0 else 0.0
        else:
            ob.location = (0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z + 0.5 * height)
        hooks.append(ob)
    # the bar: over her head, following it across, coming down, swaying, flying away
    bar = next(iter(objects(mask, "BAR")), None)
    if bar is None:
        bar = bpy.data.objects.new(NAME + " Bar", bar_mesh(NAME + " Bar"))
        collection.objects.link(bar)
        bar[P_PUPPET], bar[P_KIND] = mask, "BAR"
        bar.hide_select = True
        bar.data.materials.append(materials.ensure_cover_material("PUPPET_BAR"))
    from .cover import _clear_keys, _curves, _key, _shown

    for c in list(bar.constraints):
        bar.constraints.remove(c)
    _clear_keys(bar)
    if head is not None:
        con = bar.constraints.new("COPY_LOCATION")
        con.target, con.subtarget, con.use_z = arm, head.name, False
    bar.scale = (BAR * height / 0.62,) * 3
    camera = scene.camera
    if camera is not None:
        from . import sampling

        to = sampling.matrix_at(camera, arrive).translation - Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), 0.0))
        bar.rotation_euler = (0.0, 0.0, math.atan2(to.x, -to.y) if to.length > 1e-6 else 0.0)
    hang = hi.z + (ABOVE + (settings.float_height if settings.float_up else 0.0)) * height
    top = hang + 1.4 * height
    bar.location = (0.0, 0.0, top)
    gone0, gone1 = moment + AWAY[0] * fps, moment + AWAY[1] * fps
    _key(bar, "location", ((start - 1.0, top), (start, top), (arrive, hang), (gone0, hang), (gone1, top)), index=2,
         interpolation="BEZIER")
    for fc in _curves(bar):
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
    for i in (0, 1):  # a puppeteer's hand: the bar sways a little
        bar.rotation_euler[i] = 0.0
        bar.keyframe_insert("rotation_euler", index=i, frame=start)
    for fc in _curves(bar):
        if fc.data_path == "rotation_euler" and fc.array_index in (0, 1) and not fc.modifiers:
            noise = fc.modifiers.new("NOISE")
            noise.scale, noise.strength, noise.phase = 18.0, math.radians(9.0), 3.0 + 5.0 * fc.array_index
    _shown(bar, int(math.floor(start)), int(math.ceil(gone1)) + 1)
    # the strings
    strings = next(iter(objects(mask, "STRINGS")), None)
    if strings is None:
        me = bpy.data.meshes.new(NAME + " Strings")
        strings = bpy.data.objects.new(NAME + " Strings", me)
        collection.objects.link(strings)
        strings[P_PUPPET], strings[P_KIND] = mask, "STRINGS"
        strings.hide_select = True
        if hasattr(strings, "visible_shadow"):
            strings.visible_shadow = False
    strings["mmdd_color"] = tuple(settings.puppet_color)
    mod = next((m for m in strings.modifiers if m.type == "NODES"), None) or strings.modifiers.new(NAME, "NODES")
    group = cover_nodes.ensure_puppet_strings_group()
    if mod.node_group != group:
        mod.node_group = group
    from .node_groups import input_identifiers

    ids = input_identifiers(group)
    values = {"Bar": bar, "Show": arrive + 0.1 * fps, "Grow": DROP * fps, "Whip": WHIP * fps,
              "Radius": 0.0016 * height, "Sag": 0.03 * height, "Gone": gone1,
              "Material": materials.ensure_cover_material("PUPPET_STRING")}
    for k in range(STRINGS):
        values["Hook %d" % k] = hooks[k]
        values["Attach %d" % k] = Vector(ATTACH[k])
        values["Snap %d" % k] = snap_of[k]
    for name, value in values.items():
        if name in ids:
            mod[ids[name]] = value
    strings.update_tag()


def _drive(mat, expression):
    nt = mat.node_tree
    node = nt.nodes.get(materials.PORCELAIN + " On")
    if node is None:
        return
    sock = node.outputs[0]
    sock.driver_remove("default_value")
    driver = sock.driver_add("default_value").driver
    driver.type = "SCRIPTED"
    driver.expression = expression
