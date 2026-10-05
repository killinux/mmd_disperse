import bpy
from bpy.props import EnumProperty

from . import beats, compositor, effect, materials, presets


class MMDDISPERSE_OT_assign(bpy.types.Operator):
    """Use the active object's model"""

    bl_idname = "mmd_disperse.assign"
    bl_label = "Use Active"
    bl_options = {"REGISTER", "UNDO"}

    role: EnumProperty(items=(("BASE", "Old Outfit", ""), ("TARGET", "New Outfit", "")))

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        settings = context.scene.mmd_disperse
        ob = context.active_object
        if self.role == "BASE":
            settings.base = ob
        else:
            settings.target = ob
        return {"FINISHED"}


class MMDDISPERSE_OT_build(bpy.types.Operator):
    """Create the mask, the Geometry Nodes modifiers and the wire material"""

    bl_idname = "mmd_disperse.build"
    bl_label = "Build Transformation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.mmd_disperse
        return settings.target is not None or settings.base is not None

    def execute(self, context):
        settings = context.scene.mmd_disperse
        try:
            info = effect.build(context, settings)
        except effect.EffectError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        if info["unbound"]:
            self.report({"WARNING"}, "Bone names differ, not following the old armature: "
                        + ", ".join(info["unbound"]))
        else:
            text = "Built: {} new / {} old meshes, radius {:.2f}, path computed in {:.1f}s".format(
                info["target_meshes"], info["base_meshes"], info["radius"], info["arrival_seconds"])
            if info["record_seconds"]:
                text += ", motion recorded in {:.1f}s".format(info["record_seconds"])
            self.report({"INFO"}, text)
        return {"FINISHED"}


class MMDDISPERSE_OT_remove(bpy.types.Operator):
    """Remove the effect and restore the models"""

    bl_idname = "mmd_disperse.remove"
    bl_label = "Remove"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.mmd_disperse.mask is not None

    def execute(self, context):
        effect.remove_effect(context.scene.mmd_disperse.mask)
        return {"FINISHED"}


class MMDDISPERSE_OT_fit(bpy.types.Operator):
    """Scale all sizes to the height of the new (or else the old) outfit"""

    bl_idname = "mmd_disperse.fit_size"
    bl_label = "Fit Sizes to Model"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.mmd_disperse
        return settings.target is not None or settings.base is not None

    def execute(self, context):
        settings = context.scene.mmd_disperse
        height = effect.model_height(settings.target or settings.base)
        if height <= 0.0:
            self.report({"ERROR"}, "The outfit has no meshes")
            return {"CANCELLED"}
        effect.fit_sizes(settings, height)
        return {"FINISHED"}


class MMDDISPERSE_OT_bloom(bpy.types.Operator):
    """Turn on bloom so the wires glow (EEVEE bloom before 4.2, otherwise a compositor Glare node)"""

    bl_idname = "mmd_disperse.add_bloom"
    bl_label = "Add Bloom"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            how = compositor.add_bloom(context.scene)
        except RuntimeError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        self.report({"INFO"}, "EEVEE bloom enabled" if how == "EEVEE" else "Glare node added to the compositor")
        return {"FINISHED"}


class MMDDISPERSE_OT_preset(bpy.types.Operator):
    """Set all options for a style (rebuilds the effect when one is already built)"""

    bl_idname = "mmd_disperse.apply_preset"
    bl_label = "Apply Preset"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(name="Preset", items=presets.ITEMS)

    def execute(self, context):
        settings = context.scene.mmd_disperse
        presets.apply(settings, self.preset)
        if settings.mask is not None:
            try:
                effect.build(context, settings)
            except effect.EffectError as err:
                self.report({"ERROR"}, str(err))
                return {"CANCELLED"}
        if self.preset in presets.WHITE_FLASH:
            try:
                compositor.add_white_flash(context.scene)
            except RuntimeError as err:
                self.report({"WARNING"}, str(err))
            effect.update_white_flash(settings)
        if self.preset in presets.REFRACTION and materials.enable_refraction(context.scene):
            self.report({"INFO"}, "EEVEE refraction turned on for the clear ice")
        return {"FINISHED"}


class MMDDISPERSE_OT_glitch_fx(bpy.types.Operator):
    """RGB split that flickers in the compositor while the transformation runs (Lens Distortion dispersion)"""

    bl_idname = "mmd_disperse.add_glitch_fx"
    bl_label = "Add RGB Split"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mmd_disperse
        beat = beats.beat_object() if settings.beat_sync else None
        try:
            compositor.add_glitch(context.scene, settings.frame_start, settings.frame_end, settings.glitch_rate,
                                  beat=beat)
        except RuntimeError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        self.report({"INFO"}, "Lens Distortion added to the compositor")
        return {"FINISHED"}


class MMDDISPERSE_OT_find_beats(bpy.types.Operator):
    """Find the beats of the music (the file, or the first sound strip of the Video Sequencer) for the effect to
    follow"""

    bl_idname = "mmd_disperse.find_beats"
    bl_label = "Find Beats"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mmd_disperse
        scene = context.scene
        fps = scene.render.fps / scene.render.fps_base
        try:
            path, start = beats.music_source(scene, settings.beat_audio)
            times = beats.find(path, fps, settings.beat_sensitivity)
        except beats.BeatError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        if not times:
            self.report({"WARNING"}, "No beats found; try a higher sensitivity")
            return {"CANCELLED"}
        beats.write(scene, times, start, path)
        settings.beat_sync = True
        effect.sync(settings)
        if len(times) > 1:
            bpm = 60.0 * (len(times) - 1) / max(times[-1] - times[0], 1e-6)
            self.report({"INFO"}, "Found {} beats (about {:.0f} per minute)".format(len(times), bpm))
        else:
            self.report({"INFO"}, "Found 1 beat")
        return {"FINISHED"}


class MMDDISPERSE_OT_white_flash(bpy.types.Operator):
    """Flash the whole picture white as the finale starts (a Mix node in the compositor, driven by the mask)"""

    bl_idname = "mmd_disperse.add_white_flash"
    bl_label = "Add White Flash"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mmd_disperse
        try:
            compositor.add_white_flash(context.scene)
        except RuntimeError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        effect.update_white_flash(settings)
        if settings.mask is None or not settings.finale:
            self.report({"WARNING"}, "White flash added; it shows once the effect is built with the finale on")
        else:
            self.report({"INFO"}, "White flash added to the compositor")
        return {"FINISHED"}


classes = (
    MMDDISPERSE_OT_assign,
    MMDDISPERSE_OT_build,
    MMDDISPERSE_OT_remove,
    MMDDISPERSE_OT_fit,
    MMDDISPERSE_OT_bloom,
    MMDDISPERSE_OT_glitch_fx,
    MMDDISPERSE_OT_find_beats,
    MMDDISPERSE_OT_white_flash,
    MMDDISPERSE_OT_preset,
)
