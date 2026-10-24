"""Freezing the dance or slowing it down at the big moment (定格、变速: bullet time, the velocity edit of short videos),
or stepping it on twos like stop motion, while the transformation itself runs on in real time; and (1.12) the hold of
a finishing pose (finish.py), in which the transformation (the mask) stands still with the dance.

The models' motion (the bones, the facial expressions on the shape keys, the root's) is put into an NLA strip whose
time is animated: it stands still (or crawls) round the moment and then catches up with the music, so the dance is in
time again afterwards. The rigid bodies (hair, skirts) are slowed by keying the rigid body world's speed the same way,
so they hang in the air while the dance stands still. Removing the effect puts the actions back as they were.
"""

import bpy

TRACK = "MMD Disperse Time"
P_ACTION = "mmd_disperse_time_action"  # on an animated ID we warped: the name of its action before
P_MASK = "mmd_disperse_time_mask"  # ... and the mask of the effect that did it
P_SPEED = "mmd_disperse_time_speed"  # on the scene: the rigid body world's speed before we keyed it
P_KEY = "mmd_disperse_time_key"  # on the mask: the warp as it was applied (redone only when it changes)
STILL = 0.0001  # the rigid bodies' speed while the dance stands still (not 0: the solver still steps)
SPEED_PATH = "rigidbody_world.time_scale"


def _curves(id_):
    ad = id_.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return None, []
    curves = getattr(action, "fcurves", None)
    if curves is None:  # Blender 5.0+: the curves are kept per slot
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        return bag, (bag.fcurves if bag is not None else [])
    return action, curves


def targets(models):
    """The animated objects and shape keys of `models` (model.Model) whose actions make the dance."""
    found = []
    for model in models:
        if not model:
            continue
        obs = set(model.meshes) | {model.armature, model.root}
        if model.root is not None:
            obs |= set(model.root.children_recursive)
        for ob in obs:
            if ob is None or ob.type in ("CAMERA", "LIGHT"):
                continue
            found.append(ob)
            keys = ob.data.shape_keys if ob.type == "MESH" and ob.data is not None else None
            if keys is not None:
                found.append(keys)
    out = []
    for id_ in found:
        ad = id_.animation_data
        if id_ not in out and ad is not None and (ad.action is not None or P_ACTION in id_):
            out.append(id_)
    return out


REWIND_AFTER = 0.35  # seconds after the moment the tape rewinds ...
REWIND_BACK = 0.15  # ... back to this long before the transformation started ...
REWIND_SPEED = 3.0  # ... this many times as fast; the replay goes on this long past the moment ...
REPLAY_PAST = 0.2
CATCH_UP = 4.0  # ... and then it fast-forwards at about this speed until it has caught up with the music


def rewind_frames(moment, start, length, fps):
    """(rewinds from, replays from, fast-forwards from, caught up), scene frames, of Rewind and Replay round the moment
    at frame `moment` of a transformation starting at frame `start`, the replay lasting `length` seconds; and (the
    dance's frame it rewinds to, the one the replay ends on)."""
    a = int(moment + round(REWIND_AFTER * fps))
    back = int(min(start, moment) - round(REWIND_BACK * fps))
    b = a + max(int(round((a - back) / REWIND_SPEED)), 6)
    end = int(moment + round(REPLAY_PAST * fps))
    c = b + max(int(round(length * fps)), 8)
    d = c + max(int(round((c - end) / (CATCH_UP - 1.0))), 4)
    return (a, b, c, d), (back, end)


