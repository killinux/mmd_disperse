"""Many starting points (多点开花, 1.13): the outfit changes from several points of the body, each setting off at a
moment of its own (the path From Many Points: arrival.surface_distances with a delay for each seed, so a vertex
changes when the first front gets there: its landing frame plus its distance along the body over the pace), and
something lands on each point first:

* SPARKS (打铁花): on the beat a smith strikes molten iron behind the dancer and a fountain of golden sparks shoots
  up and rains down; the few that land on her are where the new outfit starts (the 2025 Spring Festival Gala's
  opening);
* SPLATS (随机斑点): blobs of paint fly at her from the camera's side and splat on her, the new outfit spreading out
  from each splat;
* TOKENS (信物上身): small tokens (stars, or an object of your own) fly onto her chest, wrists, waist and ankles one
  after another on the beat, and the new outfit spreads out from each (She-Ra's new suit, Miraculous' fused forms).

At build the points are picked on the old outfit (not on its locked parts) on the rest pose, with their landing frames
(on the beats with beat sync); the front keeps a pace of its own (linear, like the hand path), so the end frame
follows. What flies is a Geometry Nodes object of ours per mesh (cover_nodes' Origin Flights: each lands on the vertex
nearest its rest point, where that is now in the dance); the fountain is cover_nodes' Pieces. The landing frames are
read off the mask's keys, so they move with them (Start On). Removing the effect takes it all away."""

import fnmatch
import math

import bpy
import numpy as np
from mathutils import Vector

from . import arrival, beats, materials, motion, sampling
from . import model as mdl

STYLES = ("SPARKS", "SPLATS", "TOKENS")
P_ORIGINS = "mmd_disperse_origins"  # on the mask: the record of the points; on our objects: the mask ...
P_KIND = "mmd_disperse_origins_kind"  # ... FLIGHTS_0 .., FOUNTAIN, LIGHT
NAME = "MMD Disperse Origins"
TRAVEL = 0.5  # the fronts travel this far (model heights) in the start-to-end frames ...
SPREAD = 0.55  # ... and the points land over this share of them
SPACING = 0.14  # the points at least this far apart (model heights) while there is room
# how each kind flies: seconds in the air, height of the arc and size (model heights), seconds shown before it sets
# off, seconds of the pop when it lands, seconds it stays after landing (tokens: until the change is over), how much
# bigger it pops
LOOK = {
    "SPARKS": dict(flight=0.9, arc=0.8, size=0.03, appear=0.0, pop=0.2, stay=0.25, burst=2.0),
    "SPLATS": dict(flight=0.3, arc=0.1, size=0.07, appear=0.08, pop=0.25, stay=0.6, burst=0.8),
    "TOKENS": dict(flight=0.45, arc=0.12, size=0.05, appear=0.35, pop=0.3, stay=None, burst=1.0),
}
SMITH_BEHIND = 0.45  # the smith strikes this far behind her (model heights) ...
SMITH_UP = 0.1  # ... the iron this high
STRIKE_GAP = 0.6  # seconds between two strikes (without beats; at least this with them)
STRIKE_LANDS = 3  # sparks of a strike that land on her ...
STRIKE_SPREAD = 0.08  # ... this many seconds apart
FOUNTAIN = 70  # sparks of a strike that rain down round her ...
FOUNTAIN_UP = (3.0, 4.2)  # ... their speed up and ...
FOUNTAIN_SIDE = 0.5  # ... sideways (model heights a second) ...
FOUNTAIN_LIFE = 1.3  # ... seconds they last
GRAVITY = 6.1  # model heights a second squared (9.8 m/s² on a 1.6 m dancer)
LIGHT_POWER = 450.0  # the warm flash of a strike, in watts per square model height
SPLAT_FROM = 1.1  # the paint flies from this far toward the camera (model heights)
TOKEN_GAP = 0.4  # seconds between two tokens (without beats; at least this with them)
TOKEN_RING = 0.55  # the tokens wait round her this far out (model heights) ...
TOKEN_UP = 0.62  # ... at this height
CHEST = ("上半身2", "上半身", "UpperBody2", "UpperBody", "upper body 2", "upper body", "Chest", "chest", "Spine2")
TOKEN_BONES = (CHEST, arrival.LIMB_BONES[1], arrival.LIMB_BONES[0], arrival.WAIST_BONES, arrival.LIMB_BONES[3],
               arrival.LIMB_BONES[2], arrival.KNEE_BONES[1], arrival.KNEE_BONES[0])  # chest, wrists, waist, ankles ...
