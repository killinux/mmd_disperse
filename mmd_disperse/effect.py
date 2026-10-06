"""Build, update and remove a suit-up effect (mask empty + modifiers + materials)."""

import fnmatch
import math
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import (arrival, beats, compositor, domain, impact, launch, materials, motion, particles, ribbons, rings, shots,
               timewarp, toon, trails, venom)
from . import model as mdl
from .node_groups import BASE_GROUP, DISTANCE_INPUTS, TARGET_GROUP, ensure_node_groups, input_identifiers

MOD_NAME = "MMD Disperse"
MASK_NAME = "MMD Disperse Mask"
WIRE_MATERIAL = materials.WIRE_MATERIAL

# Custom properties used to undo what build() changed.
P_MASK = "mmd_disperse_mask"
P_ROLE = "mmd_disperse_role"
P_REST = "mmd_disperse_rest_attr"
P_ARM = "mmd_disperse_armatures"
P_MATRIX = "mmd_disperse_matrix"
P_ROOTS = "mmd_disperse_roots"
P_FOLLOWERS = "mmd_disperse_followers"  # on the mask: armatures whose bones copy the old armature's pose
FOLLOW = "MMD Disperse Follow"  # name of those bone constraints
# What sync() needs to know about the built effect (stored on the mask).
P_PATH = "mmd_disperse_path"
P_REACH = "mmd_disperse_reach"  # largest mask radius (end of the keys)
P_WAVE = "mmd_disperse_wave"  # mask radius at which the wave has passed everything
P_AREA = "mmd_disperse_area"
P_AREA_NEW = "mmd_disperse_area_new"
P_LAYOUT = "mmd_disperse_layout"  # sweeps and the spiral: where the front starts and the axes it moves along
P_ROOT = "mmd_disperse_root"  # the model the effect follows when it moves as a whole
P_PITCH = "mmd_disperse_pitch"  # the spiral's pitch the arrival field was built with
P_BROOCH = "mmd_disperse_brooch"  # world rest position the old outfit is sucked into (the start bone)
P_TRIGGER = "mmd_disperse_trigger"  # the frame the move of the dance that starts it was found on (-1: none found)
P_SPEED = "mmd_disperse_speed"  # hand path: how far the front gets in a frame (its keys go linearly at that pace)
FLAKES = ("FRAGMENTS", "SUCK")  # exit styles that break the old outfit into flakes

# Sizes as a fraction of the model height (tuned on Tifa, ~20.7 MMD units tall).
SIZE_RATIOS = {
    "noise_amount": 0.05,
    "edge_width": 0.05,
    "edge_push": 0.01,
    "wire_inner": 0.03,
    "wire_outer": 0.015,
    "wire_radius": 0.0008,
    "wire_lift": 0.0015,
    "base_shrink": 0.004,
    "base_delete_offset": 0.03,
    "frag_burst": 0.012,
    "frag_wind": 0.3,
    "frag_turbulence": 0.05,
    "particle_size": 0.018,
    "holo_width": 0.12,
    "glitch_width": 0.15,
    "glitch_slice": 0.012,
    "glitch_shift": 0.02,
    "piece_size": 0.06,
    "fly_distance": 0.25,
    "fly_range": 0.08,
    "chunk_force": 0.15,
    "silhouette_width": 0.1,
    "ribbon_width": 0.004,
    "ribbon_linger": 0.12,
    "finale_distance": 0.17,
    "finale_width": 0.04,
    "layer_width": 0.12,
    "inner_depth": 0.1,
    "venom_length": 0.16,
    "venom_thickness": 0.0028,
    "surface_width": 0.12,
    "crystal_size": 0.03,
    "clamp_distance": 0.22,
    "ghost_distance": 0.25,
    "scale_size": 0.025,
    "flip_width": 0.08,
    "spiral_pitch": 0.1,
    "smoke_size": 0.09,
    "paint_width": 0.12,
    "sketch_width": 0.15,
    "outline_width": 0.0012,
    "reactor_size": 0.03,
    "plate_size": 0.045,
    "plate_lift": 0.02,
    "plate_width": 0.12,
    "arc_length": 0.05,
    "arc_reach": 0.03,
    "arc_thickness": 0.001,
    "silk_swell": 0.008,
    "hand_reach": 0.07,
    "flame_width": 0.1,
    "flame_height": 0.12,
    "shock_size": 0.6,
    "split_distance": 0.4,
    "trail_width": 0.035,
}
PAINT_STYLES = ("NONE", "LINEART", "INK", "CODE")
PAINT_CELL = 0.012  # size of the hatching / washes of the drawings, fraction of the model height
CODE_CELL = 0.015  # width of a column of the digital rain, fraction of the model height
STRIKE_FRAMES = 8  # how long the lightning strike lasts, in frames from the start
STRIKE_HEIGHT = 1.4  # how far above the start point the strike comes from, in model heights
HOLO_LINE_SPACING = 0.006  # scan line spacing of the hologram, fraction of the model height
LAYER_CELL = 0.012  # cell size of the line web on the undersuit, fraction of the model height
GOO_CELL = 0.02  # size of the goo's wet and dry smears, fraction of the model height
SURFACE_CELL = 0.03  # cell size of the veins, frost and char ahead of the edge, fraction of the model height
STRAND_LIFE = 2.0  # how far the edge moves on before a strand is gone, in tendril lengths
ABSORB = 0.6  # how far behind the edge the goo swallows a tendril, in tendril lengths
CLAMP_AT = 0.8  # share of the wave at which the halves of the new outfit clamp shut, or the ghosts meet
# entrances where all of the new outfit is there at that moment (the old one goes then): the halves clamp shut, the
# ghosts meet, the evolution flash ends, the smoke puff hides the swap, the new outfit has stood up out of the shadow
# or shimmered in in the transporter beam, it simply swaps, or the lotus bud is shut round it
AT_ONCE = ("CLAMP", "GHOSTS", "EVOLVE", "POOF", "SHADOW", "BEAM", "SWAP", "LOTUS")
LOTUS_END = 1.65  # share of the moment by which the lotus has opened and sunk away
FLAME_AFTER = 0.25  # share of the wave the flames' aura burns on after the big moment
SHOCK_SPAN = 0.2  # share of the wave the shockwave takes to spread
SOUL_PEAK = 0.6  # share of the big moment by which the soul rings have risen ...
SOUL_AFTER = 0.3  # ... and the share of the wave they stay after it
HUSK_RISE = 0.5  # how far the husk floats up, in model heights
SPLIT_SLIDE = 0.06  # share of the wave the old self takes to step out beside the dancer
FIGURINE_AWAY = (0.3, 0.12)  # where the figurine lands: to the side and towards the camera, in model heights
SHATTER_AT = 1.0  # share of the wave at which the old outfit goes all at once (exit timing): when the wave is done
BEAT_REACH = 2.0  # seconds a moment may wait for the next beat
WORLD_CLOSE = 0.12  # share of the wave the world change takes to shatter or close back
NOISE_CELLS_PER_HEIGHT = 6.0


class EffectError(Exception):
    pass


def fit_sizes(settings, height):
    height = max(height, 1e-6)
    for key, ratio in SIZE_RATIOS.items():
        setattr(settings, key, ratio * height)
    settings.noise_scale = NOISE_CELLS_PER_HEIGHT / height
    settings.size_reference = height


def model_height(ob):
    model = mdl.resolve(ob)
    if not model:
        return 0.0
    lo, hi = mdl.rest_bounds(model.meshes)
    return hi.z - lo.z


def _object_scale(ob):
    s = ob.matrix_world.to_scale()
    return max((abs(s.x) + abs(s.y) + abs(s.z)) / 3.0, 1e-9)


# --------------------------------------------------------------------------- mask

def _origin(context, settings, model):
    if settings.origin_mode == "CURSOR":
        return context.scene.cursor.location.copy(), None
    if settings.origin_mode == "BONE" and model.armature is not None:
        name = settings.origin_bone or mdl.auto_origin_bone(model.armature)
        bone = model.armature.data.bones.get(name)
        if bone is not None:
            return model.armature.matrix_world @ bone.head_local, name
    lo, hi = mdl.rest_bounds(model.meshes)
    return (lo + hi) / 2, None


def _insert_scale_keys(mask, frames_values, interpolation):
    prefs = bpy.context.preferences.edit
    old = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = interpolation
    try:
        for frame, value in frames_values:
            mask.scale = (value, value, value)
            mask.keyframe_insert("scale", frame=frame)
    finally:
        prefs.keyframe_new_interpolation_type = old
    # (set on the keys too: Blender 3.6 run from the command line keeps Bezier keys whatever the preference says)
    for fc in _scale_curves(mask):
        for key in fc.keyframe_points:
            key.interpolation = interpolation
        fc.update()


