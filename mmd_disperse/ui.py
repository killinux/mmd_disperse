import bpy

from . import beats, effect
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
        if s.path == "SPIRAL":
            col.prop(s, "spiral_pitch")

        col = layout.column(align=True)
        col.prop(s, "frame_start")
        col.prop(s, "frame_end")
        col = layout.column()
        col.prop(s, "direction")
        col.prop(s, "easing")
        col.prop(s, "leave_behind")
        if effect.missing_recording(s):
            col.label(text="Rebuild to record the motion", icon="INFO")

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
        col = layout.column(align=True)
        col.prop(s, "inner_glow")
        sub = col.column(align=True)
        sub.active = s.inner_glow
        sub.prop(s, "inner_glow_strength")
        sub.prop(s, "inner_depth")
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


class MMDDISPERSE_PT_ring(_Panel, bpy.types.Panel):
    bl_label = "Front Ring"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "ring_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.ring_enable
        layout.prop(s, "ring_style")
        col = layout.column(align=True)
        col.prop(s, "ring_size")
        col.prop(s, "ring_strength")
        if s.path in ("SPHERE", "SURFACE"):
            layout.label(text="Only with the sweeps or Spiral Up", icon="INFO")
        else:
            layout.label(text="Uses the glow color of the wire layer", icon="INFO")


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
        col = layout.column(align=True)
        col.prop(s, "reactor")
        sub = col.column(align=True)
        sub.active = s.reactor
        sub.prop(s, "reactor_size")
        col = layout.column(align=True)
        col.prop(s, "plates")
        sub = col.column(align=True)
        sub.active = s.plates
        sub.prop(s, "plate_size")
        sub.prop(s, "plate_lift")
        sub.prop(s, "plate_width")
        if s.entrance == "ASSEMBLE":
            col = layout.column(align=True)
            col.prop(s, "piece_size")
            col.prop(s, "fly_distance")
            col.prop(s, "fly_range")
            col.prop(s, "frag_spin")
            if s.leave_behind and s.subdivide > 0:
                layout.label(text="Pieces fly in from fixed points only without Subdivide", icon="INFO")
        elif s.entrance == "CLAMP":
            layout.prop(s, "clamp_distance")
            layout.label(text="The frames use the wire layer's colors", icon="INFO")
        elif s.entrance == "GHOSTS":
            col = layout.column(align=True)
            col.prop(s, "ghost_count")
            col.prop(s, "ghost_distance")
            if not s.holo_enable:
                layout.label(text="Turn on the hologram for see-through ghosts", icon="INFO")
        elif s.entrance == "SCALES":
            col = layout.column(align=True)
            col.prop(s, "scale_size")
            col.prop(s, "flip_width")
            layout.label(text="The old outfit turns away on the other side", icon="INFO")
        elif s.entrance == "EVOLVE":
            layout.label(text="Uses the glow color and the edge glow strength", icon="INFO")
        elif s.entrance == "POOF":
            col = layout.column(align=True)
            col.prop(s, "smoke_count")
            col.prop(s, "smoke_size")
        elif s.entrance == "SHADOW":
            layout.prop(s, "shadow_dir")


class MMDDISPERSE_PT_paint(_Panel, bpy.types.Panel):
    bl_label = "Line Art and Ink"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.prop(s, "paint_style")
        if s.paint_style == "NONE" and s.old_surface != "INK":
            return
        col = layout.column(align=True)
        col.prop(s, "paint_width")
        if s.paint_style == "LINEART":
            col.prop(s, "sketch_width")
        col.prop(s, "outline_width")
        col = layout.column()
        col.prop(s, "paper_color")
        col.prop(s, "ink_color")


class MMDDISPERSE_PT_undersuit(_Panel, bpy.types.Panel):
    bl_label = "Dark Undersuit"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "layer_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.layer_enable
        layout.prop(s, "layer_style")
        col = layout.column(align=True)
        col.prop(s, "layer_width")
        if s.layer_style == "GOO":
            layout.label(text="Uses the goo color of the symbiote", icon="INFO")
            return
        col.prop(s, "layer_color")
        col.prop(s, "layer_lines")
        layout.label(text="The seam glows with the edge glow", icon="INFO")