TOKEN_FRONT = 0.3  # a token lands on the front of the part nearest its bone: looked for this far toward the camera


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_ORIGINS) == mask and (kind is None or ob.get(P_KIND) == kind)]


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


def record(mask):
    rec = mask.get(P_ORIGINS) if mask is not None else None
    return rec.to_dict() if rec is not None and hasattr(rec, "to_dict") else None


# --------------------------------------------------------------------------- build: the points and the arrival field

def _toward(scene, frame, middle):
    """The horizontal way from her to the camera of `frame` (unit), and the picture's right."""
    camera = sampling.camera_at(scene, frame)
    toward = camera.matrix_world.translation - middle if camera is not None else Vector((0.0, -1.0, 0.0))
    toward.z = 0.0
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    return toward, (-toward).cross(Vector((0.0, 0.0, 1.0)))


def _candidates(settings, meshes):
    """The outfit's vertices (of faces whose material is not locked) of each mesh: (mesh, vertex indices, rest world
    positions, rest world normals)."""
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    out = []
    for ob in meshes:
        me = ob.data
        locked = np.array([s.material is not None and any(fnmatch.fnmatchcase(mdl.material_key(s.material), p)
                                                           for p in patterns) for s in ob.material_slots] + [False])
        index = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("material_index", index)
        total = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_total", total)
        loops = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", loops)
        free = ~locked[np.minimum(index, len(locked) - 1)]
        keep = np.zeros(len(me.vertices), dtype=bool)
        keep[loops[np.repeat(free, total)]] = True
        picked = np.nonzero(keep)[0]
        if not len(picked):
            continue
        points = mdl.rest_points_world(ob)[picked]
        normals = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("normal", normals)
        turn = np.array(ob.matrix_world.to_3x3().inverted_safe().transposed(), dtype=np.float64)
        normals = normals.reshape(-1, 3)[picked].astype(np.float64) @ turn.T
        normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-9)[:, None]
        out.append((ob, picked, points, normals))
    return out


def _pick(cands, count, weights, spacing, rng):
    """`count` of the candidates, at random as `weights` say (one array per mesh), each at least `spacing` from the
    others while there is room: [(mesh, vertex index, rest world point, rest world normal)]."""
    obs = [c[0] for c in cands]
    which = np.concatenate([np.full(len(c[1]), k) for k, c in enumerate(cands)])
    index = np.concatenate([c[1] for c in cands])
    points = np.concatenate([c[2] for c in cands])
    normals = np.concatenate([c[3] for c in cands])
    weight = np.concatenate(weights).astype(np.float64)
    near = np.full(len(points), np.inf)
    out = []
    while len(out) < count:
        allowed = weight * (near >= spacing)
        if allowed.sum() <= 0.0:
            if spacing < 1e-6:
                break
            spacing *= 0.7
            continue
        k = int(rng.choice(len(points), p=allowed / allowed.sum()))
        out.append((obs[which[k]], int(index[k]), points[k], normals[k]))
        near = np.minimum(near, np.linalg.norm(points - points[k], axis=1))
    return out


def _nearest(cands, target):
    best = None
    for ob, picked, points, normals in cands:
        d = np.linalg.norm(points - np.asarray(target), axis=1)
        k = int(np.argmin(d))
        if best is None or d[k] < best[0]:
            best = (float(d[k]), (ob, int(picked[k]), points[k], normals[k]))
    return best[1] if best is not None else None