def _create_mask(settings, location, armature, bone, collection, radius_max, path, root=None, axis=None, speed=0.0):
    mask = bpy.data.objects.new(MASK_NAME, None)
    # The scale is how far the wave has travelled; for the sweeps an arrow shows the direction.
    mask.empty_display_type = "SINGLE_ARROW" if path in arrival.SWEEPS else "SPHERE"
    if path in arrival.SWEEPS and axis is not None:
        mask.rotation_euler = Vector((0.0, 0.0, 1.0)).rotation_difference(axis).to_euler()
    mask.empty_display_size = 1.0
    mask.show_in_front = True
    mask.hide_render = True
    collection.objects.link(mask)
    mask.location = location
    if path == "SPHERE" and settings.space == "POSED" and armature is not None and bone:
        con = mask.constraints.new("COPY_LOCATION")
        con.target = armature
        con.subtarget = bone
    elif root is not None:
        # The centre stays where it is on the body when the whole model moves or turns (object animation);
        # the scale is the radius, so it is not inherited.
        con = mask.constraints.new("CHILD_OF")
        con.name = FOLLOW
        con.target = root
        con.use_scale_x = con.use_scale_y = con.use_scale_z = False
        loc, rot, _scale = root.matrix_world.decompose()
        con.inverse_matrix = Matrix.LocRotScale(loc, rot, None).inverted()
    start = settings.frame_start
    end = max(settings.frame_end, start + 1)
    if speed > 0.0:  # (the hand path: at the pace the hands set)
        end = start + radius_max / speed
    keys = [(start, 0.0), (end, radius_max)]
    if settings.direction == "SHRINK":
        keys = [(start, radius_max), (end, 0.0)]
    _insert_scale_keys(mask, keys, "LINEAR" if settings.easing == "LINEAR" or speed > 0.0 else "BEZIER")
    return mask


def _layer(settings):
    """How far the new outfit's final look trails behind the edge (the dark undersuit), in world units."""
    return settings.layer_width if settings.layer_enable else 0.0


def _old_at_once(settings):
    """True when all of the old outfit goes at one moment: the new outfit's halves clamp shut or its ghosts meet, or
    the old outfit stays (freezing over ...) while the wave crosses it and then goes all at once, or leaves its husk."""
    return (settings.entrance in AT_ONCE or settings.exit_style == "HUSK"
            or (settings.exit_timing == "AT_ONCE" and settings.entrance != "SCALES"))


def _held(settings):
    """True when the new outfit waits under the old one's opaque surface (veins, char, ink, stone, gold, silk, code)
    until the old outfit goes all at once, instead of growing at the edge and showing through it (under clear ice it
    is seen forming), or for the moment the old outfit is left behind as a husk."""
    if settings.entrance != "GROW":
        return False
    return settings.exit_style == "HUSK" or (settings.exit_timing == "AT_ONCE"
                                             and settings.old_surface not in ("NONE", "FROST"))


def _on_beat(settings, mask, radius):
    """`radius` moved on to where the mask is a frame before the next beat (with beat sync on and beats found), so what
    starts there peaks on the beat. Unchanged without a beat within BEAT_REACH seconds."""
    frames = beats.beat_frames() if settings.beat_sync and settings.direction == "GROW" and mask is not None else []
    curves = _scale_curves(mask) if frames else []
    keys = curves[0].keyframe_points if curves else []
    if len(keys) < 2:
        return radius
    fc = curves[0]
    frame, last = keys[0].co[0], keys[-1].co[0]
    while frame <= last and fc.evaluate(frame) < radius:
        frame += 0.25
    scene = settings.id_data
    reach = BEAT_REACH * scene.render.fps / scene.render.fps_base
    beat = next((f for f in frames if f >= frame), None)
    if frame > last or beat is None or beat > last or beat - frame > reach:
        return radius
    return fc.evaluate(beat - 1.0)


def _moment(settings, wave, mask=None):
    """Mask radius at which all of the old outfit goes (when it goes at once): the halves clamp shut / the ghosts meet,
    or the wave is done. On the beat with beat sync."""
    return _on_beat(settings, mask, (CLAMP_AT if settings.entrance in AT_ONCE else SHATTER_AT) * wave)


def _finale_start(settings, wave, mask=None):
    """Mask radius at which the new outfit is complete and the finale starts: when the halves clamp shut, or once the
    wave has passed and the final look (behind the undersuit) is complete. On the beat with beat sync."""
    if settings.entrance in AT_ONCE:
        return _moment(settings, wave, mask)
    return _on_beat(settings, mask, wave + _layer(settings))


def _extra(settings, wave, has_base, has_target):
    """How much further the mask grows after the wave has passed (radius `wave`) so everything finishes: flakes and
    particles (their flight is a share of the wave), the undersuit turning into the final look and then the finale, the
    last armour plates settling."""
    extra = 0.0
    if has_base:
        if settings.exit_style in FLAKES + ("CHUNKS",):
            extra = settings.frag_life * wave
        if settings.particles != "NONE":
            extra = max(extra, settings.particle_life * wave)
        if _old_at_once(settings) and settings.entrance not in AT_ONCE:
            # it goes once the wave is done (give or take a few percent), then shrinks away or flies off
            extra = max(extra, settings.base_delete_offset) + (SHATTER_AT + 0.05 - 1.0) * wave
    if has_target:
        extra = max(extra, _layer(settings) + (settings.finale_length * wave if settings.finale else 0.0))
    if has_target and settings.plates:  # the last plates rise and settle up to a plate width (and their jitter) behind
        extra = max(extra, settings.plate_width + 0.25 * settings.plate_size)
    if has_target and settings.entrance == "POOF":  # the smoke drifts up and thins out after the moment
        extra = max(extra, (1.35 * CLAMP_AT - 1.0) * wave)
    if settings.venom_enable:  # the last strands snap
        extra = max(extra, STRAND_LIFE * settings.venom_length)
    # 1.10: what goes on after the big moment (the swap, or the new outfit complete)
    big = (CLAMP_AT * wave if settings.entrance in AT_ONCE else wave + _layer(settings))
    if settings.entrance == "LOTUS":  # the lotus opens and sinks away
        extra = max(extra, (LOTUS_END * CLAMP_AT - 1.0) * wave)
    if has_base and settings.exit_style == "HUSK":  # the husk holds, then crumbles or floats away
        moment = (CLAMP_AT if settings.entrance in AT_ONCE else SHATTER_AT) * wave
        extra = max(extra, moment - wave + (settings.husk_hold + settings.husk_time + 0.02) * wave)
    if settings.flame_enable and settings.flame_mode == "AURA":
        extra = max(extra, big + FLAME_AFTER * wave - wave)
    if settings.impact_enable and settings.shockwave:
        extra = max(extra, big + SHOCK_SPAN * wave - wave)
    if settings.soul_enable:
        extra = max(extra, big + SOUL_AFTER * wave - wave)
    if settings.domain_enable:  # 1.11: the world change stays a while, then shatters or closes back
        extra = max(extra, _world_times(settings, wave, big)[2] - wave)
    return extra


def _world_times(settings, wave, big):
    """(open end, close start, close end) of the world change in mask radius: it opens over a share of the way to the
    big moment `big`, stays for a share of the wave after it and then shatters or closes back."""
    open_end = max(settings.domain_open * big, 1e-3 * max(wave, 1e-3))
    close_start = big + settings.domain_hold * wave
    return open_end, close_start, close_start + WORLD_CLOSE * wave


def _scale_curves(ob):
    """F-curves animating the object's scale (the mask radius)."""
    ad = ob.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return []
    curves = getattr(action, "fcurves", None)  # gone in Blender 5.0: layered actions keep them per slot
    if curves is None:
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    return [fc for fc in curves if fc.data_path == "scale"]


def _retime(settings, mask, objects):
    """Stretch the mask's keys so it grows far enough for the flakes, particles and finale to finish after
    the wave (their timing follows the panel). Scaling the key values keeps any retiming done by hand."""
    wave = float(mask.get(P_WAVE, 0.0))
    old = float(mask.get(P_REACH, 0.0))
    if wave <= 0.0 or old <= 0.0:
        return
    roles = {ob.get(P_ROLE) for ob in objects}
    radius = wave + _extra(settings, wave, "BASE" in roles, "TARGET" in roles)
    curves = _scale_curves(mask)
    if abs(radius - old) <= 1e-6 * radius or not curves:
        return
    ratio = radius / old
    speed = float(mask.get(P_SPEED, 0.0))  # the hand path keeps its pace: the keys move later instead
    for fc in curves:
        first = fc.keyframe_points[0].co[0]
        for key in fc.keyframe_points:
            key.co[1] *= ratio
            key.handle_left[1] *= ratio
            key.handle_right[1] *= ratio
            if speed > 0.0 and settings.direction == "GROW":
                key.co[0] = key.handle_left[0] = key.handle_right[0] = first + key.co[1] / speed
        fc.update()
    if speed > 0.0 and settings.direction == "GROW":
        settings.frame_end = int(math.ceil(curves[0].keyframe_points[-1].co[0]))
    mask[P_REACH] = radius
    for ob in objects:  # recorded for the old timing: follow the body until the next build
        launch.remove(ob)
    frame = settings.id_data.frame_current
    for fc in curves:  # show the new radius now, not only after the next frame change
        mask.scale[fc.array_index] = fc.evaluate(frame)


# --------------------------------------------------------------------------- objects

def _move_after_armature(ob, mod):
    """Place our modifier right after the last Armature modifier (before outlines etc.)."""
    mods = list(ob.modifiers)
    arm = [i for i, m in enumerate(mods) if m.type == "ARMATURE"]
    target = arm[-1] + 1 if arm else 0
    current = mods.index(mod)
    if current != target:
        ob.modifiers.move(current, target)


