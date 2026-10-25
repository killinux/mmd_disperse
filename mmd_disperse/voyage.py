"""Camera journeys at the big moment (1.17), two styles of the camera move (shots.py): out to the Earth (地球拉远,
EARTH) and into her eye (钻进瞳孔, PUPIL). A camera of ours, keyed frame by frame, starts where the scene camera is and
ends where it is (no jump either way); the timeline markers switch to it for the journey.

Out to the Earth: the camera rises over her, turning to look straight down, faster and faster: the stage falls away,
it bursts through a layer of clouds (a white-out: a sheet of cloud in front of the lens hides the jump in scale) and
out in space the whole Earth lies below it, a storm of cloud over the spot where she dances; there, at its farthest,
the outfits swap, and it dives back down through the clouds to her. The Earth is ours: a ball EARTH_SIZE model heights
in radius whose top is the floor under her, its clouds, the glow of its air and a sky of stars round all of it, lit by
their own light (a sun in their shaders) and shown only while the camera is above the clouds.

Into the pupil: the camera flies at her face and into the eye nearer to it, turning to look straight into it, the
focal length drawing out and the depth of field closing in, and a black iris closes over the picture from its edge to
the pupil; in the dark the outfits swap, and it comes back out the way it went in. Where the pupil is: the front of the
vertices weighted to the eye bone (the iris), moved with the eye bone every frame (the eyes may look about); the bones
are played once for the journey's frames and what they did is kept on the mask.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from . import materials, motion, sampling

NAME = "MMD Disperse Journey"
EARTH_SIZE = 4000.0  # the Earth's radius, in model heights
SINK = 0.5  # its top this far (model heights) under the floor (no fighting with the stage's own floor)
CLOUDS = 0.012  # the clouds this far over the ground, a share of the radius (the white-out as the camera goes through)
AIR = 0.025  # the glow of the air round it
STARS = 3.0  # the sky of stars round it, this many times as far as the camera gets from its middle
FILL = 0.8  # at its farthest the Earth fills this share of the picture's narrower side
UP = 0.5  # the share of the move time on the way up (the rest coming back down) ...
TOP = 0.12  # ... and the share of it hanging out there round the moment
ROLL = math.radians(25.0)  # the picture turns this far on the way up (and back on the way down)
WHITE = (3, 0, 3)  # the white-out: frames whitening before the clouds, all white either side, clearing after
PUPIL_IN = 0.55  # into the pupil: the share of the move time going in (the rest coming back out) ...
DARK = 0.07  # ... in the dark either side of the moment (seconds)
NEAR = 0.02  # how close the camera comes to the eye (model heights) ...
ZOOM = 2.0  # ... the focal length drawn out to this many times the scene camera's
APERTURE = 2.0  # the depth of field's f-stop close to the eye
EARTH_ROLES = ("EARTH_CAM", "EARTH", "CLOUDS", "AIR", "STARS", "WHITE")
PUPIL_ROLES = ("PUPIL_CAM", "IRIS")
P_EYES = "mmd_disperse_pupil"  # on the mask: the eyes as played for the journey (see _played)


def _smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def _span(u, a, b):
    """0 before `a`, 1 after `b`, eased in between."""
    return _smooth((u - a) / (b - a)) if b > a else float(u >= b)


def _look(forward, up):
    """The turn (quaternion) of a camera looking along `forward`, `up` towards the top of its picture."""
    f = forward.normalized()
    x = f.cross(up)
    if x.length < 1e-9:
        x = f.orthogonal()
    x.normalize()
    y = x.cross(f)
    return Matrix((x, y, -f)).transposed().to_quaternion()


def _turn(matrix):
    return matrix.to_3x3().normalized().to_quaternion()


def _part(mask, role, collection, make, parent=None):
    """Our object `role` of the journey (made with make() -> data the first time), lit by nothing of the scene and
    casting nothing."""
    from .shots import P_ROLE, P_SHOT, _ours

    ob = _ours(mask, role)
    if ob is None:
        ob = bpy.data.objects.new("%s %s" % (NAME, role.title().replace("_", " ")), make())
        collection.objects.link(ob)
        ob[P_SHOT] = mask
        ob[P_ROLE] = role
        ob.hide_select = True
        for flag in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission",
                     "visible_volume_scatter"):
            if hasattr(ob, flag):
                setattr(ob, flag, False)
    from .cover import _clear_keys

    _clear_keys(ob)
    for c in list(ob.constraints):
        ob.constraints.remove(c)
    ob.parent = parent
    ob.matrix_parent_inverse = Matrix.Identity(4)
    return ob


def _ball(name, material):
    """A sphere of radius 1, smooth (128 x 64), with `material`."""
    import bmesh

    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(material)
    me.update()
    return me


def _sheet(scene, camera, name, material):
    """A sheet over the whole picture of `camera` one unit in front of it (scaled by its depth: it stays over the
    picture), its UVs 0 .. 1 across it."""
    from .picture import _frame

    centre, width, height = _frame(scene, camera, 1.0)
    half_w, half_h = 0.55 * width, 0.55 * height
    me = bpy.data.meshes.new(name)
    me.from_pydata([(centre.x + sx * half_w, centre.y + sy * half_h, -1.0)
                    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))], [], [(0, 1, 2, 3)])
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        layer.data[loop.index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
    me.materials.append(material)
    me.update()
    return me


def _camera(mask, role, user, collection, title):
    """Our camera `role`, a copy of the scene camera's, keyed afresh: no shift (it looks where it is keyed to)."""
    from .shots import NAME as CAMERA, _new_camera, _ours
    from .cover import _clear_keys

    cam = _ours(mask, role) or _new_camera("%s %s" % (CAMERA, title), user, collection, mask, role)
    _clear_keys(cam)
    _clear_keys(cam.data)
    for c in list(cam.constraints):
        cam.constraints.remove(c)
    cam.parent = None
    cam.rotation_mode = "QUATERNION"
    data = cam.data
    data.lens = user.data.lens
    data.sensor_fit = user.data.sensor_fit
    data.shift_x = data.shift_y = 0.0
    data.clip_start, data.clip_end = user.data.clip_start, user.data.clip_end
    return cam


