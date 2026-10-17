"""The front on the picture (画面上的前沿, 1.12): the picture path's front drawn where the camera sees it, exactly where
the outfit changes (sampling.time_field; the materials draw the same field):

* a sheet just in front of the camera (parented to it, like the speed lines): a line of light wiping across, a ring
  opening from the dancer, a folding fan, three strokes of a big brush in ink, a hole burning through the film;
* the paint smear (颜料抹开): the strokes of wet paint the palms leave across the picture (a mesh of ours on the same
  plane, made from where the palms were on the picture every frame, shown up to the frame and drying away after), and
  a blob of paint on each palm before, one in each of the new outfit's two main colours, swirled together from the
  moment the change starts (the clap).

The sheet reads its object properties (materials.FRONT_*): the progress (driven on the frame), the centre of the iris
or the burn (keyed per frame as the dancer moves) and the direction, the picture's shape, the frame. Building records
what the camera saw on the mask (record()); removing the effect removes all of it.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials, motion, sampling

SHEET = "MMD Disperse Picture Front"
SMEAR = "MMD Disperse Paint Smear"
BLOB = "MMD Disperse Paint"
P_FRONT = "mmd_disperse_picture_front"  # on our objects: the mask of their effect
P_KIND = "mmd_disperse_picture_kind"  # ... SHEET, SMEAR, BLOB_L, BLOB_R
P_KEY = "mmd_disperse_picture_key"  # ... what they were made for
BLOB_SIZE = 0.03  # how big a blob of paint is, a share of the model height
BLOB_BEFORE = 1.0  # seconds the blobs show up before the change starts ...
BLOB_GROW = 0.3  # ... growing over this long
SMEAR_STEPS = 4  # points of the paint stroke a frame (the palms' way between frames is smoothed) ...
SMEAR_GAP = 1.0  # ... kept at least this many brush half widths apart (a palm that hardly moves leaves no knot) ...
SMEAR_TURN = 0.35  # ... and a stroke ends where the way turns sharper than this (cosine), the next starts there
SMEAR_AFTER = 0.2  # seconds the palms go on smearing after nearly all the change has come
DEPTH = 1.02  # the paint lies this much further than the sheet


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_FRONT) == mask and (kind is None or ob.get(P_KIND) == kind)]


def record(question):
    """What the camera saw while the picture path was sampled (sampling.PictureFront), to keep on the mask."""
    out = {"shape": question.shape, "start": question.start, "end": question.end, "angle": question.angle,
           "aspect": question.aspect, "brush": question.brush,
           "until": float(getattr(question, "touched_until", question.end)),
           "camera": question.camera.name if question.camera is not None else "",
           "span": list(question.span) if question.span is not None else [0.0, 1.0, 0.0, 0.0]}
    frames = sorted(question.centres)
    if frames:
        out["frames"] = [float(f) for f in frames]
        out["cx"] = [question.centres[f][0] for f in frames]
        out["cy"] = [question.centres[f][1] for f in frames]
    for side, way in question.hands.items():
        if way:
            frames = sorted(way)
            out["hand_" + side] = [v for f in frames for v in (float(f), way[f][0], way[f][1])]
    return out


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)


def remove(mask, kinds=None):
    for ob in objects(mask):
        if kinds is None or ob.get(P_KIND) in kinds:
            _delete(ob)
    if kinds is None:
        for name in [m.name for m in bpy.data.materials if m.name.startswith((materials.PICTURE_MATERIAL,
                                                                              materials.PAINT_MATERIAL))]:
            mat = bpy.data.materials.get(name)
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


def _frame(scene, camera, depth):
    """(centre, width, height) of `camera`'s picture at `depth` in front of it, in its own space."""
    corners = [c.copy() for c in camera.data.view_frame(scene=scene)]
    if camera.data.type != "ORTHO":
        for c in corners:
            c *= depth / max(abs(c.z), 1e-9)
    xs, ys = [c.x for c in corners], [c.y for c in corners]
    centre = Vector(((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, -depth))
    return centre, max(xs) - min(xs), max(ys) - min(ys)


def _near(camera):
    return max(camera.data.clip_start * 3.0, 1e-3)


def _sheet(scene, mask, camera, collection, shape):
    """The sheet in front of `camera`, just larger than its picture, its UVs 0 .. 1 across it."""
    ob = next(iter(objects(mask, "SHEET")), None)
    key = "%s:%s:%d:%d:%.4f" % (camera.name, shape, scene.render.resolution_x, scene.render.resolution_y,
                                camera.data.clip_start)
    if ob is not None and (ob.parent != camera or ob.get(P_KEY) != key):
        _delete(ob)
        ob = None
    if ob is not None:
        return ob
    centre, width, height = _frame(scene, camera, _near(camera))
    half_w, half_h = 0.5 * width * materials.FRONT_SHEET, 0.5 * height * materials.FRONT_SHEET
    corners = [centre + Vector((sx * half_w, sy * half_h, 0.0)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = bpy.data.meshes.new(SHEET)
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        sx, sy = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
        uv.data[loop.index].uv = (sx, sy)
    me.materials.append(materials.ensure_picture_material(shape))
    ob = bpy.data.objects.new(SHEET, me)
    collection.objects.link(ob)
    ob.parent = camera
    ob.hide_select = True
    if hasattr(ob, "visible_shadow"):
        ob.visible_shadow = False
    ob[P_FRONT] = mask
    ob[P_KIND] = "SHEET"
    ob[P_KEY] = key
    return ob


def _drive(ob, prop, expression, index=-1):
    ob.driver_remove(prop, index) if index >= 0 else ob.driver_remove(prop)
    driver = (ob.driver_add(prop, index) if index >= 0 else ob.driver_add(prop)).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def _keys(ob, prop, index, frames, values):
    """Key element `index` of the vector property `prop` of `ob` at `frames` (linear)."""
    data_path = '["%s"]' % prop
    for f, v in zip(frames, values):
        ob[prop][index] = v
        ob.keyframe_insert(data_path, index=index, frame=f)
    ad = ob.animation_data
    action = ad.action if ad is not None else None
    curves = getattr(action, "fcurves", None) if action is not None else None
    if action is not None and curves is None:  # Blender 5.0+
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    for fc in curves or []:
        if fc.data_path == data_path and fc.array_index == index:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"
            fc.update()


def _sync_sheet(scene, mask, rec, camera, collection, settings):
    shape = rec["shape"]
    ob = _sheet(scene, mask, camera, collection, shape)
    start, end = float(rec["start"]), float(rec["end"])
    ob[materials.FRONT_ASPECT] = float(rec["aspect"])
    ob[materials.FRONT_TICK] = float(scene.frame_current)
    ob[materials.FRONT_P] = 0.0
    _drive(ob, '["%s"]' % materials.FRONT_P, "(frame - {s}) / {l}".format(s=start, l=max(end - start, 1.0)))
    _drive(ob, '["%s"]' % materials.FRONT_TICK, "frame")
    if ob.animation_data is not None and ob.animation_data.action is not None:
        action = ob.animation_data.action
        ob.animation_data.action = None
        if action.users == 0:
            bpy.data.actions.remove(action)
    angle = float(rec["angle"])
    span = [float(v) for v in rec.get("span", (0.0, 1.0, 0.0, 0.0))]
    ob[materials.FRONT_SPAN] = tuple(span[:3])
    ob[materials.FRONT_SPAN4] = span[3]
    frames = list(rec.get("frames", []))
    if shape in sampling.CENTRED and frames:
        ob[materials.FRONT_AT] = (float(rec["cx"][0]), float(rec["cy"][0]), angle)
        _keys(ob, materials.FRONT_AT, 0, frames, list(rec["cx"]))
        _keys(ob, materials.FRONT_AT, 1, frames, list(rec["cy"]))
    else:
        ob[materials.FRONT_AT] = (0.0, 0.0, angle)
    materials.update_picture_material(shape, settings.glow_color, settings.picture_glow, settings.paper_color,
                                      settings.ink_color)
    ob.update_tag()
    return ob


def _smooth_way(samples, steps):
    """Catmull-Rom through `samples` (frame, x, y): `steps` points a frame, as (frames, xs, ys)."""
    f = np.asarray([s[0] for s in samples], dtype=np.float64)
    p = np.asarray([(s[1], s[2]) for s in samples], dtype=np.float64)
    if len(p) < 2:
        return f, p[:, 0], p[:, 1]
    padded = np.concatenate([p[:1], p, p[-1:]])
    out_f, out_p = [], []
    for i in range(len(p) - 1):
        p0, p1, p2, p3 = padded[i], padded[i + 1], padded[i + 2], padded[i + 3]
        for k in range(steps):
            t = k / float(steps)
            point = 0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                           + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t)
            out_f.append(f[i] + (f[i + 1] - f[i]) * t)
            out_p.append(point)
    out_f.append(f[-1])
    out_p.append(p[-1])
    out_p = np.asarray(out_p)
    return np.asarray(out_f), out_p[:, 0], out_p[:, 1]


def _runs(samples):
    """`samples` (frame, x, y) cut where a frame is missing (the palm off the picture)."""
    runs, current = [], []
    for sample in samples:
        if current and sample[0] - current[-1][0] > 1.5:
            runs.append(current)
            current = []
        current.append(sample)
    if current:
        runs.append(current)
    return [r for r in runs if len(r) >= 2]


def _strokes(pts, frames, gap):
    """The way (points on the plane, their frames) thinned to points at least `gap` apart and cut into strokes where it
    turns back: [(points, frames)], each of two points or more."""
    keep = [0]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[keep[-1]]) >= gap:
            keep.append(i)
    if keep[-1] != len(pts) - 1 and len(keep) > 1 and np.linalg.norm(pts[-1] - pts[keep[-2]]) >= gap:
        keep[-1] = len(pts) - 1  # (end where the palm ended, not a hair short of it)
    pts, frames = pts[keep], frames[keep]
    if len(pts) < 2:
        return []
    seg = np.diff(pts, axis=0)
    seg /= np.maximum(np.linalg.norm(seg, axis=1), 1e-12)[:, None]
    turns = np.einsum("ij,ij->i", seg[1:], seg[:-1])
    cuts = [0] + [int(i) + 1 for i in np.nonzero(turns < SMEAR_TURN)[0]] + [len(pts) - 1]
    return [(pts[a:b + 1], frames[a:b + 1]) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def _strip(pts, frames, half, depth, out):
    """A stroke's strip, `half` either side of its points (on the plane `depth` in front of the camera), added to
    `out` (verts, faces, times, alongs, lefts, acrosses): the sides follow the way's direction over a few points, and a
    side that would fold back on the inside of a bend stays put instead."""
    verts, faces, times, alongs, lefts, acrosses = out
    n = len(pts)
    tangent = pts[np.minimum(np.arange(n) + 2, n - 1)] - pts[np.maximum(np.arange(n) - 2, 0)]
    lengths = np.linalg.norm(tangent, axis=1)
    ok = lengths > 1e-9
    tangent[ok] /= lengths[ok, None]
    tangent[~ok] = (1.0, 0.0)
    normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    travelled = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    width = max(2.0 * half, 1e-9)
    base = len(verts)
    sides = {-1.0: [], 1.0: []}
    for i in range(n):
        for side_k in (-1.0, 1.0):
            q = pts[i] + normal[i] * half * side_k
            if i and np.dot(q - sides[side_k][-1], tangent[i]) < 0.0:
                q = sides[side_k][-1]  # (folding back: hold this side where it was)
            sides[side_k].append(q)
    for i in range(n):
        for side_k, across in ((-1.0, 0.0), (1.0, 1.0)):
            q = sides[side_k][i]
            verts.append((q[0], q[1], -depth))
            times.append(frames[i])
            alongs.append(travelled[i] / width)
            lefts.append((travelled[-1] - travelled[i]) / width)
            acrosses.append(across)
        if i:
            a = base + 2 * (i - 1)
            faces.append((a, a + 2, a + 3, a + 1))


def _smear_mesh(rec, scene, camera):
    """The paint strokes on the picture's plane (in the camera's space): a strip along each palm's way as wide as the
    brush (see _strokes), until shortly after nearly all the change has come, with the frame (mmdd_t), how far along
    (mmdd_along, in brush widths) and across (ATTR_ACROSS) on its points."""
    depth = _near(camera) * DEPTH
    centre, width, height = _frame(scene, camera, depth)
    aspect = float(rec["aspect"])
    half = float(rec["brush"]) * height
    fps = scene.render.fps / scene.render.fps_base
    stop = float(rec.get("until", rec["end"])) + SMEAR_AFTER * fps
    out = ([], [], [], [], [], [])
    for side in motion.SIDES:
        flat = list(rec.get("hand_" + side, []))
        samples = [flat[i:i + 3] for i in range(0, len(flat) - 2, 3)]
        for run in _runs([s for s in samples if s[0] <= stop]):
            frames, xs, ys = _smooth_way(run, SMEAR_STEPS)
            # picture (x across, its width the aspect; y up, height 1) -> the plane
            way = np.stack([centre.x + xs / aspect * width, centre.y + ys * height], axis=1)
            for pts, at in _strokes(way, frames, SMEAR_GAP * half):
                _strip(pts, at, half, depth, out)
    verts, faces, times, alongs, lefts, acrosses = out
    me = bpy.data.meshes.new(SMEAR)
    me.from_pydata(verts, [], faces)
    for name, values in (("mmdd_t", times), ("mmdd_along", alongs), ("mmdd_left", lefts),
                         (materials.ATTR_ACROSS, acrosses)):
        attr = me.attributes.new(name, "FLOAT", "POINT")
        if values:
            attr.data.foreach_set("value", np.asarray(values, dtype=np.float32))
    me.materials.append(materials.ensure_paint_material())
    me.update()
    return me


def _smear(scene, mask, rec, camera, collection):
    key = "%s:%s:%.4f:%d:%d" % (camera.name, mask.name, float(rec["start"]), scene.render.resolution_x,
                                scene.render.resolution_y)
    ob = next(iter(objects(mask, "SMEAR")), None)
    if ob is not None and (ob.parent != camera or ob.get(P_KEY) != key):
        _delete(ob)
        ob = None
    if ob is None:
        ob = bpy.data.objects.new(SMEAR, _smear_mesh(rec, scene, camera))
        collection.objects.link(ob)
        ob.parent = camera
        ob.hide_select = True
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
        ob[P_FRONT] = mask
        ob[P_KIND] = "SMEAR"
        ob[P_KEY] = key
        ob[materials.FRONT_TICK] = 0.0
        _drive(ob, '["%s"]' % materials.FRONT_TICK, "frame")
    return ob


def _blob_mesh(radius):
    """A lumpy ball of paint."""
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
    for v in bm.verts:
        d = v.co.normalized()
        bump = 1.0 + 0.18 * math.sin(5.0 * d.x + 1.3) * math.sin(4.0 * d.y + 0.7) + 0.1 * math.sin(9.0 * d.z)
        v.co = d * radius * bump * (0.8 if d.z < -0.3 else 1.0)
    me = bpy.data.meshes.new(BLOB)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    return me


def _blobs(scene, mask, rec, armature, collection, height, sides):
    """A blob of paint on each palm: growing in before the change starts, its own colour, both colours swirled from the
    start on (the clap), used up as the hands smear."""
    fps = scene.render.fps / scene.render.fps_base
    start, end = float(rec["start"]), float(rec["end"])
    key = "%s:%.3f:%.3f:%.4f" % (armature.name, start, end, height)
    made = []
    for k, side in enumerate(motion.SIDES):
        kind = "BLOB_" + side
        ob = next(iter(objects(mask, kind)), None)
        if side not in sides:
            if ob is not None:
                _delete(ob)
            continue
        if ob is not None and ob.get(P_KEY) == key:
            made.append(ob)
            continue
        if ob is not None:
            _delete(ob)
        wrist, finger = motion._hand(armature, side)
        if wrist is None:
            continue
        me = _blob_mesh(BLOB_SIZE * height)
        me.materials.append(materials.ensure_blob_material())
        ob = bpy.data.objects.new("%s %s" % (BLOB, side), me)
        collection.objects.link(ob)
        ob[P_FRONT] = mask
        ob[P_KIND] = kind
        ob[P_KEY] = key
        ob[materials.PAINT_SIDE] = float(k)
        ob[materials.PAINT_MIX] = 0.0
        # on the palm, carried by the wrist bone (kept where it is now)
        mw = armature.matrix_world
        palm_now = mw @ (wrist.head + 0.6 * ((finger.head if finger is not None else wrist.tail) - wrist.head))
        ob.parent = armature
        ob.parent_type = "BONE"
        ob.parent_bone = wrist.name
        bone_world = mw @ wrist.matrix @ Matrix.Translation((0.0, wrist.bone.length, 0.0))
        ob.matrix_parent_inverse = bone_world.inverted()
        ob.location = palm_now
        ob.hide_select = True
        appear = start - BLOB_BEFORE * fps
        grown = appear + BLOB_GROW * fps
        gone = max(start + 2.0, min(float(rec.get("until", end)), start + 0.6 * (end - start)))
        for frame, size in ((appear, 0.0), (grown, 1.0), (start, 1.0), (gone, 0.0)):
            ob.scale = (size, size, size)
            ob.keyframe_insert("scale", frame=frame)
        for frame, mix in ((start - 1.0, 0.0), (start, 1.0)):
            ob[materials.PAINT_MIX] = mix
            ob.keyframe_insert('["%s"]' % materials.PAINT_MIX, frame=frame)
        made.append(ob)
    return made


def _palette(settings, mask):
    """The two paint colours: the new outfit's main colours (found when the effect was built) or the panel's."""
    found = mask.get("mmd_disperse_palette")
    if settings.paint_auto and found is not None and len(found) >= 6:
        return tuple(found[0:3]), tuple(found[3:6])
    return tuple(settings.paint_color_a), tuple(settings.paint_color_b)


def sync(settings, mask, models):
    """Create / update / remove the front on the picture to match the built effect and the panel."""
    rec = mask.get("mmd_disperse_picture")
    scene = settings.id_data
    if rec is None or mask.get("mmd_disperse_path") != "PICTURE":
        remove(mask)
        return
    rec = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
    camera = bpy.data.objects.get(rec.get("camera", ""))
    if camera is None or camera.type != "CAMERA":
        remove(mask)
        return
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    shape = rec["shape"]
    if shape != "SMEAR" and settings.picture_show:
        _sync_sheet(scene, mask, rec, camera, collection, settings)
    else:
        remove(mask, ("SHEET",))
    if shape == "SMEAR":
        _smear(scene, mask, rec, camera, collection)
        model = next(iter(models), None)
        armature = model.armature if model else None
        if armature is not None and settings.picture_show:
            from .model import rest_bounds
            lo, hi = rest_bounds(model.meshes)
            sides = {"BOTH": ("L", "R"), "LEFT": ("L",), "RIGHT": ("R",)}[settings.hand_side]
            _blobs(scene, mask, rec, armature, collection, hi.z - lo.z, sides)
        else:
            remove(mask, ("BLOB_L", "BLOB_R"))
        for ob in objects(mask, "SMEAR"):
            ob.hide_viewport = ob.hide_render = not settings.picture_show
        materials.update_paint_materials(*_palette(settings, mask))
    else:
        remove(mask, ("SMEAR", "BLOB_L", "BLOB_R"))


# --------------------------------------------------------------------------- the new outfit's own colours

def _image_of(mat):
    """The image a material takes its base colour from (mmd_tools' base texture, or one feeding a Base Color)."""
    nt = mat.node_tree if mat.use_nodes else None
    if nt is None:
        return None
    node = nt.nodes.get("mmd_base_tex")
    if node is not None and getattr(node, "image", None) is not None:
        return node.image
    for link in nt.links:
        if link.from_node.bl_idname == "ShaderNodeTexImage" and link.to_socket.name in ("Base Color", "Color",
                                                                                         "Base Tex"):
            if link.from_node.image is not None:
                return link.from_node.image
    return None


def _to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


PAINT_GROUPS = 6  # colour groups the outfit is sorted into before the paints are picked
PAINT_LIGHT = 0.3  # the paints are at least this light (display value), so they show on a dark stage


def outfit_colors(materials_areas, count=2, samples=20000, seed=7):
    """The `count` paint colours (linear RGB) for the materials in `materials_areas` ((material, area) pairs): pixels
    of each material's base colour texture, as many as its share of the area, or its viewport colour, sorted into
    colour groups by k-means; the groups that are common, colourful and light come first (a black suit's coloured
    trim rather than black twice), each at least PAINT_LIGHT light."""
    rng = np.random.default_rng(seed)
    total = sum(area for _m, area in materials_areas) or 1.0
    picked = []
    for mat, area in materials_areas:
        n = max(int(samples * area / total), 16)
        image = _image_of(mat)
        pixels = None
        if image is not None and image.size[0] * image.size[1] > 0:
            try:
                buf = np.empty(image.size[0] * image.size[1] * image.channels, dtype=np.float32)
                image.pixels.foreach_get(buf)
                px = buf.reshape(-1, image.channels)
                if image.channels >= 4:
                    px = px[px[:, 3] > 0.5]
                px = px[:, :3]
                if len(px):
                    pixels = px[rng.integers(0, len(px), n)]
                    if image.colorspace_settings.name not in ("sRGB", "Filmic sRGB", "AgX Base sRGB"):
                        pixels = np.clip(pixels, 0.0, 1.0) ** (1.0 / 2.2)  # (linear or data: roughly to display)
            except (RuntimeError, ValueError, TypeError):
                pixels = None
        if pixels is None:
            c = np.clip(np.asarray(mat.diffuse_color[:3], dtype=np.float64), 0.0, 1.0) ** (1.0 / 2.2)
            pixels = np.repeat(c[None, :], n, axis=0)
        picked.append(pixels)
    if not picked:
        return []
    data = np.concatenate(picked).astype(np.float64)
    groups = max(count, PAINT_GROUPS)
    # k-means in display colours: start from the median colour and, one by one, the farthest from those
    centres = [np.median(data, axis=0)]
    while len(centres) < groups:
        d = np.min([np.linalg.norm(data - c, axis=1) for c in centres], axis=0)
        centres.append(data[int(np.argmax(d))])
    centres = np.asarray(centres)
    for _ in range(12):
        label = np.argmin(np.stack([np.linalg.norm(data - c, axis=1) for c in centres]), axis=0)
        for k in range(groups):
            if (label == k).any():
                centres[k] = data[label == k].mean(axis=0)
    label = np.argmin(np.stack([np.linalg.norm(data - c, axis=1) for c in centres]), axis=0)
    share = np.asarray([(label == k).mean() for k in range(groups)])
    value = centres.max(axis=1)
    saturation = (value - centres.min(axis=1)) / np.maximum(value, 1e-6)
    score = np.sqrt(share) * (0.1 + saturation) * (0.15 + value) * (share > 0.004)
    chosen = []
    for k in np.argsort(-score):
        if len(chosen) < count and all(np.linalg.norm(centres[k] - centres[j]) > 0.15 for j in chosen):
            chosen.append(int(k))
    paints = [centres[k] for k in chosen]
    while len(paints) < count:  # (one colour all over: a lighter one of it as well)
        paints.append(np.clip(paints[-1] * 1.6 + 0.1, 0.0, 1.0) if paints else np.full(3, 0.5))
    lit = [c * (PAINT_LIGHT / max(c.max(), 1e-6)) if c.max() < PAINT_LIGHT else c for c in paints]
    return [tuple(float(v) for v in _to_linear(np.clip(c, 0.0, 1.0))) for c in lit]
