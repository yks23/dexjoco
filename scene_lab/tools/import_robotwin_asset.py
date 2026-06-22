#!/usr/bin/env python
"""Import one local RoboTwin-OD object into the Scene Lab asset registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import (  # noqa: E402
    PROCESSED_ROOT,
    build_manifest,
    choose_mesh,
    ensure_safe_id,
    find_meshes,
    infer_category,
    infer_collision,
    infer_mass,
    prepare_visual_mesh,
    robotwin_model_data_for_mesh,
    write_json,
)


ARTICULATED_TOKENS = (
    "partnet",
    "mobility",
    "articulated",
    "joint",
    "link_",
    "urdf",
    "drawer",
    "door",
    "cabinet",
)


def _metadata_files(source: Path) -> list[Path]:
    if source.is_file():
        return []
    return sorted(
        p
        for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in (".json", ".yaml", ".yml")
    )


def _looks_articulated(source: Path, metadata_paths: list[Path]) -> bool:
    haystack = " ".join([str(source).lower(), *(str(p).lower() for p in metadata_paths)])
    if any(token in haystack for token in ARTICULATED_TOKENS):
        return True
    for path in metadata_paths[:8]:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()[:8000]
        if any(token in text for token in ("joint", "articulated", "partnet", "mobility")):
            return True
    return False


def _read_small_metadata(metadata_paths: list[Path]) -> dict:
    merged = {}
    for path in metadata_paths[:5]:
        if path.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            merged[path.name] = data
    return merged


def _choose_robotwin_visual_mesh(source: Path) -> Path | None:
    visual_dir = source / "visual"
    if visual_dir.is_dir():
        visual_meshes = find_meshes(visual_dir)
        chosen = choose_mesh(visual_meshes)
        if chosen is not None:
            return chosen
    return choose_mesh(find_meshes(source))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="RoboTwin object folder or mesh file")
    parser.add_argument("--asset-id", required=True, help="Stable Scene Lab asset id")
    parser.add_argument("--category", help="Override inferred object category")
    parser.add_argument("--mass", type=float, help="Override object mass in kg")
    parser.add_argument("--size", nargs="+", type=float, help="Override primitive collision size")
    parser.add_argument("--copy", action="store_true", help="Copy mesh instead of symlinking it")
    parser.add_argument(
        "--force-ready",
        action="store_true",
        help="Mark as ready_for_pick_place even if the path/metadata looks articulated",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Missing source path: {source}")

    asset_id = ensure_safe_id(args.asset_id, "asset_id")
    meshes = find_meshes(source)
    mesh = _choose_robotwin_visual_mesh(source)
    if mesh is None:
        raise SystemExit(f"No supported mesh found under {source}")

    metadata_paths = _metadata_files(source)
    articulated = _looks_articulated(source, metadata_paths)
    status = "ready_for_pick_place" if args.force_ready or not articulated else "registered_only"
    category = infer_category(source, args.category)
    processed_dir = PROCESSED_ROOT / "robotwin" / asset_id
    model_data = robotwin_model_data_for_mesh(mesh)
    processed_mesh, conversion_status = prepare_visual_mesh(
        mesh,
        processed_dir,
        copy=args.copy,
        model_data=model_data,
    )
    mesh_extents = np.asarray(trimesh.load(processed_mesh, force="mesh").extents, dtype=float)
    collision = infer_collision(category, args.size)
    mass = infer_mass(category, args.mass)

    manifest = build_manifest(
        asset_id=asset_id,
        source_benchmark="robotwin",
        source_path=source,
        mesh_path=mesh,
        processed_mesh=processed_mesh,
        category=category,
        collision=collision,
        mass=mass,
        status=status,
        source_url="https://robotwin-platform.github.io/doc/objects/index.html",
        license_name="RoboTwin-OD license/source terms; verify before redistribution",
        extra={
            "robotwin_object_id": source.name if source.is_dir() else source.parent.name,
            "is_articulated_candidate": articulated,
            "mesh_candidates": [str(p.resolve()) for p in meshes],
            "metadata_files": [str(p.resolve()) for p in metadata_paths],
            "metadata_preview": _read_small_metadata(metadata_paths),
            "conversion_status": conversion_status,
            "model_data": {
                key: model_data[key]
                for key in ("center", "extents", "scale", "stable")
                if key in model_data
            },
            "dexjoco_calibration": {
                "method": "robotwin_model_data_strict",
                "source": "RoboTwin model_data*.json extents and scale",
                "extra_uniform_scale": 1.0,
                "processed_extents_m": mesh_extents.tolist(),
                "calibrated_extents_m": mesh_extents.tolist(),
                "scale_policy": {
                    "mode": "robotwin_strict",
                    "source": "RoboTwin model_data*.json",
                    "model_data_scale": model_data.get("scale"),
                    "extra_uniform_scale": 1.0,
                },
            },
            "scale_policy": {
                "mode": "robotwin_strict",
                "source": "RoboTwin model_data*.json",
                "model_data_scale": model_data.get("scale"),
                "extra_uniform_scale": 1.0,
            },
        },
    )
    write_json(processed_dir / "asset_manifest.json", manifest)
    write_json(processed_dir / "collision.json", collision)
    print(processed_dir / "asset_manifest.json")


if __name__ == "__main__":
    main()
