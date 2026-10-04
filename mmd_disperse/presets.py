"""One-click looks. A preset only sets panel values (sizes stay fitted to the model); some of them are
build-time settings, so an effect that is already built gets rebuilt with them. Presets in WHITE_FLASH also want
the compositor's white flash (the operator adds it)."""

_OFF = dict(
    entrance="GROW", exit_style="SHRINK", particles="NONE", wire_enable=False, holo_enable=False,
    glitch_enable=False, silhouette=False, ribbon_enable=False, edge_glow=True, finale=False, finale_style="PULSE",
    finale_length=0.15, layer_enable=False, layer_style="NANO", inner_glow=False, venom_enable=False,
    old_surface="NONE", particle_count=600,
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
     dict(_OFF, path="SURFACE", seeds="ORIGIN", venom_enable=True, old_surface="VEINS",
          surface_color=(0.006, 0.006, 0.009), layer_enable=True, layer_style="GOO", edge_glow=False)),
    ("ICE", "Freeze and Shatter", "Frost creeps up from the feet and ice crystals grow out of the old outfit, which "
                                  "shatters into chunks and splinters of ice",
     dict(_OFF, path="UP", old_surface="FROST", surface_color=(0.72, 0.86, 1.0), exit_style="CHUNKS",
          frag_glow=False, particles="SHARD", particle_color=(0.75, 0.9, 1.0), particle_glow=1.0,
          glow_color=(0.55, 0.85, 1.0))),
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
    ("MAGICAL", "Magical Girl", "Hands and feet first: the body lights up, ribbons of light wrap the limbs, "
                                "the old outfit bursts into sparkles and the new one flashes when it is complete",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="FRAGMENTS", frag_glow=True, silhouette=True,
          frag_glow_strength=1.5, ribbon_enable=True, ribbon_strength=2.5, particles="STAR", finale=True,
          particle_color=(1.0, 0.85, 0.55), particle_glow=4.0,
          glow_color=(1.0, 0.45, 0.8), frag_wind_dir=(0.0, 0.2, 1.0))),
)

ITEMS = tuple((key, label, description) for key, label, description, _values in PRESETS)
BUILD_TIME = {"path", "seeds", "entrance", "exit_style", "particles"}
WHITE_FLASH = {"NANO_FINALE", "CLAMP", "GHOSTS"}


def apply(settings, key):
    """Set the panel values of preset `key`; True when a rebuild is needed for them to take effect."""
    values = next(values for k, _label, _description, values in PRESETS if k == key)
    rebuild = False
    for name, value in values.items():
        if name in BUILD_TIME and getattr(settings, name) != value:
            rebuild = True
        setattr(settings, name, value)
    return rebuild
