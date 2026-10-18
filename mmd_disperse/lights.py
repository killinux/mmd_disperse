"""Light and the moment (1.12): the follow spot of the path Under the Spotlight (a spot light of ours aimed as the
building found it, with a beam you can see), lights out round the transformation (the scene's own lights and its
world dimmed by drivers, put back when the effect is removed) and a camera flash (a light on the camera that fires at
the big moment, and on the beats before it; with Flash Steps the change itself only moves on with each flash).
"""

import math

import bpy
from mathutils import Vector

from . import materials

SPOT = "MMD Disperse Follow Spot Light"
BEAM = "MMD Disperse Spot Beam"
FLASH = "MMD Disperse Camera Flash"
BOOM = "MMD Disperse Explosion Light"
BOOM_POWER = 900.0  # the toon explosion's light at its peak, in watts per square model height ...
BOOM_COLOR = (1.0, 0.45, 0.12)
BOOM_FADE = 0.6  # ... gone this many seconds after the moment
P_LIGHT = "mmd_disperse_light"  # on our lights and the beam: the mask of their effect
P_KIND = "mmd_disperse_light_kind"  # ... SPOT, BEAM, FLASH, BOOM
P_DIM = "mmd_disperse_dim"  # on a light data block (or the world) we dim: its strength before, and ...
P_DIM_MASK = "mmd_disperse_dim_mask"  # ... the mask of the effect that dims it
SPOT_POWER = 600.0  # how bright the follow spot is, in watts per square model height
FLASH_POWER = 800.0  # ... and the flash at its peak
DIM_RAMP = 0.3  # seconds the lights take to go down and come back up


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_LIGHT) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if isinstance(data, bpy.types.Light) and data.users == 0:
        bpy.data.lights.remove(data)
    elif isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)


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


def _clear(id_):
    if id_.animation_data is not None and id_.animation_data.action is not None:
        action = id_.animation_data.action
        id_.animation_data.action = None
        if action.users == 0:
            bpy.data.actions.remove(action)


def _linear(id_):
    for fc in _curves(id_):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
        fc.update()


def _beam_mesh():
    """A cone from its tip at the origin down -Z to a ring of radius 1 at z = -1 (a spot light's way), open."""
    me = bpy.data.meshes.new(BEAM)
    sides = 32
    verts = [(0.0, 0.0, 0.0)] + [(math.cos(2.0 * math.pi * k / sides), math.sin(2.0 * math.pi * k / sides), -1.0)
                                 for k in range(sides)]
    faces = [(0, 1 + (k + 1) % sides, 1 + k) for k in range(sides)]
    me.from_pydata(verts, [], faces)
    for poly in me.polygons:
        poly.use_smooth = True
    me.materials.append(materials.ensure_beam_glow_material())
    return me


