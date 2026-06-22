#!/usr/bin/env python
"""Create a pick/place Scene Lab candidate from a processed external asset."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import (  # noqa: E402
    REGISTRY,
    ensure_safe_id,
    load_asset_manifest,
    write_json,
)
from scene_lab.tools.generate_mjcf_scene import generate_scene_xml  # noqa: E402


def _object_height(collision: dict) -> float:
    geom_type = collision.get("type", "box")
    size = collision.get("size") or [0.06, 0.04, 0.05]
    if geom_type == "mesh":
        return _object_height(collision.get("fallback") or {})
    if geom_type == "box" and len(size) >= 3:
        return float(size[2])
    if geom_type in ("cylinder", "capsule") and len(size) >= 2:
        return float(size[1])
    if geom_type == "sphere" and size:
        return float(size[0])
    return 0.05


def _task_for_asset(task_id: str, manifest: dict, instruction: str | None) -> dict:
    asset_id = manifest["asset_id"]
    source = manifest["source_benchmark"]
    category = manifest.get("category", "object")
    object_name = "object"
    table_top_z = 0.92
    obj_z = table_top_z + _object_height(manifest.get("collision", {})) + 0.01

    return {
        "task_id": task_id,
        "task_name": "pick_place_asset",
        "task_family": "pick_place_ycb" if source == "ycb" else "pick_place_robotwin",
        "instruction": instruction
        or f"Pick up the {source} {category.replace('_', ' ')} and place it on the green target area.",
        "robot": {
            "name": "panda_allegro_right",
            "arm": "Franka Panda",
            "hand": "Wonik Allegro Hand V3 right",
            "dof": 23,
        },
        "simulator": {
            "backend": "mujoco",
            "entrypoint": {
                "xml_path": "scene.xml",
                "env_class": "scene_lab.runtime.generated_scene_env.PandaGeneratedSceneEnv",
            },
        },
        "objects": [
            {
                "name": object_name,
                "role": "manipulated_object",
                "type": "external_asset",
                "asset_ref": asset_id,
                "asset_manifest": "asset_manifest.json",
                "source_benchmark": source,
                "category": category,
                "pose": [-0.32, -0.18, obj_z, 1.0, 0.0, 0.0, 0.0],
                "size": [0.12, 0.08, max(0.04, _object_height(manifest.get("collision", {})) * 2)],
                "collision": manifest.get("collision", {}),
                "material": "external visual mesh with primitive collision",
            },
            {
                "name": "goal_zone",
                "role": "target_region",
                "type": "flat_box",
                "pose": [0.12, 0.22, 0.925],
                "size": [0.26, 0.20, 0.008],
                "material": "translucent green",
            },
            {
                "name": "table",
                "role": "support_surface",
                "type": "box_table",
                "pose": [-0.15, 0.0, 0.89],
                "size": [0.90, 1.70, 0.06],
            },
        ],
        "success_condition": {
            "type": "object_in_region",
            "object": object_name,
            "target": "goal_center",
            "radius": 0.08,
            "min_z": 0.90,
            "description": "Success when the object center is in the target region and remains above the table.",
            "params": {"xy_radius": 0.08, "min_z": 0.90},
        },
        "static_review": {
            "must_be_visible": [object_name, "goal_zone", "robot hand", "table"],
            "must_be_reachable": [object_name, "goal_zone"],
            "common_failure_modes": [
                "External mesh scale is too large or too small.",
                "Primitive collision does not match the visual mesh.",
                "Object starts intersecting the table.",
                "Target is outside reachable workspace.",
            ],
        },
        "generator": {
            "kind": "asset_pick_place_factory",
            "version": 1,
            "source_benchmark": source,
            "asset_id": asset_id,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--instruction")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    task_id = ensure_safe_id(args.task_id, "task_id")
    _, manifest = load_asset_manifest(args.asset_id)
    if manifest.get("status") != "ready_for_pick_place":
        raise SystemExit(
            f"Asset {args.asset_id} has status={manifest.get('status')}; "
            "only ready_for_pick_place assets can generate pick/place candidates."
        )

    candidate_dir = REGISTRY / "pending" / task_id
    if candidate_dir.exists():
        if not args.replace:
            raise SystemExit(f"{candidate_dir} already exists; pass --replace")
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)

    task = _task_for_asset(task_id, manifest, args.instruction)
    write_json(candidate_dir / "task.json", task)
    write_json(candidate_dir / "asset_manifest.json", manifest)
    (candidate_dir / "scene.xml").write_text(
        generate_scene_xml(task, candidate_dir=candidate_dir),
        encoding="utf-8",
    )
    print(candidate_dir)


if __name__ == "__main__":
    main()