def _narrow_angle(scene, camera):
    """The angle across the narrower side of `camera`'s picture."""
    corners = camera.data.view_frame(scene=scene)
    depth = max(abs(corners[0].z), 1e-9)
    half_x = max(abs(c.x) for c in corners) / depth
    half_y = max(abs(c.y) for c in corners) / depth
    return 2.0 * math.atan(min(half_x, half_y))


def _keyed(id_, path, rows, index=-1, interpolation="LINEAR"):
    """Key `path` of `id_` at (frame, value) `rows`; a path into a part of it (dof.focus_distance) too."""
    from .cover import _curves, _key

    if "." not in path or path.startswith('["'):
        _key(id_, path, rows, index=index, interpolation=interpolation)
        return
    owner_path, attr = path.rsplit(".", 1)
    owner = id_.path_resolve(owner_path)
    for f, value in rows:
        setattr(owner, attr, value)
        id_.keyframe_insert(path, frame=f)
    for fc in _curves(id_):
        if fc.data_path == path:
            for k in fc.keyframe_points:
                k.interpolation = interpolation
            fc.update()


def _bump(f, at):
    """How white the clouds' sheet is at frame `f` for a crossing at frame `at` (WHITE: before, all white, after)."""
    before, hold, after = WHITE
    d = f - at
    if d < -before or d > after:
        return 0.0
    if -hold <= d <= hold:
        return 1.0
    if d < 0:
        return _smooth((d + before) / max(before - hold, 1))
    return 1.0 - _smooth((d - hold) / max(after - hold, 1))


# --------------------------------------------------------------------------- out to the Earth

