#!/usr/bin/env python
"""Materialize promoted RoboTwin tasks as normal DexJoCo task directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = ROOT / "dexjoco" / "dexjoco" / "tasks"
CATALOG = TASK_ROOT / "robotwin_transfer" / "catalog.json"


CONFIG_TEMPLATE = '''"""DexJoCo-native RoboTwin transferred task: {task_id}."""

from ..robotwin_transfer.config import RoboTwinTaskConfig


class TaskConfig(RoboTwinTaskConfig):
    def __init__(self):
        super().__init__("{task_id}")
'''


def _class_name(task_id: str) -> str:
    return "".join(part.capitalize() for part in task_id.split("_")) + "Config"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--task-root", type=Path, default=TASK_ROOT)
    args = parser.parse_args()

    data = json.loads(args.catalog.read_text(encoding="utf-8"))
    tasks = sorted(data.get("tasks", []), key=lambda item: item["task_id"])
    for task in tasks:
        task_id = task["task_id"]
        task_dir = args.task_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "config.py").write_text(
            CONFIG_TEMPLATE.format(task_id=task_id),
            encoding="utf-8",
        )

    imports = [
        f"from .{task['task_id']}.config import TaskConfig as {_class_name(task['task_id'])}"
        for task in tasks
    ]
    entries = [
        f'    "{task["task_id"]}": {_class_name(task["task_id"])},'
        for task in tasks
    ]
    mapping_text = "\n".join(
        [
            '"""Generated RoboTwin task mapping entries."""',
            "",
            *imports,
            "",
            "ROBOTWIN_CONFIG_MAPPING = {",
            *entries,
            "}",
            "",
        ]
    )
    (args.task_root / "robotwin_mappings.py").write_text(mapping_text, encoding="utf-8")
    print(f"materialized {len(tasks)} tasks")


if __name__ == "__main__":
    main()
