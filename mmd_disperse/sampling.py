"""Build-time sampling of the dance (逐帧采样).

While the effect is built, the frames of the transformation play once (the bones only, see motion.play) and every
frame each vertex of both outfits, where the skinning puts it then, is asked one question: has it been touched yet? The
first time it was (to a fraction of a frame) is when the change comes to it: its arrival distance is how far the mask
has grown by then, and the mask grows at an even pace (P_SPEED), so any frame can still be scrubbed to. The parts never
touched take their turn after the nearest parts that were, along the body (arrival.surface_fill).

A question is called `question(i, frame, positions)` with the skinned world positions of each mesh and returns, per
mesh, when within the last frame each vertex was touched (np.inf where it was not):

* HandSweep: a dancing hand came over it (1.10, the hand path);
* PictureFront: a front on the picture came over it as the scene camera sees it (1.12, the picture path): a wipe
  across the picture, an iris opening from the dancer, a folding fan opening, three strokes of a big brush, a hole
  burning through the film, all growing at an even pace over the transformation; a clock's hand ticking round her; the
  white fish of a taiji turning and growing over her; or the dancing hands smearing paint across the picture;
* Spotlight: a follow spot found it (1.12); Spray: a spray from the palms coated it; Moving: it moved enough.
"""

import math

import bpy
import numpy as np

from . import motion, shots
from .model import ORIGIN_BONES

SHAPES = ("WIPE", "IRIS", "FAN", "BRUSH", "BURN", "SMEAR", "CLOCK", "TAIJI")
CENTRED = ("IRIS", "BURN", "CLOCK", "TAIJI")  # fronts round the dancer's chest (or the middle of the picture)
MARGIN = 0.02  # the fronts start (and end) this far outside the dancer, a share of the picture's height ...
SPAN_MARGIN = 0.06  # ... and this share of her size, so their glow comes in
STROKES = 3  # the big brush paints this many strokes, from the top of the picture down, each the other way ...
STROKE_WAVE = (0.04, 7.0, 1.7)  # ... with wavy edges between them: (height, a share of the strokes', waves across the
# picture, phase a stroke)
FAN_PIVOT = -0.56  # the fan opens about a point just under the middle of the picture's bottom edge
# the edge of the hole burning through the film: (how far it reaches in and out, waves round it, phase) ...
BURN_WOBBLE = ((0.09, 3.0, 1.3), (0.08, 5.0, 4.1), (0.06, 8.0, 2.2), (0.04, 13.0, 0.7), (0.03, 21.0, 5.3))
BURN_SPAN = 1.0 / (1.0 - sum(w[0] for w in BURN_WOBBLE))  # ... so its deepest bays have passed the corners at the end
HAND_STEPS = 3  # a hand's way from one frame to the next is checked in this many steps (a fast hand leaves no gaps)
CLOCK_TICKS = 12  # the clock's hand jumps round in this many ticks ...
CLOCK_BOUNCE = 0.3  # ... overshooting by this share of a tick ...
CLOCK_SETTLE = 0.3  # ... and settling back over this share of the time to the next; its face is drawn this share
CLOCK_FACE = 0.62  # of the way to her furthest point
TAIJI_GROW = 0.55  # the taiji grows to its full size over this share of the transformation ...
TAIJI_TURNS = 1.25  # ... turning this many times round over all of it
TAIJI_EYE = 0.125  # the fishes' eyes: this share of its radius
SPOT_FIND = 0.3  # share of the transformation the follow spot takes to slide onto the dancer ...
SPOT_SIDE = 0.9  # ... from this far to her side (model heights) ...
SPOT_START = 0.25  # ... its beam this wide where it falls (model heights), opening up to ...
SPOT_END = 0.95  # ... this wide by the end
SPRAY_ANGLE = math.radians(20.0)  # the spray's cone (half its angle) ...
SPRAY_RATE = 0.35  # ... and how much of a coat a frame gives right in front of the nozzle; it sprays at the body
SPRAY_FINGERS = 0.3  # ... (the nearest point of the line from a little under the hips to the neck), this much along
# the fingers
SPRAY_LOW = 0.25  # (that line starts this many model heights under the hips)


