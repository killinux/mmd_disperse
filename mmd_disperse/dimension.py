"""The dimension switch (次元切换, 1.14, after the virtual idol naevis' "Done"): the dancer goes from the MMD look
(toon, the materials as they are) to a realistic one: each material's own texture under a Principled BSDF set for what
it is (skin scattering light under its surface, glossy hair, latex and metal, cloth with a sheen;
materials.add_real), with a camera's grain and vignette over the picture (Film Look: a sheet of ours in front of the
camera) and studio lights coming up with it (Studio Lights):

* FRONT (along the front): the new outfit comes in realistic and the old one stays toon until it goes; the head and
  the hair (locked to the old model) turn realistic as the front passes them;
* BEATS (on the beats): the whole of her flips between the two looks on every beat (every Flip seconds without beat
  sync) in the Dimension Time before the big moment, and stays realistic from then on.

Reverse goes the other way, from realistic to toon. The timing is in drivers on the frame (short simple expressions,
which Blender runs without Python) on a value in each material, the film sheet and the lights. Removing the effect
takes it all away."""

import fnmatch
import math
import re

import bpy
import numpy as np
from mathutils import Vector

from . import beats, materials, shots
from . import model as mdl

STYLES = ("NONE", "FRONT", "BEATS")
P_DIM = "mmd_disperse_dimension"  # on our objects (the film sheet, the lights): the mask of their effect ...
P_KIND = "mmd_disperse_dimension_kind"  # ... FILM, KEY, RIM_LEFT, RIM_RIGHT
NAME = "MMD Disperse Dimension"
FILM = "mmdd_film"  # on the film sheet: how much of the film look shows (driven)
FLIP = 0.4  # seconds between two flips without beats
MOST_FLIPS = 13  # (a driver expression is at most 255 characters long)
SWITCH = 4.0  # frames a part of her takes to turn as the front passes it
SCATTER = 0.006  # how far light scatters under the skin (model heights): about a centimetre
# the studio lights: sun lights at (degrees round from the way to the camera, degrees down), their strength
LIGHTS = (("KEY", -35.0, 50.0, 3.0, (1.0, 0.96, 0.92)), ("RIM_LEFT", -150.0, 20.0, 3.5, (0.55, 0.8, 1.0)),
          ("RIM_RIGHT", 150.0, 20.0, 2.5, (0.75, 0.82, 1.0)))
# what a material is, from its name (English, Japanese): the first that matches
KINDS = (
    ("lash", re.compile(r"lash|brow|眉|まつ|睫")),
    ("eye", re.compile(r"eye|iris|pupil|目|瞳|ハイライト")),
    ("mouth", re.compile(r"mouth|teeth|tooth|tongue|口|歯|舌")),
    ("hair", re.compile(r"hair|髪|bang|ponytail|もみあげ")),
    ("metal", re.compile(r"metal|金属|buckle|chain|zipper|silver|銀|金具")),
    ("leather", re.compile(r"leather|latex|vinyl|rubber|革|レザー|ラテックス|エナメル")),
    ("skin", re.compile(r"skin|exposed|(?<![a-z])body(?!suit)|face|head|neck|肌|顔|首|体|手(?!袋)|腕|脚|足|tifa|"
                        r"gens")),
)


def kind_of(mat):
    name = mat.name.lower()
    for kind, pattern in KINDS:
        if pattern.search(name):
            return kind
    return "cloth"


def objects(mask, kind=None):
    return [ob for ob in bpy.data.objects if ob.get(P_DIM) == mask and (kind is None or ob.get(P_KIND) == kind)]


