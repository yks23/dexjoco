#!/usr/bin/env python
"""Bulk import local YCB object models into Scene Lab."""

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
    choose_mesh,
    ensure_safe_id,
    find_meshes,
    infer_category,
    infer_mass,
    prepare_visual_mesh,
    write_json,
)
from scene_lab.tools.create_pick_place_candidate import _task_for_asset  # noqa: E402
from scene_lab.tools.generate_mjcf_scene import generate_scene_xml  # noqa: E402


YCB_SOURCE_URL = "https://www.ycbbenchmarks.com/object-models/"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower().replace("-", "_")).strip("_")


def _object_id(source: Path) -> str:
    if source.is_file():
        return source.parent.name
    return source.name


def _asset_id(object_dir: Path) -> str:
    return ensure_safe_id(f"ycb_{_slug(_object_id(object_dir))}", "asset_id")


def _object_dirs(objects_root: Path) -> list[Path]:
    if _is_habitat_ycb_root(objects_root):
        return []
    child_mesh_dirs = [
        child
        for child in objects_root.iterdir()
        if child.is_dir() and re.match(r"^[0-9]+[_-]", child.name) and find_meshes(child)
    ]
    if child_mesh_dirs:
        return sorted(child_mesh_dirs)
    if find_meshes(objects_root):
        return [objects_root]
    return sorted(child for child in objects_root.iterdir() if child.is_dir() and find_meshes(child))


def _is_habitat_ycb_root(path: Path) -> bool:
    return (path / "configs").is_dir() and (path / "meshes").is_dir()


def _habitat_configs(path: Path) -> list[Path]:
    return sorted((path / "configs").glob("*.object_config.json"))


def _habitat_object_id(config_path: Path) -> str:
    return config_path.name.removesuffix(".object_config.json")


def _habitat_asset_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()


def _prefer_uncompressed_glb(path: Path) -> Path:
    candidate = path.with_name(path.name + ".orig")
    return candidate if candidate.exists() else path


def _ycb_mesh(meshes: list[Path]) -> Path | None:
    if not meshes:
        return None
    preferred = (
        "google_16k/textured.obj",
        "google_16k/nontextured.stl",
        "google_16k",
        "tsdf/textured.obj",
        "textured.obj",
        "textured",
        "model.obj",
        "model",
    )
    lowered = [(str(mesh).lower(), mesh) for mesh in meshes]
    for token in preferred:
        for value, mesh in lowered:
            if token in value:
                return mesh
    return choose_mesh(meshes)


def _scale_mesh_in_place(mesh_path: Path, unit_scale: float) -> None:
    if unit_scale == 1.0:
        return
    mesh = trimesh.load(mesh_path, force="mesh")
    mesh.vertices = np.asarray(mesh.vertices, dtype=float) * float(unit_scale)
    if mesh_path.exists() or mesh_path.is_symlink():
        mesh_path.unlink()
    mesh.export(mesh_path)


def _mesh_extents(mesh_path: Path) -> list[float]:
    mesh = trimesh.load(mesh_path, force="mesh")
    return np.asarray(mesh.extents, dtype=float).tolist()


def _collision_from_extents(extents: list[float]) -> dict[str, Any]:
    safe = np.maximum(np.asarray(extents, dtype=float), 0.002)
    return {
        "type": "box",
        "size": (safe / 2.0).tolist(),
        "source": "visual_mesh_aabb",
    }


def _write_candidate(task_id: str, manifest: dict[str, Any], replace: bool) -> bool:
    candidate_dir = REGISTRY / "pending" / task_id
    if candidate_dir.exists():
        if not replace:
            return False
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    task = _task_for_asset(task_id, manifest, None)
    write_json(candidate_dir / "task.json", task)
    write_json(candidate_dir / "asset_manifest.json", manifest)
    (candidate_dir / "scene.xml").write_text(
        generate_scene_xml(task, candidate_dir=candidate_dir),
        encoding="utf-8",
    )
    return True