# --------------------------------------------------------------------------- the frames played once

def touch_frames(scene, armature, meshes, frames, question, hidden=()):
    """For every vertex of `meshes`: the frame (fractional) at which `question` first found it touched while `frames`
    played, np.inf if never. Only the skinning counts: the modifiers after the armature (an outline's shell, a mask)
    are off meanwhile, and a mesh whose posed vertices still do not line up with its own is left out."""
    first = [np.full(len(ob.data.vertices), np.inf) for ob in meshes]
    paused = []
    for ob in meshes:
        mods = list(ob.modifiers)
        after = max((i for i, m in enumerate(mods) if m.type == "ARMATURE"), default=-1)
        paused += [m for m in mods[after + 1:] if m.show_viewport]

    def visit(i, frame, positions):
        ok = [len(pts) == len(out) for pts, out in zip(positions, first)]
        whens = question(i, frame, [pts if good else np.zeros((0, 3)) for pts, good in zip(positions, ok)])
        for out, when, good in zip(first, whens, ok):
            if good and when is not None and len(when) == len(out):
                np.minimum(out, when, out=out)

    for m in paused:
        m.show_viewport = False
    try:
        motion.play(scene, armature, frames, hidden, meshes, visit)
    finally:
        for m in paused:
            m.show_viewport = True
    return first


def arrival(scene, armature, meshes, start, end, question, height, fallback):
    """Arrival distances (one array per mesh, world units) and the front's pace (world units a frame) from what
    `question` finds while the transformation plays from `start` to `end`: a body height of the front for the whole of
    it, the parts never touched in turn from the nearest that were, along the body. With nothing touched at all the
    change flows over the body from the `fallback` points (world)."""
    from . import arrival as arr
    from .model import rest_points_world

    end = max(end, start + 1)
    speed = height / float(end - start)
    touches = touch_frames(scene, armature, meshes, range(start, end + 1), question)
    # (by when nearly all that was ever touched had been: the paint smear stops there)
    found = np.concatenate([t[np.isfinite(t)] for t in touches]) if touches else np.zeros(0)
    question.touched_until = float(np.percentile(found, 98)) if len(found) else float(end)
    known = [np.where(np.isfinite(t), (t - start) * speed, np.inf) for t in touches]
    points = [rest_points_world(ob) for ob in meshes]
    tris = [arr._triangles(ob) for ob in meshes]
    if any(np.isfinite(k).any() for k in known):
        return arr.surface_fill(points, tris, known, height), speed
    return arr.surface_distances(points, tris, fallback, height), speed


# --------------------------------------------------------------------------- the hands

class HandSweep:
    """Did one of the hands (`sides`: "L", "R") come within `reach` of the vertex? A hand is a capsule from the wrist
    to the fingertips; its way from one frame to the next is checked in HAND_STEPS steps."""

    def __init__(self, armature, sides, reach):
        self.armature, self.sides, self.reach = armature, tuple(sides), reach
        self.last = {}

    def __call__(self, i, frame, positions):
        out = [np.full(len(p), np.inf) for p in positions]
        hands = {}
        mw = self.armature.matrix_world
        for side in self.sides:
            wrist, finger = motion._hand(self.armature, side)
            if wrist is None:
                continue
            w = np.array(mw @ wrist.head)
            f = np.array(mw @ finger.head) if finger is not None else np.array(mw @ wrist.tail)
            hands[side] = (w, w + 2.0 * (f - w))
        for side, (a1, b1) in hands.items():
            a0, b0 = self.last.get(side, (a1, b1))
            for s in range(1, HAND_STEPS + 1):
                t = s / float(HAND_STEPS) if side in self.last else 1.0
                a, b = a0 + (a1 - a0) * t, b0 + (b1 - b0) * t
                ab = b - a
                length2 = max(float(ab @ ab), 1e-12)
                when = frame - 1.0 + t if side in self.last else frame
                for pts, o in zip(positions, out):
                    if not len(pts):
                        continue
                    v = pts - a
                    u = np.clip(v @ ab / length2, 0.0, 1.0)
                    near = np.linalg.norm(v - u[:, None] * ab, axis=1) < self.reach
                    o[near & (when < o)] = when
        self.last.update(hands)
        return out


