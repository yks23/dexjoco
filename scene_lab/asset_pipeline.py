"""Shared helpers for Scene Lab external asset import and task generation."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = ROOT / "scene_lab" / "assets"
PROCESSED_ROOT = ASSETS_ROOT / "processed"
REGISTRY = ROOT / "scene_lab" / "registry"

MESH_EXTENSIONS = (".obj", ".stl", ".dae", ".ply", ".glb")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


def ensure_safe_id(value: str, label: str = "id") -> str:
    if not SAFE_ID_RE.match(value):
        raise ValueError(f"{label} must match {SAFE_ID_RE.pattern}: {value}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def find_meshes(source: Path) -> list[Path]:
    if source.is_file() and source.suffix.lower() in MESH_EXTENSIONS:
        return [source]
    if not source.is_dir():
        return []
    return sorted(
        p
        for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in MESH_EXTENSIONS
    )


def choose_mesh(meshes: list[Path]) -> Path | None:
    if not meshes:
        return None
    preferred_tokens = (
        "google_16k",
        "textured",
        "model_normalized",
        "model",
        "collision",
    )
    for token in preferred_tokens:
        for mesh in meshes:
            if token in str(mesh).lower():
                return mesh
    return meshes[0]


def infer_category(source: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    name = source.stem if source.is_file() else source.name
    cleaned = re.sub(r"^[0-9]+[_-]*", "", name).strip("_- ")
    return cleaned.lower().replace(" ", "_") or "object"


def infer_collision(category: str, explicit_size: list[float] | None = None) -> dict[str, Any]:
    if explicit_size:
        return {"type": "box", "size": explicit_size}
    category_l = category.lower()
    if any(token in category_l for token in ("bottle", "can", "cup", "mug")):
        return {"type": "cylinder", "size": [0.04, 0.075]}
    if any(token in category_l for token in ("ball", "sphere", "orange", "apple")):
        return {"type": "sphere", "size": [0.045]}
    if "banana" in category_l:
        return {"type": "capsule", "size": [0.025, 0.08]}
    return {"type": "box", "size": [0.06, 0.04, 0.05]}


def infer_mass(category: str, explicit: float | None = None) -> float:
    if explicit is not None:
        return explicit
    category_l = category.lower()
    if any(token in category_l for token in ("bottle", "mug", "cup")):
        return 0.18
    if "box" in category_l:
        return 0.22
    return 0.15


def mirror_mesh(mesh: Path, processed_dir: Path, copy: bool = False) -> Path:
    visual_dir = processed_dir / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    dest = visual_dir / mesh.name
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    if copy:
        shutil.copy2(mesh, dest)
    else:
        dest.symlink_to(mesh.resolve())
    return dest


def robotwin_model_data_for_mesh(mesh: Path) -> dict[str, Any]:
    stem = mesh.stem
    match = re.match(r"base([0-9]+)$", stem)
    if not match:
        return {}
    candidate = mesh.parents[1] / f"model_data{match.group(1)}.json"
    if not candidate.exists():
        return {}
    try:
        return read_json(candidate)
    except Exception:
        return {}


def prepare_visual_mesh(
    mesh: Path,
    processed_dir: Path,
    copy: bool = False,
    model_data: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    if mesh.suffix.lower() != ".glb":
        return mirror_mesh(mesh, processed_dir, copy=copy), "linked_or_copied"

    visual_dir = processed_dir / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    dest = visual_dir / f"{mesh.stem}.obj"
    try:
        import trimesh

        loaded = trimesh.load(mesh, force="scene")
        if hasattr(loaded, "dump"):
            dumped = loaded.dump(concatenate=True)
        else:
            dumped = loaded
        if model_data:
            center = model_data.get("center")
            scale = model_data.get("scale")
            if center and scale and hasattr(dumped, "vertices"):
                import numpy as np

                vertices = dumped.vertices.copy()
                vertices -= np.asarray(center, dtype=float)
                vertices *= np.asarray(scale, dtype=float)
                vertices = vertices[:, [0, 2, 1]]
                vertices[:, 1] *= -1
                bbox_center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
                vertices -= bbox_center
                dumped.vertices = vertices
        dumped.export(dest)
        return dest, "glb_converted_to_obj"
    except Exception:
        return mirror_mesh(mesh, processed_dir, copy=copy), "glb_linked_without_conversion"


def load_asset_manifest(asset_id: str) -> tuple[Path, dict[str, Any]]:
    ensure_safe_id(asset_id, "asset_id")
    matches = sorted(PROCESSED_ROOT.glob(f"*/{asset_id}/asset_manifest.json"))
    if not matches:
        raise FileNotFoundError(f"No processed asset manifest found for asset_id={asset_id}")
    if len(matches) > 1:
        raise ValueError(f"Multiple manifests found for asset_id={asset_id}: {matches}")
    return matches[0], read_json(matches[0])


def build_manifest(
    *,
    asset_id: str,
    source_benchmark: str,
    source_path: Path,
    mesh_path: Path,
    processed_mesh: Path,
    category: str,
    collision: dict[str, Any],
    mass: float,
    status: str,
    source_url: str,
    license_name: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "asset_id": asset_id,
        "source_benchmark": source_benchmark,
        "category": category,
        "source_path": str(source_path.resolve()),
        "source_url": source_url,
        "license": license_name,
        "status": status,
        "visual_mesh": str(processed_mesh.resolve()),
        "source_mesh": str(mesh_path.resolve()),
        "scale": 1.0,
        "mass": mass,
        "collision": collision,
        "affordances": ["pick", "place"] if status == "ready_for_pick_place" else [],
    }
    if extra:
        manifest.update(extra)
    return manifest