def _prepare_mesh(ob, role, mask, group, patterns):
    ob[P_MASK] = mask
    ob[P_ROLE] = role
    ob[P_REST] = int(ob.add_rest_position_attribute)
    ob.add_rest_position_attribute = True
    locked = mdl.write_lock_attribute(ob, patterns)
    mod = ob.modifiers.new(MOD_NAME, "NODES")
    mod.node_group = group
    _move_after_armature(ob, mod)
    return locked


def _shares_skeleton(ob, armature, threshold=0.8):
    """True when most of the mesh's vertex groups are bones of `armature`."""
    groups = [vg.name for vg in ob.vertex_groups if not vg.name.startswith("mmd_")]
    if not groups:
        return True
    bones = armature.data.bones
    return sum(1 for name in groups if name in bones) >= threshold * len(groups)


def _bind_to_armature(meshes, armature):
    """Let the new outfit follow the old model's armature (same MMD skeleton).

    Returns the meshes that were left alone because their bone names do not match."""
    skipped = []
    for ob in meshes:
        if not _shares_skeleton(ob, armature):
            skipped.append(ob.name)
            continue
        saved = {}
        for mod in ob.modifiers:
            if mod.type == "ARMATURE":
                saved[mod.name] = mod.object.name if mod.object else ""
                mod.object = armature
        if saved:
            ob[P_ARM] = saved
    return skipped


def _contains_skeleton(armature, source, threshold=0.8):
    """True when `armature` has most of the bones of `source` (e.g. the same skeleton plus skirt bones)."""
    bones = source.data.bones
    return len(bones) > 0 and sum(1 for b in bones if b.name in armature.data.bones) >= threshold * len(bones)


def _copy_pose(armature, source):
    """Make every bone of `armature` that `source` also has copy that bone's local pose, so a new outfit
    with extra bones (skirt, ribbons ...) still dances along: the extra bones follow their parents.
    Returns how many bones copy."""
    count = 0
    for pb in armature.pose.bones:
        if pb.name not in source.pose.bones:
            continue
        con = pb.constraints.new("COPY_TRANSFORMS")
        con.name = FOLLOW
        con.target = source
        con.subtarget = pb.name
        con.owner_space = con.target_space = "LOCAL"
        count += 1
    return count


def _uncopy_pose(armature):
    for pb in armature.pose.bones:
        for con in [c for c in pb.constraints if c.name.startswith(FOLLOW)]:
            pb.constraints.remove(con)


def _cleanup_mesh(ob):
    for mod in list(ob.modifiers):
        if mod.type == "NODES" and mod.node_group and mod.node_group.name in (TARGET_GROUP, BASE_GROUP):
            ob.modifiers.remove(mod)
    if ob.get(P_ROLE) in ("TARGET", "BASE"):
        for slot in ob.material_slots:
            if slot.material is not None:
                materials.remove_husk(slot.material)
                materials.remove_edge_glow(slot.material)
                materials.remove_hologram(slot.material)
                materials.remove_inner_glow(slot.material)
                materials.remove_layer(slot.material)
                materials.remove_surface(slot.material)
                materials.remove_shadow(slot.material)
                materials.remove_paint(slot.material)
    saved = ob.get(P_ARM)
    if saved:
        for mod_name, arm_name in saved.to_dict().items():
            mod = ob.modifiers.get(mod_name)
            if mod is not None and mod.type == "ARMATURE":
                mod.object = bpy.data.objects.get(arm_name) if arm_name else None
    if P_REST in ob:
        ob.add_rest_position_attribute = bool(ob[P_REST])
    if ob.type == "MESH":
        mdl.remove_lock_attribute(ob)
        arrival.remove(ob)
        launch.remove(ob)
        venom.remove(ob)
    for key in (P_MASK, P_ROLE, P_REST, P_ARM):
        if key in ob:
            del ob[key]


def _restore_root(root):
    for con in [c for c in root.constraints if c.name.startswith(FOLLOW)]:
        root.constraints.remove(con)
    flat = root.get(P_MATRIX)  # effects built before 1.4 moved the root itself
    if flat is not None:
        flat = list(flat)
        root.matrix_basis = Matrix([flat[0:4], flat[4:8], flat[8:12], flat[12:16]])
        del root[P_MATRIX]


def effect_objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_MASK) == mask]


def remove_effect(mask):
    for ob in effect_objects(mask):
        _cleanup_mesh(ob)
    for root_name in list(mask.get(P_ROOTS, [])):
        root = bpy.data.objects.get(root_name)
        if root is not None:
            _restore_root(root)
    for arm_name in list(mask.get(P_FOLLOWERS, [])):
        arm = bpy.data.objects.get(arm_name)
        if arm is not None and arm.type == "ARMATURE":
            _uncopy_pose(arm)
    for scene in bpy.data.scenes:  # the white flash node stays, switched off until the next build drives it
        settings = getattr(scene, "mmd_disperse", None)
        if settings is not None and settings.mask == mask:
            compositor.update_white_flash(scene, None, 0.0, 0.0, 0.0, 0.0)
            compositor.update_impact(scene, None, 0)
            compositor.remove_look(scene)
    ribbons.remove(mask)
    rings.remove(mask)
    impact.remove(mask)
    domain.remove(mask)
    shots.remove(mask)
    timewarp.restore(mask)
    toon.remove(mask)
    trails.remove(mask)
    action = mask.animation_data.action if mask.animation_data else None
    bpy.data.objects.remove(mask)
    if action is not None and action.users == 0:
        bpy.data.actions.remove(action)
    if not any(ob.type == "EMPTY" and ob.name.startswith(MASK_NAME) for ob in bpy.data.objects):
        particles.remove_assets()
        goo = bpy.data.materials.get(materials.GOO_MATERIAL)
        if goo is not None and goo.users == 0:
            bpy.data.materials.remove(goo)


# --------------------------------------------------------------------------- settings -> scene

def _glow_materials(ob, settings, locked=False):
    """Materials of an outfit mesh that may glow (locked parts never break or show the rim), or with `locked` the
    locked ones."""
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    for slot in ob.material_slots:
        mat = slot.material
        if mat is None or mat.name == WIRE_MATERIAL:
            continue
        name = mdl.material_key(mat)
        if any(fnmatch.fnmatchcase(name, p) for p in patterns) == locked:
            yield mat


def _update_glow(ob, settings, enabled, strength):
    # the evolution flash, the shadow and the transporter beam light up the locked parts (head, hair) too
    whole = settings.entrance in ("EVOLVE", "SHADOW", "BEAM") and ob.get(P_ROLE) == "BASE"
    for locked in (False, True):
        for mat in _glow_materials(ob, settings, locked):
            if enabled and (whole or not locked):
                materials.add_edge_glow(mat)
                materials.update_edge_glow(mat, settings.glow_color, strength)
            else:
                materials.remove_edge_glow(mat)


def _update_shadow(ob, settings):
    """Rising from the shadow: every material of the outfit (the locked head too) can turn into the black shadow."""
    for slot in ob.material_slots:
        mat = slot.material
        if mat is None or mat.name == WIRE_MATERIAL:
            continue
        if settings.entrance == "SHADOW":
            materials.add_shadow(mat)
        else:
            materials.remove_shadow(mat)


def _update_hologram(ob, settings):
    spacing = HOLO_LINE_SPACING * max(settings.size_reference, 1e-3)
    for mat in _glow_materials(ob, settings):
        if settings.holo_enable:
            materials.add_hologram(mat, settings.holo_style)
            materials.update_hologram(mat, settings.glow_color, settings.holo_strength, settings.holo_opacity,
                                      spacing)
        else:
            materials.remove_hologram(mat)


def _update_inner_glow(ob, settings):
    for mat in _glow_materials(ob, settings):
        if settings.inner_glow:
            materials.add_inner_glow(mat)
            materials.update_inner_glow(mat, settings.glow_color, settings.inner_glow_strength)
        else:
            materials.remove_inner_glow(mat)


def _update_layer(ob, settings):
    # the cells sit on the rest position, which is in object units
    height = max(settings.size_reference, 1e-3) / _object_scale(ob)
    goo = (settings.venom_color, GOO_CELL * height, settings.venom_metallic) if settings.layer_style == "GOO" else None
    for mat in _glow_materials(ob, settings):
        if settings.layer_enable:
            materials.add_layer(mat)
            materials.update_layer(mat, settings.layer_color, settings.glow_color, settings.layer_lines,
                                   LAYER_CELL * height, goo)
        else:
            materials.remove_layer(mat)


def _update_paint(ob, settings):
    height = max(settings.size_reference, 1e-3) / _object_scale(ob)  # (the cells sit on the rest position)
    for mat in _glow_materials(ob, settings):
        if settings.paint_style != "NONE":
            materials.add_paint(mat)
            # line art 0, ink wash 1, the digital rain 2
            materials.update_paint(mat, float(PAINT_STYLES.index(settings.paint_style) - 1), settings.paper_color,
                                   settings.ink_color, PAINT_CELL * height, settings.glow_color, CODE_CELL * height)
        else:
            materials.remove_paint(mat)


