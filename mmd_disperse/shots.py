"""Camera moves at the big moment (变身镜头): a whip pan, a roll, a zoom punch, a dolly zoom, an orbit round the dancer
(with the dance frozen: bullet time) or the cuts of a game's ultimate.

The scene camera's own animation is never touched. A camera of ours rides on it (Child Of: where it is when its own
transform is zero) and makes the whip, the roll, the punch and the dolly on its own keys; the orbit and the cuts have
cameras of their own. Timeline markers switch to ours just for the move and back to the scene camera (or the one the
scene's own markers pick then). The compositor smears the picture in the fast moves (Directional Blur on the frame).
"""

import math

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

from . import compositor

NAME = "MMD Disperse Camera"
PIVOT = "MMD Disperse Camera Pivot"
P_SHOT = "mmd_disperse_shot"  # on our cameras and the pivot: the mask of their effect
P_ROLE = "mmd_disperse_shot_role"  # ... RIDE (on the scene camera), ORBIT, PIVOT, LOW, EYES, WIDE (the cuts)
P_USER = "mmd_disperse_user_camera"  # on the mask: the scene camera the moves ride on and go back to
P_KEY = "mmd_disperse_shot_key"  # on the mask: the orbit and the cuts as they were set up (redone when it changes)
ZOOM = "mmdd_zoom"  # on the riding camera: its focal length as a share of the scene camera's (keyed)
MARKER = "MMD Disperse Shot"  # our timeline markers' names start with it
STYLES = ("WHIP", "ROLL", "PUNCH", "DOLLY", "ORBIT", "CUTS")
RIDING = ("WHIP", "ROLL", "PUNCH", "DOLLY")
SWING = 2.5  # how far a whip pan swings each way, in the picture's widths (between ...
SWING_RANGE = (math.radians(20.0), math.radians(75.0))  # ... these angles)
ROLL = math.radians(100.0)  # ... and a roll
PUNCH = 1.3  # how far a zoom punch zooms in (focal length)
BLUR = {"WHIP": 0.12, "ROLL": math.radians(35.0), "PUNCH": 0.25}  # the compositor's smear at the fastest
# The cuts (a game's ultimate): a low angle, the eyes close up, a wide shot from above at the moment; when each starts
# and ends as a share of the Move Time before (-) or after (+) the moment, and its focal lengths (it pushes in)
CUTS = (("LOW", -0.45, -0.25, (18.0, 22.0)), ("EYES", -0.25, 0.0, (50.0, 62.0)), ("WIDE", 0.0, 0.3, (30.0, 30.0)))
CENTER_BONES = ("センター", "center", "Center", "下半身", "lower body", "Hips", "hips", "J_Bip_C_Hips")
HEAD_BONES = ("頭", "head", "Head", "J_Bip_C_Head")


def shot_objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_SHOT) == mask]


def _ours(mask, role):
    return next((ob for ob in shot_objects(mask) if ob.get(P_ROLE) == role), None)


def user_camera(scene, mask):
    """The camera the moves ride on and switch back to: the one kept on the mask, else the scene camera when it is
    not one of ours."""
    cam = mask.get(P_USER) if mask is not None else None
    if isinstance(cam, bpy.types.Object) and cam.type == "CAMERA" and cam.name in bpy.data.objects:
        return cam
    cam = scene.camera
    if cam is not None and cam.type == "CAMERA" and cam.get(P_SHOT) is None:
        return cam
    return None


def carrier(scene, mask):
    """The camera a sheet in front of the picture (the speed lines) hangs on: the riding camera when there is one
    (it is the scene camera outside the moves), else the scene camera."""
    ride = _ours(mask, "RIDE") if mask is not None else None
    return ride or user_camera(scene, mask) or scene.camera


def _curves(ob):
    ad = ob.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return []
    curves = getattr(action, "fcurves", None)
    if curves is None:  # Blender 5.0+: the curves are kept per slot
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    return list(curves)


def _key(ob, path, keys, index=-1, interpolation="LINEAR"):
    """Key `path` of `ob` (or its `index`) at (frame, value) and set the keys' interpolation (Blender 3.6 run from the
    command line ignores the preference)."""
    for frame, value in keys:
        if index >= 0:
            getattr(ob, path)[index] = value
            ob.keyframe_insert(path, index=index, frame=frame)
        elif path.startswith('["'):
            ob[path[2:-2]] = value
            ob.keyframe_insert(path, frame=frame)
        else:
            setattr(ob, path, value)
            ob.keyframe_insert(path, frame=frame)
    for fc in _curves(ob):
        for k in fc.keyframe_points:
            k.interpolation = interpolation
        fc.update()


