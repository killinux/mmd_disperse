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

        layout.operator_menu_enum("mmd_disperse.apply_preset", "preset", icon="PRESET")
        col = layout.column()
        _model_row(col, s, "base", "BASE")
        _model_row(col, s, "target", "TARGET")
        col.prop(s, "follow_base")

        col = layout.column()
        col.prop(s, "path")
        if s.path == "SURFACE":
            col.prop(s, "seeds")
        if s.path == "SPHERE" or (s.path == "SURFACE" and s.seeds != "LIMBS"):
            col.prop(s, "origin_mode")
            if s.origin_mode == "BONE":
                arm = find_armature(s.base or s.target)
                if arm is not None:
                    col.prop_search(s, "origin_bone", arm.data, "bones")
        if s.path == "SPHERE":
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


class MMDDISPERSE_PT_entrance(_Panel, bpy.types.Panel):
    bl_label = "New Outfit Entrance"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.prop(s, "entrance")
        if s.entrance == "ASSEMBLE":
            col = layout.column(align=True)
            col.prop(s, "piece_size")
            col.prop(s, "fly_distance")
            col.prop(s, "fly_range")
            col.prop(s, "frag_spin")


class MMDDISPERSE_PT_hologram(_Panel, bpy.types.Panel):
    bl_label = "Hologram"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "holo_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.holo_enable
        col = layout.column(align=True)
        col.prop(s, "holo_width")
        col.prop(s, "holo_opacity")
        col.prop(s, "holo_strength")
        layout.label(text="Uses the glow color of the wire layer", icon="INFO")


class MMDDISPERSE_PT_glitch(_Panel, bpy.types.Panel):
    bl_label = "Glitch"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "glitch_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.glitch_enable
        col = layout.column(align=True)
        col.prop(s, "glitch_width")
        col.prop(s, "glitch_slice")
        col.prop(s, "glitch_rate")
        col.prop(s, "glitch_shift")
        layout.prop(s, "glitch_flash")
        layout.operator("mmd_disperse.add_glitch_fx", icon="SEQ_CHROMA_SCOPE")


class MMDDISPERSE_PT_ribbons(_Panel, bpy.types.Panel):
    bl_label = "Light Ribbons"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "ribbon_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.ribbon_enable
        col = layout.column(align=True)
        col.prop(s, "ribbon_turns")
        col.prop(s, "ribbon_width")
        col.prop(s, "ribbon_linger")
        col.prop(s, "ribbon_strength")
        layout.label(text="Uses the glow color of the wire layer", icon="INFO")


class MMDDISPERSE_PT_old(_Panel, bpy.types.Panel):
    bl_label = "Old Outfit Cleanup"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.prop(s, "exit_style")
        if s.exit_style == "SHRINK":
            col = layout.column(align=True)
            col.prop(s, "base_shrink")
            col.prop(s, "base_delete_offset")
        elif s.exit_style == "CHUNKS":
            col = layout.column(align=True)
            col.prop(s, "piece_size")
            col.prop(s, "chunk_force")
            col.prop(s, "frag_life")
            col.prop(s, "frag_spin")
        else:
            col = layout.column(align=True)
            col.prop(s, "frag_size")
            col.prop(s, "frag_subdivide")
            col.prop(s, "frag_life")
            col = layout.column(align=True)
            col.prop(s, "frag_burst")
            col.prop(s, "frag_wind")
            col.prop(s, "frag_wind_dir")
            col.prop(s, "frag_turbulence")
            col.prop(s, "frag_spin")
        col = layout.column(align=True)
        if s.exit_style != "SHRINK":
            col.prop(s, "frag_glow")
        col.prop(s, "silhouette")
        sub = col.column(align=True)
        sub.active = s.silhouette
        sub.prop(s, "silhouette_width")
        sub = col.column()
        sub.active = s.silhouette or (s.frag_glow and s.exit_style != "SHRINK")
        sub.prop(s, "frag_glow_strength")
        layout.prop(s, "use_lock")
        col = layout.column()
        col.active = s.use_lock
        col.prop(s, "lock_patterns")
        col.label(text="Rebuild to apply the patterns", icon="INFO")


class MMDDISPERSE_PT_particles(_Panel, bpy.types.Panel):
    bl_label = "Particles"
    bl_parent_id = "MMDDISPERSE_PT_old"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.prop(s, "particles")
        if s.particles == "NONE":
            return
        col = layout.column(align=True)
        if s.particles == "OBJECT":
            col.prop(s, "particle_object")
        col.prop(s, "particle_count")
        col.prop(s, "particle_size")
        col.prop(s, "particle_life")
        if s.particles == "BUTTERFLY":
            col.prop(s, "flap_speed")
        if s.particles != "OBJECT":
            col = layout.column()
            col.prop(s, "particle_color")
            col.prop(s, "particle_glow")


classes = (
    MMDDISPERSE_PT_main,
    MMDDISPERSE_PT_edge,
    MMDDISPERSE_PT_wire,
    MMDDISPERSE_PT_entrance,
    MMDDISPERSE_PT_hologram,
    MMDDISPERSE_PT_glitch,
    MMDDISPERSE_PT_ribbons,
    MMDDISPERSE_PT_old,
    MMDDISPERSE_PT_particles,
)