def _update_surface(ob, settings):
    height = max(settings.size_reference, 1e-3) / _object_scale(ob)
    cell = SURFACE_CELL * height
    for mat in _glow_materials(ob, settings):
        if settings.old_surface != "NONE":
            materials.add_surface(mat, settings.old_surface)
            materials.update_surface(mat, settings.surface_color, settings.glow_color, cell, settings.venom_metallic,
                                     settings.ice_clarity, CODE_CELL * height)
            if settings.old_surface == "INK":  # its drawing uses the paint colours (and its cells)
                materials.update_paint(mat, 1.0, settings.paper_color, settings.ink_color,
                                       PAINT_CELL * max(settings.size_reference, 1e-3) / _object_scale(ob))
        else:
            materials.remove_surface(mat)


def _update_husk(ob, settings):
    """The husk: every material of the old outfit (its head and hair are left behind too) shows it as the husk style."""
    for slot in ob.material_slots:
        mat = slot.material
        if mat is None or mat.name == WIRE_MATERIAL:
            continue
        if settings.exit_style == "HUSK":
            materials.add_husk(mat)
            materials.update_husk(mat, settings.husk_style, settings.glow_color)
        else:
            materials.remove_husk(mat)


def _venom_owners(objects):
    """The meshes the symbiote's tendrils run over: the old outfit's, or the new one's when there is no old one."""
    meshes = [ob for ob in objects if ob.type == "MESH" and ob.get(P_ROLE) in ("BASE", "TARGET")]
    role = "BASE" if any(ob.get(P_ROLE) == "BASE" for ob in meshes) else "TARGET"
    return [ob for ob in meshes if ob.get(P_ROLE) == role]


def _update_venom(settings, mask, objects):
    """Trace the tendrils and strands when the symbiote is on (again when what they depend on or the mesh changed),
    drop them when it is off. Returns the goo material (None when off)."""
    owners = _venom_owners(objects) if settings.venom_enable else []
    for ob in objects:
        if ob.type == "MESH" and ob not in owners and venom.skeleton(ob) is not None:
            venom.remove(ob)
    if not owners:
        return None
    arrival_path = mask.get(P_PATH, "SPHERE") != "SPHERE"
    height = max(settings.size_reference, 1e-3)
    scene = settings.id_data
    for ob in owners:
        if not venom.matches(ob, venom.signature(settings, _object_scale(ob))):
            values = venom.field_values(ob, mask.matrix_world.translation, arrival_path)
            # strands are also looked for in the poses the body takes while it transforms
            start, end = settings.frame_start, max(settings.frame_end, settings.frame_start + 1)
            frames = [int(round(start + (end - start) * (i + 1) / (venom.POSES + 1))) for i in range(venom.POSES)]
            poses, key = venom.sample_poses(scene, ob, frames, objects) if settings.venom_strands > 0 else ([], None)
            venom.build(ob, values, settings, height, scene, poses, key)
    goo = materials.ensure_goo_material()
    materials.update_goo_material(settings.venom_color, GOO_CELL * height, settings.venom_metallic)
    return goo


def _update_ribbons(settings, mask, snap):
    """Create / recreate / remove the limb ribbons and the cocoon's silk threads to match the panel (they need the
    built effect); the threads snap at the mask radius `snap` (None: after the edge)."""
    meshes = [ob for ob in effect_objects(mask) if ob.type == "MESH"]
    old = [ob for ob in meshes if ob.get(P_ROLE) == "BASE"]
    collection = mask.users_collection[0] if mask.users_collection else settings.id_data.collection
    height = max(settings.size_reference, 1e-3)
    for kind, wanted, around in ((ribbons.LIGHT, settings.ribbon_enable, meshes),
                                 (ribbons.SILK, settings.old_surface == "SILK" and settings.silk_threads, old)):
        current = ribbons.ribbon_objects(mask, kind)
        if not wanted or any(ribbons.stale(ob, settings) for ob in current):
            ribbons.remove(mask, kind)
            current = []
        if wanted and not current and around:
            owner = next((ob for ob in around if ob.get(P_ROLE) == "BASE"), around[0])
            ribbons.create(settings, mask, around, mdl.find_armature(owner), height, collection, kind)
    ribbons.sync(settings, mask, snap)


def _update_ring(settings, mask, beat):
    """Create / remove the front's decoration to match the panel (sweeps and the spiral only) and push its values."""
    layout = mask.get(P_LAYOUT)
    current = rings.ring_objects(mask)
    if not settings.ring_enable or layout is None:
        if current:
            rings.remove(mask)
        return
    if not current:
        root = bpy.data.objects.get(mask.get(P_ROOT, ""))
        collection = mask.users_collection[0] if mask.users_collection else settings.id_data.collection
        rings.create(mask, layout, root, collection)
    rings.sync(settings, mask, layout.to_dict(), beat)


def _update_world(settings, mask, wave, big):
    """Create / remove the world change to match the panel and push its values: it opens round the middle of the
    body, past wherever the camera is while it is there."""
    current = domain.world_objects(mask)
    meshes = [ob for ob in effect_objects(mask) if ob.type == "MESH" and ob.get(P_ROLE) in ("BASE", "TARGET")]
    if not settings.domain_enable or wave <= 0.0 or not meshes:
        if current:
            domain.remove(mask)
        return
    if not current:
        collection = mask.users_collection[0] if mask.users_collection else settings.id_data.collection
        domain.create(mask, collection)
    lo, hi = mdl.rest_bounds(meshes)
    height = max(hi.z - lo.z, 1e-3)
    centre = _focus(mask)
    open_end, close_start, close_end = _world_times(settings, wave, big)
    last = _frame_at(mask, close_end)
    first = settings.frame_start
    last = int(last) if last is not None else max(settings.frame_end, first + 1)
    reach = domain.camera_reach(settings.id_data, mask, centre, first, last, height)
    domain.sync(settings, mask, centre, lo.z, height, open_end, close_start, close_end, reach)


def _particle_object(settings):
    """Object the old outfit's particles are made of (built-in petal / butterfly, or the user's)."""
    if settings.particles == "OBJECT":
        return settings.particle_object
    if settings.particles in particles.NAMES:
        return particles.ensure_asset(settings.particles, settings.id_data)
    return None


def _radius_step(mask, radius):
    """How much the mask radius changes per frame where it passes `radius` (0 when it never does)."""
    curves = _scale_curves(mask)
    keys = curves[0].keyframe_points if curves else []
    if len(keys) < 2:
        return 0.0
    fc = curves[0]
    frame, last = keys[0].co[0], keys[-1].co[0]
    before = fc.evaluate(frame)
    while frame < last:
        after = fc.evaluate(frame + 0.25)
        if (before - radius) * (after - radius) <= 0.0 and after != before:
            return abs(after - before) * 4.0
        before, frame = after, frame + 0.25
    return 0.0


def _radius_at(mask, frames):
    """The mask radius `frames` frames after its first key (0 without keys)."""
    curves = _scale_curves(mask) if mask is not None else []
    keys = curves[0].keyframe_points if curves else []
    if len(keys) < 2:
        return 0.0
    return float(curves[0].evaluate(keys[0].co[0] + frames))


def _striking(settings):
    """True when lightning strikes the start point as the transformation begins."""
    return settings.arc_enable and settings.arc_strike and settings.direction == "GROW"


def _from_move(settings, mask):
    """True when a move of the dance (a clap ...) was found and the front sets off from it."""
    return settings.trigger in motion.GESTURES and mask is not None and mask.get(P_TRIGGER, -1.0) >= 0.0


def _impact_start(settings, mask, wave):
    """Mask radius the impact frames (and the shockwave) start at: as the front sets off when a move of the dance
    starts it, otherwise a frame after the big moment (the swap, or the new outfit complete), when its glow is up and
    the figure stands out of a dark stage in black and white."""
    if _from_move(settings, mask):
        return max(0.5 * _radius_at(mask, 1.0), 1e-6)
    big = _finale_start(settings, wave, mask)
    return big + (_radius_step(mask, big) if mask is not None else 0.0)


def _focus(mask):
    """World point the speed lines rush towards: the middle of the body, a little above (the chest)."""
    meshes = [ob for ob in effect_objects(mask) if ob.type == "MESH" and ob.get(P_ROLE) in ("BASE", "TARGET")]
    if not meshes:
        return None
    lo, hi = mdl.rest_bounds(meshes)
    return Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z + 0.62 * (hi.z - lo.z)))


def update_impact(settings):
    """Drive the impact frames (when the compositor has them) and the speed lines from the current effect."""
    mask = settings.mask
    scene = settings.id_data
    wave = float(mask.get(P_WAVE, 0.0)) if mask is not None else 0.0
    if mask is None or wave <= 0.0 or not settings.impact_enable:
        compositor.update_impact(scene, None, 0)
        if mask is not None:
            impact.remove(mask)
        return
    # the first whole frame at which the mask radius gets there, counted on in frames from it (the mask keys as they
    # are now: this runs again whenever the effect syncs)
    at = _frame_at(mask, _impact_start(settings, mask, wave))
    first = None if at is None else int(math.ceil(at - 1e-6))
    compositor.update_impact(scene, first, settings.impact_frames)
    camera = shots.carrier(scene, mask)
    if settings.speed_lines and camera is not None and first is not None:
        if any(ob.parent != camera for ob in impact.sheets(mask)):  # (a camera move came or went)
            impact.remove(mask)
        if not impact.sheets(mask):
            collection = mask.users_collection[0] if mask.users_collection else scene.collection
            impact.create(scene, mask, collection, camera)
        impact.sync(scene, mask, _focus(mask), first, settings.impact_frames, shots.user_camera(scene, mask))
    else:
        impact.remove(mask)