def _new_camera(name, source, collection, mask, role):
    data = source.data.copy()
    data.name = name
    if data.animation_data is not None:
        data.animation_data_clear()
    ob = bpy.data.objects.new(name, data)
    collection.objects.link(ob)
    ob[P_SHOT] = mask
    ob[P_ROLE] = role
    return ob


def _riding(mask, user, collection):
    """Our camera on the scene camera: Child Of with nothing in between, its focal length the scene camera's times
    ZOOM (so a camera whose zoom is animated keeps it)."""
    ob = _ours(mask, "RIDE")
    if ob is not None:
        return ob
    ob = _new_camera(NAME, user, collection, mask, "RIDE")
    con = ob.constraints.new("CHILD_OF")
    con.name = "MMD Disperse Ride"
    con.target = user
    con.inverse_matrix = Matrix.Identity(4)
    ob[ZOOM] = 1.0
    driver = ob.data.driver_add("lens").driver
    driver.type = "SCRIPTED"
    for name, id_type, target, path in (("lens", "CAMERA", user.data, "lens"), ("zoom", "OBJECT", ob, '["%s"]' % ZOOM)):
        var = driver.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = id_type
        var.targets[0].id = target
        var.targets[0].data_path = path
    driver.expression = "lens * zoom"
    return ob


def _clear_keys(ob):
    if ob.animation_data is not None:
        ob.animation_data_clear()


def _width_angle(scene, camera):
    """The angle across the picture of `camera` (its sensor fit and the render's shape)."""
    corners = camera.data.view_frame(scene=scene)
    if camera.data.type == "ORTHO":
        return math.radians(30.0)
    half = max(abs(c.x) for c in corners) / max(abs(corners[0].z), 1e-9)
    return 2.0 * math.atan(half)


def _swing(frame, before, after, angle):
    """Keys of a swing out to `angle` over `before` frames (faster and faster), a jump to -`angle` at `frame` and
    back to 0 over `after` frames (slower and slower)."""
    keys = [(frame - before + i, angle * (i / before) ** 2) for i in range(before)]
    keys.append((frame - 0.02, angle))
    keys += [(frame + j, -angle * (1.0 - j / after) ** 2) for j in range(after + 1)]
    return keys


def _ramp(frame, before, after, amount):
    """Driver expression on the frame: up to `amount` at `frame` over `before` frames, down over `after` (the
    compositor's smear, as fast as the move)."""
    return ("{a:.4f} * (clamp((frame - {s}) / {b}, 0, 1) * (frame < {f}) + clamp(1 - (frame - {f}) / {n}, 0, 1) * "
            "(frame >= {f}))").format(a=amount, s=frame - before, b=float(before), f=frame, n=float(after))


def _markers(scene):
    return [m for m in scene.timeline_markers if m.name.startswith(MARKER)]


def _camera_at(scene, frame):
    """The camera the scene's own markers pick at `frame` (None when it has none)."""
    picked, best, first, first_frame = None, None, None, None
    for m in scene.timeline_markers:
        if m.camera is None or m.name.startswith(MARKER):
            continue
        if m.frame <= frame and (best is None or m.frame > best):
            picked, best = m.camera, m.frame
        if first_frame is None or m.frame < first_frame:
            first, first_frame = m.camera, m.frame
    return picked or first


def _set_markers(scene, user, cuts):
    """Our markers: each of `cuts` (frame, camera), then back to the scene camera; before them the scene camera too
    when the scene has no markers of its own (the first marker's camera holds before it)."""
    for m in _markers(scene):
        scene.timeline_markers.remove(m)
    if not cuts:
        return
    own = any(m.camera is not None for m in scene.timeline_markers)
    first, last = cuts[0][0], cuts[-1][0]
    marks = list(cuts[:-1]) + [(last, _camera_at(scene, last) or user)]
    if not own:
        marks.insert(0, (first - 1, user))
    for i, (frame, camera) in enumerate(marks):
        m = scene.timeline_markers.new("%s %d" % (MARKER, i), frame=int(frame))
        m.camera = camera


