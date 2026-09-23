from __future__ import annotations

from pathlib import Path

import pytest

from scripts.full1m_performance_matrix import configure_variant


def _inp(path: Path) -> None:
    path.write_text(
        """dtmapout               = 60
dtmaxout               = 1800
storecumprcp            = 0
storevel                = 1
alpha                   = 0.75
""",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("variant", "dtmaxout", "storecumprcp", "alpha"),
    [
        ("baseline", 60.0, 1, 0.50),
        ("dtmax_only", 1800.0, 1, 0.50),
        ("cumprcp_only", 60.0, 0, 0.50),
        ("alpha_only", 60.0, 1, 0.75),
        ("optimized", 1800.0, 0, 0.75),
    ],
)
def test_performance_matrix_variants_isolate_three_changes(
    tmp_path: Path,
    variant: str,
    dtmaxout: float,
    storecumprcp: int,
    alpha: float,
) -> None:
    model_dir = tmp_path / variant
    model_dir.mkdir()
    _inp(model_dir / "sfincs.inp")

    settings = configure_variant(
        model_dir,
        variant=variant,
        duration_seconds=1800.0,
    )

    assert float(settings["dtmapout"]) == pytest.approx(60.0)
    assert float(settings["dtmaxout"]) == pytest.approx(dtmaxout)
    assert int(float(settings["storecumprcp"])) == storecumprcp
    assert int(float(settings["storevel"])) == 1
    assert float(settings["alpha"]) == pytest.approx(alpha)
