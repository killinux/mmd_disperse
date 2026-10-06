"""Freezing the dance or slowing it down at the big moment (定格、变速: bullet time, the velocity edit of short videos),
or stepping it on twos like stop motion, while the transformation itself runs on in real time.

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


def keys_for(kind, moment, length, fps):
    """(time keys [(scene frame, action frame, interpolation)], speed keys [(frame, rigid body speed factor)]) of the
    warp `kind` round frame `moment`, lasting `length` seconds."""
    span = max(int(round(length * fps)), 2)
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
    a = moment - span // 2
    b = a + span
    time = [(a - 1, a - 1, "LINEAR")] + [(f, f, "CONSTANT") for f in range(a, b, 2)] + [(b, b, "LINEAR"),
                                                                                         (b + 1, b + 1, "LINEAR")]
    return time, []


def _warp(id_, mask, time):
    """Put the action of `id_` into a strip of ours whose time follows `time`; False when it has an NLA of its own."""
    ad = id_.animation_data
    action = ad.action
    if action is None or len(ad.nla_tracks):
        return False
    slot = getattr(ad, "action_slot", None)
    track = ad.nla_tracks.new()
    track.name = TRACK
    start = int(action.frame_range[0])
    strip = track.strips.new(action.name, start, action)
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


def sync(settings, mask, models, moment):
    """Warp the dance of `models` round frame `moment` as the panel says (redone only when that changed), or put it
    back when it is off. Returns how many animated things follow the warp."""
    scene = settings.id_data
    kind = settings.time_warp
    if kind == "NONE" or moment is None:
        restore(mask, scene)
        return 0
    fps = scene.render.fps / scene.render.fps_base
    key = "%s:%d:%.3f:%.3f" % (kind, int(moment), settings.warp_length, fps)
    if mask.get(P_KEY) == key and _warped(mask):
        return len(_warped(mask))
    restore(mask, scene)
    time, speeds = keys_for(kind, int(moment), settings.warp_length, fps)
    count = sum(1 for id_ in targets(models) if _warp(id_, mask, time))
    _key_speed(scene, speeds)
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
