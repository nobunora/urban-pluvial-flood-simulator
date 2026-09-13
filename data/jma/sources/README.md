# Packaged JMA catalog inputs

These files are fixed snapshots of official Japan Meteorological Agency (JMA)
inputs used to build the packaged Phase 2B catalogs:

- `ame_master.zip` — official JMA AMeDAS station master.
- `rank_44173.html` — official annual ranking page for 大島北ノ山.
- `rank_44132.html` — official annual ranking page for 東京.

Official source URLs:

- `https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.zip`
- `https://www.data.jma.go.jp/stats/etrn/view/rank_a.php?block_no=1467&day=&month=&prec_no=44&view=a2&year=`
- `https://www.data.jma.go.jp/stats/etrn/view/rank_s.php?prec_no=44&block_no=47662&year=&month=&day=&view=a2`

The catalog generation timestamp used for these packaged assets is
`2026-09-03T00:00:00+00:00`.

Validated SHA-256 values:

- `ame_master.zip` — `2374836F9F7FBF884D92F49DEFB9EA166ABD60ABE075914BCF7720947AF33596`
- `rank_44132.html` — `3A5D658076A41DE29C450A76EC1EAFC8D669833E251F17AF281E741152DAF123`
- `rank_44173.html` — `68B64F3B86399DB83B7554BC5E10CE9E0E6CFD957F35D1C999C605D49B8DE92D`

Rebuild the committed catalogs from the fixed snapshots with:

```powershell
$catalogArgs = @(
  '-m', 'scripts.build_jma_rainfall_catalog',
  '--station-input', 'data/jma/sources/ame_master.zip',
  '--ranking-input', '44173|大島北ノ山|https://www.data.jma.go.jp/stats/etrn/view/rank_a.php?block_no=1467&day=&month=&prec_no=44&view=a2&year=|data/jma/sources/rank_44173.html',
  '--ranking-input', '44132|東京|https://www.data.jma.go.jp/stats/etrn/view/rank_s.php?prec_no=44&block_no=47662&year=&month=&day=&view=a2|data/jma/sources/rank_44132.html',
  '--generated-at-utc', '2026-09-03T00:00:00+00:00'
)
.venv\Scripts\python.exe @catalogArgs
```

The two ranking snapshots each contribute the explicitly supported rainfall
rows for 10-minute maximum, 1-hour maximum, and daily rainfall. Only the ten
ranked value columns are parsed; the trailing statistics-period column is not
an event. With these two snapshots, the committed event catalog therefore
contains 60 events (2 stations × 3 supported durations × 10 ranks).

This is intentionally limited geographic coverage for Phase 2B and does not
claim nationwide extreme-event coverage. The station catalog remains nationwide
and nearest-station search returns the nearest packaged precipitation-capable
stations even when a station currently has no packaged extreme event; in that
case the station extremes endpoint returns an empty event list.

JMA source attribution must be preserved in generated event/station records and
in user-facing provenance where those records are used.