def import_object(
    object_dir: Path,
    *,
    replace: bool,
    create_candidate: bool,
    copy: bool,
    unit_scale: float,
) -> dict[str, Any]:
    meshes = find_meshes(object_dir)
    mesh = _ycb_mesh(meshes)
    if mesh is None:
        raise FileNotFoundError(f"No supported mesh under {object_dir}")

    asset_id = _asset_id(object_dir)
    processed_dir = PROCESSED_ROOT / "ycb" / asset_id
    if processed_dir.exists() and replace:
        shutil.rmtree(processed_dir)

    processed_mesh, conversion_status = prepare_visual_mesh(mesh, processed_dir, copy=copy)
    _scale_mesh_in_place(processed_mesh, unit_scale)
    extents = _mesh_extents(processed_mesh)
    category = infer_category(object_dir)
    collision = _collision_from_extents(extents)
    mass = infer_mass(category)
    calibration = {
        "method": "ycb_metric_mesh_strict",
        "source": "YCB object model mesh units",
        "unit_scale_to_meters": unit_scale,
        "extra_uniform_scale": 1.0,
        "processed_extents_m": extents,
        "calibrated_extents_m": extents,
        "scale_policy": {
            "mode": "ycb_metric_strict",
            "source": "YCB object model mesh vertices",
            "unit_scale_to_meters": unit_scale,
            "extra_uniform_scale": 1.0,
        },
    }
    manifest = build_manifest(
        asset_id=asset_id,
        source_benchmark="ycb",
        source_path=object_dir,
        mesh_path=mesh,
        processed_mesh=processed_mesh,
        category=category,
        collision=collision,
        mass=mass,
        status="ready_for_pick_place",
        source_url=YCB_SOURCE_URL,
        license_name="YCB Object and Model Set license; verify before redistribution",
        extra={
            "ycb_object_id": _object_id(object_dir),
            "mesh_candidates": [str(path.resolve()) for path in meshes],
            "conversion_status": conversion_status,
            "dexjoco_calibration": calibration,
            "scale_policy": calibration["scale_policy"],
        },
    )
    write_json(processed_dir / "asset_manifest.json", manifest)
    write_json(processed_dir / "collision.json", collision)
    task_id = f"pick_place_{asset_id}"
    candidate_created = False
    if create_candidate:
        candidate_created = _write_candidate(task_id, manifest, replace)
    return {
        "asset_id": asset_id,
        "task_id": task_id,
        "object_id": _object_id(object_dir),
        "category": category,
        "status": manifest["status"],
        "source_mesh": str(mesh.resolve()),
        "visual_mesh": str(processed_mesh.resolve()),
        "conversion_status": conversion_status,
        "candidate_created": candidate_created,
        "unit_scale_to_meters": unit_scale,
        "calibrated_extents_m": extents,
    }