def _token_points(armature, cands, count, toward, height, rng):
    """The tokens land on the front of the chest, the wrists, the waist, the ankles and the knees in turn (the bones
    there are), then anywhere on her front."""
    out = []
    for names in TOKEN_BONES:
        if len(out) >= count:
            break
        place = motion.rest_head(armature, names)
        if place is None:
            continue
        found = _nearest(cands, np.asarray(place + toward * (TOKEN_FRONT * height)))
        if found is not None and all(found[1] != o[1] or found[0] != o[0] for o in out):
            out.append(found)
    if len(out) < count:
        weights = [np.maximum(c[3] @ np.asarray(toward), 0.0) ** 2 + 1e-3 for c in cands]
        more = _pick(cands, count, weights, SPACING * height, rng)
        out += [m for m in more if all(m[1] != o[1] or m[0] != o[0] for o in out)][:count - len(out)]
    return out


def _on_beats(first, count, gap, beat_frames):
    """`count` frames from `first` on, `gap` apart; with beats, the beats from `first` on that are at least `gap`
    apart (and `gap` on past the last beat)."""
    if not beat_frames:
        return [first + k * gap for k in range(count)]
    out = []
    for b in beat_frames:
        if b >= first - 0.5 and (not out or b - out[-1] >= gap - 0.5):
            out.append(b)
        if len(out) == count:
            return out
    while len(out) < count:
        out.append((out[-1] if out else first) + gap)
    return out


def arrival_field(context, settings, owner, meshes, height):
    """The path From Many Points: (arrival distances of `meshes` (one array each, world units, rest pose), the front's
    pace in world units a frame, the record of the points for the flights). The points are on the old outfit (the
    owner's meshes, not their locked parts)."""
    scene = context.scene
    fps = scene.render.fps / scene.render.fps_base
    start = float(settings.frame_start)
    span = float(max(settings.frame_end - settings.frame_start, 1))
    speed = TRAVEL * height / span
    style = settings.origins_style
    count = max(1, settings.origins_count)
    rng = np.random.default_rng(1013 + 7 * count + STYLES.index(style))
    lo, hi = mdl.rest_bounds(owner.meshes)
    middle = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))
    toward, side = _toward(scene, settings.frame_start, middle)
    cands = _candidates(settings, owner.meshes)
    if not cands:
        cands = _candidates(settings, meshes) or []
    if not cands:
        from .effect import EffectError

        raise EffectError("No outfit to start from (everything is locked)")
    beat_frames = beats.beat_frames() if settings.beat_sync else []
    look = LOOK[style]
    t = np.asarray(toward)
    groups = []
    if style == "TOKENS":
        picks = _token_points(owner.armature, cands, count, toward, height, rng)
        lands = _on_beats(start, len(picks), TOKEN_GAP * fps, beat_frames)
    elif style == "SPARKS":  # where sparks falling from above can land: on top of her, a little to the front
        weights = [np.maximum(c[3][:, 2], 0.0) ** 1.5 + 0.25 * np.maximum(c[3] @ t, 0.0) + 0.02 for c in cands]
        picks = _pick(cands, count, weights, SPACING * height, rng)
        strikes = _on_beats(start - look["flight"] * fps, int(math.ceil(len(picks) / float(STRIKE_LANDS))),
                            STRIKE_GAP * fps, beat_frames)
        lands, groups = [], []
        for k in range(len(picks)):
            j = k // STRIKE_LANDS
            lands.append(max(strikes[j] + (look["flight"] + STRIKE_SPREAD * (k % STRIKE_LANDS)) * fps, start))
            groups.append(j)
    else:  # paint thrown from the camera's side lands on the parts facing it
        weights = [np.maximum(c[3] @ t, 0.0) ** 2 + 0.01 for c in cands]
        picks = _pick(cands, count, weights, SPACING * height, rng)
        lands = sorted([start] + [start + float(rng.uniform(0.0, SPREAD * span)) for _ in range(len(picks) - 1)])
        if beat_frames:
            lands = [min((b for b in beat_frames if b >= start - 0.5), key=lambda b: abs(b - f), default=f)
                     for f in lands]
    order = sorted(range(len(picks)), key=lambda k: lands[k])  # (in the order they land)
    picks, lands = [picks[k] for k in order], [lands[k] for k in order]
    groups = [groups[k] for k in order] if groups else []
    delays = [speed * max(f - start, 0.0) for f in lands]
    point_sets = [mdl.rest_points_world(ob) for ob in meshes]
    values = arrival.surface_distances(point_sets, [arrival._triangles(ob) for ob in meshes],
                                       [tuple(p[2]) for p in picks], height, delays)
    # where each sets off from
    starts = []
    smith = middle - toward * (SMITH_BEHIND * height) + Vector((0.0, 0.0, SMITH_UP * height))
    ring = middle + Vector((0.0, 0.0, TOKEN_UP * height))
    for k, (_ob, _i, point, _normal) in enumerate(picks):
        p = Vector(tuple(point))
        if style == "SPARKS":
            starts.append(smith)
        elif style == "SPLATS":
            starts.append(p + toward * (SPLAT_FROM * height) + side * (float(rng.uniform(-0.35, 0.35)) * height)
                          + Vector((0.0, 0.0, float(rng.uniform(0.0, 0.3)) * height)))
        else:
            way = p - ring
            way.z = 0.0
            way = way.normalized() if way.length > 1e-6 else (side if k % 2 else -side)
            starts.append(ring + (way + toward * 0.5).normalized() * (TOKEN_RING * height))
    rec = {
        "style": style, "height": height, "speed": speed,
        "mesh": [p[0].name for p in picks], "index": [p[1] for p in picks],
        "rest": [float(v) for p in picks for v in p[0].data.vertices[p[1]].co],
        "world": [float(v) for p in picks for v in p[2]],
        "from": [float(v) for s in starts for v in s],
        "delay": delays, "group": groups, "smith": list(smith),
    }
    return values, speed, rec