def _orbit(scene, mask, user, collection, start, end, focus, angle):
    """The orbit: a camera on a pivot at the dancer, set where the scene camera is as it starts (no jump), the pivot
    turning `angle` about the up from `start` to `end`, eased in and out."""
    pivot = _ours(mask, "PIVOT")
    if pivot is None:
        pivot = bpy.data.objects.new(PIVOT, None)
        pivot.empty_display_type = "SPHERE"
        collection.objects.link(pivot)
        pivot[P_SHOT] = mask
        pivot[P_ROLE] = "PIVOT"
    cam = _ours(mask, "ORBIT") or _new_camera(NAME + " Orbit", user, collection, mask, "ORBIT")
    current = scene.frame_current
    scene.frame_set(int(start))
    seen, lens = user.matrix_world.copy(), user.data.lens
    scene.frame_set(current)
    _clear_keys(pivot)
    pivot.location = focus
    pivot.rotation_euler = (0.0, 0.0, 0.0)
    cam.parent = pivot
    cam.matrix_parent_inverse = Matrix.Translation(-focus)
    cam.matrix_basis = seen
    cam.data.lens = lens
    _key(pivot, "rotation_euler", ((start, 0.0), (end, angle)), index=2, interpolation="BEZIER")
    return cam


def _bone(armature, names):
    bones = armature.pose.bones if armature is not None else {}
    return next((bones[n] for n in names if n in bones), None)


def _follow(cam, armature, names, location_only):
    """Let `cam`, placed for the armature's rest pose, follow the bone of `names` from there (only its position with
    `location_only`): Child Of with the bone's rest matrix as the inverse. False without such a bone."""
    bone = _bone(armature, names)
    for con in [c for c in cam.constraints if c.name == "MMD Disperse Follow"]:
        cam.constraints.remove(con)
    if bone is None:
        return False
    con = cam.constraints.new("CHILD_OF")
    con.name = "MMD Disperse Follow"
    con.target = armature
    con.subtarget = bone.name
    rest = armature.matrix_world @ bone.bone.matrix_local
    if location_only:
        con.use_rotation_x = con.use_rotation_y = con.use_rotation_z = False
        con.use_scale_x = con.use_scale_y = con.use_scale_z = False
        rest = Matrix.Translation(rest.translation)
    con.inverse_matrix = rest.inverted()
    return True


def _aim(cam, spot, at):
    """`cam` at `spot`, looking at `at`, upright."""
    cam.matrix_basis = Matrix.Translation(spot) @ (at - spot).to_track_quat("-Z", "Y").to_matrix().to_4x4()


def _cuts(scene, mask, user, collection, armature, frame, length, focus, height):
    """The three cameras of the cuts placed round the dancer as the scene camera sees it at the moment, following the
    hips (the low and the wide shot) and the head (the eyes): (start frame, camera) of each."""
    fps = scene.render.fps / scene.render.fps_base
    current = scene.frame_current
    scene.frame_set(int(frame))
    seen = user.matrix_world.translation.copy()
    scene.frame_set(current)
    focus = Vector(focus)
    back = focus - seen
    back.z = 0.0
    back = back.normalized() if back.length > 1e-6 else Vector((0.0, 1.0, 0.0))
    side = back.cross(Vector((0.0, 0.0, 1.0)))
    up = Vector((0.0, 0.0, 1.0))
    floor = focus.z - 0.62 * height  # (the focus is the chest)
    eyes = None
    head = _bone(armature, HEAD_BONES)
    if head is not None:
        eyes = armature.matrix_world @ (head.bone.head_local + Vector((0.0, -0.8 * head.bone.length,
                                                                         0.8 * head.bone.length)))
    out = []
    for role, start, _end, lens in CUTS:
        cam = _ours(mask, role) or _new_camera("%s %s" % (NAME, role.title()), user, collection, mask, role)
        _clear_keys(cam)
        cam.data.sensor_fit = user.data.sensor_fit
        if role == "LOW":  # from the front, low, close: looking up at the dancer
            _aim(cam, focus - back * (0.75 * height) - up * (focus.z - floor - 0.12 * height) + side * (0.15 * height),
                 focus + up * (0.2 * height))
            _follow(cam, armature, CENTER_BONES, True)
        elif role == "EYES" and eyes is not None:  # the eyes close up, riding on the head
            _aim(cam, eyes - Vector((0.0, 0.2 * height, 0.0)), eyes)
            if not _follow(cam, armature, HEAD_BONES, False):
                _aim(cam, focus + up * (0.3 * height) - back * (0.25 * height), focus + up * (0.3 * height))
        elif role == "EYES":
            _aim(cam, focus + up * (0.3 * height) - back * (0.25 * height), focus + up * (0.3 * height))
        else:  # WIDE: high and a quarter round
            spot = focus + (-back * math.cos(0.6) + side * math.sin(0.6)) * (2.3 * height) + up * (0.45 * height)
            _aim(cam, spot, focus - up * (0.08 * height))
            _follow(cam, armature, CENTER_BONES, True)
        first = int(round(frame + start * length * fps))
        last = int(round(frame + _end * length * fps))
        _key(cam.data, "lens", ((first, lens[0]), (max(last, first + 1), lens[1])), interpolation="LINEAR")
        out.append((first, cam))
    return out