def sync_spot(settings, mask, rec, height, collection):
    """The follow spot of the path Under the Spotlight from what building found (`rec`: its source and, per frame,
    where it aimed (flat x, y, z) and how wide): a spot light keyed to aim and open the same way, and its beam."""
    if rec is None:
        for ob in objects(mask, "SPOT") + objects(mask, "BEAM"):
            _delete(ob)
        return
    source = Vector(rec["source"])
    flat = list(rec["aims"])
    frames, halves = list(rec["frames"]), list(rec["halves"])
    aims = [flat[i:i + 3] for i in range(0, len(flat) - 2, 3)]
    if not frames or len(aims) != len(frames):
        return
    spot = next(iter(objects(mask, "SPOT")), None)
    if spot is None:
        data = bpy.data.lights.new(SPOT, "SPOT")
        spot = bpy.data.objects.new(SPOT, data)
        collection.objects.link(spot)
        spot[P_LIGHT] = mask
        spot[P_KIND] = "SPOT"
        spot.hide_select = True
    beam = next(iter(objects(mask, "BEAM")), None)
    if beam is None:
        beam = bpy.data.objects.new(BEAM, _beam_mesh())
        collection.objects.link(beam)
        beam[P_LIGHT] = mask
        beam[P_KIND] = "BEAM"
        beam.hide_select = True
        if hasattr(beam, "visible_shadow"):
            beam.visible_shadow = False
    data = spot.data
    data.color = settings.spot_color
    data.energy = SPOT_POWER * settings.spot_energy * height * height
    data.spot_blend = 0.25
    data.shadow_soft_size = 0.02 * height
    if hasattr(data, "use_shadow"):
        data.use_shadow = True
    for ob in (spot, beam, data):
        _clear(ob)
    spot.location = source
    beam.location = source
    spot.rotation_mode = beam.rotation_mode = "QUATERNION"
    first, last = frames[0], frames[-1]
    for f, aim, half in zip(frames, aims, halves):
        way = Vector(aim) - source
        turn = way.to_track_quat("-Z", "Y")
        spot.rotation_quaternion = beam.rotation_quaternion = turn
        spot.keyframe_insert("rotation_quaternion", frame=f)
        beam.rotation_quaternion = turn
        beam.keyframe_insert("rotation_quaternion", frame=f)
        data.spot_size = min(2.0 * half * 1.08, math.pi)
        data.keyframe_insert("spot_size", frame=f)
        reach = way.length * 1.02  # (the beam ends where it falls on her)
        wide = math.tan(half) * reach
        beam.scale = (wide, wide, reach)
        beam.keyframe_insert("scale", frame=f)
    # on from a little before the transformation to a little after it, the beam fading with it
    on = settings.spot_energy > 0.0
    for f, level in ((first - 6, 0.0), (first, 1.0), (last + 10, 1.0), (last + 22, 0.0)):
        data.energy = SPOT_POWER * settings.spot_energy * height * height * level
        data.keyframe_insert("energy", frame=f)
        beam["mmdd_beam_on"] = level if on else 0.0
        beam.keyframe_insert('["mmdd_beam_on"]', frame=f)
    for ob in (spot, beam, data):
        _linear(ob)
    materials.update_beam_glow_material(settings.spot_color, settings.spot_beam)


MIRROR = "MMD Disperse Mirror Ball"
MIRROR_POWER = 320.0  # 1.13: each of the mirror ball's spots, in watts per square model height
MIRROR_COLORS = ((1.0, 1.0, 1.0), (1.0, 0.55, 0.85), (0.5, 0.85, 1.0), (1.0, 0.85, 0.45))
MIRROR_SIZE = 0.09  # the ball's radius (model heights)


def _mirror_ball_mesh():
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    me = bpy.data.meshes.new(MIRROR)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(materials.ensure_cover_material("MIRRORBALL"))  # (flat faces: its tiles)
    return me


