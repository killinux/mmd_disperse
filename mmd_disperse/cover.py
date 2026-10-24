"""Covers (遮挡, 1.13): at the big moment (the swap, or the new outfit complete) something covers the dancer and the
change happens behind it. The sixth research round's finding (docs/research.md 「十」): what people remember is not
how an outfit turns into the next, but the beat where something covers her and then opens, or lets something go.

In front of the camera (parented to it):
* SHATTER (打碎画面): a sword slash streaks across the picture, cracks run out from it, the glass flashes white and
  bursts into shards flying at the camera (Honkai: Star Rail's Seele);
* CLOTH (飞布盖镜头): a cloth flies from her hand at the lens, unfolding, covers it and slides down (Don't Rush);
* UMBRELLA (雨伞花瓣): an umbrella spins past the lens, its canopy filling the picture, and lifts away shedding
  petals;
* FAN (风扇叶片): the wooden blades of a fan turn slowly in front of the camera; the outfit changes as a blade sweeps
  over her (the fan-blade transition);
* EMOJI (emoji 遮脸): an emoji on her face pops up over all of her for a few frames and shrinks back.
On the stage:
* FRAME (画框爆羽): a gilded frame stands in front of her; its canvas turns paper white and bursts into feathers
  (Solange Kardinaly's quick change);
* CONFETTI (彩带炮): cannons at the front of the stage fire foil streamers over her;
* BALLOONS (气球放飞): a cloud of balloons bursts out in front of her and rises (Nymphia Wind's reveal);
* FEATHERS (羽扇遮身): a great feather fan on each hand opens in front of her body (a burlesque fan dance);
* CURTAIN (落幕): a red curtain comes down in front of her and drops to the floor (the kabuki drop);
* SLOT (老虎机开奖, 1.15): a slot machine drops in front of her, its reels stop one by one on the beats, 7 7 7 at the
  moment, and it rises away leaving coins on the floor (slot.py).

The coverage check (覆盖判定): building plays the dance round the moment (the bones only, motion.play) and sees where
she is on the picture every frame: the ends of all her deform bones, hair and skirt too, give her outline (watch).
The full covers are fitted to cover all of her at the moment; the balloons and the feather fans cover only part of
her, so the moment moves (within SEARCH) to the frame they cover most of her then (best_frame). What was seen is kept
on the mask (P_SEEN); the pieces are made for the camera of that moment when the effect syncs. Removing the effect
takes them all away.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials, motion, sampling, shots

STYLES = ("NONE", "SHATTER", "CLOTH", "UMBRELLA", "FAN", "EMOJI", "FRAME", "CONFETTI", "BALLOONS", "FEATHERS",
          "CURTAIN", "SLOT")
LENS = ("SHATTER", "CLOTH", "UMBRELLA", "FAN", "EMOJI")  # the covers in front of the camera
MOVABLE = ("BALLOONS", "FEATHERS")  # the covers the moment moves for, to where they cover most of her
P_COVER = "mmd_disperse_cover"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_cover_kind"  # ... GLASS, CLOTH, UMBRELLA, PETALS, FAN, EMOJI, FRAME, CANVAS, FEATHERS_BURST,
# CANNON, CONFETTI, BALLOONS, FAN_L, FAN_R, CURTAIN, SLOT, REEL_0..2, LEVER, COINS
P_KEY = "mmd_disperse_cover_key"  # ... what it was made for
P_SEEN = "mmd_disperse_cover_seen"  # on the mask: what building saw of the dancer round the moment (watch)
P_MOVED = "mmd_disperse_cover_moved"  # ... and how many frames the coverage check moved the moment
NAME = "MMD Disperse Cover"
WATCH = 2.0  # seconds before and after the planned moment building watches the dancer
SEARCH = 0.6  # seconds the moment may move for the balloons and the feather fans to cover most of her
PAD = 0.08  # the box round her bones' ends is this much larger (a share of its size): her body round them
DEPTH = 0.94  # the lens covers hang this much nearer the camera than the picture fronts' sheet

# the glass (seconds, round the moment)
SLASH_BEFORE = 0.5  # the sword slash streaks across the picture this long before ...
SLASH_TIME = 0.12  # ... in this long ...
CRACK_TIME = 0.3  # ... the cracks then run out from it over this long
SHARDS = 46  # pieces the glass breaks into
SHARD_FLY = 0.9  # seconds they fly
# the cloth
CLOTH_FLY = 0.45  # seconds from her hand to the lens ...
CLOTH_SLIDE = 0.45  # ... and sliding down off the picture after the moment
CLOTH_STEPS = 8  # keys of its flight (its apparent size grows evenly while it rushes at the camera)
# the umbrella
UMBRELLA_IN = 0.55  # seconds it takes to come over the lens ...
UMBRELLA_OUT = 0.6  # ... and to lift away
UMBRELLA_RIBS = 16
UMBRELLA_TURNS = 0.5  # turns it spins while it is in the picture
# the fan
FAN_TURN = 1.8  # seconds a turn of the fan takes (three blades: one passes every 0.6 s) ...
FAN_BEFORE, FAN_AFTER = 1.0, 0.8  # ... shown this long before and after the moment
FAN_BLADES = 3
# the emoji
EMOJI_FACE = 0.16  # its size on the face, a share of the model height
EMOJI_ON, EMOJI_OFF = 0.5, 0.45  # seconds it is on her face before and after the moment
EMOJI_POP = (3, 4, 4)  # frames it pops up over all of her, holds and shrinks back
# the frame
FRAME_IN = 1.0  # seconds before the moment it stands up in front of her ...
CANVAS_WHITE = 0.25  # ... its canvas turning white over this long before it ...
FRAME_OUT = (0.35, 0.9)  # ... and after the moment it tilts and falls away between these times
FRAME_FEATHERS = 160
# the confetti
CANNON_FIRE = 0.35  # seconds before the moment the cannons fire ...
CONFETTI_COUNT = 1300
CANNON_SIZE = 0.2  # how long a cannon is (model heights)
CONFETTI_LIFE = 1.8  # ... and how long the streamers flutter
# the balloons
BALLOON_RISE = 0.5  # seconds before the moment they burst out ...
BALLOON_COUNT = 40
BALLOON_LIFE = 2.6  # ... and how long they are in the air
BALLOON_SIZE = 0.075  # a balloon's radius, a share of the model height
BALLOON_SPREAD = (0.42, 0.2, 0.5)  # how far the cloud spreads round where it burst out (her hips, in front of them):
# across, in depth, up and down (model heights)
BALLOON_UP = (0.22, 0.5)  # how fast they rise (model heights a second) and how much faster each second
# the feather fans
FAN_OPEN = (0.5, 0.12)  # seconds before the moment they open, and are open by ...
FAN_CLOSE = (0.3, 0.75)  # ... and after it they fold away between these times
FAN_RADIUS = 0.58  # a fan's radius, a share of the model height ...
FAN_AHEAD = 0.12  # ... held this far in front of her hand (model heights)
FAN_FEATHERS = 24
FAN_SPREAD = math.radians(80.0)  # how far an open fan spreads either side of its middle, which points at her chest
FAN_UP = 0.15  # ... turned this share of the way towards straight up
# the curtain
CURTAIN_DOWN = 0.35  # seconds it takes to come down in front of her ...
CURTAIN_HOLD = 0.1  # ... it holds this long after the moment ...
CURTAIN_DROP = 0.55  # ... then drops to the floor over this long ...
CURTAIN_GONE = 1.1  # ... and is gone this long after the moment
CURTAIN_AHEAD = 0.45  # it hangs this far in front of her (model heights)


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_COVER) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def remove(mask, kinds=None):
    for ob in objects(mask):
        if kinds is None or ob.get(P_KIND) in kinds:
            _delete(ob)
    if kinds is None and not any(ob.get(P_COVER) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_unused()
        for name in [m.name for m in bpy.data.materials if m.name.startswith(materials.COVER_MATERIAL)]:
            mat = bpy.data.materials.get(name)
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)


# --------------------------------------------------------------------------- the coverage check

def watch(scene, armature, frames, hidden=(), style="NONE", height=1.0):
    """What the camera sees of the dancer at `frames`, playing them (the bones only): (seen, points).

    `seen` (kept on the mask) has a row per frame: the box round her on the picture (x0, x1, y0, y1; padded), her head's
    and her chest's spot on the picture with their depth in front of the camera, the world positions of her head,
    chest, hips and palms, and the camera's world matrix then (camera_w: an orbiting camera is somewhere else at the
    moment than when the effect syncs). Picture units as sampling.project: x across (its width the aspect), y up (its height 1), 0 in
    the middle. `points` (not kept) are the picture spots (x, y arrays) of the ends of all her deform bones every frame.
    For the covers that hide only part of her (MOVABLE) `seen` also has how much of her the cover `style` would cover
    if the moment were at each frame ("cover"), worked out while that frame plays (the camera as it is then)."""
    from .model import ORIGIN_BONES

    bones = [pb for pb in armature.pose.bones if pb.bone.use_deform] or list(armature.pose.bones)
    head = motion.find_bone(armature, motion.HEAD)
    chest = motion.find_bone(armature, ORIGIN_BONES)
    hips = motion.find_bone(armature, motion.HIPS)
    seen = {key: [] for key in ("frames", "box", "head", "chest", "hips", "head_w", "chest_w", "hips_w", "palm_l",
                                "palm_r")}
    points = []
    nan3 = [float("nan")] * 3

    def at(pb, end="head"):
        return armature.matrix_world @ getattr(pb, end) if pb is not None else None

    def visit(i, frame, _positions):
        camera = sampling.camera_at(scene, frame)
        mw = armature.matrix_world
        ends = np.array([tuple(mw @ pb.head) for pb in bones] + [tuple(mw @ pb.tail) for pb in bones])
        top = at(head, "tail") if head is not None else at(chest, "tail")
        middle = at(chest)
        seen["frames"].append(float(frame))
        for key, p in (("head_w", top), ("chest_w", middle), ("hips_w", at(hips))):
            seen[key].extend(tuple(p) if p is not None else nan3)
        for side, key in (("L", "palm_l"), ("R", "palm_r")):
            wrist, finger = motion._hand(armature, side)
            if wrist is None:
                seen[key].extend(nan3)
                continue
            w = mw @ wrist.head
            f = mw @ finger.head if finger is not None else mw @ wrist.tail
            seen[key].extend(tuple(w + 0.6 * (f - w)))
        if camera is None:
            seen["box"].extend([float("nan")] * 4)
            for key in ("head", "chest", "hips"):
                seen[key].extend(nan3)
            seen.setdefault("camera_w", []).extend([float("nan")] * 16)
            points.append((np.zeros(0), np.zeros(0)))
            return
        seen.setdefault("camera_w", []).extend(float(v) for line in camera.matrix_world for v in line)
        x, y, ok = sampling.project(scene, camera, ends)
        x, y = x[ok], y[ok]
        points.append((x, y))
        if len(x):
            pad = PAD * max(float(x.max() - x.min()), float(y.max() - y.min())) + 0.01
            seen["box"].extend((float(x.min()) - pad, float(x.max()) + pad, float(y.min()) - pad,
                                float(y.max()) + pad))
        else:
            seen["box"].extend([float("nan")] * 4)
        inverse = camera.matrix_world.inverted()
        for key, p in (("head", top), ("chest", middle), ("hips", at(hips))):
            if p is None:
                seen[key].extend(nan3)
                continue
            px, py, pok = sampling.project(scene, camera, np.array([tuple(p)]))
            depth = -(inverse @ p).z
            seen[key].extend((float(px[0]), float(py[0]), float(depth)) if pok[0] else nan3)
        if style in MOVABLE:
            seen.setdefault("cover", []).append(coverage(style, seen, points, len(seen["frames"]) - 1, height, scene,
                                                         camera))

    motion.play(scene, armature, list(frames), hidden=hidden, visit=visit)
    seen["aspect"] = sampling.picture_aspect(scene)
    return seen, points


def row(seen, frame):
    """The row of `seen` nearest `frame` (a dict of tuples), None when nothing was seen."""
    frames = list(seen.get("frames", ())) if seen else []
    if not frames:
        return None
    i = int(np.argmin(np.abs(np.asarray(frames) - float(frame))))
    out = {"frame": frames[i]}
    for key, size in (("box", 4), ("head", 3), ("chest", 3), ("hips", 3), ("head_w", 3), ("chest_w", 3), ("hips_w", 3),
                      ("palm_l", 3), ("palm_r", 3), ("camera_w", 16)):
        values = list(seen.get(key, ()))
        out[key] = tuple(values[size * i:size * i + size]) if len(values) >= size * (i + 1) else (float("nan"),) * size
    return out


def _finite(values):
    return all(math.isfinite(v) for v in values)


class _AtMoment:
    """The camera as it was at the moment (its world matrix then, as watch saw it); its lens and picture as they are.
    The covers standing on the stage are placed for it."""

    def __init__(self, camera, matrix):
        self.camera, self.data, self.type, self.name = camera, camera.data, camera.type, camera.name
        self.matrix_world = matrix

    def calc_matrix_camera(self, *args, **kwargs):
        return self.camera.calc_matrix_camera(*args, **kwargs)


def at_moment(seen, frame, camera):
    """`camera` as watch saw it at `frame` (the nearest frame it played), or as it is now when it saw nothing."""
    here = row(seen, frame) if seen else None
    values = here.get("camera_w") if here else None
    if not values or not _finite(values):
        return camera
    return _AtMoment(camera, Matrix([values[0:4], values[4:8], values[8:12], values[12:16]]))


def _discs_cover(x, y, discs):
    """Share of the picture points (x, y) inside any of `discs` (cx, cy, r, lo, hi): within r of (cx, cy) and, when
    lo < hi, at an angle about it between lo and hi (a fan: a slice of a disc)."""
    if not len(x):
        return 0.0
    inside = np.zeros(len(x), dtype=bool)
    for cx, cy, r, lo, hi in discs:
        dx, dy = x - cx, y - cy
        near = dx * dx + dy * dy <= r * r
        if lo < hi:
            a = np.arctan2(dy, dx)
            mid = 0.5 * (lo + hi)
            off = np.abs((a - mid + math.pi) % (2.0 * math.pi) - math.pi)
            near &= off <= 0.5 * (hi - lo)
        inside |= near
    return float(inside.mean())


def balloon_points(count=BALLOON_COUNT, seed=11):
    """Each balloon's own numbers: (offset across, in depth, up: -1 .. 1 within the cloud's spread), how fast it rises
    (a share of BALLOON_UP), its sway's phase (0 .. 1). The same every build."""
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < count:
        p = rng.uniform(-1.0, 1.0, 3)
        if p @ p <= 1.0:
            out.append((tuple(float(v) for v in p), float(rng.uniform(0.75, 1.25)), float(rng.uniform())))
    return out