def _big_frame(settings, mask, wave):
    """The first whole frame of the big moment (where the impact frames start: a frame after the swap or the new
    outfit complete, or as the front sets off from a move of the dance); None without mask keys."""
    if mask is None or wave <= 0.0:
        return None
    at = _frame_at(mask, _impact_start(settings, mask, wave))
    return None if at is None else int(math.ceil(at - 1e-6))


def _models(settings):
    return [m for m in (mdl.resolve(settings.base) if settings.base else None,
                        mdl.resolve(settings.target) if settings.target else None) if m]


LOOK_BEFORE = 0.4  # share of the look's time it comes before the big moment


def _update_look(settings, moment):
    """The picture's look round the big moment (compositor.update_look): on from a little before it for Look Time;
    the dancer it picks out (the silhouette, the colour that stays, the painted figure) is both outfits."""
    scene = settings.id_data
    if settings.look_style == "NONE" or moment is None:
        compositor.remove_look(scene)
        return
    fps = scene.render.fps / scene.render.fps_base
    span = max(int(round(settings.look_length * fps)), 1)
    first = moment - int(round(LOOK_BEFORE * span))
    dancer = [ob for m in _models(settings) for ob in m.meshes]
    try:
        compositor.update_look(scene, settings.look_style, first, first + span, dancer, tuple(settings.look_color))
    except RuntimeError:  # (no compositor output)
        pass


def update_white_flash(settings):
    """Drive the compositor's white flash (when the scene has one) from the current effect's finale: it comes up
    within a frame where the finale starts and is gone about six frames later, however long the finale is. When
    lightning strikes at the start the picture flashes white then too, for a frame or two."""
    mask = settings.mask
    wave = float(mask.get(P_WAVE, 0.0)) if mask is not None else 0.0
    start = _finale_start(settings, wave, mask) if wave > 0.0 else 0.0
    step = _radius_step(mask, start) if mask is not None else 0.0
    if step <= 0.0:  # no keys to measure: a share of the finale instead
        step = 0.05 * settings.finale_length * wave
    if settings.impact_enable and wave > 0.0 and not _from_move(settings, mask):
        # the impact frames first, then the flash (it would wash them out)
        start = _impact_start(settings, mask, wave) + settings.impact_frames * step
    amount = settings.finale_white if settings.finale else 0.0
    strike = None
    if _striking(settings) and _radius_at(mask, STRIKE_FRAMES) > 0.0:  # a frame or two, the bolt shows after it
        strike = (max(_radius_at(mask, 1.0), 1e-6), _radius_at(mask, 3.0), 0.8 * settings.finale_white)
    compositor.update_white_flash(settings.id_data, mask, start, step, 6.0 * step, amount, strike)


def _signatures(settings, role, s):
    """What the recorded moments of a mesh depend on besides the mask keys, in object space (`s` is its scale):
    (its vertices', its pieces'). A recording that does not match any more is dropped (launch.py)."""
    mask = settings.mask
    wave = float(mask.get(P_WAVE, 0.0)) if mask is not None else 0.0
    synced = settings.beat_sync and beats.beat_object() is not None  # moments on the beat move with the beats
    if role == "BASE":
        at_once = (_moment(settings, wave, mask) / s,) if _old_at_once(settings) else ()
        return at_once, (settings.piece_size / s,) + at_once
    layer = _layer(settings) / s  # the finale starts when the final look is complete
    if settings.finale_style == "SWEEP":
        stars = (1.0, settings.finale_length, settings.finale_width / s, layer)
    else:
        stars = (0.0, layer)
    if settings.entrance in AT_ONCE:  # ... or when the halves clamp shut / the ghosts meet
        stars += (1.0,)
    if synced:
        stars += (_finale_start(settings, wave, mask) / s,)
    return stars, (settings.piece_size / s, settings.fly_range / s, float(settings.subdivide))


def _record_parts(settings, role, shown=False):
    """(vertices, pieces): which moments of a mesh of `role` leave behind records with the current settings, or with
    `shown` only those the current settings show. The old outfit's vertices are recorded with its chunks too, so
    switching between flakes and chunks needs no new recording."""
    if role == "BASE":
        pieces = settings.exit_style == "CHUNKS"
        vertices = (settings.exit_style in FLAKES or settings.particles != "NONE"
                    or (settings.exit_style == "HUSK" and settings.husk_motion == "STILL"))
        return vertices or (pieces and not shown), pieces
    stars = settings.finale and settings.finale_sparkles > 0
    # with Subdivide the fly-in pieces are cut from another mesh than the one recorded
    return stars, settings.entrance == "ASSEMBLE" and settings.subdivide == 0


def _recording(settings, role):
    """True when the meshes of `role` are recorded: with leave behind, or the old outfit for its husk (one that holds
    still: a husk dancing beside the dancer is the live old self)."""
    return settings.leave_behind or (role == "BASE" and settings.exit_style == "HUSK" and settings.husk_motion == "STILL")


def missing_recording(settings):
    """True when leave behind (or the husk) is on but some part of the built effect that needs a recording has none
    (rebuild)."""
    if settings.mask is None:
        return False
    for ob in effect_objects(settings.mask):
        if ob.type != "MESH" or ob.get(P_ROLE) not in ("BASE", "TARGET") or not _recording(settings, ob.get(P_ROLE)):
            continue
        vertices, chunks = _record_parts(settings, ob.get(P_ROLE), shown=True)
        if (vertices and not launch.has_launch(ob)) or (chunks and not launch.has_launch(ob, chunks=True)):
            return True
    return False


