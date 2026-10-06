"""The dance drawn in the air (舞蹈绸带): ribbons trailing from the hands, and the feet if asked, while the
transformation runs: trails of light, white water sleeves of Chinese opera, Ne Zha's red silk sash, or a trail of
petals. And flowers underfoot (步步生莲): wherever a foot comes down a lotus opens (or a golden seal lights up).

Building plays the dance once (bones only, twice a frame) round the transformation and writes where the fingertips
(and toes) were into a mesh of ours: one chain of points per limb, each with its frame (ATTR_T). A Geometry Nodes
modifier (node_groups.build_trail_group) shows the last part of each chain at every frame, so the ribbons follow the
dance exactly and any frame can be scrubbed to. The footfalls found in the same playing are a second mesh of points
(node_groups.build_steps_group). Both stay where they were recorded: rebuild after moving the model.
"""

import math

import bpy
import numpy as np

from . import materials, motion, particles
from .model import rest_bounds
from .node_groups import (ATTR_T, STEPS_GROUP, TRAIL_GROUP, TRAIL_STYLES, ensure_steps_group, ensure_trail_group,
                          input_identifiers)

TRAIL = "MMD Disperse Ribbons"
STEPS = "MMD Disperse Steps"
P_TRAIL = "mmd_disperse_trail"  # on the ribbons and steps objects: the mask of their effect
P_KIND = "mmd_disperse_trail_kind"  # ... TRAIL or STEPS
P_KEY = "mmd_disperse_trail_key"  # ... what their recording was made for
BEFORE = 0.4  # seconds the ribbons come in before the transformation starts ...
AFTER = 1.0  # ... and stay after it ends (the flowers too)
LIGHT_WIDTH = 0.15  # a trail of light is this much of the silk's width
SAG = 0.07  # how far the silk hangs down at its tail, a share of the model height
STEP_STRENGTH = 4.0  # how brightly the seals and ripples underfoot shine


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_TRAIL) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _object(mask, kind, collection, group):
    ob = next(iter(objects(mask, kind)), None)
    if ob is None:
        me = bpy.data.meshes.new(TRAIL if kind == "TRAIL" else STEPS)
        ob = bpy.data.objects.new(me.name, me)
        collection.objects.link(ob)
        ob[P_TRAIL] = mask
        ob[P_KIND] = kind
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
        mod = ob.modifiers.new(me.name, "NODES")
        mod.node_group = group
    return ob


def _write(ob, points, edges, times):
    me = ob.data
    me.clear_geometry()
    me.from_pydata([tuple(p) for p in points], edges, [])
    attr = me.attributes.new(ATTR_T, "FLOAT", "POINT")
    if len(times):
        attr.data.foreach_set("value", np.asarray(times, dtype=np.float32))
    me.update()


def _chains(track, feet):
    chains = [track.tip["L"], track.tip["R"]]
    if feet:
        for side in motion.SIDES:
            toe = track.toe[side]
            chains.append(toe if np.isfinite(toe).all(axis=1).any() else track.ankle[side])
    return chains


def record(scene, armature, hidden, first, last, feet, height):
    """Play the dance from `first` to `last` twice a frame: (ribbon points, edges, frames), (footfall points, frames)."""
    frames = np.arange(first, last + 0.25, 0.5)
    track = motion.play(scene, armature, list(frames), hidden=hidden)
    points, edges, times = [], [], []
    for chain in _chains(track, feet):
        last_index = None
        for f, p in zip(frames, chain):
            if not np.isfinite(p).all():
                last_index = None
                continue
            points.append(p)
            times.append(f)
            if last_index is not None:
                edges.append((last_index, len(points) - 1))
            last_index = len(points) - 1
    fps = scene.render.fps / scene.render.fps_base
    steps = motion.footfalls(track, height, 2.0 * fps)
    return (points, edges, times), ([s[2] for s in steps], [float(frames[s[0]]) for s in steps])


def sync(settings, mask, model, hidden):
    """Create / record / update the dance ribbons and the flowers underfoot of the old (or only) `model` as the panel
    says, or remove them. `hidden`: meshes switched off while the dance plays."""
    scene = settings.id_data
    want_trail, want_steps = settings.trail_enable, settings.step_flowers
    arm = model.armature if model else None
    if not (want_trail or want_steps) or arm is None:
        remove(mask)
        return
    fps = scene.render.fps / scene.render.fps_base
    length = max(settings.trail_length * fps, 1.0)
    first = int(math.floor(settings.frame_start - BEFORE * fps - length))
    last = int(math.ceil(max(settings.frame_end, settings.frame_start + 1) + AFTER * fps))
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    action = arm.animation_data.action if arm.animation_data else None
    feet = settings.trail_feet
    key = "%s:%s:%d:%d:%d:%.3f" % (arm.name, action.name if action else "", first, last, int(feet), fps)
    trail = _object(mask, "TRAIL", collection, ensure_trail_group())
    steps = _object(mask, "STEPS", collection, ensure_steps_group()) if want_steps else None
    if not want_steps:
        for ob in objects(mask, "STEPS"):
            _delete(ob)
    lo, hi = rest_bounds(model.meshes)
    height = hi.z - lo.z
    if trail.get(P_KEY) != key or (steps is not None and steps.get(P_KEY) != key):
        (points, edges, times), (spots, at) = record(scene, arm, hidden, first, last, feet, height)
        _write(trail, points, edges, times)
        trail[P_KEY] = key
        if steps is not None:
            _write(steps, spots, [], at)
            steps[P_KEY] = key
    trail.hide_viewport = trail.hide_render = not want_trail
    style = settings.trail_style
    mat = materials.ensure_trail_material(style) if style != "PETALS" else None
    materials.update_trail_material(style, settings.glow_color, settings.trail_strength)
    width = settings.trail_width * (LIGHT_WIDTH if style == "LIGHT" else 1.0)
    end = max(settings.frame_end, settings.frame_start + 1)
    _push(trail, TRAIL_GROUP, {
        "Style": TRAIL_STYLES.index(style),
        "Length": length,
        "Width": width,
        "Sag": SAG * height if style in ("SLEEVE", "SASH") else 0.0,
        "Height": height,
        "Start": float(settings.frame_start) - BEFORE * fps,
        "End": float(end),
        "Fade": AFTER * fps,
        "Material": mat,
        "Petal Object": particles.ensure_asset("PETAL", scene) if style == "PETALS" else None,
    })
    if steps is not None:
        glow = materials.ensure_step_material()
        materials.update_step_material(settings.glow_color, STEP_STRENGTH)
        _push(steps, STEPS_GROUP, {
            "Seal": settings.step_style == "SEAL",
            "Height": height,
            "Floor": lo.z,
            "Rate": 30.0 / max(fps, 1e-3),
            "Petal Material": materials.ensure_lotus_material(),
            "Glow Material": glow,
        })


def _push(ob, group_name, values):
    for mod in ob.modifiers:
        if mod.type == "NODES" and mod.node_group and mod.node_group.name == group_name:
            ids = input_identifiers(mod.node_group)
            for name, value in values.items():
                if ids.get(name) is not None and value is not None:
                    mod[ids[name]] = value
    ob.update_tag()


def _delete(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def remove(mask):
    for ob in objects(mask):
        _delete(ob)