def balloon_launch(start, scene, camera, height):
    """Where the balloon cloud bursts out: in front of her hips (or her chest) at the row `start` of what was seen."""
    if start is None:
        return None
    for key in ("hips_w", "chest_w"):
        if _finite(start[key]):
            p = Vector(start[key])
            return p + _toward(scene, camera, p)[0] * (0.2 * height)
    return None


def balloon_offset(offset, toward, side, up):
    """A balloon's place in the cloud round where it burst out (model heights, world directions)."""
    across, depth, rise = offset
    return side * (BALLOON_SPREAD[0] * across) + toward * (BALLOON_SPREAD[1] * depth) + up * (BALLOON_SPREAD[2] * rise)


def balloon_at(launch, side, up, height, place, speed, phase, seconds):
    """World position of a balloon `seconds` after the cloud burst out from `launch` (the chest, a little in front of
    it), its `place` in the cloud (balloon_offset): it spreads out to there over the first quarter second, rises ever
    faster and sways (cover_nodes' balloons group draws the same)."""
    t = max(seconds, 0.0)
    spread = min(t / 0.25, 1.0)
    spread = 0.35 + 0.65 * spread * (2.0 - spread)
    lift = (BALLOON_UP[0] * t + 0.5 * BALLOON_UP[1] * t * t) * speed
    sway = 0.03 * math.sin(2.0 * math.pi * (0.7 * t + phase))
    return launch + place * (height * spread) + up * (height * lift) + side * (height * sway)


def _toward(scene, camera, point):
    """(toward the camera, its right, up), level, from `point` (world)."""
    to = camera.matrix_world.translation - point if camera is not None else Vector((0.0, -1.0, 0.0))
    to.z = 0.0
    to = to.normalized() if to.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    up = Vector((0.0, 0.0, 1.0))
    return to, (-to).cross(up), up


def coverage(style, seen, points, i, height, scene, camera):
    """How much of the dancer the cover `style` covers at row `i` of `seen` (its points), when the big moment is then:
    the balloons that burst out BALLOON_RISE before from her chest, the feather fans open on her hands. 1 for the full
    covers (they are fitted to cover all of her)."""
    if style not in MOVABLE:
        return 1.0
    frames = seen["frames"]
    x, y = points[i]
    if not len(x) or camera is None:
        return 0.0
    fps = scene.render.fps / scene.render.fps_base
    frame = frames[i]
    discs = []
    if style == "BALLOONS":
        start = row(seen, frame - BALLOON_RISE * fps)
        launch = balloon_launch(start, scene, camera, height)
        if launch is None:
            return 0.0
        toward, side, up = _toward(scene, camera, launch)
        centres = [balloon_at(launch, side, up, height, balloon_offset(offset, toward, side, up), speed, phase,
                              BALLOON_RISE) for offset, speed, phase in balloon_points()]
        cx, cy, ok = sampling.project(scene, camera, np.array([tuple(c) for c in centres]))
        rim = np.array([tuple(c + up * (BALLOON_SIZE * height)) for c in centres])
        _rx, ry, _ok = sampling.project(scene, camera, rim)
        discs = [(float(a), float(b), abs(float(r - b)) * 1.05, 0.0, 0.0)
                 for a, b, r, good in zip(cx, cy, ry, ok) if good]
    else:  # FEATHERS: a slice of a disc on each palm, opening up and out to its side
        here = row(seen, frame)
        for key in ("palm_l", "palm_r"):
            palm = here[key] if here is not None else None
            if palm is None or not _finite(palm):
                continue
            p = Vector(palm)
            toward, _side, up = _toward(scene, camera, p)
            pivot = p + toward * (FAN_AHEAD * height)
            px, py, ok = sampling.project(scene, camera, np.array([tuple(pivot), tuple(pivot + up * (FAN_RADIUS *
                                                                                                     height))]))
            if not ok.all():
                continue
            r = abs(float(py[1] - py[0]))
            mid = fan_mid((float(px[0]), float(py[0])), fan_aim(here))
            discs.append((float(px[0]), float(py[0]), r, mid - FAN_SPREAD, mid + FAN_SPREAD))
    return _discs_cover(x, y, discs)


