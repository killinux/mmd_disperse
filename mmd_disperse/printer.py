"""Printed layer by layer (激光打印, 1.14, after the printers of Tron: Ares): the path Printed Layer by Layer is the
upward sweep in whole layers (the distances of the sweep up rounded down to a Layer Height of the model's height over
Layers, so each layer comes at once), the newest layers glowing hot in the glow colour with the lines between them
(materials.add_print). Round the dancer laser heads shoot beams at the layer being printed (each frame a point of it at
random, the beam stopping at the first part of her in its way), and a light in the glow colour rides up with it.
Thin supports hold up what hangs over: each from a face of the new outfit that looks down, straight down to the part
of her below it (both ends on her, so they dance along), or (1.25) where nothing of her is below it, down to the build
plate under her feet (its foot stays there), printed with the layers from the plate up; once the print is done they
snap off one after another and break into little cubes that fall and fade. The plate glows under her while she is
printed.

The supports are picked at build on the rest pose (a record on the mask: for each mesh of the new outfit, the three
vertices and weights of each end of each support and the two layers it runs between). They hang on a hidden twin of
each mesh of the new outfit: the same mesh data with only its armature, so the twin is the whole dancing body, also
where the print has not got to yet; the supports and the lasers read it with Object Info (cover_nodes' Print Supports
and Print Lasers). Removing the effect takes it all away."""

import fnmatch
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import arrival, materials, shots
from . import model as mdl

P_PRINT = "mmd_disperse_print"  # on the mask: the record of the supports; on our objects: the mask ...
P_KIND = "mmd_disperse_print_kind"  # ... TWIN, SUPPORTS, LASERS, LIGHT
P_SOURCE = "mmd_disperse_print_source"  # on a twin and its supports: the name of the mesh they belong to
NAME = "MMD Disperse Print"
DOWN = 0.55  # a face holds a support when it looks down at least this much (the cosine with straight down)
SPACING = 0.03  # supports at least this far apart (model heights) ...
LONGEST = 0.28  # ... none longer than this ...
SHORTEST = 0.006  # ... or shorter
MOST = 400  # supports at most (all the meshes of the new outfit)
TRIES = 8000  # points tried (picked by area on the faces that look down)
ROD = 0.0024  # radius of a support (model heights)
SNAP = 0.15  # seconds after the print the supports start to snap off, one after another over ...
SNAP_SPREAD = 0.35  # ... these seconds, each breaking into cubes that fall and fade over ...
CRUMBLE = 0.7  # ... these
GRAVITY = 6.1  # model heights a second squared (9.8 m/s² on a 1.6 m dancer)
HEADS_OUT = 0.55  # the laser heads stand round her this far out (model heights) ...
HEADS_UP = 1.15  # ... this high
BEAM = 0.0013  # radius of a beam (model heights)
SPOT = 0.012  # the glowing spot where a beam hits (model heights)
LIGHT_POWER = 6.0  # the light on the layer, watts per square model height
PLATE = 0.85  # (1.25) the build plate under her: this wide (model heights); supports down to it: at most ...
PLATE_MOST = 12  # ... these a mesh, ...
PLATE_SPACING = 0.08  # ... this far apart (model heights) ...
PLATE_REACH = 0.6  # ... from no higher up her than this (model heights: not from her shoulders or bust)


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_PRINT) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def remove(mask):
    for ob in objects(mask):
        _delete(ob)
    if not any(ob.get(P_PRINT) is not None for ob in bpy.data.objects):
        from . import cover_nodes

        cover_nodes.remove_print_assets()


def record(mask):
    rec = mask.get(P_PRINT) if mask is not None else None
    return rec.to_dict() if rec is not None and hasattr(rec, "to_dict") else None


def layer_height(settings, height):
    return height / float(max(settings.print_layers, 1))


def layered(values, layer):
    """Arrival distances rounded down to whole layers (each layer comes at once)."""
    return [np.floor(v / layer + 1e-6) * layer for v in values]


# --------------------------------------------------------------------------- build: the supports

