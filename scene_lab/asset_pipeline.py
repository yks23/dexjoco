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
    for companion in _mesh_companions(mesh):
        companion_dest = visual_dir / companion.name
        if companion_dest == dest:
            continue
        if companion_dest.exists() or companion_dest.is_symlink():
            companion_dest.unlink()
        if copy:
            shutil.copy2(companion, companion_dest)
        else:
            companion_dest.symlink_to(companion.resolve())
    return dest


def _mesh_companions(mesh: Path) -> list[Path]:
    companions: list[Path] = []
    if mesh.suffix.lower() == ".obj":
        try:
            for line in mesh.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0] == "mtllib":
                    candidate = mesh.parent / parts[1]
                    if candidate.exists():
                        companions.append(candidate)
        except OSError:
            pass
    for path in mesh.parent.iterdir():
        if path.is_file() and path.suffix.lower() in (".mtl", ".png", ".jpg", ".jpeg", ".bmp", ".tga"):
            companions.append(path)
    unique: list[Path] = []
    seen = set()
    for path in companions:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


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
    is_glb = mesh.suffix.lower() == ".glb" or mesh.name.endswith(".glb.orig")
    if not is_glb:
        return mirror_mesh(mesh, processed_dir, copy=copy), "linked_or_copied"

    visual_dir = processed_dir / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    stem = mesh.name.removesuffix(".glb.orig") if mesh.name.endswith(".glb.orig") else mesh.stem
    dest = visual_dir / f"{stem}.obj"
    try:
        import trimesh

        loaded = trimesh.load(mesh, file_type="glb" if mesh.name.endswith(".glb.orig") else None, force="scene")
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
        elif _export_textured_scene_obj(loaded, dest):
            return dest, "glb_converted_to_textured_obj"
        dumped.export(dest)
        return dest, "glb_converted_to_obj"
    except Exception:
        return mirror_mesh(mesh, processed_dir, copy=copy), "glb_linked_without_conversion"


def _export_textured_scene_obj(scene_or_mesh: Any, dest: Path) -> bool:
    try:
        import numpy as np
        import trimesh

        if isinstance(scene_or_mesh, trimesh.Scene):
            geometries = list(scene_or_mesh.geometry.values())
            if len(geometries) != 1:
                return False
            mesh = geometries[0]
        else:
            mesh = scene_or_mesh
        visual = getattr(mesh, "visual", None)
        uv = getattr(visual, "uv", None)
        material = getattr(visual, "material", None)
        image = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
        if uv is None or image is None:
            return False
        texture_path = dest.with_name("texture.png")
        material_path = dest.with_name("material.mtl")
        image.save(texture_path)
        material_path.write_text(
            "newmtl textured_material\n"
            "Ka 1 1 1\n"
            "Kd 1 1 1\n"
            "Ks 0.1 0.1 0.1\n"
            "Ns 16\n"
            f"map_Kd {texture_path.name}\n",
            encoding="utf-8",
        )
        vertices = np.asarray(mesh.vertices, dtype=float)
        uvs = np.asarray(uv, dtype=float)
        faces = np.asarray(mesh.faces, dtype=int)
        with dest.open("w", encoding="utf-8") as handle:
            handle.write(f"mtllib {material_path.name}\n")
            handle.write("usemtl textured_material\n")
            for vertex in vertices:
                handle.write(f"v {vertex[0]:.9g} {vertex[1]:.9g} {vertex[2]:.9g}\n")
            for texcoord in uvs:
                handle.write(f"vt {texcoord[0]:.9g} {1.0 - texcoord[1]:.9g}\n")
            for face in faces:
                items = [f"{index + 1}/{index + 1}" for index in face]
                handle.write("f " + " ".join(items) + "\n")
        return True
    except Exception:
        return False


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
