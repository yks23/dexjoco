#!/usr/bin/env python
"""Verify RoboTwin tasks are materialized in normal DexJoCo task structure."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TASK_ROOT = ROOT / "dexjoco" / "dexjoco" / "tasks"
CATALOG = TASK_ROOT / "robotwin_transfer" / "catalog.json"


def _check_task(task: dict[str, Any], reset: bool) -> dict[str, Any]:
    task_id = task["task_id"]
    result: dict[str, Any] = {"task_id": task_id, "ok": False, "checks": {}, "errors": []}
    task_dir = TASK_ROOT / task_id
    config_path = task_dir / "config.py"
    xml_path = Path(task["xml_path"])
    result["checks"]["task_dir_exists"] = task_dir.is_dir()
    result["checks"]["config_py_exists"] = config_path.is_file()
    result["checks"]["xml_exists"] = xml_path.is_file()
    result["checks"]["config_location_matches_dexjoco_convention"] = (
        config_path == TASK_ROOT / task_id / "config.py"
    )
    try:
        module = importlib.import_module(f"dexjoco.tasks.{task_id}.config")
        result["checks"]["task_config_imports"] = hasattr(module, "TaskConfig")
    except Exception as exc:
        result["checks"]["task_config_imports"] = False
        result["errors"].append(f"import failed: {type(exc).__name__}: {exc}")

    try:
        from dexjoco.tasks import CONFIG_MAPPING

        result["checks"]["config_mapping_registered"] = task_id in CONFIG_MAPPING
        if reset and task_id in CONFIG_MAPPING:
            env = CONFIG_MAPPING[task_id]().get_environment(
                policy_mode=True,
                render_mode="none",
            )
            try:
                obs, info = env.reset()
                result["checks"]["reset_ok"] = True
                result["state_shape"] = list(obs["state"].shape)
                result["action_shape"] = list(env.action_space.shape)
                result["predicate_type"] = info.get("predicate", {}).get("predicate_type")
            finally:
                env.close()
    except Exception as exc:
        if reset:
            result["checks"]["reset_ok"] = False
        result["errors"].append(f"runtime failed: {type(exc).__name__}: {exc}")
        result["traceback"] = traceback.format_exc()

    result["ok"] = all(result["checks"].values()) and not result["errors"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--full-reset", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    tasks = sorted(catalog.get("tasks", []), key=lambda item: item["task_id"])
    if args.limit is not None:
        tasks = tasks[: args.limit]

    results = [_check_task(task, reset=args.full_reset) for task in tasks]
    summary = {
        "catalog": str(args.catalog),
        "checked_count": len(results),
        "ok_count": sum(1 for item in results if item["ok"]),
        "bad_count": sum(1 for item in results if not item["ok"]),
        "registered_spec_count": catalog.get("registered_spec_count", 0),
        "registered_specs": catalog.get("registered_specs", []),
        "results": results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"checked={summary['checked_count']} ok={summary['ok_count']} "
        f"bad={summary['bad_count']} registered_specs={summary['registered_spec_count']}"
    )
    if summary["bad_count"]:
        for item in results:
            if not item["ok"]:
                print(item["task_id"], item["errors"], item["checks"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
