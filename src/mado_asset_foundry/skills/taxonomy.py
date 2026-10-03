from __future__ import annotations

CAPABILITY_TERMS: dict[str, tuple[str, ...]] = {
    "background_remove": (
        "background remove",
        "background removal",
        "remove background",
        "remove bg",
        "foreground segmentation",
        "transparent cutout",
    ),
    "alpha_cleanup": (
        "alpha cleanup",
        "alpha mask",
        "edge cleanup",
        "fringe removal",
        "alpha hardening",
    ),
    "trim_transparent_margin": (
        "trim transparent",
        "transparent margin",
        "trim whitespace",
    ),
    "padding_normalize": (
        "padding normalize",
        "normalize padding",
        "consistent padding",
    ),
    "pixel_cleanup": (
        "pixel art cleanup",
        "pixel-art cleanup",
        "pixel cleanup",
        "pixel cleanup pipeline",
    ),
    "palette_reduce": (
        "palette reduce",
        "palette reduction",
        "reduce colors",
        "color reduction",
    ),
    "palette_lock": (
        "palette lock",
        "fixed palette",
        "palette mapping",
        "locked palette",
    ),
    "despeckle": (
        "despeckle",
        "noise pixel removal",
        "isolated pixel removal",
    ),
    "grid_recover": (
        "grid recovery",
        "recover pixel grid",
        "pixel grid recovery",
        "grid reconstruction",
    ),
    "frame_extract": (
        "frame extraction",
        "extract frames",
        "video to frames",
        "video-to-frames",
    ),
    "frame_align": (
        "frame alignment",
        "align frames",
        "sprite alignment",
    ),
    "sprite_sheet_pack": (
        "sprite sheet",
        "spritesheet",
        "sprite atlas",
        "atlas packing",
    ),
    "animation_preview_gif": (
        "gif preview",
        "animated gif",
        "animation preview",
        "preview gif",
    ),
    "godot_export": (
        "godot export",
        "godot import",
        "godot asset",
    ),
    "unity_export": (
        "unity export",
        "unity import",
        "unity asset",
    ),
    "visual_qa": (
        "visual qa",
        "visual quality check",
        "quality inspection",
    ),
}

CAPABILITY_IO: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "background_remove": (("image",), ("transparent_png",)),
    "alpha_cleanup": (("transparent_png",), ("transparent_png",)),
    "trim_transparent_margin": (("transparent_png",), ("transparent_png",)),
    "padding_normalize": (("transparent_png",), ("transparent_png",)),
    "pixel_cleanup": (("image",), ("pixel_art_png",)),
    "palette_reduce": (("image",), ("pixel_art_png",)),
    "palette_lock": (("image",), ("pixel_art_png",)),
    "despeckle": (("image",), ("pixel_art_png",)),
    "grid_recover": (("image",), ("pixel_art_png",)),
    "frame_extract": (("video", "sprite_sheet"), ("frames",)),
    "frame_align": (("frames",), ("frames",)),
    "sprite_sheet_pack": (("frames",), ("sprite_sheet",)),
    "animation_preview_gif": (("frames", "sprite_sheet"), ("gif",)),
    "godot_export": (("image", "sprite_sheet"), ("godot_asset",)),
    "unity_export": (("image", "sprite_sheet"), ("unity_asset",)),
    "visual_qa": (("image",), ("qa_report",)),
}
