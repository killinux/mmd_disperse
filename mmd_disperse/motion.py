"""The dance itself: when and from where the transformation starts (a clap, a blown kiss, a salute, a toss of the head,
the back turned to the camera; 1.11: a squat, a jump, landing, a footfall, a hand thrown up to the sky, a finger heart,
a wink, a cord pulled on the chest), and where the hands sweep over the body (the hand path).

Short-video outfit changes are set off by a move of the dance (#拍手变装 "clap change", #飞吻变装 "kiss change" ...), and
Lynda Carter's Wonder Woman changed in the middle of a spin. The build looks for the move in the old model's motion,
from the transformation's start frame on, and moves the transformation there.

Only the armature is needed for the bones: while the frames play the meshes of both models are switched off in the
viewport, so nothing else is computed. The hand path needs the posed outfits too: their skinned vertices are read every
frame (our modifiers are not on them yet when it is worked out).
"""

import math

import numpy as np
from mathutils import Vector

from . import arrival
from .model import ORIGIN_BONES

TRIGGERS = ("NONE", "CLAP", "KISS", "SALUTE", "FLIP", "TURN", "SQUAT", "JUMP", "LAND", "STEP", "RAISE", "HEART",
            "WINK", "PULL")
# moves the front starts from (where they are made) ...
GESTURES = ("CLAP", "KISS", "SALUTE", "FLIP", "STEP", "RAISE", "HEART", "WINK", "PULL")
# ... and moves the big moment (the swap, or the middle of the wave) is put on
MOMENTS = ("TURN", "SQUAT", "JUMP", "LAND")
ANKLES = arrival.LIMB_BONES[2:4]
TOES = (("つま先ＩＫ.L", "左つま先ＩＫ", "つま先.L", "左つま先", "toe.L", "Toes_L", "LeftToeBase", "J_Bip_L_ToeBase"),
        ("つま先ＩＫ.R", "右つま先ＩＫ", "つま先.R", "右つま先", "toe.R", "Toes_R", "RightToeBase", "J_Bip_R_ToeBase"))
HIPS = ("センター", "center", "Center", "下半身", "lower body", "Hips", "hips", "J_Bip_C_Hips")
NECK = ("首", "neck", "Neck", "J_Bip_C_Neck")
THUMBS = (("親指２.L", "左親指２", "thumb2.L", "Thumb2_L", "LeftHandThumb3", "J_Bip_L_Thumb3"),
          ("親指２.R", "右親指２", "thumb2.R", "Thumb2_R", "RightHandThumb3", "J_Bip_R_Thumb3"))
INDEXES = (("人指３.L", "左人指３", "index3.L", "Index3_L", "LeftHandIndex3", "J_Bip_L_Index3"),
           ("人指３.R", "右人指３", "index3.R", "Index3_R", "RightHandIndex3", "J_Bip_R_Index3"))
WINKS = (("ウィンク", "ウインク", "wink", "Wink", "wink_l", "Wink_L", "ウィンク２", "ウインク２"),
         ("ウィンク右", "ウインク右", "wink_r", "Wink_R", "ｳｨﾝｸ２右", "ウィンク２右", "ウインク２右"))
WRISTS = arrival.LIMB_BONES[:2]
HEAD = ("頭", "head", "Head", "J_Bip_C_Head")
EYES = (("目.L", "左目", "eye.L", "Eye_L", "J_Adj_L_FaceEye"), ("目.R", "右目", "eye.R", "Eye_R", "J_Adj_R_FaceEye"))
FINGERS = (("中指１.L", "左中指１", "middle1.L", "MiddleFinger1_L", "J_Bip_L_Middle1"),
           ("中指１.R", "右中指１", "middle1.R", "MiddleFinger1_R", "J_Bip_R_Middle1"))
INDEX_ROOTS = (("人指１.L", "左人指１", "index1.L", "Index1_L", "LeftHandIndex1", "J_Bip_L_Index1"),
               ("人指１.R", "右人指１", "index1.R", "Index1_R", "RightHandIndex1", "J_Bip_R_Index1"))
MIDDLE_TIPS = (("中指３.L", "左中指３", "middle3.L", "MiddleFinger3_L", "LeftHandMiddle3", "J_Bip_L_Middle3"),
               ("中指３.R", "右中指３", "middle3.R", "MiddleFinger3_R", "RightHandMiddle3", "J_Bip_R_Middle3"))
