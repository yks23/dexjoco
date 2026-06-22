#!/usr/bin/env python
"""Build DexJoCo/MuJoCo mesh collision metadata for processed assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import PROCESSED_ROOT, REGISTRY, load_asset_manifest, write_json  # noqa: E402


def _source_collision_mesh(manifest: dict) -> Path | None:
    if manifest.get("source_benchmark") != "robotwin":
        return None
    source_path = Path(str(manifest.get("source_path") or ""))
    variant = str(manifest.get("robotwin_variant") or Path(str(manifest.get("source_mesh") or "")).stem)
    candidate = source_path / "collision" / f"{variant}.glb"
    return candidate if candidate.exists() else None


def _load_as_mesh(path: Path):
    import trimesh

    loaded = trimesh.load(path, force="scene")
    return loaded.dump(concatenate=True) if hasattr(loaded, "dump") else loaded


def _load_mesh_parts(path: Path) -> list:
    import trimesh

    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        parts = loaded.dump(concatenate=False)
    else:
        parts = [loaded]
    return [part for part in parts if len(getattr(part, "vertices", [])) and len(getattr(part, "faces", []))]


def _apply_robotwin_transforms(meshes: list, manifest: dict) -> None:
    model_data = manifest.get("model_data") or {}
    center = model_data.get("center")
    scale = model_data.get("scale")
    all_vertices = []
    for mesh in meshes:
        vertices = np.asarray(mesh.vertices, dtype=float)
        if center and scale:
            vertices = vertices - np.asarray(center, dtype=float)
            vertices = vertices * np.asarray(scale, dtype=float)
            vertices = vertices[:, [0, 2, 1]]
            vertices[:, 1] *= -1
        all_vertices.append(vertices)
        mesh.vertices = vertices
    stacked = np.vstack(all_vertices)
    bbox_center = (stacked.min(axis=0) + stacked.max(axis=0)) / 2.0
    factor = float((manifest.get("dexjoco_calibration") or {}).get("uniform_scale_factor") or 1.0)
    for mesh in meshes:
        mesh.vertices = (np.asarray(mesh.vertices, dtype=float) - bbox_center) * factor


def _collision_safe_mesh(mesh, min_thickness: float = 0.001):
    import trimesh

    extents = np.asarray(mesh.extents, dtype=float)
    if not np.all(np.isfinite(extents)) or len(extents) != 3:
        return mesh, "unchanged"
    rank = int(np.count_nonzero(extents > min_thickness * 0.25))
    volume = abs(float(getattr(mesh, "volume", 0.0) or 0.0))
    face_count = int(len(getattr(mesh, "faces", [])))
    if rank >= 3 and extents.min() >= min_thickness * 0.25 and volume > 1e-12 and face_count >= 4:
        return mesh, "unchanged"

    safe_extents = np.maximum(extents, min_thickness)
    center = np.asarray(mesh.bounds, dtype=float).mean(axis=0)
    repaired = trimesh.creation.box(
        extents=safe_extents,
        transform=trimesh.transformations.translation_matrix(center),
    )
    return repaired, "aabb_min_thickness"


def _collision_mesh_for_manifest(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    visual_mesh = Path(manifest["visual_mesh"])
    if not visual_mesh.exists():
        raise FileNotFoundError(visual_mesh)

    collision_dir = manifest_path.parent / "collision"
    collision_dir.mkdir(parents=True, exist_ok=True)
    source_collision = _source_collision_mesh(manifest)
    source_kind = "processed_visual_mesh"
    raw_source_mesh = Path(str(manifest.get("source_mesh") or ""))
    source_mesh = raw_source_mesh if raw_source_mesh.exists() else visual_mesh
    collision_meshes = []

    try:
        import trimesh

        if source_collision is not None:
            source_kind = "robotwin_collision_mesh"
            source_mesh = source_collision
        elif source_mesh.suffix.lower() == ".glb":
            source_kind = "visual_scene_component_meshes"
        parts = _load_mesh_parts(source_mesh)
        if manifest.get("source_benchmark") == "robotwin" and (
            source_collision is not None or source_mesh.suffix.lower() == ".glb"
        ):
            _apply_robotwin_transforms(parts, manifest)
        for index, mesh in enumerate(parts):
            mesh, repair = _collision_safe_mesh(mesh)
            mesh.visual = trimesh.visual.ColorVisuals(mesh)
            collision_mesh = collision_dir / f"{visual_mesh.stem}_collision_{index:03d}.obj"
            mesh.export(collision_mesh)
            collision_meshes.append(
                {
                    "name": f"collision_{index}",
                    "path": str(collision_mesh.resolve()),
                    "geom_type": "mesh",
                    "repair": repair,
                }
            )
    except Exception:
        collision_mesh = collision_dir / f"{visual_mesh.stem}_collision_000.obj"
        if collision_mesh.exists() or collision_mesh.is_symlink():
            collision_mesh.unlink()
        collision_mesh.symlink_to(visual_mesh.resolve())
        collision_meshes = [
            {
                "name": "collision_0",
                "path": str(collision_mesh.resolve()),
                "geom_type": "mesh",
                "repair": "symlink_fallback",
            }
        ]

    collision_manifest = {
        "mode": "mujoco_mesh_collision",
        "source": source_kind,
        "source_mesh": str(source_mesh.resolve()),
        "engine_semantics": "DexJoCo/MuJoCo mesh collision; MuJoCo uses convex mesh collision semantics for dynamic contacts.",
        "meshes": collision_meshes,
        "fallback": manifest.get("collision", {}),
    }
    write_json(collision_dir / "collision_manifest.json", collision_manifest)
    manifest["collision"] = {
        "type": "mesh",
        "mode": collision_manifest["mode"],
        "collision_manifest": str((collision_dir / "collision_manifest.json").resolve()),
        "meshes": collision_manifest["meshes"],
        "fallback": collision_manifest["fallback"],
    }
    write_json(manifest_path, manifest)
    return {
        "asset_id": manifest.get("asset_id"),
        "collision_mode": manifest["collision"]["mode"],
        "source": source_kind,
        "mesh_count": len(collision_manifest["meshes"]),
        "collision_manifest": manifest["collision"]["collision_manifest"],
    }


def _candidate_manifest_paths(source: str) -> list[Path]:
    summary_path = REGISTRY / "pending" / f"{source}_bulk_import_summary.json"
    if not summary_path.exists():
        return []
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    paths = []
    for item in summary.get("results", []):
        if item.get("candidate_created") and item.get("asset_id"):
            task_id = item.get("task_id") or f"pick_place_{item['asset_id']}"
            path = REGISTRY / "pending" / task_id / "asset_manifest.json"
            if path.exists():
                paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id")
    parser.add_argument("--source", default="robotwin")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--pending-candidates", action="store_true")
    args = parser.parse_args()

    if args.asset_id:
        manifest_paths = [load_asset_manifest(args.asset_id)[0]]
    elif args.pending_candidates:
        manifest_paths = _candidate_manifest_paths(args.source)
    elif args.all:
        manifest_paths = sorted((PROCESSED_ROOT / args.source).glob("*/asset_manifest.json"))
    else:
        raise SystemExit("Pass --asset-id, --all, or --pending-candidates")

    results = [_collision_mesh_for_manifest(path) for path in manifest_paths]
    print(json.dumps({"count": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