def _bones(ob):
    """The bone each vertex of `ob` follows most (its vertex group's name, '' for none) and the armature's parents."""
    me = ob.data
    names = {g.index: g.name for g in ob.vertex_groups}
    arm = next((m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object is not None), None)
    parents = {}
    if arm is not None:
        parents = {b.name: (b.parent.name if b.parent else "") for b in arm.data.bones}

    def main(index):
        best, weight = "", 0.0
        for g in me.vertices[int(index)].groups:
            name = names.get(g.group, "")
            if g.weight > weight and name in parents:
                best, weight = name, g.weight
        return best

    return main, parents


def _together(a, b, parents):
    """Bones that move (nearly) together: the same, one the other's parent, or two children of one bone."""
    if not a or not b:
        return False
    pa, pb = parents.get(a, ""), parents.get(b, "")
    return a == b or pa == b or pb == a or (pa and pa == pb)


def _supports(ob, axis, lo, height, layer, lead, patterns, rng):
    """The supports of one mesh of the new outfit: (top vertices and weights, bottom vertices and weights, bottom
    arrival, top arrival), each a list; None without any."""
    me = ob.data
    me.calc_loop_triangles()
    count = len(me.loop_triangles)
    if not count or not len(me.vertices):
        return None
    tris = np.empty(count * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    tris = tris.reshape(-1, 3)
    slot = np.empty(count, dtype=np.int64)
    me.loop_triangles.foreach_get("material_index", slot)
    locked = np.array([s.material is not None and any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                       for p in patterns) for s in ob.material_slots] + [False])
    free = ~locked[np.minimum(slot, len(locked) - 1)]
    points = mdl.rest_points_world(ob)
    p0, p1, p2 = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    area = np.linalg.norm(cross, axis=1)
    facing = (cross @ axis) / np.maximum(area, 1e-12)
    down = np.nonzero(free & (facing < -DOWN) & (area > 1e-12))[0]
    if not len(down):
        return None
    pick = rng.choice(down, size=min(TRIES, 20 * len(down)), p=area[down] / area[down].sum())
    r1, r2 = rng.random(len(pick)), rng.random(len(pick))
    s = np.sqrt(r1)
    weights = np.stack([1.0 - s, s * (1.0 - r2), s * r2], axis=1)
    tops = (weights[:, 0, None] * p0[pick] + weights[:, 1, None] * p1[pick] + weights[:, 2, None] * p2[pick])
    tree = BVHTree.FromPolygons(points.tolist(), tris.tolist(), all_triangles=True)
    main, parents = _bones(ob)
    cell = SPACING * height
    taken = {}
    on_plate = []
    out = ([], [], [], [], [], [])
    up = Vector(axis.tolist())
    for k in range(len(pick)):
        top = Vector(tops[k].tolist())
        key = tuple(int(math.floor(c / cell)) for c in top)
        near = [taken[(key[0] + i, key[1] + j, key[2] + m)] for i in (-1, 0, 1) for j in (-1, 0, 1)
                for m in (-1, 0, 1) if (key[0] + i, key[1] + j, key[2] + m) in taken]
        if any((p - top).length < cell for p in near):
            continue
        hit, normal, index, dist = tree.ray_cast(top - up * (0.003 * height), -up, LONGEST * height)
        if hit is None:
            # (1.25) nothing of her right below it: down to the build plate if nothing of her is in the way at all
            drop = top.dot(up) - lo
            if drop < SHORTEST * height or drop > PLATE_REACH * height or len(on_plate) >= PLATE_MOST or any(
                    (q - top).length < PLATE_SPACING * height for q in on_plate):
                continue
            if tree.ray_cast(top - up * (0.003 * height), -up, drop)[0] is not None:
                continue
            taken[key] = top
            on_plate.append(top)
            out[0].extend(int(i) for i in tris[pick[k]])
            out[1].extend(float(w) for w in weights[k])
            out[2].extend((-1, -1, -1))  # (its foot on the plate: where, in place of the weights)
            out[3].extend(float(c) for c in top - up * drop)
            out[4].append(float(lead))
            out[5].append(float(math.floor((top.dot(up) - lo) / layer + 1e-6) * layer + lead))
            continue
        if dist < SHORTEST * height or normal.dot(up) < -0.2:
            continue
        below = tris[index]
        if not _together(main(tris[pick[k]][0]), main(below[0]), parents):
            continue
        # where the ray hit, in its triangle's corners
        a, b, c = (Vector(points[i].tolist()) for i in below)
        v0, v1, v2 = b - a, c - a, hit - a
        d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-20:
            continue
        wb = (d11 * d20 - d01 * d21) / den
        wc = (d00 * d21 - d01 * d20) / den
        taken[key] = top
        out[0].extend(int(i) for i in tris[pick[k]])
        out[1].extend(float(w) for w in weights[k])
        out[2].extend(int(i) for i in below)
        out[3].extend((1.0 - wb - wc, wb, wc))
        out[4].append(float(math.floor((hit.dot(up) - lo) / layer + 1e-6) * layer + lead))
        out[5].append(float(math.floor((top.dot(up) - lo) / layer + 1e-6) * layer + lead))
    return out if out[4] else None