SIDES = ("L", "R")
# Shares of the model height and seconds (tuned on 20 MMD dances):
CLAP_GAP = 0.06  # the palms closer than this ...
CLAP_RUSH = 0.1  # ... after coming together by this much within CLAP_TIME
CLAP_TIME = 0.4
MOUTH_DOWN = 0.035  # the mouth this far below the eyes ...
BROW_UP = 0.02  # ... the brow this far above them ...
FACE_FRONT = 0.015  # ... both this far in front of them (on the face)
LIPS_NEAR = 0.04  # the fingers (palm to fingertips) this close to the mouth, below the eyes by FACE_LOW ...
FACE_LOW = 0.015
KISS_AWAY = 0.15  # ... then the palm this much further from the mouth within KISS_TIME
KISS_TIME = 0.5
BROW_NEAR = 0.04  # the fingers at the brow, above the eyes ...
SALUTE_TIME = 0.15  # ... for this long; for both, the other hand no nearer the face than twice that
FLIP_SPEED = 350.0  # degrees a second the head tilts at against the body, at least, in a toss
BACK_TURNED = -0.5  # the body faces away from the camera at least this much (cosine)
REST_NEAR = 0.005  # hands this close to where they are in the rest pose: the motion has not started yet ...
SETTLE = 1.0  # ... and moves found within this many seconds after it leaves the rest pose do not count
SNAP = 0.3  # seconds: a move this close to a beat (with beat sync) is taken to be on it
SQUAT_DEPTH = 0.12  # the hips this far below where they stand (a share of the height): a squat
FLOOR_NEAR = 0.025  # a foot this close to its lowest is on the floor ...
JUMP_CLEAR = 0.035  # ... and both this far above it, in the air: a jump (for JUMP_TIME at least)
JUMP_TIME = 0.1
STEP_STILL = 0.5  # a foot on the floor moving slower than this (heights a second) has come down: a footfall ...
STEP_LIFT = 0.02  # ... once it was this far up since the last one
KICK_HIGH = 0.25  # a foot kicked up this high comes down within KICK_TIME: a landing (and the end of a jump)
KICK_TIME = 0.6
RAISE_UP = 0.08  # a wrist this far above the top of the head: a hand thrown up to the sky
HEART_PINCH = 0.015  # thumb and forefinger tips this close (the hand above the chest) for HEART_TIME ...
HEART_INDEX = 0.8  # ... the forefinger about straight past its knuckle (its tip this share of its length from it) ...
HEART_CURL = 0.5  # ... the middle finger curled into the palm (at most this share): not a fist, an OK sign, a claw
HEART_TIME = 0.2
PULL_NEAR = 0.07  # a palm this close to the chest or the neck ...
PULL_AWAY = 0.18  # ... then this much further from it within PULL_TIME (a cord pulled, a pin pulled out)
PULL_TIME = 0.3
WINK_SHUT = 0.6  # a wink morph past this


def find_bone(armature, names):
    bones = armature.pose.bones if armature is not None else {}
    return next((bones[n] for n in names if n in bones), None)


def rest_head(armature, names):
    """World rest position of the first of `names` the armature has (None without)."""
    bones = armature.data.bones if armature is not None else {}
    bone = next((bones[n] for n in names if n in bones), None)
    return armature.matrix_world @ bone.head_local if bone is not None else None


