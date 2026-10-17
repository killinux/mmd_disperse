"""The spray's mist (1.12, the path Sprayed On): building found where the palms were and which way the hands pointed
every frame (sampling.Spray); this writes a speck of mist for every frame and nozzle a few times over into a mesh of
points of ours (its frame ATTR_T, its way ATTR_WAY: random within the spray's cone), and a Geometry Nodes modifier
(node_groups.build_mist_group) lets the specks of the last moments fly on, slowing and spreading. They stay where they
were sprayed: rebuild after moving the model.
"""

import math
import random

import bpy
import numpy as np
from mathutils import Vector

from . import materials
from .node_groups import ATTR_T, ATTR_WAY, MIST_GROUP, ensure_mist_group, input_identifiers

NAME = "MMD Disperse Mist"
P_MIST = "mmd_disperse_mist"  # on the mist object: the mask of its effect
SPECKS = 28  # specks a nozzle sprays a frame
LIFE = 0.5  # seconds a speck flies
SPEED = 0.025  # model heights a frame a speck leaves the nozzle at


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_MIST) == mask]


def _points(rec, height, cone):
    """(positions, frames, ways) of the specks."""
    rng = random.Random(7)
    points, times, ways = [], [], []
    for side, flat in sorted(rec.items()):
        if not side.startswith("nozzle_"):
            continue
        for i in range(0, len(flat) - 6, 7):
            f, px, py, pz, dx, dy, dz = flat[i:i + 7]
            axis = Vector((dx, dy, dz)).normalized()
            other = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
            u = axis.cross(other).normalized()
            v = axis.cross(u)
            for _k in range(SPECKS):
                a = rng.random() * 2.0 * math.pi
                r = math.tan(cone) * math.sqrt(rng.random())
                way = (axis + u * (r * math.cos(a)) + v * (r * math.sin(a))).normalized()
                points.append((px, py, pz))
                times.append(f + rng.random())
                ways.append(tuple(way * (SPEED * height * (0.6 + 0.8 * rng.random()))))
    return points, times, ways


def sync(settings, mask, rec, height, collection, cone):
    """Create / update / remove the mist from what building found (`rec`: per nozzle, flat lists of frame, position
    and direction), as the panel says."""
    ob = next(iter(objects(mask)), None)
    if rec is None or not settings.picture_show:
        if ob is not None:
            remove(mask)
        return
    if ob is None:
        me = bpy.data.meshes.new(NAME)
        points, times, ways = _points(rec, height, cone)
        me.from_pydata(points, [], [])
        attr = me.attributes.new(ATTR_T, "FLOAT", "POINT")
        if times:
            attr.data.foreach_set("value", np.asarray(times, dtype=np.float32))
        attr = me.attributes.new(ATTR_WAY, "FLOAT_VECTOR", "POINT")
        if ways:
            attr.data.foreach_set("vector", np.asarray(ways, dtype=np.float32).ravel())
        me.update()
        ob = bpy.data.objects.new(NAME, me)
        collection.objects.link(ob)
        ob[P_MIST] = mask
        ob.hide_select = True
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
        mod = ob.modifiers.new(NAME, "NODES")
        mod.node_group = ensure_mist_group()
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    mat = materials.ensure_mist_material()
    materials.update_mist_material(settings.spray_color, 1.5)
    values = {"Size": 0.0025 * height, "Life": LIFE * fps, "Material": mat}
    for mod in ob.modifiers:
        if mod.type == "NODES" and mod.node_group and mod.node_group.name == MIST_GROUP:
            ids = input_identifiers(mod.node_group)
            for name, value in values.items():
                if ids.get(name) is not None:
                    mod[ids[name]] = value
    ob.update_tag()


def remove(mask):
    for ob in objects(mask):
        me = ob.data
        bpy.data.objects.remove(ob)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    mat = bpy.data.materials.get(materials.MIST_MATERIAL)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)
