from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_jma_rainfall_catalog import (
    _parse_source_spec,
    _require_official_jma_url,
    build_catalog,
)

FIXTURES = Path(__file__).parent / "fixtures" / "phase2b"
GENERATED_AT = "2026-09-03T00:00:00+00:00"
STATION_SOURCE = "https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.zip"
RANKING_SOURCE = "https://www.data.jma.go.jp/stats/etrn/view/rank_a.php?block_no=1467&view=a2"


def test_generator_accepts_only_official_jma_https_hosts() -> None:
    assert _require_official_jma_url(STATION_SOURCE, label="station source") == STATION_SOURCE
    assert _require_official_jma_url(RANKING_SOURCE, label="ranking source") == RANKING_SOURCE

    invalid_urls = (
        "http://www.jma.go.jp/example",
        "https://example.com/rank",
        "https://jma.go.jp.example.com/rank",
        "https://user@example.jma.go.jp/rank",
        "https://www.jma.go.jp:444/rank",
    )
    for url in invalid_urls:
        with pytest.raises(ValueError):
            _require_official_jma_url(url, label="source")

    with pytest.raises(ValueError, match="official jma.go.jp host"):
        _parse_source_spec("44173|大島北ノ山|https://example.com/rank")


def test_generator_fails_when_required_rainfall_duration_is_missing() -> None:
    # Deliberately omit the daily-rainfall row. A provider layout change must
    # fail generation rather than silently publishing a partial catalog.
    ranking_html = """
    <table>
      <tr>
        <th>日最大10分間降水量<br>(mm)</th>
        <td>26.0<br>(2018/9/10)</td>
      </tr>
      <tr>
        <th>日最大1時間降水量<br>(mm)</th>
        <td>81.0<br>(2022/8/13)</td>
      </tr>
    </table>
    """.encode()

    with pytest.raises(ValueError, match="missing required rainfall durations: 1440 minutes"):
        build_catalog(
            station_payload=(FIXTURES / "jma_amedas.csv").read_bytes(),
            station_source_url=STATION_SOURCE,
            ranking_payloads=[("44173", "大島北ノ山", RANKING_SOURCE, ranking_html)],
            generated_at_utc=GENERATED_AT,
        )


def test_programmatic_catalog_build_rejects_non_jma_provenance_urls() -> None:
    with pytest.raises(ValueError, match="official jma.go.jp host"):
        build_catalog(
            station_payload=(FIXTURES / "jma_amedas.csv").read_bytes(),
            station_source_url="https://example.com/ame_master.zip",
            ranking_payloads=[],
            generated_at_utc=GENERATED_AT,
        )