class Track:
    """World positions of the hands (palm, wrist, fingertip) and the eyes, which way the face is turned (up and front),
    the turn of the head and of the body, the body's facing and up, the camera and how far the hands are from the
    rest pose, one row per frame."""

    def __init__(self, frames):
        self.frames = np.asarray(frames, dtype=np.float64)
        count = len(frames)
        self.palm = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.wrist = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.tip = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.eyes = np.full((count, 3), np.nan)
        self.up = np.full((count, 3), np.nan)
        self.front = np.full((count, 3), np.nan)
        self.head_turn = np.full((count, 3, 3), np.nan)
        self.body_turn = np.full((count, 3, 3), np.nan)
        self.body_up = np.full((count, 3), np.nan)
        self.chest = np.full((count, 3), np.nan)
        self.facing = np.full((count, 3), np.nan)
        self.camera = np.full((count, 3), np.nan)
        self.from_rest = np.full(count, np.nan)  # how far the hands are from where they are in the rest pose
        # 1.11: the feet (ankles, toes), the hips, the neck, the thumb and forefinger tips, the winks (0 .. 1)
        self.ankle = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.toe = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.thumb = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.index = {side: np.full((count, 3), np.nan) for side in SIDES}
        self.hips = np.full((count, 3), np.nan)
        self.neck = np.full((count, 3), np.nan)
        self.wink = {side: np.zeros(count) for side in SIDES}
        # how straight the forefinger and the middle finger are: knuckle to tip as a share of the rest length
        self.stretch = {finger: {side: np.full(count, np.nan) for side in SIDES} for finger in ("index", "middle")}

    def mouth(self, height):
        return self.eyes - self.up * (MOUTH_DOWN * height) + self.front * (FACE_FRONT * height)

    def brow(self, height):
        return self.eyes + self.up * (BROW_UP * height) + self.front * (FACE_FRONT * height)


def rest_eyes(armature):
    """Armature-space rest position between the eyes: the eye bones, or about where they are from the head bone."""
    bones = armature.data.bones
    eyes = [next((bones[n] for n in names if n in bones), None) for names in EYES]
    if all(b is not None for b in eyes):
        return (eyes[0].head_local + eyes[1].head_local) / 2.0
    head = next((bones[n] for n in HEAD if n in bones), None)
    if head is None:
        return None
    reach = 0.8 * head.length
    return head.head_local + Vector((0.0, -reach, reach))


def _hand(armature, side):
    k = SIDES.index(side)
    return find_bone(armature, WRISTS[k]), find_bone(armature, FINGERS[k])


def _record(track, i, armature, camera, eyes):
    mw = armature.matrix_world
    turn = mw.to_3x3().normalized()
    for side in SIDES:
        wrist, finger = _hand(armature, side)
        if wrist is None:
            continue
        w = mw @ wrist.head
        away = (w - mw @ wrist.bone.head_local).length
        track.from_rest[i] = away if not np.isfinite(track.from_rest[i]) else max(track.from_rest[i], away)
        # the hand: from the wrist to about the fingertips (twice the way to the middle finger's root)
        f = mw @ finger.head if finger is not None else mw @ wrist.tail
        track.wrist[side][i] = w
        track.palm[side][i] = w + 0.6 * (f - w)
        track.tip[side][i] = w + 2.0 * (f - w)
    for k, side in enumerate(SIDES):
        for store, names, end in ((track.ankle, ANKLES[k], "head"), (track.toe, TOES[k], "head"),
                                  (track.thumb, THUMBS[k], "tail"), (track.index, INDEXES[k], "tail")):
            bone = find_bone(armature, names)
            if bone is not None:
                store[side][i] = mw @ getattr(bone, end)
        for finger, roots, tips in (("index", INDEX_ROOTS[k], INDEXES[k]), ("middle", FINGERS[k], MIDDLE_TIPS[k])):
            root, tip = find_bone(armature, roots), find_bone(armature, tips)
            rest = (tip.bone.tail_local - root.bone.head_local).length if root and tip else 0.0
            if rest > 1e-6:
                track.stretch[finger][side][i] = (tip.tail - root.head).length / rest
    for store, names in ((track.hips, HIPS), (track.neck, NECK)):
        bone = find_bone(armature, names)
        if bone is not None:
            store[i] = mw @ bone.head
    head = find_bone(armature, HEAD)
    if head is not None:
        track.head_turn[i] = np.array(turn @ head.matrix.to_3x3())
        if eyes is not None:
            # the face goes with the head: rest (armature space) -> posed -> world
            deform = mw @ head.matrix @ head.bone.matrix_local.inverted()
            track.eyes[i] = deform @ eyes
            spin = deform.to_3x3()
            track.up[i] = (spin @ Vector((0.0, 0.0, 1.0))).normalized()
            track.front[i] = (spin @ Vector((0.0, -1.0, 0.0))).normalized()
    body = find_bone(armature, ORIGIN_BONES)
    if body is not None:
        track.chest[i] = mw @ body.head
        track.body_turn[i] = np.array(turn @ body.matrix.to_3x3())
        # the body's facing: MMD models face -Y; turned as the bone has turned from its rest pose
        delta = body.matrix.to_3x3() @ body.bone.matrix_local.to_3x3().inverted()
        track.facing[i] = turn @ (delta @ Vector((0.0, -1.0, 0.0)))
        track.body_up[i] = (turn @ (delta @ Vector((0.0, 0.0, 1.0)))).normalized()
    if camera is not None:
        track.camera[i] = camera.matrix_world.translation