def keys_for(kind, moment, length, fps, start=None, before=False):
    """(time keys [(scene frame, action frame, interpolation)], speed keys [(frame, rigid body speed factor)]) of the
    warp `kind` round frame `moment`, lasting `length` seconds (REWIND: the transformation starting at `start`; TWOS
    `before`: all of it before the moment, as the marionette hangs on its strings)."""
    span = max(int(round(length * fps)), 2)
    if kind == "REWIND":  # on, back like a tape, again slowly, fast forward
        (a, b, c, d), (back, end) = rewind_frames(moment, moment if start is None else start, length, fps)
        time = [(a - 1, a - 1), (a, a), (b, back), (c, end), (d, d), (d + 1, d + 1)]
        speeds = [(a, 1.0), (b, (end - back) / float(c - b)), (c, (d - end) / float(d - c)), (d, 1.0)]
        return [(f, v, "LINEAR") for f, v in time], speeds
    if kind == "FREEZE":  # stand still (the moment four tenths in), then catch up at once, a little faster
        a = moment - int(round(0.4 * span))
        b = a + span
        c = b + max(int(round(0.6 * span)), 2)
        time = [(a - 1, a - 1), (a, a), (b, a), (c, c), (c + 1, c + 1)]
        return [(f, v, "LINEAR") for f, v in time], [(a, STILL), (b, (c - a) / float(c - b)), (c, 1.0)]
    if kind == "SLOW":  # a quarter speed round the moment, then catch up
        a = moment - int(round(0.35 * span))
        b = a + span
        c = b + max(int(round(0.4 * span)), 2)
        slow = 0.25
        reached = a + slow * span
        time = [(a - 1, a - 1), (a, a), (b, reached), (c, c), (c + 1, c + 1)]
        return [(f, v, "LINEAR") for f, v in time], [(a, slow), (b, (c - reached) / float(c - b)), (c, 1.0)]
    # TWOS: every pose held for two frames over the span round the moment, as in stop motion
    a = moment - (span if before else span // 2)
    b = a + span
    time = [(a - 1, a - 1, "LINEAR")] + [(f, f, "CONSTANT") for f in range(a, b, 2)] + [(b, b, "LINEAR"),
                                                                                         (b + 1, b + 1, "LINEAR")]
    return time, []


def hold_keys(first, length):
    """(time keys, speed keys) of a hold: everything stands still for `length` frames from frame `first`, then catches
    up with the music, a little faster, over 0.6 of that."""
    a = int(first)
    b = a + max(int(round(length)), 1)
    c = b + max(int(round(0.6 * length)), 2)
    time = [(a - 1, a - 1), (a, a), (b, a), (c, c), (c + 1, c + 1)]
    return [(f, v, "LINEAR") for f, v in time], [(a, STILL), (b, (c - a) / float(c - b)), (c, 1.0)]


def strip_action(id_):
    """The action of `id_`, also while it is in a strip of ours (warped), and the slot it uses there (Blender 4.4+);
    (None, None) without one."""
    ad = id_.animation_data
    if ad is None:
        return None, None
    if ad.action is not None:
        return ad.action, getattr(ad, "action_slot", None)
    for track in ad.nla_tracks:
        if track.name == TRACK:
            for strip in track.strips:
                if strip.action is not None:
                    return strip.action, getattr(strip, "action_slot", None)
    return None, None


def _warp(id_, mask, time, until=None):
    """Put the action of `id_` into a strip of ours whose time follows `time` (the strip reaching to frame `until` at
    least); False when it has an NLA of its own."""
    ad = id_.animation_data
    action = ad.action
    if action is None or len(ad.nla_tracks):
        return False
    slot = getattr(ad, "action_slot", None)
    track = ad.nla_tracks.new()
    track.name = TRACK
    start = int(action.frame_range[0])
    strip = track.strips.new(action.name, start, action)
    if until is not None and strip.action_frame_end < until:
        strip.action_frame_end = until  # (past its last key it holds that)
    if slot is not None and hasattr(strip, "action_slot"):
        strip.action_slot = slot
    strip.extrapolation = "HOLD"
    strip.blend_type = "REPLACE"
    strip.use_animated_time = True
    for frame, value, _interp in time:
        strip.strip_time = value
        strip.keyframe_insert("strip_time", frame=frame)
    by_frame = {round(f, 3): interp for f, _v, interp in time}
    for fc in strip.fcurves:
        if fc.data_path == "strip_time":
            fc.extrapolation = "LINEAR"  # (outside the keys the dance runs on with the scene)
            for key in fc.keyframe_points:
                key.interpolation = by_frame.get(round(key.co[0], 3), "LINEAR")
    id_[P_ACTION] = action.name
    id_[P_MASK] = mask
    ad.action = None
    return True


def _restore_id(id_):
    ad = id_.animation_data
    name = id_.get(P_ACTION)
    if ad is not None:
        for track in [t for t in ad.nla_tracks if t.name == TRACK]:
            ad.nla_tracks.remove(track)
        action = bpy.data.actions.get(name) if name else None
        if ad.action is None and action is not None:
            ad.action = action
    for key in (P_ACTION, P_MASK):
        if key in id_:
            del id_[key]


def _warped(mask=None):
    ids = list(bpy.data.objects) + list(bpy.data.shape_keys)
    return [i for i in ids if P_ACTION in i and (mask is None or i.get(P_MASK) == mask)]


def _key_speed(scene, speeds):
    """Key the rigid body world's speed at (frame, factor of its own speed), constant between: unless the scene keys
    it itself."""
    rbw = scene.rigidbody_world
    if rbw is None or not speeds:
        return
    owner, curves = _curves(scene)
    if P_SPEED not in scene and any(fc.data_path == SPEED_PATH for fc in curves):
        return  # (the scene animates its speed: leave it alone)
    _clear_speed(scene, keep=True)
    base = float(scene.get(P_SPEED, rbw.time_scale))
    scene[P_SPEED] = base
    for frame, factor in [(speeds[0][0] - 1, 1.0)] + list(speeds):
        rbw.time_scale = base * factor
        rbw.keyframe_insert("time_scale", frame=frame)
    for fc in _curves(scene)[1]:
        if fc.data_path == SPEED_PATH:
            for key in fc.keyframe_points:
                key.interpolation = "CONSTANT"


def _clear_speed(scene, keep=False):
    if P_SPEED not in scene:
        return
    owner, curves = _curves(scene)
    for fc in [fc for fc in curves if fc.data_path == SPEED_PATH]:
        owner.fcurves.remove(fc)
    if scene.rigidbody_world is not None:
        scene.rigidbody_world.time_scale = float(scene[P_SPEED])
    if not keep:
        del scene[P_SPEED]


def sync(settings, mask, models, moment, hold=None):
    """Warp the dance of `models` round frame `moment` as the panel says and hold it (and the transformation) still
    for a finishing pose: `hold` (first frame, frames), after the warp has caught up; redone only when that changed,
    put back when there is nothing to do. Returns how many animated things follow the warp."""
    scene = settings.id_data
    kind = settings.time_warp if moment is not None else "NONE"
    if kind == "NONE" and hold is None:
        restore(mask, scene)
        return 0
    fps = scene.render.fps / scene.render.fps_base
    before = bool(getattr(settings, "puppet_enable", False) or getattr(settings, "shadow_enable", False))  # (1.16:
    # on twos while she hangs on the strings or is a figure of the shadow play, not after)
    key = "%s:%s:%.3f:%.3f:%s:%d:%d" % (kind, int(moment) if moment is not None else -1, settings.warp_length, fps,
                                        "%d,%d" % (int(hold[0]), int(hold[1])) if hold is not None else "-",
                                        settings.frame_start, before)
    if mask.get(P_KEY) == key and _warped(mask):
        return len(_warped(mask))
    restore(mask, scene)
    time, speeds = keys_for(kind, int(moment), settings.warp_length, fps,
                            settings.frame_start, before) if kind != "NONE" else ([], [])
    held, held_speeds = [], []
    if hold is not None:
        first = int(hold[0])
        if time:  # (after the warp at the moment has caught up)
            first = max(first, int(max(f for f, _v, _i in time)) + 2)
        held, held_speeds = hold_keys(first, hold[1])
    count = sum(1 for id_ in targets(models) if _warp(id_, mask, time + held))
    # the transformation stands still with a finishing pose too, and rewinds and replays with the tape
    own = (time if kind == "REWIND" else []) + held
    if own and mask.animation_data is not None and mask.animation_data.action is not None:
        _warp(mask, mask, own, until=own[-1][0] + 1)
    _key_speed(scene, speeds + held_speeds)
    mask[P_KEY] = key
    return count


def restore_models(models):
    """Put back whatever of `models` is warped (by any effect, also one whose mask is gone)."""
    for id_ in targets(models):
        if P_ACTION in id_:
            _restore_id(id_)


def restore(mask=None, scene=None):
    """Put back the actions warped by the effect of `mask` (all of ours without one) and the rigid bodies' speed."""
    for id_ in _warped(mask):
        _restore_id(id_)
    for sc in [scene] if scene is not None else list(bpy.data.scenes):
        _clear_speed(sc)
    if mask is not None and P_KEY in mask:
        del mask[P_KEY]
