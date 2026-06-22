#!/usr/bin/env python
"""Create the bundled move_book candidate in the pending registry."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "scene_lab" / "examples" / "move_book_demo.task.json"
DEST = ROOT / "scene_lab" / "registry" / "pending" / "move_book_demo"


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    (DEST / "task.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(DEST)


if __name__ == "__main__":
    main()
