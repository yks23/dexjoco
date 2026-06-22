#!/usr/bin/env python
"""Build per-asset modeling reports for processed RoboTwin assets."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import PROCESSED_ROOT, write_json  # noqa: E402


def _mesh_stats(path: Path) -> dict[str, Any]:
    try:
        import trimesh

        loaded = trimesh.load(path, force="scene")
        mesh = loaded.dump(concatenate=True) if hasattr(loaded, "dump") else loaded
        return {
            "path": str(path.resolve()),
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
            "extents_m": [float(v) for v in mesh.extents],
            "is_watertight": bool(getattr(mesh, "is_watertight", False)),
            "bounds_m": [[float(v) for v in row] for row in mesh.bounds],
        }
    except Exception as exc:
        return {"path": str(path.resolve()), "error": f"{type(exc).__name__}: {exc}"}


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _source_points_info(manifest: dict[str, Any]) -> Any:
    source_path = Path(str(manifest.get("source_path") or ""))
    return _read_json(source_path / "points_info.json")


def build_report(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset_dir = manifest_path.parent
    visual_mesh = Path(manifest["visual_mesh"])
    collision = manifest.get("collision", {})
    collision_manifest = _read_json(Path(str(collision.get("collision_manifest") or ""))) or {}
    physical_material = _read_json(asset_dir / "physical_material.json") or manifest.get("physical_material") or {}
    collision_meshes = []
    for item in collision_manifest.get("meshes", []):
        path = Path(item["path"])
        collision_meshes.append({**item, "stats": _mesh_stats(path)})

    model_data = manifest.get("model_data") or {}
    calibration = manifest.get("dexjoco_calibration") or {}
    report = {
        "asset_id": manifest.get("asset_id"),
        "source_benchmark": manifest.get("source_benchmark"),
        "robotwin_object_id": manifest.get("robotwin_object_id"),
        "robotwin_variant": manifest.get("robotwin_variant"),
        "category": manifest.get("category"),
        "status": manifest.get("status"),
        "modeling_status": "complete_mesh_collision" if collision.get("type") == "mesh" else "fallback_primitive_collision",
        "ready_for_pick_place": manifest.get("status") == "ready_for_pick_place",
        "visual": {
            "source_mesh": manifest.get("source_mesh"),
            "processed_mesh": manifest.get("visual_mesh"),
            "conversion_status": manifest.get("conversion_status"),
            "stats": _mesh_stats(visual_mesh),
        },
        "collision": {
            "type": collision.get("type"),
            "mode": collision.get("mode"),
            "source": collision_manifest.get("source"),
            "source_mesh": collision_manifest.get("source_mesh"),
            "engine_semantics": collision_manifest.get("engine_semantics"),
            "mesh_count": len(collision_meshes),
            "meshes": collision_meshes,
        },
        "physical_material": physical_material,
        "scale_alignment": {
            "model_data_center": model_data.get("center"),
            "model_data_scale": model_data.get("scale"),
            "model_data_stable": model_data.get("stable"),
            "calibration": calibration,
        },
        "semantic_points": _source_points_info(manifest),
        "limitations": [],
    }
    if collision_manifest.get("source") != "robotwin_collision_mesh":
        report["limitations"].append("No matching RoboTwin collision GLB was found; collision mesh falls back to processed visual mesh.")
    if manifest.get("status") != "ready_for_pick_place":
        report["limitations"].append("Asset is fully registered/modelled but not used for first-pass pick/place candidate generation.")
    if not report["semantic_points"]:
        report["limitations"].append("No RoboTwin points_info semantic contact/functional point metadata found.")
    write_json(asset_dir / "modeling_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="robotwin")
    args = parser.parse_args()

    reports = [build_report(path) for path in sorted((PROCESSED_ROOT / args.source).glob("*/asset_manifest.json"))]
    summary = {
        "source": args.source,
        "asset_count": len(reports),
        "status": dict(Counter(str(r.get("status")) for r in reports)),
        "modeling_status": dict(Counter(str(r.get("modeling_status")) for r in reports)),
        "collision_source": dict(Counter(str((r.get("collision") or {}).get("source")) for r in reports)),
        "physical_material": dict(Counter(str((r.get("physical_material") or {}).get("material_key")) for r in reports)),
        "ready_for_pick_place": sum(bool(r.get("ready_for_pick_place")) for r in reports),
        "registered_only_or_other": sum(not bool(r.get("ready_for_pick_place")) for r in reports),
        "reports_root": str((PROCESSED_ROOT / args.source).resolve()),
    }
    out = PROCESSED_ROOT / args.source / "robotwin_modeling_summary.json"
    write_json(out, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
