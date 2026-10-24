"""The photo first (拍立得, 1.16): a cover (cover.py, style POLAROID). A polaroid shows up in her hand, and in it she
is dancing already in the new outfit, small; a little before the big moment it flies at the camera and fills the
picture, the outfits swap behind it, and it tumbles away: the girl in the photo has come to life (the badge and
polaroid transitions of short videos, 「画里先换好」).

The card is ours, parented to the camera like the other lens covers and keyed in its space: held where her palm is on
the picture (as the coverage check saw it, every few frames), then rushing at the lens. On it, the figure: an object
of ours parented to the card carrying cover_nodes' photo group, which takes a twin of each mesh of the new outfit
(the same mesh data posed by its armature only: the whole outfit as it is when complete), moves it from round her
centre bone (an empty following it) onto the photo, small, pressed flat and cut to the photo's edge.
"""

import math

import bpy
from mathutils import Vector

from . import materials

IN = 2.2  # seconds before the moment it shows up in her hand ...
FLY = 0.5  # ... it flies at the camera over this long before the moment ...
AWAY = 0.55  # ... and tumbles away over this long after it
HELD = 0.24  # its height in her hand (model heights)
PHOTO = (0.78, 0.78, 0.0, 0.1)  # the photo on the card (a unit wide): its width, height and middle (x, y)
CARD = (1.0, 1.22)  # the card: wide and tall