def play(scene, armature, frames, hidden=(), meshes=(), visit=None):
    """Play `frames` and record a Track of `armature`. The objects in `hidden` are switched off in the viewport
    meanwhile (nothing to compute for them). With `meshes`, `visit(i, frame, positions)` gets their skinned world
    positions every frame (they must stay on)."""
    track = Track(frames)
    eyes = rest_eyes(armature)
    current = scene.frame_current
    off = [ob for ob in hidden if not ob.hide_viewport and ob not in meshes]
    for ob in off:
        ob.hide_viewport = True
    try:
        for i, f in enumerate(frames):
            whole = int(math.floor(f))
            scene.frame_set(whole, subframe=float(f) - whole)  # (subframes: the dance ribbons are recorded twice a frame)
            _record(track, i, armature, scene.camera, eyes)
            if visit is not None:
                visit(i, f, [world_positions(ob) for ob in meshes])
    finally:
        for ob in off:
            ob.hide_viewport = False
        scene.frame_set(current)
    return track


def world_positions(ob):
    """Evaluated (skinned) vertex positions of a mesh in world space."""
    import bpy

    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        mw = np.array(ev.matrix_world, dtype=np.float64)
    finally:
        ev.to_mesh_clear()
    return co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]


def _distance(a, b):
    return np.linalg.norm(a - b, axis=1)


def _fingers(track, side, points):
    """Per frame: how close the fingers (palm to fingertips) of hand `side` come to `points`, and the nearest point."""
    a, b = track.palm[side], track.tip[side]
    ab = b - a
    t = np.clip(((points - a) * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-12), 0.0, 1.0)
    near = a + t[:, None] * ab
    return _distance(points, near), near


def _settled(track, height, fps):
    """Per frame: False while the motion is in the rest pose and for SETTLE seconds after it leaves it (motions often
    start in the rest pose and jump into the dance, which looks like a rush of the hands)."""
    at_rest = track.from_rest <= REST_NEAR * height
    settled = np.ones(len(at_rest), dtype=bool)
    if len(at_rest) and at_rest[0]:
        moving = np.nonzero(~at_rest)[0]
        settled[:moving[0] + int(round(SETTLE * fps)) if len(moving) else len(at_rest)] = False
    return settled & ~at_rest


def _clap(track, height, fps):
    """The palms come together fast: closer than CLAP_GAP, having closed in by CLAP_RUSH within CLAP_TIME."""
    gap = _distance(track.palm["L"], track.palm["R"])
    reach = max(1, int(round(CLAP_TIME * fps)))
    settled = _settled(track, height, fps)
    for i in range(1, len(gap) - 1):
        if not np.isfinite(gap[i]) or gap[i] > CLAP_GAP * height or not settled[max(0, i - reach):i + 1].all():
            continue
        if gap[i] > gap[i - 1] or gap[i] > gap[i + 1]:
            continue
        before = gap[max(0, i - reach):i]
        if before.size and np.nanmax(before) - gap[i] > CLAP_RUSH * height:
            return i, ("L", "R")
    return None


def _alone(track, side, points, near):
    """Per frame: the other hand's fingers are not within `near` of `points` (one hand at the face, not both)."""
    other = SIDES[1 - SIDES.index(side)]
    return ~(_fingers(track, other, points)[0] <= near)


