"""The big calligraphy title (书法大字幕, 1.18): a little before the big moment the name of the move is brushed onto the
picture in great strokes of ink (or gold), one sweep of the brush across it (down it, set upright), and holds as the
outfits swap; then it blows away in specks of ink, or shrinks into a red seal in a corner of the picture and stays a
while. The huge on-screen titles of a drama's finishing moves (《烈焰》); a skin of the fourth round's system window.

Our objects hang on the camera in front of the picture like the other lens covers: the words (a text object of the
font the panel names: Blender's own has no Chinese on 3.6, Windows' 楷体 is C:/Windows/Fonts/simkai.ttf) and the seal's
frame behind them. The material brushes them in along their own X (or down their Y, set upright) as the object's
mmdd_reveal goes 0 .. 1, blows them away as mmdd_blow does and turns them seal red as mmdd_seal does; mmdd_span_x and
mmdd_span_y are their extent, mmdd_style their colour (0 ink, 0.5 gold, 1 white).
"""

import math

import bpy
from mathutils import Vector

from . import materials

P_TITLE = "mmd_disperse_title"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_title_kind"  # ... WORDS or SEAL
NAME = "MMD Disperse Title"
BRUSH = 0.7  # the brushing takes this share of Title Time, the rest it holds before the moment
HOLD = 0.45  # seconds it stays after the moment before it goes ...
GO = 0.5  # ... going over this long (blown away, or shrinking into the seal)
STAY = 1.6  # ... the seal staying this long after that
WIDE = 0.72  # the words as wide as this share of the picture (or as tall, set upright)
CORNER = (0.28, -0.32)  # where the seal sits (shares of the picture's width and height from its middle) ...
SEAL_SIZE = 0.17  # ... and how big the words are in it (a share of their size)


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_TITLE) == mask and (kind is None or ob.get(P_KIND) == kind)]


def remove(mask):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Curve) and data.users == 0:
            bpy.data.curves.remove(data)
        elif isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    if not any(ob.get(P_TITLE) is not None for ob in bpy.data.objects):
        for kind in ("TITLE", "SEAL_FRAME"):
            mat = bpy.data.materials.get(materials._cover_name(kind))
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def _font(path):
    """The font file `path` (Blender's own when empty or unreadable)."""
    if path:
        try:
            return bpy.data.fonts.load(bpy.path.abspath(path), check_existing=True)
        except (RuntimeError, OSError):
            pass
    return bpy.data.fonts.load("<builtin>", check_existing=True)


def _extent(ob):
    """(x min, x max, y min, y max) of the words in their own space, read off their shape."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        xs = [v.co.x for v in me.vertices] or [0.0]
        ys = [v.co.y for v in me.vertices] or [0.0]
    finally:
        ev.to_mesh_clear()
    return min(xs), max(xs), min(ys), max(ys)


def _words(mask, collection, camera, text, font_path, upright):
    """The words' object on `camera` (made again when the words, the font or the setting changed)."""
    key = "%s|%s|%d|%s" % (text, font_path, int(upright), camera.name)
    ob = next(iter(objects(mask, "WORDS")), None)
    if ob is not None and (ob.get("mmdd_key") != key or ob.parent != camera):
        cu = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        ob = None
    if ob is None:
        cu = bpy.data.curves.new(NAME, "FONT")
        cu.body = "\n".join(text) if upright else text
        cu.font = _font(font_path)
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.space_line = 0.95
        cu.materials.append(materials.ensure_cover_material("TITLE"))
        ob = bpy.data.objects.new(NAME, cu)
        collection.objects.link(ob)
        ob[P_TITLE], ob[P_KIND], ob["mmdd_key"] = mask, "WORDS", key
        ob.hide_select = True
        ob.parent = camera
        for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
            if hasattr(ob, flag):
                setattr(ob, flag, False)
    return ob


