#!/usr/bin/env python
"""Import an AI-generated task JSON into the pending registry."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PENDING = ROOT / "scene_lab" / "registry" / "pending"
TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_json", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.task_json.read_text(encoding="utf-8"))
    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
        raise SystemExit("task_json must contain a safe string task_id")

    dest = PENDING / task_id
    if dest.exists() and not args.replace:
        raise SystemExit(f"{dest} already exists; pass --replace to overwrite task.json")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "task.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