def _delete(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def _materials(ob):
    return [slot.material for slot in ob.material_slots
            if slot.material is not None and slot.material.name != materials.WIRE_MATERIAL]


def remove(mask, meshes=()):
    """Our sheet and lights, and with `meshes` the realistic look in their materials."""
    for ob in objects(mask):
        _delete(ob)
    for ob in meshes:
        for mat in _materials(ob):
            materials.remove_real(mat)


def _num(value):
    return ("%.1f" % value).rstrip("0").rstrip(".")


def _flips(start, moment, beat_frames, fps):
    """The frames she flips at: on the beats (every FLIP seconds without them) from `start` until the big moment,
    an odd number of them (she ends realistic), the last at the moment."""
    if len(beat_frames) > 1:
        edges = [float(b) for b in beat_frames if start <= b < moment - 0.5]
    else:
        step = max(FLIP * fps, 2.0)
        edges = [start + k * step for k in range(int((moment - start) / step) + 1) if start + k * step < moment - 0.5]
    edges = edges[-(MOST_FLIPS - 1):] if len(edges) >= MOST_FLIPS else edges
    if len(edges) % 2 == 0:
        edges.append(float(moment))
    return edges


def _toggle(edges):
    """Driver expression on the frame: 0 before the first edge, then 1, 0, 1 ... at each one."""
    terms = "".join(("-" if k % 2 else "+") + "(frame>=%s)" % _num(e) for k, e in enumerate(edges))
    return "(%s)" % terms.lstrip("+") if terms else "1"


def _step(frame):
    """Driver expression on the frame: 0 before `frame`, 1 from SWITCH frames after it, smooth in between."""
    return "smoothstep(%s,%s,frame)" % (_num(frame), _num(frame + SWITCH))


def _flip(expression, reverse):
    if not reverse:
        return expression
    if expression in ("0", "1"):
        return "1" if expression == "0" else "0"
    return "1-" + expression


def _locked(settings, mat):
    patterns = mdl.split_patterns(settings.lock_patterns) if settings.use_lock else []
    return any(fnmatch.fnmatchcase(mdl.material_key(mat), p) for p in patterns)


def _passing(ob, mat, mask, frame_at):
    """The frame the front gets to the part of `ob` in `mat` (the middle of its arrival distances, or of its distances
    from the mask on the sphere path); None when it never does."""
    from .node_groups import ATTR_ARRIVAL

    me = ob.data
    index = next((i for i, slot in enumerate(ob.material_slots) if slot.material == mat), None)
    if index is None or not len(me.polygons):
        return None
    slots = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("material_index", slots)
    total = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_total", total)
    loops = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loops)
    picked = np.unique(loops[np.repeat(slots == index, total)])
    if not len(picked):
        return None
    attr = me.attributes.get(ATTR_ARRIVAL)
    if attr is not None and attr.domain == "POINT":
        values = np.empty(len(me.vertices), dtype=np.float32)
        attr.data.foreach_get("value", values)
        scale = ob.matrix_world.to_scale()
        distance = float(np.median(values[picked])) * (abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3.0
    else:
        points = mdl.rest_points_world(ob)[picked]
        distance = float(np.median(np.linalg.norm(points - np.asarray(mask.matrix_world.translation), axis=1)))
    return frame_at(distance)


def _sheet(scene, mask, camera, collection):
    """The film sheet just in front of `camera`, a little larger than its picture, its UVs 0 .. 1 across it."""
    from .picture import _frame, _near

    depth = 0.96 * _near(camera)  # (in front of the tape and the picture fronts)
    key = "%s:%d:%d:%.4f" % (camera.name, scene.render.resolution_x, scene.render.resolution_y, depth)
    ob = next(iter(objects(mask, "FILM")), None)
    if ob is not None and (ob.parent != camera or ob.get("mmdd_key") != key):
        _delete(ob)
        ob = None
    if ob is not None:
        return ob
    centre, width, height = _frame(scene, camera, depth)
    half_w, half_h = 0.5 * width * materials.FRONT_SHEET, 0.5 * height * materials.FRONT_SHEET
    corners = [centre + Vector((sx * half_w, sy * half_h, 0.0)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = bpy.data.meshes.new(NAME + " Film")
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        uv.data[loop.index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[loop.vertex_index]
    me.materials.append(materials.ensure_film_material())
    ob = bpy.data.objects.new(NAME + " Film", me)
    collection.objects.link(ob)
    ob.parent = camera
    ob.hide_select = True
    if hasattr(ob, "visible_shadow"):
        ob.visible_shadow = False
    ob[P_DIM] = mask
    ob[P_KIND] = "FILM"
    ob["mmdd_key"] = key
    return ob


def _drive(owner, path, expression, index=-1):
    owner.driver_remove(path, index) if index >= 0 else owner.driver_remove(path)
    driver = (owner.driver_add(path, index) if index >= 0 else owner.driver_add(path)).driver
    driver.type = "SCRIPTED"
    driver.expression = expression


def _film(settings, mask, scene, collection, real):
    from .finish import sampling_aspect

    camera = shots.carrier(scene, mask)
    film = next(iter(objects(mask, "FILM")), None)
    if not settings.dim_film or camera is None or camera.type != "CAMERA":
        if film is not None:
            _delete(film)
        return
    film = _sheet(scene, mask, camera, collection)
    film[materials.FRONT_ASPECT] = sampling_aspect(scene)
    film[materials.FRONT_TICK] = 0.0
    film[FILM] = 0.0
    _drive(film, '["%s"]' % materials.FRONT_TICK, "frame")
    _drive(film, '["%s"]' % FILM, real)


def _lights(settings, mask, scene, collection, real, middle, height):
    """The studio lights: sun lights from the camera's side and behind her, as bright as the realistic look is."""
    ours = {ob.get(P_KIND): ob for ob in objects(mask) if ob.get(P_KIND) in {k for k, *_r in LIGHTS}}
    if not settings.dim_lights:
        for ob in ours.values():
            _delete(ob)
        return
    camera = shots.carrier(scene, mask)
    toward = camera.matrix_world.translation - middle if camera is not None else Vector((0.0, -1.0, 0.0))
    toward.z = 0.0
    toward = toward.normalized() if toward.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    base = math.atan2(toward.y, toward.x)
    for kind, round_, down, power, color in LIGHTS:
        light = ours.get(kind)
        if light is None:
            light = bpy.data.objects.new("%s %s" % (NAME, kind.title()), bpy.data.lights.new(NAME, "SUN"))
            collection.objects.link(light)
            light[P_DIM] = mask
            light[P_KIND] = kind
            light.hide_select = True
        light.data.color = color
        light.data.angle = math.radians(5.0)
        way = base + math.radians(round_)
        # the light comes from (way, down): it shines the other way
        source = Vector((math.cos(way) * math.cos(math.radians(down)), math.sin(way) * math.cos(math.radians(down)),
                         math.sin(math.radians(down))))
        light.rotation_euler = (-source).to_track_quat("-Z", "Y").to_euler()
        light.location = middle + source * (2.0 * height)
        _drive(light.data, "energy", "%s*(%s)" % (_num(power), real))


def sync(settings, mask, models, moment, frame_at):
    """The dimension switch as the panel says, the big moment at frame `moment`: the realistic look in the materials of
    both outfits driven on the frame, the film sheet and the lights; all taken away without it."""
    style = getattr(settings, "dim_style", "NONE")
    base = mdl.resolve(settings.base) if settings.base else None
    target = mdl.resolve(settings.target) if settings.target else None
    meshes = [(ob, "BASE") for ob in (base.meshes if base else ())] + \
             [(ob, "TARGET") for ob in (target.meshes if target else ())]
    if style == "NONE" or moment is None or not meshes or mask is None:
        if mask is not None:
            remove(mask, [ob for ob, _role in meshes])
        return
    scene = settings.id_data
    fps = scene.render.fps / scene.render.fps_base
    lo, hi = mdl.rest_bounds([ob for ob, _role in meshes])
    height = max(hi.z - lo.z, 1e-3)
    moment = float(moment)
    reverse = settings.dim_reverse
    if style == "BEATS":
        start = max(moment - max(settings.dim_length, 0.2) * fps, float(scene.frame_start))
        beat_frames = beats.beat_frames() if settings.beat_sync else []
        everyone = _flip(_toggle(_flips(start, moment, beat_frames, fps)), reverse)
        real = everyone
    else:
        everyone = None
        real = _flip("smoothstep(%s,%s,frame)" % (_num(float(settings.frame_start)), _num(max(
            moment, settings.frame_start + 1.0))), reverse)
    for ob, role in meshes:
        scale = ob.matrix_world.to_scale()
        unit = SCATTER * height / max((abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3.0, 1e-9)
        for mat in _materials(ob):
            if everyone is not None:
                expression = everyone
            elif role == "TARGET":
                expression = _flip("1", reverse)
            elif not _locked(settings, mat):
                expression = _flip("0", reverse)
            else:
                at = _passing(ob, mat, mask, frame_at)
                expression = _flip(_step(at) if at is not None else "0", reverse)
            materials.add_real(mat, kind_of(mat), unit)
            materials.update_real(mat, expression)
    collection = mask.users_collection[0] if mask.users_collection else scene.collection
    middle = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z + 0.55 * height))
    _film(settings, mask, scene, collection, real)
    _lights(settings, mask, scene, collection, real, middle, height)
