"""Beats of the music, for the glitch: slices jump, flash and reshuffle, and the RGB split spikes, on the beat.

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
P_SOURCE = "mmd_disperse_beat_source"  # ... and where they came from
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
    return times


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


def write(scene, times, start, source=""):
    """The beat empty for beats at `times` (seconds) of music starting at frame `start`."""
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
    return ob


def beat_object():
    ob = bpy.data.objects.get(BEAT)
    return ob if ob is not None and ob.type == "EMPTY" else None