def _kiss(track, height, fps):
    """A kiss blown: the fingers of one hand at the lips (below the eyes), then its palm KISS_AWAY further from the
    mouth within KISS_TIME."""
    reach = max(1, int(round(KISS_TIME * fps)))
    mouth = track.mouth(height)
    settled = _settled(track, height, fps)
    best = None
    for side in SIDES:
        near, spot = _fingers(track, side, mouth)
        low = ((spot - track.eyes) * track.up).sum(axis=1) < -FACE_LOW * height
        ok = (near <= LIPS_NEAR * height) & low & _alone(track, side, mouth, 2.0 * LIPS_NEAR * height) & settled
        palm = _distance(track.palm[side], mouth)
        for i in range(1, len(near) - 1):
            if not ok[i] or near[i] > near[i - 1] or near[i] > near[i + 1]:
                continue
            after = palm[i + 1:i + 1 + reach]
            if after.size and np.nanmax(after) - palm[i] > KISS_AWAY * height:
                if best is None or i < best[0]:
                    best = (i, (side,))
                break
    return best


def _salute(track, height, fps):
    """A salute: the fingers of one hand held at the brow, above the eyes, for SALUTE_TIME."""
    hold = max(2, int(round(SALUTE_TIME * fps)))
    brow = track.brow(height)
    settled = _settled(track, height, fps)
    best = None
    for side in SIDES:
        near, spot = _fingers(track, side, brow)
        above = ((spot - track.eyes) * track.up).sum(axis=1) > 0.0
        at = (near < BROW_NEAR * height) & above & _alone(track, side, brow, 2.0 * BROW_NEAR * height) & settled
        run = 0
        for i, close in enumerate(at):
            run = run + 1 if close else 0
            if run >= hold:
                start = i - hold + 1
                if best is None or start < best[0]:
                    best = (start, (side,))
                break
    return best


def head_tilt_speed(track, fps):
    """Per frame: degrees a second the head tilts at against the body (nodding, tipping to the side; turning it about
    the body's up, as dancers do in a spin, does not count)."""
    head, body, up = track.head_turn, track.body_turn, track.body_up
    speed = np.zeros(len(head))
    last = None
    for i in range(len(head)):
        if not (np.isfinite(head[i]).all() and np.isfinite(body[i]).all() and np.isfinite(up[i]).all()):
            last = None
            continue
        rel = body[i].T @ head[i]
        if last is not None:
            d = rel @ last.T
            angle = math.acos(min(1.0, max(-1.0, (np.trace(d) - 1.0) / 2.0)))
            axis = np.array((d[2, 1] - d[1, 2], d[0, 2] - d[2, 0], d[1, 0] - d[0, 1]))
            length = np.linalg.norm(axis)
            if angle > 1e-6 and length > 1e-9:
                local_up = body[i].T @ up[i]
                along = float(axis @ local_up) / (length * max(np.linalg.norm(local_up), 1e-9))
                speed[i] = math.degrees(angle) * fps * math.sqrt(max(0.0, 1.0 - along * along))
        last = rel
    return speed


def _flip(track, height, fps):
    speed = head_tilt_speed(track, fps)
    settled = _settled(track, height, fps)
    for i in range(1, len(speed) - 1):
        if not (settled[i - 1] and settled[i]):
            continue
        if speed[i] >= FLIP_SPEED and speed[i] >= speed[i - 1] and speed[i] >= speed[i + 1]:
            return i, ("HEAD",)
    return None


def facing_camera(track):
    """Per frame: how much the body faces the camera (1 straight at it, -1 its back to it), on the floor plane. With
    no camera the view is taken to be from the front of the scene (-Y)."""
    face = track.facing.copy()
    face[:, 2] = 0.0
    to_cam = track.camera - track.chest
    no_cam = ~np.isfinite(to_cam).all(axis=1)
    to_cam[no_cam] = (0.0, -1.0, 0.0)
    to_cam[:, 2] = 0.0
    lengths = np.linalg.norm(face, axis=1) * np.linalg.norm(to_cam, axis=1)
    return np.where(lengths > 1e-9, (face * to_cam).sum(axis=1) / np.maximum(lengths, 1e-9), 1.0)


def _turn(track):
    facing = facing_camera(track)
    away = np.nonzero(facing < BACK_TURNED)[0]
    if not len(away):
        return None
    start = away[0]
    end = start
    while end + 1 < len(facing) and facing[end + 1] < BACK_TURNED:
        end += 1
    return start + int(np.argmin(facing[start:end + 1])), ()