def fan_aim(here):
    """Where on the picture the feather fans open towards: between her chest and her hips (or her chest)."""
    chest, hips = here["chest"], here.get("hips", (float("nan"),) * 3)
    if _finite(chest[:2]) and _finite(hips[:2]):
        return (0.5 * (chest[0] + hips[0]), 0.5 * (chest[1] + hips[1]))
    return chest


def fan_mid(palm, chest):
    """Which way a feather fan on the palm at `palm` (picture x, y) opens: at her chest (`chest`: its picture x, y),
    a little upwards; straight up when the hand is at her chest."""
    if chest is None or not _finite(chest[:2]):
        return 0.5 * math.pi
    dx, dy = chest[0] - palm[0], chest[1] - palm[1]
    if math.hypot(dx, dy) < 0.04:
        return 0.5 * math.pi
    a = math.atan2(dy, dx)
    # (turned a little towards straight up, so the fans spread over her rather than past her middle)
    turn = (0.5 * math.pi - a + math.pi) % (2.0 * math.pi) - math.pi
    return a + FAN_UP * turn


def best_frame(style, seen, planned, fps):
    """The frame within SEARCH of `planned` (a frame) the cover `style` covers the dancer most at (the nearest of the
    best, as watch worked it out), and how much it covers then; `planned` itself for the full covers."""
    covers = list(seen.get("cover", ()))
    if style not in MOVABLE or not covers:
        return planned, 1.0
    reach = SEARCH * fps
    best, best_cover = planned, -1.0
    for frame, c in zip(seen["frames"], covers):
        if abs(frame - planned) > reach + 1e-6:
            continue
        if c > best_cover + 0.02 or (abs(c - best_cover) <= 0.02 and abs(frame - planned) < abs(best - planned)):
            best, best_cover = frame, c
    return best, max(best_cover, 0.0)


def keep(mask, seen, moved):
    """What was seen (watch) and how far the moment moved, on the mask."""
    mask[P_SEEN] = {key: (list(value) if isinstance(value, (list, tuple)) else value) for key, value in seen.items()}
    mask[P_MOVED] = float(moved)


def seen_of(mask):
    rec = mask.get(P_SEEN) if mask is not None else None
    if rec is None:
        return None
    return rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)


# --------------------------------------------------------------------------- pieces

def _link(ob, mask, kind, collection, key=""):
    collection.objects.link(ob)
    ob[P_COVER] = mask
    ob[P_KIND] = kind
    ob[P_KEY] = key
    ob.hide_select = True
    if hasattr(ob, "visible_shadow"):
        ob.visible_shadow = False
    return ob


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


def _clear_keys(id_):
    ad = id_.animation_data
    if ad is not None and ad.action is not None:
        action = ad.action
        ad.action = None
        if action.users == 0:
            bpy.data.actions.remove(action)


def _key(id_, path, keys, index=-1, interpolation="LINEAR"):
    """Key `path` of `id_` at (frame, value) pairs (a vector value keys all of it, or its `index`)."""
    prop = path[2:-2] if path.startswith('["') else None
    for frame, value in keys:
        if prop is not None:
            if index >= 0:
                id_[prop][index] = value
            else:
                id_[prop] = value
        elif index >= 0:
            getattr(id_, path)[index] = value
        else:
            setattr(id_, path, value)
        id_.keyframe_insert(path, index=index, frame=frame)
    for fc in _curves(id_):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            for k in fc.keyframe_points:
                k.interpolation = interpolation
            fc.update()


def _shown(ob, first, last):
    """Shown (render and viewport) from frame `first` to `last` only."""
    for path in ("hide_render", "hide_viewport"):
        _key(ob, path, ((first - 1, True), (first, False), (last, False), (last + 1, True)),
             interpolation="CONSTANT")


def _drive_frame(id_, prop, expression="frame"):
    id_[prop] = 0.0
    path = '["%s"]' % prop
    id_.driver_remove(path)
    driver = id_.driver_add(path).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def _mesh(name, verts, faces, attrs=(), uv=None, smooth=False):
    """A mesh of `verts` and `faces` with point attributes `attrs` ((name, type, values)) and a UV map (per vertex),
    shaded smooth when `smooth`."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if smooth and len(me.polygons):
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    for attr_name, kind, values in attrs:
        attr = me.attributes.new(attr_name, kind, "POINT")
        flat = np.asarray(values, dtype=np.float32).ravel()
        attr.data.foreach_set("vector" if kind == "FLOAT_VECTOR" else "value", flat)
    if uv is not None:
        layer = me.uv_layers.new(name="UVMap")
        for loop in me.loops:
            layer.data[loop.index].uv = uv[loop.vertex_index]
    me.update()
    return me


def _piece(mask, kind, collection, key, make, parent=None):
    """Our object `kind`, made anew (make() -> data) when what it was made for (`key`) changed."""
    ob = next(iter(objects(mask, kind)), None)
    if ob is not None and (ob.get(P_KEY) != key or ob.parent != parent):
        _delete(ob)
        ob = None
    if ob is None:
        ob = _link(bpy.data.objects.new(NAME + " " + kind.title().replace("_", " "), make()), mask, kind, collection,
                   key)
        ob.parent = parent
    for c in list(ob.constraints):
        ob.constraints.remove(c)
    _clear_keys(ob)
    return ob


def _modifier(ob, group, values):
    mod = next((m for m in ob.modifiers if m.type == "NODES"), None)
    if mod is None:
        mod = ob.modifiers.new(NAME, "NODES")
    if mod.node_group != group:
        mod.node_group = group
    from .node_groups import input_identifiers

    ids = input_identifiers(group)
    for name, value in values.items():
        key = ids.get(name)
        if key is not None and value is not None:
            mod[key] = value
    ob.update_tag()
    return mod


def _plane(scene, camera, depth):
    """(centre, width, height) of the camera's picture `depth` in front of it, in its own space."""
    from .picture import _frame

    return _frame(scene, camera, depth)


def _to_camera(scene, camera, x, y, depth, aspect):
    """The camera-space point `depth` in front of the camera where the picture spot (x, y) is."""
    centre, width, height = _plane(scene, camera, depth)
    return Vector((centre.x + x / max(aspect, 1e-6) * width, centre.y + y * height, -depth))


def _near_depth(camera):
    from .picture import _near

    return _near(camera) * DEPTH


# --------------------------------------------------------------------------- the glass (打碎画面)

def _cells(seeds, lo, hi):
    """The Voronoi cells of 2D `seeds` within the box `lo` .. `hi` (each a list of corners, anticlockwise)."""
    out = []
    for i, s in enumerate(seeds):
        poly = [np.array((lo[0], lo[1])), np.array((hi[0], lo[1])), np.array((hi[0], hi[1])),
                np.array((lo[0], hi[1]))]
        for j, t in enumerate(seeds):
            if i == j or not poly:
                continue
            n = t - s
            c = 0.5 * float(n @ (s + t))  # keep n.p <= c (the side of s)
            new = []
            for k in range(len(poly)):
                a, b = poly[k], poly[(k + 1) % len(poly)]
                fa, fb = float(n @ a) - c, float(n @ b) - c
                if fa <= 0.0:
                    new.append(a)
                if (fa <= 0.0) != (fb <= 0.0):
                    new.append(a + (b - a) * (fa / (fa - fb)))
            poly = new
        out.append(poly)
    return out


def _glass_mesh(scene, camera, aspect, slash_point, slash_angle):
    """The glass in front of the camera, broken into SHARDS pieces (more along the sword slash), each a fan of
    triangles: mmdd_c its middle (camera space), mmdd_rim 0 there .. 1 at its edge (the cracks), mmdd_reveal when the
    crack reaches it (0 on the slash .. 1 furthest from it), mmdd_side which side of the slash it is on, mmdd_r its own
    random number, mmdd_pic where on the picture each point is (x, y)."""
    depth = _near_depth(camera)
    centre, width, height = _plane(scene, camera, depth)
    rng = np.random.default_rng(5)
    half = 0.5 * 1.08
    lo, hi = np.array((-half * aspect, -half)), np.array((half * aspect, half))
    d = np.array((math.cos(slash_angle), math.sin(slash_angle)))
    normal = np.array((-d[1], d[0]))
    seeds = []
    while len(seeds) < SHARDS:
        p = rng.uniform(lo, hi)
        off = abs(float((p - slash_point) @ normal))
        if rng.uniform() < math.exp(-off / 0.25) + 0.25:  # (denser along the slash)
            seeds.append(p)
    cells = _cells(seeds, lo, hi)
    reach = max(float(np.max(np.abs((np.array(seeds) - slash_point) @ normal))), 1e-6)
    verts, faces, cs, rims, reveals, sides, rnds, pics = [], [], [], [], [], [], [], []

    def to_cam(p):
        return (centre.x + p[0] / aspect * width, centre.y + p[1] * height, -depth)

    for s, poly in zip(seeds, cells):
        if len(poly) < 3:
            continue
        mid = np.mean(poly, axis=0)
        c = to_cam(mid)
        reveal = abs(float((mid - slash_point) @ normal)) / reach
        side = 1.0 if float((mid - slash_point) @ normal) >= 0.0 else -1.0
        r = float(rng.uniform())
        base = len(verts)
        for p, rim in [(mid, 0.0)] + [(p, 1.0) for p in poly]:
            verts.append(to_cam(p))
            cs.append(c)
            rims.append(rim)
            reveals.append(reveal)
            sides.append(side)
            rnds.append(r)
            pics.append((float(p[0]), float(p[1]), 0.0))
        n = len(poly)
        for k in range(n):
            faces.append((base, base + 1 + k, base + 1 + (k + 1) % n))
    return _mesh(NAME + " Glass", verts, faces,
                 (("mmdd_c", "FLOAT_VECTOR", cs), ("mmdd_rim", "FLOAT", rims), ("mmdd_reveal", "FLOAT", reveals),
                  ("mmdd_side", "FLOAT", sides), ("mmdd_r", "FLOAT", rnds), ("mmdd_pic", "FLOAT_VECTOR", pics)))