def import_habitat_config(
    config_path: Path,
    *,
    replace: bool,
    create_candidate: bool,
    copy: bool,
    unit_scale: float,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    object_id = _habitat_object_id(config_path)
    render_asset = _prefer_uncompressed_glb(_habitat_asset_path(config_path, config["render_asset"]))
    collision_asset = _habitat_asset_path(config_path, config["collision_asset"])
    if not render_asset.exists():
        raise FileNotFoundError(render_asset)
    asset_id = ensure_safe_id(f"ycb_{_slug(object_id)}", "asset_id")
    processed_dir = PROCESSED_ROOT / "ycb" / asset_id
    if processed_dir.exists() and replace:
        shutil.rmtree(processed_dir)

    processed_mesh, conversion_status = prepare_visual_mesh(render_asset, processed_dir, copy=copy)
    _scale_mesh_in_place(processed_mesh, unit_scale)
    extents = _mesh_extents(processed_mesh)
    category = infer_category(Path(object_id))
    collision = _collision_from_extents(extents)
    mass = infer_mass(category)
    calibration = {
        "method": "ycb_habitat_metric_mesh_strict",
        "source": "Habitat YCB render_asset mesh units",
        "unit_scale_to_meters": unit_scale,
        "extra_uniform_scale": 1.0,
        "processed_extents_m": extents,
        "calibrated_extents_m": extents,
        "scale_policy": {
            "mode": "ycb_metric_strict",
            "source": "Habitat YCB mesh vertices",
            "unit_scale_to_meters": unit_scale,
            "extra_uniform_scale": 1.0,
        },
    }
    manifest = build_manifest(
        asset_id=asset_id,
        source_benchmark="ycb",
        source_path=config_path,
        mesh_path=render_asset,
        processed_mesh=processed_mesh,
        category=category,
        collision=collision,
        mass=mass,
        status="ready_for_pick_place",
        source_url="https://huggingface.co/datasets/ai-habitat/ycb",
        license_name="CC BY 4.0; original YCB Object and Model Set source",
        extra={
            "ycb_object_id": object_id,
            "habitat_config": str(config_path.resolve()),
            "habitat_render_asset": str(render_asset.resolve()),
            "source_collision_mesh": str(collision_asset.resolve()) if collision_asset.exists() else None,
            "friction_coefficient": config.get("friction_coefficient"),
            "conversion_status": conversion_status,
            "dexjoco_calibration": calibration,
            "scale_policy": calibration["scale_policy"],
        },
    )
    write_json(processed_dir / "asset_manifest.json", manifest)
    write_json(processed_dir / "collision.json", collision)
    task_id = f"pick_place_{asset_id}"
    candidate_created = False
    if create_candidate:
        candidate_created = _write_candidate(task_id, manifest, replace)
    return {
        "asset_id": asset_id,
        "task_id": task_id,
        "object_id": object_id,
        "category": category,
        "status": manifest["status"],
        "source_mesh": str(render_asset.resolve()),
        "source_collision_mesh": str(collision_asset.resolve()) if collision_asset.exists() else None,
        "visual_mesh": str(processed_mesh.resolve()),
        "conversion_status": conversion_status,
        "candidate_created": candidate_created,
        "unit_scale_to_meters": unit_scale,
        "calibrated_extents_m": extents,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects-root", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--no-candidates", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--unit-scale",
        type=float,
        default=1.0,
        help="Multiplier from source mesh units to meters. Official YCB object models are treated as metric by default.",
    )
    args = parser.parse_args()

    objects_root = args.objects_root.expanduser().resolve()
    if not objects_root.exists():
        raise SystemExit(f"Missing YCB objects root: {objects_root}")
    if _is_habitat_ycb_root(objects_root):
        sources = _habitat_configs(objects_root)
        if args.limit:
            sources = sources[: args.limit]
        results = [
            import_habitat_config(
                config_path,
                replace=args.replace,
                create_candidate=not args.no_candidates,
                copy=args.copy,
                unit_scale=args.unit_scale,
            )
            for config_path in sources
        ]
    else:
        sources = _object_dirs(objects_root)
        if args.limit:
            sources = sources[: args.limit]
        results = [
            import_object(
                object_dir,
                replace=args.replace,
                create_candidate=not args.no_candidates,
                copy=args.copy,
                unit_scale=args.unit_scale,
            )
            for object_dir in sources
        ]
    summary = {
        "objects_root": str(objects_root),
        "object_count": len(sources),
        "asset_count": len(results),
        "ready_for_pick_place": sum(r["status"] == "ready_for_pick_place" for r in results),
        "candidate_count": sum(bool(r["candidate_created"]) for r in results),
        "scale_mode": "ycb_metric_strict",
        "unit_scale_to_meters": args.unit_scale,
        "results": results,
    }
    out = REGISTRY / "pending" / "ycb_bulk_import_summary.json"
    write_json(out, summary)
    print(out)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
