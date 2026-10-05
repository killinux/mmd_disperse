"""Build, update and remove a suit-up effect (mask empty + modifiers + materials)."""

import fnmatch
import time

import bpy
from mathutils import Matrix, Vector

from . import arrival, beats, compositor, launch, materials, particles, ribbons, rings, venom
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
# or shimmered in in the transporter beam
AT_ONCE = ("CLAMP", "GHOSTS", "EVOLVE", "POOF", "SHADOW", "BEAM")
SHATTER_AT = 1.0  # share of the wave at which the old outfit goes all at once (exit timing): when the wave is done
BEAT_REACH = 2.0  # seconds a moment may wait for the next beat
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


def _create_mask(settings, location, armature, bone, collection, radius_max, path, root=None, axis=None):
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
    keys = [(start, 0.0), (end, radius_max)]
    if settings.direction == "SHRINK":
        keys = [(start, radius_max), (end, 0.0)]
    _insert_scale_keys(mask, keys, "LINEAR" if settings.easing == "LINEAR" else "BEZIER")
    return mask


def _layer(settings):
    """How far the new outfit's final look trails behind the edge (the dark undersuit), in world units."""
    return settings.layer_width if settings.layer_enable else 0.0


def _old_at_once(settings):
    """True when all of the old outfit goes at one moment: the new outfit's halves clamp shut or its ghosts meet, or
    the old outfit stays (freezing over ...) while the wave crosses it and then goes all at once."""
    return settings.entrance in AT_ONCE or (settings.exit_timing == "AT_ONCE" and settings.entrance != "SCALES")


def _held(settings):
    """True when the new outfit waits under the old one's opaque surface (veins, char, ink, stone, gold, silk, code)
    until the old outfit goes all at once, instead of growing at the edge and showing through it. (Under clear ice it
    is seen forming.)"""
    return (settings.exit_timing == "AT_ONCE" and settings.entrance == "GROW"
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
    return extra


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
    for fc in curves:
        for key in fc.keyframe_points:
            key.co[1] *= ratio
            key.handle_left[1] *= ratio
            key.handle_right[1] *= ratio
        fc.update()
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
    ribbons.remove(mask)
    rings.remove(mask)
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
            materials.add_hologram(mat)
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
        vertices = settings.exit_style in FLAKES or settings.particles != "NONE"
        return vertices or (pieces and not shown), pieces
    stars = settings.finale and settings.finale_sparkles > 0
    # with Subdivide the fly-in pieces are cut from another mesh than the one recorded
    return stars, settings.entrance == "ASSEMBLE" and settings.subdivide == 0


def missing_recording(settings):
    """True when leave behind is on but some part of the built effect that needs a recording has none (rebuild)."""
    if not settings.leave_behind or settings.mask is None:
        return False
    for ob in effect_objects(settings.mask):
        if ob.type != "MESH" or ob.get(P_ROLE) not in ("BASE", "TARGET"):
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
    update_white_flash(settings)
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
        own = {"Reach": reach, "Venom": skeleton is not None, "Venom Skeleton": skeleton, "Clamp Distance": moment,
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
        if role in ("TARGET", "BASE"):
            _update_inner_glow(ob, settings)
            _update_shadow(ob, settings)


def _seeds(settings, location, model):
    seeds = [] if settings.seeds == "LIMBS" else [location]
    if settings.seeds != "ORIGIN":
        seeds += arrival.limb_points(model.armature)
    return seeds or [location]


def build(context, settings):
    context.view_layer.update()  # matrix_world must reflect recent transform edits
    venom.forget()  # the motion may have changed: look for the strands in its poses again
    target = mdl.resolve(settings.target)
    base = mdl.resolve(settings.base) if settings.base else mdl.Model(None, None, [])
    if not target and not base:
        raise EffectError("Pick the old or the new outfit first")
    if base.root is not None and base.root == target.root:
        raise EffectError("Old and new outfit must be different models")

    # Rebuilding replaces any effect already attached to these meshes.
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
    if path == "SPHERE":
        reach = mdl.max_distance(meshes, location)
    else:
        if path == "SURFACE":
            seeds = _seeds(settings, location, owner)
        # Start a little short of the surface so nothing (not even the wire ahead of the edge) shows at
        # radius 0, like the sphere that starts inside the body.
        lead = settings.wire_outer + 0.005 * height
        # sweeps and the spiral follow the model's own axes (it may stand turned in the world)
        frame = (owner.root or meshes[0]).matrix_world.to_3x3().normalized()
        values = [v + lead for v in arrival.compute(meshes, path, seeds, height, frame, settings.spiral_pitch)]
        for ob, v in zip(meshes, values):
            arrival.write(ob, v / _object_scale(ob))
        reach = max(float(v.max()) for v in values)
        if path != "SURFACE":
            layout = arrival.front_layout(meshes, path, frame)
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
                        layout["axis"] if layout else None)
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
    if settings.leave_behind:
        for role, outfit in (("BASE", base.meshes), ("TARGET", target.meshes)):
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
    }
