"""Finishing poses (1.12, 收尾亮相): once the new outfit is complete it is shown off.

* PHOTO (写真定格, Infinity Nikki's photo poses): a beat or so after the big moment, where the whole body moves least,
  the camera's shutter flashes, the dance (hair, skirts and all that flies) freezes and a polaroid's white frame
  closes in round the picture, the world outside it dimmed and a warm light from behind outlining her; it holds, slides
  away, and the dance catches up with the music.
* GACHA (抽卡出金, the pulls of Genshin Impact and Wuthering Waves): a meteor in the colour of its rarity (blue, purple,
  gold) falls onto her just before the big moment; a flash, a ring of light runs out over the floor and a pillar of
  light rises; a moment later the dance freezes for the reveal: rays of light behind her, her name writing itself in
  letter by letter and the stars lighting up one by one; then it fades and the dance catches up.

The freeze is timewarp's hold (the dance and the transformation in strips whose time stands still, the rigid bodies
slowed to a crawl); the frame, the flash, the rays, the name and the stars are sheets and objects of ours by the
camera, the meteor, the ring and the pillar objects of ours where she stands. They are made for the camera of the
scene when the effect syncs; removing the effect takes them all away.
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector

from . import beats, materials, motion, timewarp
from . import model as mdl

P_FINISH = "mmd_disperse_finish"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_finish_kind"  # ... CARD, SHUTTER, RIM, METEOR, TAIL, RING, PILLAR, RAYS, TITLE
P_FOUND = "mmd_disperse_finish_found"  # on the mask: "key|frame" of the photo's stillest moment, found once
NAME = "MMD Disperse Finish"
SEARCH = 1.0  # seconds after the delay the photo looks for the stillest moment in
SHUTTER_POWER = 800.0  # the shutter's flash, in watts per square model height ...
RIM_POWER = 500.0  # ... the warm light from behind her while the photo holds ...
RIM_COLOR = (1.0, 0.72, 0.42)
RARITY = {"BLUE": (0.3, 0.6, 1.0), "PURPLE": (0.72, 0.36, 1.0), "GOLD": (1.0, 0.74, 0.25)}
STARS = {"BLUE": 3, "PURPLE": 4, "GOLD": 5}
METEOR_FALL = 0.55  # seconds the meteor takes to fall ...
METEOR_FROM = (1.6, 0.8, 3.2)  # ... from this far to her side, towards the camera and up (model heights)
RING_TIME = 0.7  # seconds the ring of light takes to run out ...
RING_SIZE = 2.2  # ... this far (model heights)
PILLAR = (0.17, 5.0)  # the pillar of light: its radius and height (model heights) ...
PILLAR_TIME = 1.2  # ... and how long it stands (seconds)
TITLE_SIZE = 0.065  # the name's letters: this share of the picture's height ...
TITLE_LOW = 0.33  # ... under the middle of the picture by this share of it
CARD_DEPTH = 0.98  # the card hangs this much nearer the camera than the picture fronts' sheet (in front of it)
CJK_FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf", "C:/Windows/Fonts/simhei.ttf",
             "C:/Windows/Fonts/msgothic.ttc", "/System/Library/Fonts/PingFang.ttc",
             "/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
             "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc")


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_FINISH) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is None or data.users:
        return
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Light):
        bpy.data.lights.remove(data)


def remove(mask):
    for ob in objects(mask):
        _delete(ob)
    for name in (materials.POLAROID_MATERIAL, materials.RAYS_MATERIAL, materials.FINISH_GLOW_MATERIAL):
        mat = bpy.data.materials.get(name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)
    group = bpy.data.node_groups.get(TITLE_GROUP)
    if group is not None and group.users == 0:
        bpy.data.node_groups.remove(group)


# --------------------------------------------------------------------------- when

def _stillest(scene, armature, first, last, beat_frames, hidden):
    """The frame from `first` to `last` at which the dancer moves least (her hands, feet, head and hips together), on a
    beat when there are beats then."""
    frames = list(range(int(math.floor(first)) - 1, int(math.ceil(last)) + 1))
    track = motion.play(scene, armature, frames, hidden=hidden)
    speed = np.zeros(len(frames))
    for points in (track.palm["L"], track.palm["R"], track.ankle["L"], track.ankle["R"], track.eyes, track.hips):
        speed[1:] += np.nan_to_num(np.linalg.norm(np.diff(points, axis=0), axis=1))
    candidates = list(range(1, len(frames)))
    on_beat = [i for i in candidates if any(abs(frames[i] - b) < 0.5 for b in beat_frames)]
    return frames[min(on_beat or candidates, key=lambda i: speed[i])]


def hold(settings, mask, models, big):
    """(the frame the finishing pose freezes on, how many frames it holds), None without one: the photo a little after
    the big moment `big` (a frame) where the whole body moves least (found once, kept on the mask), the gacha's reveal
    the delay after it."""
    style = settings.finish_style
    if style == "NONE" or big is None or mask is None:
        return None
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    length = max(int(round(settings.finish_hold * fps)), 2)
    first = big + settings.finish_delay * fps
    if style == "GACHA":
        return int(round(first)), length
    model = next(iter(models), None)
    armature = model.armature if model else None
    if armature is None:
        return int(round(first)), length
    key = "%d:%.3f:%.3f:%s:%d" % (big, settings.finish_delay, fps, armature.name, settings.beat_sync)
    found = str(mask.get(P_FOUND, ""))
    if found.startswith(key + "|"):
        return int(found.split("|")[1]), length
    timewarp.restore(mask, scene)  # (the dance as it is, not as a pose holds it)
    beat_frames = beats.beat_frames() if settings.beat_sync else []
    frame = _stillest(scene, armature, first, first + SEARCH * fps, beat_frames,
                      [ob for m in models for ob in m.meshes])
    mask[P_FOUND] = "%s|%d" % (key, frame)
    return frame, length


# --------------------------------------------------------------------------- pieces

def _link(ob, mask, kind, collection):
    collection.objects.link(ob)
    ob[P_FINISH] = mask
    ob[P_KIND] = kind
    ob.hide_select = True
    if hasattr(ob, "visible_shadow"):
        ob.visible_shadow = False
    return ob


def _clear_keys(id_):
    ad = id_.animation_data
    if ad is not None and ad.action is not None:
        action = ad.action
        ad.action = None
        if action.users == 0:
            bpy.data.actions.remove(action)


def _key(id_, path, keys, index=-1, interpolation=None):
    """Key `path` of `id_` at (frame, value) pairs (a vector value keys all of it)."""
    for frame, value in keys:
        prop = path[2:-2] if path.startswith('["') else None
        if prop is not None:
            id_[prop] = value
        else:
            setattr(id_, path, value)
        id_.keyframe_insert(path, index=index, frame=frame)
    if interpolation is not None:
        for fc in _curves(id_):
            if fc.data_path == path:
                for k in fc.keyframe_points:
                    k.interpolation = interpolation


def _curves(id_):
    ad = id_.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return []
    curves = getattr(action, "fcurves", None)
    if curves is None:  # Blender 5.0+
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    return list(curves)


def _sheet(scene, mask, camera, collection, kind, material, depth):
    """A sheet of ours `depth` in front of `camera`, just larger than its picture, its UVs 0 .. 1 across it."""
    from .picture import _frame

    ob = next(iter(objects(mask, kind)), None)
    key = "%s:%d:%d:%.4f:%.4f" % (camera.name, scene.render.resolution_x, scene.render.resolution_y,
                                  camera.data.clip_start, depth)
    if ob is not None and (ob.parent != camera or ob.get("mmdd_key") != key):
        _delete(ob)
        ob = None
    if ob is not None:
        return ob
    centre, width, height = _frame(scene, camera, depth)
    half_w, half_h = 0.5 * width * materials.FRONT_SHEET, 0.5 * height * materials.FRONT_SHEET
    corners = [centre + Vector((sx * half_w, sy * half_h, 0.0)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = bpy.data.meshes.new(NAME + " " + kind.title())
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        uv.data[loop.index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
    me.materials.append(material)
    ob = _link(bpy.data.objects.new(NAME + " " + kind.title(), me), mask, kind, collection)
    ob.parent = camera
    ob["mmdd_key"] = key
    return ob


def _point_light(mask, kind, collection, color, soft):
    ob = next(iter(objects(mask, kind)), None)
    if ob is None:
        ob = _link(bpy.data.objects.new(NAME + " " + kind.title(), bpy.data.lights.new(NAME + " " + kind.title(),
                                                                                      "POINT")),
                   mask, kind, collection)
    ob.data.color = color
    ob.data.shadow_soft_size = soft
    _clear_keys(ob.data)
    return ob


def _toward_camera(scene, middle):
    camera = scene.camera
    toward = camera.matrix_world.translation - middle if camera is not None else Vector((0.0, -1.0, 0.0))
    toward.z = 0.0
    return toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))


def _glow(ob, color, strength, alpha=1.0):
    """Our glowing objects share one material: their colour, strength and opacity are on them (and mmdd_fade, keyed).
    (Kept low: brighter, the colours would burn out to white.)"""
    ob["mmdd_color"] = tuple(color)
    ob["mmdd_glow"] = strength
    ob["mmdd_alpha"] = alpha
    if "mmdd_fade" not in ob:
        ob["mmdd_fade"] = 1.0


# --------------------------------------------------------------------------- the photo

def _photo(settings, mask, models, frame, length, height, collection):
    from .picture import _near

    scene = settings.id_data
    camera = scene.camera

    card = _sheet(scene, mask, camera, collection, "CARD", materials.ensure_polaroid_material(),
                  CARD_DEPTH * _near(camera))
    card[materials.FRONT_ASPECT] = sampling_aspect(scene)
    _clear_keys(card)
    f, d = float(frame), float(length)
    # the shutter: a flash of white; the frame closes in after it, holds, and slides away as the dance goes on
    _key(card, '["mmdd_flash"]', ((f - 1, 0.0), (f, 1.0), (f + 1, 0.55), (f + 3, 0.0)), interpolation="LINEAR")
    _key(card, '["mmdd_photo"]', ((f, (0.0, 0.0, 0.0)), (f + 1, (0.0, 0.0, 0.0)), (f + 6, (1.0, 0.0, 1.0)),
                                  (f + d - 1, (1.0, 0.0, 1.0)), (f + d + 6, (1.0, 1.0, 0.0))))
    # (kept closed in once it has slid away: opened up again it would be large enough to reach back into the picture)
    for path in ("hide_render", "hide_viewport"):
        _key(card, path, ((f - 2, True), (f - 1, False), (f + d + 7, True)), interpolation="CONSTANT")
    shutter = _point_light(mask, "SHUTTER", collection, (1.0, 0.98, 0.95), 0.004 * height)
    if shutter.parent != camera:
        shutter.parent = camera
    shutter.location = (0.0, 0.0, 0.0)
    peak = SHUTTER_POWER * settings.flash_power * height * height
    _key(shutter.data, "energy", ((f - 1, 0.0), (f, peak), (f + 1, 0.4 * peak), (f + 3, 0.0)),
         interpolation="LINEAR")
    rim = _point_light(mask, "RIM", collection, RIM_COLOR, 0.2 * height)
    middle = _middle(models)
    rim.location = middle - _toward_camera(scene, middle) * (0.8 * height) + Vector((0.0, 0.0, 0.5 * height))
    level = RIM_POWER * height * height
    _key(rim.data, "energy", ((f, 0.0), (f + 3, level), (f + d, level), (f + d + 6, 0.0)), interpolation="LINEAR")
    return card


def sampling_aspect(scene):
    r = scene.render
    return (r.resolution_x * r.pixel_aspect_x) / max(r.resolution_y * r.pixel_aspect_y, 1e-9)


def _middle(models):
    meshes = [ob for m in models for ob in m.meshes]
    if not meshes:
        return Vector((0.0, 0.0, 0.0))
    lo, hi = mdl.rest_bounds(meshes)
    return Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z + 0.55 * (hi.z - lo.z)))


def _floor(models):
    meshes = [ob for m in models for ob in m.meshes]
    if not meshes:
        return 0.0
    return mdl.rest_bounds(meshes)[0].z


# --------------------------------------------------------------------------- the gacha pull

def _sphere_mesh(name, radius, t_value):
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radius)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    attr = me.attributes.new("mmdd_t", "FLOAT", "POINT")
    attr.data.foreach_set("value", [t_value] * len(me.vertices))
    return me


def _tail_mesh(name, length, radius, sides=12):
    """A cone along +Z from its base (radius `radius`, mmdd_t 0) to its tip (`length`, mmdd_t 1)."""
    verts = [(radius * math.cos(2 * math.pi * k / sides), radius * math.sin(2 * math.pi * k / sides), 0.0)
             for k in range(sides)] + [(0.0, 0.0, length)]
    faces = [(k, (k + 1) % sides, sides) for k in range(sides)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new("mmdd_t", "FLOAT", "POINT")
    attr.data.foreach_set("value", [0.0] * sides + [1.0])
    for poly in me.polygons:
        poly.use_smooth = True
    return me


def _ring_mesh(name, sides=96, width=0.08):
    """A flat ring of radius 1 in the XY plane, `width` wide inwards; mmdd_t 0 at its outer edge .. 1 at its inner."""
    verts, t = [], []
    for k in range(sides):
        a = 2 * math.pi * k / sides
        verts += [(math.cos(a), math.sin(a), 0.0), ((1.0 - width) * math.cos(a), (1.0 - width) * math.sin(a), 0.0)]
        t += [0.0, 1.0]
    faces = [(2 * k, 2 * ((k + 1) % sides), 2 * ((k + 1) % sides) + 1, 2 * k + 1) for k in range(sides)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new("mmdd_t", "FLOAT", "POINT")
    attr.data.foreach_set("value", t)
    return me


def _pillar_mesh(name, sides=32):
    """An open cylinder of radius 1 from z 0 to 1; mmdd_t its height."""
    verts, t = [], []
    for z in (0.0, 1.0):
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append((math.cos(a), math.sin(a), z))
            t.append(z)
    faces = [(k, (k + 1) % sides, sides + (k + 1) % sides, sides + k) for k in range(sides)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new("mmdd_t", "FLOAT", "POINT")
    attr.data.foreach_set("value", t)
    for poly in me.polygons:
        poly.use_smooth = True
    return me


def _piece(mask, kind, collection, make):
    ob = next(iter(objects(mask, kind)), None)
    if ob is None:
        me = make()
        me.materials.append(materials.ensure_finish_glow_material())
        ob = _link(bpy.data.objects.new(NAME + " " + kind.title(), me), mask, kind, collection)
    _clear_keys(ob)
    return ob


def _gacha(settings, mask, models, moment, frame, length, height, collection):
    scene = settings.id_data
    camera = scene.camera
    fps = scene.render.fps / scene.render.fps_base
    color = RARITY[settings.finish_rarity]
    middle = _middle(models)
    floor = _floor(models)
    toward = _toward_camera(scene, middle)
    side = toward.cross(Vector((0.0, 0.0, 1.0)))
    m = float(moment)
    # the meteor: from high up at her side down onto her, its tail behind it
    start = middle + side * (METEOR_FROM[0] * height) + toward * (METEOR_FROM[1] * height) + \
        Vector((0.0, 0.0, METEOR_FROM[2] * height))
    fall = METEOR_FALL * fps
    head = _piece(mask, "METEOR", collection, lambda: _sphere_mesh(NAME + " Meteor", 1.0, 0.0))
    _glow(head, (1.0, 0.97, 0.9), 12.0)
    size = 0.05 * height
    _key(head, "location", ((m - fall - 1, start), (m - fall, start), (m - 1, middle), (m, middle)))
    _key(head, "scale", ((m - fall - 1, (0.0,) * 3), (m - fall, (size,) * 3), (m - 1, (size,) * 3), (m, (0.0,) * 3)),
         interpolation="CONSTANT")
    tail = _piece(mask, "TAIL", collection, lambda: _tail_mesh(NAME + " Meteor Tail", 1.0, 1.0))
    _glow(tail, color, 3.0, 0.5)
    tail.parent = head
    tail.matrix_parent_inverse.identity()
    way = (start - middle).normalized()
    tail.rotation_mode = "QUATERNION"
    tail.rotation_quaternion = way.to_track_quat("Z", "Y")
    tail.scale = (0.35, 0.35, 30.0)  # (in the head's units: it is scaled by the head)
    # the landing: a ring of light runs out over the floor, a pillar of light rises
    ring = _piece(mask, "RING", collection, lambda: _ring_mesh(NAME + " Ring"))
    _glow(ring, color, 4.0, 0.9)
    ring.location = (middle.x, middle.y, floor + 0.002 * height)
    grow = RING_TIME * fps
    _key(ring, "scale", ((m - 1, (0.0,) * 3), (m, (0.15 * height,) * 3), (m + grow, (RING_SIZE * height,) * 3)))
    _key(ring, '["mmdd_fade"]', ((m - 1, 0.0), (m, 1.0), (m + 0.5 * grow, 0.8), (m + grow, 0.0)),
         interpolation="LINEAR")
    pillar = _piece(mask, "PILLAR", collection, lambda: _pillar_mesh(NAME + " Pillar"))
    _glow(pillar, color, 2.5, 0.4)
    pillar.location = (middle.x, middle.y, floor)
    r, tall = PILLAR[0] * height, PILLAR[1] * height
    stand = PILLAR_TIME * fps
    _key(pillar, "scale", ((m - 1, (0.0, 0.0, tall)), (m + 3, (r, r, tall)),
                           (m + 0.5 * stand, (0.7 * r, 0.7 * r, tall)), (m + stand, (0.0, 0.0, tall))))
    _key(pillar, '["mmdd_fade"]', ((m - 1, 0.0), (m, 1.0), (m + stand, 0.0)), interpolation="LINEAR")
    # the reveal: rays behind her, a white flash at the landing; the name and the stars in front
    from .picture import _near

    distance = max((camera.matrix_world.translation - middle).length, 1e-3)
    rays = _sheet(scene, mask, camera, collection, "RAYS", materials.ensure_rays_material(), distance + 0.8 * height)
    rays[materials.FRONT_ASPECT] = sampling_aspect(scene)
    rays["mmdd_color"] = tuple(color)
    rays[materials.FRONT_TICK] = 0.0
    rays.driver_remove('["%s"]' % materials.FRONT_TICK)
    tick = rays.driver_add('["%s"]' % materials.FRONT_TICK).driver
    tick.type = "SCRIPTED"
    tick.expression = "frame"
    _clear_keys(rays)
    f, d = float(frame), float(length)
    _key(rays, '["mmdd_shown"]', ((f - 1, 0.0), (f + 3, 1.0), (f + d, 1.0), (f + d + 6, 0.0)), interpolation="LINEAR")
    card = _sheet(scene, mask, camera, collection, "CARD", materials.ensure_polaroid_material(),
                  CARD_DEPTH * _near(camera))
    card[materials.FRONT_ASPECT] = sampling_aspect(scene)
    _clear_keys(card)
    card.hide_render = card.hide_viewport = False  # (the photo pose hides it once it has slid away)
    _key(card, '["mmdd_flash"]', ((m - 1, 0.0), (m, 1.0), (m + 2, 0.4), (m + 5, 0.0)), interpolation="LINEAR")
    card["mmdd_photo"] = (0.0, 0.0, 0.0)
    _title(settings, mask, models, camera, collection, f, d, color)


# --------------------------------------------------------------------------- the name and the stars

TITLE_GROUP = "MMDDisperse Finish Title"


def _font(text):
    """A font with the letters of `text`: a system font with Chinese and Japanese, None for plain letters (or when there
    is none): Blender's own then (_builtin_font)."""
    if all(ord(ch) < 128 for ch in text):
        return None
    for path in CJK_FONTS:
        if os.path.exists(path):
            for font in bpy.data.fonts:
                if bpy.path.abspath(font.filepath).replace("\\", "/").lower() == path.lower():
                    return font
            try:
                return bpy.data.fonts.load(path, check_existing=True)
            except (RuntimeError, OSError):
                continue
    return None