def build_record(settings, target, meshes, frame, height, layer, lead):
    """What the mask keeps for the print (see the module's doc): the layer and lead, the up axis and where the layers
    start, the supports of each mesh of the new outfit."""
    axis = np.asarray(arrival.axes(frame, "PRINT")[0], dtype=np.float64)
    lo = min(float((mdl.rest_points_world(ob) @ axis).min()) for ob in meshes if len(ob.data.vertices))
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    rng = np.random.default_rng(37)
    found = []
    for ob in target.meshes if target else ():
        sup = _supports(ob, axis, lo, height, layer, lead, patterns, rng) if settings.print_supports else None
        if sup is not None:
            found.append((ob, sup))
    total = sum(len(sup[4]) for _ob, sup in found)
    rec = {"layer": layer, "lead": lead, "lo": lo, "axis": [float(v) for v in axis], "height": height,
           "meshes": [], "supports": 0, "plate": bool(settings.print_supports)}
    for ob, sup in found:
        keep = len(sup[4]) if total <= MOST else max(1, int(round(MOST * len(sup[4]) / float(total))))
        order = np.random.default_rng(41).permutation(len(sup[4]))[:keep] if keep < len(sup[4]) else range(keep)
        entry = {"name": ob.name}
        for key, values, width in (("top", sup[0], 3), ("top_w", sup[1], 3), ("bottom", sup[2], 3),
                                   ("bottom_w", sup[3], 3), ("a0", sup[4], 1), ("a1", sup[5], 1)):
            entry[key] = [values[width * i + j] for i in order for j in range(width)]
        rec["meshes"].append(entry)
        rec["supports"] += keep
    return rec


# --------------------------------------------------------------------------- sync: twins, supports, lasers, light

def _ours(name, collection, mask, kind, source=""):
    ob = next((o for o in objects(mask, kind) if o.get(P_SOURCE, "") == source), None)
    if ob is None:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        collection.objects.link(ob)
        ob[P_PRINT] = mask
        ob[P_KIND] = kind
        ob[P_SOURCE] = source
        ob.hide_select = True
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
    return ob


def _twin(source, mask, collection, k):
    """The hidden twin of a mesh of the new outfit: its mesh data, posed by its armature only."""
    ob = next((o for o in objects(mask, "TWIN") if o.get(P_SOURCE) == source.name), None)
    if ob is None or ob.data != source.data:
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new("%s Twin %d" % (NAME, k), source.data)
        collection.objects.link(ob)
        ob[P_PRINT] = mask
        ob[P_KIND] = "TWIN"
        ob[P_SOURCE] = source.name
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


def _fill(ob, positions, attrs):
    """Our points at `positions` with the attributes `attrs` (name: list of floats or of 3-tuples)."""
    me = ob.data
    me.clear_geometry()
    me.from_pydata([tuple(p) for p in positions], [], [])
    for name, values in attrs.items():
        vector = bool(values) and isinstance(values[0], (tuple, list, Vector))
        kind = "FLOAT_VECTOR" if vector else "FLOAT"
        attr = me.attributes.get(name)
        if attr is not None and attr.data_type != kind:
            me.attributes.remove(attr)
            attr = None
        attr = attr or me.attributes.new(name, kind, "POINT")
        flat = [float(v) for item in values for v in item] if vector else [float(v) for v in values]
        attr.data.foreach_set("vector" if vector else "value", flat)
    me.update()


