#!/usr/bin/env python
"""Infer DexJoCo-style physical material metadata for processed assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import PROCESSED_ROOT, REGISTRY, load_asset_manifest, write_json  # noqa: E402
from scene_lab.physical_materials import infer_physical_material  # noqa: E402


def _write_for_manifest(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    material = infer_physical_material(manifest)
    out = manifest_path.parent / "physical_material.json"
    write_json(out, material)
    manifest["physical_material_path"] = str(out.resolve())
    manifest["physical_material"] = {
        "material_key": material["material_key"],
        "surface_type": material["surface_type"],
        "contact": material["contact"],
    }
    write_json(manifest_path, manifest)
    return {
        "asset_id": manifest.get("asset_id"),
        "category": manifest.get("category"),
        "material_key": material.get("material_key"),
        "physical_material": str(out),
    }


def _candidate_paths() -> list[Path]:
    summary_path = REGISTRY / "pending" / "robotwin_bulk_import_summary.json"
    if not summary_path.exists():
        return []
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    paths = []
    for item in summary.get("results", []):
        if item.get("candidate_created") and item.get("asset_id"):
            path = REGISTRY / "pending" / f"pick_place_{item['asset_id']}" / "asset_manifest.json"
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

    manifest_paths: list[Path]
    if args.asset_id:
        manifest_paths = [load_asset_manifest(args.asset_id)[0]]
    elif args.pending_candidates:
        manifest_paths = _candidate_paths()
    elif args.all:
        manifest_paths = sorted((PROCESSED_ROOT / args.source).glob("*/asset_manifest.json"))
    else:
        raise SystemExit("Pass --asset-id, --all, or --pending-candidates")

    results = [_write_for_manifest(path) for path in manifest_paths]
    print(json.dumps({"count": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