# --------------------------------------------------------------------------- the picture

def picture_aspect(scene):
    """The picture's width over its height (the render's shape)."""
    r = scene.render
    return (r.resolution_x * r.pixel_aspect_x) / max(r.resolution_y * r.pixel_aspect_y, 1e-9)


def camera_at(scene, frame):
    """The camera that shows frame `frame`: the one the scene's own markers pick then, else the scene camera."""
    cam = shots._camera_at(scene, frame) or scene.camera
    return cam if cam is not None and cam.type == "CAMERA" else None


def project(scene, camera, points):
    """(X, Y, ok) of world `points` on `camera`'s picture: X across it (its width is the aspect), Y up it (its height
    is 1), both 0 in its middle; ok is False behind the camera."""
    r = scene.render
    deps = bpy.context.evaluated_depsgraph_get()
    proj = np.array(camera.calc_matrix_camera(deps, x=r.resolution_x, y=r.resolution_y, scale_x=r.pixel_aspect_x,
                                              scale_y=r.pixel_aspect_y), dtype=np.float64)
    m = proj @ np.array(camera.matrix_world.inverted(), dtype=np.float64)
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    clip = pts @ m[:3, :3].T + m[:3, 3]
    w = pts @ m[3, :3] + m[3, 3]
    ok = w > 1e-6
    safe = np.where(ok, w, 1.0)
    aspect = picture_aspect(scene)
    return 0.5 * clip[:, 0] / safe * aspect, 0.5 * clip[:, 1] / safe, ok


def clock_progress(p):
    """How far round the clock's hand is (0 .. 1) at progress `p` (numbers or a numpy array): CLOCK_TICKS jumps, each
    overshooting and settling back (materials draws the same)."""
    p = np.clip(np.asarray(p, dtype=np.float64), 0.0, 1.0)
    k = np.minimum(np.floor(p * CLOCK_TICKS + 1e-6), CLOCK_TICKS)
    u = p * CLOCK_TICKS - k
    bounce = CLOCK_BOUNCE * np.maximum(1.0 - u / CLOCK_SETTLE, 0.0) * (k > 0) * (k < CLOCK_TICKS)
    return np.clip((k + bounce) / CLOCK_TICKS, 0.0, 1.0)


def taiji_distance(x, y, p, centre, span):
    """How far the picture points (x, y) are outside the taiji's white fish at progress `p` (< 0 inside), in picture
    units: the taiji round `centre` grows to its full radius (span[0]) over TAIJI_GROW and turns TAIJI_TURNS times
    over the transformation; the white fish is the big circle's right half (as it has turned) with the upper small
    circle and without the lower one, a black eye in its head and a white eye in the black fish's head."""
    radius = max(float(span[0]) * min(max(p, 0.0) / TAIJI_GROW, 1.0), 1e-6)
    turn = 2.0 * math.pi * TAIJI_TURNS * p
    dx, dy = np.asarray(x, dtype=np.float64) - centre[0], np.asarray(y, dtype=np.float64) - centre[1]
    c, s = math.cos(turn), math.sin(turn)
    u, v = (dx * c + dy * s) / radius, (-dx * s + dy * c) / radius  # in the taiji's own turn, its radius 1
    r = np.hypot(u, v)
    up, down = np.hypot(u, v - 0.5), np.hypot(u, v + 0.5)
    d = np.maximum(r - 1.0, -u)  # the right half
    d = np.maximum(d, 0.5 - down)  # without the lower small circle
    d = np.minimum(d, up - 0.5)  # with the upper one
    d = np.maximum(d, TAIJI_EYE - up)  # the black eye
    d = np.minimum(d, down - TAIJI_EYE)  # the white eye
    return d * radius