def _modifier(ob, group, values):
    from .node_groups import input_identifiers

    mod = next((m for m in ob.modifiers if m.type == "NODES"), None) or ob.modifiers.new(NAME, "NODES")
    mod.node_group = group
    ids = input_identifiers(group)
    for key, value in values.items():
        if ids.get(key) is not None:
            mod[ids[key]] = value
    ob.update_tag()
    return mod


def _printed_faces(ob, patterns):
    """How many faces of `ob` get printed: those whose material is not locked."""
    me = ob.data
    if not len(me.polygons):
        return 0
    locked = np.array([s.material is not None and any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                       for p in patterns) for s in ob.material_slots] + [False])
    slots = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("material_index", slots)
    return int((~locked[np.minimum(slots, len(locked) - 1)]).sum())


def _heads(scene, mask, centre, count, height):
    """Where the laser heads are (world): round her above her head, the first two either side of the way to the camera
    (in front of her), the rest spread round behind."""
    camera = shots.carrier(scene, mask)
    toward = camera.matrix_world.translation - centre if camera is not None else Vector((0.0, -1.0, 0.0))
    toward.z = 0.0
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    base = math.atan2(toward.y, toward.x)
    out = []
    for k in range(count):
        angle = base + math.radians(180.0 / count) + 2.0 * math.pi * k / count
        out.append(centre + Vector((math.cos(angle), math.sin(angle), 0.0)) * (HEADS_OUT * height)
                   + Vector((0.0, 0.0, HEADS_UP * height * (1.0 - 0.06 * (k % 2)))))
    return out


def _light(mask, collection, rec, centre, color, height, frames):
    """The light in the glow colour on the layer being printed: it rides up with the front (a driver on the mask's
    size) while the print goes on (`frames`: first, last)."""
    from .cover import _clear_keys
    from .pyro import _key

    light = next(iter(objects(mask, "LIGHT")), None)
    if light is None:
        light = bpy.data.objects.new(NAME + " Light", bpy.data.lights.new(NAME + " Light", "POINT"))
        collection.objects.link(light)
        light[P_PRINT] = mask
        light[P_KIND] = "LIGHT"
        light.hide_select = True
    _clear_keys(light.data)
    light.data.color = tuple(color)
    light.data.shadow_soft_size = 0.3 * height
    light.location = (centre.x, centre.y, rec["lo"])
    light.driver_remove("location", 2)
    driver = light.driver_add("location", 2).driver
    driver.type = "SCRIPTED"
    var = driver.variables.new()
    var.name = "r"
    var.type = "SINGLE_PROP"
    var.targets[0].id = mask
    var.targets[0].data_path = "scale[0]"
    span = float(rec["height"])
    driver.expression = "%.4f + clamp(r - %.4f, 0, %.4f)" % (rec["lo"], rec["lead"], span)
    peak = LIGHT_POWER * height * height
    first, last = frames
    _key(light.data, "energy", [(first - 1.0, 0.0), (first + 2.0, peak), (last, peak), (last + 4.0, 0.0)])