def earth(scene, mask, user, collection, frame, length, focus, height):
    """The journey out to the Earth round the moment (frame `frame`), `length` seconds in all, over her (`focus`: her
    chest): our camera, the Earth's parts and the clouds' sheet, keyed. Its cuts."""
    fps = scene.render.fps / scene.render.fps_base
    total = max(length * fps, 16.0)
    up_n = max(int(round(UP * total)), 8)
    down_n = max(int(round((1.0 - UP) * total)), 8)
    hang = max(int(round(0.5 * TOP * total)), 1)
    moment = int(frame)
    first, last = moment - up_n, moment + down_n
    h = max(height, 1e-3)
    focus = Vector(focus)
    floor = focus.z - 0.62 * h  # (the focus is the chest)
    radius = EARTH_SIZE * h
    middle = Vector((focus.x, focus.y, floor - SINK * h - radius))
    cam = _camera(mask, "EARTH_CAM", user, collection, "Earth")
    cam.data.dof.use_dof = False
    top = radius * (1.0 / math.sin(0.5 * FILL * _narrow_angle(scene, cam)) - 1.0)  # how high it gets over the floor
    cloud = CLOUDS * radius
    clip0 = (user.data.clip_start, user.data.clip_end)

    def leg(f, start, end, at):
        """Where the camera is (position, turn, height over the floor) at frame `f` on the leg from `start` (the
        scene camera's end of it) to `end` (the top), `at` the scene camera's frame for its end."""
        here = sampling.matrix_at(user, f)
        anchor = sampling.matrix_at(user, at)
        u = (f - start) / float(end - start) if end != start else 1.0
        base = max(anchor.translation.z - floor, 0.3 * h)
        lift = math.exp(math.log(base) + (math.log(top) - math.log(base)) * _smooth(u)) - base
        w = _span(_smooth(u), 0.08, 0.35)  # (over her only once it is well above her head)
        spot = here.translation.copy()
        spot.x += (focus.x - spot.x) * w
        spot.y += (focus.y - spot.y) * w
        spot.z += lift
        away = Vector((focus.x - anchor.translation.x, focus.y - anchor.translation.y, 0.0))
        away = away.normalized() if away.length > 1e-6 else Vector((0.0, 1.0, 0.0))
        forward = focus - spot
        forward = forward.normalized() if forward.length > 1e-6 else Vector((0.0, 0.0, -1.0))
        fz = forward.z
        hint = Vector((0.0, 0.0, 1.0)) * (1.0 + fz) - away * fz if fz < 0.0 else Vector((0.0, 0.0, 1.0))
        q = _look(forward, hint) @ Quaternion(Vector((0.0, 0.0, 1.0)), ROLL * _span(u, 0.35, 1.0))
        q = _turn(here).slerp(q, _span(u, 0.0, 0.3))
        return spot, q, base + lift

    rows = []
    for f in range(first, moment - hang + 1):
        rows.append((f,) + leg(f, first, moment - hang, first))
    rising = leg(moment - hang, first, moment - hang, first)
    falling = leg(moment + hang, last, moment + hang, last)
    for f in range(moment - hang + 1, moment + hang):
        t = (f - (moment - hang)) / float(2 * hang)
        rows.append((f, rising[0].lerp(falling[0], t), rising[1].slerp(falling[1], t),
                     rising[2] + (falling[2] - rising[2]) * t))
    for f in range(moment + hang, last + 1):
        rows.append((f,) + leg(f, last, moment + hang, last))
    # through the clouds: the first frame above them on the way up, the last on the way down
    above = [f for f, _p, _q, a in rows if a >= cloud]
    up_at, down_at = (above[0], above[-1]) if above else (moment, moment)
    last_q = None
    spots, turns = [], []
    for f, p, q, _a in rows:
        if last_q is not None and q.dot(last_q) < 0.0:
            q = -q
        last_q = q
        spots.append((f, p))
        turns.append((f, q))
    _keyed(cam, "location", spots)
    _keyed(cam, "rotation_quaternion", turns)
    clips = []
    for f, _p, _q, a in rows:
        if up_at <= f <= down_at:
            clips.append((f, (max(0.25 * (a - cloud), clip0[0]), (STARS + 1.2) * (radius + SINK * h + top))))
        else:
            clips.append((f, clip0))
    _keyed(cam.data, "clip_start", [(f, c[0]) for f, c in clips], interpolation="CONSTANT")
    _keyed(cam.data, "clip_end", [(f, c[1]) for f, c in clips], interpolation="CONSTANT")
    # the Earth, its clouds and air, the stars: shown above the clouds only
    from .cover import _drive_frame, _shown

    parts = (("EARTH", radius, "EARTH"), ("CLOUDS", radius + SINK * h + cloud, "EARTH_CLOUDS"),
             ("AIR", (radius + SINK * h) * (1.0 + AIR), "EARTH_AIR"),
             ("STARS", STARS * (radius + SINK * h + top), "SPACE"))
    for role, size, kind in parts:
        ob = _part(mask, role, collection, lambda r=role, k=kind: _ball("%s %s" % (NAME, r.title()),
                                                                         materials.ensure_cover_material(k)))
        ob.location = middle
        ob.rotation_euler = (0.0, 0.0, 0.0)
        ob.scale = (size, size, size)
        _shown(ob, up_at, down_at)
    # the clouds' sheet in front of the lens, white as the camera goes through them
    sheet = _part(mask, "WHITE", collection,
                  lambda: _sheet(scene, cam, NAME + " White", materials.ensure_cover_material("CLOUD_SHEET")),
                  parent=cam)
    _drive_frame(sheet, "mmdd_drift", "frame * 0.08")
    whites, depths = [], []
    near = dict((f, c[0]) for f, c in clips)
    for f, _p, _q, _a in rows:
        whites.append((f, max(_bump(f, up_at), _bump(f, down_at))))
        d = 1.5 * near[f]
        depths.append((f, (d, d, d)))
    sheet["mmdd_white"] = 0.0
    _keyed(sheet, '["mmdd_white"]', whites)
    # (the clouds swell out from the middle as the camera flies through them, up or down)
    sheet["mmdd_zoom"] = 1.0
    _keyed(sheet, '["mmdd_zoom"]', [(f, min(max(math.exp(0.18 * (f - (up_at if abs(f - up_at) <= abs(f - down_at)
                                                                           else down_at))), 0.3), 3.5))
                                    for f, _p, _q, _a in rows])
    _keyed(sheet, "scale", depths, interpolation="CONSTANT")
    lit = [f for f, v in whites if v > 0.0]
    _shown(sheet, (lit[0] if lit else first), (lit[-1] if lit else first))
    return [(first, cam), (last + 1, None)]