def read_winks(track, meshes):
    """Fill the track's winks from the shape key animation of `meshes` (the facial expressions of the dance: read off
    their curves, nothing evaluated): per frame the strongest wink morph of each eye."""
    for ob in meshes:
        keys = ob.data.shape_keys if ob.type == "MESH" and ob.data is not None else None
        ad = keys.animation_data if keys is not None else None
        action = ad.action if ad is not None else None
        if action is None:
            continue
        curves = getattr(action, "fcurves", None)
        if curves is None:  # Blender 5.0+
            from bpy_extras import anim_utils
            bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
            curves = bag.fcurves if bag is not None else []
        for fc in curves:
            path = fc.data_path
            if not path.startswith('key_blocks["') or not path.endswith('"].value'):
                continue
            name = path[len('key_blocks["'):-len('"].value')]
            for k, side in enumerate(SIDES):
                if name in WINKS[k]:
                    values = np.array([fc.evaluate(float(f)) for f in track.frames])
                    track.wink[side] = np.maximum(track.wink[side], values)
    return track


def _floor(track):
    """The lowest each foot gets (its ankle) over the track: where it stands on the floor."""
    return {side: np.nanmin(track.ankle[side][:, 2]) if np.isfinite(track.ankle[side][:, 2]).any() else np.nan
            for side in SIDES}


def _lift(track):
    """Per frame and foot: how far its ankle is above the floor."""
    low = _floor(track)
    return {side: track.ankle[side][:, 2] - low[side] for side in SIDES}


def _runs(flags):
    """(start, end) index pairs of the runs of True in `flags`."""
    runs, start = [], None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def _squat(track, height, fps):
    """The hips sink SQUAT_DEPTH below where they stand: the lowest point of the first such dip."""
    hips = track.hips[:, 2]
    if not np.isfinite(hips).any():
        return None
    stand = np.nanpercentile(hips, 80)  # (where they stand: a dance with many squats lowers the median)
    settled = _settled(track, height, fps)
    low = (hips < stand - SQUAT_DEPTH * height) & settled
    for start, end in _runs(low):
        return start + int(np.nanargmin(hips[start:end + 1])), ("HIPS",)
    return None


def _airborne(track, height, fps):
    """(start, end) of the runs of frames with both feet off the floor for JUMP_TIME at least."""
    lift = _lift(track)
    up = (lift["L"] > JUMP_CLEAR * height) & (lift["R"] > JUMP_CLEAR * height) & _settled(track, height, fps)
    least = max(1, int(round(JUMP_TIME * fps)))
    return [(a, b) for a, b in _runs(up) if b - a + 1 >= least]


def _jump(track, height, fps):
    """A jump: both feet in the air; its top (the hips highest)."""
    for start, end in _airborne(track, height, fps):
        hips = track.hips[start:end + 1, 2]
        top = int(np.nanargmax(hips)) if np.isfinite(hips).any() else (end - start) // 2
        return start + top, ("FEET",)
    return None


def _land(track, height, fps):
    """Landing: the first frame back on the floor after a jump, or a foot kicked KICK_HIGH up coming down within
    KICK_TIME."""
    best = None
    for _start, end in _airborne(track, height, fps):
        if end + 1 < len(track.frames):
            best = (end + 1, ("FEET",))
        break
    lift = _lift(track)
    settled = _settled(track, height, fps)
    reach = max(1, int(round(KICK_TIME * fps)))
    for side in SIDES:
        high = np.nonzero((lift[side] > KICK_HIGH * height) & settled)[0]
        if not len(high):
            continue
        i = high[0]
        down = np.nonzero(lift[side][i:i + reach] < FLOOR_NEAR * height)[0]
        if len(down) and (best is None or i + down[0] < best[0]):
            best = (i + down[0], ("FOOT_" + side,))
    return best


def footfalls(track, height, fps):
    """Every footfall of the track: (index, side, world position of the ankle on the floor). A foot comes down once
    it was STEP_LIFT up since its last footfall and is back near the floor, slow."""
    lift = _lift(track)
    settled = _settled(track, height, fps)
    steps = []
    for side in SIDES:
        a = track.ankle[side]
        if not np.isfinite(a).all(axis=1).any():
            continue
        speed = np.zeros(len(a))
        speed[1:] = np.linalg.norm(np.diff(a, axis=0), axis=1) * fps
        lifted = False  # (a foot standing when the dance starts has not come down: it must be lifted first)
        for i in range(len(a)):
            if not np.isfinite(lift[side][i]):
                continue
            if lift[side][i] > STEP_LIFT * height and settled[i]:  # (not while it leaves the rest pose)
                lifted = True
            elif lifted and settled[i] and lift[side][i] < FLOOR_NEAR * height and speed[i] < STEP_STILL * height:
                steps.append((i, side, a[i].copy()))
                lifted = False
    return sorted(steps, key=lambda step: step[0])