def _title_text(settings, models):
    if settings.finish_title.strip():
        return settings.finish_title.strip()
    target = settings.target or settings.base
    return target.name if target is not None else "New Outfit"


def _builtin_font():
    for font in bpy.data.fonts:
        if font.filepath == "<builtin>":
            return font
    return bpy.data.fonts.load("<builtin>")


def _title(settings, mask, models, camera, collection, frame, length, color):
    """The name (letter by letter) and the stars (one by one) in the lower part of the picture, a Geometry Nodes object
    of ours by the camera; its Reveal (0 .. 1) driven on the frame."""
    from . import node_groups
    from .picture import _frame, _near

    scene = settings.id_data
    ob = next(iter(objects(mask, "TITLE")), None)
    if ob is None or ob.parent != camera:
        if ob is not None:
            _delete(ob)
        ob = _link(bpy.data.objects.new(NAME + " Title", bpy.data.meshes.new(NAME + " Title")), mask, "TITLE",
                   collection)
        ob.parent = camera
        mod = ob.modifiers.new(NAME, "NODES")
        mod.node_group = node_groups.ensure_title_group()
    depth = _near(camera) * 1.01
    centre, _width, height = _frame(scene, camera, depth)
    ob.location = (centre.x, centre.y - TITLE_LOW * height, -depth)
    text = _title_text(settings, models)
    values = {"Text": text, "Size": TITLE_SIZE * height, "Stars": STARS[settings.finish_rarity],
              "Star Size": 0.6 * TITLE_SIZE * height, "Material": materials.ensure_finish_glow_material()}
    mod = next(m for m in ob.modifiers if m.type == "NODES")
    letters = mod.node_group.nodes.get(node_groups.TITLE_TEXT)
    if letters is not None:  # (a property before Blender 5.0, a socket after; without a font no letters at all)
        font = _font(text) or _builtin_font()
        if hasattr(letters, "font"):
            letters.font = font
        elif letters.inputs.get("Font") is not None:
            letters.inputs["Font"].default_value = font
    ids = node_groups.input_identifiers(mod.node_group)
    for name, value in values.items():
        if ids.get(name) is not None and value is not None:
            mod[ids[name]] = value
    _glow(ob, (1.0, 1.0, 1.0), 1.4)
    ob["mmdd_color"] = tuple(color)
    ob["mmdd_solid"] = 1.0
    reveal = ids.get("Reveal")
    if reveal is not None:
        path = '["%s"]' % reveal
        mod.driver_remove(path)
        driver = mod.driver_add(path).driver
        driver.type = "SCRIPTED"
        driver.expression = "clamp((frame - {f:.2f}) / {d:.2f}, 0, 1)".format(f=frame + 2, d=max(0.75 * length, 1))
    _clear_keys(ob)
    _key(ob, '["mmdd_fade"]', ((frame, 1.0), (frame + length, 1.0), (frame + length + 6, 0.0)), interpolation="LINEAR")
    _key(ob, "hide_render", ((frame - 1, True), (frame, False), (frame + length + 7, True)), interpolation="CONSTANT")
    _key(ob, "hide_viewport", ((frame - 1, True), (frame, False), (frame + length + 7, True)),
         interpolation="CONSTANT")


# --------------------------------------------------------------------------- the panel -> the scene

def sync(settings, mask, models, moment, held):
    """The finishing pose's pieces as the panel says, `held` (first frame, frames) from hold(), the big moment at frame
    `moment`; all taken away when there is none."""
    style = settings.finish_style
    scene = settings.id_data
    if style == "NONE" or held is None or moment is None or scene.camera is None or not models:
        remove(mask)
        return
    keep = {"PHOTO": ("CARD", "SHUTTER", "RIM"),
            "GACHA": ("METEOR", "TAIL", "RING", "PILLAR", "RAYS", "CARD", "TITLE")}[style]
    for ob in objects(mask):
        if ob.get(P_KIND) not in keep:
            _delete(ob)
    height = max(settings.size_reference, 1e-3)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    frame, length = held
    if style == "PHOTO":
        _photo(settings, mask, models, frame, length, height, collection)
    else:
        _gacha(settings, mask, models, moment, frame, length, height, collection)
