import bpy
from bpy.props import EnumProperty

from . import compositor, effect


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
            self.report({"INFO"}, "Built: {} new / {} old meshes, radius {:.2f}, path computed in {:.1f}s".format(
                info["target_meshes"], info["base_meshes"], info["radius"], info["arrival_seconds"]))
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


classes = (
    MMDDISPERSE_OT_assign,
    MMDDISPERSE_OT_build,
    MMDDISPERSE_OT_remove,
    MMDDISPERSE_OT_fit,
    MMDDISPERSE_OT_bloom,
)