def _seal_frame(mask, collection, words):
    """The seal's frame: a square a unit across behind the words (their child)."""
    ob = next(iter(objects(mask, "SEAL")), None)
    if ob is None:
        me = bpy.data.meshes.new(NAME + " Seal")
        me.from_pydata([(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)], [], [(0, 1, 2, 3)])
        layer = me.uv_layers.new(name="UVMap")
        for loop in me.loops:
            layer.data[loop.index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
        me.materials.append(materials.ensure_cover_material("SEAL_FRAME"))
        ob = bpy.data.objects.new(NAME + " Seal", me)
        collection.objects.link(ob)
        ob[P_TITLE], ob[P_KIND] = mask, "SEAL"
        ob.hide_select = True
        for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
            if hasattr(ob, flag):
                setattr(ob, flag, False)
    ob.parent = words
    return ob


def sync(settings, mask, moment):
    """The title as the panel says, for the big moment at frame `moment`; taken away when it is off."""
    from . import shots
    from .cover import _clear_keys, _key, _near_depth, _plane, _shown

    if mask is None:
        return
    scene = settings.id_data
    camera = shots.carrier(scene, mask)
    text = settings.title_text.strip()
    if not getattr(settings, "title_enable", False) or moment is None or camera is None or not text:
        remove(mask)
        return
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    start = m - settings.title_time * fps
    brushed = start + BRUSH * settings.title_time * fps
    go = m + HOLD * fps
    gone = go + GO * fps
    end = gone + (STAY * fps if settings.title_end == "SEAL" else 0.0)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    upright = settings.title_upright
    words = _words(mask, collection, camera, text, settings.title_font, upright)
    _clear_keys(words)
    x0, x1, y0, y1 = _extent(words)
    words["mmdd_span_x"] = (x0, x1, 0.0)
    words["mmdd_span_y"] = (y0, y1, 0.0)
    words["mmdd_upright"] = 1.0 if upright else 0.0
    words["mmdd_style"] = {"INK": 0.0, "GOLD": 0.5, "WHITE": 1.0}[settings.title_style]
    depth = _near_depth(camera)
    centre, width, tall = _plane(scene, camera, depth)
    across = max((y1 - y0) if upright else (x1 - x0), 1e-6)
    size = WIDE * (tall if upright else width) / across
    if not upright:  # (no wider than the picture is tall, either)
        size = min(size, 0.5 * tall / max(y1 - y0, 1e-6))
    here = Vector((centre.x - 0.5 * (x0 + x1) * size, centre.y - 0.5 * (y0 + y1) * size, -depth))
    seal = _seal_frame(mask, collection, words)
    seal_size = SEAL_SIZE * size
    corner = Vector((centre.x + CORNER[0] * width, centre.y + CORNER[1] * tall, -depth)) - Vector((
        0.5 * (x0 + x1) * seal_size, 0.5 * (y0 + y1) * seal_size, 0.0))
    words.rotation_euler = (0.0, 0.0, 0.0)
    for prop, value in (("mmdd_reveal", 0.0), ("mmdd_blow", 0.0), ("mmdd_seal", 0.0)):
        words[prop] = value
    _key(words, '["mmdd_reveal"]', ((start, 0.0), (brushed, 1.0)), interpolation="LINEAR")
    if settings.title_end == "SEAL":
        _key(words, "location", ((go, here), (gone, corner)), interpolation="BEZIER")
        _key(words, "scale", ((go, (size, size, size)), (gone, (seal_size,) * 3)), interpolation="BEZIER")
        _key(words, '["mmdd_seal"]', ((go, 0.0), (gone, 1.0)), interpolation="LINEAR")
        _key(words, '["mmdd_blow"]', ((end - 0.3 * fps, 0.0), (end, 1.0)), interpolation="LINEAR")
    else:  # blown away: drifting up and growing a little as it goes to specks
        drift = Vector((0.06 * width, 0.08 * tall, 0.0))
        _key(words, "location", ((go, here), (gone, here + drift)), interpolation="LINEAR")
        _key(words, "scale", ((go, (size, size, size)), (gone, (1.08 * size,) * 3)), interpolation="LINEAR")
        _key(words, '["mmdd_blow"]', ((go, 0.0), (gone, 1.0)), interpolation="LINEAR")
    _shown(words, int(math.floor(start)) - 1, int(math.ceil(end)) + 1)
    # the seal's frame: a square round the words' middle, a little larger than them, red as they shrink into it
    _clear_keys(seal)
    seal.location = (0.5 * (x0 + x1), 0.5 * (y0 + y1), -0.01 * (y1 - y0))
    side = 1.25 * max(x1 - x0, y1 - y0)
    seal.scale = (side, side, 1.0)
    seal["mmdd_seal"] = 0.0
    if settings.title_end == "SEAL":
        _key(seal, '["mmdd_seal"]', ((go, 0.0), (gone, 1.0), (end - 0.3 * fps, 1.0), (end, 0.0)),
             interpolation="LINEAR")
        _shown(seal, int(math.floor(go)), int(math.ceil(end)) + 1)
    else:
        _shown(seal, -100000, -99999)
