"""One-click looks. A preset only sets panel values (sizes stay fitted to the model, or are a share of its height:
Height); some of them are build-time settings, so an effect that is already built gets rebuilt with them. Presets in
WHITE_FLASH also want the compositor's white flash, those in REFRACTION EEVEE's refraction, those with impact frames the
compositor's impact frames (the operator adds them)."""


class Height(float):
    """A size in a preset as a share of the model height (turned into world units when the preset is applied)."""

_OFF = dict(
    entrance="GROW", exit_style="SHRINK", exit_timing="EDGE", particles="NONE", wire_enable=False, holo_enable=False,
    glitch_enable=False, silhouette=False, ribbon_enable=False, edge_glow=True, finale=False, finale_style="PULSE",
    finale_length=0.15, finale_white=0.8, layer_enable=False, layer_style="NANO", inner_glow=False, venom_enable=False,
    venom_metallic=0.0, old_surface="NONE", particle_count=600, easing="EASE", ring_enable=False, paint_style="NONE",
    reactor=False, plates=False, arc_enable=False, trigger="NONE", flame_enable=False, impact_enable=False,
    soul_enable=False, domain_enable=False, domain_arrive="OPEN", shot_enable=False, time_warp="NONE", toon_style="NONE", float_up=False,
    husk_motion="STILL", trail_enable=False, step_flowers=False, look_style="NONE", holo_style="SCAN",
    shell_enable=False, lights_out=False, flash_enable=False, flash_steps=False, streaks=False, smoke_style="WHITE",
    cover_style="NONE", stage_flames=False, tint_style="NONE", body_grow=0.0, dim_style="NONE", totem_enable=False,
    ghost_enable=False, puppet_enable=False, shadow_enable=False, shadow_style="SHADOW", mirror_enable=False,
    echo_enable=False, title_enable=False, sweat_enable=False, peel_enable=False, peel_threads=0.0, fumble_enable=False,
)
# (the finishing pose is not reset: it is a layer over any preset)

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
    ("CLAP", "Clap Change", "On the first clap of the dance the change flows over the body from both hands, the old "
                            "outfit bursting into sparkles, with impact frames (#拍手变装; needs a dance)",
     dict(_OFF, path="SURFACE", trigger="CLAP", exit_style="FRAGMENTS", frag_glow=True, particles="STAR",
          particle_count=500, finale=True, finale_white=0.6, impact_enable=True, speed_lines=True, shockwave=False,
          particle_color=(1.0, 0.85, 0.6), particle_glow=4.0, glow_color=(1.0, 0.5, 0.75),
          frag_wind_dir=(0.0, 0.2, 1.0))),
    ("TURN", "Spin Change", "As the dancer's back is turned to the camera the outfits swap all at once behind a white "
                            "flash and a burst of stars (Wonder Woman's spin; needs a dance with a turn)",
     dict(_OFF, entrance="SWAP", trigger="TURN", exit_style="FRAGMENTS", frag_glow=True, particles="STAR",
          particle_count=400, finale=True, finale_white=0.9, particle_color=(1.0, 0.9, 0.6), particle_glow=4.0,
          glow_color=(1.0, 0.8, 0.4), frag_wind_dir=(0.0, 0.0, 1.0))),
    ("HAND_SWIPE", "Hand Swipe", "The outfit changes where the hands sweep over the body as the dance goes, "
                                 "glittering, then over the rest of it (the hand-swipe change of short videos; needs "
                                 "a dance)",
     dict(_OFF, path="HAND", exit_style="FRAGMENTS", frag_glow=True, particles="STAR", particle_count=400,
          edge_glow_strength=6.0, finale=True, finale_white=0.5, particle_color=(0.8, 0.9, 1.0), particle_glow=4.0,
          glow_color=(0.6, 0.8, 1.0), frag_wind_dir=(0.0, 0.2, 1.0))),
    ("BLUE_FLAME", "Blue Flame Awakening", "Blue flames engulf the body and the outfits swap at their height, with "
                                           "impact frames and a shockwave (Persona 5)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", flame_enable=True, flame_mode="AURA", flame_color=(0.15, 0.45, 1.0),
          flame_strength=5.0, impact_enable=True, speed_lines=True, shockwave=True, edge_glow=False, finale=True,
          finale_white=0.4, particle_color=(0.5, 0.7, 1.0), glow_color=(0.25, 0.5, 1.0))),
    ("PHOENIX", "Phoenix Fire", "A band of fire runs up the body: the old outfit chars and burns away into embers and "
                                "the new one comes out of the flames",
     dict(_OFF, path="UP", flame_enable=True, flame_mode="EDGE", flame_color=(1.0, 0.38, 0.06), old_surface="CHAR",
          surface_color=(0.03, 0.022, 0.016), exit_style="FRAGMENTS", frag_glow=True, particles="EMBER",
          particle_count=600, particle_color=(1.0, 0.45, 0.1), particle_glow=6.0, glow_color=(1.0, 0.45, 0.1),
          frag_wind_dir=(0.0, 0.3, 1.0))),
    ("SUPER_AURA", "Golden Aura", "A golden aura blazes up round the body with arcs of lightning while the change "
                                  "flows over it from the chest, then a flash, impact frames and a shockwave (a "
                                  "Super Saiyan)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", flame_enable=True, flame_mode="AURA", flame_color=(1.0, 0.78, 0.15),
          flame_strength=4.0, arc_enable=True, arc_strike=False, edge_glow_strength=5.0, finale=True, finale_white=0.6,
          impact_enable=True, speed_lines=True, shockwave=True, particle_color=(1.0, 0.9, 0.5),
          glow_color=(1.0, 0.8, 0.25))),
    ("LOTUS", "Lotus Bloom", "Big petals grow up from the floor and close into a lotus bud round the body; the outfits "
                             "swap inside it with a flash and the lotus opens again, petals drifting off (Ne Zha 2)",
     dict(_OFF, entrance="LOTUS", easing="LINEAR", exit_style="FRAGMENTS", frag_glow=True, particles="PETAL",
          particle_count=500, finale=True, finale_white=0.6, particle_color=(1.0, 0.36, 0.5), particle_glow=1.5,
          glow_color=(1.0, 0.75, 0.45), frag_wind_dir=(0.0, 0.2, 1.0))),
    ("HUSK", "Golden Cicada", "At the moment the whole old self is left behind as an amber shell while the dancer goes "
                              "on in the new outfit; then the shell crumbles away (Black Myth's 聚形散气)",
     dict(_OFF, entrance="SWAP", exit_style="HUSK", husk_style="AMBER", husk_away="CRUMBLE", finale=True,
          finale_white=0.5, impact_enable=True, speed_lines=False, shockwave=True, particle_color=(1.0, 0.8, 0.45),
          glow_color=(1.0, 0.7, 0.3), frag_wind_dir=(0.3, 0.3, 0.6))),
    ("SOUL_DEPART", "Soul Departs", "The old self is left behind as a glowing ghost that floats up and fades while the "
                                    "dancer goes on in the new outfit",
     dict(_OFF, entrance="SWAP", exit_style="HUSK", husk_style="GHOST", husk_away="FLOAT", finale=True,
          finale_white=0.3, particle_color=(0.7, 0.85, 1.0), glow_color=(0.45, 0.7, 1.0))),
    ("IMPACT", "Anime Impact", "The change bursts out from the chest under hexagon wires; when it is complete, impact "
                               "frames, speed lines and a shockwave on the floor",
     dict(_OFF, path="SPHERE", wire_enable=True, exit_style="FRAGMENTS", frag_glow=True, impact_enable=True,
          speed_lines=True, shockwave=True, finale=True, finale_white=0.7, particle_color=(1.0, 0.9, 0.7),
          glow_color=(1.0, 0.35, 0.2))),
    ("DANNY", "Two Rings", "A ring of light at the waist splits in two, one going up and one down, and the outfit "
                           "changes where they pass (Danny Phantom)",
     dict(_OFF, path="MIDDLE", ring_enable=True, ring_style="HALO", ring_size=0.9, edge_glow_strength=5.0,
          glow_color=(0.55, 0.85, 1.0))),
    ("IDOL", "Idol Coord Change", "One garment after the other, from the top down, each sweeping on in a glow, the old "
                                  "clothes bursting into sparkles (an idol anime's card-by-card outfit change)",
     dict(_OFF, path="GARMENTS", garment_order="DOWN", exit_style="FRAGMENTS", frag_glow=True, particles="STAR",
          particle_count=400, edge_glow_strength=6.0, finale=True, finale_white=0.5, particle_color=(1.0, 0.85, 0.95),
          particle_glow=4.0, glow_color=(1.0, 0.5, 0.85), frag_wind_dir=(0.0, 0.2, 1.0))),
    ("SOUL_RINGS", "Soul Rings", "Rings of light rise round the body one after another, yellow, purple, black and red, "
                                 "while the change flows over it from the chest (Soul Land)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", soul_enable=True, soul_count=7, exit_style="FRAGMENTS", frag_glow=True,
          particles="STAR", particle_count=300, finale=True, finale_white=0.5, particle_color=(1.0, 0.85, 0.5),
          glow_color=(1.0, 0.75, 0.3))),
    ("MAGICAL", "Magical Girl", "Hands and feet first: the body lights up, ribbons of light wrap the limbs, "
                                "the old outfit bursts into sparkles and the new one flashes when it is complete",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="FRAGMENTS", frag_glow=True, silhouette=True,
          frag_glow_strength=1.5, ribbon_enable=True, ribbon_strength=2.5, particles="STAR", finale=True,
          particle_color=(1.0, 0.85, 0.55), particle_glow=4.0,
          glow_color=(1.0, 0.45, 0.8), frag_wind_dir=(0.0, 0.2, 1.0))),
    # --- 1.11: the world, the camera and time, cartoon physics, the split self, ribbons, moves, looks
    ("DOMAIN", "Domain Expansion", "A starry void opens out from the dancer and swallows the picture; the outfits swap "
                                   "at its height with a zoom punch and impact frames, then the world shatters "
                                   "(Jujutsu Kaisen)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", domain_enable=True, domain_style="VOID", domain_close="SHATTER",
          shot_enable=True, shot_style="PUNCH", impact_enable=True, speed_lines=True, shockwave=False, finale=True,
          finale_white=0.5, particle_color=(0.7, 0.85, 1.0), glow_color=(0.45, 0.65, 1.0))),
    ("CRIMSON", "Crimson Wasteland", "A red sky with a dark sun opens behind the dancer, swords rise out of the "
                                     "cracked ground, and the old outfit chars and burns away into embers (Honkai: "
                                     "Star Rail)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", domain_enable=True, domain_style="CRIMSON", old_surface="CHAR",
          surface_color=(0.03, 0.022, 0.016), exit_style="FRAGMENTS", frag_glow=True, particles="EMBER",
          particle_count=500, particle_color=(1.0, 0.4, 0.08), particle_glow=6.0, glow_color=(1.0, 0.3, 0.05),
          frag_wind_dir=(0.0, 0.3, 1.0))),
    ("FLOWER_FIELD", "Flower Field", "A meadow of flowers opens out from the dancer under a pastel sky; the old outfit "
                                     "blows away in petals from the feet up and a lotus blooms at every step",
     dict(_OFF, path="UP", domain_enable=True, domain_style="FLOWERS", exit_style="FRAGMENTS", frag_glow=False,
          particles="PETAL", particle_count=600, step_flowers=True, step_style="LOTUS",
          particle_color=(1.0, 0.55, 0.7), particle_glow=1.0, glow_color=(1.0, 0.6, 0.8),
          frag_wind_dir=(0.4, 0.2, 0.6))),
    ("SKY_MIRROR", "Sky Mirror", "The dancer floats up into a blue sky over still water with white feathers falling, "
                                 "and lands in the new outfit (a magical girl's transformation; Precure)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", domain_enable=True, domain_style="WATER", float_up=True,
          exit_style="FRAGMENTS", frag_glow=True, particles="FEATHER", particle_count=300,
          particle_color=(1.0, 1.0, 1.0), particle_glow=0.5, finale=True, finale_white=0.6,
          glow_color=(0.75, 0.9, 1.0), frag_wind_dir=(0.0, 0.2, 0.6))),
    ("CONCERT", "Concert", "The stage goes dark, beams of light sweep the hall and the light sticks wave; trails of "
                           "light follow the dancing hands and the picture cuts like a music video at the swap: a low "
                           "angle, the eyes, a wide shot (needs a dance)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", domain_enable=True, domain_style="STAGE", trail_enable=True,
          trail_style="LIGHT", trail_length=0.8, shot_enable=True, shot_style="CUTS", shot_length=2.0, finale=True,
          finale_white=0.4, particle_color=(1.0, 0.85, 1.0), glow_color=(0.85, 0.45, 1.0))),
    ("BULLET_TIME", "Bullet Time", "The dance freezes, hair and skirt hanging in the air, the camera circles the "
                                   "dancer while the outfits swap, then the dance catches up with the music (The "
                                   "Matrix; needs a dance)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", time_warp="FREEZE", warp_length=1.5, shot_enable=True,
          shot_style="ORBIT", shot_angle=360.0, shot_length=1.5, exit_style="FRAGMENTS", frag_glow=True,
          particles="SHARD", particle_count=400, particle_color=(0.75, 0.9, 1.0), particle_glow=2.0,
          glow_color=(0.4, 0.8, 1.0), frag_wind_dir=(0.0, 0.0, 0.0))),
    ("WHIP", "Whip Pan", "The camera whips away and back, the picture smearing, and the outfits swap in the blur (the "
                         "classic outfit change cut of short videos)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", shot_enable=True, shot_style="WHIP", edge_glow=False,
          glow_color=(1.0, 1.0, 1.0))),
    ("VELOCITY", "Velocity Edit", "The dance slows to a quarter at the moment, a zoom punch and impact frames hit, "
                                  "then it speeds up to catch the music (the velocity edits of short videos; needs a "
                                  "dance)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", time_warp="SLOW", warp_length=1.0, shot_enable=True,
          shot_style="PUNCH", impact_enable=True, speed_lines=True, shockwave=True, finale=True, finale_white=0.4,
          particle_color=(1.0, 0.9, 0.7), glow_color=(1.0, 0.4, 0.3))),
    ("SQUISH", "Squash and Bounce", "The body squashes flat as if pressed from above, the outfits swap when it is "
                                    "flattest and it bounces back up, wobbling (Pika's Squish)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", toon_style="SQUASH", edge_glow=False,
          particle_color=(1.0, 0.95, 0.9), glow_color=(1.0, 0.9, 0.6))),
    ("PAPER_FLIP", "Paper Flip", "The body presses into a sheet of paper that turns over, the old outfit on one side "
                                 "and the new one on the other (Paper Mario)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", toon_style="PAPER", edge_glow=False,
          particle_color=(1.0, 1.0, 1.0), glow_color=(1.0, 1.0, 0.9))),
    ("CARD_FLIP", "Card Flip", "The dancer floats up, turns into a magic card that flips over and lands in the new "
                               "outfit, sparkles bursting off (a tarot card)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", toon_style="CARD", float_up=True, exit_style="FRAGMENTS",
          frag_glow=True, particles="STAR", particle_count=300,
          particle_color=(1.0, 0.8, 0.45), particle_glow=4.0, glow_color=(0.8, 0.5, 1.0),
          frag_wind_dir=(0.0, 0.2, 1.0))),
    ("SPLIT", "Split Self", "At the moment the old self steps out beside the dancer and dances on as a mirror image "
                            "while the dancer goes on in the new outfit, then it crumbles away (Lady Gaga's "
                            "Abracadabra; needs a dance)",
     dict(_OFF, entrance="SWAP", exit_style="HUSK", husk_style="ASIS", husk_motion="DANCE", husk_away="CRUMBLE",
          split_mirror=True, husk_hold=1.2, husk_time=0.4, finale=True, finale_white=0.4,
          particle_color=(1.0, 0.9, 0.8), glow_color=(1.0, 0.75, 0.5), frag_wind_dir=(0.3, 0.3, 0.6))),
    ("FIGURINE", "Figurine", "The old self is left behind and shrinks to a glossy figurine on a clear stand beside "
                             "the dancer (the AI figurine craze of 2025)",
     dict(_OFF, entrance="SWAP", exit_style="HUSK", husk_style="PVC", husk_away="FIGURINE", husk_hold=0.1,
          husk_time=0.25, finale=True, finale_white=0.4, particle_color=(1.0, 0.95, 0.85),
          glow_color=(1.0, 0.85, 0.6))),
    ("SLEEVES", "Water Sleeves", "Long white silk sleeves trail from the dancing hands and the new outfit appears "
                                 "wherever they sweep (Chinese opera's water sleeves; needs a dance)",
     dict(_OFF, path="HAND", trail_enable=True, trail_style="SLEEVE", trail_length=0.8, exit_style="FRAGMENTS",
          frag_glow=False, particles="PETAL", particle_count=300, particle_color=(1.0, 0.8, 0.85),
          particle_glow=0.5, glow_color=(0.9, 0.95, 1.0), frag_wind_dir=(0.2, 0.2, 0.5))),
    ("NEZHA", "Red Silk Sash", "A red silk sash with gold hems flies from the hands, a lotus opens at every step, and "
                               "the change flows over the body from the chest (Ne Zha; needs a dance)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", trail_enable=True, trail_style="SASH", trail_length=0.8,
          step_flowers=True, step_style="LOTUS", exit_style="FRAGMENTS", frag_glow=True, particles="PETAL",
          particle_count=300, finale=True, finale_white=0.5, particle_color=(1.0, 0.36, 0.5), particle_glow=1.5,
          glow_color=(1.0, 0.6, 0.3), frag_wind_dir=(0.0, 0.2, 1.0))),
    ("HEART", "Finger Heart", "On the first finger heart of the dance the change bursts out from the hands in pink "
                              "sparkles, a zoom punch at the moment (needs a dance with a finger heart)",
     dict(_OFF, path="SURFACE", trigger="HEART", exit_style="FRAGMENTS", frag_glow=True, particles="STAR",
          particle_count=500, shot_enable=True, shot_style="PUNCH", finale=True, finale_white=0.5,
          particle_color=(1.0, 0.6, 0.8), particle_glow=4.0, glow_color=(1.0, 0.4, 0.7),
          frag_wind_dir=(0.0, 0.2, 1.0))),
    ("SILHOUETTE", "Silhouette", "At the moment the dancer turns into a black silhouette on red and the outfits swap "
                                 "inside it (a magical girl transformation)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", look_style="SILHOUETTE", look_length=0.8,
          look_color=(1.0, 0.08, 0.03), finale=True, finale_white=0.4, glow_color=(1.0, 0.4, 0.3))),
    ("SONG_PAINTING", "Old Painting", "Ink spreads over the old outfit and the picture turns into an old Chinese "
                                      "painting at the moment, the dance going on twos",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", old_surface="INK", look_style="SONG", look_length=1.5,
          time_warp="TWOS", warp_length=1.5, exit_style="FRAGMENTS", frag_glow=False, particles="INK",
          particle_count=300, edge_glow=False, glow_color=(0.2, 0.2, 0.2))),
    ("STARRY_VEIL", "Starry Veil", "The new outfit shows up as a veil of night sky full of stars, sweeping up from the "
                                   "feet, then turns real; the old outfit bursts into sparkles",
     dict(_OFF, path="UP", holo_enable=True, holo_style="STARS", holo_opacity=0.5, exit_style="FRAGMENTS",
          frag_glow=True, particles="STAR", particle_count=400, finale=True, finale_white=0.4,
          particle_color=(0.8, 0.85, 1.0), particle_glow=4.0, glow_color=(0.5, 0.6, 1.0),
          frag_wind_dir=(0.0, 0.2, 1.0))),
    ("PAPER_CUT", "Paper Cut", "The old outfit turns into a red paper cut from the feet up and flies away as red "
                               "paper birds (Chinese paper window flowers)",
     dict(_OFF, path="UP", old_surface="PAPERCUT", surface_color=(0.75, 0.04, 0.03), exit_style="FRAGMENTS",
          frag_glow=False, particles="PAPER_BIRD", particle_count=300, edge_glow=True, glow_color=(1.0, 0.75, 0.4),
          frag_wind_dir=(0.3, 0.2, 0.8))),
    ("WATER_BREATHING", "Water Breathing", "A band of cartoon water winds up round the body and the outfit changes "
                                           "where it passes (Demon Slayer)",
     dict(_OFF, path="SPIRAL", ring_enable=True, ring_style="WATER", ring_size=1.1, exit_style="FRAGMENTS",
          frag_glow=False, particles="SHARD", particle_count=300, particle_color=(0.7, 0.9, 1.0),
          particle_glow=1.0, glow_color=(0.4, 0.75, 1.0), frag_wind_dir=(0.0, 0.0, 0.5))),
    # --- 1.12
    ("WIPE", "Picture Wipe", "A line of light wipes across the picture and the outfit changes wherever it has passed "
                             "over the dancer, front and back alike (the wipe of a video edit)",
     dict(_OFF, path="PICTURE", picture_front="WIPE", picture_angle=0.0, easing="LINEAR", exit_style="FRAGMENTS",
          frag_glow=True, particles="STAR", particle_count=300, particle_color=(0.7, 0.9, 1.0), particle_glow=3.0,
          glow_color=(0.3, 0.8, 1.0), frag_wind_dir=(0.6, 0.0, 0.3))),
    ("IRIS", "Iris Out", "A ring of light opens from the dancer's chest until it has filled the picture, the outfit "
                         "changing inside it",
     dict(_OFF, path="PICTURE", picture_front="IRIS", picture_follow=True, easing="LINEAR", finale=True,
          finale_white=0.4, glow_color=(1.0, 0.85, 0.4))),
    ("FOLDING_FAN", "Folding Fan", "A paper fan opens across the picture from below and the outfit changes as its "
                                   "ribs sweep over the dancer, petals drifting (国风)",
     dict(_OFF, path="PICTURE", picture_front="FAN", paper_color=(0.95, 0.9, 0.78), easing="LINEAR",
          exit_style="FRAGMENTS", frag_glow=False, particles="PETAL", particle_count=300,
          particle_color=(1.0, 0.7, 0.75), particle_glow=0.5, glow_color=(1.0, 0.7, 0.3),
          frag_wind_dir=(0.3, 0.2, 0.5))),
    ("BIG_BRUSH", "Big Brush", "Three strokes of a giant brush in gold ink sweep across the picture, the outfit "
                               "changing under the ink (巨笔; black ink for a light background)",
     dict(_OFF, path="PICTURE", picture_front="BRUSH", ink_color=(0.78, 0.47, 0.09), easing="LINEAR",
          exit_style="FRAGMENTS", frag_glow=False, particles="INK", particle_count=300, edge_glow=False,
          glow_color=(0.2, 0.2, 0.2), frag_wind_dir=(0.4, 0.0, 0.2))),
    ("FILM_BURN", "Film Burn", "The film burns through from the dancer: a hole with a glowing, charred edge spreads "
                               "over the picture with the new outfit in it",
     dict(_OFF, path="PICTURE", picture_front="BURN", picture_follow=True, easing="LINEAR", exit_style="FRAGMENTS",
          frag_glow=True, particles="EMBER", particle_count=400, particle_color=(1.0, 0.5, 0.15), particle_glow=4.0,
          glow_color=(1.0, 0.45, 0.1), frag_wind_dir=(0.0, 0.2, 0.8))),
    ("PAINT_SMEAR", "Paint Smear", "A clap mixes paint on the palms and wherever the hands then smear it across the "
                                   "picture the outfit changes (手搓颜料; needs a dance with a clap)",
     dict(_OFF, path="PICTURE", picture_front="SMEAR", trigger="CLAP", paint_auto=True, picture_brush=0.06,
          easing="LINEAR", edge_glow=False, glow_color=(1.0, 1.0, 1.0))),
    ("CLOCK_HAND", "Clock Hand", "A clock face round the dancer, its hand ticking round in twelve jumps, the outfit "
                                 "changing wherever it has gone round (表盘跳针)",
     dict(_OFF, path="PICTURE", picture_front="CLOCK", picture_follow=True, easing="LINEAR", finale=True,
          finale_white=0.3, glow_color=(1.0, 0.85, 0.5))),
    ("TAIJI", "Taiji", "A taiji turns and grows round the dancer; wherever its white fish comes over her the outfit "
                       "changes, until it has swallowed all of her (太极阴阳)",
     dict(_OFF, path="PICTURE", picture_front="TAIJI", picture_follow=True, easing="LINEAR", exit_style="FRAGMENTS",
          frag_glow=True, particles="STAR", particle_count=200, particle_color=(1.0, 0.95, 0.85), particle_glow=2.0,
          glow_color=(1.0, 0.9, 0.7), frag_wind_dir=(0.0, 0.2, 0.6))),
    ("DHARMA", "Dharma Form", "A giant golden copy of the dancer rises behind her, dances along and dives into her "
                              "at the moment, the outfits swapping in a flash (法相)",
     dict(_OFF, entrance="GIANT", easing="LINEAR", spirit_scale=3.0, spirit_color=(1.0, 0.68, 0.22),
          spirit_glow=2.0, finale=True, finale_white=0.5, glow_color=(1.0, 0.75, 0.3))),
    ("SIX_ARMS", "Three Heads, Six Arms", "Golden arms open out about the dancer's shoulders and heads turn out to "
                                          "either side, the outfits swap in a flash and they fold back (三头六臂, Ne "
                                          "Zha 2)",
     dict(_OFF, entrance="ARMS", easing="LINEAR", arm_pairs=2, arm_heads=True, spirit_color=(1.0, 0.68, 0.22),
          spirit_glow=2.0, finale=True, finale_white=0.4, glow_color=(1.0, 0.75, 0.3))),
    ("THOUSAND_HANDS", "Thousand Hands", "Eight pairs of golden arms fan out about the dancer like a peacock's tail, "
                                         "the outfits swap in a flash and they fold back (千手开屏)",
     dict(_OFF, entrance="ARMS", easing="LINEAR", arm_pairs=8, arm_spread=0.35, arm_heads=False,
          spirit_color=(1.0, 0.72, 0.3), spirit_glow=2.0, finale=True, finale_white=0.4,
          glow_color=(1.0, 0.8, 0.4))),
    ("BARRIER", "Barrier Dome", "A dome of light rises over the dancer from the floor while the outfit changes inside "
                                "it, and shatters at the moment (结界; KPop Demon Hunters' Honmoon)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", shell_enable=True, shell_style="DOME", shell_color=(1.0, 0.78, 0.35),
          shell_glow=2.0, glow_color=(1.0, 0.8, 0.4))),
    ("BUBBLE", "Bubble", "A soap bubble swells round the dancer, the outfit changes inside it and it pops at the "
                         "moment (Glinda's bubble)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", shell_enable=True, shell_style="BUBBLE",
          shell_color=(1.0, 0.85, 0.95), shell_glow=1.5, glow_color=(1.0, 0.75, 0.95))),
    ("WATER_SHELL", "Water Shell", "A ball of rippling water forms round the dancer and bursts into drops at the "
                                   "moment",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", shell_enable=True, shell_style="WATER",
          shell_color=(0.35, 0.65, 1.0), shell_glow=1.5, glow_color=(0.4, 0.75, 1.0))),
    ("TATTOO", "Glowing Tattoos", "Purple marks like tattoos spread over the old outfit ahead of the change, and "
                                  "glitter bursts off it (KPop Demon Hunters)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", old_surface="TATTOO", surface_color=(0.55, 0.15, 1.0),
          exit_style="FRAGMENTS", frag_glow=True, particles="GLITTER", particle_count=900,
          particle_color=(1.0, 0.55, 0.9), particle_glow=2.0, glow_color=(0.8, 0.4, 1.0),
          frag_wind_dir=(0.0, 0.2, 0.8))),
    ("FOLLOW_SPOT", "Follow Spot", "The stage goes dark, a follow spot finds the dancer and the outfit changes "
                                   "wherever its light falls, star streaks at the moment (needs a dance)",
     dict(_OFF, path="SPOTLIGHT", easing="LINEAR", lights_out=True, lights_level=0.08, spot_energy=1.0,
          spot_beam=0.6, spot_color=(1.0, 0.94, 0.82), streaks=True, finale=True, finale_white=0.3,
          glow_color=(1.0, 0.9, 0.7))),
    ("SPRAY_ON", "Spray-On Outfit", "The palms spray the new outfit onto the body in a fine mist, coat by coat "
                                    "(Coperni's spray-on dress; needs a dance)",
     dict(_OFF, path="SPRAY", easing="LINEAR", spray_color=(0.85, 0.93, 1.0), glow_color=(0.7, 0.9, 1.0))),
    ("LIVING_DRESS", "Living Dress", "What moves lights up first: the dancing arms and legs change first and the "
                                     "still parts last (Iris van Herpen's living dress; needs a dance)",
     dict(_OFF, path="MOTION", easing="LINEAR", motion_amount=0.6, exit_style="FRAGMENTS", frag_glow=True,
          particles="STAR", particle_count=300, particle_color=(0.6, 1.0, 0.8), particle_glow=3.0,
          glow_color=(0.3, 1.0, 0.7), frag_wind_dir=(0.0, 0.2, 0.6))),
    ("CAMERA_FLASH", "Camera Flashes", "Camera flashes go off and the change moves on a step with each; the last one "
                                       "shows the new outfit complete (#闪光灯变装)",
     dict(_OFF, path="SPHERE", easing="LINEAR", flash_enable=True, flash_count=4, flash_steps=True, flash_power=1.0,
          glow_color=(1.0, 1.0, 1.0))),
    ("PHOTO_POSE", "Photo Pose", "After the change the dance freezes in a polaroid's frame for a beat and then goes on "
                                 "(写真定格)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", finish_style="PHOTO", finish_delay=0.5, finish_hold=1.2,
          finale=True, finale_white=0.3, glow_color=(1.0, 0.95, 0.85))),
    ("GACHA", "Gacha Pull", "A golden meteor falls onto the dancer, a pillar of light rises, and her name and five "
                            "stars appear while she holds still (抽卡出金)",
     dict(_OFF, entrance="SWAP", easing="LINEAR", finish_style="GACHA", finish_rarity="GOLD", finish_delay=0.6,
          finish_hold=1.5, glow_color=(1.0, 0.8, 0.35))),
    ("EYE_CONTACT", "Eye Contact", "The moment the dancer looks into the camera a star glints in her eyes and the "
                                   "outfit changes from there (#对视变装; needs a dance)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", trigger="GAZE", exit_style="FRAGMENTS", frag_glow=True,
          particles="STAR", particle_count=300, particle_color=(1.0, 0.9, 1.0), particle_glow=3.0,
          glow_color=(1.0, 0.7, 0.9), frag_wind_dir=(0.0, 0.2, 0.8))),
    ("TOON_BOOM", "Toon Explosion", "A cartoon explosion bursts out of the dancer and hides the swap, then burns out "
                                    "into black smoke (卡通爆炸)",
     dict(_OFF, entrance="POOF", smoke_style="BOOM", easing="LINEAR", glow_color=(1.0, 0.6, 0.2))),
    ("SLICED", "Sliced", "The body is cut into bands that change one after another in a random order, the background "
                         "showing between (切片拼装)",
     dict(_OFF, path="SLICES", garment_order="RANDOM", easing="LINEAR", glow_color=(1.0, 1.0, 1.0))),
    ("REWIND", "Rewind and Replay", "The suit-up happens in a flash, then the picture rewinds like a tape and plays it "
                                    "again slowly before catching up with the music (Space Sheriff Gavan; needs a "
                                    "dance)",
     dict(_OFF, path="SPHERE", easing="LINEAR", time_warp="REWIND", warp_length=2.5, wire_enable=True,
          exit_style="FRAGMENTS", frag_glow=True, particles="STAR", particle_count=300,
          particle_color=(0.8, 0.9, 1.0), particle_glow=3.0, glow_color=(0.4, 0.8, 1.0),
          frag_wind_dir=(0.0, 0.2, 0.6))),
    # --- 1.13: what covers the dancer at the big moment
    ("SHATTER", "Shattered Picture", "A sword slash streaks across the picture, cracks run out from it, the glass "
                                     "flashes white as the outfits swap and bursts into shards flying at the camera "
                                     "(打碎画面; Honkai: Star Rail's Seele)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="SHATTER",
          glow_color=(0.55, 0.8, 1.0))),
    ("CLOTH_COVER", "Cloth over the Lens", "A silk cloth flies from her hand at the camera, covers the lens as the "
                                           "outfits swap and slides down (飞布盖镜头)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="CLOTH",
          cover_color=(0.75, 0.08, 0.16), glow_color=(1.0, 0.8, 0.8))),
    ("UMBRELLA", "Umbrella Change", "An umbrella spins past the lens, its canopy filling the picture as the outfits "
                                    "swap, and lifts away shedding petals (雨伞变装)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="UMBRELLA",
          cover_color=(0.85, 0.2, 0.3), particle_color=(1.0, 0.72, 0.78), glow_color=(1.0, 0.8, 0.85))),
    ("FAN_BLADES", "Fan Blades", "The wooden blades of a fan turn in front of the camera and the outfits swap as one "
                                 "sweeps over her (风扇变装)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="FAN",
          glow_color=(1.0, 0.9, 0.8))),
    ("EMOJI", "Emoji Pop", "An emoji on her face pops up over all of her while the outfits swap and shrinks back "
                           "(表情包转场; a picture of your own in the Cover panel)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="EMOJI",
          glow_color=(1.0, 0.85, 0.3))),
    ("FRAME_BURST", "Feathers from the Frame", "A gilded frame stands in front of her, its canvas turns white as the "
                                               "outfits swap and bursts into feathers (画框爆羽, Solange Kardinaly's "
                                               "quick change)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="FRAME",
          glow_color=(1.0, 0.85, 0.5))),
    ("CONFETTI", "Confetti Cannons", "Cannons at the front of the stage fire foil streamers over her as the outfits "
                                     "swap (彩带炮)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="CONFETTI",
          cover_color=(1.0, 0.35, 0.6), finale=True, finale_white=0.2, glow_color=(1.0, 0.85, 0.6))),
    ("BALLOONS", "Balloon Reveal", "As her arms fly open a cloud of balloons bursts out in front of her and rises, "
                                   "the outfits swapping behind it (Drag Race's balloon reveal; on the dance's first "
                                   "open arms when it has them)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, trigger="OPEN",
          cover_style="BALLOONS", cover_color=(0.95, 0.3, 0.55), glow_color=(1.0, 0.8, 0.9))),
    ("FEATHER_FANS", "Feather Fan Dance", "A great feather fan opens on each hand in front of her as the outfits swap "
                                          "(羽扇遮身, a burlesque fan dance; needs a dance)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="FEATHERS",
          cover_color=(1.0, 0.45, 0.7), glow_color=(1.0, 0.85, 0.9))),
    ("CURTAIN_DROP", "Curtain Drop", "A red curtain comes down in front of her, the outfits swap behind it and it "
                                     "drops to the floor (落幕, the kabuki drop)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="CURTAIN",
          cover_color=(0.5, 0.02, 0.04), glow_color=(1.0, 0.75, 0.4))),
    ("MIRROR_BALL", "Mirror Ball", "The lights go down and a mirror ball turns over the dancer, its spots of light "
                                   "sweeping over her and the outfit changing wherever they pass (needs a dance)",
     dict(_OFF, path="MIRROR", easing="LINEAR", lights_out=True, lights_level=0.12, spot_energy=1.0,
          exit_style="FRAGMENTS", frag_glow=True, particles="GLITTER", particle_count=400,
          particle_color=(1.0, 0.8, 0.95), particle_glow=2.0, glow_color=(1.0, 0.8, 1.0),
          frag_wind_dir=(0.0, 0.2, 0.6))),
    ("FLAME_JETS", "Stage Flames", "At the top of her first jump the outfits swap and a row of flame jets along "
                                   "the front of the stage shoots up columns of fire, the lights down round it "
                                   "(台口火柱; needs a dance with a jump)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, trigger="JUMP", stage_flames=True,
          lights_out=True, lights_level=0.25, glow_color=(1.0, 0.6, 0.2))),
    # --- 1.13: tricks on the picture
    ("PIXELATED", "Pixelated Change", "The dancer breaks up into big blocks of colour, the outfits swap while the "
                                      "blocks are biggest, and she comes sharp again (像素打码)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", look_style="PIXEL", look_length=1.2,
          glow_color=(1.0, 1.0, 1.0))),
    ("EDITOR_CURSOR", "Editor Cursor", "A mouse pointer flies in, clicks by the dancer's head and drags a selection "
                                       "box over her; the outfit changes inside it (编辑器光标)",
     dict(_OFF, path="PICTURE", picture_front="MARQUEE", picture_angle=0.0, easing="LINEAR", edge_glow=False,
          glow_color=(1.0, 1.0, 1.0))),
    # --- 1.13: the outfit as a screen
    ("LED_DRESS", "LED Dress", "The old outfit lights up as an LED screen, colour bars, stripes and rings running over "
                               "it, and the new outfit comes behind it from the chest (Beyoncé's LED dress)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", old_surface="LED", surface_width=Height(0.6), edge_glow=True,
          glow_color=(0.6, 0.8, 1.0))),
    ("EPAPER_DRESS", "Electronic Paper", "The old outfit turns into scales of electronic paper that flash and turn "
                                         "grey one by one, and the new outfit ripples in after them (ANREALAGE's SKIN)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", old_surface="EPAPER", surface_width=Height(0.5), edge_glow=False,
          glow_color=(1.0, 1.0, 1.0))),
    # --- 1.13: from many points
    ("IRON_SPARKS", "Iron Sparks", "On the beat a smith strikes molten iron behind her and golden sparks rain down; "
                                   "where they land on her the new outfit starts, with the lights down (打铁花)",
     dict(_OFF, path="ORIGINS", origins_style="SPARKS", origins_count=9, easing="LINEAR", lights_out=True,
          lights_level=0.15, particles="EMBER", particle_count=300, particle_color=(1.0, 0.6, 0.2), particle_glow=3.0,
          glow_color=(1.0, 0.55, 0.15))),
    ("PAINT_SPLATS", "Paint Splats", "Blobs of paint fly at her and splat, the new outfit spreading out from each "
                                     "splat (随机斑点)",
     dict(_OFF, path="ORIGINS", origins_style="SPLATS", origins_count=7, origins_color=(0.95, 0.2, 0.5),
          easing="LINEAR", edge_glow=False)),
    ("TOKENS", "Tokens", "Gold stars fly onto her chest, wrists, waist and ankles one after another and the new outfit "
                         "spreads out from each (信物上身)",
     dict(_OFF, path="ORIGINS", origins_style="TOKENS", origins_count=5, origins_color=(1.0, 0.78, 0.25),
          easing="LINEAR", particles="STAR", particle_count=250, particle_color=(1.0, 0.9, 0.5), particle_glow=3.0,
          glow_color=(1.0, 0.85, 0.4))),
    # --- 1.13: the camera rising with the reveal, growing
    ("SECTION_REVEAL", "Section Reveal", "The new outfit comes garment by garment from the feet up while the camera, "
                                         "close up, rises with it, pausing between the garments, then pulls back to "
                                         "show all of her (分段揭晓, a VTuber's new outfit shown part by part)",
     dict(_OFF, path="GARMENTS", garment_order="UP", easing="LINEAR", shot_enable=True, shot_style="RISE",
          particles="STAR", particle_count=200, particle_color=(1.0, 0.95, 0.85), particle_glow=2.0,
          glow_color=(0.9, 0.95, 1.0))),
    ("POWER_UP", "Power Up", "The new outfit spreads out over her from the chest and she grows a little taller and "
                             "broader as it completes, in a flash (长高变壮, He-Man's first change)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", easing="EASE", body_grow=1.5, finale=True, finale_white=0.35,
          particles="STAR", particle_count=300, particle_color=(1.0, 0.9, 0.5), particle_glow=3.0,
          glow_color=(1.0, 0.85, 0.4))),
    # --- 1.13: the old outfit recoloured on the way to the big moment
    ("FACE_CHANGE", "Face Change", "The whole of her flips through the colours of the opera masks, faster and "
                                   "faster, and the new outfit is the last face (变脸)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, tint_style="FACE", tint_count=7,
          tint_length=2.4, glow_color=(1.0, 0.85, 0.5))),
    ("COLOR_TUG", "Colour Tug", "Pink and blue chase each other across the dress, sweep after sweep, until the new "
                                "outfit takes over (颜色拉锯, the fairies of Sleeping Beauty)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, tint_style="TUG", tint_count=6,
          tint_length=3.0, tint_color_a=(1.0, 0.35, 0.65), tint_color_b=(0.2, 0.45, 1.0), finale=True,
          finale_white=0.2, glow_color=(1.0, 0.8, 1.0))),
    ("ERAS", "Dancers of Every Era", "Copies of her in the looks of other ages come beside and behind her one after "
                                     "another and dance along, then fly into her as the outfits swap (历代舞伴, "
                                     "the juke joint of Sinners; best with a dance)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, tint_style="ERAS", tint_count=6,
          tint_length=4.0, finale=True, finale_white=0.35, glow_color=(1.0, 0.9, 0.7))),
    # --- 1.14: printed layer by layer, the dimension switch
    ("LASER_PRINT", "Laser Print", "The new outfit is printed from the feet up one layer after another, the newest "
                                   "layers red hot, laser heads round her shooting at the layer being printed; thin "
                                   "supports hold up what hangs over and crumble into cubes once it is done, while "
                                   "the old outfit breaks into glowing red flakes (激光打印, Tron: Ares)",
     dict(_OFF, path="PRINT", entrance="GROW", easing="LINEAR", exit_style="FRAGMENTS", frag_glow=True,
          noise_amount=0.0, edge_push=0.0, edge_glow=False, edge_width=Height(0.1), print_layers=48,
          print_supports=True, print_lasers=4, glow_color=(1.0, 0.08, 0.03))),
    ("DIMENSION", "Into the Real", "The new outfit comes in realistic over her MMD look (her own textures under "
                                   "realistic shading), her head and hair turning as the front passes them, a film "
                                   "camera's grain coming up (次元切换, naevis' \"Done\")",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", easing="EASE", dim_style="FRONT", dim_film=True, dim_lights=True,
          glow_color=(0.9, 0.95, 1.0))),
    ("DIMENSION_BEATS", "Dimension Flicker", "On the beats before the big moment she flips between her MMD look and "
                                             "a realistic one, then the outfits swap in a flash and she stays "
                                             "realistic (次元闪切; best with the music's beats)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, dim_style="BEATS", dim_length=2.5,
          dim_film=True, dim_lights=True, finale=True, finale_white=0.3, glow_color=(1.0, 1.0, 1.0))),
    # --- 1.15: the slot machine, the totem in the mist
    ("SLOT_MACHINE", "Slot Machine", "A slot machine drops in front of her, the lever is pulled and the reels stop "
                                     "one by one on the beats: 7 7 7, the outfits swap behind it in a flash, coins "
                                     "gush out and it rises away (老虎机开奖; best with the music's beats)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="SLOT",
          cover_color=(0.62, 0.02, 0.03), slot_tease=False, finale=True, finale_white=0.25,
          glow_color=(1.0, 0.85, 0.4))),
    ("TOTEM", "Totem in the Mist", "Mist swirls behind her; as her hand goes up lightning strikes it, the mist is "
                                   "drawn into a great star behind her while the change runs from her hand over her, "
                                   "and blows away once she is done (雾中图腾, He-Man's \"I have the power!\")",
     dict(_OFF, trigger="RAISE", path="SPHERE", arc_enable=True, arc_strike=True, exit_style="FRAGMENTS",
          frag_glow=True, edge_glow_strength=5.0, finale=True, finale_white=0.5, totem_enable=True,
          totem_shape="STAR", totem_color=(0.45, 0.6, 1.0), particle_color=(0.7, 0.8, 1.0), particle_glow=3.0,
          glow_color=(0.5, 0.65, 1.0), frag_wind_dir=(0.0, 0.3, 1.0))),
    # --- 1.16: the ghost
    ("GHOST", "Ghost", "She turns into a spirit, see-through from the feet up with pale light flowing up her, mist "
                       "sinking from under her feet and a candle flickering by her; she floats while the new outfit "
                       "comes on, then her feet come back solid and she lands (幽灵化, 以闪亮之名's 「烛魇幽歌」)",
     dict(_OFF, path="SURFACE", seeds="ORIGIN", easing="EASE", ghost_enable=True, ghost_color=(0.6, 0.78, 1.0),
          ghost_alpha=0.45, ghost_glow=1.0, ghost_mist=True, ghost_light=True, float_up=True, float_height=0.1,
          lights_out=True, lights_level=0.35, exit_style="FRAGMENTS", frag_glow=True, particles="STAR",
          particle_count=300, particle_color=(0.75, 0.85, 1.0), particle_glow=2.0, glow_color=(0.6, 0.78, 1.0))),
    ("MARIONETTE", "Marionette", "A control bar comes down over her and threads of light hook her head, wrists and "
                                 "knees; she hangs on them dancing on twos as the old outfit turns to porcelain, the "
                                 "strings snap one by one on the beats, the last as the outfits swap in a white flash, "
                                 "and she lands with a shockwave (人偶, the doll on strings of the Nikki games)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, puppet_enable=True,
          puppet_color=(1.0, 0.82, 0.55), float_up=True, float_height=0.08, time_warp="TWOS", warp_length=3.0,
          impact_enable=True, shockwave=True, finale=True, finale_white=0.4, glow_color=(1.0, 0.9, 0.75))),
    ("SHADOW_PLAY", "Shadow Play", "The lights go down, a glowing screen stands behind her and she is pressed onto it "
                                   "as a shadow-play figure of dyed leather with flowers cut out of it, rods on her "
                                   "hands, moving on twos; the outfits swap in a flash, the screen rises and she steps "
                                   "out of it (皮影, 朱铁雄's 国风 transformation)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, shadow_enable=True,
          shadow_color=(1.0, 0.82, 0.55), shadow_length=2.5, time_warp="TWOS", warp_length=2.5, lights_out=True,
          lights_level=0.15, finale=True, finale_white=0.3, glow_color=(1.0, 0.85, 0.6))),
    ("PAINTING", "Into the Painting", "She is pressed into an oil painting in a gilded frame and dances on in it, "
                                      "painted, while the outfits swap; then the painting rises away and she steps "
                                      "out of it in the new outfit (画中人活过来, Taylor Swift's \"The Fate of "
                                      "Ophelia\")",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, shadow_enable=True,
          shadow_style="PAINTING", shadow_length=2.5, finale=True, finale_white=0.3, glow_color=(1.0, 0.85, 0.55))),
    ("MIRROR_FIRST", "Mirror First", "A tall gilded mirror stands beside her and her reflection dances along; the "
                                     "glass flashes and the reflection is in the new outfit first, then the outfits "
                                     "swap on her too, and the mirror goes (倒影先换, The Little Mermaid's mirror)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, mirror_enable=True,
          mirror_length=2.8, mirror_first=0.9, finale=True, finale_white=0.3, glow_color=(0.85, 0.9, 1.0))),
    ("POLAROID", "Photo Comes Alive", "A polaroid shows up in her hand with her in it, dancing in the new outfit "
                                      "already; it flies at the camera, the outfits swap behind it and it tumbles "
                                      "away (拍立得: the girl in the photo comes to life)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, cover_style="POLAROID",
          finale=True, finale_white=0.25, glow_color=(1.0, 0.9, 0.9))),
    # --- 1.17: the journeys out to the Earth and into the eye, the world folding round her
    ("EARTH_ZOOM", "Out to the Earth", "The camera rises over her faster and faster, bursts through the clouds and "
                                       "out into space where the whole Earth lies below; the outfits swap out there "
                                       "and it dives back down to her in the new one (地球拉远)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, shot_enable=True,
          shot_style="EARTH", shot_length=3.0, glow_color=(0.75, 0.88, 1.0))),
    ("INTO_EYE", "Into the Eye", "The camera flies into her eye, a black iris closing over the picture; the outfits "
                                 "swap in the dark and it comes back out with her in the new one (钻进瞳孔)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, shot_enable=True,
          shot_style="PUPIL", shot_length=2.4, glow_color=(1.0, 0.92, 0.85))),
    ("WORLD_FOLD", "World Fold", "A meadow of flowers rises all round at the horizon and rolls in over her head "
                                 "into a closed ball; the outfits swap in a flash as it closes and it opens out flat, "
                                 "a new world under a pastel sky (世界折叠, Inception)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, domain_enable=True,
          domain_style="FLOWERS", domain_arrive="FOLD", domain_open=0.85, domain_hold=0.5, domain_close="SHATTER",
          finale=True, finale_white=0.35, particle_color=(1.0, 0.75, 0.85), glow_color=(1.0, 0.7, 0.85))),
    # --- 1.18
    ("MULTI_EXPOSURE", "Multiple Exposure", "Copies of her swell out one after another in 1960s colours as the old "
                                            "outfit's last moments play, and copies in the new outfit gather back "
                                            "into her (迷幻多重曝光, The Fantastic Four: First Steps)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, echo_enable=True,
          echo_style="PSYCHEDELIC", echo_count=5, echo_spread=0.6, echo_length=1.5, finale=True, finale_white=0.3,
          glow_color=(1.0, 0.45, 0.8))),
    ("BIG_TITLE", "Big Title", "Gold strokes brush the name of the move across the picture just before the outfits "
                               "swap in a flash, then blow away in specks (书法大字幕)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, title_enable=True,
          title_style="GOLD", title_end="BLOW", title_time=1.0, finale=True, finale_white=0.35,
          glow_color=(1.0, 0.8, 0.4))),
    ("AB_SIDE", "A/B Side", "Plain and washed out, dancing on in flat light, sweat glistening; a wave of the hand "
                            "up, the dance slows and the picture cuts to full colour in a flash as the outfits swap "
                            "(反差 A/B 面 of short videos)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, look_style="PLAIN",
          look_length=4.0, trigger="RAISE", time_warp="SLOW", warp_length=1.0, sweat_enable=True, sweat_amount=1.0,
          sweat_time=4.0, finale=True, finale_white=0.45, glow_color=(1.0, 0.85, 0.7))),
    ("TOUCH_CHANGE", "Touch to Change", "A fingertip touches an ear, the corner of an eye or the glasses and the "
                                        "change flows over the body from there, the old outfit bursting into "
                                        "sparkles (VRChat's outfit gimmicks: 碰饰品、扶眼镜; needs a dance)",
     dict(_OFF, path="SURFACE", trigger="TOUCH", exit_style="FRAGMENTS", frag_glow=True, particles="STAR",
          particle_count=400, finale=True, finale_white=0.5, particle_color=(0.8, 0.9, 1.0), particle_glow=3.0,
          glow_color=(0.5, 0.8, 1.0), frag_wind_dir=(0.0, 0.2, 1.0))),
    ("CHEST_BEAT", "Chest Beat", "Fists drummed on the chest and the change bursts out of it, impact frames and a "
                                 "shockwave on the floor (捶胸, Donkey Kong Bananza's ritual; needs a dance)",
     dict(_OFF, path="SPHERE", trigger="BEAT", exit_style="FRAGMENTS", frag_glow=True, particles="EMBER",
          particle_count=400, impact_enable=True, speed_lines=True, shockwave=True, finale=True, finale_white=0.5,
          particle_color=(1.0, 0.6, 0.2), particle_glow=4.0, glow_color=(1.0, 0.55, 0.15),
          frag_wind_dir=(0.0, 0.3, 1.0))),
    ("SHIRT_RIP", "Shirt Rip", "At the moment the old outfit is ripped open down the middle and flung off round "
                               "her sides, the new one already on under it (撕衬衫: Superman's S)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, peel_enable=True,
          peel_style="RIP", peel_time=0.5, impact_enable=True, speed_lines=True, glow_color=(1.0, 0.8, 0.5))),
    ("KABUKI_FLIP", "Kabuki Flip", "The top of the old outfit turns down over her waist inside out, a red lining with "
                                   "gold crests showing, hangs a moment and drops (ぶっ返り)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, peel_enable=True,
          peel_style="FLIP", peel_time=0.45, peel_hold=1.0, peel_lining=(0.7, 0.04, 0.06),
          glow_color=(1.0, 0.75, 0.4))),
    ("KABUKI_YANK", "Kabuki Yank", "The old outfit is yanked off in two halves, the top up and away and the bottom "
                                   "dropping, in a few frames (引抜き)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, peel_enable=True,
          peel_style="YANK", peel_time=0.25, glow_color=(1.0, 0.8, 0.5))),
    ("PEEL_AWAY", "Peel Away", "The old outfit comes off in strips curling down from the top one after another, "
                               "like a sticker (剥落卷起)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, peel_enable=True,
          peel_style="STRIPS", peel_time=1.2, peel_strips=14, glow_color=(1.0, 0.85, 0.6))),
    ("LOTUS_THREADS", "Lotus Threads", "The old outfit is ripped open and flung off, sticky pink threads stretching "
                                       "from it back to her until they snap (藕断丝连: Ne Zha's lotus-root body)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, peel_enable=True,
          peel_style="RIP", peel_time=0.9, peel_threads=1.5, peel_thread_color=(1.0, 0.62, 0.74),
          peel_lining=(0.95, 0.75, 0.8), glow_color=(1.0, 0.7, 0.8))),
    ("FUMBLE", "Fumble", "She changes in a flash of stars and strikes a pose; then her arm guard (or belt, pads ...) "
                         "drops off, bounces on the floor and goes in a puff of smoke (变身翻车)",
     dict(_OFF, path="SPHERE", exit_style="FRAGMENTS", frag_glow=True, particles="STAR", particle_count=300,
          finale=True, finale_white=0.4, fumble_enable=True, fumble_delay=0.8, fumble_smoke=True,
          particle_color=(1.0, 0.9, 0.6), glow_color=(1.0, 0.85, 0.5))),
    ("DREAM_WORLD", "Dream World", "She blinks and the stage is a dream: a violet night, a great red moon, gouged and "
                                   "twisting, over a black mirror; she changes there and blinks awake on the stage in "
                                   "the new outfit (梦境领域, Kamen Rider Zeztz)",
     dict(_OFF, path="SPHERE", entrance="SWAP", easing="LINEAR", edge_glow=False, domain_enable=True,
          domain_style="DREAM", domain_arrive="BLINK", domain_open=0.6, domain_hold=0.6, finale=True,
          finale_white=0.3, glow_color=(1.0, 0.2, 0.3))),
)