def sync_mirror(settings, mask, rec, height, collection):
    """The mirror ball of the path Swept by a Mirror Ball from what building found (`rec`: where it hangs, its spots'
    directions at the first frame): the ball and a spot light for each spot, hung on an empty that turns as the
    spots turned while building, on from a little before the transformation to a little after it."""
    from .sampling import MIRROR_HALF, MIRROR_TURN

    kinds = ("MIRROR_PIVOT", "MIRROR_BALL", "MIRROR_SPOT")
    if rec is None:
        for ob in [ob for kind in kinds for ob in objects(mask, kind)]:
            _delete(ob)
        return
    ball = Vector(rec["ball"])
    flat = list(rec["dirs"])
    dirs = [Vector(flat[i:i + 3]) for i in range(0, len(flat) - 2, 3)]
    start = float(rec["start"])
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    first = start - 0.5 * fps
    last = max(float(settings.frame_end), start + 1.0) + 0.8 * fps
    pivot = next(iter(objects(mask, "MIRROR_PIVOT")), None)
    if pivot is None:
        pivot = bpy.data.objects.new(MIRROR + " Pivot", None)
        pivot.empty_display_size = 0.05 * height
        collection.objects.link(pivot)
        pivot[P_LIGHT] = mask
        pivot[P_KIND] = "MIRROR_PIVOT"
        pivot.hide_select = True
    _clear(pivot)
    pivot.location = ball
    pivot.rotation_mode = "XYZ"
    rate = 2.0 * math.pi / (MIRROR_TURN * fps)
    for f in (first, last):
        pivot.rotation_euler = (0.0, 0.0, (f - start) * rate)
        pivot.keyframe_insert("rotation_euler", frame=f)
    _linear(pivot)
    sphere = next(iter(objects(mask, "MIRROR_BALL")), None)
    if sphere is None:
        sphere = bpy.data.objects.new(MIRROR, _mirror_ball_mesh())
        collection.objects.link(sphere)
        sphere[P_LIGHT] = mask
        sphere[P_KIND] = "MIRROR_BALL"
        sphere.hide_select = True
    sphere.parent = pivot
    sphere.location = (0.0, 0.0, 0.0)
    sphere.scale = (MIRROR_SIZE * height,) * 3
    spots = objects(mask, "MIRROR_SPOT")
    for ob in spots[len(dirs):]:
        _delete(ob)
    spots = spots[:len(dirs)]
    while len(spots) < len(dirs):
        data = bpy.data.lights.new(MIRROR + " Spot", "SPOT")
        ob = bpy.data.objects.new(MIRROR + " Spot", data)
        collection.objects.link(ob)
        ob[P_LIGHT] = mask
        ob[P_KIND] = "MIRROR_SPOT"
        ob.hide_select = True
        spots.append(ob)
    power = MIRROR_POWER * height * height * max(settings.spot_energy, 0.0)
    for k, (ob, way) in enumerate(zip(spots, dirs)):
        ob.parent = pivot
        ob.location = (0.0, 0.0, 0.0)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = way.to_track_quat("-Z", "Y")  # (as at the first frame, when the pivot is not turned)
        data = ob.data
        data.color = MIRROR_COLORS[k % len(MIRROR_COLORS)]
        data.spot_size = 2.0 * MIRROR_HALF * 1.1
        data.spot_blend = 0.05
        data.shadow_soft_size = 0.002 * height
        if hasattr(data, "use_shadow"):
            data.use_shadow = False
        _clear(data)
        for f, level in ((first, 0.0), (first + 0.3 * fps, 1.0), (last - 0.3 * fps, 1.0), (last, 0.0)):
            data.energy = power * level
            data.keyframe_insert("energy", frame=f)
        _linear(data)


def _dimmed(mask=None):
    ids = list(bpy.data.lights) + list(bpy.data.worlds)
    return [i for i in ids if P_DIM in i and (mask is None or i.get(P_DIM_MASK) == mask)]