def _shatter(settings, mask, here, moment, camera, collection, fps, aspect):
    from . import cover_nodes

    m = float(moment)
    chest = here["chest"] if here is not None and _finite(here["chest"][:2]) else (0.0, 0.0, 1.0)
    # the slash: from the top left down to the bottom right through her chest
    angle = math.radians(-32.0)
    point = np.array((float(chest[0]), float(chest[1])))
    key = "%s:%d:%d:%.4f:%.3f:%.3f" % (camera.name, settings.id_data.render.resolution_x,
                                       settings.id_data.render.resolution_y, camera.data.clip_start, point[0],
                                       point[1])
    glass = _piece(mask, "GLASS", collection, key,
                   lambda: _glass_mesh(settings.id_data, camera, aspect, point, angle), parent=camera)
    if not glass.data.materials:
        glass.data.materials.append(materials.ensure_cover_material("GLASS"))
    glass["mmdd_color"] = tuple(settings.glow_color)
    glass["mmdd_slash"] = (float(point[0]), float(point[1]), angle)
    glass[materials.FRONT_ASPECT] = aspect
    s0 = m - SLASH_BEFORE * fps
    s1 = s0 + SLASH_TIME * fps
    c1 = s1 + CRACK_TIME * fps
    glass["mmdd_cover"] = (0.0, 0.0, 0.0)
    _key(glass, '["mmdd_cover"]', ((s0, 0.0), (s1, 1.0)), index=0)
    _key(glass, '["mmdd_cover"]', ((s1, 0.0), (c1, 1.0)), index=1)
    _key(glass, '["mmdd_cover"]', ((m - 3, 0.0), (m - 1, 1.0), (m + 1, 1.0), (m + 4, 0.0)), index=2)
    _shown(glass, int(math.floor(s0)), int(math.ceil(m + SHARD_FLY * fps)))
    _modifier(glass, cover_nodes.ensure_shatter_group(),
              {"Moment": m, "Rate": fps, "Slide": 0.012 * _plane(settings.id_data, camera, _near_depth(camera))[2],
               "Spread": 0.6, "Slash Angle": angle, "Material": materials.ensure_cover_material("GLASS")})
    return glass


# --------------------------------------------------------------------------- the cloth (飞布盖镜头)

def _grid(name, cols, rows, width, height, attrs=None, smooth=False):
    """A plane `width` x `height` in its XY plane round its middle, `cols` x `rows` quads, UVs 0 .. 1."""
    verts, uvs = [], []
    for j in range(rows + 1):
        for i in range(cols + 1):
            u, v = i / float(cols), j / float(rows)
            verts.append(((u - 0.5) * width, (v - 0.5) * height, 0.0))
            uvs.append((u, v))
    faces = [(j * (cols + 1) + i, j * (cols + 1) + i + 1, (j + 1) * (cols + 1) + i + 1, (j + 1) * (cols + 1) + i)
             for j in range(rows) for i in range(cols)]
    extra = [("mmdd_uv", "FLOAT_VECTOR", [(u, v, 0.0) for u, v in uvs])]
    return _mesh(name, verts, faces, tuple(extra) + tuple(attrs or ()), uv=uvs, smooth=smooth)


def _cloth(settings, mask, seen, moment, camera, collection, fps, aspect, height):
    from . import cover_nodes

    scene = settings.id_data
    m = float(moment)
    first = m - CLOTH_FLY * fps
    start = row(seen, first)
    depth_end = _near_depth(camera)
    _centre, w_end, h_end = _plane(scene, camera, depth_end)
    cloth = _piece(mask, "CLOTH", collection, "cloth:2", lambda: _grid(NAME + " Cloth", 44, 32, 1.0, 1.0, smooth=True),
                   parent=camera)
    if not cloth.data.materials:
        cloth.data.materials.append(materials.ensure_cover_material("CLOTH"))
    cloth["mmdd_color"] = tuple(settings.cover_color)
    inverse = camera.matrix_world.inverted()
    palm = None
    if start is not None:
        for key in ("palm_r", "palm_l"):
            if _finite(start[key]):
                palm = inverse @ Vector(start[key])
                break
    if palm is None or palm.z > -1e-3:
        palm = Vector((0.0, -0.1 * h_end, -10.0 * depth_end))
    depth0 = max(-palm.z, depth_end * 1.5)
    # (its apparent size on the picture: from a hand's width to just more than the picture, the cover's corners out of
    # it whichever way it turns)
    cover_w, cover_h = 1.35 * w_end / depth_end, 1.35 * h_end / depth_end
    size0 = 0.2 * height / depth0
    cloth.rotation_mode = "XYZ"
    steps = []
    for k in range(CLOTH_STEPS + 1):
        u = k / float(CLOTH_STEPS)
        eased = u * u * (3.0 - 2.0 * u)
        d = depth0 * (depth_end / depth0) ** u
        apparent = size0 + (cover_w - size0) * eased
        x = palm.x / depth0 * (1.0 - eased)
        y = palm.y / depth0 * (1.0 - eased)
        f = first + u * (m - 2.0 - first)
        # (its depth scaled as its width: the ripples are a share of its size; it unfolds as it flies, turning)
        unfold = 0.3 + 0.7 * eased
        steps.append((f, (x * d, y * d, -d), (apparent * d, apparent * d * unfold * cover_h / cover_w, apparent * d),
                      (math.radians(25.0) * (1.0 - eased), 0.0, math.radians(60.0) * (1.0 - eased))))
    full = (cover_w * depth_end, cover_h * depth_end, cover_w * depth_end)
    steps.append((m + 2.0, (0.0, 0.0, -depth_end), full, (0.0, 0.0, 0.0)))
    slide_end = m + 2.0 + CLOTH_SLIDE * fps
    steps.append((slide_end, (0.0, -1.6 * h_end, -depth_end), full, (0.0, 0.0, math.radians(-8.0))))
    _key(cloth, "location", [(f, loc) for f, loc, _s, _r in steps])
    _key(cloth, "scale", [(f, sc) for f, _l, sc, _r in steps])
    _key(cloth, "rotation_euler", [(f, rot) for f, _l, _s, rot in steps])
    _shown(cloth, int(math.floor(first)), int(math.ceil(slide_end)))
    _modifier(cloth, cover_nodes.ensure_ripple_group(),
              {"Moment": m, "Rate": fps, "Amount": 0.1, "Waves": 3.0, "Material":
               materials.ensure_cover_material("CLOTH")})
    return cloth


# --------------------------------------------------------------------------- the umbrella (雨伞花瓣)

