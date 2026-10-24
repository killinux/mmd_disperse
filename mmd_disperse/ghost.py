"""The ghost (幽灵化, 1.16): she turns into a spirit while she changes: see-through from the feet up (nothing left of
her feet), a rim of pale light and wisps flowing up her, mist sinking from under her feet and a candle-warm light
flickering by her; with Float Up (1.11) she floats meanwhile. The new outfit comes on in the spirit state; once it is
complete the mist stops, her feet come back solid and she lands. 以闪亮之名's 「烛魇幽歌」 (2026-08). Not the soul leaving
(1.10): there an empty shell drifts away, here she herself turns into the spirit and back.

The look is spliced into every material of both outfits (materials.add_ghost) and timed by drivers (simple
expressions of the frame): GHOST + " On" (the spirit state) and GHOST + " Feet" (the height of her feet: the floor,
lifted as the float lifts her). The mist is points of ours on the cover pieces group (they sink and spread from a
ring round her feet), on an object that follows her centre bone; the candle is a point light of ours with a noise on
its energy (an F-curve modifier: no Python).
"""

import math

import bpy
import numpy as np
from mathutils import Vector

from . import materials

P_GHOST = "mmd_disperse_ghost"  # on our objects: the mask of their effect ...
P_KIND = "mmd_disperse_ghost_kind"  # ... MIST, CANDLE
NAME = "MMD Disperse Ghost"
IN = 0.6  # seconds she takes to turn into the spirit, ending as the transformation starts ...
AFTER, OUT = 0.3, 0.6  # ... she turns back from this long after the new outfit is complete, over this long
FADE = 0.5  # how far up from her feet she fades in (model heights): her legs go first
PUFFS = 300  # the mist's puffs
CANDLE_POWER = 8.0  # the candle's energy, watts per square model height
CENTRE = ("センター", "center", "Center", "下半身", "lower body", "Hips", "hips", "pelvis", "J_Bip_C_Hips")


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_GHOST) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _materials(meshes):
    seen = []
    for ob in meshes:
        for slot in ob.material_slots:
            if slot.material is not None and slot.material.node_tree is not None and slot.material not in seen:
                seen.append(slot.material)
    return seen


def remove(mask, meshes=()):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Light) and data.users == 0:
            bpy.data.lights.remove(data)
    for mat in [m for m in bpy.data.materials if m.get(materials.P_GHOST)]:
        if not meshes or mat in _materials(meshes):
            materials.remove_ghost(mat)
    if not any(ob.get(P_GHOST) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_totem_assets()  # (the puff, when the totem does not use it either)
        mat = bpy.data.materials.get(materials._cover_name("GHOST_MIST"))
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)


def _drive(mat, node, expression):
    nt = mat.node_tree
    path = 'nodes["%s"].outputs[0].default_value' % node
    if nt.nodes.get(node) is None:
        return
    nt.driver_remove(path)
    driver = nt.driver_add(path).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def spirit_expression(start, moment, fps):
    """0 .. 1: how much of a spirit she is at the frame (simple math only)."""
    return "smoothstep({a}, {b}, frame) * (1 - smoothstep({c}, {d}, frame))".format(
        a=float(start - IN * fps), b=float(start), c=float(moment + AFTER * fps), d=float(moment + (AFTER + OUT) * fps))


