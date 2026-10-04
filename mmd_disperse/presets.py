"""One-click looks. A preset only sets panel values (sizes stay fitted to the model); some of them are
build-time settings, so an effect that is already built gets rebuilt with them."""

_OFF = dict(
    entrance="GROW", exit_style="SHRINK", particles="NONE", wire_enable=False, holo_enable=False,
    glitch_enable=False, silhouette=False, ribbon_enable=False, edge_glow=True, finale=False, finale_style="PULSE",
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
    ("MAGICAL", "Magical Girl", "Hands and feet first: the body lights up, ribbons of light wrap the limbs, "
                                "the old outfit bursts into sparkles and the new one flashes when it is complete",
     dict(_OFF, path="SURFACE", seeds="LIMBS", exit_style="FRAGMENTS", frag_glow=True, silhouette=True,
          frag_glow_strength=1.5, ribbon_enable=True, ribbon_strength=2.5, particles="STAR", finale=True,
          particle_color=(1.0, 0.85, 0.55), particle_glow=4.0,
          glow_color=(1.0, 0.45, 0.8), frag_wind_dir=(0.0, 0.2, 1.0))),
)

ITEMS = tuple((key, label, description) for key, label, description, _values in PRESETS)
BUILD_TIME = {"path", "seeds", "entrance", "exit_style", "particles"}


def apply(settings, key):
    """Set the panel values of preset `key`; True when a rebuild is needed for them to take effect."""
    values = next(values for k, _label, _description, values in PRESETS if k == key)
    rebuild = False
    for name, value in values.items():
        if name in BUILD_TIME and getattr(settings, name) != value:
            rebuild = True
        setattr(settings, name, value)
    return rebuild
