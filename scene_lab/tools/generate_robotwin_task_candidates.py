#!/usr/bin/env python
"""Generate Scene Lab pending candidates from parsed RoboTwin task specs."""

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

from scene_lab.asset_pipeline import ensure_safe_id, read_json, write_json  # noqa: E402
from scene_lab.tools.generate_mjcf_scene import generate_scene_xml  # noqa: E402

TABLE_TOP_Z = 0.92


def _safe_task_id(value: str) -> str:
    return ensure_safe_id(value.lower().replace(" ", "_"), "task_id")


def _manifest_index(assets_root: Path) -> tuple[dict[str, tuple[Path, dict[str, Any]]], dict[str, list[tuple[Path, dict[str, Any]]]]]:
    by_id: dict[str, tuple[Path, dict[str, Any]]] = {}
    by_model: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path in sorted(assets_root.glob("*/asset_manifest.json")):
        manifest = read_json(path)
        asset_id = manifest.get("asset_id")
        if not asset_id:
            continue
        item = (path, manifest)
        by_id[asset_id] = item
        source_path = Path(manifest.get("source_path", ""))
        model = source_path.name.replace("-", "_")
        if model:
            by_model.setdefault(model, []).append(item)
    return by_id, by_model


def _height_from_manifest(manifest: dict[str, Any] | None) -> float:
    if not manifest:
        return 0.05
    calibration = manifest.get("dexjoco_calibration") or {}
    extents = calibration.get("calibrated_extents_m")
    if isinstance(extents, list) and len(extents) >= 3:
        return max(0.015, float(extents[2]))
    collision = manifest.get("collision", {})
    size = collision.get("size")
    if isinstance(size, list):
        if collision.get("type") == "box" and len(size) >= 3:
            return max(0.015, float(size[2]) * 2)
        if collision.get("type") in ("cylinder", "capsule") and len(size) >= 2:
            return max(0.015, float(size[1]) * 2)
        if collision.get("type") == "sphere" and size:
            return max(0.015, float(size[0]) * 2)
    return 0.08


def _size_from_manifest(manifest: dict[str, Any] | None) -> list[float]:
    if not manifest:
        return [0.08, 0.08, 0.08]
    extents = (manifest.get("dexjoco_calibration") or {}).get("calibrated_extents_m")
    if isinstance(extents, list) and len(extents) >= 3:
        return [max(0.02, float(v)) for v in extents[:3]]
    height = _height_from_manifest(manifest)
    return [0.08, 0.08, height]