def _step(track, height, fps):
    steps = footfalls(track, height, fps)
    return (steps[0][0], ("FOOT_" + steps[0][1],)) if steps else None


def _raise(track, height, fps):
    """A hand thrown up to the sky: its wrist RAISE_UP above the top of the head, at its highest."""
    top = track.eyes[:, 2] + 0.08 * height  # (about the top of the head)
    settled = _settled(track, height, fps)
    best = None
    for side in SIDES:
        over = track.wrist[side][:, 2] - top
        for start, end in _runs((over > RAISE_UP * height) & settled):
            peak = start + int(np.nanargmax(over[start:end + 1]))
            if best is None or peak < best[0]:
                best = (peak, (side,))
            break
    return best


def _heart(track, height, fps):
    """A finger heart: the thumb and forefinger tips of a hand crossed above the chest, the forefinger about straight,
    the other fingers curled (or both hands making one: the forefinger tips together and the thumb tips together), for
    HEART_TIME. (Over 20 dances fists, claws, thumbs up and OK signs had the tips as close: the fingers tell them
    apart.)"""
    hold = max(2, int(round(HEART_TIME * fps)))
    settled = _settled(track, height, fps)
    raised = {side: track.wrist[side][:, 2] > track.chest[:, 2] for side in SIDES}
    held = {side: (_distance(track.thumb[side], track.index[side]) < HEART_PINCH * height)
            & (track.stretch["index"][side] > HEART_INDEX) & (track.stretch["middle"][side] < HEART_CURL)
            & raised[side] & settled for side in SIDES}
    held["BOTH"] = ((_distance(track.index["L"], track.index["R"]) < 2.0 * HEART_PINCH * height)
                    & (_distance(track.thumb["L"], track.thumb["R"]) < 2.0 * HEART_PINCH * height)
                    & (_distance(track.wrist["L"], track.wrist["R"]) > 0.06 * height)
                    & raised["L"] & raised["R"] & settled)
    best = None
    for key, flags in held.items():
        for start, end in _runs(flags):
            if end - start + 1 >= hold:
                parts = ("L", "R") if key == "BOTH" else (key,)
                if best is None or start < best[0]:
                    best = (start, parts)
                break
    return best


def _wink(track):
    best = None
    for side in SIDES:
        shut = np.nonzero(track.wink[side] > WINK_SHUT)[0]
        if len(shut) and (best is None or shut[0] < best[0]):
            best = (int(shut[0]), ("EYE_" + side,))
    return best


def _pull(track, height, fps):
    """A cord pulled (Chainsaw Man): one palm at the chest or the neck, then PULL_AWAY further from it within
    PULL_TIME, the other hand not there."""
    reach = max(1, int(round(PULL_TIME * fps)))
    settled = _settled(track, height, fps)
    best = None
    for side in SIDES:
        palm = track.palm[side]
        # nearest point on the line from the chest to the neck
        a, b = track.chest, track.neck
        ab = b - a
        t = np.clip(((palm - a) * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-12), 0.0, 1.0)
        spot = a + t[:, None] * ab
        near = _distance(palm, spot)
        other = SIDES[1 - SIDES.index(side)]
        alone = ~(_distance(track.palm[other], spot) < 2.0 * PULL_NEAR * height)
        ok = (near < PULL_NEAR * height) & alone & settled
        for i in range(1, len(near) - 1):
            if not ok[i] or near[i] > near[i - 1] or near[i] > near[i + 1]:
                continue
            after = _distance(palm[i + 1:i + 1 + reach], spot[i])
            if after.size and np.nanmax(after) - near[i] > PULL_AWAY * height:
                if best is None or i < best[0]:
                    best = (i, (side,))
                break
    return best


