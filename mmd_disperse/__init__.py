"""MMD Disperse: nanotech suit-up / outfit transformation for MMD models with Geometry Nodes.

Based on the Hell FX "Spider-Man suit-up with Geometry Nodes" tutorial
(Chinese dub: https://www.bilibili.com/video/BV1Yd4y1X7eR/).
"""

bl_info = {
    "name": "MMD Disperse",
    "description": "Geometry Nodes suit-up transformation between two MMD outfits",
    "author": "mmd_disperse",
    "version": (1, 5, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > MMD Disperse",
    "category": "Animation",
}

import bpy

from . import operators, properties, translations, ui

_classes = operators.classes + ui.classes


def register():
    properties.register()
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.app.translations.register(__name__, translations.translations)


def unregister():
    bpy.app.translations.unregister(__name__)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    properties.unregister()
