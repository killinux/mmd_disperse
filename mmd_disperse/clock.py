"""The transformation's own clock (变身的时钟, 1.30).

When the transformation slows down with the dance (Camera and Time: Transformation Slows Too) its time is not the
scene's frame any more: it crawls through the big moment with the dance and gets there on the same frame as before (so
what is keyed on the moment, the camera move and the impact frames, stays on it), runs a little faster just before to
make up for it, and stays that much behind afterwards (no fast forward: the roar after it plays at its own pace). The
mask's radius is put into an NLA strip whose time follows it (timewarp.py); this module keeps that time on an empty of
the effect as a keyed custom property, for everything else that moves by the frame: the node trees' Effect Time
(drivers on the modifiers' inputs), and the drivers of the symbiote's face on the goo coat, of the growth and of the
roar. Without it they all keep the scene's frame.

The empty also carries the lag of inertia.py for the big tendrils off her back: the outfits' meshes cannot carry keys
of their own (their actions are warped with the dance), so their modifiers are driven from here.
"""

import bpy

NAME = "MMD Disperse Clock"
P_CLOCK = "mmd_disperse_clock"  # on our empty: the mask of its effect
TIME = "mmdd_time"  # the transformation's own time (keyed while it slows with the dance; missing: the scene's frame)
BACK_LAG = "mmdd_back_lag"  # the lag of the big tendrils off her back, the back mesh's space (keyed by inertia.py)


def find(mask):
    return next((ob for ob in bpy.data.objects if ob.get(P_CLOCK) == mask), None) if mask is not None else None


def ensure(mask):
    """Our empty for the effect of `mask` (made when missing, in the mask's collection)."""
    ob = find(mask)
    if ob is None:
        ob = bpy.data.objects.new(NAME, None)
        collection = mask.users_collection[0] if mask.users_collection else bpy.context.scene.collection
        collection.objects.link(ob)
        ob[P_CLOCK] = mask
        ob.hide_select = True
        ob.empty_display_size = 0.01
    return ob


def remove(mask):
    ob = find(mask)
    if ob is not None:
        bpy.data.objects.remove(ob)


def _curve(ob, path, index=0):
    from .timewarp import _curves

    _owner, curves = _curves(ob)
    return next((fc for fc in curves if fc.data_path == path and fc.array_index == index), None)


def _drop(ob, prop):
    path = '["%s"]' % prop
    ad = ob.animation_data
    if ad is not None and ad.action is not None:
        from .timewarp import _curves

        owner, curves = _curves(ob)
        for fc in [fc for fc in curves if fc.data_path == path]:
            owner.fcurves.remove(fc)
    if prop in ob:
        del ob[prop]


def has_time(mask):
    """True when the transformation of `mask` runs on its own time."""
    ob = find(mask)
    return ob is not None and TIME in ob and _curve(ob, '["%s"]' % TIME) is not None


def set_time(mask, keys):
    """Key the transformation's own time: `keys` (scene frame, its time, interpolation), straight on beyond them."""
    ob = ensure(mask)
    _drop(ob, TIME)
    for frame, value, _interp in keys:
        ob[TIME] = float(value)
        ob.keyframe_insert('["%s"]' % TIME, frame=frame)
    fc = _curve(ob, '["%s"]' % TIME)
    if fc is not None:
        by_frame = {round(f, 3): interp for f, _v, interp in keys}
        fc.extrapolation = "LINEAR"
        for key in fc.keyframe_points:
            key.interpolation = by_frame.get(round(key.co[0], 3), "LINEAR")
        fc.update()


def clear_time(mask):
    ob = find(mask)
    if ob is not None:
        _drop(ob, TIME)


def key_vector(ob, prop, frames, values):
    """Key the vector custom property `prop` of `ob` at each of `frames` (`values`: (frames, 3)), linear between; the
    first and last values held outside."""
    _drop(ob, prop)
    if not len(frames):
        return
    ob[prop] = [float(v) for v in values[0]]
    for k in range(3):
        ob.keyframe_insert('["%s"]' % prop, index=k, frame=frames[0])
    for k in range(3):
        fc = _curve(ob, '["%s"]' % prop, k)
        if fc is None:
            continue
        points = fc.keyframe_points
        points.add(len(frames) - 1)
        co = [c for f, v in zip(frames, values) for c in (float(f), float(v[k]))]
        points.foreach_set("co", co)
        for key in points:
            key.interpolation = "LINEAR"
        fc.update()


def drive(owner, path, expression, mask, index=-1):
    """A frame driver `expression` on `path` of `owner` (any ID or struct with driver_add): by the transformation's
    own time when it has one (`frame` read as it), else by the scene's frame. Returns the driver."""
    try:
        owner.driver_remove(path, index)
    except TypeError:
        owner.driver_remove(path)
    fc = owner.driver_add(path, index) if index >= 0 else owner.driver_add(path)
    driver = fc.driver
    driver.type = "SCRIPTED"
    ob = find(mask) if has_time(mask) else None
    if ob is None:
        driver.expression = expression
        return driver
    var = driver.variables.new()
    var.name = "t"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "OBJECT"
    var.targets[0].id = ob
    var.targets[0].data_path = '["%s"]' % TIME
    driver.expression = expression.replace("frame", "t")
    return driver


def drive_value(owner, path, mask, prop, component=-1, index=-1):
    """A driver on `path` of `owner` reading our empty's custom property `prop` (its `component`): the lag."""
    ob = ensure(mask)
    try:
        owner.driver_remove(path, index)
    except TypeError:
        owner.driver_remove(path)
    fc = owner.driver_add(path, index) if index >= 0 else owner.driver_add(path)
    driver = fc.driver
    driver.type = "SCRIPTED"
    var = driver.variables.new()
    var.name = "v"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "OBJECT"
    var.targets[0].id = ob
    var.targets[0].data_path = '["%s"]' % prop + ("[%d]" % component if component >= 0 else "")
    driver.expression = "v"
    return driver
