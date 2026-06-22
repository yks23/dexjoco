#!/usr/bin/env python
"""Verify promoted RoboTwin success predicates with synthetic MuJoCo states."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

CATALOG = ROOT / "dexjoco" / "dexjoco" / "tasks" / "robotwin_transfer" / "catalog.json"


def _raw_env(env):
    cur = env
    for _ in range(8):
        if cur.__class__.__name__ == "PandaRoboTwinTaskGymEnv":
            return cur
        cur = getattr(cur, "env", None)
        if cur is None:
            break
    raise RuntimeError("Could not unwrap PandaRoboTwinTaskGymEnv")


def _set_object_pose(raw, pos: np.ndarray) -> None:
    start = raw._object_joint_qposadr
    quat = raw._data.qpos[start + 3 : start + 7].copy()
    if not np.any(quat):
        quat = np.asarray([1.0, 0.0, 0.0, 0.0])
    raw._data.qpos[start : start + 7] = np.concatenate([pos, quat])
    mujoco.mj_forward(raw._model, raw._data)


def _positive_position(raw, predicate_type: str, params: dict[str, Any]) -> np.ndarray:
    target = raw._data.site_xpos[raw._target_site_id].copy()
    current = raw._data.body(raw._object_name).xpos.copy()
    if predicate_type == "object_lifted":
        target = current.copy()
        target[2] = float(params.get("min_z", params.get("height", 0.98))) + 0.03
        return target
    if predicate_type in {"objects_stacked", "object_pose_relative_to_object"}:
        target[2] += float(params.get("z_offset", 0.05))
        return target
    if predicate_type in {"object_contact_object", "tool_contact_target"}:
        target[2] = current[2]
        return target
    min_z = float(params.get("min_z", 0.90))
    target[2] = max(current[2], min_z + 0.03)
    return target


def _negative_position(raw, predicate_type: str, params: dict[str, Any]) -> np.ndarray:
    if predicate_type == "object_lifted":
        current = raw._data.body(raw._object_name).xpos.copy()
        current[2] = float(params.get("min_z", params.get("height", 0.98))) - 0.05
        return current
    target = raw._data.site_xpos[raw._target_site_id].copy()
    return target + np.asarray([0.45, 0.45, 0.0])


def _check_one(task_id: str) -> dict[str, Any]:
    from dexjoco.tasks import CONFIG_MAPPING

    result: dict[str, Any] = {"task_id": task_id, "ok": False, "checks": {}, "errors": []}
    env = None
    try:
        env = CONFIG_MAPPING[task_id]().get_environment(policy_mode=True, render_mode="none")
        obs, info = env.reset()
        raw = _raw_env(env)
        predicate_type = raw._predicate_type
        params = raw._predicate_params
        initial = raw._compute_predicate()
        result["predicate_type"] = predicate_type
        result["initial"] = initial
        result["checks"]["initial_false"] = not bool(initial["ok"])

        _set_object_pose(raw, _positive_position(raw, predicate_type, params))
        positive = raw._compute_predicate()
        result["positive"] = positive
        result["checks"]["positive_true"] = bool(positive["ok"])

        _set_object_pose(raw, _negative_position(raw, predicate_type, params))
        negative = raw._compute_predicate()
        result["negative"] = negative
        result["checks"]["negative_false"] = not bool(negative["ok"])
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        result["traceback"] = traceback.format_exc()
    finally:
        if env is not None:
            env.close()
    result["ok"] = all(result["checks"].values()) and not result["errors"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    task_ids = sorted(task["task_id"] for task in catalog.get("tasks", []))
    if args.limit is not None:
        task_ids = task_ids[: args.limit]
    results = [_check_one(task_id) for task_id in task_ids]
    summary = {
        "checked_count": len(results),
        "ok_count": sum(1 for item in results if item["ok"]),
        "bad_count": sum(1 for item in results if not item["ok"]),
        "results": results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"checked={summary['checked_count']} ok={summary['ok_count']} bad={summary['bad_count']}")
    if summary["bad_count"]:
        for item in results:
            if not item["ok"]:
                print(item["task_id"], item["checks"], item["errors"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
