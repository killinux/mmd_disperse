"""A star glinting in the eyes (1.12): with Start On Eye Contact, as the dancer looks straight into the camera a
four-pointed star of light flashes over each eye: a flat star of ours carried by the eye bones (the head's when there
are none), turned to face the camera, growing in at once and fading out.
"""

import math

import bpy
from mathutils import Matrix, Vector

from . import materials, motion

NAME = "MMD Disperse Eye Glint"
P_GLINT = "mmd_disperse_glint"  # on the stars: the mask of their effect ...
P_KEY = "mmd_disperse_glint_key"  # ... and what they were made for
SIZE = 0.045  # how far across the star reaches, a share of the model height
AHEAD = 0.012  # how far in front of the eye it floats, a share of the model height
EYE_APART = 0.018  # without eye bones: how far each eye is from between them, a share of the model height
RISE = 0.06  # seconds it takes to grow in ...
FALL = 0.45  # ... and to fade out after


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_GLINT) == mask]


def _delete(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def _star_mesh():
    """A flat star in the XY plane, 1 across: four long points (up, down, left, right), four short ones between them,
    ATTR_EDGE 1 at the middle .. 0 at the tips."""
    verts, edge = [(0.0, 0.0, 0.0)], [1.0]
    points = 8
    for k in range(points):
        angle = 2.0 * math.pi * k / points
        tip = 0.5 if k % 2 == 0 else 0.16
        verts.append((tip * math.cos(angle), tip * math.sin(angle), 0.0))
        edge.append(0.0)
        waist = angle + math.pi / points
        verts.append((0.03 * math.cos(waist), 0.03 * math.sin(waist), 0.0))
        edge.append(0.7)
    faces = []
    for k in range(points):
        t, w, t_next = 1 + 2 * k, 2 + 2 * k, 1 + 2 * ((k + 1) % points)
        faces += [(0, t, w), (0, w, t_next)]
    me = bpy.data.meshes.new(NAME)
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new(materials.ATTR_EDGE, "FLOAT", "POINT")
    attr.data.foreach_set("value", edge)
    me.materials.append(materials.ensure_glint_material())
    me.update()
    return me


def _eyes(armature, height):
    """[(side, the bone that carries the star, its world rest spot)] of both eyes."""
    bones = armature.data.bones
    mw = armature.matrix_world
    head = next((bones[n] for n in motion.HEAD if n in bones), None)
    between = motion.rest_eyes(armature)
    front = (mw.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()  # MMD models face -Y
    out = []
    for k, side in enumerate(motion.SIDES):
        eye = next((bones[n] for n in motion.EYES[k] if n in bones), None)
        if eye is not None:
            spot = mw @ eye.head_local
        elif head is not None and between is not None:
            spot = mw @ (between + Vector((EYE_APART * height * (1.0 if side == "L" else -1.0), 0.0, 0.0)))
        else:
            continue
        out.append((side, eye or head, spot + front * (AHEAD * height)))
    return out


def sync(settings, mask, model):
    """The glint in the eyes for Start On Eye Contact, at the frame the eye contact was found (none when it was not)."""
    found = float(mask.get("mmd_disperse_trigger", -1.0))
    want = (settings.trigger == "GAZE" and found >= 0.0 and model is not None and model.armature is not None)
    obs = objects(mask)
    if not want:
        for ob in obs:
            _delete(ob)
        return
    scene = settings.id_data
    camera = scene.camera
    height = max(settings.size_reference, 1e-3)
    fps = scene.render.fps / scene.render.fps_base
    armature = model.armature
    materials.ensure_glint_material()  # (made before it is set: a new one would start dark)
    materials.update_glint_material(settings.glow_color, settings.edge_glow_strength)
    key = "%s:%.2f:%.4f:%s:%.3f" % (armature.name, found, height, camera.name if camera else "", fps)
    if obs and all(ob.get(P_KEY) == key for ob in obs):
        return
    for ob in obs:
        _delete(ob)
    collection = armature.users_collection[0] if armature.users_collection else scene.collection
    mw = armature.matrix_world
    for side, bone, spot in _eyes(armature, height):
        ob = bpy.data.objects.new("%s %s" % (NAME, side), _star_mesh())
        collection.objects.link(ob)
        ob[P_GLINT] = mask
        ob[P_KEY] = key
        ob.hide_select = True
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
        # carried by the bone (where it is on it in the rest pose)
        ob.parent = armature
        ob.parent_type = "BONE"
        ob.parent_bone = bone.name
        ob.matrix_parent_inverse = (mw @ bone.matrix_local @ Matrix.Translation((0.0, bone.length, 0.0))).inverted()
        ob.location = spot
        if camera is not None:  # turned to face the camera
            con = ob.constraints.new("COPY_ROTATION")
            con.target = camera
        size = SIZE * height
        for frame, s in ((found - 1.0, 0.0), (found + RISE * fps, 1.0), (found + (RISE + FALL) * fps, 0.0)):
            ob.scale = (size * s, size * s, size * s)
            ob.keyframe_insert("scale", frame=frame)


def remove(mask):
    for ob in objects(mask):
        _delete(ob)
    mat = bpy.data.materials.get(materials.GLINT_MATERIAL)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)
