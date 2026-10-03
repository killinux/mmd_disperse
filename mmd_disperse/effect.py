"""Build, update and remove a suit-up effect (mask empty + modifiers + materials)."""

import fnmatch
import math
import time

import bpy
from mathutils import Matrix, Vector

from . import arrival, materials, particles
from . import model as mdl
from .node_groups import BASE_GROUP, TARGET_GROUP, ensure_node_groups, input_identifiers

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
# What sync() needs to know about the built effect (stored on the mask).
P_PATH = "mmd_disperse_path"
P_REACH = "mmd_disperse_reach"
P_WAVE = "mmd_disperse_wave"
P_AREA = "mmd_disperse_area"

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
}
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


def _create_mask(settings, location, armature, bone, collection, radius_max, path):
    mask = bpy.data.objects.new(MASK_NAME, None)
    # The scale is how far the wave has travelled; for the sweeps an arrow shows the direction.
    mask.empty_display_type = "SINGLE_ARROW" if path in ("UP", "DOWN") else "SPHERE"
    if path == "DOWN":
        mask.rotation_euler = (math.pi, 0.0, 0.0)
    mask.empty_display_size = 1.0
    mask.show_in_front = True
    mask.hide_render = True
    collection.objects.link(mask)
    mask.location = location
    if path == "SPHERE" and settings.space == "POSED" and armature is not None and bone:
        con = mask.constraints.new("COPY_LOCATION")
        con.target = armature
        con.subtarget = bone
    start = settings.frame_start
    end = max(settings.frame_end, start + 1)
    keys = [(start, 0.0), (end, radius_max)]
    if settings.direction == "SHRINK":
        keys = [(start, radius_max), (end, 0.0)]
    _insert_scale_keys(mask, keys, "LINEAR" if settings.easing == "LINEAR" else "BEZIER")
    return mask


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


def _cleanup_mesh(ob):
    for mod in list(ob.modifiers):
        if mod.type == "NODES" and mod.node_group and mod.node_group.name in (TARGET_GROUP, BASE_GROUP):
            ob.modifiers.remove(mod)
    if ob.get(P_ROLE) in ("TARGET", "BASE"):
        for slot in ob.material_slots:
            if slot.material is not None:
                materials.remove_edge_glow(slot.material)
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
    for key in (P_MASK, P_ROLE, P_REST, P_ARM):
        if key in ob:
            del ob[key]


def _restore_root(root):
    flat = root.get(P_MATRIX)
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
    action = mask.animation_data.action if mask.animation_data else None
    bpy.data.objects.remove(mask)
    if action is not None and action.users == 0:
        bpy.data.actions.remove(action)
    if not any(ob.type == "EMPTY" and ob.name.startswith(MASK_NAME) for ob in bpy.data.objects):
        particles.remove_assets()


# --------------------------------------------------------------------------- settings -> scene

def _glow_materials(ob, settings):
    """Materials of an outfit mesh that may glow (locked parts never break or show the rim)."""
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    for slot in ob.material_slots:
        mat = slot.material
        if mat is None or mat.name == WIRE_MATERIAL:
            continue
        name = mdl.material_key(mat)
        if not any(fnmatch.fnmatchcase(name, p) for p in patterns):
            yield mat


def _update_glow(ob, settings, enabled, strength):
    for mat in _glow_materials(ob, settings):
        if enabled:
            materials.add_edge_glow(mat)
            materials.update_edge_glow(mat, settings.glow_color, strength)
        else:
            materials.remove_edge_glow(mat)


def _particle_object(settings):
    """Object the old outfit's particles are made of (built-in petal / butterfly, or the user's)."""
    if settings.particles == "OBJECT":
        return settings.particle_object
    if settings.particles in particles.NAMES:
        return particles.ensure_asset(settings.particles, settings.id_data)
    return None