def card_mesh(name):
    """The polaroid: a white card a unit wide (X) and CARD[1] tall (Y), facing +Z (the camera), the photo a little
    above its middle (mmdd_photo 1 there), a UV over it."""
    w, h = 0.5 * CARD[0], 0.5 * CARD[1]
    pw, ph, px, py = 0.5 * PHOTO[0], 0.5 * PHOTO[1], PHOTO[2], PHOTO[3]
    verts = [(-w, -h, 0.0), (w, -h, 0.0), (w, h, 0.0), (-w, h, 0.0),
             (px - pw, py - ph, 0.0005), (px + pw, py - ph, 0.0005), (px + pw, py + ph, 0.0005), (px - pw, py + ph,
                                                                                                  0.0005)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new("mmdd_photo", "FLOAT", "FACE")
    attr.data.foreach_set("value", [0.0, 1.0])
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        x, y, _z = me.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = ((x + w) / (2 * w), (y + h) / (2 * h))
    me.update()
    return me


def _twin(source, mask, collection):
    """The hidden twin of a mesh of the new outfit: its mesh data, posed by its armature only (a cover piece)."""
    from .cover import NAME, P_COVER, P_KEY, P_KIND, objects

    ob = next((o for o in objects(mask, "PHOTO_TWIN") if o.get(P_KEY) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s Photo Twin %s" % (NAME, source.name), source.data)
        collection.objects.link(ob)
        ob[P_COVER], ob[P_KIND], ob[P_KEY] = mask, "PHOTO_TWIN", source.name
        ob.hide_select = True
        ob.hide_render = True
        ob.display_type = "WIRE"
    ob.parent = source.parent
    ob.parent_type = source.parent_type
    ob.parent_bone = source.parent_bone
    ob.matrix_parent_inverse = source.matrix_parent_inverse.copy()
    ob.matrix_basis = source.matrix_basis.copy()
    for mod in list(ob.modifiers):
        ob.modifiers.remove(mod)
    for mod in source.modifiers:
        if mod.type != "ARMATURE":
            continue
        twin = ob.modifiers.new(mod.name, "ARMATURE")
        for prop in ("object", "use_vertex_groups", "use_bone_envelopes", "use_deform_preserve_volume",
                     "use_multi_modifier", "vertex_group", "invert_vertex_group"):
            setattr(twin, prop, getattr(mod, prop))
    try:
        ob.hide_set(True)
    except RuntimeError:  # (not in the view layer: hidden there anyway)
        pass
    return ob


def place(settings, mask, seen, moment, camera, collection, fps, aspect, height, models):
    """The polaroid for the big moment at frame `moment` (cover.sync, style POLAROID): the card, the figure on it, the
    twins of the new outfit and the empty at her centre."""
    from . import cover, cover_nodes
    from .model import rest_bounds
    from .node_groups import input_identifiers

    scene = settings.id_data
    m = float(moment)
    target = models[-1] if models else None
    if target is None or not target.meshes:
        return None
    first, fly = m - IN * fps, m - FLY * fps
    gone = m + AWAY * fps
    depth_end = cover._near_depth(camera)
    _c, w_end, h_end = cover._plane(scene, camera, depth_end)
    inverse = camera.matrix_world.inverted()
    card = cover._piece(mask, "POLAROID", collection, "polaroid:1", lambda: card_mesh(cover.NAME + " Polaroid"),
                        parent=camera)
    if not card.data.materials:
        card.data.materials.append(materials.ensure_cover_material("POLAROID"))
    card.rotation_mode = "XYZ"
    # held where her palm is (every few frames as the coverage check saw it), then rushing at the lens
    keys = []
    f = first
    last_palm = None
    while f < fly:
        here = cover.row(seen, f)
        palm = None
        for key in ("palm_r", "palm_l"):
            if here is not None and cover._finite(here[key]):
                palm = inverse @ (Vector(here[key]) + Vector((0.0, 0.0, 0.06 * height)))
                break
        if palm is None:
            palm = last_palm if last_palm is not None else Vector((0.15 * h_end, -0.1 * h_end, -6.0 * depth_end))
        palm.z = min(palm.z, -2.0 * depth_end)
        # (kept in the picture when her hand reaches past its edge)
        _c_, pic_w, pic_h = cover._plane(scene, camera, -palm.z)
        half_w, half_h = 0.5 * HELD * height * CARD[0] / CARD[1], 0.5 * HELD * height
        palm.x = min(max(palm.x, -0.5 * pic_w + 1.15 * half_w), 0.5 * pic_w - 1.15 * half_w)
        palm.y = min(max(palm.y, -0.5 * pic_h + 1.15 * half_h), 0.5 * pic_h - 1.15 * half_h)
        keys.append((f, palm.copy(), HELD * height / CARD[1]))
        last_palm = palm
        f += 3.0
    if not keys:
        keys.append((first, Vector((0.0, 0.0, -6.0 * depth_end)), HELD * height / CARD[1]))
    start_at = keys[-1][1]
    fill = 1.15 * max(w_end, h_end * CARD[0] / CARD[1]) / CARD[0]  # (its width over the picture's, at the lens)
    for k in range(1, 7):
        u = k / 6.0
        eased = u * u * (3.0 - 2.0 * u)
        d = -start_at.z * (depth_end / -start_at.z) ** u
        size = (HELD * height / CARD[1]) * (1.0 - eased) * d / -start_at.z + fill * eased
        loc = Vector((start_at.x * (1.0 - eased) * d / -start_at.z, start_at.y * (1.0 - eased) * d / -start_at.z, -d))
        keys.append((fly + u * (m - 1.0 - fly), loc, size))
    keys.append((m + 1.0, Vector((0.0, 0.0, -depth_end)), fill))
    keys.append((gone, Vector((0.25 * w_end, -1.4 * h_end, -depth_end)), fill))
    cover._key(card, "location", [(f_, loc) for f_, loc, _s in keys])
    cover._key(card, "scale", [(f_, (s_, s_, s_)) for f_, _l, s_ in keys])
    cover._key(card, "rotation_euler", ((first, (0.0, 0.0, math.radians(-6.0))), (fly, (0.0, 0.0, math.radians(4.0))),
                                        (m - 1.0, (0.0, 0.0, 0.0)), (m + 1.0, (0.0, 0.0, 0.0)),
                                        (gone, (math.radians(35.0), 0.0, math.radians(-40.0)))))
    cover._shown(card, int(math.floor(first)), int(math.ceil(gone)))
    # her centre (the figure turns about it), the twins, the figure on the photo
    arm = target.armature
    from .spirit import CENTRE

    centre_bone = next((n for n in CENTRE if arm is not None and n in arm.data.bones), None)
    anchor = next(iter(cover.objects(mask, "PHOTO_ANCHOR")), None)
    if anchor is None:
        anchor = cover._link(bpy.data.objects.new(cover.NAME + " Photo Anchor", None), mask, "PHOTO_ANCHOR",
                             collection)
        anchor.hide_render = True
    for c in list(anchor.constraints):
        anchor.constraints.remove(c)
    lo, hi = rest_bounds(target.meshes)
    anchor.location = (0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z + 0.5 * (hi.z - lo.z))
    if centre_bone is not None:
        con = anchor.constraints.new("COPY_LOCATION")
        con.target, con.subtarget = arm, centre_bone
    twins = [_twin(ob, mask, collection) for ob in target.meshes]
    for ob in cover.objects(mask, "PHOTO_TWIN"):
        if ob not in twins:
            bpy.data.objects.remove(ob)
    group = cover_nodes.ensure_photo_group()
    ids = input_identifiers(group)
    figures = []
    for k, twin in enumerate(twins):
        kind = "PHOTO_FIGURE"
        fig = next((o for o in cover.objects(mask, kind) if o.get(cover.P_KEY) == twin.name), None)
        if fig is None:
            fig = cover._link(bpy.data.objects.new("%s Photo Figure %d" % (cover.NAME, k),
                                                   bpy.data.meshes.new(cover.NAME + " Photo Figure")), mask, kind,
                              collection, twin.name)
        fig.parent = card
        fig.location, fig.rotation_euler, fig.scale = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        cover._modifier(fig, group, {"Twin": twin, "Anchor": anchor, "Height": max(hi.z - lo.z, 1e-6),
                                     "Photo Width": PHOTO[0], "Photo Height": PHOTO[1],
                                     "Photo X": PHOTO[2], "Photo Y": PHOTO[3]})
        cover._shown(fig, int(math.floor(first)), int(math.ceil(gone)))
        figures.append(fig)
    for ob in cover.objects(mask, "PHOTO_FIGURE"):
        if ob not in figures:
            cover._delete(ob)
    del ids
    return card
