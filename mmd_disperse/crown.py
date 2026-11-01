"""The gem crown (宝石冠, 1.26): on the way to the big moment a crown of crystal grows over her head out of a glint
(Pokémon's Tera Jewel, worn as it terastallizes): a ring of crystal points round a tall one in the middle, turning
slowly and bobbing; it flashes at the moment, floats over the new outfit for Crown Time and then bursts (swells and
is gone in a flash of light).

Our object: the crown (a mesh made here, its faces flat: facets), following the tip of her head bone (kept upright),
sized and turned by drivers on the frame; its material (the cover material CROWN) flashes as its mmdd_crown_flash says
and shows as much as its mmdd_crown_fade (custom properties, driven, read as object attributes).
"""

import math

import bpy

from . import materials

P_CROWN = "mmd_disperse_crown"  # on our object: the mask of its effect
NAME = "MMD Disperse Gem Crown"
SIZE = 0.2  # across, a share of her height
ABOVE = 0.06  # its bottom this far over the top of her head (a share of her height)
GROW = (1.1, 0.6)  # it grows from this many seconds before the moment to this many
BURST = 0.3  # seconds it takes to burst at the end
TURN = 0.6  # radians a second it turns
POINTS = 6  # crystal points round the middle one ...
RING = 0.33  # ... this far out (its width is 1) ...
LEAN = 0.35  # ... leaning out this much (sideways for each up)
HEIGHTS = (0.5, 0.38)  # ... every other one this tall (its own length along its lean)


def objects(mask):
    return [ob for ob in bpy.data.objects if ob.get(P_CROWN) == mask]


def remove(mask):
    for ob in objects(mask):
        data = ob.data
        bpy.data.objects.remove(ob)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    if not any(ob.get(P_CROWN) is not None for ob in bpy.data.objects):
        mat = bpy.data.materials.get(materials._cover_name("CROWN"))
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)


def _crystal(verts, faces, centre, axis, radius, girdle, top, bottom, sides=6, turn=0.0):
    """A crystal point: a ring of `sides` corners `radius` round the point `girdle` along `axis` from `centre`, a tip
    `top` along it and one `bottom` back from the centre (flat facets, faces out)."""
    ax = axis.normalized()
    u = ax.orthogonal().normalized()
    v = ax.cross(u)
    mid = centre + ax * girdle
    first = len(verts)
    for k in range(sides):
        phi = turn + 2.0 * math.pi * k / sides
        verts.append(tuple(mid + radius * (math.cos(phi) * u + math.sin(phi) * v)))
    verts.append(tuple(centre + ax * top))
    verts.append(tuple(centre - ax * bottom))
    tip, foot = first + sides, first + sides + 1
    for k in range(sides):
        a, b = first + k, first + (k + 1) % sides
        faces.append((a, b, tip))
        faces.append((b, a, foot))


def crown_mesh():
    """The crown 1 unit across standing on z = 0: a tall crystal in the middle, POINTS round it leaning out."""
    from mathutils import Vector

    verts, faces = [], []
    _crystal(verts, faces, Vector((0.0, 0.0, 0.08)), Vector((0.0, 0.0, 1.0)), 0.1, 0.22, 0.78, 0.08)
    for i in range(POINTS):
        theta = 2.0 * math.pi * (i + 0.5) / POINTS
        out = Vector((math.cos(theta), math.sin(theta), 0.0))
        _crystal(verts, faces, RING * out + Vector((0.0, 0.0, 0.06)), out * LEAN + Vector((0.0, 0.0, 1.0)), 0.065,
                 0.12, HEIGHTS[i % 2], 0.06, turn=theta)
    me = bpy.data.meshes.new(NAME)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def _head(armature):
    from .motion import HEAD

    return next((n for n in HEAD if armature is not None and n in armature.data.bones), None)


def _drive(ob, path, expression, index=-1):
    ob.driver_remove(path, index)
    driver = ob.driver_add(path, index).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def sync(settings, mask, models, moment):
    """The crown as the panel says, round the big moment at frame `moment`; taken away when it is off."""
    from mathutils import Vector

    from .model import rest_bounds

    if mask is None:
        return
    model = next(iter(models), None) if models else None
    bone = _head(model.armature) if model is not None else None
    if not getattr(settings, "crown_enable", False) or moment is None or bone is None:
        remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    m = float(moment)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    ob = next(iter(objects(mask)), None)
    if ob is None:
        ob = bpy.data.objects.new(NAME, crown_mesh())
        collection.objects.link(ob)
        ob[P_CROWN] = mask
        ob.hide_select = True
        ob.data.materials.append(materials.ensure_cover_material("CROWN"))
    arm = model.armature
    lo, hi = rest_bounds(model.meshes)
    height = max(hi.z - lo.z, 1e-3)
    tip = arm.matrix_world @ arm.data.bones[bone].tail_local
    # over the top of her head, following the tip of her head bone (upright: the location only)
    ob.parent = None
    for con in list(ob.constraints):
        ob.constraints.remove(con)
    con = ob.constraints.new("COPY_LOCATION")
    con.target, con.subtarget = arm, bone
    con.head_tail = 1.0
    con.use_offset = True
    ob.location = Vector((0.0, 0.0, hi.z - tip.z + ABOVE * height))
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (0.0, 0.0, 0.0)
    size = SIZE * height
    a0, a1 = m - GROW[0] * fps, m - GROW[1] * fps
    end = m + settings.crown_time * fps
    gone = end + BURST * fps
    grow = "smoothstep(%.2f, %.2f, frame) * (1 + 0.4 * smoothstep(%.2f, %.2f, frame)) * (1 - smoothstep(%.2f, %.2f, " \
           "frame))" % (a0, a1, end, gone, gone, gone + 0.5)
    for i in range(3):
        _drive(ob, "scale", "%.5f * %s" % (size, grow), i)
    _drive(ob, "rotation_euler", "frame * %.5f" % (TURN / fps), 2)
    _drive(ob, "location", "%.5f + %.5f * sin(frame * %.4f)" % (ob.location.z, 0.006 * height, 2.4 / fps), 2)
    ob["mmdd_crown_flash"] = 0.0
    ob["mmdd_crown_fade"] = 1.0
    _drive(ob, '["mmdd_crown_flash"]', "smoothstep(%.2f, %.2f, frame) * (1 - smoothstep(%.2f, %.2f, frame)) + "
                                       "smoothstep(%.2f, %.2f, frame) * (1 - smoothstep(%.2f, %.2f, frame)) + "
                                       "smoothstep(%.2f, %.2f, frame)"
           % (a0, a0 + 3.0, a0 + 3.0, a1, m - 4.0, m, m, m + 10.0, end, gone))
    _drive(ob, '["mmdd_crown_fade"]', "1 - smoothstep(%.2f, %.2f, frame)" % (end, gone))
    gem = settings.old_surface == "GEM"
    materials.update_crown(tuple(settings.surface_color if gem else settings.glow_color))
    for flag in ("visible_shadow",):
        if hasattr(ob, flag):
            setattr(ob, flag, False)
    ob.update_tag()
