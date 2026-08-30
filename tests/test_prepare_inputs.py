import numpy as np
from scripts.prepare_inputs import roof_rain_weights


def test_roof_rain_weights_conserve_mass():
    b = np.zeros((20, 20), dtype=bool)
    b[5:10, 6:12] = True
    b[13:16, 2:5] = True
    w = roof_rain_weights(b)
    assert np.all(w[b] == 0)
    assert np.isclose(w.sum(), b.size, rtol=0, atol=1e-4)
    assert np.all(w >= 0)