def sync(settings, mask, models, start, moment):
    """The spirit look as the panel says, from the start of the transformation (frame `start`) till the new outfit is
    complete (frame `moment`); all of it taken away when it is off."""
    from . import cover_nodes, toon
    from .model import rest_bounds

    meshes = [ob for m in models for ob in m.meshes] if models else []
    if mask is None:
        return
    if not getattr(settings, "ghost_enable", False) or start is None or moment is None or not meshes:
        remove(mask, meshes)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    height = max(settings.size_reference, 1e-3)
    lo, hi = rest_bounds(meshes)
    floor = lo.z
    on = spirit_expression(start, moment, fps)
    # her feet: the floor, lifted as the float lifts her (toon's float, in world units here)
    if settings.float_up:
        land = int(math.ceil(moment - 1e-6))
        span = max(land - settings.frame_start, 1.0)
        up = max(min(toon.RISE * fps, 0.45 * span), 1.0)
        down = max(min(toon.FALL * fps, 0.45 * span), 1.0)
        feet = toon.float_expression(floor, settings.float_height * height, settings.frame_start, up, down, land,
                                     toon.BOB * height)
    else:
        feet = "%.5f" % floor
    for mat in _materials(meshes):
        materials.add_ghost(mat)
        materials.update_ghost(mat, settings.ghost_color, settings.ghost_glow, settings.ghost_alpha)
        mat.node_tree.nodes[materials.GHOST + " Fade"].outputs[0].default_value = FADE * height
        _drive(mat, materials.GHOST + " On", on)
        _drive(mat, materials.GHOST + " Feet", feet)
        _drive(mat, materials.GHOST + " Tick", "frame")
    for mat in [m for m in bpy.data.materials if m.get(materials.P_GHOST) and m not in _materials(meshes)]:
        materials.remove_ghost(mat)  # (a model no longer picked)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    arm = next((m.armature for m in models if m.armature is not None), None)
    # the mist: puffs sinking and spreading from a ring round her feet, on an object following her centre bone
    if settings.ghost_mist:
        ob = next(iter(objects(mask, "MIST")), None)
        key = "%.4f:%.1f:%.1f" % (height, start, moment)
        if ob is not None and ob.get("mmdd_key") != key:
            data = ob.data
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(data)
            ob = None
        if ob is None:
            ob = bpy.data.objects.new(NAME + " Mist", _mist_points(height, start, moment, fps))
            collection.objects.link(ob)
            ob[P_GHOST] = mask
            ob[P_KIND] = "MIST"
            ob["mmdd_key"] = key
            ob.hide_select = True
            if hasattr(ob, "visible_shadow"):
                ob.visible_shadow = False
        for c in list(ob.constraints):
            ob.constraints.remove(c)
        centre = next((arm.data.bones[n] for n in CENTRE if arm is not None and n in arm.data.bones), None)
        if centre is not None:
            rest = arm.matrix_world @ centre.head_local
            ob.location = (0.0, 0.0, floor - rest.z)
            con = ob.constraints.new("COPY_LOCATION")
            con.target, con.subtarget, con.use_offset = arm, centre.name, True
        else:
            ob.location = (0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), floor)
        ob["mmdd_color"] = tuple(settings.ghost_color)
        cover_nodes_mod = next((m for m in ob.modifiers if m.type == "NODES"), None) or ob.modifiers.new(NAME, "NODES")
        group = cover_nodes.ensure_pieces_group()
        if cover_nodes_mod.node_group != group:
            cover_nodes_mod.node_group = group
        from .node_groups import input_identifiers

        ids = input_identifiers(group)
        for name, value in (("Instance", cover_nodes.ensure_puff_object(scene)), ("Size", 0.075 * height),
                            ("Gravity", (0.0, 0.0, 0.0)), ("Drag", 0.04), ("Flutter", 0.02 * height),
                            ("Spin", 0.05), ("Life", 1.6 * fps),
                            ("Material", materials.ensure_cover_material("GHOST_MIST"))):
            if name in ids:
                cover_nodes_mod[ids[name]] = value
        ob.update_tag()
    else:
        for ob in objects(mask, "MIST"):
            data = ob.data
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(data)
    # the candle: a warm point light by her, flickering (a noise on its energy) while she is a spirit
    if settings.ghost_light:
        ob = next(iter(objects(mask, "CANDLE")), None)
        if ob is None:
            light = bpy.data.lights.new(NAME + " Candle", "POINT")
            ob = bpy.data.objects.new(NAME + " Candle", light)
            collection.objects.link(ob)
            ob[P_GHOST] = mask
            ob[P_KIND] = "CANDLE"
            ob.hide_select = True
        light = ob.data
        light.color = (1.0, 0.55, 0.25)
        light.shadow_soft_size = 0.04 * height
        if hasattr(light, "use_shadow"):
            light.use_shadow = False
        from . import sampling

        camera = sampling.camera_at(scene, start)  # (by her, towards the camera as it is when she turns)
        centre_w = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), floor))
        toward = (sampling.matrix_at(camera, start).translation - centre_w) if camera is not None else Vector(
            (0.0, -1.0, 0.0))
        toward.z = 0.0
        toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
        side = toward.cross(Vector((0.0, 0.0, 1.0)))
        ob.location = centre_w + side * (0.55 * height) + toward * (0.3 * height) + Vector((0.0, 0.0, 0.7 * height))
        power = CANDLE_POWER * height * height
        ad = light.animation_data
        if ad is not None and ad.action is not None:
            action = ad.action
            ad.action = None
            if action.users == 0:
                bpy.data.actions.remove(action)
        for frame, value in ((start - IN * fps - 1.0, 0.0), (start, power), (moment + AFTER * fps, power),
                             (moment + (AFTER + OUT) * fps, 0.0)):
            light.energy = value
            light.keyframe_insert("energy", frame=frame)
        from .cover import _curves

        for fc in _curves(light):
            if fc.data_path == "energy":
                noise = fc.modifiers.new("NOISE")
                noise.scale, noise.strength, noise.phase = 3.0, 0.45 * power, 7.0
                noise.blend_type = "ADD"
                noise.use_restricted_range = True  # (it flickers only while it is lit)
                noise.frame_start, noise.frame_end = start, moment + AFTER * fps
                noise.blend_in = noise.blend_out = 0.3 * fps
    else:
        for ob in objects(mask, "CANDLE"):
            data = ob.data
            bpy.data.objects.remove(ob)
            if data.users == 0:
                bpy.data.lights.remove(data)


def _mist_points(height, start, moment, fps):
    """Puffs (cover_nodes' pieces): born on a ring round her feet from when she turns into a spirit till she turns
    back, sinking and spreading out."""
    from .cover import _mesh

    rng = np.random.default_rng(31)
    n = PUFFS
    first, last = start - IN * fps, moment + AFTER * fps
    angle = rng.uniform(0.0, 2.0 * math.pi, n)
    radius = (0.12 + 0.18 * rng.random(n)) * height
    pts = np.stack([radius * np.cos(angle), radius * np.sin(angle), 0.03 * height * rng.random(n)], axis=1)
    out = (0.05 + 0.12 * rng.random(n)) * height / fps
    vel = np.stack([out * np.cos(angle), out * np.sin(angle), -(0.08 + 0.12 * rng.random(n)) * height / fps], axis=1)
    t0 = first + (last - first) * rng.random(n)
    return _mesh(NAME + " Mist", [tuple(p) for p in pts], [],
                 (("mmdd_t0", "FLOAT", t0), ("mmdd_v", "FLOAT_VECTOR", vel), ("mmdd_r", "FLOAT", rng.random(n)),
                  ("mmdd_axis", "FLOAT_VECTOR", rng.normal(size=(n, 3)))))
