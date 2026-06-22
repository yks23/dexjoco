#!/usr/bin/env python
"""Promote generated RoboTwin candidates into DexJoCo-native task catalog."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import read_json, write_json  # noqa: E402

DEXJOCO_XML_ROOT = ROOT / "dexjoco" / "dexjoco" / "sim" / "envs" / "xmls" / "robotwin_tasks"
DEXJOCO_TASK_ROOT = ROOT / "dexjoco" / "dexjoco" / "tasks" / "robotwin_transfer"


def _is_robotwin_candidate(candidate_dir: Path) -> bool:
    task_path = candidate_dir / "task.json"
    if not task_path.exists():
        return False
    try:
        task = read_json(task_path)
    except Exception:
        return False
    return task.get("generator", {}).get("kind") == "robotwin_task_transfer"


def _native_xml_text(scene_xml: str, task_id: str) -> str:
    text = scene_xml.replace('model="SceneLabGenerated"', f'model="{task_id}"')
    text = text.replace("scene_lab_floor", "robotwin_floor")
    text = text.replace("scene_lab_table", "robotwin_table")
    text = text.replace("scene_lab_floor_tex", "robotwin_floor_tex")
    text = text.replace("scene_lab_table_tex", "robotwin_table_tex")
    return text


def _catalog_task(candidate_dir: Path, xml_path: Path) -> dict[str, Any]:
    task = read_json(candidate_dir / "task.json")
    validation = read_json(candidate_dir / "validation.json") if (candidate_dir / "validation.json").exists() else {}
    transfer = read_json(candidate_dir / "transfer_report.json") if (candidate_dir / "transfer_report.json").exists() else {}
    manipulated = next(obj for obj in task.get("objects", []) if obj.get("role") == "manipulated_object")
    return {
        "task_id": task["task_id"],
        "source_task": task.get("task_name"),
        "task_family": task.get("task_family"),
        "instruction": task.get("instruction"),
        "xml_path": str(xml_path.resolve()),
        "object_pose": manipulated.get("pose", [-0.32, -0.18, 0.96, 1.0, 0.0, 0.0, 0.0]),
        "asset_ref": manipulated.get("asset_ref"),
        "asset_category": manipulated.get("category"),
        "success_condition": task.get("success_condition", {}),
        "transfer_report": transfer,
        "validation": {
            "ok": bool(validation.get("ok")),
            "previews": validation.get("previews", []),
            "errors": validation.get("errors", []),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument(
        "--generation-summary",
        type=Path,
        default=ROOT / "scene_lab" / "registry" / "robotwin_task_generation_summary.json",
    )
    parser.add_argument("--xml-out", type=Path, default=DEXJOCO_XML_ROOT)
    parser.add_argument("--task-out", type=Path, default=DEXJOCO_TASK_ROOT)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    args.xml_out.mkdir(parents=True, exist_ok=True)
    args.task_out.mkdir(parents=True, exist_ok=True)

    tasks = []
    for candidate_dir in sorted(args.pending.iterdir()):
        if not candidate_dir.is_dir() or not _is_robotwin_candidate(candidate_dir):
            continue
        validation_path = candidate_dir / "validation.json"
        if not validation_path.exists() or not read_json(validation_path).get("ok"):
            continue
        task_id = candidate_dir.name
        xml_path = args.xml_out / f"{task_id}.xml"
        if xml_path.exists() and not args.replace:
            pass
        else:
            xml_path.write_text(
                _native_xml_text((candidate_dir / "scene.xml").read_text(encoding="utf-8"), task_id),
                encoding="utf-8",
            )
        tasks.append(_catalog_task(candidate_dir, xml_path))

    generation = read_json(args.generation_summary) if args.generation_summary.exists() else {}
    catalog = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "format": "dexjoco.robotwin_transfer.catalog.v1",
        "task_count": len(tasks),
        "tasks": tasks,
        "registered_specs": generation.get("registered_specs", []),
        "registered_spec_count": len(generation.get("registered_specs", [])),
        "notes": [
            "Executable tasks are native DexJoCo CONFIG_MAPPING entries.",
            "registered_specs preserve RoboTwin source-task coverage for tasks that need future bimanual or articulated runtime support.",
        ],
    }
    write_json(args.task_out / "catalog.json", catalog)
    shutil.copy2(args.generation_summary, args.task_out / "robotwin_task_generation_summary.json")
    print(args.task_out / "catalog.json")


if __name__ == "__main__":
    main()
