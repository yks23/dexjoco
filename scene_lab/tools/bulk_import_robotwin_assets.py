#!/usr/bin/env python
"""Bulk import RoboTwin-OD visual assets into Scene Lab."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import (  # noqa: E402
    PROCESSED_ROOT,
    REGISTRY,
    build_manifest,
    ensure_safe_id,
    prepare_visual_mesh,
    robotwin_model_data_for_mesh,
    write_json,
)
from scene_lab.tools.create_pick_place_candidate import _task_for_asset  # noqa: E402
from scene_lab.tools.generate_mjcf_scene import generate_scene_xml  # noqa: E402


FIXTURE_TOKENS = (
    "cabinet",
    "bookcase",
    "rack",
    "laptop",
    "oven",
    "microwave",
    "switch",
    "screen",
    "fan",
    "displaystand",
)
ARTICULATED_TOKENS = ("kettle", "door", "drawer", "partnet", "mobility")

TARGET_MAX_BY_TOKEN = {
    "bottle": 0.22,
    "olive": 0.23,
    "soy": 0.22,
    "vinegar": 0.22,
    "shampoo": 0.20,
    "pillbottle": 0.10,
    "bowl": 0.16,
    "plate": 0.20,
    "cup": 0.10,
    "mug": 0.11,
    "glass": 0.12,
    "apple": 0.075,
    "fruit": 0.08,
    "hamburg": 0.09,
    "bread": 0.16,
    "fries": 0.11,
    "box": 0.18,
    "tissue": 0.13,
    "tray": 0.30,
    "coaster": 0.10,
    "hammer": 0.18,
    "drill": 0.18,
    "screwdriver": 0.18,
    "fork": 0.18,
    "knife": 0.18,
    "pen": 0.16,
    "microphone": 0.16,
    "scanner": 0.16,
    "mouse": 0.10,
    "phone": 0.15,
    "calculator": 0.16,
    "stapler": 0.14,
    "shoe": 0.26,
    "basket": 0.24,
    "pot": 0.16,
    "plant": 0.16,
    "block": 0.08,
    "can": 0.11,
    "battery": 0.08,
    "bell": 0.10,
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower().replace("-", "_")).strip("_")


def _category(object_dir: Path) -> str:
    return re.sub(r"^[0-9]+[_-]*", "", object_dir.name).replace("-", "_")


def _target_max(category: str) -> float:
    lower = category.lower()
    for token, value in TARGET_MAX_BY_TOKEN.items():
        if token in lower:
            return value
    return 0.14


def _status(category: str, model_data: dict[str, Any]) -> str:
    lower = category.lower()
    if any(token in lower for token in ARTICULATED_TOKENS):
        return "registered_only"
    if any(token in lower for token in FIXTURE_TOKENS):
        return "registered_only"
    if model_data.get("stable") is False:
        return "registered_only"
    return "ready_for_pick_place"


def _measure_mesh(mesh_path: Path) -> dict[str, Any]:
    mesh = trimesh.load(mesh_path, force="mesh")
    extents = np.asarray(mesh.extents, dtype=float)
    return {
        "method": "robotwin_model_data_strict",
        "source": "RoboTwin model_data*.json extents and scale",
        "extra_uniform_scale": 1.0,
        "processed_extents_m": extents.tolist(),
        "calibrated_extents_m": extents.tolist(),
    }


def _calibrate_mesh(mesh_path: Path, target_max: float) -> dict[str, Any]:
    mesh = trimesh.load(mesh_path, force="mesh")
    before = np.asarray(mesh.extents, dtype=float)
    max_before = float(before.max()) if len(before) else 0.0
    factor = target_max / max_before if max_before > 0 else 1.0
    vertices = np.asarray(mesh.vertices, dtype=float)
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    mesh.vertices = (vertices - center) * factor
    mesh.export(mesh_path)
    after = np.asarray(mesh.extents, dtype=float)
    return {
        "method": "per_asset_target_max_extent",
        "raw_processed_extents_m": before.tolist(),
        "target_max_extent_m": target_max,
        "uniform_scale_factor": factor,
        "calibrated_extents_m": after.tolist(),
    }


def _visual_meshes(objects_root: Path) -> list[Path]:
    return sorted(objects_root.glob("*/visual/*.glb"))


def _candidate_id(asset_id: str) -> str:
    return f"pick_place_{asset_id}"


def _write_candidate(task_id: str, manifest: dict[str, Any], replace: bool) -> None:
    candidate_dir = REGISTRY / "pending" / task_id
    if candidate_dir.exists():
        if not replace:
            return
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    task = _task_for_asset(task_id, manifest, None)
    write_json(candidate_dir / "task.json", task)
    write_json(candidate_dir / "asset_manifest.json", manifest)
    (candidate_dir / "scene.xml").write_text(
        generate_scene_xml(task, candidate_dir=candidate_dir),
        encoding="utf-8",
    )


def import_mesh(
    mesh_path: Path,
    replace: bool,
    create_candidate: bool,
    scale_mode: str,
) -> dict[str, Any]:
    object_dir = mesh_path.parents[1]
    category = _category(object_dir)
    variant = mesh_path.stem
    asset_id = ensure_safe_id(f"robotwin_{_slug(object_dir.name)}_{_slug(variant)}", "asset_id")
    processed_dir = PROCESSED_ROOT / "robotwin" / asset_id
    if processed_dir.exists() and replace:
        shutil.rmtree(processed_dir)
    model_data = robotwin_model_data_for_mesh(mesh_path)
    processed_mesh, conversion_status = prepare_visual_mesh(
        mesh_path,
        processed_dir,
        copy=False,
        model_data=model_data,
    )
    target_max = _target_max(category)
    if scale_mode == "category_target_max":
        calibration = _calibrate_mesh(processed_mesh, target_max)
    else:
        calibration = _measure_mesh(processed_mesh)
    scale_policy = {
        "mode": scale_mode,
        "source": "RoboTwin model_data*.json",
        "model_data_scale": model_data.get("scale"),
        "extra_uniform_scale": calibration.get("uniform_scale_factor", 1.0),
    }
    calibration["scale_policy"] = scale_policy
    extents = np.asarray(calibration["calibrated_extents_m"], dtype=float)
    status = _status(category, model_data)
    collision = {"type": "box", "size": (extents / 2.0).tolist()}
    manifest = build_manifest(
        asset_id=asset_id,
        source_benchmark="robotwin",
        source_path=object_dir,
        mesh_path=mesh_path,
        processed_mesh=processed_mesh,
        category=category,
        collision=collision,
        mass=0.15,
        status=status,
        source_url="https://robotwin-platform.github.io/doc/objects/index.html",
        license_name="RoboTwin-OD license/source terms; verify before redistribution",
        extra={
            "robotwin_object_id": object_dir.name,
            "robotwin_variant": variant,
            "conversion_status": conversion_status,
            "model_data": {
                key: model_data[key]
                for key in ("center", "extents", "scale", "stable")
                if key in model_data
            },
            "dexjoco_calibration": calibration,
            "scale_policy": scale_policy,
        },
    )
    if status != "ready_for_pick_place":
        manifest["affordances"] = []
    write_json(processed_dir / "asset_manifest.json", manifest)
    write_json(processed_dir / "collision.json", collision)
    candidate_created = False
    if create_candidate and status == "ready_for_pick_place":
        _write_candidate(_candidate_id(asset_id), manifest, replace=replace)
        candidate_created = True
    return {
        "asset_id": asset_id,
        "object_id": object_dir.name,
        "variant": variant,
        "category": category,
        "status": status,
        "candidate_created": candidate_created,
        "target_max_extent_m": target_max if scale_mode == "category_target_max" else None,
        "calibrated_extents_m": calibration["calibrated_extents_m"],
        "scale_mode": scale_mode,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--objects-root",
        type=Path,
        default=ROOT / "third_party" / "assets" / "robotwin" / "assets" / "objects",
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--no-candidates", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--scale-mode",
        choices=("robotwin_strict", "category_target_max"),
        default="robotwin_strict",
        help=(
            "robotwin_strict preserves RoboTwin model_data*.json scale exactly; "
            "category_target_max applies the older DexJoCo review target_max normalization."
        ),
    )
    args = parser.parse_args()

    meshes = _visual_meshes(args.objects_root)
    if args.limit:
        meshes = meshes[: args.limit]
    results = [
        import_mesh(
            mesh,
            replace=args.replace,
            create_candidate=not args.no_candidates,
            scale_mode=args.scale_mode,
        )
        for mesh in meshes
    ]
    summary = {
        "objects_root": str(args.objects_root.resolve()),
        "visual_mesh_count": len(meshes),
        "asset_count": len(results),
        "ready_for_pick_place": sum(r["status"] == "ready_for_pick_place" for r in results),
        "registered_only": sum(r["status"] != "ready_for_pick_place" for r in results),
        "candidate_count": sum(bool(r["candidate_created"]) for r in results),
        "scale_mode": args.scale_mode,
        "results": results,
    }
    out = REGISTRY / "pending" / "robotwin_bulk_import_summary.json"
    write_json(out, summary)
    print(out)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
