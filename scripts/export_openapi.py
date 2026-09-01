"""Export the FastAPI OpenAPI document without starting a server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from floodsim.api.app import app


def export_openapi(output: Path | None = None) -> str:
    """Return deterministic OpenAPI JSON and optionally write it to a file."""
    document: dict[str, Any] = app.openapi()
    rendered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = export_openapi(args.output)
    if args.output is None:
        print(rendered, end="")


if __name__ == "__main__":
    main()
