from __future__ import annotations

from collections.abc import Sequence

from PIL import Image


def flattened_data(image: Image.Image) -> Sequence[object]:
    """Return flattened pixel data without Pillow 12.1+ deprecation warnings.

    Pillow 12.1+ provides get_flattened_data(). Pillow 11 remains supported by
    the project, so older installations fall back to getdata(), where it is
    not deprecated.
    """
    getter = getattr(image, "get_flattened_data", None)
    if getter is not None:
        return getter()
    return tuple(image.getdata())
