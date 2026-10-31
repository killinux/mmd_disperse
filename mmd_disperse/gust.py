"""The wind at the change (换装吹风, 1.25: the one new thing of 反差 AB 面): a force field of ours blows her hair and
skirt about as the outfits change, a gust rising to the big moment and dying away over Wind Time:

* FRONT (迎面吹来): from in front of her, a little from her left (from the camera, turned SIDE), her hair
  streaming back and out to her right where the camera sees it;
* UP (上升气流): from under her, hair and skirt lifting (the magical girl's updraft);
* WHIRL (旋风): a whirlwind round her (a vortex about her upright axis).

What it blows are the model's rigid bodies (her physics as mmd_tools builds it: the hair and skirt that swing as she
dances); without them the field is there but nothing moves. Its strength follows the frame through a driver (a simple
expression, no Python when rendering). The rigid body world's cache is reset whenever the field changes, so the
simulation runs with it from the start."""

import math

import bpy
from mathutils import Matrix, Vector

from . import model as mdl
from . import shots

P_GUST = "mmd_disperse_gust"  # on our field: the mask of its effect
NAME = "MMD Disperse Wind"
STYLES = ("NONE", "FRONT", "UP", "WHIRL")
STRENGTH = {"FRONT": 12.0, "UP": 10.0, "WHIRL": 9.0}  # at Wind Strength 1 (mmd_tools' bodies weigh about 1)
RISE = 0.35  # seconds the gust takes to rise to the big moment
NOISE = 1.5  # how gusty (the field's noise)
SIDE = 40.0  # degrees the wind from the front comes from her left (straight from the camera it blows her hair back
# behind her, where the camera hardly sees it move)


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_GUST) == mask]


def _reset(scene):
    """The rigid body simulation cached so far thrown away (it ran without our wind, or with an older one)."""
    rbw = scene.rigidbody_world if scene is not None else None
    cache = rbw.point_cache if rbw is not None else None
    if cache is not None and not cache.is_baked:
        cache.frame_end += 1
        cache.frame_end -= 1


def remove(mask):
    gone = objects(mask)
    scenes = {sc for ob in gone for sc in ob.users_scene}
    for ob in gone:
        bpy.data.objects.remove(ob)
    for scene in scenes:
        _reset(scene)


def bodies(scene):
    """How many rigid bodies her wind can blow: the moving (not animated) ones of the scene's rigid body world."""
    rbw = scene.rigidbody_world
    if rbw is None or not rbw.enabled or rbw.collection is None:
        return 0
    return sum(1 for ob in rbw.collection.objects
               if ob.rigid_body is not None and ob.rigid_body.enabled and not ob.rigid_body.kinematic)


def _field(collection, mask):
    ob = next(iter(objects(mask)), None)
    if ob is not None:
        return ob
    ob = bpy.data.objects.new(NAME, None)
    collection.objects.link(ob)
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                   selected_editable_objects=[ob]):
        bpy.ops.object.forcefield_toggle()
    ob[P_GUST] = mask
    ob.empty_display_size = 0.5
    ob.hide_select = True
    return ob


def sync(settings, mask, models, moment):
    """The wind as the panel says, the gust at its strongest at the big moment (frame `moment`); none when it is off."""
    if mask is None:
        return
    style = getattr(settings, "wind_style", "NONE")
    meshes = [ob for m in models[:1] for ob in m.meshes] if models else []
    if style == "NONE" or moment is None or not meshes:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    lo, hi = mdl.rest_bounds(meshes)
    height = max(hi.z - lo.z, 1e-3)
    middle = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z + 0.6 * height))
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    ob = _field(collection, mask)
    field = ob.field
    if style == "WHIRL":
        field.type = "VORTEX"
        way = Vector((0.0, 0.0, 1.0))
        ob.location = middle
    else:
        field.type = "WIND"
        if style == "UP":
            way = Vector((0.0, 0.0, 1.0))
        else:  # from the camera (MMD's front, -Y, without one) towards her, from her left, a little upwards
            camera = shots.carrier(scene, mask)
            way = middle - camera.matrix_world.translation if camera is not None else Vector((0.0, 1.0, 0.0))
            way.z = 0.0
            way = way.normalized() if way.length > 1e-6 else Vector((0.0, 1.0, 0.0))
            way = Matrix.Rotation(math.radians(SIDE), 3, "Z") @ way
            way = (way + Vector((0.0, 0.0, 0.3))).normalized()
        ob.location = middle - way * height
    ob.rotation_euler = way.to_track_quat("Z", "Y").to_euler()
    field.noise = NOISE
    field.seed = 7
    m = float(moment)
    rise, end = m - RISE * fps, m + max(settings.wind_time, 0.2) * fps
    hold = m + 0.3 * (end - m)
    strength = STRENGTH[style] * max(settings.wind_strength, 0.0)
    field.driver_remove("strength")
    driver = field.driver_add("strength").driver
    driver.type = "SCRIPTED"
    driver.expression = "%.2f*smoothstep(%.1f,%.1f,frame)*(1-smoothstep(%.1f,%.1f,frame))" % (
        strength, rise, m, hold, end)
    rbw = scene.rigidbody_world
    weights = rbw.effector_weights if rbw is not None else None
    if weights is not None and weights.collection is not None and ob.name not in weights.collection.objects:
        weights.collection.objects.link(ob)  # (the world takes only the fields of its own collection)
    _reset(scene)