def find(track, kind, height, fps):
    """(index into the track's frames, what it starts from: hand sides "L" / "R", "HEAD", "HIPS", "FEET", "FOOT_L" /
    "FOOT_R" or "EYE_L" / "EYE_R") of the first `kind` of move in the track, None when there is none."""
    if kind == "SQUAT":
        return _squat(track, height, fps)
    if kind == "JUMP":
        return _jump(track, height, fps)
    if kind == "LAND":
        return _land(track, height, fps)
    if kind == "STEP":
        return _step(track, height, fps)
    if kind == "RAISE":
        return _raise(track, height, fps)
    if kind == "HEART":
        return _heart(track, height, fps)
    if kind == "WINK":
        return _wink(track)
    if kind == "PULL":
        return _pull(track, height, fps)
    if kind == "CLAP":
        return _clap(track, height, fps)
    if kind == "KISS":
        return _kiss(track, height, fps)
    if kind == "SALUTE":
        return _salute(track, height, fps)
    if kind == "FLIP":
        return _flip(track, height, fps)
    if kind == "TURN":
        return _turn(track)
    return None


def start_points(armature, parts):
    """Rest-pose world positions (and bone names) the front starts from for the found move's parts."""
    points, names = [], []
    for part in parts:
        if part == "HEAD":
            choices = [HEAD]
        elif part == "HIPS":
            choices = [HIPS]
        elif part == "FEET":
            choices = list(ANKLES)
        elif part.startswith("FOOT_"):
            choices = [ANKLES[SIDES.index(part[-1])]]
        elif part.startswith("EYE_"):
            choices = [EYES[SIDES.index(part[-1])], HEAD]
            choices = [next((c for c in choices if rest_head(armature, c) is not None), HEAD)]
        else:
            choices = [WRISTS[SIDES.index(part)]]
        for bones in choices:
            p = rest_head(armature, bones)
            if p is not None:
                points.append(p)
                names.append(next(n for n in bones if n in armature.data.bones))
    return points, names


def snap(frame, beats, fps):
    """`frame` moved onto the nearest beat within SNAP seconds (unchanged when there is none)."""
    near = [b for b in beats if abs(b - frame) <= SNAP * fps]
    return min(near, key=lambda b: abs(b - frame)) if near else frame


def hand_touches(scene, armature, meshes, frames, sides, reach, hidden=()):
    """For every vertex of `meshes`: the frame (fractional) at which one of the hands (`sides`) first came within
    `reach` of it while the frames played, np.inf if never. A hand is a capsule from the wrist to the fingertips; its
    way from one frame to the next is checked in three steps, so a fast hand leaves no gaps. Only the skinning counts:
    the modifiers after the armature (an outline's shell, a mask) are off meanwhile, and a mesh whose posed vertices
    still do not line up with its own is left out."""
    first = [np.full(len(ob.data.vertices), np.inf) for ob in meshes]
    last = {}
    steps = 3
    paused = []
    for ob in meshes:
        mods = list(ob.modifiers)
        after = max((i for i, m in enumerate(mods) if m.type == "ARMATURE"), default=-1)
        paused += [m for m in mods[after + 1:] if m.show_viewport]

    def visit(i, frame, positions):
        hands = {}
        for side in sides:
            wrist, finger = _hand(armature, side)
            if wrist is None:
                continue
            mw = armature.matrix_world
            w = np.array(mw @ wrist.head)
            f = np.array(mw @ finger.head) if finger is not None else np.array(mw @ wrist.tail)
            hands[side] = (w, w + 2.0 * (f - w))
        for side, (a1, b1) in hands.items():
            a0, b0 = last.get(side, (a1, b1))
            for s in range(1, steps + 1):
                t = s / float(steps) if side in last else 1.0
                a, b = a0 + (a1 - a0) * t, b0 + (b1 - b0) * t
                ab = b - a
                length2 = max(float(ab @ ab), 1e-12)
                when = frame - 1.0 + t if side in last else frame
                for pts, out in zip(positions, first):
                    if len(pts) != len(out):
                        continue
                    v = pts - a
                    u = np.clip(v @ ab / length2, 0.0, 1.0)
                    near = np.linalg.norm(v - u[:, None] * ab, axis=1) < reach
                    hit = near & (when < out)
                    out[hit] = when
        last.update(hands)

    for m in paused:
        m.show_viewport = False
    try:
        play(scene, armature, frames, hidden, meshes, visit)
    finally:
        for m in paused:
            m.show_viewport = True
    return first
