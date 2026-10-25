"""The sweat (汗光, 1.18): as she dances towards the big moment she glistens more and more, a wet sheen on her skin and
the old outfit and beads of sweat catching the light; the new outfit comes on dry. Gakumas' live shows (CEDEC 2024:
five kinds of sweat, and when it starts depends on how good a dancer the idol is and how hard the song is).

A layer spliced into every material of the old outfit (materials.add_sweat), as wet as its SWEAT + " On" value, which
a driver raises from the start of the transformation (Sweat From before the moment, when that is later) to the moment
and drops to nothing at it (simple expressions).
"""

import bpy

from . import materials


def _materials(model):
    return {sl.material for ob in model.meshes for sl in ob.material_slots
            if sl.material is not None and sl.material.node_tree is not None}


def remove(mask, models=()):
    for mat in [m for m in bpy.data.materials if m.get(materials.P_SWEAT)]:
        materials.remove_sweat(mat)


def sync(settings, mask, models, start, moment):
    """The sweat as the panel says: from frame `start` (the transformation's) to the big moment at frame `moment`;
    taken out of the materials when it is off."""
    if mask is None:
        return
    if not getattr(settings, "sweat_enable", False) or moment is None or not models:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    first = max(float(start) if start is not None else m - settings.sweat_time * fps, m - settings.sweat_time * fps)
    wet = _materials(models[0]) if len(models) > 1 else set()
    for mat in [mt for mt in bpy.data.materials if mt.get(materials.P_SWEAT) and mt not in wet]:
        materials.remove_sweat(mat)
    for mat in wet:
        materials.add_sweat(mat)
        nt = mat.node_tree
        shine = nt.nodes.get(materials.SWEAT + " Shine")
        if shine is not None:
            shine.outputs[0].default_value = settings.sweat_amount
        on = nt.nodes.get(materials.SWEAT + " On")
        if on is None:
            continue
        on.outputs[0].driver_remove("default_value")
        driver = on.outputs[0].driver_add("default_value").driver
        driver.type = "SCRIPTED"
        driver.expression = "smoothstep(%.2f, %.2f, frame) * (frame < %.2f)" % (first, m, m)
