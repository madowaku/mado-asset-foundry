from PIL import Image

from mado_asset_foundry.pillow_compat import flattened_data


def test_flattened_data_returns_pixels() -> None:
    image = Image.new("L", (2, 2))
    image.putdata([1, 2, 3, 4])

    assert tuple(flattened_data(image)) == (1, 2, 3, 4)