def sync(settings):
    """Push the panel values to every modifier and material of the current effect."""
    mask = settings.mask
    if mask is None:
        return
    objects = effect_objects(mask)
    _retime(settings, mask, objects)
    # 1.11: the dance frozen or slowed round the big moment (before anything below plays it), the camera move then
    wave_big = float(mask.get(P_WAVE, 0.0))
    big_frame = _big_frame(settings, mask, wave_big)
    timewarp.sync(settings, mask, _models(settings), big_frame)
    update_white_flash(settings)
    update_impact(settings)
    models = _models(settings)
    focus = _focus(mask)
    shots.sync(settings, mask, big_frame, focus, models[0].armature if models else None,
               max(settings.size_reference, 1e-3))
    _update_look(settings, big_frame)
    wire = bpy.data.materials.get(WIRE_MATERIAL)
    materials.update_wire_material(wire, settings)
    shape = _particle_object(settings)
    crystal = None
    if settings.old_surface == "FROST" and settings.ice_crystals > 0:
        crystal = particles.ensure_asset("CRYSTAL", settings.id_data)
    sparkle = None
    if settings.finale and settings.finale_sparkles > 0:
        sparkle = particles.ensure_asset("STAR", settings.id_data)
    materials.update_particle_material(settings)
    materials.update_outline_material(settings.ink_color)
    wave_now = float(mask.get(P_WAVE, 0.0))
    _update_ribbons(settings, mask, _moment(settings, wave_now, mask) if _old_at_once(settings) else None)
    goo = _update_venom(settings, mask, objects)
    beat = beats.beat_object() if settings.beat_sync else None
    _update_ring(settings, mask, beat)
    compositor.update_glitch(settings.id_data, settings.frame_start, settings.frame_end, settings.glitch_rate,
                             beat=beat)
    height = max(settings.size_reference, 1e-3)
    # Lightning runs over the new outfit (the old one when there is none); one mesh of the effect (the biggest of
    # those) draws what there is once: the strike, the transporter beam's column.
    meshes = [ob for ob in objects if ob.type == "MESH" and ob.get(P_ROLE) in ("BASE", "TARGET")]
    arc_role = "TARGET" if any(ob.get(P_ROLE) == "TARGET" for ob in meshes) else "BASE"
    main = max((ob for ob in meshes if ob.get(P_ROLE) == arc_role), key=lambda ob: len(ob.data.vertices),
               default=None)
    arc_area = float(mask.get(P_AREA_NEW if arc_role == "TARGET" else P_AREA, 0.0))
    # about Arc Count arcs where the edge crosses the body: the faces within Arc Reach of it are about 2 reach / height
    # of the outfit
    arc_density = (settings.arc_count * height / (2.0 * max(settings.arc_reach, 1e-6) * arc_area)
                   if arc_area > 0.0 else 0.0)
    if settings.arc_enable:
        materials.ensure_arc_material()
    materials.update_arc_material(settings)
    beam = settings.entrance == "BEAM"
    if beam:
        materials.ensure_beam_material()
    materials.update_beam_material(settings)
    strike_until = _radius_at(mask, STRIKE_FRAMES) if _striking(settings) else 0.0
    # 1.10: the lotus, flames, the shockwave and the soul rings, timed by the big moment
    scene = settings.id_data
    wave_at = float(mask.get(P_WAVE, 0.0))
    big = _finale_start(settings, wave_at, mask)
    # 1.11: the dance ribbons and the flowers underfoot (whose lotus shares the lotus entrance's material)
    models = _models(settings)
    trails.sync(settings, mask, next(iter(models), None), [ob for m in models for ob in m.meshes])
    lotus = settings.entrance == "LOTUS"
    if lotus:
        materials.ensure_lotus_material()
    materials.update_lotus_material(settings.particle_color, settings.glow_color, settings.edge_glow_strength)
    if settings.flame_enable:
        materials.ensure_flame_material()
    materials.update_flame_material(settings.flame_color, settings.flame_strength, height)
    shock = settings.impact_enable and settings.shockwave
    if shock:
        materials.ensure_shock_material()
    materials.update_shock_material(settings.glow_color, 1.5 * settings.edge_glow_strength)
    if settings.soul_enable:
        materials.ensure_soul_material()
    materials.update_soul_material(settings.soul_strength)
    shock_start = _impact_start(settings, mask, wave_at) if wave_at > 0.0 else 0.0
    _update_world(settings, mask, wave_at, big)
    # 1.11: cartoon physics at the big moment (the first frame of it: the swap, or the new outfit complete), about an
    # anchor under the old model's hips; the float lands then
    landing = _frame_at(mask, big) if wave_at > 0.0 else None
    landing = None if landing is None else int(math.ceil(landing - 1e-6))
    toon_anchor = toon.sync(settings, mask, next(iter(_models(settings)), None), settings.frame_start, landing)
    fps = scene.render.fps / scene.render.fps_base
    common = {
        "Mask": mask,
        "Use Rest Position": settings.space == "REST",
        "Use Arrival": mask.get(P_PATH, "SPHERE") != "SPHERE",
        "Noise Scale": settings.noise_scale,
        "Noise Detail": settings.noise_detail,
        "Noise Amount": settings.noise_amount,
        "Glitch": settings.glitch_enable,
        "Glitch Width": settings.glitch_width,
        "Slice Height": settings.glitch_slice,
        "Glitch Rate": settings.glitch_rate,
        "Glitch Shift": settings.glitch_shift,
        "Glitch Flash": settings.glitch_flash,
        "Beat Sync": beat is not None,
        "Beat Object": beat,
        "Leave Behind": settings.leave_behind,
        "Inner Glow": settings.inner_glow,
        "Inner Depth": settings.inner_depth,
        "Tendril Radius": settings.venom_thickness,
        "Tendril Speed": settings.venom_speed,
        "Tendril Absorb": ABSORB * settings.venom_length,
        "Strand Life": STRAND_LIFE * settings.venom_length,
        "Venom Material": goo,
        "Edge Glow": settings.edge_glow,
        "Scales": settings.entrance == "SCALES",
        "Scale Size": settings.scale_size,
        "Flip Width": settings.flip_width,
        "Evolve": settings.entrance == "EVOLVE",
        "Shadow": settings.entrance == "SHADOW",
        "Shadow Direction": tuple(settings.shadow_dir),
        "Beam": beam,
        "Arc Length": settings.arc_length,
        "Arc Reach": settings.arc_reach,
        "Arc Thickness": settings.arc_thickness,
        "Arc Material": bpy.data.materials.get(materials.ARC_MATERIAL),
        "Strike Until": strike_until,
        "Strike Height": STRIKE_HEIGHT * height,
        "Beam Count": settings.beam_sparkles,
        "Beam Material": bpy.data.materials.get(materials.BEAM_MATERIAL),
        "Star Object": particles.ensure_asset("STAR", settings.id_data) if beam else None,
        "Star Size": settings.particle_size,
        "Swap": settings.entrance == "SWAP",
        "Lotus": lotus,
        "Lotus Petals": settings.lotus_petals,
        "Lotus Material": bpy.data.materials.get(materials.LOTUS_MATERIAL),
        "Flames": settings.flame_enable,
        "Flame Aura": settings.flame_mode == "AURA",
        "Flame Width": settings.flame_width,
        "Flame Height": settings.flame_height,
        "Flame Start": 0.05 * big,
        "Flame Peak": big,
        "Flame End": big + FLAME_AFTER * wave_at,
        "Flame Material": bpy.data.materials.get(materials.FLAME_MATERIAL),
        "Camera": scene.camera,
        "Shock": shock,
        "Shock Start": shock_start,
        "Shock End": shock_start + SHOCK_SPAN * wave_at,
        "Shock Size": settings.shock_size,
        "Shock Material": bpy.data.materials.get(materials.SHOCK_MATERIAL),
        "Dust Material": materials.ensure_dust_material() if shock else None,
        "Soul Rings": settings.soul_count if settings.soul_enable else 0,
        "Soul Start": 0.0,
        "Soul Peak": SOUL_PEAK * big,
        "Soul End": big + SOUL_AFTER * wave_at,
        "Soul Material": bpy.data.materials.get(materials.SOUL_MATERIAL),
        "Toon": toon.SHAPES.get(settings.toon_style, 0) if toon_anchor is not None and landing is not None else 0,
        "Toon Frame": float(landing or 0),
        "Toon Rate": 30.0 / max(fps, 1e-3),
        "Toon Anchor": toon_anchor,
        "Toon Gap": toon.GAP * height,
        "Card Material": bpy.data.materials.get(materials.TOON_CARD_MATERIAL),
    }
    values = {
        TARGET_GROUP: dict(common, **{
            "Subdivide": settings.subdivide,
            "Edge Width": settings.edge_width,
            "Edge Push": settings.edge_push,
            "Wire": settings.wire_enable,
            "Hex Wire": settings.wire_hex,
            "Wire Inner": settings.wire_inner,
            "Wire Outer": settings.wire_outer,
            "Wire Radius": settings.wire_radius,
            "Wire Lift": settings.wire_lift,
            "Wire Resolution": settings.wire_resolution,
            "Wire Material": wire,
            "Hologram": settings.holo_enable,
            "Hologram Width": settings.holo_width,
            "Assemble": settings.entrance == "ASSEMBLE",
            "Piece Size": settings.piece_size,
            "Fly Distance": settings.fly_distance,
            "Fly Range": settings.fly_range,
            "Spin": settings.frag_spin,
            "Finale": settings.finale,
            # the material multiplies the stored flash by the edge glow strength
            "Finale Glow": settings.finale_glow / max(settings.edge_glow_strength, 1e-3),
            "Sparkles": sparkle is not None,
            "Sparkle Object": sparkle,
            "Sparkle Size": settings.particle_size,
            "Sparkle Distance": settings.finale_distance,
            "Finale Sweep": settings.finale_style == "SWEEP",
            "Sweep Width": settings.finale_width,
            "Undersuit": settings.layer_enable,
            "Undersuit Width": settings.layer_width,
            "Goo": settings.layer_enable and settings.layer_style == "GOO",
            "Clamp": settings.entrance == "CLAMP",
            "Ghosts": settings.entrance == "GHOSTS",
            "Ghost Count": settings.ghost_count,
            "Ghost Distance": settings.ghost_distance,
            "Reactor": settings.reactor,
            "Reactor Size": settings.reactor_size,
            "Plates": settings.plates,
            "Plate Size": settings.plate_size,
            "Plate Lift": settings.plate_lift,
            "Plate Width": settings.plate_width,
            "Paint Style": PAINT_STYLES.index(settings.paint_style),
            "Paint Width": settings.paint_width,
            "Sketch Width": settings.sketch_width,
            "Outline Width": settings.outline_width,
            "Outline Material": materials.ensure_outline_material() if settings.paint_style != "NONE" else None,
            "Poof": settings.entrance == "POOF",
            "Smoke Size": settings.smoke_size,
            "Smoke Material": materials.ensure_smoke_material() if settings.entrance == "POOF" else None,
        }),
        BASE_GROUP: dict(common, **{
            "Shrink": settings.base_shrink,
            "Delete Offset": settings.base_delete_offset,
            "Fragments": settings.exit_style in FLAKES,
            "Suck": settings.exit_style == "SUCK",
            "Suck Turns": settings.suck_turns,
            "Brooch Object": (particles.ensure_asset("STAR", settings.id_data) if settings.exit_style == "SUCK"
                              else None),
            "Chunks": settings.exit_style == "CHUNKS",
            "Piece Size": settings.piece_size,
            "Chunk Force": settings.chunk_force,
            "Silhouette": settings.silhouette,
            "Silhouette Width": settings.silhouette_width,
            "Flake Size": settings.frag_size,
            "Flake Subdivide": settings.frag_subdivide,
            "Burst": settings.frag_burst,
            "Turbulence": settings.frag_turbulence,
            "Spin": settings.frag_spin,
            "Flake Glow": settings.frag_glow,
            "Particles": shape is not None,
            "Particle Object": shape,
            "Flap": settings.particles in particles.FLAPPING,
            "Upright": settings.particles in particles.UPRIGHT,
            "Flap Speed": settings.flap_speed,
            "Particle Size": settings.particle_size,
            "Surface Ahead": settings.old_surface != "NONE",
            "Surface Reach": settings.surface_width,
            "Crystals": crystal is not None,
            "Crystal Object": crystal,
            "Crystal Size": settings.crystal_size,
            "Clamp": _old_at_once(settings),  # the old outfit goes all at once
            "Swell": settings.silk_swell if settings.old_surface == "SILK" else 0.0,
            "Glyphs": settings.particles in particles.VARIANTS,
            "Husk": settings.exit_style == "HUSK",
            "Husk Hold": settings.husk_hold * wave_at,
            "Husk Span": settings.husk_time * wave_at,
            "Husk Float": settings.husk_away == "FLOAT",
            "Husk Rise": HUSK_RISE * height,
            "Husk Dance": settings.husk_motion == "DANCE",
            "Split Slide": SPLIT_SLIDE * wave_at,
            "Split Mirror": settings.split_mirror,
            "Husk Figurine": settings.husk_away == "FIGURINE",
            "Stand Material": materials.ensure_stand_material() if settings.husk_away == "FIGURINE" else None,
            # the husk is the old outfit at one moment: all of it goes then, none of it a little before or after
            "Clamp Jitter": 0.0 if settings.exit_style == "HUSK" else 0.04,
        }),
    }
    reach = float(mask.get(P_REACH, 0.0)) or 1e6
    wave = float(mask.get(P_WAVE, 0.0)) or reach
    area = float(mask.get(P_AREA, 0.0))
    density = settings.particle_count / area if area > 0.0 else 0.0
    area_new = float(mask.get(P_AREA_NEW, 0.0))
    sparkle_density = settings.finale_sparkles / area_new if area_new > 0.0 else 0.0
    wind = Vector(settings.frag_wind_dir)
    wind = wind.normalized() * settings.frag_wind if wind.length > 1e-9 else Vector((0.0, 0.0, 0.0))
    moment = _moment(settings, wave, mask)  # (on the beat with beat sync)
    finale_start = _finale_start(settings, wave, mask)
    for ob in objects:
        role = ob.get(P_ROLE)
        # Node trees work in object space: world distances shrink with the object's scale (densities and
        # frequencies grow), so a scaled model looks the same as an unscaled one.
        s = _object_scale(ob)
        skeleton = venom.skeleton(ob)
        flame_area = float(mask.get(P_AREA_NEW if role == "TARGET" else P_AREA, 0.0))
        flame_density = settings.flame_count / flame_area if flame_area > 0.0 else 0.0
        own = {"Reach": reach, "Venom": skeleton is not None, "Venom Skeleton": skeleton, "Clamp Distance": moment,
               "Flame Density": flame_density * s * s,
               "Main": ob == main, "Arcs": settings.arc_enable and role == arc_role, "Arc Density": arc_density * s * s,
               "Strike": _striking(settings) and ob == main,
               "Code": (role == "TARGET" and settings.paint_style == "CODE")
               or (role == "BASE" and settings.old_surface == "CODE")}
        if role in ("BASE", "TARGET") and launch.space(ob) is not None:
            # A recording made with other settings (piece size, the finale's timing ...) does not match any more:
            # those pieces follow the body again until the next build records them.
            for chunks, wanted in enumerate(_signatures(settings, role, s)):
                if launch.has_launch(ob, chunks) and not launch.matches(ob, chunks, wanted):
                    launch.remove(ob, "chunks" if chunks else "vertices")
            if launch.space(ob) is not None:
                own["Launch Space"] = launch.space(ob)
        if role == "BASE":
            own["Split Offset"], own["Figurine Offset"] = _beside(settings, height)
            brooch = mask.get(P_BROOCH)
            if brooch is not None:  # the rest pose is in object space
                own["Suck Target"] = tuple(ob.matrix_world.inverted() @ Vector(brooch))
            own.update({
                "Flight": settings.frag_life * wave,
                "Particle Flight": settings.particle_life * wave,
                "Wind": tuple(wind),  # world direction: the node group turns it into object space every frame
                "Particle Density": density * s * s,
                "Crystal Density": (settings.ice_crystals / area if area > 0.0 else 0.0) * s * s,
            })
        elif role == "TARGET":
            own.update({
                "Hold Until": moment if _held(settings) else 0.0,
                "Finale Start": finale_start,
                "Clamp Offset": settings.clamp_distance,
                "Finale Length": settings.finale_length * wave,
                "Sparkle Density": sparkle_density * s * s,
                "Smoke Density": (settings.smoke_count / area_new if area_new > 0.0 else 0.0) * s * s,
            })
        for mod in ob.modifiers:
            group = mod.node_group if mod.type == "NODES" else None
            if group is None or group.name not in values:
                continue
            ids = input_identifiers(group)
            for name, value in list(values[group.name].items()) + list(own.items()):
                key = ids.get(name)
                if key is None or value is None:
                    continue
                if name in DISTANCE_INPUTS:
                    value = value / s
                elif name == "Noise Scale":
                    value = value * s
                mod[key] = value
            ob.update_tag()
        flashes = settings.glitch_enable and settings.glitch_flash
        evolve = settings.entrance == "EVOLVE"
        if role == "TARGET":
            _update_glow(ob, settings, settings.edge_glow or flashes or settings.finale or evolve or settings.reactor
                         or settings.plates,
                         settings.edge_glow_strength)
            _update_hologram(ob, settings)
            _update_layer(ob, settings)
            _update_paint(ob, settings)
        elif role == "BASE":
            flakes = settings.exit_style in FLAKES + ("CHUNKS",) and settings.frag_glow
            glint = settings.entrance == "SCALES" and settings.edge_glow  # the turning scales glint
            # it glows darkly while it slides into the shadow, or as it shimmers away in the beam
            timeline = settings.entrance in ("SHADOW", "BEAM") and settings.edge_glow
            _update_glow(ob, settings, flakes or flashes or settings.silhouette or glint or evolve or timeline,
                         settings.frag_glow_strength if (flakes or settings.silhouette) and not (evolve or timeline)
                         else settings.edge_glow_strength)
            _update_surface(ob, settings)
            _update_husk(ob, settings)
        if role in ("TARGET", "BASE"):
            _update_inner_glow(ob, settings)
            _update_shadow(ob, settings)


