"""One-click looks. A preset only sets panel values (sizes stay fitted to the model); some of them are
build-time settings, so an effect that is already built gets rebuilt with them. Presets in WHITE_FLASH also want
the compositor's white flash, those in REFRACTION EEVEE's refraction (the operator adds them)."""

_OFF = dict(
    entrance="GROW", exit_style="SHRINK", exit_timing="EDGE", particles="NONE", wire_enable=False, holo_enable=False,
    glitch_enable=False, silhouette=False, ribbon_enable=False, edge_glow=True, finale=False, finale_style="PULSE",
    finale_length=0.15, layer_enable=False, layer_style="NANO", inner_glow=False, venom_enable=False,
    venom_metallic=0.0, old_surface="NONE", particle_count=600, easing="EASE", ring_enable=False, paint_style="NONE",
    reactor=False, plates=False, arc_enable=False,
)

PRESETS = (
    ("NANOTECH", "Nanotech Suit", "The tutorial: a sphere of hexagon wires sweeps the new suit on",
     dict(_OFF, path="SPHERE", wire_enable=True, glow_color=(0.1, 0.75, 1.0))),
    ("FLOW", "Nanotech Flow", "The suit flows over the body from the chest and both hands and feet",
     dict(_OFF, path="SURFACE", seeds="ORIGIN_LIMBS", wire_enable=True, glow_color=(0.1, 0.75, 1.0))),
    ("DUST", "Turn to Dust", "The old outfit crumbles into dust that blows away, starting at the hands and feet",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="FRAGMENTS", frag_glow=False, edge_glow=False,
          frag_wind_dir=(1.0, 0.4, 0.5))),
    ("SCAN", "Hologram Scan", "A scan from the feet up: the new outfit is printed as a hologram, then turns solid",
     dict(_OFF, path="UP", holo_enable=True, glow_color=(0.1, 0.75, 1.0))),
    ("GLITCH", "Glitch", "Slices flicker between the two outfits around the edge",
     dict(_OFF, path="SPHERE", glitch_enable=True, glitch_flash=True, glow_color=(1.0, 0.15, 0.6))),
    ("ARMOR", "Armor Change", "The old armour is thrown off in chunks while the new one flies in piece by piece",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", entrance="ASSEMBLE", exit_style="CHUNKS", frag_glow=True,
          glow_color=(1.0, 0.55, 0.1))),
    ("NANO_FINALE", "Nanotech Finale", "A dark undersuit flows out from the chest under hexagon wires, the suit forms "
                                       "behind it, then a band of light sweeps over it, stars burst out and the "
                                       "picture flashes white",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", wire_enable=True, layer_enable=True, inner_glow=True, finale=True,
          finale_style="SWEEP", finale_length=0.3, finale_white=0.8, particle_color=(0.6, 0.9, 1.0),
          particle_glow=3.0, glow_color=(0.1, 0.75, 1.0))),
    ("VENOM", "Symbiote", "Black veins spread under the old outfit from the chest, tendrils of goo crawl ahead, sticky "
                          "strands stretch across the gaps, and the goo that covers the body turns into the new suit",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", venom_enable=True, venom_color=(0.006, 0.006, 0.009),
          old_surface="VEINS", surface_color=(0.006, 0.006, 0.009), layer_enable=True, layer_style="GOO",
          edge_glow=False)),
    ("LIQUID_METAL", "Liquid Metal", "Liquid metal runs over the body from the chest in silver veins and tendrils, "
                                     "coats it and turns into the new outfit (Terminator 2's T-1000)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", venom_enable=True, venom_metallic=1.0, venom_color=(0.85, 0.87, 0.9),
          old_surface="VEINS", surface_color=(0.85, 0.87, 0.9), layer_enable=True, layer_style="GOO",
          edge_glow=False)),
    ("ICE", "Freeze and Shatter", "Frost creeps up from the feet and freezes the old outfit to clear ice, crystals "
                                  "grow out of it, the new outfit forms underneath; then all of it shatters into "
                                  "chunks and splinters of ice",
     dict(_OFF, path="UP", old_surface="FROST", surface_color=(0.72, 0.86, 1.0), ice_clarity=0.7, exit_style="CHUNKS",
          exit_timing="AT_ONCE", frag_glow=False, particles="SHARD", particle_color=(0.75, 0.9, 1.0),
          particle_glow=1.0, glow_color=(0.55, 0.85, 1.0))),
    ("BURN", "Burn to Ash", "The old outfit chars from the hands and feet, glowing cracks open, it crumbles into ash "
                            "and embers drift up; the new outfit appears behind a fiery edge",
     dict(_OFF, path="SURFACE", seeds="LIMBS", old_surface="CHAR", surface_color=(0.03, 0.022, 0.016),
          exit_style="FRAGMENTS", frag_glow=True, frag_glow_strength=2.0, particles="EMBER",
          particle_color=(1.0, 0.45, 0.1), particle_glow=6.0, glow_color=(1.0, 0.4, 0.08),
          frag_wind_dir=(0.0, 0.3, 1.0))),
    ("DEREZ", "Derez Cubes", "The old outfit breaks into flakes and glowing cubes from the head down (Tron)",
     dict(_OFF, path="DOWN", exit_style="FRAGMENTS", frag_glow=True, particles="CUBE",
          particle_color=(0.35, 0.9, 1.0), particle_glow=4.0, glow_color=(0.3, 0.85, 1.0),
          frag_wind_dir=(0.0, 0.2, -0.3))),
    ("COINS", "Coin Burst", "The old outfit bursts into spinning gold coins (Ready Player One)",
     dict(_OFF, path="SPHERE", exit_style="SHRINK", particles="COIN", particle_count=2000,
          particle_color=(1.0, 0.72, 0.22), glow_color=(1.0, 0.75, 0.3), frag_wind_dir=(0.0, 0.0, 1.0))),
    ("CLAMP", "Front and Back Clamp", "The new suit is printed in two halves in glowing frames in front of and behind "
                                      "the body; they slide in and clamp shut, the old outfit bursts into flakes, "
                                      "stars and a white flash (Kamen Rider Build)",
     dict(_OFF, entrance="CLAMP", exit_style="FRAGMENTS", frag_glow=True, finale=True, finale_white=0.8,
          particle_color=(1.0, 0.75, 0.5), particle_glow=3.0, glow_color=(1.0, 0.3, 0.2))),
    ("GHOSTS", "Converging Ghosts", "Glowing see-through copies of the new suit appear around the body and converge "
                                    "into it; the suit flashes on as they meet (Kamen Rider Decade)",
     dict(_OFF, entrance="GHOSTS", holo_enable=True, finale=True, finale_white=0.5, particle_color=(1.0, 0.6, 0.9),
          particle_glow=3.0, glow_color=(1.0, 0.2, 0.7))),
    ("MYSTIQUE", "Mystique Scales", "Scales ripple over the body from the chest and turn over one by one, the old "
                                    "outfit on one side of every scale and the new one on the other (X-Men)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", entrance="SCALES", edge_glow=True, glow_color=(0.25, 0.55, 1.0))),
    ("BEAT_DROP", "Beat Drop", "Everything on the beats of the music: the wires flare, the slices glitch, the old "
                               "outfit bursts into sparkles that pop, and the finale flashes white on a beat (Find "
                               "Beats first)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN_LIMBS", wire_enable=True, glitch_enable=True, glitch_flash=True,
          exit_style="FRAGMENTS", frag_glow=True, particles="STAR", finale=True, finale_white=0.8, beat_sync=True,
          particle_color=(0.6, 0.9, 1.0), particle_glow=3.0, glow_color=(1.0, 0.2, 0.6))),
    ("MAGIC_CIRCLE", "Magic Circle Pass", "A glowing magic circle passes through the body from the side and leaves "
                                           "the new outfit behind it (Kamen Rider Wizard)",
     dict(_OFF, path="RIGHT_LEFT", ring_enable=True, ring_style="MAGIC", ring_size=0.85,
          glow_color=(1.0, 0.22, 0.06))),
    ("SPARK_PORTAL", "Spark Portal", "A ring of spinning sparks sweeps across the body like a portal, embers falling "
                                     "where it passes (Doctor Strange)",
     dict(_OFF, path="LEFT_RIGHT", ring_enable=True, ring_style="SPARKS", particles="EMBER", particle_count=250,
          particle_color=(1.0, 0.5, 0.1), particle_glow=6.0, glow_color=(1.0, 0.5, 0.1),
          frag_wind_dir=(0.0, 0.0, -0.3))),
    ("TV_BARRIER", "TV Barrier", "The body passes through a sheet of TV static from the front to the back; slices "
                                 "flicker between the outfits where it is (WandaVision)",
     dict(_OFF, path="FRONT_BACK", ring_enable=True, ring_style="STATIC", glitch_enable=True, glitch_flash=True,
          glow_color=(1.0, 0.2, 0.25))),
    ("SKETCH", "Sketch and Color", "The new outfit is drawn ahead of the edge as line art on paper, from the feet up, "
                                   "and its colours flood in behind it like watercolour",
     dict(_OFF, path="UP", paint_style="LINEART", edge_glow=False)),
    ("INK_WASH", "Ink Wash Painting", "Ink spreads from the chest over the old outfit and turns it into an ink wash "
                                      "painting that breaks up into drops of ink; the new outfit blooms in colour "
                                      "behind it",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", paint_style="INK", old_surface="INK", exit_style="FRAGMENTS",
          frag_glow=False, particles="INK", particle_count=900, edge_glow=False, frag_wind_dir=(0.6, 0.3, 0.2))),
    ("EVOLUTION", "Evolution", "The body glows up and the two outfits flash in turn, faster and faster, until they are "
                               "pure light; then the new one shines out with a burst of stars (Pokemon)",
     dict(_OFF, entrance="EVOLVE", easing="LINEAR", edge_glow_strength=8.0, finale=True, finale_white=0.6,
          particle_color=(0.85, 0.95, 1.0), particle_glow=4.0, glow_color=(0.85, 0.95, 1.0))),
    ("SMOKE_PUFF", "Ninja Smoke Puff", "A puff of white smoke bursts out of the body, the outfit is changed when it "
                                       "clears (a ninja's transformation)",
     dict(_OFF, entrance="POOF", easing="LINEAR", edge_glow=False)),
    ("SHADOW_RISE", "Rise from the Shadow", "The body sinks into its own black shadow on the floor and the new outfit "
                                            "stands up out of it",
     dict(_OFF, entrance="SHADOW", easing="LINEAR", edge_glow=True, edge_glow_strength=3.0,
          glow_color=(0.45, 0.08, 1.0))),
    ("SPARKLE_SPIRAL", "Sparkle Spiral", "A comet of sparkles circles up the body from the feet and changes the outfit "
                                         "where it passes, scattering glittering dust (Cinderella)",
     dict(_OFF, path="SPIRAL", ring_enable=True, ring_style="COMET", exit_style="FRAGMENTS", frag_glow=True,
          particles="STAR", particle_count=500, finale=True, finale_white=0.5, particle_color=(0.7, 0.88, 1.0),
          particle_glow=4.0, glow_color=(0.6, 0.85, 1.0), frag_wind_dir=(0.0, 0.0, 1.0))),
    ("BROOCH", "Magical Brooch", "From the hands and feet the old outfit breaks into glowing flakes that spiral into "
                                 "the brooch on the chest; the new outfit shines when it is complete",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="SUCK", frag_glow=True, particles="STAR", particle_count=400,
          finale=True, finale_white=0.6, particle_color=(1.0, 0.75, 0.9), particle_glow=4.0,
          glow_color=(1.0, 0.45, 0.8))),
    ("MARK50", "Mark 50", "The reactor on the chest (and on the hands and feet) lights up, the dark undersuit flows "
                          "out of it under hexagon wires and the armour plates rise and settle behind it, then a band "
                          "of light runs over the suit (Iron Man)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN_LIMBS", reactor=True, plates=True, layer_enable=True, wire_enable=True,
          inner_glow=True, finale=True, finale_style="SWEEP", finale_length=0.3, finale_white=0.6,
          particle_color=(0.6, 0.9, 1.0), particle_glow=3.0, glow_color=(0.1, 0.75, 1.0))),
    ("BATS", "Bat Swarm", "The old outfit crumbles into darkness and a swarm of bats flies off, a red rim at the edge "
                          "(vampire)",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="FRAGMENTS", frag_glow=False, particles="BAT",
          particle_count=300, glow_color=(0.9, 0.05, 0.1), frag_wind_dir=(0.3, 0.6, 1.0))),
    ("CARDS", "Card Storm", "The old outfit bursts into a storm of glowing playing cards (Gambit)",
     dict(_OFF, path="SPHERE", exit_style="FRAGMENTS", frag_glow=True, particles="CARD", particle_count=700,
          glow_color=(1.0, 0.2, 0.7), frag_wind_dir=(0.0, 0.3, 1.0))),
    ("FEATHERS", "Angel Feathers", "From the head down the old outfit dissolves into light and white feathers drift "
                                   "away; the new outfit glows when it is complete",
     dict(_OFF, path="DOWN", exit_style="FRAGMENTS", frag_glow=True, particles="FEATHER", particle_count=600,
          finale=True, particle_color=(1.0, 0.97, 0.9), particle_glow=1.2, glow_color=(1.0, 0.85, 0.6),
          frag_wind_dir=(0.4, 0.3, -0.2))),
    ("NOTES", "Music Notes", "Glowing music notes float off the old outfit as it changes, for a dance",
     dict(_OFF, path="SURFACE", seeds="ORIGIN_LIMBS", exit_style="FRAGMENTS", frag_glow=True, particles="NOTE",
          particle_count=500, particle_color=(0.45, 0.9, 1.0), particle_glow=4.0, glow_color=(0.45, 0.8, 1.0),
          frag_wind_dir=(0.0, 0.2, 1.0))),
    ("LIGHTNING", "Lightning Strike", "A bolt of lightning strikes the chest with a white flash and the change flows "
                                      "over the body from there, arcs of electricity crackling along its edge; the "
                                      "new outfit flashes when it is complete (Shazam, Thor)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", arc_enable=True, arc_strike=True, exit_style="FRAGMENTS",
          frag_glow=True, edge_glow_strength=6.0, finale=True, finale_white=0.7, particle_color=(0.7, 0.85, 1.0),
          particle_glow=3.0, glow_color=(0.45, 0.65, 1.0), frag_wind_dir=(0.0, 0.3, 1.0))),
    ("MATRIX", "Digital Rain", "Code rains down the old outfit from the head down and it falls apart into glyphs; the "
                               "new outfit appears as code, then its colours come in (The Matrix)",
     dict(_OFF, path="DOWN", old_surface="CODE", paint_style="CODE", exit_style="FRAGMENTS", frag_glow=True,
          particles="GLYPH", particle_count=900, particle_color=(0.35, 1.0, 0.5), particle_glow=3.0,
          glow_color=(0.2, 1.0, 0.4), frag_wind_dir=(0.0, 0.0, -1.0))),
    ("PETRIFY", "Petrify and Crumble", "Stone creeps up the old outfit from the feet and turns it into a cracked "
                                       "statue; the statue crumbles into chunks and pebbles and the new outfit stands "
                                       "there (Medusa)",
     dict(_OFF, path="UP", old_surface="STONE", surface_color=(0.42, 0.4, 0.37), exit_style="CHUNKS",
          exit_timing="AT_ONCE", frag_glow=False, particles="PEBBLE", particle_count=700,
          particle_color=(0.45, 0.43, 0.4), edge_glow=False, frag_wind_dir=(0.0, 0.0, -1.0))),
    ("MIDAS", "Midas Touch", "Liquid gold spreads over the old outfit from the hands and feet until it is a gold "
                             "statue, which bursts into glittering gold and a shower of coins (King Midas)",
     dict(_OFF, path="SURFACE", seeds="LIMBS", old_surface="GOLD", surface_color=(1.0, 0.71, 0.29),
          exit_style="FRAGMENTS", exit_timing="AT_ONCE", frag_glow=True, frag_glow_strength=2.0, particles="COIN",
          particle_count=900, particle_color=(1.0, 0.72, 0.22), glow_color=(1.0, 0.7, 0.25),
          frag_wind_dir=(0.0, 0.3, -1.0))),
    ("TRANSPORTER", "Transporter Beam", "A column of light comes down round the body with sparkles drifting in it; the "
                                        "old outfit shimmers away and the new one shimmers in (Star Trek)",
     dict(_OFF, entrance="BEAM", easing="LINEAR", edge_glow=True, edge_glow_strength=3.0,
          particle_color=(0.75, 0.88, 1.0), particle_glow=4.0, glow_color=(0.5, 0.75, 1.0))),
    ("COCOON", "Break the Cocoon", "White silk spreads up the old outfit from the feet and threads wind round it until "
                                   "it is a cocoon; the cocoon cracks open, falls away and butterflies fly out "
                                   "(Alienware's ad by Framestore)",
     dict(_OFF, path="UP", old_surface="SILK", surface_color=(0.93, 0.91, 0.86), silk_threads=True,
          exit_style="CHUNKS", exit_timing="AT_ONCE", frag_glow=False, particles="BUTTERFLY", particle_count=250,
          particle_color=(0.35, 0.75, 1.0), particle_glow=2.0, finale=True, finale_white=0.4,
          glow_color=(0.6, 0.85, 1.0), frag_wind_dir=(0.0, 0.3, 1.0))),
    ("MAGICAL", "Magical Girl", "Hands and feet first: the body lights up, ribbons of light wrap the limbs, "
                                "the old outfit bursts into sparkles and the new one flashes when it is complete",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="FRAGMENTS", frag_glow=True, silhouette=True,
          frag_glow_strength=1.5, ribbon_enable=True, ribbon_strength=2.5, particles="STAR", finale=True,
          particle_color=(1.0, 0.85, 0.55), particle_glow=4.0,
          glow_color=(1.0, 0.45, 0.8), frag_wind_dir=(0.0, 0.2, 1.0))),
)

ITEMS = tuple((key, label, description) for key, label, description, _values in PRESETS)
BUILD_TIME = {"path", "seeds", "entrance", "exit_style", "particles", "spiral_pitch"}
WHITE_FLASH = {"NANO_FINALE", "CLAMP", "GHOSTS", "BEAT_DROP", "EVOLUTION", "SPARKLE_SPIRAL", "BROOCH", "MARK50",
               "LIGHTNING", "COCOON"}
REFRACTION = {"ICE"}  # presets with clear ice: EEVEE's raytracing (screen space refraction before 4.2) goes on


def apply(settings, key):
    """Set the panel values of preset `key`; True when a rebuild is needed for them to take effect."""
    values = next(values for k, _label, _description, values in PRESETS if k == key)
    rebuild = False
    for name, value in values.items():
        if name in BUILD_TIME and getattr(settings, name) != value:
            rebuild = True
        setattr(settings, name, value)
    return rebuild