def sync(settings, mask, models, frame_at):
    """The supports, the laser heads and their beams and the light as the record of the build says (the path Printed
    Layer by Layer); nothing for any other path."""
    from . import cover_nodes

    rec = record(mask)
    if rec is None or mask.get("mmd_disperse_path") != "PRINT" or settings.direction != "GROW":
        if mask is not None:
            remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    height = float(rec["height"])
    layer, lead = float(rec["layer"]), float(rec["lead"])
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    target = mdl.resolve(settings.target) if settings.target else None
    sources = list(target.meshes) if target else []
    first = frame_at(lead)
    last = frame_at(lead + height)
    first = float(first) if first is not None else float(settings.frame_start)
    last = float(last) if last is not None else float(settings.frame_end)
    color = tuple(settings.glow_color)
    keep = set()
    twins = {}
    for k, source in enumerate(sources):
        twins[source.name] = _twin(source, mask, collection, k)
        keep.add(twins[source.name].name)
    # the supports of each mesh
    rod_material = materials.ensure_cover_material("PRINT_ROD")
    for k, entry in enumerate(rec.get("meshes", [])):
        twin = twins.get(entry["name"])
        if twin is None or not entry["a0"]:
            continue
        n = len(entry["a0"])
        ob = _ours("%s Supports %d" % (NAME, k), collection, mask, "SUPPORTS", entry["name"])
        keep.add(ob.name)
        ob["mmdd_color"] = color
        triples = {key: [tuple(entry[key][3 * i:3 * i + 3]) for i in range(n)]
                   for key in ("top", "top_w", "bottom", "bottom_w")}
        rng = np.random.default_rng(43 + k)
        _fill(ob, [(0.0, 0.0, 0.0)] * n, {
            "mmdd_top": triples["top"], "mmdd_top_w": triples["top_w"], "mmdd_bottom": triples["bottom"],
            "mmdd_bottom_w": triples["bottom_w"], "mmdd_a0": entry["a0"], "mmdd_a1": entry["a1"],
            "mmdd_r": [float(v) for v in rng.random(n)]})
        _modifier(ob, cover_nodes.ensure_print_supports_group(), {
            "Twin": twin, "Mask": mask, "Layer": layer, "Size": ROD * height, "Snap": last + SNAP * fps,
            "Spread": SNAP_SPREAD * fps, "Crumble": CRUMBLE * fps, "Gravity": GRAVITY * height / (fps * fps),
            "Rod": cover_nodes.ensure_rod_object(scene), "Tip": cover_nodes.ensure_tip_object(scene),
            "Cube": cover_nodes.ensure_cube_object(scene),
            "Material": rod_material})
    # the laser heads, on the mesh with the most of the outfit that gets printed (not the locked hair or head)
    lo, hi = mdl.rest_bounds(sources) if sources else (None, None)
    if sources and settings.print_lasers > 0:
        patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
        main = max(sources, key=lambda ob: _printed_faces(ob, patterns))
        centre = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
        heads = _heads(scene, mask, centre, settings.print_lasers, height)
        ob = _ours(NAME + " Lasers", collection, mask, "LASERS")
        keep.add(ob.name)
        ob["mmdd_color"] = color
        _fill(ob, heads, {"mmdd_head": [float(i) for i in range(len(heads))]})
        _modifier(ob, cover_nodes.ensure_print_lasers_group(), {
            "Twin": twins[main.name], "Mask": mask, "Lead": lead, "Layer": layer, "Span": height,
            "Beam": BEAM * height, "Spot": SPOT * height, "Beam Shape": cover_nodes.ensure_beam_object(scene),
            "Head": cover_nodes.ensure_laser_head_object(scene),
            "Head Size": 0.035 * height, "Material": materials.ensure_cover_material("LASER")})
        _light(mask, collection, rec, centre, color, height, (first, last))
        keep.update(o.name for o in objects(mask, "LIGHT"))
    # (1.25) the build plate under her feet, while she is printed and her supports crumble
    if sources and rec.get("plate", False):  # (with the supports: chosen at building time)
        plate = _ours(NAME + " Plate", collection, mask, "PLATE")
        keep.add(plate.name)
        # (its top a little above her soles: she stands on it, and a floor at her feet does not hide it)
        _plate_mesh(plate, Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, float(rec["lo"]) + 0.004 * height)),
                    PLATE * height)
        plate["mmdd_color"] = color
        if not plate.data.materials:
            plate.data.materials.append(materials.ensure_cover_material("PRINT_PLATE"))
        _modifier(plate, cover_nodes.ensure_chain_group(), {
            "From": first - 3.0, "To": last + (SNAP + SNAP_SPREAD + CRUMBLE) * fps + 6.0})
    for ob in objects(mask):
        if ob.name not in keep:
            _delete(ob)


def _plate_mesh(ob, centre, size):
    """The build plate: a thin square `size` wide on the floor at `centre`, its edge bevelled."""
    half, rim, depth = 0.5 * size, 0.47 * size, 0.012 * size
    x, y, z = centre
    top = [(x + sx * half, y + sy * half, z) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    low = [(x + sx * rim, y + sy * rim, z - depth) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = ob.data
    me.clear_geometry()
    me.from_pydata(top + low, [], [(0, 1, 2, 3), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3),
                                   (7, 6, 5, 4)])
    layer = me.uv_layers.new(name="UVMap") if not me.uv_layers else me.uv_layers[0]
    for loop in me.loops:  # (the top face across the plate 0 .. 1: the material draws its grid)
        vx, vy, _vz = me.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = ((vx - x) / size + 0.5, (vy - y) / size + 0.5)
    me.update()
