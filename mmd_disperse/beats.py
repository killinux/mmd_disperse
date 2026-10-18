"""Beats of the music: the glitch slices jump, flash and reshuffle and the RGB split spikes on the beat; the wires, the
rim, the finale and the particles pulse with it, and the big moments (the finale, the halves clamping shut, the old
outfit shattering) wait for the next beat (effect.py).

The music is read with Audaspace (`aud`, part of Blender), mixed to mono and cut into windows of half a frame. The
loudness of each window (in a log scale, the bass weighted up so the kick drum counts most) rises sharply where a
note starts; a beat is a rise well above the rises around it (within about a second) and above the noise floor, at least
a fifth of a second after the one before; it starts where the sound first gets to half its peak there.

The beats end up on a hidden empty, as animation the node trees and the compositor read without any script running:
its X location is a pulse (1 on a beat, fading over a few frames) and its Y location counts the beats so far.
"""

import math
import os

import bpy
import numpy as np

from . import particles

BEAT = "MMD Disperse Beat"
P_BEATS = "mmd_disperse_beats"  # on the empty: how many beats
P_SOURCE = "mmd_disperse_beat_source"  # ... where they came from
P_FRAMES = "mmd_disperse_beat_frames"  # ... and the frames they are on
P_LOUD = "mmd_disperse_loudness"  # ... the music's loudness frame by frame (1.13), from frame ...
P_LOUD_START = "mmd_disperse_loudness_start"  # ... this one on
BAR = 4  # beats in a bar
DECAY = 3.0  # frames for the pulse to fade to a third
MIN_GAP = 0.2  # seconds between two beats at least


class BeatError(Exception):
    pass


def _strips(scene):
    editor = scene.sequence_editor
    if editor is None:
        return []
    strips = getattr(editor, "strips_all", None)  # Blender 5.0+
    if strips is None:
        strips = editor.sequences_all
    return [s for s in strips if s.type == "SOUND" and s.sound is not None and not s.mute]


def music_source(scene, path):
    """(file, frame where the music starts): `path`, starting with the scene, or the first sound strip of the Video
    Sequencer."""
    if path:
        full = bpy.path.abspath(path)
        if not os.path.isfile(full):
            raise BeatError("Music file not found: " + full)
        return full, float(scene.frame_start)
    strips = sorted(_strips(scene), key=lambda s: s.frame_start)
    if not strips:
        raise BeatError("Pick a music file, or add the music to the Video Sequencer")
    strip = strips[0]
    return bpy.path.abspath(strip.sound.filepath, library=strip.sound.library), float(strip.frame_start)


def _samples(sound):
    data = np.asarray(sound.data(), dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1)
    return data