def _beside(settings, height):
    """(world offsets) where the old self steps out to dance beside the dancer, and where its figurine lands: to the
    side the panel says as the scene camera sees it (level), the figurine a little towards the camera too."""
    camera = settings.id_data.camera
    right, toward = Vector((1.0, 0.0, 0.0)), Vector((0.0, -1.0, 0.0))
    if camera is not None:
        m = camera.matrix_world.to_3x3()
        right = Vector((m.col[0].x, m.col[0].y, 0.0))
        toward = Vector((m.col[2].x, m.col[2].y, 0.0))
        right = right.normalized() if right.length > 1e-6 else Vector((1.0, 0.0, 0.0))
        toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    side = 1.0 if settings.split_side == "RIGHT" else -1.0
    step = right * (side * settings.split_distance)
    figurine = (right * (side * FIGURINE_AWAY[0]) + toward * FIGURINE_AWAY[1]) * height
    return tuple(step), tuple(figurine)


def _seeds(settings, location, model):
    seeds = [] if settings.seeds == "LIMBS" else [location]
    if settings.seeds != "ORIGIN":
        seeds += arrival.limb_points(model.armature)
    return seeds or [location]


def _find_move(context, settings, owner, meshes, height):
    """The first move of the kind the panel asks for (Start On) in the old model's motion, from the start frame to the
    end of the scene: a dict with its frame (on the nearest beat with beat sync) and the rest positions and bone names
    the front starts from; None when there is none."""
    scene = context.scene
    fps = scene.render.fps / scene.render.fps_base
    first = settings.frame_start
    frames = list(range(first, max(scene.frame_end, first + 1) + 1))
    track = motion.play(scene, owner.armature, frames, hidden=meshes)
    motion.read_winks(track, owner.meshes)
    hit = motion.find(track, settings.trigger, height, fps)
    if hit is None:
        return None
    index, parts = hit
    frame = float(frames[index])
    if settings.beat_sync:
        frame = motion.snap(frame, beats.beat_frames(), fps)
    points, names = motion.start_points(owner.armature, parts)
    return {"frame": frame, "points": points, "bones": names}


def _hand_arrival(context, settings, owner, meshes, height, location):
    """Hand path: arrival distances (one array per mesh) and the front's pace (world units a frame). A point arrives
    when a hand first sweeps over it during the transformation (a body height of the front for the whole of it), the
    rest of the body in turn from there, along it."""
    scene = context.scene
    start, end = settings.frame_start, max(settings.frame_end, settings.frame_start + 1)
    speed = height / float(end - start)
    sides = {"BOTH": ("L", "R"), "LEFT": ("L",), "RIGHT": ("R",)}[settings.hand_side]
    reach = settings.hand_reach
    if settings.trail_enable and settings.trail_style in ("SLEEVE", "SASH"):
        reach += settings.trail_width  # (the silk sweeps a wider way than the bare hand)
    touches = motion.hand_touches(scene, owner.armature, meshes, range(start, end + 1), sides, reach)
    known = [np.where(np.isfinite(t), (t - start) * speed, np.inf) for t in touches]
    points = [mdl.rest_points_world(ob) for ob in meshes]
    tris = [arrival._triangles(ob) for ob in meshes]
    if any(np.isfinite(k).any() for k in known):
        return arrival.surface_fill(points, tris, known, height), speed
    # the hands never came near the body: flow out from the wrists
    seeds = arrival.limb_points(owner.armature)[:2] or [location]
    return arrival.surface_distances(points, tris, seeds, height), speed


def _shift_keys(mask, delta):
    """Move the mask's keys `delta` frames later."""
    for fc in _scale_curves(mask):
        for key in fc.keyframe_points:
            key.co[0] += delta
            key.handle_left[0] += delta
            key.handle_right[0] += delta
        fc.update()


