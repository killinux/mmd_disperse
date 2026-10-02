import bpy

from .model import find_armature


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD Disperse"


def _model_row(layout, settings, prop, role):
    row = layout.row(align=True)
    row.prop(settings, prop)
    row.operator("mmd_disperse.assign", text="", icon="EYEDROPPER").role = role


class MMDDISPERSE_PT_main(_Panel, bpy.types.Panel):
    bl_label = "MMD Disperse"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse

        col = layout.column()
        _model_row(col, s, "base", "BASE")
        _model_row(col, s, "target", "TARGET")
        col.prop(s, "follow_base")

        col = layout.column()
        col.prop(s, "origin_mode")
        if s.origin_mode == "BONE":
            arm = find_armature(s.base or s.target)
            if arm is not None:
                col.prop_search(s, "origin_bone", arm.data, "bones")
        col.prop(s, "space")

        col = layout.column(align=True)
        col.prop(s, "frame_start")
        col.prop(s, "frame_end")
        col = layout.column()
        col.prop(s, "direction")
        col.prop(s, "easing")

        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("mmd_disperse.build", icon="MOD_PARTICLES")
        if s.mask is not None:
            row.operator("mmd_disperse.remove", text="", icon="TRASH")
            layout.prop(s, "mask")


class MMDDISPERSE_PT_edge(_Panel, bpy.types.Panel):
    bl_label = "Edge"
    bl_parent_id = "MMDDISPERSE_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        row = layout.row(align=True)
        row.prop(s, "auto_size")
        row.operator("mmd_disperse.fit_size", text="", icon="FULLSCREEN_ENTER")
        col = layout.column(align=True)
        col.prop(s, "noise_scale")
        col.prop(s, "noise_detail")
        col.prop(s, "noise_amount")
        col = layout.column(align=True)
        col.prop(s, "edge_width")
        col.prop(s, "edge_push")
        col = layout.column(align=True)
        col.prop(s, "edge_glow")
        sub = col.column()
        sub.active = s.edge_glow
        sub.prop(s, "edge_glow_strength")
        layout.prop(s, "subdivide")


class MMDDISPERSE_PT_wire(_Panel, bpy.types.Panel):
    bl_label = "Wire Layer"
    bl_parent_id = "MMDDISPERSE_PT_main"

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "wire_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.wire_enable
        layout.prop(s, "wire_hex")
        col = layout.column(align=True)
        col.prop(s, "wire_inner")
        col.prop(s, "wire_outer")
        col = layout.column(align=True)
        col.prop(s, "wire_radius")
        col.prop(s, "wire_lift")
        col.prop(s, "wire_resolution")
        col = layout.column()
        col.prop(s, "wire_color")
        col.prop(s, "glow_color")
        col.prop(s, "glow_strength")
        layout.operator("mmd_disperse.add_bloom", icon="LIGHT_SUN")


class MMDDISPERSE_PT_old(_Panel, bpy.types.Panel):
    bl_label = "Old Outfit Cleanup"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        col = layout.column(align=True)
        col.prop(s, "base_shrink")
        col.prop(s, "base_delete_offset")
        layout.prop(s, "use_lock")
        col = layout.column()
        col.active = s.use_lock
        col.prop(s, "lock_patterns")
        col.label(text="Rebuild to apply the patterns", icon="INFO")


classes = (
    MMDDISPERSE_PT_main,
    MMDDISPERSE_PT_edge,
    MMDDISPERSE_PT_wire,
    MMDDISPERSE_PT_old,
)