def front_span(shape, x, y, aspect, angle=0.0, centre=(0.0, 0.0)):
    """Where the front `shape` runs on the picture, fitted to the dancer there at its start (her points `x`, `y`), so
    it takes the whole transformation to cross her: four numbers, by shape
    * WIPE: the line's first and last place along its direction (and 0, 0);
    * IRIS, BURN, CLOCK, TAIJI: how far out from `centre` it grows (and 0, 0, 0);
    * FAN: the fan's first and last angle about its pivot (and 0, 0);
    * BRUSH: the strokes' left, right, top and bottom."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if not len(x):  # (nothing on the picture: the whole of it)
        x = np.array((-0.5 * aspect, 0.5 * aspect, -0.5 * aspect, 0.5 * aspect))
        y = np.array((-0.5, -0.5, 0.5, 0.5))
    if shape == "WIPE":
        d = x * math.cos(angle) + y * math.sin(angle)
        lo, hi = float(d.min()), float(d.max())
        m = SPAN_MARGIN * (hi - lo) + MARGIN
        return (lo - m, hi + m, 0.0, 0.0)
    if shape in CENTRED:
        r = np.hypot(x - centre[0], y - centre[1])
        return (float(r.max()) * (1.0 + SPAN_MARGIN) + MARGIN, 0.0, 0.0, 0.0)
    if shape == "FAN":
        phi = np.arctan2(y - FAN_PIVOT, x if math.cos(angle) >= 0.0 else -x)
        phi = np.clip(phi, 0.0, math.pi)
        lo, hi = float(phi.min()), float(phi.max())
        m = SPAN_MARGIN * (hi - lo) + 0.05
        return (min(hi + m, math.pi), max(lo - m, 0.0), 0.0, 0.0)
    if shape == "BRUSH":
        mx = SPAN_MARGIN * float(x.max() - x.min()) + MARGIN
        my = SPAN_MARGIN * float(y.max() - y.min()) + MARGIN
        return (float(x.min()) - mx, float(x.max()) + mx, float(y.max()) + my, float(y.min()) - my)
    raise ValueError(shape)


def time_field(shape, x, y, angle, centre, span):
    """At what progress (0 at the start .. 1 at the end) the front `shape` reaches each picture point (x, y), as numpy
    arrays (materials.ensure_picture_material draws the same), within its `span` (front_span):
    * WIPE: a straight line moving the way `angle` points (0: to the right);
    * IRIS: a circle growing from `centre`;
    * FAN: a folding fan opening about a point under the middle of the picture's bottom edge, from the left to the
      right (from the right with `angle` pointing left);
    * BRUSH: STROKES strokes of a big brush from the top down, the first to the right (left with `angle` pointing
      left), each the other way;
    * BURN: a hole with a ragged edge burning out from `centre`;
    * CLOCK: a clock's hand going round `centre` from twelve o'clock (reached when clock_progress has passed it).
    (The taiji has no such field: taiji_distance says where it is.)"""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    s0, s1, s2, s3 = span
    if shape == "CLOCK":
        theta = np.arctan2(x - centre[0], y - centre[1])  # clockwise from straight up
        return np.where(theta >= 0.0, theta, theta + 2.0 * math.pi) / (2.0 * math.pi)
    if shape == "WIPE":
        return (x * math.cos(angle) + y * math.sin(angle) - s0) / max(s1 - s0, 1e-6)
    if shape in ("IRIS", "BURN"):
        dx, dy = x - centre[0], y - centre[1]
        r = np.sqrt(dx * dx + dy * dy) / max(s0, 1e-6)
        if shape == "IRIS":
            return r
        theta = np.arctan2(dy, dx)
        wobble = 1.0 + sum(a * np.sin(n * theta + phase) for a, n, phase in BURN_WOBBLE)
        return r / (BURN_SPAN * wobble)
    rightwards = math.cos(angle) >= 0.0
    if shape == "FAN":
        phi = np.arctan2(y - FAN_PIVOT, x if rightwards else -x)
        phi = np.where(phi >= 0.0, phi, np.where(phi < -0.5 * math.pi, math.pi, 0.0))
        return (s0 - phi) / max(s0 - s1, 1e-6)
    if shape == "BRUSH":
        height, waves, phase = STROKE_WAVE
        row = np.zeros_like(x)
        tall = s2 - s3
        for j in range(1, STROKES):
            row += y < s2 - tall * j / float(STROKES) + height * tall * np.sin(waves * x + phase * j)
        along = (x - s0) / max(s1 - s0, 1e-6)
        along = np.where((row % 2 == 0) == rightwards, along, 1.0 - along)
        return (row + along) / float(STROKES)
    raise ValueError(shape)


def chest(armature):
    """World position of the middle of the chest: between the upper body and the neck (None without the bones)."""
    body = motion.find_bone(armature, ORIGIN_BONES)
    if body is None:
        return None
    neck = motion.find_bone(armature, motion.NECK)
    mw = armature.matrix_world
    top = neck.head if neck is not None else body.tail
    return np.array(mw @ ((body.head + top) * 0.5))


class PictureFront:
    """Has the front on the picture come over the vertex, as the camera of each frame sees it? The front grows at an
    even pace from frame `start` to `end` (time_field); the iris and the burn open from the dancer's chest as it moves
    (`follow`) or from the middle of the picture. SMEAR is the dancing hands (`sides`) smearing paint across the
    picture, a brush `brush` high (a share of the picture's height) round each.

    What was seen is kept for the sheet in front of the camera that draws the front (picture.py): the camera of the
    first frame, the centres of the iris or the burn per frame and the hands' way over the picture."""

    def __init__(self, scene, shape, start, end, armature=None, angle=0.0, follow=True, sides=("L", "R"),
                 brush=0.12):
        self.scene, self.shape, self.armature = scene, shape, armature
        self.start, self.end = float(start), float(max(end, start + 1))
        self.angle, self.follow, self.sides, self.brush = angle, follow, tuple(sides), brush
        self.aspect = picture_aspect(scene)
        self.camera = None
        self.last = None  # per mesh: how far ahead of the front each vertex was a frame before (time field - progress)
        self.centres = {}  # frame: (x, y) of the iris / burn centre
        self.span = None  # where the front runs, fitted to the dancer at the first frame (front_span)
        self.hands = {side: {} for side in self.sides}  # SMEAR: frame: (x, y) of each palm on the picture
        self.previous = {}  # SMEAR: the palms the frame before

    def progress(self, frame):
        """How far the front is at `frame`: the share of the transformation (the clock's hand: how far round)."""
        p = (frame - self.start) / (self.end - self.start)
        return float(clock_progress(p)) if self.shape == "CLOCK" else p

    def __call__(self, i, frame, positions):
        camera = camera_at(self.scene, frame)
        if self.camera is None:
            self.camera = camera
        if camera is None:
            return [np.full(len(p), np.inf) for p in positions]
        if self.shape == "SMEAR":
            return self._smear(frame, camera, positions)
        centre = (0.0, 0.0)
        if self.shape in CENTRED and self.follow and self.armature is not None:
            spot = chest(self.armature)
            if spot is not None:
                cx, cy, ok = project(self.scene, camera, spot[None, :])
                if ok[0]:
                    centre = (float(cx[0]), float(cy[0]))
        self.centres[frame] = centre
        p = self.progress(frame)
        seen = [project(self.scene, camera, pts) if len(pts) else None for pts in positions]
        if self.span is None:
            xs = np.concatenate([x[ok] for x, _y, ok in (v for v in seen if v is not None)] or [np.zeros(0)])
            ys = np.concatenate([y[ok] for _x, y, ok in (v for v in seen if v is not None)] or [np.zeros(0)])
            self.span = front_span(self.shape, xs, ys, self.aspect, self.angle, centre)
        ahead = []
        for got in seen:
            if got is None:
                ahead.append(np.zeros(0))
                continue
            x, y, ok = got
            if self.shape == "TAIJI":
                ahead.append(np.where(ok, taiji_distance(x, y, p, centre, self.span), np.inf))
                continue
            t = time_field(self.shape, x, y, self.angle, centre, self.span)
            ahead.append(np.where(ok, t - p, np.inf))
        out = []
        for k, now in enumerate(ahead):
            before = self.last[k] if self.last is not None and len(self.last[k]) == len(now) else None
            when = np.full(len(now), np.inf)
            reached = now <= 0.0
            if before is None:
                when[reached] = frame
            else:
                crossing = reached & (before > 0.0) & np.isfinite(before)
                share = np.where(crossing, before / np.where(crossing, before - now, 1.0), 1.0)
                when[crossing] = frame - 1.0 + share[crossing]
                when[reached & ~crossing] = frame
            out.append(when)
        self.last = ahead
        return out

    def _smear(self, frame, camera, positions):
        out = [np.full(len(p), np.inf) for p in positions]
        palms = {}
        mw = self.armature.matrix_world if self.armature is not None else None
        for side in self.sides:
            wrist, finger = motion._hand(self.armature, side) if self.armature is not None else (None, None)
            if wrist is None:
                continue
            w = np.array(mw @ wrist.head)
            f = np.array(mw @ finger.head) if finger is not None else np.array(mw @ wrist.tail)
            x, y, ok = project(self.scene, camera, (w + 0.6 * (f - w))[None, :])
            if ok[0]:
                palms[side] = np.array((x[0], y[0]))
                self.hands[side][frame] = (float(x[0]), float(y[0]))
        seen = [project(self.scene, camera, pts)[:3] if len(pts) else None for pts in positions]
        for side, b in palms.items():
            a = self.previous.get(side, b)
            ab = b - a
            length2 = max(float(ab @ ab), 1e-12)
            for got, o in zip(seen, out):
                if got is None:
                    continue
                x, y, ok = got
                vx, vy = x - a[0], y - a[1]
                u = np.clip((vx * ab[0] + vy * ab[1]) / length2, 0.0, 1.0)
                near = (np.hypot(vx - u * ab[0], vy - u * ab[1]) < self.brush) & ok
                when = frame - 1.0 + u if side in self.previous else np.full(len(x), float(frame))
                hit = near & (when < o)
                o[hit] = when[hit]
        self.previous.update(palms)
        return out


def picture_question(scene, settings, armature, start, end):
    """The PictureFront the panel asks for."""
    sides = {"BOTH": ("L", "R"), "LEFT": ("L",), "RIGHT": ("R",)}[settings.hand_side]
    return PictureFront(scene, settings.picture_front, start, end, armature, settings.picture_angle,
                        settings.picture_follow, sides, settings.picture_brush)


# --------------------------------------------------------------------------- lit, sprayed, moved (1.12)

def patches(points, height, seed=0.0):
    """A smooth pseudo-random number 0 .. 1 for each of `points` (world, rest pose), changing over about a tenth of
    the model height: where coats of paint and glows come first, in patches."""
    p = np.asarray(points, dtype=np.float64) / max(height, 1e-6)
    v = np.zeros(len(p))
    for k, (a, b, c, w) in enumerate(((11.0, 7.3, 9.1, 0.5), (17.0, 23.0, 13.0, 0.3), (37.0, 29.0, 41.0, 0.2))):
        v += w * np.sin(a * p[:, 0] + 1.7 * k + seed) * np.sin(b * p[:, 1] + 0.9 * k) * np.sin(c * p[:, 2] + 2.3 * k)
    return np.clip(0.5 + v, 0.0, 1.0)


def _crossing(before, now, frame):
    """When within the last frame a value went from above 0 (`before`) to 0 or below (`now`), np.inf where it did not
    (the first frame: `frame` where it is at or below 0)."""
    when = np.full(len(now), np.inf)
    reached = now <= 0.0
    if before is None:
        when[reached] = frame
        return when
    crossing = reached & (before > 0.0) & np.isfinite(before)
    share = np.where(crossing, before / np.where(crossing, before - now, 1.0), 1.0)
    when[crossing] = frame - 1.0 + share[crossing]
    when[reached & ~crossing] = frame
    return when


class Spotlight:
    """Did the follow spot light the vertex (front or back)? The spot hangs at `source`; its beam, narrow at first
    (SPOT_START of the model height across where it falls), slides in from `side` (a world direction, level) onto the
    dancer's chest over the first SPOT_FIND of the transformation, then opens up until it takes all of her in
    (SPOT_END across). What it did each frame is kept (aims, angles) for the light and the beam (lights.py)."""

    def __init__(self, armature, source, side, start, end, height):
        self.armature, self.source, self.side = armature, np.asarray(source, dtype=np.float64), np.asarray(side)
        self.start, self.end, self.height = float(start), float(max(end, start + 1)), height
        self.last = None
        self.aims = {}  # frame: (aim point (world), half angle)

    def aim(self, frame):
        """(the point the beam aims at, its half angle) at `frame`."""
        t = (frame - self.start) / (self.end - self.start)
        spot = chest(self.armature) if self.armature is not None else None
        if spot is None:
            spot = self.source + np.array((0.0, 0.0, -1.0))
        find = min(max(t / SPOT_FIND, 0.0), 1.0)
        find = find * find * (3.0 - 2.0 * find)
        point = spot + self.side * (SPOT_SIDE * self.height * (1.0 - find))
        open_ = min(max((t - SPOT_FIND) / (1.0 - SPOT_FIND), 0.0), 1.0)
        open_ = open_ * open_ * (3.0 - 2.0 * open_)
        across = (SPOT_START + (SPOT_END - SPOT_START) * open_) * self.height
        distance = max(float(np.linalg.norm(point - self.source)), 1e-6)
        return point, math.atan(0.5 * across / distance)

    def __call__(self, i, frame, positions):
        point, half = self.aim(frame)
        self.aims[frame] = (tuple(float(v) for v in point), half)
        axis = point - self.source
        axis /= max(np.linalg.norm(axis), 1e-9)
        ahead = []
        for pts in positions:
            if not len(pts):
                ahead.append(np.zeros(0))
                continue
            v = pts - self.source
            cos = (v @ axis) / np.maximum(np.linalg.norm(v, axis=1), 1e-9)
            ahead.append(np.arccos(np.clip(cos, -1.0, 1.0)) - half)
        out = [_crossing(self.last[k] if self.last is not None and len(self.last[k]) == len(a) else None, a, frame)
               for k, a in enumerate(ahead)]
        self.last = ahead
        return out


class Spray:
    """The palms spray (Coperni's spray-on dress, a perfume spray): every frame each vertex in a cone from a palm (past
    the fingertips) at the body (SPRAY_ANGLE wide, `reach` long) gets a coat, more near the cone's axis and the nozzle;
    it is covered once it has had enough, its own amount (`needs`: per mesh, about 1, so the coat comes in patches).
    The cone points at the nearest point of the body's middle line (from SPRAY_LOW under the hips to the neck), a
    little along the fingers. The nozzles' way is kept for the mist (mist.py)."""

    def __init__(self, armature, sides, reach, needs, height=1.0):
        self.armature, self.sides, self.reach, self.needs = armature, tuple(sides), reach, needs
        self.height = height
        self.dose = [np.zeros(len(n)) for n in needs]
        self.nozzles = {side: {} for side in self.sides}  # frame: (position, direction) of each nozzle

    def _middle(self):
        """(bottom, top) of the body's middle line now (world), None without the bones."""
        hips = motion.find_bone(self.armature, motion.HIPS)
        neck = motion.find_bone(self.armature, motion.NECK)
        if hips is None or neck is None:
            return None
        mw = self.armature.matrix_world
        low = np.array(mw @ hips.head) - np.array((0.0, 0.0, SPRAY_LOW * self.height))
        return low, np.array(mw @ neck.head)

    def __call__(self, i, frame, positions):
        out = [np.full(len(p), np.inf) for p in positions]
        mw = self.armature.matrix_world
        cone = math.cos(SPRAY_ANGLE)
        middle = self._middle()
        for side in self.sides:
            wrist, finger = motion._hand(self.armature, side)
            if wrist is None:
                continue
            w = np.array(mw @ wrist.head)
            f = np.array(mw @ finger.head) if finger is not None else np.array(mw @ wrist.tail)
            way = f - w
            way /= max(np.linalg.norm(way), 1e-9)
            nozzle = w + 2.0 * (f - w)
            if middle is not None:  # at the body
                a, b = middle
                ab = b - a
                t = min(max(float((nozzle - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0), 1.0)
                at = a + t * ab - nozzle
                if np.linalg.norm(at) > 1e-9:
                    way = SPRAY_FINGERS * way + (1.0 - SPRAY_FINGERS) * at / np.linalg.norm(at)
                    way /= max(np.linalg.norm(way), 1e-9)
            self.nozzles[side][frame] = (tuple(float(v) for v in nozzle), tuple(float(v) for v in way))
            for k, pts in enumerate(positions):
                if not len(pts) or len(pts) != len(self.dose[k]):
                    continue
                v = pts - nozzle
                dist = np.linalg.norm(v, axis=1)
                cos = (v @ way) / np.maximum(dist, 1e-9)
                inside = np.clip((cos - cone) / (1.0 - cone), 0.0, 1.0)
                near = np.clip(1.0 - dist / self.reach, 0.0, 1.0)
                gain = SPRAY_RATE * inside * near
                before = self.dose[k]
                after = before + gain
                need = self.needs[k]
                crossing = (before < need) & (after >= need) & (gain > 0.0)
                when = frame - 1.0 + (need - before) / np.where(crossing, gain, 1.0)
                o = out[k]
                hit = crossing & (when < o)
                o[hit] = when[hit]
                self.dose[k] = after
        return out


class Moving:
    """Moving fast lights it up first (Iris van Herpen's dress of living algae, lit by every move): every frame the way
    each vertex moved, the dancer's own travel (her hips) taken away, is added up; it lights up once that has passed
    its own amount (`needs`: per mesh, world units)."""

    def __init__(self, armature, needs):
        self.armature, self.needs = armature, needs
        self.total = [np.zeros(len(n)) for n in needs]
        self.last = None  # (positions per mesh, hips) the frame before

    def __call__(self, i, frame, positions):
        out = [np.full(len(p), np.inf) for p in positions]
        hips = motion.find_bone(self.armature, motion.HIPS) if self.armature is not None else None
        here = np.array(self.armature.matrix_world @ hips.head) if hips is not None else np.zeros(3)
        if self.last is not None:
            before, there = self.last
            for k, pts in enumerate(positions):
                if not len(pts) or len(pts) != len(self.total[k]) or len(before[k]) != len(pts):
                    continue
                step = np.linalg.norm((pts - before[k]) - (here - there), axis=1)
                was = self.total[k]
                now = was + step
                need = self.needs[k]
                crossing = (was < need) & (now >= need) & (step > 0.0)
                when = frame - 1.0 + (need - was) / np.where(crossing, step, 1.0)
                o = out[k]
                o[crossing] = when[crossing]
                self.total[k] = now
        self.last = ([np.array(p, copy=True) for p in positions], here)
        return out