def _frame_at(mask, radius):
    """First frame (to a quarter) at which the mask radius reaches `radius`; None if it never does."""
    curves = _scale_curves(mask)
    keys = curves[0].keyframe_points if curves else []
    if len(keys) < 2:
        return None
    frame, last = keys[0].co[0], keys[-1].co[0]
    while frame <= last:
        if curves[0].evaluate(frame) >= radius:
            return frame
        frame += 0.25
    return None


def build(context, settings):
    context.view_layer.update()  # matrix_world must reflect recent transform edits
    venom.forget()  # the motion may have changed: look for the strands in its poses again
    target = mdl.resolve(settings.target)
    base = mdl.resolve(settings.base) if settings.base else mdl.Model(None, None, [])
    if not target and not base:
        raise EffectError("Pick the old or the new outfit first")
    if base.root is not None and base.root == target.root:
        raise EffectError("Old and new outfit must be different models")

    # Rebuilding replaces any effect already attached to these meshes (and the dance warped by one is put back first:
    # the moves of the dance and the hands are looked for in it as it is).
    timewarp.restore_models([target, base])
    for ob in target.meshes + base.meshes:
        old = ob.get(P_MASK)
        if isinstance(old, bpy.types.Object):
            remove_effect(old)
        else:
            _cleanup_mesh(ob)

    roots = []
    unbound = []
    followers = []
    copied = 0
    if settings.follow_base and base.armature is not None and target.armature is not None:
        if target.root.type in {"EMPTY", "ARMATURE"} and base.root.type in {"EMPTY", "ARMATURE"}:
            # The new outfit takes the old one's place, also while that moves as a whole (object animation:
            # an armature modifier follows the bones, not the armature object).
            con = target.root.constraints.new("COPY_TRANSFORMS")
            con.name = FOLLOW
            con.target = base.root
            roots.append(target.root.name)
            context.view_layer.update()  # the meshes' matrix_world now include the snap
        unbound = _bind_to_armature(target.meshes, base.armature)
        # Extra bones in the new outfit (skirt, ribbons ...): keep its own armature, copying the old pose.
        if unbound and _contains_skeleton(target.armature, base.armature):
            copied = _copy_pose(target.armature, base.armature)
            followers.append(target.armature.name)
            unbound = []

    # Measured after the snap: the new outfit takes over the old one's transform (and scale).
    lo, hi = mdl.rest_bounds((target or base).meshes)
    height = hi.z - lo.z
    if settings.auto_size and abs(height - settings.size_reference) > 1e-4 * max(height, 1.0):
        fit_sizes(settings, height)

    owner = base if base else target
    meshes = target.meshes + base.meshes
    path = settings.path
    location, bone = _origin(context, settings, owner)
    seeds = []
    layout = None
    t0 = time.time()
    # A move of the dance starts it (Start On): found from the start frame on. A clap, a kiss, a salute or a toss of
    # the head moves the transformation to start there, from the hands or the head; turning away moves it so the swap
    # (or the middle of the wave) comes as the back is turned to the camera (after the mask is made).
    found = None
    if settings.trigger != "NONE" and owner.armature is not None:
        found = _find_move(context, settings, owner, meshes, height)
    if found is not None and settings.trigger in motion.GESTURES:
        length = max(settings.frame_end - settings.frame_start, 1)
        settings.frame_start = int(round(found["frame"]))
        settings.frame_end = settings.frame_start + length
        if found["points"] and path == "SPHERE":
            location, bone = found["points"][0], found["bones"][0]
    speed = 0.0
    if path == "SPHERE":
        reach = mdl.max_distance(meshes, location)
    else:
        if path == "SURFACE":
            moved = found is not None and settings.trigger in motion.GESTURES and found["points"]
            seeds = found["points"] if moved else _seeds(settings, location, owner)
        # Start a little short of the surface so nothing (not even the wire ahead of the edge) shows at
        # radius 0, like the sphere that starts inside the body.
        lead = settings.wire_outer + 0.005 * height
        # sweeps and the spiral follow the model's own axes (it may stand turned in the world)
        frame = (owner.root or meshes[0]).matrix_world.to_3x3().normalized()
        if path == "HAND":
            values, speed = _hand_arrival(context, settings, owner, meshes, height, location)
        else:
            patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
            keys = [[None if s.material is None or any(fnmatch.fnmatchcase(mdl.material_key(s.material), q)
                                                       for q in patterns) else mdl.material_key(s.material)
                     for s in ob.material_slots] for ob in meshes]
            roles = ["TARGET"] * len(target.meshes) + ["BASE"] * len(base.meshes)
            values = arrival.compute(meshes, path, seeds, height, frame, settings.spiral_pitch, owner.armature, roles,
                                     keys, settings.garment_order)
        values = [v + lead for v in values]
        for ob, v in zip(meshes, values):
            arrival.write(ob, v / _object_scale(ob))
        reach = max(float(v.max()) for v in values)
        if path in arrival.LAID_OUT:
            layout = arrival.front_layout(meshes, path, frame, owner.armature)
            location = layout["start"].copy()
            layout["lead"] = lead
    arrival_seconds = time.time() - t0

    margin = settings.noise_amount + max(settings.edge_width, settings.wire_outer) + 0.02 * height
    if path == "SPHERE" and settings.space == "POSED":
        margin += 0.1 * height
    # Flakes, particles, the undersuit and the finale go on after the front has passed: leave them time to finish.
    wave = reach + margin
    radius = wave + _extra(settings, wave, bool(base), bool(target))
    root = target.root or base.root
    collection = root.users_collection[0] if root.users_collection else context.scene.collection
    mask = _create_mask(settings, location, owner.armature, bone, collection, radius, path, owner.root,
                        layout["axis"] if layout else None, speed)
    if speed > 0.0:  # the hand path runs at its own pace: the transformation lasts as long as that takes
        mask[P_SPEED] = speed
        settings.frame_end = int(math.ceil(settings.frame_start + radius / speed))
    if found is not None and settings.trigger in motion.MOMENTS and path != "HAND":
        # the swap (or the middle of the wave) as the back is turned to the camera, at the bottom of the squat, the top
        # of the jump, as the feet land
        aim = _moment(settings, wave) if _old_at_once(settings) else 0.5 * wave
        at = _frame_at(mask, aim)
        if at is not None:
            delta = found["frame"] - at
            _shift_keys(mask, delta)
            settings.frame_start = int(round(settings.frame_start + delta))
            settings.frame_end = int(round(settings.frame_end + delta))
    mask[P_TRIGGER] = found["frame"] if found is not None else -1.0
    mask[P_ROOTS] = roots
    mask[P_FOLLOWERS] = followers
    mask[P_PATH] = path
    mask[P_REACH] = radius
    mask[P_WAVE] = wave
    if layout is not None:  # where the front's decoration (rings.py) goes
        mask[P_LAYOUT] = {key: list(value) if isinstance(value, Vector) else value for key, value in layout.items()}
    mask[P_ROOT] = owner.root.name if owner.root is not None else ""
    mask[P_BROOCH] = list(_origin(context, settings, owner)[0])
    mask[P_PITCH] = settings.spiral_pitch

    target_group, base_group = ensure_node_groups()
    settings.mask = mask
    materials.ensure_wire_material(settings)
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    locked = 0
    for ob in target.meshes:
        locked += _prepare_mesh(ob, "TARGET", mask, target_group, patterns)
    for ob in base.meshes:
        locked += _prepare_mesh(ob, "BASE", mask, base_group, patterns)
    mask[P_AREA] = sum(mdl.free_area(ob) for ob in base.meshes)
    mask[P_AREA_NEW] = sum(mdl.free_area(ob) for ob in target.meshes)
    sync(settings)

    # Leave behind: play the transformation once and record where the old outfit (and each chunk) breaks off, where
    # the new outfit's stars are born and where its pieces take off.
    recorded, record_seconds = 0, 0.0
    jobs = []
    for role, outfit in (("BASE", base.meshes), ("TARGET", target.meshes)):
        if _recording(settings, role):
            vertices, chunks = _record_parts(settings, role)
            for ob in outfit if vertices or chunks else ():
                jobs.append(launch.Job(ob, role == "TARGET", vertices, chunks,
                                       *_signatures(settings, role, _object_scale(ob))))
    if jobs:
        t0 = time.time()
        scene = context.scene
        physics = scene.rigidbody_world is not None and scene.rigidbody_world.enabled
        start, end = settings.frame_start, max(settings.frame_end, settings.frame_start + 1)
        warmup = scene.frame_start if physics and scene.frame_start < start else None
        busy = {job.ob for job in jobs}
        others = [ob for ob in meshes if ob not in busy] + ribbons.ribbon_objects(mask) + rings.ring_objects(mask)
        recorded = launch.record(context, jobs, others, range(start, end + 1), warmup)
        record_seconds = time.time() - t0
    return {
        "mask": mask,
        "height": height,
        "radius": radius,
        "path": path,
        "seeds": len(seeds),
        "arrival_seconds": arrival_seconds,
        "target_meshes": len(target.meshes),
        "base_meshes": len(base.meshes),
        "locked_faces": locked,
        "origin_bone": bone,
        "unbound": unbound,
        "recorded": recorded,
        "record_seconds": record_seconds,
        "trigger": found["frame"] if found is not None else None,
    }