def _background(world):
    """The world's Background node strength socket (None when it has none)."""
    if world is None or not world.use_nodes or world.node_tree is None:
        return None
    node = next((n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeBackground"), None)
    return node.inputs["Strength"] if node is not None else None


def dim_expression(first, last, ramp, level):
    """Driver expression on the frame: 1 outside, `level` from `first` to `last`, ramping over `ramp` frames each way
    (simple math only)."""
    return ("1 - {d:.4f} * clamp((frame - {a:.2f}) / {r:.2f}, 0, 1) * clamp(({b:.2f} - frame) / {r:.2f}, 0, 1)"
            .format(d=1.0 - level, a=first - ramp, b=last + ramp, r=max(ramp, 1e-3)))


def sync_dim(settings, mask, first, last):
    """Lights out from frame `first` to `last`: the scene's own lights (and its world) dimmed to Lights Level by a
    driver on their strength, which removing the effect (or turning it off) takes off again."""
    scene = settings.id_data
    undim(mask)
    if not settings.lights_out or first is None or last is None:
        return 0
    fps = scene.render.fps / scene.render.fps_base
    expression = dim_expression(first, last, DIM_RAMP * fps, settings.lights_level)
    count = 0
    ours = {ob.data for ob in objects(mask) if ob.type == "LIGHT"}
    for ob in scene.objects:
        if ob.type != "LIGHT" or ob.data in ours or ob.data.get(P_DIM) is not None:
            continue
        data = ob.data
        if data.animation_data is not None and any(d.data_path == "energy" for d in data.animation_data.drivers):
            continue  # (driven by the scene itself ...
        if any(fc.data_path == "energy" for fc in _curves(data)):
            continue  # ... or animated: a driver would take its animation over)
        data[P_DIM] = data.energy
        data[P_DIM_MASK] = mask
        driver = data.driver_add("energy").driver
        driver.type = "SCRIPTED"
        driver.expression = "{e:.5f} * ({x})".format(e=data.energy, x=expression)
        count += 1
    world = scene.world
    strength = _background(world)
    animated = world is not None and any("Background" in fc.data_path or "inputs[1]" in fc.data_path
                                         for fc in _curves(world.node_tree)) if strength is not None else True
    if strength is not None and world.get(P_DIM) is None and not strength.is_linked and not animated:
        world[P_DIM] = strength.default_value
        world[P_DIM_MASK] = mask
        driver = strength.driver_add("default_value").driver
        driver.type = "SCRIPTED"
        driver.expression = "{e:.5f} * ({x})".format(e=strength.default_value, x=expression)
        count += 1
    return count


def undim(mask=None):
    """Put back the strength of the lights (and worlds) dimmed by the effect of `mask` (all of ours without one)."""
    for id_ in _dimmed(mask):
        if isinstance(id_, bpy.types.World):
            strength = _background(id_)
            if strength is not None:
                strength.driver_remove("default_value")
                strength.default_value = float(id_[P_DIM])
        else:
            id_.driver_remove("energy")
            id_.energy = float(id_[P_DIM])
        for key in (P_DIM, P_DIM_MASK):
            if key in id_:
                del id_[key]


def flash_frames(moment, count, beats, fps):
    """The frames the camera flashes on: the last at `moment`, the ones before on the beats before it (`beats`), else
    half a second apart."""
    before = sorted(b for b in beats if b < moment - 1)[-(count - 1):] if count > 1 and beats else []
    if count > 1 and len(before) < count - 1:
        before = [moment - (count - 1 - k) * 0.5 * fps for k in range(count - 1)]
    return [float(f) for f in before] + [float(moment)]


def sync_flash(settings, mask, frames, height, camera):
    """The camera flash: a light on the camera firing at `frames` (bright for a frame, gone over three)."""
    flash = next(iter(objects(mask, "FLASH")), None)
    if not settings.flash_enable or not frames or camera is None:
        if flash is not None:
            _delete(flash)
        return None
    if flash is None or flash.parent != camera:
        if flash is not None:
            _delete(flash)
        data = bpy.data.lights.new(FLASH, "POINT")
        flash = bpy.data.objects.new(FLASH, data)
        collection = camera.users_collection[0] if camera.users_collection else settings.id_data.collection
        collection.objects.link(flash)
        flash.parent = camera
        flash[P_LIGHT] = mask
        flash[P_KIND] = "FLASH"
        flash.hide_select = True
    data = flash.data
    data.color = (1.0, 0.98, 0.95)
    data.shadow_soft_size = 0.004 * height
    flash.location = (0.0, 0.0, 0.0)
    _clear(data)
    peak = FLASH_POWER * settings.flash_power * height * height
    for f in frames:
        for df, level in ((-1.0, 0.0), (0.0, 1.0), (1.0, 0.45), (3.0, 0.0)):
            data.energy = peak * level
            data.keyframe_insert("energy", frame=f + df)
    _linear(data)
    data.energy = 0.0
    return flash


def sync_boom(settings, mask, first, moment, middle, height, collection):
    """The toon explosion's light: an orange point light amid the outfits (`middle`), glowing up as the fire wraps them
    from frame `first`, flaring at the moment and dying away (none when `first` is None)."""
    boom = next(iter(objects(mask, "BOOM")), None)
    if first is None or moment is None or middle is None:
        if boom is not None:
            _delete(boom)
        return None
    if boom is None:
        data = bpy.data.lights.new(BOOM, "POINT")
        boom = bpy.data.objects.new(BOOM, data)
        collection.objects.link(boom)
        boom[P_LIGHT] = mask
        boom[P_KIND] = "BOOM"
        boom.hide_select = True
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    data = boom.data
    data.color = BOOM_COLOR
    data.shadow_soft_size = 0.15 * height
    boom.location = middle
    _clear(data)
    peak = BOOM_POWER * height * height
    rise = max(first, moment - 0.5 * fps)
    for f, level in ((rise - 1.0, 0.0), (moment - 2.0, 0.35), (moment, 1.0), (moment + BOOM_FADE * fps, 0.0)):
        data.energy = peak * level
        data.keyframe_insert("energy", frame=f)
    _linear(data)
    data.energy = 0.0
    return boom


def remove(mask):
    for ob in objects(mask):
        _delete(ob)
    undim(mask)
    mat = bpy.data.materials.get(materials.BEAM_GLOW_MATERIAL)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)
