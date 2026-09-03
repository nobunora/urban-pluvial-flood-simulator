# Packaged JMA catalog inputs

These files are fixed snapshots of the official inputs used to build the
packaged Phase 2B catalogs:

- `ame_master.zip`: JMA AMeDAS station master.
- `rank_44173.html`: annual ranking page for 大島北ノ山.
- `rank_44132.html`: annual ranking page for 東京.

Rebuild the committed catalogs with a controlled timestamp:

```powershell
$catalogArgs = @(
  '-m', 'scripts.build_jma_rainfall_catalog',
  '--station-input', 'data/jma/sources/ame_master.zip',
  '--ranking-input', '44173|大島北ノ山|https://www.data.jma.go.jp/stats/etrn/view/rank_a.php?block_no=1467&day=&month=&prec_no=44&view=a2&year=|data/jma/sources/rank_44173.html',
  '--ranking-input', '44132|東京|https://www.data.jma.go.jp/stats/etrn/view/rank_s.php?prec_no=44&block_no=47662&year=&month=&day=&view=a2|data/jma/sources/rank_44132.html',
  '--default-selection',
  '--generated-at-utc', '2026-09-03T00:00:00+00:00'
)
.venv\Scripts\python.exe @catalogArgs
```

`--default-selection` is explicit: it retains the two highest ranked values
for the documented station/duration mapping in the generator. The committed
catalog therefore has limited historical-event coverage and does not claim
nationwide extreme-event coverage.
