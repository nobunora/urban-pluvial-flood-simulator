import json
import subprocess
import sys


def test_openapi_export_is_deterministic_and_contains_phase2b_routes(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    for output in (first, second):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.export_openapi", "--output", str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_text(encoding="utf-8"))
    required_phase2_paths = {
        "/api/v1/geocode",
        "/api/v1/health",
        "/api/v1/rainfall/events/{event_id}",
        "/api/v1/rainfall/stations",
        "/api/v1/rainfall/stations/{station_id}/extremes",
    }
    assert required_phase2_paths <= set(document["paths"])
