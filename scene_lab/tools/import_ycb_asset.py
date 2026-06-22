#!/usr/bin/env python
"""Import one local YCB object model into the Scene Lab asset registry."""

from __future__ import annotations

import argparse
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
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="YCB object folder or mesh file")
    parser.add_argument("--asset-id", required=True, help="Stable Scene Lab asset id")
    parser.add_argument("--category", help="Override inferred object category")
    parser.add_argument("--mass", type=float, help="Override object mass in kg")
    parser.add_argument(
        "--size",
        nargs="+",
        type=float,
        help="Override primitive collision size. Box expects 3 values; cylinder/capsule 2; sphere 1.",
    )
    parser.add_argument("--copy", action="store_true", help="Copy mesh instead of symlinking it")
    parser.add_argument(
        "--unit-scale",
        type=float,
        default=1.0,
        help="Multiplier from source mesh units to meters. Official YCB object models are treated as metric by default.",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Missing source path: {source}")

    asset_id = ensure_safe_id(args.asset_id, "asset_id")
    meshes = find_meshes(source)
    mesh = choose_mesh(meshes)
    if mesh is None:
        raise SystemExit(f"No supported mesh found under {source}")

    category = infer_category(source, args.category)
    processed_dir = PROCESSED_ROOT / "ycb" / asset_id
    processed_mesh, conversion_status = prepare_visual_mesh(mesh, processed_dir, copy=args.copy)
    if args.unit_scale != 1.0:
        loaded = trimesh.load(processed_mesh, force="mesh")
        loaded.vertices = np.asarray(loaded.vertices, dtype=float) * float(args.unit_scale)
        if processed_mesh.exists() or processed_mesh.is_symlink():
            processed_mesh.unlink()
        loaded.export(processed_mesh)
    extents = np.asarray(trimesh.load(processed_mesh, force="mesh").extents, dtype=float)
    collision = infer_collision(category, args.size) if args.size else {
        "type": "box",
        "size": (np.maximum(extents, 0.002) / 2.0).tolist(),
        "source": "visual_mesh_aabb",
    }
    mass = infer_mass(category, args.mass)
    calibration = {
        "method": "ycb_metric_mesh_strict",
        "source": "YCB object model mesh units",
        "unit_scale_to_meters": args.unit_scale,
        "extra_uniform_scale": 1.0,
        "processed_extents_m": extents.tolist(),
        "calibrated_extents_m": extents.tolist(),
        "scale_policy": {
            "mode": "ycb_metric_strict",
            "source": "YCB object model mesh vertices",
            "unit_scale_to_meters": args.unit_scale,
            "extra_uniform_scale": 1.0,
        },
    }

    manifest = build_manifest(
        asset_id=asset_id,
        source_benchmark="ycb",
        source_path=source,
        mesh_path=mesh,
        processed_mesh=processed_mesh,
        category=category,
        collision=collision,
        mass=mass,
        status="ready_for_pick_place",
        source_url="https://www.ycbbenchmarks.com/object-models/",
        license_name="YCB Object and Model Set license; verify before redistribution",
        extra={
            "ycb_object_id": source.name if source.is_dir() else source.parent.name,
            "mesh_candidates": [str(p.resolve()) for p in meshes],
            "conversion_status": conversion_status,
            "dexjoco_calibration": calibration,
            "scale_policy": calibration["scale_policy"],
        },
    )
    write_json(processed_dir / "asset_manifest.json", manifest)
    write_json(processed_dir / "collision.json", collision)
    print(processed_dir / "asset_manifest.json")


if __name__ == "__main__":
    main()