def sync(settings):
    """Push the panel values to every modifier and material of the current effect."""
    mask = settings.mask
    if mask is None:
        return
    wire = bpy.data.materials.get(WIRE_MATERIAL)
    materials.update_wire_material(wire, settings)
    shape = _particle_object(settings)
    materials.update_particle_material(settings)
    common = {
        "Mask": mask,
        "Use Rest Position": settings.space == "REST",
        "Use Arrival": mask.get(P_PATH, "SPHERE") != "SPHERE",
        "Noise Scale": settings.noise_scale,
        "Noise Detail": settings.noise_detail,
        "Noise Amount": settings.noise_amount,
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
        }),
        BASE_GROUP: dict(common, **{
            "Shrink": settings.base_shrink,
            "Delete Offset": settings.base_delete_offset,
            "Fragments": settings.exit_style == "FRAGMENTS",
            "Flake Size": settings.frag_size,
            "Flake Subdivide": settings.frag_subdivide,
            "Burst": settings.frag_burst,
            "Turbulence": settings.frag_turbulence,
            "Spin": settings.frag_spin,
            "Flake Glow": settings.frag_glow,
            "Particles": shape is not None,
            "Particle Object": shape,
            "Flap": settings.particles == "BUTTERFLY",
            "Flap Speed": settings.flap_speed,
            "Particle Size": settings.particle_size,
        }),
    }
    reach = float(mask.get(P_REACH, 0.0)) or 1e6
    wave = float(mask.get(P_WAVE, 0.0)) or reach
    area = float(mask.get(P_AREA, 0.0))
    density = settings.particle_count / area if area > 0.0 else 0.0
    wind = Vector(settings.frag_wind_dir)
    wind = wind.normalized() * settings.frag_wind if wind.length > 1e-9 else Vector((0.0, 0.0, 0.0))
    for ob in effect_objects(mask):
        role = ob.get(P_ROLE)
        own = {}
        if role == "BASE":  # node trees work in object space
            s = _object_scale(ob)
            own = {
                "Reach": reach / s,
                "Flight": settings.frag_life * wave / s,
                "Particle Flight": settings.particle_life * wave / s,
                "Wind": tuple(ob.matrix_world.inverted_safe().to_3x3() @ wind),
                "Particle Density": density * s * s,
            }
        for mod in ob.modifiers:
            group = mod.node_group if mod.type == "NODES" else None
            if group is None or group.name not in values:
                continue
            ids = input_identifiers(group)
            for name, value in list(values[group.name].items()) + list(own.items()):
                key = ids.get(name)
                if key is not None and value is not None:
                    mod[key] = value
            ob.update_tag()
        if role == "TARGET":
            _update_glow(ob, settings, settings.edge_glow, settings.edge_glow_strength)
        elif role == "BASE":
            _update_glow(ob, settings, settings.exit_style == "FRAGMENTS" and settings.frag_glow,
                         settings.frag_glow_strength)


def _seeds(settings, location, model):
    seeds = [] if settings.seeds == "LIMBS" else [location]
    if settings.seeds != "ORIGIN":
        seeds += arrival.limb_points(model.armature)
    return seeds or [location]


def build(context, settings):
    context.view_layer.update()  # matrix_world must reflect recent transform edits
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

    lo, hi = mdl.rest_bounds((target or base).meshes)
    height = hi.z - lo.z
    if settings.auto_size and abs(height - settings.size_reference) > 1e-4 * max(height, 1.0):
        fit_sizes(settings, height)

    roots = []
    unbound = []
    if settings.follow_base and base.armature is not None and target.armature is not None:
        if target.root.type in {"EMPTY", "ARMATURE"} and base.root.type in {"EMPTY", "ARMATURE"}:
            target.root[P_MATRIX] = [v for row in target.root.matrix_basis for v in row]
            target.root.matrix_world = base.root.matrix_world.copy()
            roots.append(target.root.name)
            context.view_layer.update()  # the meshes' matrix_world now include the snap
        unbound = _bind_to_armature(target.meshes, base.armature)

    owner = base if base else target
    meshes = target.meshes + base.meshes
    path = settings.path
    location, bone = _origin(context, settings, owner)
    seeds = []
    t0 = time.time()
    if path == "SPHERE":
        reach = mdl.max_distance(meshes, location)
    else:
        if path == "SURFACE":
            seeds = _seeds(settings, location, owner)
        # Start a little short of the surface so nothing (not even the wire ahead of the edge) shows at
        # radius 0, like the sphere that starts inside the body.
        lead = settings.wire_outer + 0.005 * height
        values = [v + lead for v in arrival.compute(meshes, path, seeds, height)]
        for ob, v in zip(meshes, values):
            arrival.write(ob, v / _object_scale(ob))
        reach = max(float(v.max()) for v in values)
        if path != "SURFACE":
            blo, bhi = mdl.rest_bounds(meshes)
            location = Vector(((blo.x + bhi.x) / 2, (blo.y + bhi.y) / 2, blo.z if path == "UP" else bhi.z))
    arrival_seconds = time.time() - t0

    margin = settings.noise_amount + max(settings.edge_width, settings.wire_outer) + 0.02 * height
    if path == "SPHERE" and settings.space == "POSED":
        margin += 0.1 * height
    # Flakes and particles keep flying after the front has passed: leave them time to finish.
    wave = reach + margin
    tail = 0.0
    if base:
        if settings.exit_style == "FRAGMENTS":
            tail = settings.frag_life
        if settings.particles != "NONE":
            tail = max(tail, settings.particle_life)
    radius = wave * (1.0 + tail)
    root = target.root or base.root
    collection = root.users_collection[0] if root.users_collection else context.scene.collection
    mask = _create_mask(settings, location, owner.armature, bone, collection, radius, path)
    mask[P_ROOTS] = roots
    mask[P_PATH] = path
    mask[P_REACH] = radius
    mask[P_WAVE] = wave

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
    sync(settings)
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
    }