class MMDDISPERSE_PT_venom(_Panel, bpy.types.Panel):
    bl_label = "Symbiote"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "venom_enable", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.venom_enable
        col = layout.column(align=True)
        col.prop(s, "venom_tendrils")
        col.prop(s, "venom_length")
        col.prop(s, "venom_thickness")
        col.prop(s, "venom_speed")
        layout.prop(s, "venom_webs")
        layout.prop(s, "venom_strands")
        col = layout.column(align=True)
        col.prop(s, "venom_color")
        col.prop(s, "venom_metallic")
        if not (s.layer_enable and s.layer_style == "GOO"):
            layout.label(text="Goo coat: Dark Undersuit, Symbiote Goo style", icon="INFO")
        if s.old_surface != "VEINS":
            layout.label(text="Black veins: Old Outfit Surface", icon="INFO")


class MMDDISPERSE_PT_surface(_Panel, bpy.types.Panel):
    bl_label = "Old Outfit Surface"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.prop(s, "old_surface")
        if s.old_surface == "NONE":
            return
        col = layout.column(align=True)
        col.prop(s, "surface_width")
        col.prop(s, "surface_color")
        if s.old_surface == "FROST":
            col = layout.column(align=True)
            col.prop(s, "ice_clarity")
            col.prop(s, "ice_crystals")
            col.prop(s, "crystal_size")


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


class MMDDISPERSE_PT_beats(_Panel, bpy.types.Panel):
    bl_label = "Music Beats"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "beat_sync", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        col = layout.column()
        col.prop(s, "beat_audio")
        row = col.row(align=True)
        row.prop(s, "beat_sensitivity")
        row.operator("mmd_disperse.find_beats", text="", icon="SOUND")
        found = beats.beat_object()
        if found is not None:
            col.label(text="{} beats".format(found.get(beats.P_BEATS, 0)), icon="CHECKMARK")
        elif s.beat_sync:
            col.label(text="Find the beats first", icon="INFO")
        layout.label(text="Glitch, wires, rim, finale and particles follow them", icon="INFO")


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


class MMDDISPERSE_PT_finale(_Panel, bpy.types.Panel):
    bl_label = "Finale Flash"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mmd_disperse, "finale", text="")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        layout.active = s.finale
        layout.prop(s, "finale_style")
        col = layout.column(align=True)
        col.prop(s, "finale_length")
        col.prop(s, "finale_glow")
        if s.finale_style == "SWEEP":
            col.prop(s, "finale_width")
        col = layout.column(align=True)
        col.prop(s, "finale_sparkles")
        col.prop(s, "finale_distance")
        col.prop(s, "particle_size")
        col = layout.column()
        col.prop(s, "particle_color")
        col.prop(s, "particle_glow")
        col = layout.column()
        col.prop(s, "finale_white")
        col.operator("mmd_disperse.add_white_flash", icon="NODE_COMPOSITING")


class MMDDISPERSE_PT_old(_Panel, bpy.types.Panel):
    bl_label = "Old Outfit Cleanup"
    bl_parent_id = "MMDDISPERSE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.mmd_disperse
        if s.entrance == "SCALES":
            layout.label(text="The old outfit turns over with the scales", icon="INFO")
        col = layout.column()
        col.active = s.entrance != "SCALES"
        col.prop(s, "exit_style")
        col.prop(s, "exit_timing")
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
        elif s.exit_style == "SUCK":
            col = layout.column(align=True)
            col.prop(s, "frag_size")
            col.prop(s, "frag_subdivide")
            col.prop(s, "frag_life")
            col.prop(s, "suck_turns")
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
        if s.particles in ("BUTTERFLY", "BAT"):
            col.prop(s, "flap_speed")
        if s.particles not in ("OBJECT", "CARD", "BAT", "INK"):  # those have colours of their own
            col = layout.column()
            col.prop(s, "particle_color")
            col.prop(s, "particle_glow")


classes = (
    MMDDISPERSE_PT_main,
    MMDDISPERSE_PT_edge,
    MMDDISPERSE_PT_wire,
    MMDDISPERSE_PT_ring,
    MMDDISPERSE_PT_entrance,
    MMDDISPERSE_PT_paint,
    MMDDISPERSE_PT_undersuit,
    MMDDISPERSE_PT_venom,
    MMDDISPERSE_PT_surface,
    MMDDISPERSE_PT_hologram,
    MMDDISPERSE_PT_glitch,
    MMDDISPERSE_PT_beats,
    MMDDISPERSE_PT_ribbons,
    MMDDISPERSE_PT_finale,
    MMDDISPERSE_PT_old,
    MMDDISPERSE_PT_particles,
)
