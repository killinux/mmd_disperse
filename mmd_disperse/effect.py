"""Build, update and remove a suit-up effect (mask empty + modifiers + materials)."""

import fnmatch

import bpy
from mathutils import Matrix

from . import materials
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


def _create_mask(settings, location, armature, bone, collection, radius_max):
    mask = bpy.data.objects.new(MASK_NAME, None)
    mask.empty_display_type = "SPHERE"
    mask.empty_display_size = 1.0
    mask.show_in_front = True
    mask.hide_render = True
    collection.objects.link(mask)
    mask.location = location
    if settings.space == "POSED" and armature is not None and bone:
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
    if ob.get(P_ROLE) == "TARGET":
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


# --------------------------------------------------------------------------- settings -> scene

def _glow_materials(ob, settings):
    """Materials of a new-outfit mesh that get the glowing rim (locked parts never show)."""
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    for slot in ob.material_slots:
        mat = slot.material
        if mat is None or mat.name == WIRE_MATERIAL:
            continue
        name = mdl.material_key(mat)
        if not any(fnmatch.fnmatchcase(name, p) for p in patterns):
            yield mat


def sync(settings):
    """Push the panel values to every modifier and material of the current effect."""
    mask = settings.mask
    if mask is None:
        return
    wire = bpy.data.materials.get(WIRE_MATERIAL)
    materials.update_wire_material(wire, settings)
    common = {
        "Mask": mask,
        "Use Rest Position": settings.space == "REST",
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
        }),
    }
    for ob in effect_objects(mask):
        for mod in ob.modifiers:
            group = mod.node_group if mod.type == "NODES" else None
            if group is None or group.name not in values:
                continue
            ids = input_identifiers(group)
            for name, value in values[group.name].items():
                key = ids.get(name)
                if key is not None:
                    mod[key] = value
            ob.update_tag()
        if ob.get(P_ROLE) == "TARGET":
            for mat in _glow_materials(ob, settings):
                if settings.edge_glow:
                    materials.add_edge_glow(mat)
                    materials.update_edge_glow(mat, settings)
                else:
                    materials.remove_edge_glow(mat)


def build(context, settings):
    context.view_layer.update()  # matrix_world must reflect recent transform edits
    target = mdl.resolve(settings.target)
    if not target:
        raise EffectError("Pick the new outfit (target model) first")
    base = mdl.resolve(settings.base) if settings.base else mdl.Model(None, None, [])
    if base.root is not None and base.root == target.root:
        raise EffectError("Old and new outfit must be different models")

    # Rebuilding replaces any effect already attached to these meshes.
    for ob in target.meshes + base.meshes:
        old = ob.get(P_MASK)
        if isinstance(old, bpy.types.Object):
            remove_effect(old)
        else:
            _cleanup_mesh(ob)

    lo, hi = mdl.rest_bounds(target.meshes)
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
        unbound = _bind_to_armature(target.meshes, base.armature)

    owner = base if base else target
    location, bone = _origin(context, settings, owner)
    reach = mdl.max_distance(target.meshes + base.meshes, location)
    margin = settings.noise_amount + max(settings.edge_width, settings.wire_outer) + 0.02 * height
    if settings.space == "POSED":
        margin += 0.1 * height
    collection = target.root.users_collection[0] if target.root.users_collection else context.scene.collection
    mask = _create_mask(settings, location, owner.armature, bone, collection, reach + margin)
    mask[P_ROOTS] = roots

    target_group, base_group = ensure_node_groups()
    settings.mask = mask
    materials.ensure_wire_material(settings)
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    locked = 0
    for ob in target.meshes:
        locked += _prepare_mesh(ob, "TARGET", mask, target_group, patterns)
    for ob in base.meshes:
        locked += _prepare_mesh(ob, "BASE", mask, base_group, patterns)
    sync(settings)
    return {
        "mask": mask,
        "height": height,
        "radius": reach + margin,
        "target_meshes": len(target.meshes),
        "base_meshes": len(base.meshes),
        "locked_faces": locked,
        "origin_bone": bone,
        "unbound": unbound,
    }