def _loudness(data, hop):
    """Log loudness of windows `hop` samples apart (two hops long)."""
    count = max(1, len(data) // hop - 1)
    frames = np.lib.stride_tricks.sliding_window_view(data[:(count + 1) * hop], 2 * hop)[::hop][:count]
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    return np.log1p(100.0 * rms)


def find(path, fps, sensitivity=0.5):
    """Times (seconds) of the beats in the music file `path`."""
    return analyse(path, fps, sensitivity)[0]


def analyse(path, fps, sensitivity=0.5):
    """(times (seconds) of the beats in the music file `path`, its loudness frame by frame from its start)."""
    try:
        import aud
    except ImportError as exc:  # pragma: no cover - Blender always has it
        raise BeatError("Audaspace (aud) is not available") from exc
    try:
        sound = aud.Sound(path)
        rate = int(sound.specs[0])
        full = _samples(sound)
        bass = _samples(aud.Sound(path).lowpass(160.0, 0.5))
    except Exception as exc:
        raise BeatError("Cannot read the music: %s" % exc) from exc
    if rate <= 0 or len(full) < rate // 10:
        raise BeatError("The music is too short")
    hop = max(1, int(round(rate / fps / 2.0)))
    step = hop / float(rate)
    loud = _loudness(full, hop) + 1.5 * _loudness(bass, hop)
    frames = loud[:len(loud) // 2 * 2].reshape(-1, 2).mean(axis=1)  # (two windows a frame)
    rise = np.maximum(np.diff(loud, prepend=0.0), 0.0)  # (a loud start is a beat too)
    # compared with the rises within about a second around it
    window = max(3, int(round(1.0 / step)))
    kernel = np.ones(window) / window
    mean = np.convolve(rise, kernel, mode="same")
    spread = np.sqrt(np.maximum(np.convolve(rise * rise, kernel, mode="same") - mean * mean, 0.0))
    level = mean + (2.5 - 2.0 * min(max(sensitivity, 0.0), 1.0)) * spread
    # ... and never at the noise floor of a quiet passage
    level = np.maximum(level, (0.15 - 0.1 * sensitivity) * float(np.percentile(rise, 99.5)) + 1e-4)
    gap = max(1, int(round(MIN_GAP / step)))
    beats = []
    candidates = np.nonzero(rise > level)[0]
    for i in candidates:
        lo, hi = max(0, i - gap), min(len(rise), i + gap + 1)
        if rise[i] < rise[lo:hi].max():
            continue  # a bigger rise close by
        if beats and i - beats[-1] < gap:
            continue
        beats.append(i)
    # The note starts where the sound first gets to half its peak in the windows around the rise.
    times = []
    for i in beats:
        part = np.abs(full[i * hop:(i + 3) * hop])
        onset = int(np.argmax(part >= 0.5 * part.max())) if len(part) else 0
        times.append((i * hop + onset) / float(rate))
    return times, frames


def _fcurves(ob):
    ad = ob.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return []
    curves = getattr(action, "fcurves", None)  # gone in Blender 5.0: layered actions keep them per slot
    if curves is None:
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        curves = bag.fcurves if bag is not None else []
    return list(curves)


def _key(ob, index, frames, values, interpolation):
    """Keys on location[`index`] of `ob` at `frames`, all with `interpolation`."""
    ob.location[index] = values[0]
    ob.keyframe_insert("location", index=index, frame=frames[0])
    fc = next(c for c in _fcurves(ob) if c.data_path == "location" and c.array_index == index)
    fc.keyframe_points.add(len(frames) - 1)
    co = np.column_stack([frames, values]).astype(np.float32).ravel()
    fc.keyframe_points.foreach_set("co", co)
    for key in fc.keyframe_points:
        key.interpolation = interpolation
    fc.update()


def remove():
    ob = bpy.data.objects.get(BEAT)
    if ob is not None:
        action = ob.animation_data.action if ob.animation_data else None
        bpy.data.objects.remove(ob)
        if action is not None and action.users == 0:
            bpy.data.actions.remove(action)


def write(scene, times, start, source="", loudness=None):
    """The beat empty for beats at `times` (seconds) of music starting at frame `start` (and the music's `loudness`
    frame by frame, for the pace of the front and the suggested moment)."""
    remove()
    fps = scene.render.fps / scene.render.fps_base
    ob = bpy.data.objects.new(BEAT, None)
    ob.empty_display_size = 0.1
    ob.hide_render = True
    particles.asset_collection(scene).objects.link(ob)
    beat_frames = np.round(np.array([start + t * fps for t in times], dtype=np.float64))  # on whole frames
    first = int(math.floor(min(scene.frame_start, start)))
    last = int(math.ceil(max(scene.frame_end, beat_frames[-1] + 4 * DECAY if len(beat_frames) else start)))
    frames = np.arange(first, last + 1, dtype=np.float64)
    pulse = np.zeros(len(frames))
    for b in beat_frames:
        after = frames - b
        hit = after >= -0.5
        pulse[hit] = np.maximum(pulse[hit], np.exp(-np.maximum(after[hit], 0.0) / DECAY))
    _key(ob, 0, frames, pulse, "LINEAR")
    count_frames = np.concatenate([[first], beat_frames])
    _key(ob, 1, count_frames, np.arange(len(count_frames), dtype=np.float64), "CONSTANT")
    ob.location = (0.0, 0.0, 0.0)
    ob[P_BEATS] = len(times)
    ob[P_SOURCE] = source
    ob[P_FRAMES] = [float(f) for f in beat_frames]
    if loudness is not None and len(loudness):
        ob[P_LOUD] = [float(v) for v in loudness]
        ob[P_LOUD_START] = float(start)
    return ob


def beat_object():
    ob = bpy.data.objects.get(BEAT)
    return ob if ob is not None and ob.type == "EMPTY" else None


def beat_frames():
    """Frames of the beats found (whole frames, in order); empty when there are none."""
    ob = beat_object()
    return [float(f) for f in ob.get(P_FRAMES, ())] if ob is not None else []


def loudness_at(frames):
    """The music's loudness at `frames` (an array; the quietest level of the song outside it), or None without it."""
    ob = beat_object()
    track = ob.get(P_LOUD) if ob is not None else None
    if not track:
        return None
    track = np.asarray(track, dtype=np.float64)
    index = np.round(np.asarray(frames, dtype=np.float64) - float(ob.get(P_LOUD_START, 0.0))).astype(np.int64)
    inside = (index >= 0) & (index < len(track))
    return np.where(inside, track[np.clip(index, 0, len(track) - 1)], float(track.min()))


SPANS = {"MIDDLE": (0.55, 0.8), "START": (0.03, 0.35), "END": (0.8, 0.97)}
LATEST = 0.88  # the surge after the quiet bars mid-song no later than this share of the song


def suggest(where="MIDDLE"):
    """A frame to change on, from the beats and the loudness of the music: in the middle of the song (55-80% of it,
    where idol games change), the first strong beat after the quietest two bars there whose bar is much louder; near
    the start, the first bar much louder than the two before; near the end, the bar that rises most over the two
    before. (frame, share of the song) or None without beats and loudness."""
    ob = beat_object()
    frames = beat_frames()
    track = ob.get(P_LOUD) if ob is not None else None
    if not track or len(frames) < 3 * BAR:
        return None
    first = float(ob.get(P_LOUD_START, 0.0))
    length = float(len(track))
    gap = float(np.median(np.diff(frames)))
    # the bars every BAR beats from the first, each start put on the beat nearest to it (a beat missed in a quiet
    # passage does not shift the bars after it)
    beat = np.asarray(frames, dtype=np.float64)
    starts = [float(beat[0])]
    while starts[-1] + BAR * gap <= beat[-1] + 0.5 * gap:
        want = starts[-1] + BAR * gap
        near = float(beat[np.argmin(np.abs(beat - want))])
        starts.append(near if abs(near - want) < 0.3 * gap else want)
    bars = list(zip(starts, starts[1:] + [starts[-1] + BAR * gap]))
    level = np.array([float(loudness_at(np.arange(a, max(b, a + 1))).mean()) for a, b in bars])
    lo, hi = SPANS[where]
    inside = [k for k, (a, _b) in enumerate(bars) if first + lo * length <= a <= first + hi * length]
    if not inside:
        return None
    pick = None
    if where == "MIDDLE":
        pairs = [k for k in inside if k + 2 < len(bars)]
        if pairs:
            quiet = min(pairs, key=lambda k: level[k] + level[k + 1])
            floor = 0.5 * (level[quiet] + level[quiet + 1])
            loud = max(1.2 * floor, 0.9 * float(np.median(level)))
            latest = first + LATEST * length
            after = quiet + 2 if bars[quiet + 2][0] <= latest else quiet + 1
            pick = next((j for j in range(quiet + 2, len(bars)) if level[j] >= loud and bars[j][0] <= latest), after)
    else:
        rises = [(level[j] / max(0.5 * (level[j - 1] + level[j - 2]), 1e-6), j) for j in inside if j >= 2]
        if where == "START":
            pick = next((j for ratio, j in rises if ratio >= 1.25), rises[0][1] if rises else inside[0])
        else:
            pick = max(rises)[1] if rises else inside[-1]
    if pick is None:  # (too few bars after the quiet ones)
        pick = inside[0]
    frame = bars[pick][0]
    return frame, (frame - first) / length