# --------------------------------------------------------------------------- sync: what flies

def _points(name, collection, mask, kind):
    ob = next(iter(objects(mask, kind)), None)
    if ob is None:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        collection.objects.link(ob)
        ob[P_ORIGINS] = mask
        ob[P_KIND] = kind
        ob.hide_select = True
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False
    return ob


def _fill(ob, positions, attrs):
    """Our points at `positions` with the attributes `attrs` (name: list of floats or of 3-tuples)."""
    me = ob.data
    me.clear_geometry()
    me.from_pydata([tuple(p) for p in positions], [], [])
    for name, values in attrs.items():
        vector = bool(values) and isinstance(values[0], (tuple, list, Vector))
        attr = me.attributes.get(name)
        if attr is not None and attr.data_type != ("FLOAT_VECTOR" if vector else "FLOAT"):
            me.attributes.remove(attr)
            attr = None
        attr = attr or me.attributes.new(name, "FLOAT_VECTOR" if vector else "FLOAT", "POINT")
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


def _light(mask, collection, smith, strikes, height):
    """The warm flash of each strike, behind her where the iron is struck."""
    from .cover import _clear_keys
    from .pyro import _key

    light = next(iter(objects(mask, "LIGHT")), None)
    if light is None:
        light = bpy.data.objects.new(NAME + " Light", bpy.data.lights.new(NAME + " Light", "POINT"))
        collection.objects.link(light)
        light[P_ORIGINS] = mask
        light[P_KIND] = "LIGHT"
        light.hide_select = True
    _clear_keys(light.data)
    light.data.color = (1.0, 0.6, 0.25)
    light.data.shadow_soft_size = 0.2 * height
    light.location = Vector(smith) + Vector((0.0, 0.0, 0.35 * height))
    peak = LIGHT_POWER * height * height
    keys = [(strikes[0] - 2.0, 0.0)]
    for f in strikes:
        keys += [(f - 1.0, 0.0), (f, peak), (f + 6.0, 0.25 * peak), (f + 14.0, 0.0)]
    _key(light.data, "energy", keys)