def _umbrella_mesh(ribs=UMBRELLA_RIBS):
    """An umbrella's canopy seen from above (radius 1 round its tip, which points at +Z, the rim at z -0.38, dipping
    between the ribs), its ribs and a knob on top: mmdd_part 0 a panel (mmdd_panel which one), 1 a rib or the knob;
    mmdd_uv x round it (0 .. 1), y out from the tip (0 .. 1)."""
    rings = 10
    verts, faces, part, panel, uvs = [], [], [], [], []
    verts.append((0.0, 0.0, 0.0))
    part.append(0.0)
    panel.append(0.0)
    uvs.append((0.0, 0.0, 0.0))
    seg = ribs * 6
    for j in range(1, rings + 1):
        r = j / float(rings)
        for k in range(seg):
            a = 2.0 * math.pi * k / seg
            between = abs(math.sin(math.pi * (k % 6) / 6.0))  # 0 on a rib .. 1 mid-panel
            rr = r * (1.0 - 0.06 * between * r)
            z = -0.38 * r ** 1.6 - 0.05 * between * r * r
            verts.append((rr * math.cos(a), rr * math.sin(a), z))
            part.append(0.0)
            panel.append(float(k // 6))
            uvs.append((k / float(seg), r, 0.0))
    for k in range(seg):
        faces.append((0, 1 + k, 1 + (k + 1) % seg))
    for j in range(1, rings):
        a0, a1 = 1 + (j - 1) * seg, 1 + j * seg
        for k in range(seg):
            faces.append((a0 + k, a1 + k, a1 + (k + 1) % seg, a0 + (k + 1) % seg))
    # the ribs: thin raised strips on top of the canopy
    for rib in range(ribs):
        a = 2.0 * math.pi * rib / ribs
        c, s = math.cos(a), math.sin(a)
        nx, ny = -s * 0.012, c * 0.012
        base = len(verts)
        for j in range(rings + 1):
            r = j / float(rings)
            z = -0.38 * r ** 1.6 + 0.008
            verts += [(r * c + nx, r * s + ny, z), (r * c - nx, r * s - ny, z)]
            part += [1.0, 1.0]
            panel += [0.0, 0.0]
            uvs += [(rib / float(ribs), r, 0.0)] * 2
        for j in range(rings):
            faces.append((base + 2 * j, base + 2 * j + 1, base + 2 * j + 3, base + 2 * j + 2))
    # the knob on the tip
    base = len(verts)
    sides = 10
    for k in range(sides):
        a = 2.0 * math.pi * k / sides
        verts.append((0.035 * math.cos(a), 0.035 * math.sin(a), 0.01))
    verts.append((0.0, 0.0, 0.07))
    part += [1.0] * (sides + 1)
    panel += [0.0] * (sides + 1)
    uvs += [(0.0, 0.0, 0.0)] * (sides + 1)
    for k in range(sides):
        faces.append((base + k, base + (k + 1) % sides, base + sides))
    return _mesh(NAME + " Umbrella", verts, faces,
                 (("mmdd_part", "FLOAT", part), ("mmdd_panel", "FLOAT", panel), ("mmdd_uv", "FLOAT_VECTOR", uvs)))


def _umbrella(settings, mask, here, moment, camera, collection, fps, aspect, height):
    scene = settings.id_data
    m = float(moment)
    depth = _near_depth(camera) * 1.25
    _centre, width, tall = _plane(scene, camera, depth)
    reach = 0.5 * math.hypot(width, tall) * 1.15  # its rim past the picture's corners
    umbrella = _piece(mask, "UMBRELLA", collection, "umbrella", _umbrella_mesh, parent=camera)
    if not umbrella.data.materials:
        umbrella.data.materials.append(materials.ensure_cover_material("UMBRELLA"))
    umbrella["mmdd_color"] = tuple(settings.cover_color)
    umbrella.rotation_mode = "XYZ"
    a = m - UMBRELLA_IN * fps
    b = m + UMBRELLA_OUT * fps
    # in from the bottom right, tilted, over the lens at the moment (its top towards the camera), up and away to the
    # top left; spinning all the while
    _key(umbrella, "location", ((a, (0.9 * width, -0.8 * tall, -depth)), (m - 2, (0.0, 0.0, -depth)),
                                (m + 2, (0.0, 0.02 * tall, -depth)), (b, (-0.7 * width, 1.1 * tall, -depth))))
    spin = 2.0 * math.pi * UMBRELLA_TURNS
    _key(umbrella, "rotation_euler", ((a, (math.radians(-25.0), math.radians(20.0), 0.0)),
                                      (m, (0.0, 0.0, 0.6 * spin)),
                                      (b, (math.radians(30.0), math.radians(-15.0), spin))))
    _key(umbrella, "scale", ((a, (0.55 * reach,) * 3), (m - 2, (reach,) * 3), (m + 2, (reach,) * 3),
                             (b, (0.8 * reach,) * 3)))
    _shown(umbrella, int(math.floor(a)), int(math.ceil(b)))
    # the petals it sheds as it lifts away
    petals = _petals(settings, mask, collection, camera, m, b, depth, width, tall, fps)
    return umbrella, petals


def _petals(settings, mask, collection, camera, moment, until, depth, width, tall, fps):
    """Petals falling from the umbrella's rim from the moment on, in front of the camera."""
    from . import cover_nodes, particles

    rng = np.random.default_rng(3)
    count = 90
    pts, t0, vel, rnd, axis = [], [], [], [], []
    for k in range(count):
        a = rng.uniform(0.0, 2.0 * math.pi)
        r = rng.uniform(0.3, 0.6)
        pts.append((r * width * math.cos(a), r * tall * math.sin(a), -depth * rng.uniform(1.05, 1.4)))
        t0.append(moment + rng.uniform(0.0, 0.6) * (until - moment))
        vel.append((rng.uniform(-0.3, 0.3) * width / fps, rng.uniform(-0.1, 0.4) * tall / fps, 0.0))
        rnd.append(rng.uniform())
        axis.append(tuple(rng.normal(size=3)))
    me_key = "petals:%.4f:%.4f" % (width, tall)
    ob = _piece(mask, "PETALS", collection, me_key,
                lambda: _mesh(NAME + " Petals", pts, [], (("mmdd_t0", "FLOAT", t0), ("mmdd_v", "FLOAT_VECTOR", vel),
                                                          ("mmdd_r", "FLOAT", rnd),
                                                          ("mmdd_axis", "FLOAT_VECTOR", axis))),
                parent=camera)
    _drive_points_time(ob, moment)
    _modifier(ob, cover_nodes.ensure_pieces_group(),
              {"Instance": particles.ensure_asset("PETAL", settings.id_data), "Size": 0.05 * tall,
               "Gravity": (0.0, -0.6 * tall / (fps * fps), 0.0), "Drag": 0.04, "Flutter": 0.03 * tall,
               "Spin": 0.25, "Life": 1.6 * fps, "Material": materials.ensure_cover_material("PETALS")})
    ob["mmdd_color"] = tuple(settings.particle_color)
    ob["mmdd_glow"] = 0.3
    return ob


def _drive_points_time(ob, moment):
    """(The pieces' group reads the scene's frame; nothing to drive. Kept for the pieces' own fade.)"""
    ob["mmdd_moment"] = float(moment)


# --------------------------------------------------------------------------- the fan (风扇叶片)

def _blade_mesh(width, blades=FAN_BLADES):
    """The fan's blades round a hub at the origin in the XY plane: each a long rounded blade along its own direction,
    length 1 and `width` across at its widest; mmdd_uv x along (0 .. 1), y across (-1 .. 1); the hub (mmdd_part 1)."""
    verts, faces, uvs, part = [], [], [], []
    along, across = 24, 6
    for k in range(blades):
        a = 2.0 * math.pi * k / blades
        c, s = math.cos(a), math.sin(a)
        base = len(verts)
        for i in range(along + 1):
            u = i / float(along)
            # the blade widens from the hub and rounds off at its tip
            grow = 0.35 + 0.65 * math.sin(0.5 * math.pi * min(u * 1.15, 1.0))
            tip = math.sqrt(max(1.0 - max(u - 0.82, 0.0) / 0.18, 0.0))
            w = 0.5 * width * grow * tip
            for j in range(across + 1):
                v = -1.0 + 2.0 * j / across
                px, py = u, v * w
                verts.append((px * c - py * s, px * s + py * c, 0.002 * k))
                uvs.append((u, v, 0.0))
                part.append(0.0)
        for i in range(along):
            for j in range(across):
                q = base + i * (across + 1) + j
                faces.append((q, q + across + 1, q + across + 2, q + 1))
    base = len(verts)
    sides = 16
    for k in range(sides):
        a = 2.0 * math.pi * k / sides
        verts.append((0.06 * math.cos(a), 0.06 * math.sin(a), 0.01))
        uvs.append((0.0, 0.0, 0.0))
        part.append(1.0)
    verts.append((0.0, 0.0, 0.02))
    uvs.append((0.0, 0.0, 0.0))
    part.append(1.0)
    for k in range(sides):
        faces.append((base + k, base + (k + 1) % sides, base + sides))
    return _mesh(NAME + " Fan", verts, faces, (("mmdd_uv", "FLOAT_VECTOR", uvs), ("mmdd_part", "FLOAT", part)))


def _fan(settings, mask, here, moment, camera, collection, fps, aspect, cuts=()):
    """The fan's blades turning in front of the camera, a blade over the dancer at the moment (and at each of `cuts`,
    the outfit chain's: as near as the turning allows)."""
    scene = settings.id_data
    m = float(moment)
    depth = _near_depth(camera)
    centre, width, tall = _plane(scene, camera, depth)
    # the hub below the bottom left corner of the picture; the blades reach past the far corner
    hub = (-0.62 * aspect, -0.72)
    box = here["box"] if here is not None and _finite(here["box"]) else (-0.15, 0.15, -0.4, 0.4)
    her = (0.5 * (box[0] + box[1]), 0.5 * (box[2] + box[3]))
    toward_her = math.atan2(her[1] - hub[1], her[0] - hub[0])
    length = math.hypot(aspect + 0.62 * aspect, 1.72) * 1.05
    # wide enough to cover her where it crosses her: her box across the blade's direction (picture units)
    dirx, diry = math.cos(toward_her), math.sin(toward_her)
    corners = [(box[i], box[j]) for i in (0, 1) for j in (2, 3)]
    spread = [(-diry) * (cx - her[0]) + dirx * (cy - her[1]) for cx, cy in corners]
    blade_w = min(max(1.25 * (max(spread) - min(spread)), 0.45), 0.9)
    share = round(blade_w / length, 3)  # (the blade's width as a share of its length)
    fan = _piece(mask, "FAN", collection, "fan:%.3f" % share, lambda: _blade_mesh(share), parent=camera)
    if not fan.data.materials:
        fan.data.materials.append(materials.ensure_cover_material("FAN"))
    fan.location = Vector((centre.x + hub[0] / aspect * width, centre.y + hub[1] * tall, -depth))
    unit = tall  # a picture unit at that depth
    fan.scale = (length * unit, length * unit, 1.0)
    fan.rotation_mode = "XYZ"
    first, last = m - FAN_BEFORE * fps, m + FAN_AFTER * fps
    rate = -2.0 * math.pi / (FAN_TURN * fps)  # (turning clockwise: the blades sweep down over her from the top)
    _key(fan, "rotation_euler", ((first, (0.0, 0.0, toward_her + rate * (first - m))),
                                 (last, (0.0, 0.0, toward_her + rate * (last - m)))))
    _shown(fan, int(math.floor(first)), int(math.ceil(last)))
    return fan


# --------------------------------------------------------------------------- the emoji (emoji 遮脸)

def _emoji(settings, mask, seen, moment, camera, collection, fps, aspect, height, armature):
    scene = settings.id_data
    m = float(moment)
    here = row(seen, m)
    sheet = _piece(mask, "EMOJI", collection, "emoji",
                   lambda: _grid(NAME + " Emoji", 1, 1, 1.0, 1.0))
    if not sheet.data.materials:
        sheet.data.materials.append(materials.ensure_cover_material("EMOJI"))
    image = settings.cover_image.strip() if hasattr(settings, "cover_image") else ""
    materials.update_emoji_material(bpy.path.abspath(image) if image else "")
    head = motion.find_bone(armature, motion.HEAD) if armature is not None else None
    if head is not None:
        con = sheet.constraints.new("COPY_LOCATION")
        con.target = armature
        con.subtarget = head.name
        con.head_tail = 0.5
        con.use_offset = True
    track = sheet.constraints.new("TRACK_TO")
    track.target = camera
    track.track_axis = "TRACK_Z"
    track.up_axis = "UP_Y"
    # how big it must be over all of her: her box on the picture at the head's depth, and a little towards the camera
    depth = here["head"][2] if here is not None and _finite(here["head"]) else 10.0 * height
    box = here["box"] if here is not None and _finite(here["box"]) else (-0.2, 0.2, -0.5, 0.5)
    _c, _w, unit = _plane(scene, camera, max(depth, 1e-3))
    span = max((box[1] - box[0]), (box[3] - box[2])) * 1.12 * unit
    face = EMOJI_FACE * height
    toward = (camera.matrix_world.translation - Vector(here["head_w"])) if here is not None and _finite(
        here["head_w"]) else Vector((0.0, -1.0, 0.0))
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    ahead = toward * (0.06 * height)
    out = toward * (0.3 * height)
    up, hold, back = EMOJI_POP
    on, off = m - EMOJI_ON * fps, m + EMOJI_OFF * fps
    # (the location is an offset from the head: a little in front of the face, further when it covers all of her,
    # and down so its middle is hers)
    middle_drop = Vector((0.0, 0.0, 0.0))
    if here is not None and _finite(here["head"]) and _finite(here["box"]):
        drop = (here["head"][1] - 0.5 * (box[2] + box[3])) * unit
        middle_drop = Vector((0.0, 0.0, -drop))
    keys_loc = ((on, ahead), (m - up, ahead), (m - up + 2, out + middle_drop), (m + hold, out + middle_drop),
                (m + hold + back, ahead), (off, ahead))
    keys_size = ((on, 0.0), (on + 3, face), (m - up, face), (m - up + 2, span), (m + hold, span),
                 (m + hold + back, face), (off - 3, face), (off, 0.0))
    _key(sheet, "location", [(f, tuple(v)) for f, v in keys_loc])
    _key(sheet, "scale", [(f, (s, s, s)) for f, s in keys_size])
    _shown(sheet, int(math.floor(on)), int(math.ceil(off)))
    return sheet


# --------------------------------------------------------------------------- the gilded frame (画框爆羽)

def _frame_mesh(wide, tall, moulding):
    """A gilded picture frame round a `wide` x `tall` window in its XY plane (facing +Z), its moulding `moulding` wide:
    a bead, a hollow and scallops along the outside; mmdd_uv x round it (0 .. 1), y across the moulding (0 inside ..
    1 outside)."""
    verts, faces, uvs = [], [], []
    profile = ((0.0, 0.0), (0.12, 0.15), (0.3, 0.2), (0.47, 0.12), (0.65, 0.26), (0.88, 0.18), (1.0, 0.0))
    hw, hh = 0.5 * wide, 0.5 * tall
    # round the window's edge from corner to corner, each side from its first corner on
    sides = ((Vector((-hw, -hh, 0.0)), Vector((hw, -hh, 0.0)), Vector((0.0, -1.0, 0.0))),
             (Vector((hw, -hh, 0.0)), Vector((hw, hh, 0.0)), Vector((1.0, 0.0, 0.0))),
             (Vector((hw, hh, 0.0)), Vector((-hw, hh, 0.0)), Vector((0.0, 1.0, 0.0))),
             (Vector((-hw, hh, 0.0)), Vector((-hw, -hh, 0.0)), Vector((-1.0, 0.0, 0.0))))
    perimeter = 2.0 * (wide + tall)
    path = []
    for a, b, n in sides:
        count = max(int(round(240 * (b - a).length / perimeter)), 2)
        for i in range(count):
            # (at a corner the moulding goes out along the diagonal, so the sides meet in a mitre)
            out = Vector((math.copysign(1.0, a.x), math.copysign(1.0, a.y), 0.0)) if i == 0 else n
            path.append((a + (b - a) * (i / float(count)), out))
    steps = len(path)
    for k, (p0, out) in enumerate(path):
        scallop = 0.06 * (0.5 + 0.5 * math.cos(2.0 * math.pi * k * 48.0 / steps))
        for j, (w, z) in enumerate(profile):
            p = p0 + out * (moulding * (w + (scallop if j == len(profile) - 2 else 0.0)))
            verts.append((p.x, p.y, z * moulding))
            uvs.append((k / float(steps), j / float(len(profile) - 1), 0.0))
    n = len(profile)
    for k in range(steps):
        a0, a1 = k * n, ((k + 1) % steps) * n
        for j in range(n - 1):
            faces.append((a0 + j, a1 + j, a1 + j + 1, a0 + j + 1))
    return _mesh(NAME + " Frame", verts, faces, (("mmdd_uv", "FLOAT_VECTOR", uvs),), smooth=True)


def _frame(settings, mask, seen, moment, camera, collection, fps, aspect, height):
    from . import cover_nodes, particles

    scene = settings.id_data
    m = float(moment)
    here = row(seen, m)
    if here is None or not _finite(here["chest_w"]) or not _finite(here["box"]):
        return None
    chest = Vector(here["chest_w"])
    hips = Vector(here["hips_w"]) if _finite(here["hips_w"]) else chest
    toward, side, up = _toward(scene, camera, chest)
    stand = Vector((0.5 * (chest.x + hips.x), 0.5 * (chest.y + hips.y), 0.0)) + toward * (0.38 * height)
    depth = max(-(camera.matrix_world.inverted() @ stand).z, 1e-3)
    _c, picture_w, unit = _plane(scene, camera, depth)
    box = here["box"]
    moulding = 0.06 * height
    # round her (within the picture: wide spread arms may reach past it, out of the frame)
    wide = min((box[1] - box[0]) * 1.1 * unit, 0.96 * picture_w - 2.0 * moulding)
    tall = min((box[3] - box[2]) * 1.06 * unit, 0.96 * unit - 2.0 * moulding)
    # its middle where hers is on the picture (at the frame's depth), all of it kept within the picture
    half_x = (0.5 * wide + moulding) / max(unit, 1e-9)
    half_y = (0.5 * tall + moulding) / max(unit, 1e-9)
    mid_x = min(max(0.5 * (box[0] + box[1]), -0.5 * aspect + half_x), 0.5 * aspect - half_x)
    mid_y = min(max(0.5 * (box[2] + box[3]), -0.5 + half_y), 0.5 - half_y)
    target = camera.matrix_world @ _to_camera(scene, camera, mid_x, mid_y, depth, aspect)
    turn = Matrix((side, up, toward)).transposed().to_quaternion()
    key = "frame:%.3f:%.3f:%.3f" % (wide, tall, moulding)
    frame = _piece(mask, "FRAME", collection, key, lambda: _frame_mesh(wide, tall, moulding))
    if not frame.data.materials:
        frame.data.materials.append(materials.ensure_cover_material("FRAME"))
    frame.rotation_mode = "QUATERNION"
    first = m - FRAME_IN * fps
    o0, o1 = m + FRAME_OUT[0] * fps, m + FRAME_OUT[1] * fps
    fallen = target - up * (0.6 * tall) - toward * (0.05 * height)
    tilt = (turn @ Matrix.Rotation(math.radians(-70.0), 4, "X").to_quaternion())
    _key(frame, "location", ((first, target), (o0, target), (o1, fallen)))
    _key(frame, "rotation_quaternion", ((first, turn), (o0, turn), (o1, tilt)))
    # (it pops up in front of her; once it has fallen it lies a moment and shrinks away)
    gone = o1 + 0.5 * fps
    _key(frame, "scale", ((first, (0.0, 0.0, 0.0)), (first + 0.18 * fps, (1.06, 1.06, 1.06)),
                          (first + 0.3 * fps, (1.0, 1.0, 1.0)), (gone - 6.0, (1.0, 1.0, 1.0)), (gone, (0.0, 0.0, 0.0))))
    _shown(frame, int(math.floor(first)), int(math.ceil(gone)))
    # the canvas in it: clear, then paper white, bursting into feathers at the moment
    canvas = _piece(mask, "CANVAS", collection, "canvas", lambda: _grid(NAME + " Canvas", 1, 1, 1.0, 1.0))
    if not canvas.data.materials:
        canvas.data.materials.append(materials.ensure_cover_material("CANVAS"))
    canvas.rotation_mode = "QUATERNION"
    canvas.rotation_quaternion = turn
    canvas.location = target + toward * 0.001 * height
    canvas.scale = (wide, tall, 1.0)
    canvas["mmdd_fade"] = 0.0
    _key(canvas, '["mmdd_fade"]', ((m - CANVAS_WHITE * fps, 0.0), (m - 2.0, 1.0)))
    _shown(canvas, int(math.floor(m - CANVAS_WHITE * fps)), int(math.floor(m)))
    # the feathers: points over the canvas, flying out at the camera and to the sides from the moment on
    rng = np.random.default_rng(9)
    pts, t0, vel, rnd, axis = [], [], [], [], []
    for _k in range(FRAME_FEATHERS):
        u, v = rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)
        p = target + side * (u * wide) + up * (v * tall) + toward * (0.01 * height)
        pts.append(tuple(p))
        t0.append(m + rng.uniform(0.0, 2.0))
        out = side * (u * 1.6) + up * (v * 1.2 + 0.2) + toward * rng.uniform(0.6, 1.6)
        vel.append(tuple(out * (height * rng.uniform(0.9, 1.6) / fps)))
        rnd.append(rng.uniform())
        axis.append(tuple(rng.normal(size=3)))
    key = "feathers:%.3f:%.3f:%.3f:%.4f:%.4f" % (target.x, target.y, target.z, wide, tall)
    burst = _piece(mask, "FEATHERS_BURST", collection, key,
                   lambda: _mesh(NAME + " Feathers", pts, [], (("mmdd_t0", "FLOAT", t0),
                                                                ("mmdd_v", "FLOAT_VECTOR", vel),
                                                                ("mmdd_r", "FLOAT", rnd),
                                                                ("mmdd_axis", "FLOAT_VECTOR", axis))))
    burst["mmdd_color"] = (1.0, 0.98, 0.95)
    burst["mmdd_glow"] = 0.15
    _modifier(burst, cover_nodes.ensure_pieces_group(),
              {"Instance": particles.ensure_asset("FEATHER", scene), "Size": 0.07 * height,
               "Gravity": (0.0, 0.0, -0.35 * height / (fps * fps)), "Drag": 0.06, "Flutter": 0.04 * height,
               "Spin": 0.15, "Life": 2.2 * fps, "Material": materials.ensure_cover_material("PETALS")})
    return frame, canvas, burst


# --------------------------------------------------------------------------- the confetti (彩带炮)

def _cannon_mesh(sides=16):
    """A confetti cannon: a tube along +Z (length 1, radius 0.12) open at the top, on a little stand."""
    verts, faces = [], []
    for z, r in ((0.0, 0.14), (0.08, 0.14), (0.08, 0.1), (1.0, 0.12), (1.0, 0.105), (0.15, 0.09)):
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            verts.append((r * math.cos(a), r * math.sin(a), z))
    rings = 6
    for j in range(rings - 1):
        for k in range(sides):
            a0, a1 = j * sides, (j + 1) * sides
            faces.append((a0 + k, a0 + (k + 1) % sides, a1 + (k + 1) % sides, a1 + k))
    return _mesh(NAME + " Cannon", verts, faces, (("mmdd_part", "FLOAT", [1.0] * len(verts)),))


def _confetti(settings, mask, seen, moment, camera, collection, fps, aspect, height, floor):
    from . import cover_nodes

    scene = settings.id_data
    m = float(moment)
    here = row(seen, m)
    if here is None or not _finite(here["chest_w"]):
        return None
    chest = Vector(here["chest_w"])
    toward, side, up = _toward(scene, camera, chest)
    fire = m - CANNON_FIRE * fps
    aim = chest + toward * (0.3 * height) + up * (0.6 * height)  # (over her head: they rain down round her)
    rng = np.random.default_rng(13)
    pts, t0, vel, rnd, axis = [], [], [], [], []
    cannons = []
    for k, across in enumerate((-0.7, 0.7, -0.5, 0.5)):
        # on the floor at her sides, the inner pair a little nearer the camera
        base = Vector((chest.x, chest.y, floor)) + toward * ((0.1 if abs(across) > 0.6 else 0.4) * height) + \
            side * (across * height)
        way = (aim - base).normalized()
        cannons.append((base, way))
        for _i in range(CONFETTI_COUNT // 4):
            jitter = Vector(rng.normal(size=3)) * 0.22
            v = (way + jitter).normalized() * (height * rng.uniform(2.6, 4.2) / fps)
            pts.append(tuple(base + way * (CANNON_SIZE * height)))
            t0.append(fire + rng.uniform(0.0, 0.12) * fps + k * 0.03 * fps)
            vel.append(tuple(v))
            rnd.append(rng.uniform())
            axis.append(tuple(rng.normal(size=3)))
    key = "confetti:%.3f:%.3f:%.3f:%.3f" % (chest.x, chest.y, floor, fire)
    pieces = _piece(mask, "CONFETTI", collection, key,
                    lambda: _mesh(NAME + " Confetti", pts, [], (("mmdd_t0", "FLOAT", t0),
                                                                 ("mmdd_v", "FLOAT_VECTOR", vel),
                                                                 ("mmdd_r", "FLOAT", rnd),
                                                                 ("mmdd_axis", "FLOAT_VECTOR", axis))))
    pieces["mmdd_color"] = tuple(settings.cover_color)
    pieces["mmdd_glow"] = 0.25
    _modifier(pieces, cover_nodes.ensure_pieces_group(),
              {"Instance": cover_nodes.ensure_streamer_object(scene), "Size": 0.035 * height,
               "Gravity": (0.0, 0.0, -1.8 * height / (fps * fps)), "Drag": 0.06, "Flutter": 0.05 * height,
               "Spin": 0.35, "Life": CONFETTI_LIFE * fps, "Material": materials.ensure_cover_material("CONFETTI")})
    made = [pieces]
    for k, (base, way) in enumerate(cannons[:2] + cannons[2:]):
        cannon = _piece(mask, "CANNON_%d" % k, collection, "cannon", _cannon_mesh)
        if not cannon.data.materials:
            cannon.data.materials.append(materials.ensure_cover_material("CANNON"))
        cannon.rotation_mode = "QUATERNION"
        cannon.location = base
        cannon.rotation_quaternion = way.to_track_quat("Z", "Y")
        cannon.scale = (CANNON_SIZE * height,) * 3
        _shown(cannon, int(math.floor(fire - 1.5 * fps)), int(math.ceil(m + 2.0 * fps)))
        made.append(cannon)
    return made


# --------------------------------------------------------------------------- the balloons (气球放飞)

def _balloon_shape():
    """A balloon (radius 1 round its middle, a knot at the bottom) with its string hanging below: mmdd_part 0 the
    balloon, 1 the string."""
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=14, radius=1.0)
    for v in bm.verts:
        z = v.co.z
        squeeze = 1.0 - 0.18 * max(-z, 0.0) ** 2  # (narrower towards the knot)
        v.co.x *= squeeze
        v.co.y *= squeeze
        v.co.z = z * (1.12 if z > 0.0 else 1.18)
    me = bpy.data.meshes.new(NAME + " Balloon")
    bm.to_mesh(me)
    bm.free()
    count = len(me.vertices)
    verts = [tuple(v.co) for v in me.vertices]
    faces = [tuple(p.vertices) for p in me.polygons]
    bpy.data.meshes.remove(me)
    part = [0.0] * count
    # the knot and the string: a thin ribbon down from the bottom, wavy
    base = len(verts)
    steps = 16
    for i in range(steps + 1):
        t = i / float(steps)
        z = -1.18 - 0.08 - t * 3.0
        x = 0.12 * math.sin(6.0 * t)
        verts += [(x - 0.02, 0.0, z), (x + 0.02, 0.0, z)]
        part += [1.0, 1.0]
    for i in range(steps):
        a = base + 2 * i
        faces.append((a, a + 1, a + 3, a + 2))
    return _mesh(NAME + " Balloon", verts, faces, (("mmdd_part", "FLOAT", part),), smooth=True)


def _balloons(settings, mask, seen, moment, camera, collection, fps, height):
    from . import cover_nodes

    scene = settings.id_data
    m = float(moment)
    launch_frame = m - BALLOON_RISE * fps
    launch = balloon_launch(row(seen, launch_frame), scene, camera, height)
    if launch is None:
        return None
    toward, side, up = _toward(scene, camera, launch)
    pts, offs, speeds, phases, rnd = [], [], [], [], []
    rng = np.random.default_rng(17)
    for offset, speed, phase in balloon_points():
        pts.append(tuple(launch))
        offs.append(tuple(balloon_offset(offset, toward, side, up)))
        speeds.append(speed)
        phases.append(phase)
        rnd.append(rng.uniform())
    key = "balloons:%.3f:%.3f:%.3f:%.3f" % (launch.x, launch.y, launch.z, launch_frame)
    ob = _piece(mask, "BALLOONS", collection, key,
                lambda: _mesh(NAME + " Balloons", pts, [], (("mmdd_off", "FLOAT_VECTOR", offs),
                                                             ("mmdd_k", "FLOAT", speeds),
                                                             ("mmdd_phase", "FLOAT", phases),
                                                             ("mmdd_r", "FLOAT", rnd))))
    ob["mmdd_color"] = tuple(settings.cover_color)
    _modifier(ob, cover_nodes.ensure_balloons_group(),
              {"Start": launch_frame, "Rate": fps, "Height": height, "Size": BALLOON_SIZE * height,
               "Life": BALLOON_LIFE * fps, "Side": tuple(side), "Toward": tuple(toward),
               "Balloon": cover_nodes.ensure_balloon_object(scene),
               "Material": materials.ensure_cover_material("BALLOON")})
    return ob


# --------------------------------------------------------------------------- the feather fans (羽扇遮身)

def _feather_fans(settings, mask, seen, moment, camera, collection, fps, height, armature):
    from . import cover_nodes

    scene = settings.id_data
    m = float(moment)
    made = []
    for side_key, kind in (("L", "FAN_L"), ("R", "FAN_R")):
        wrist, _finger = motion._hand(armature, side_key) if armature is not None else (None, None)
        if wrist is None:
            continue
        ob = _piece(mask, kind, collection, "fan", lambda: _mesh(NAME + " Fan Feathers", [(0.0, 0.0, 0.0)], []))
        con = ob.constraints.new("COPY_LOCATION")
        con.target = armature
        con.subtarget = wrist.name
        con.head_tail = 0.0
        con.use_offset = True
        track = ob.constraints.new("TRACK_TO")
        track.target = camera
        track.track_axis = "TRACK_Z"
        track.up_axis = "UP_Y"
        here = row(seen, m)
        key = "palm_l" if side_key == "L" else "palm_r"
        palm = Vector(here[key]) if here is not None and _finite(here[key]) else None
        toward = _toward(scene, camera, palm if palm is not None else Vector((0.0, 0.0, 0.0)))[0]
        ob.location = toward * (FAN_AHEAD * height)  # (an offset from the wrist: in front of her)
        mid = 0.5 * math.pi
        if palm is not None:
            px, py, _ok = sampling.project(scene, camera, np.array([tuple(palm + toward * (FAN_AHEAD * height))]))
            mid = fan_mid((float(px[0]), float(py[0])), fan_aim(here))
        o0, o1 = m - FAN_OPEN[0] * fps, m - FAN_OPEN[1] * fps
        c0, c1 = m + FAN_CLOSE[0] * fps, m + FAN_CLOSE[1] * fps
        ob["mmdd_color"] = tuple(settings.cover_color)
        ob["mmdd_glow"] = 0.2
        ob["mmdd_size"] = FAN_RADIUS * height
        mod = _modifier(ob, cover_nodes.ensure_fan_feathers_group(),
                        {"Feather": cover_nodes.ensure_plume_object(scene), "Radius": FAN_RADIUS * height,
                         "Count": FAN_FEATHERS, "Spread": FAN_SPREAD, "Lean": mid - 0.5 * math.pi,
                         "Material": materials.ensure_cover_material("PLUMES")})
        _key_input(ob, mod, "Open", ((o0 - 0.3 * fps, 0.0), (o0, 0.15), (o1, 1.0), (c0, 1.0), (c1, 0.0)))
        _shown(ob, int(math.floor(o0 - 0.3 * fps)), int(math.ceil(c1)))
        made.append(ob)
    return made


def _key_input(ob, mod, name, keys, interpolation="LINEAR"):
    """Key the input `name` of the Geometry Nodes modifier `mod` of `ob` at (frame, value) pairs."""
    from .node_groups import input_identifiers

    ident = input_identifiers(mod.node_group).get(name)
    if ident is None:
        return
    path = 'modifiers["%s"]["%s"]' % (mod.name, ident)
    for frame, value in keys:
        mod[ident] = value
        ob.keyframe_insert(path, frame=frame)
    for fc in _curves(ob):
        if fc.data_path == path:
            for k in fc.keyframe_points:
                k.interpolation = interpolation
            fc.update()


# --------------------------------------------------------------------------- the curtain (落幕)

def _curtain(settings, mask, seen, moment, camera, collection, fps, aspect, height, floor):
    from . import cover_nodes

    scene = settings.id_data
    m = float(moment)
    here = row(seen, m)
    if here is None or not _finite(here["chest_w"]):
        return None
    chest = Vector(here["chest_w"])
    toward, side, up = _toward(scene, camera, chest)
    place = Vector((chest.x, chest.y, floor)) + toward * (CURTAIN_AHEAD * height)
    depth = max(-(camera.matrix_world.inverted() @ (place + up * (0.5 * height))).z, 1e-3)
    _c, _w, unit = _plane(scene, camera, depth)
    # as wide as all the places she is on the picture while it hangs, and a little more
    frames = list(seen.get("frames", ()))
    boxes = list(seen.get("box", ()))
    lo, hi = float("inf"), -float("inf")
    for i, f in enumerate(frames):
        if m - (CURTAIN_DOWN + 0.2) * fps <= f <= m + CURTAIN_HOLD * fps and len(boxes) >= 4 * (i + 1):
            x0, x1 = boxes[4 * i], boxes[4 * i + 1]
            if math.isfinite(x0) and math.isfinite(x1):
                lo, hi = min(lo, x0), max(hi, x1)
    if not math.isfinite(lo):
        lo, hi = -0.25, 0.25
    wide = max((hi - lo) * unit * 1.35, 0.8 * height)
    tall = 1.35 * height
    mid = camera.matrix_world @ _to_camera(scene, camera, 0.5 * (lo + hi), 0.0, depth, aspect)
    place = Vector((mid.x, mid.y, floor)) - toward * 0.0
    turn = Matrix((side, up, toward)).transposed().to_quaternion()
    key = "curtain:%.4f:%.4f" % (wide, tall)
    curtain = _piece(mask, "CURTAIN", collection, key,
                     lambda: _grid(NAME + " Curtain", 64, 36, 1.0, 1.0))
    if not curtain.data.materials:
        curtain.data.materials.append(materials.ensure_cover_material("CURTAIN"))
    curtain["mmdd_color"] = tuple(settings.cover_color)
    curtain.rotation_mode = "QUATERNION"
    curtain.rotation_quaternion = turn  # (its plane facing the camera, its middle half its height up)
    above = place + up * (tall + 1.6 * height)
    hung = place + up * (0.5 * tall)
    d0 = m - CURTAIN_DOWN * fps
    _key(curtain, "location", ((d0 - 1, above), (d0, above), (m - 0.12 * fps, hung)))
    curtain.scale = (wide, tall, wide)  # (its folds' depth a share of its width)
    gone = m + CURTAIN_GONE * fps
    curtain["mmdd_fade"] = 1.0
    _key(curtain, '["mmdd_fade"]', ((gone - 0.3 * fps, 1.0), (gone, 0.0)))
    _shown(curtain, int(math.floor(d0)), int(math.ceil(gone)))
    mod = _modifier(curtain, cover_nodes.ensure_curtain_group(),
                    {"Folds": 9.0, "Depth": 0.03, "Floor": -0.5, "Aspect": tall / max(wide, 1e-6),
                     "Material": materials.ensure_cover_material("CURTAIN")})
    h0 = m + CURTAIN_HOLD * fps
    steps = [(h0, 0.0)]
    for k in range(1, 7):
        u = k / 6.0
        steps.append((h0 + u * CURTAIN_DROP * fps, u * u))  # (falling: s = g t^2 / 2)
    _key_input(curtain, mod, "Drop", steps)
    return curtain


# --------------------------------------------------------------------------- the panel -> the scene

KINDS = {"SHATTER": ("GLASS",), "CLOTH": ("CLOTH",), "UMBRELLA": ("UMBRELLA", "PETALS"), "FAN": ("FAN",),
         "EMOJI": ("EMOJI",), "FRAME": ("FRAME", "CANVAS", "FEATHERS_BURST"),
         "CONFETTI": ("CONFETTI", "CANNON_0", "CANNON_1", "CANNON_2", "CANNON_3"), "BALLOONS": ("BALLOONS",),
         "FEATHERS": ("FAN_L", "FAN_R"), "CURTAIN": ("CURTAIN",),
         "SLOT": ("SLOT", "REEL_0", "REEL_1", "REEL_2", "LEVER", "COINS")}


def sync(settings, mask, models, moment):
    """The cover's pieces as the panel says, for the big moment at frame `moment`; all taken away without one."""
    style = getattr(settings, "cover_style", "NONE")
    scene = settings.id_data
    camera = shots.carrier(scene, mask) if mask is not None else None
    if style == "NONE" or moment is None or camera is None or camera.type != "CAMERA" or not models:
        if mask is not None:
            remove(mask)
        return
    keep_kinds = KINDS.get(style, ())
    for ob in objects(mask):
        if ob.get(P_KIND) not in keep_kinds:
            _delete(ob)
    seen = seen_of(mask) or {}
    fps = scene.render.fps / scene.render.fps_base
    height = max(settings.size_reference, 1e-3)
    aspect = sampling.picture_aspect(scene)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    here = row(seen, moment)
    stage = at_moment(seen, moment, camera)  # (the covers on the stage: for the camera as it is at the moment)
    armature = next((m.armature for m in models if m.armature is not None), None)
    from .model import rest_bounds

    floor = rest_bounds([ob for m in models for ob in m.meshes])[0].z
    if style == "SHATTER":
        _shatter(settings, mask, here, moment, camera, collection, fps, aspect)
    elif style == "CLOTH":
        _cloth(settings, mask, seen, moment, camera, collection, fps, aspect, height)
    elif style == "UMBRELLA":
        _umbrella(settings, mask, here, moment, camera, collection, fps, aspect, height)
    elif style == "FAN":
        _fan(settings, mask, here, moment, camera, collection, fps, aspect)
    elif style == "EMOJI":
        _emoji(settings, mask, seen, moment, camera, collection, fps, aspect, height, armature)
    elif style == "FRAME":
        _frame(settings, mask, seen, moment, stage, collection, fps, aspect, height)
    elif style == "CONFETTI":
        _confetti(settings, mask, seen, moment, stage, collection, fps, aspect, height, floor)
    elif style == "BALLOONS":
        _balloons(settings, mask, seen, moment, stage, collection, fps, height)
    elif style == "FEATHERS":
        _feather_fans(settings, mask, seen, moment, camera, collection, fps, height, armature)
    elif style == "CURTAIN":
        _curtain(settings, mask, seen, moment, stage, collection, fps, aspect, height, floor)
    elif style == "SLOT":
        from . import slot

        slot.place(settings, mask, seen, moment, stage, collection, fps, aspect, height, floor)