def _candidate_manifests(
    spec: dict[str, Any],
    by_id: dict[str, tuple[Path, dict[str, Any]]],
    by_model: dict[str, list[tuple[Path, dict[str, Any]]]],
    max_count: int,
) -> list[tuple[Path, dict[str, Any]]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()

    def add(item: tuple[Path, dict[str, Any]] | None) -> None:
        if not item:
            return
        asset_id = item[1].get("asset_id")
        if not asset_id or asset_id in seen:
            return
        if item[1].get("status") != "ready_for_pick_place":
            return
        seen.add(asset_id)
        candidates.append(item)

    for asset in spec.get("assets", []):
        for asset_id in asset.get("asset_ids", []):
            add(by_id.get(asset_id))
        modelname = asset.get("modelname")
        if isinstance(modelname, str) and modelname != "dynamic":
            model_key = modelname.replace("-", "_")
            for item in by_model.get(model_key, [])[:max_count]:
                add(item)

    for mention in spec.get("object_mentions", []):
        model_key = mention.replace("-", "_")
        for item in by_model.get(model_key, [])[:max_count]:
            add(item)

    return candidates[:max_count]


def _has_procedural_box(spec: dict[str, Any]) -> bool:
    return any(asset.get("kind") == "procedural_box" for asset in spec.get("assets", []))


def _success_condition(spec: dict[str, Any], object_name: str) -> dict[str, Any]:
    predicate = spec.get("success_predicate") or {}
    predicate_type = predicate.get("type", "object_in_region")
    params = dict(predicate.get("params", {}))
    if predicate_type in {
        "object_near_object",
        "object_contact_object",
        "tool_contact_target",
        "object_pose_relative_to_object",
        "objects_stacked",
    }:
        predicate_type = "object_in_region"
        params.setdefault("xy_radius", 0.08)
        params.setdefault("min_z", 0.90)
    if predicate_type == "articulation_joint_threshold":
        predicate_type = "object_near_site"
        params.setdefault("radius", 0.08)
    if predicate_type == "object_lifted":
        params.setdefault("min_z", 0.98)
    else:
        params.setdefault("xy_radius", params.get("radius", 0.08))
        params.setdefault("min_z", 0.90)
    return {
        "type": predicate_type,
        "object": object_name,
        "target": "goal_center",
        "radius": float(params.get("radius", params.get("xy_radius", 0.08))),
        "min_z": float(params.get("min_z", 0.90)),
        "params": params,
        "source_predicate": predicate,
        "description": "Transferred from RoboTwin check_success where executable in the current Scene Lab runtime.",
    }


def _task_json(
    *,
    task_id: str,
    spec: dict[str, Any],
    manifest: dict[str, Any] | None,
    procedural_box: bool,
) -> dict[str, Any]:
    category = manifest.get("category", "box") if manifest else "procedural_box"
    object_name = "object"
    object_size = _size_from_manifest(manifest)
    object_height = object_size[2]
    object_collision = manifest.get("collision", {}) if manifest else {"type": "box", "size": [0.035, 0.035, 0.035]}
    return {
        "task_id": task_id,
        "task_name": spec["source_task"],
        "task_family": f"robotwin_{spec.get('skill_family', 'unclassified')}",
        "instruction": f"RoboTwin transfer: {spec.get('instruction_hint', spec['source_task'].replace('_', ' '))}.",
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
                "type": "external_asset" if manifest else "procedural_box",
                "asset_ref": manifest.get("asset_id") if manifest else None,
                "asset_manifest": "asset_manifest.json" if manifest else None,
                "source_benchmark": "robotwin",
                "category": category,
                "pose": [-0.32, -0.18, TABLE_TOP_Z + object_height / 2.0 + 0.01, 1.0, 0.0, 0.0, 0.0],
                "size": object_size,
                "collision": object_collision,
                "material": "textured visual mesh with mesh collision" if manifest else "procedural box",
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
        "success_condition": _success_condition(spec, object_name),
        "static_review": {
            "must_be_visible": [object_name, "goal_zone", "robot hand", "table"],
            "must_be_reachable": [object_name, "goal_zone"],
            "common_failure_modes": [
                "RoboTwin source task has multiple objects but current generated runtime previews one primary object.",
                "Transferred predicate may be a conservative approximation of RoboTwin check_success.",
                "Articulated or bimanual behavior is registered in transfer_report instead of executed here.",
            ],
        },
        "generator": {
            "kind": "robotwin_task_transfer",
            "version": 1,
            "source_task": spec["source_task"],
            "source_file": spec.get("source_file"),
            "skill_family": spec.get("skill_family"),
            "transfer_status": spec.get("transfer_status"),
            "asset_id": manifest.get("asset_id") if manifest else "procedural_box",
            "procedural_box": procedural_box,
        },
    }


def _copy_if_exists(source: Path | None, dest: Path) -> None:
    if source and source.exists():
        shutil.copy2(source, dest)


def _write_candidate(
    candidate_dir: Path,
    spec: dict[str, Any],
    manifest_path: Path | None,
    manifest: dict[str, Any] | None,
    replace: bool,
) -> dict[str, Any]:
    if candidate_dir.exists():
        if not replace:
            return {"candidate_dir": str(candidate_dir), "status": "skipped_existing"}
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    task_id = candidate_dir.name
    task = _task_json(
        task_id=task_id,
        spec=spec,
        manifest=manifest,
        procedural_box=manifest is None,
    )
    write_json(candidate_dir / "task.json", task)
    if manifest and manifest_path:
        write_json(candidate_dir / "asset_manifest.json", manifest)
        _copy_if_exists(manifest_path.parent / "physical_material.json", candidate_dir / "physical_material.json")
        _copy_if_exists(manifest_path.parent / "modeling_report.json", candidate_dir / "modeling_report.json")
    (candidate_dir / "scene.xml").write_text(
        generate_scene_xml(task, candidate_dir=candidate_dir),
        encoding="utf-8",
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_task": spec["source_task"],
        "skill_family": spec.get("skill_family"),
        "transfer_status": "executable",
        "source_transfer_status": spec.get("transfer_status"),
        "primary_asset": manifest.get("asset_id") if manifest else "procedural_box",
        "source_assets": spec.get("assets", []),
        "unsupported_features": spec.get("unsupported_features", []),
        "losses": [
            "RoboTwin motion trajectory is not transferred; only task geometry, asset identity, and predicate intent are transferred.",
            "Generated runtime currently previews one primary manipulated object plus target region.",
        ],
    }
    write_json(candidate_dir / "transfer_report.json", report)
    return {"candidate_dir": str(candidate_dir), "status": "generated"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-candidates-per-task", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    del args.seed  # Deterministic sorting is enough for this static transfer.
    specs = read_json(args.spec)
    by_id, by_model = _manifest_index(args.assets)
    generated: list[dict[str, Any]] = []
    registered: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for spec in specs.get("tasks", []):
        source_task = spec["source_task"]
        if spec.get("transfer_status") != "executable":
            registered.append(
                {
                    "source_task": source_task,
                    "status": spec.get("transfer_status"),
                    "skill_family": spec.get("skill_family"),
                    "unsupported_features": spec.get("unsupported_features", []),
                    "reason": "Task spec parsed but not generated because current Scene Lab runtime cannot faithfully execute it.",
                }
            )
            continue
        manifests = _candidate_manifests(spec, by_id, by_model, args.max_candidates_per_task)
        if not manifests and _has_procedural_box(spec):
            task_id = _safe_task_id(f"robotwin_{source_task}_box_demo")
            generated.append(
                _write_candidate(args.out / task_id, spec, None, None, replace=args.replace)
            )
            continue
        if not manifests:
            failed.append(
                {
                    "source_task": source_task,
                    "status": "failed",
                    "reason": "No processed ready_for_pick_place RoboTwin asset matched parsed task assets.",
                    "assets": spec.get("assets", []),
                    "object_mentions": spec.get("object_mentions", []),
                }
            )
            continue
        for index, (manifest_path, manifest) in enumerate(manifests):
            suffix = manifest.get("asset_id", f"asset_{index}").replace("robotwin_", "")
            task_id = _safe_task_id(f"robotwin_{source_task}_{suffix}")
            generated.append(
                _write_candidate(args.out / task_id, spec, manifest_path, manifest, replace=args.replace)
            )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "spec": str(args.spec),
        "assets": str(args.assets),
        "out": str(args.out),
        "max_candidates_per_task": args.max_candidates_per_task,
        "generated_count": sum(1 for item in generated if item["status"] == "generated"),
        "skipped_existing_count": sum(1 for item in generated if item["status"] == "skipped_existing"),
        "registered_spec_count": len(registered),
        "failed_count": len(failed),
        "generated": generated,
        "registered_specs": registered,
        "failed": failed,
    }
    summary_path = args.out.parent / "robotwin_task_generation_summary.json"
    write_json(summary_path, summary)
    print(summary_path)


if __name__ == "__main__":
    main()