def sync(settings, mask, moment, focus, armature=None, height=1.0):
    """Set up the camera move of the panel round the big moment (frame `moment`) at `focus` (a world point, the
    chest): our cameras, their keys, the markers and the compositor's smear; or remove it when it is off."""
    scene = settings.id_data
    user = user_camera(scene, mask)
    if not settings.shot_enable or user is None or moment is None or focus is None:
        remove(mask, scene)
        return
    mask[P_USER] = user
    style = settings.shot_style
    fps = scene.render.fps / scene.render.fps_base
    frame = int(moment)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    keep = ("RIDE",) if style in RIDING else ("ORBIT", "PIVOT") if style == "ORBIT" else tuple(c[0] for c in CUTS)
    for ob in [o for o in shot_objects(mask) if o.get(P_ROLE) not in keep]:
        _delete(ob)
    blur, center = {}, (0.5, 0.5)
    if style in RIDING:
        ride = _riding(mask, user, collection)
        _clear_keys(ride)
        ride[ZOOM] = 1.0
        if style in ("WHIP", "ROLL"):
            before, after = max(int(round(0.12 * fps)), 2), max(int(round(0.18 * fps)), 3)
            # (a whip swings a few widths of the picture: the dancer is out of it for two or three frames)
            swing = min(max(SWING * _width_angle(scene, user), SWING_RANGE[0]), SWING_RANGE[1])
            _key(ride, "rotation_euler", _swing(frame, before, after, swing if style == "WHIP" else ROLL),
                 index=1 if style == "WHIP" else 2)
            blur["shift" if style == "WHIP" else "turn"] = _ramp(frame, before, after, BLUR[style])
            cuts = [(frame - before, ride), (frame + after + 1, None)]
        elif style == "PUNCH":
            before, after = max(int(round(0.07 * fps)), 2), max(int(round(0.15 * fps)), 3)
            _key(ride, '["%s"]' % ZOOM, [(frame - before, 1.0), (frame, PUNCH), (frame + 1, PUNCH),
                                          (frame + 1 + after, 1.0)])
            blur["zoom"] = _ramp(frame, before, after + 1, BLUR["PUNCH"])
            cuts = [(frame - before, ride), (frame + after + 2, None)]
        else:  # DOLLY: back away and zoom in just as much, so the dancer stays the same size and the world stretches
            half = max(int(round(0.5 * settings.shot_length * fps)), 4)
            away = (user.matrix_world.translation - Vector(focus)).length
            back = 0.8 * away
            keys = [(frame - half + i, back * math.sin(0.5 * math.pi * i / half) ** 2) for i in range(2 * half + 1)]
            _key(ride, "location", keys, index=2)
            _key(ride, '["%s"]' % ZOOM, [(f, (away + b) / max(away, 1e-6)) for f, b in keys])
            cuts = [(frame - half, ride), (frame + half + 1, None)]
        seen = world_to_camera_view(scene, user, Vector(focus))
        center = (min(max(seen.x, 0.0), 1.0), min(max(seen.y, 0.0), 1.0))
    elif style == "ORBIT":
        half = max(int(round(0.5 * settings.shot_length * fps)), 4)
        cam = _orbit(scene, mask, user, collection, frame - half, frame + half, Vector(focus),
                     math.radians(settings.shot_angle))
        cuts = [(frame - half, cam), (frame + half + 1, None)]
    elif style == "CUTS":
        cuts = _cuts(scene, mask, user, collection, armature, frame, settings.shot_length, focus, height)
        cuts.append((int(round(frame + CUTS[-1][2] * settings.shot_length * fps)) + 1, None))
    else:
        cuts = []
    _set_markers(scene, user, cuts)
    if blur:
        compositor.add_camera_blur(scene)
    compositor.update_camera_blur(scene, blur, center)


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        bpy.data.cameras.remove(data)


def remove(mask, scene=None):
    """Our cameras, the pivot and the markers go; the scene camera is the scene's again and the smear is off."""
    scenes = [scene] if scene is not None else list(bpy.data.scenes)
    user = user_camera(scenes[0], mask) if scenes else None
    for ob in shot_objects(mask):
        _delete(ob)
    for sc in scenes:
        if _markers(sc):
            for m in _markers(sc):
                sc.timeline_markers.remove(m)
            if user is not None and (sc.camera is None or sc.camera.name not in bpy.data.objects
                                     or sc.camera.get(P_SHOT) is not None):
                sc.camera = user
        compositor.update_camera_blur(sc, {})
    for key in (P_USER, P_KEY):
        if mask is not None and key in mask:
            del mask[key]
