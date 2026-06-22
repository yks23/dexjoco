#!/usr/bin/env python
"""Render original-vs-Scene-Lab comparison previews for pending candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


VIEWS = {
    "front": (22, -65),
    "side": (18, 25),
    "top": (90, -90),
}


def _load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene")
    if hasattr(loaded, "dump"):
        return loaded.dump(concatenate=True)
    return loaded


def _face_colors(mesh: trimesh.Trimesh) -> np.ndarray:
    visual = getattr(mesh, "visual", None)
    material = getattr(visual, "material", None)
    image = getattr(material, "image", None)
    uv = getattr(visual, "uv", None)
    if image is not None and uv is not None:
        image = image.convert("RGB") if isinstance(image, Image.Image) else Image.fromarray(image).convert("RGB")
        pixels = np.asarray(image, dtype=np.float32) / 255.0
        h, w = pixels.shape[:2]
        face_uv = uv[np.asarray(mesh.faces)].mean(axis=1)
        u = np.clip(face_uv[:, 0], 0.0, 1.0)
        v = np.clip(face_uv[:, 1], 0.0, 1.0)
        x = np.clip((u * (w - 1)).astype(int), 0, w - 1)
        y = np.clip(((1.0 - v) * (h - 1)).astype(int), 0, h - 1)
        colors = pixels[y, x]
        alpha = np.ones((colors.shape[0], 1), dtype=np.float32) * 0.96
        return np.concatenate([colors, alpha], axis=1)
    face_count = len(mesh.faces)
    if hasattr(visual, "face_colors") and len(visual.face_colors) == face_count:
        colors = np.asarray(visual.face_colors, dtype=np.float32) / 255.0
        colors[:, 3] = 0.96
        return colors
    for attr in ("diffuse", "main_color"):
        value = getattr(material, attr, None)
        if value is None:
            continue
        color = np.asarray(value, dtype=np.float32).reshape(-1)
        if color.size >= 3:
            if color.max() > 1.0:
                color = color / 255.0
            rgba = np.ones(4, dtype=np.float32) * 0.96
            rgba[:3] = np.clip(color[:3], 0.0, 1.0)
            if color.size >= 4:
                rgba[3] = np.clip(color[3], 0.0, 1.0)
            return np.tile(rgba[None, :], (face_count, 1))
    return np.tile(np.asarray([[0.05, 0.20, 0.72, 0.92]], dtype=np.float32), (face_count, 1))


def _render_mesh(mesh: trimesh.Trimesh, out: Path, elev: float, azim: float) -> None:
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError(f"Mesh has no renderable faces: {out}")

    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    vertices = vertices - center
    radius = float(np.max(np.linalg.norm(vertices, axis=1)))
    radius = max(radius, 1e-3)

    fig = plt.figure(figsize=(4.2, 3.2), dpi=120)
    ax = fig.add_subplot(111, projection="3d")
    polys = vertices[faces]
    collection = Poly3DCollection(
        polys,
        linewidths=0.05,
        edgecolors=(0.08, 0.11, 0.20, 0.16),
        facecolors=_face_colors(mesh),
    )
    ax.add_collection3d(collection)
    ax.set_xlim(-radius, radius)
    ax.set_ylim(-radius, radius)
    ax.set_zlim(-radius, radius)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def render_candidate(candidate_dir: Path) -> dict:
    asset_path = candidate_dir / "asset_manifest.json"
    if not asset_path.exists():
        return {"candidate": candidate_dir.name, "ok": False, "error": "missing asset_manifest.json"}
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    mesh_path = Path(asset["visual_mesh"])
    mesh = _load_mesh(mesh_path)
    compare_dir = candidate_dir / "comparison"
    original = {}
    for name, (elev, azim) in VIEWS.items():
        out = compare_dir / f"original_{name}.png"
        _render_mesh(mesh, out, elev=elev, azim=azim)
        original[name] = str(out.relative_to(candidate_dir))

    middleware = {}
    for name in ("front", "side", "wrist"):
        preview = candidate_dir / "preview" / f"{name}.png"
        middleware[name] = str(preview.relative_to(candidate_dir)) if preview.exists() else None

    manifest = {
        "candidate": candidate_dir.name,
        "asset_id": asset.get("asset_id"),
        "source_benchmark": asset.get("source_benchmark"),
        "category": asset.get("category"),
        "original_views": original,
        "middleware_views": middleware,
    }
    (compare_dir / "comparison.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"candidate": candidate_dir.name, "ok": True, "comparison": str(compare_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    results = [render_candidate(path.resolve()) for path in args.candidate_dirs]
    print(json.dumps(results, indent=2))
    if not all(item.get("ok") for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