ITEMS = tuple((key, label, description) for key, label, description, _values in PRESETS)
BUILD_TIME = {"path", "seeds", "entrance", "exit_style", "particles", "spiral_pitch", "trigger", "garment_order",
              "picture_front", "picture_angle", "picture_follow", "picture_brush", "spot_side", "spray_reach",
              "motion_amount", "cover_style", "origins_style", "origins_count", "print_layers", "print_supports"}
WHITE_FLASH = {"NANO_FINALE", "CLAMP", "GHOSTS", "BEAT_DROP", "EVOLUTION", "SPARKLE_SPIRAL", "BROOCH", "MARK50",
               "LIGHTNING", "COCOON", "CLAP", "TURN", "HAND_SWIPE", "BLUE_FLAME", "SUPER_AURA", "LOTUS", "HUSK",
               "SOUL_DEPART", "IMPACT", "IDOL", "SOUL_RINGS", "DOMAIN", "SKY_MIRROR", "CONCERT", "VELOCITY",
               "SPLIT", "FIGURINE", "NEZHA", "HEART", "SILHOUETTE", "STARRY_VEIL", "IRIS", "CLOCK_HAND", "DHARMA",
               "SIX_ARMS", "THOUSAND_HANDS", "FOLLOW_SPOT", "PHOTO_POSE", "COLOR_TUG", "ERAS",
               "POWER_UP", "DIMENSION_BEATS", "SLOT_MACHINE", "TOTEM", "MARIONETTE", "SHADOW_PLAY", "PAINTING", "MIRROR_FIRST", "POLAROID",
               "WORLD_FOLD", "MULTI_EXPOSURE", "DREAM_WORLD", "BIG_TITLE", "AB_SIDE", "TOUCH_CHANGE",
               "CHEST_BEAT", "FUMBLE"}
REFRACTION = {"ICE"}  # presets with clear ice: EEVEE's raytracing (screen space refraction before 4.2) goes on


def apply(settings, key):
    """Set the panel values of preset `key`; True when a rebuild is needed for them to take effect. A Height value is
    a share of the model height (the panel's sizes are fitted to the model)."""
    values = next(values for k, _label, _description, values in PRESETS if k == key)
    rebuild = False
    height = None
    if settings.auto_size:  # (the sizes back at their share of the model height first: one preset's own sizes, like
        # the print's even layers without noise, do not carry over into the next preset)
        from .effect import fit_sizes

        height = _model_height(settings)
        fit_sizes(settings, height)
    for name, value in values.items():
        if isinstance(value, Height):
            if height is None:
                height = _model_height(settings)
            value = float(value) * height
        if name in BUILD_TIME and getattr(settings, name) != value:
            rebuild = True
        setattr(settings, name, value)
    return rebuild


def _model_height(settings):
    if settings.size_reference > 0.0:
        return settings.size_reference
    from .effect import model_height

    for ob in (settings.base, settings.target):
        if ob is not None:
            height = model_height(ob)
            if height > 0.0:
                return height
    return 1.0
