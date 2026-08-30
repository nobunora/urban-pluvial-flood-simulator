import numpy as np
from scripts.download_gsi_dem import decode_gsi_dem_rgb, lat_to_tile_y, lon_to_tile_x


def _rgb(code):
    return [(code >> 16) & 255, (code >> 8) & 255, code & 255]


def test_decode_gsi_dem_positive_negative_nodata():
    codes = np.array([100, (1 << 24) - 123, 1 << 23], dtype=np.uint32)
    rgb = np.array([_rgb(int(x)) for x in codes], dtype=np.uint8).reshape(1, 3, 3)
    out = decode_gsi_dem_rgb(rgb)[0]
    assert np.isclose(out[0], 1.00)
    assert np.isclose(out[1], -1.23)
    assert np.isnan(out[2])


def test_slippy_tile_coordinates_are_finite():
    assert 0 <= lon_to_tile_x(139.7671, 17) < 2**17
    assert 0 <= lat_to_tile_y(35.6812, 17) < 2**17