# --------------------------------------------------------------------------- into the pupil

def _rest_pupils(armature, meshes, height):
    """[(bone name, the pupil in armature space)] for each eye at rest: the middle of the front of the vertices
    weighted to the eye bone (the iris); without them the front of whatever is in front of the bone; the eyes estimated
    from the head without eye bones."""
    mw = armature.matrix_world
    to_arm = mw.inverted()
    forward = (mw.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
    clouds = []
    for ob in meshes:
        if ob.type != "MESH" or not len(ob.data.vertices):
            continue
        co = np.empty(len(ob.data.vertices) * 3, dtype=np.float64)
        ob.data.vertices.foreach_get("co", co)
        m = np.array(ob.matrix_world, dtype=np.float64)
        clouds.append((ob, co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]))
    f = np.array(tuple(forward))
    out = []
    eyes = [next((n for n in names if n in armature.data.bones), None) for names in motion.EYES]
    if not any(eyes):
        head = next((n for n in motion.HEAD if n in armature.data.bones), None)
        if head is None:
            return []
        bone = armature.data.bones[head]
        middle = mw @ (bone.head_local + Vector((0.0, -0.8 * bone.length, 0.8 * bone.length)))
        side = (mw.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
        guesses = [(head, middle + side * (0.025 * height)), (head, middle - side * (0.025 * height))]
    else:
        guesses = [(n, mw @ armature.data.bones[n].head_local) for n in eyes if n is not None]
    for name, at in guesses:
        a = np.array(tuple(at))
        picked = []
        for ob, co in clouds:
            group = ob.vertex_groups.get(name) if name in [n for n in eyes if n] else None
            near = np.nonzero(np.linalg.norm(co - a, axis=1) < 0.06 * height)[0]
            if group is None or not len(near):
                continue
            verts = ob.data.vertices
            for i in near:
                if any(g.group == group.index and g.weight > 0.5 for g in verts[int(i)].groups):
                    picked.append(co[i])
        if picked:
            pts = np.array(picked)
            centre = pts.mean(axis=0)
            front = float((pts @ f).max())
            pupil = centre + f * (front - float(centre @ f))
        else:  # the front of what is in front of the bone, near its line
            best = None
            for _ob, co in clouds:
                rel = co - a
                along = rel @ f
                off = np.linalg.norm(rel - np.outer(along, f), axis=1)
                ok = (off < 0.015 * height) & (along > -0.02 * height) & (along < 0.08 * height)
                if ok.any():
                    top = float(along[ok].max())
                    best = top if best is None else max(best, top)
            pupil = a + f * (best if best is not None else 0.01 * height)
        out.append((name, to_arm @ Vector(tuple(pupil))))
    return out


def _played(scene, mask, armature, user, frames, eyes, hidden):
    """What the eyes and the scene camera did over `frames`: {"frames", "eye0", "eye1" (the pupils, world), "fwd0",
    "fwd1", "up0", "up1" (where each looks and its up), "cam" (the scene camera's world matrices, 16 a frame)}; played
    once and kept on the mask for these frames, eyes and dance."""
    ad = armature.animation_data
    action = ad.action.name if ad is not None and ad.action is not None else ""
    key = "%s:%s:%s:%d:%d:%s" % (armature.name, user.name, action, frames[0], frames[-1],
                                 ";".join("%s:%.5f:%.5f:%.5f" % ((n,) + tuple(p)) for n, p in eyes))
    kept = mask.get(P_EYES)
    if kept is not None and kept.get("key") == key:
        return {k: list(v) if not isinstance(v, str) else v for k, v in kept.items()}
    record = {"frames": [], "cam": []}
    for i in range(len(eyes)):
        record["eye%d" % i], record["fwd%d" % i], record["up%d" % i] = [], [], []
    bones = armature.pose.bones

    def visit(_i, f, _positions):
        mw = armature.matrix_world
        record["frames"].append(float(f))
        record["cam"].extend(float(v) for line in user.matrix_world for v in line)
        for i, (name, pupil) in enumerate(eyes):
            pb = bones.get(name)
            moved = mw @ (pb.matrix @ pb.bone.matrix_local.inverted()) if pb is not None else mw
            turn = moved.to_3x3()
            record["eye%d" % i].extend(tuple(moved @ pupil))
            record["fwd%d" % i].extend(tuple((turn @ Vector((0.0, -1.0, 0.0))).normalized()))
            record["up%d" % i].extend(tuple((turn @ Vector((0.0, 0.0, 1.0))).normalized()))

    motion.play(scene, armature, list(frames), hidden=hidden, visit=visit)
    record["key"] = key
    mask[P_EYES] = record
    return record


def pupil(scene, mask, user, collection, armature, frame, length, focus, height, hidden=(), meshes=()):
    """The journey into the pupil round the moment (frame `frame`), `length` seconds in all: our camera and the
    iris in front of it, keyed. Its cuts; none without a dancing model with a head."""
    if armature is None:
        return []
    h = max(height, 1e-3)
    eyes = _rest_pupils(armature, meshes, h)
    if not eyes:
        return []
    fps = scene.render.fps / scene.render.fps_base
    total = max(length * fps, 12.0)
    in_n = max(int(round(PUPIL_IN * total)), 6)
    out_n = max(int(round((1.0 - PUPIL_IN) * total)), 6)
    dark = max(int(round(DARK * fps)), 1)
    moment = int(frame)
    first, last = moment - in_n, moment + out_n
    record = _played(scene, mask, armature, user, range(first, last + 1), eyes, hidden)
    index = {int(round(f)): i for i, f in enumerate(record["frames"])}

    def at(key, f, size=3):
        i = index.get(f, 0)
        return record[key][size * i:size * i + size]

    def camera_at(f):
        values = at("cam", f, 16)
        return Matrix([values[0:4], values[4:8], values[8:12], values[12:16]])

    # the eye nearer the scene camera at the moment
    seen = camera_at(moment).translation
    which = min(range(len(eyes)), key=lambda i: (Vector(at("eye%d" % i, moment)) - seen).length)
    eye_key, fwd_key, up_key = "eye%d" % which, "fwd%d" % which, "up%d" % which
    cam = _camera(mask, "PUPIL_CAM", user, collection, "Pupil")
    data = cam.data
    data.clip_start = min(user.data.clip_start, 0.2 * NEAR * h)
    data.dof.use_dof = True
    data.dof.focus_object = None
    lens0 = user.data.lens

    def leg(f, start, end):
        """(position, turn, lens, distance to the eye, iris) at frame `f` on the leg from `start` (the scene camera's
        end) to `end` (at the eye)."""
        u = (f - start) / float(end - start) if end != start else 1.0
        here = camera_at(f)
        eye, ahead, up = Vector(at(eye_key, f)), Vector(at(fwd_key, f)), Vector(at(up_key, f))
        far = max((camera_at(start).translation - Vector(at(eye_key, start))).length, 2.0 * NEAR * h)
        reach = far * (NEAR * h / far) ** _smooth(u)
        back = here.translation - eye
        back = back.normalized() if back.length > 1e-6 else ahead
        swing = back.rotation_difference(ahead)
        direction = Quaternion().slerp(swing, _span(u, 0.0, 0.45)) @ back
        spot = eye + direction * reach
        q = _turn(here).slerp(_look(eye - spot, up), _span(u, 0.0, 0.3))
        return spot, q, lens0 * (1.0 + (ZOOM - 1.0) * _span(u, 0.5, 1.0)), reach, 1.0 - _span(u, 0.6, 1.0)

    rows = []
    for f in range(first, moment - dark + 1):
        rows.append((f,) + leg(f, first, moment - dark))
    for f in range(moment - dark + 1, moment + dark):  # (in the dark it stays at the eye, wherever her head goes)
        rows.append((f,) + leg(f, first, f)[:4] + (0.0,))
    for f in range(moment + dark, last + 1):
        rows.append((f,) + leg(f, last, moment + dark))
    last_q, turns = None, []
    for f, _p, q, _l, _r, _i in rows:
        if last_q is not None and q.dot(last_q) < 0.0:
            q = -q
        last_q = q
        turns.append((f, q))
    _keyed(cam, "location", [(f, p) for f, p, _q, _l, _r, _i in rows])
    _keyed(cam, "rotation_quaternion", turns)
    _keyed(data, "lens", [(f, lens) for f, _p, _q, lens, _r, _i in rows])
    _keyed(data, "dof.focus_distance", [(f, max(0.97 * r, data.clip_start * 1.5)) for f, _p, _q, _l, r, _i in rows])
    _keyed(data, "dof.aperture_fstop", [(f, 16.0 + (APERTURE - 16.0) * _span(1.0 - min(r / (0.5 * h), 1.0), 0.0, 0.9))
                                        for f, _p, _q, _l, r, _i in rows])
    # the iris: black closing in from the edge of the picture to the pupil, in the dark round the moment
    from .cover import _shown

    sheet = _part(mask, "IRIS", collection,
                  lambda: _sheet(scene, cam, NAME + " Iris", materials.ensure_cover_material("IRIS")), parent=cam)
    depth = 1.002 * data.clip_start  # (right at the near clip: nothing, not a lock of hair, in front of it)
    sheet.scale = (depth, depth, depth)
    from .picture import _frame

    _c, width, tall = _frame(scene, cam, 1.0)
    sheet["mmdd_aspect"] = width / max(tall, 1e-9)
    sheet["mmdd_iris"] = 1.0
    _keyed(sheet, '["mmdd_iris"]', [(f, iris) for f, _p, _q, _l, _r, iris in rows])
    _shown(sheet, first, last)
    return [(first, cam), (last + 1, None)]


def forget(mask):
    """Drop what the eyes did (kept on the mask)."""
    if mask is not None and P_EYES in mask:
        del mask[P_EYES]