def sync(settings, mask, models, frame_at):
    """What flies onto her as the record of the build says (the path From Many Points), landing when the mask's front
    sets off there (`frame_at(radius)`); nothing for any other path or with Suit Down."""
    from . import cover_nodes

    rec = record(mask)
    if rec is None or mask.get("mmd_disperse_path") != "ORIGINS" or settings.direction != "GROW":
        if mask is not None:
            remove(mask)
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    style = rec["style"]
    look = LOOK[style]
    height = float(rec["height"])
    lands = [frame_at(d) for d in rec["delay"]]
    lands = [float(f) if f is not None else float(settings.frame_start) for f in lands]
    end = max([float(settings.frame_end)] + lands)
    n = len(lands)
    rest = [tuple(rec["rest"][3 * k:3 * k + 3]) for k in range(n)]
    world = [tuple(rec["world"][3 * k:3 * k + 3]) for k in range(n)]
    starts = [tuple(rec["from"][3 * k:3 * k + 3]) for k in range(n)]
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    flight = look["flight"] * fps
    stay = [(look["stay"] * fps) if look["stay"] is not None else max(end - f + 0.3 * fps, look["pop"] * fps + 1.0)
            for f in lands]
    if style == "TOKENS" and settings.origins_object is not None and settings.origins_object.type == "MESH":
        shape, own = settings.origins_object, True
    else:
        shape = {"SPARKS": cover_nodes.ensure_spark_object, "SPLATS": cover_nodes.ensure_splat_object,
                 "TOKENS": cover_nodes.ensure_token_object}[style](scene)
        own = False
    material = materials.ensure_cover_material({"SPARKS": "SPARK", "SPLATS": "SPLAT", "TOKENS": "TOKEN"}[style])
    keep = set()
    for k, mesh_name in enumerate(sorted(set(rec["mesh"]))):
        dancer = bpy.data.objects.get(mesh_name)
        mine = [i for i in range(n) if rec["mesh"][i] == mesh_name]
        if dancer is None or not mine:
            continue
        ob = _points("%s %s" % (NAME, k), collection, mask, "FLIGHTS_%d" % k)
        keep.add(ob.name)
        ob["mmdd_color"] = tuple(settings.origins_color)
        _fill(ob, [world[i] for i in mine], {
            "mmdd_t0": [lands[i] - flight for i in mine], "mmdd_t1": [lands[i] for i in mine],
            "mmdd_from": [starts[i] for i in mine], "mmdd_rest": [rest[i] for i in mine],
            "mmdd_stay": [stay[i] for i in mine]})
        _modifier(ob, cover_nodes.ensure_origins_group(), {
            "Dancer": dancer, "Shape": shape, "Size": look["size"] * height, "Arc": look["arc"] * height,
            "Appear": look["appear"] * fps, "Pop": look["pop"] * fps, "Burst": look["burst"],
            "With Material": not own, "Material": material})
    for ob in objects(mask):
        if ob.get(P_KIND, "").startswith("FLIGHTS") and ob.name not in keep:
            _delete(ob)
    if style != "SPARKS":
        for ob in objects(mask, "FOUNTAIN") + objects(mask, "LIGHT"):
            _delete(ob)
        return
    # the fountain of each strike, and its flash of light
    groups = rec.get("group") or [k // STRIKE_LANDS for k in range(n)]
    strikes = sorted({min(lands[i] for i in range(n) if groups[i] == g) - flight for g in set(groups)})
    smith = Vector(rec["smith"])
    rng = np.random.default_rng(29)
    positions, t0, vel, axis, r = [], [], [], [], []
    for f in strikes:
        for _k in range(FOUNTAIN):
            a = float(rng.uniform(0.0, 2.0 * math.pi))
            out = float(rng.uniform(0.0, FOUNTAIN_SIDE))
            up = float(rng.uniform(*FOUNTAIN_UP))
            positions.append(tuple(smith))
            t0.append(f + float(rng.uniform(0.0, 3.0)))
            vel.append((out * math.cos(a) * height / fps, out * math.sin(a) * height / fps, up * height / fps))
            axis.append(tuple(rng.normal(size=3)))
            r.append(float(rng.uniform()))
    fountain = _points(NAME + " Fountain", collection, mask, "FOUNTAIN")
    _fill(fountain, positions, {"mmdd_t0": t0, "mmdd_v": vel, "mmdd_axis": axis, "mmdd_r": r})
    _modifier(fountain, cover_nodes.ensure_pieces_group(), {
        "Instance": cover_nodes.ensure_spark_object(scene), "Size": 0.03 * height,
        "Gravity": (0.0, 0.0, -GRAVITY * height / (fps * fps)), "Drag": 0.02, "Flutter": 0.0, "Spin": 0.05,
        "Life": FOUNTAIN_LIFE * fps, "Material": materials.ensure_cover_material("SPARK")})
    _light(mask, collection, smith, strikes, height)
