#!/usr/bin/env python
"""Render asset-only MuJoCo previews from processed Scene Lab manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import imageio.v2 as imageio
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import PROCESSED_ROOT, write_json  # noqa: E402
from scene_lab.physical_materials import contact_attrs, infer_physical_material  # noqa: E402


def _fmt(values) -> str:
    return " ".join(f"{float(v):.6g}" for v in values)


def _mesh_texture_file(mesh_path: Path) -> Path | None:
    material_libs: list[Path] = []
    if mesh_path.suffix.lower() == ".obj":
        try:
            for line in mesh_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0] == "mtllib":
                    material_libs.append(mesh_path.parent / parts[1])
        except OSError:
            pass
    for material_lib in material_libs:
        if not material_lib.exists():
            continue
        try:
            for line in material_lib.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0].lower() == "map_kd":
                    candidate = material_lib.parent / parts[1]
                    if candidate.exists():
                        return candidate
        except OSError:
            pass
    for name in ("texture.png", "place_holder.png", "material.png"):
        candidate = mesh_path.parent / name
        if candidate.exists():
            return candidate
    images = sorted(
        path
        for path in mesh_path.parent.iterdir()
        if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg")
    )
    if len(images) == 1:
        return images[0]
    return None


def _collision_meshes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    collision = manifest.get("collision") or {}
    meshes = collision.get("meshes")
    if isinstance(meshes, list):
        return [item for item in meshes if isinstance(item, dict) and item.get("path")]
    return []


def _asset_scene_xml(manifest: dict[str, Any], scene_path: Path) -> tuple[str, dict[str, Any]]:
    visual_mesh = Path(manifest["visual_mesh"]).resolve()
    mesh = trimesh.load(visual_mesh, force="mesh")
    bounds = np.asarray(mesh.bounds, dtype=float)
    extents = np.asarray(mesh.extents, dtype=float)
    max_extent = float(max(extents.max(), 0.05))
    lift_z = float(-bounds[0, 2] + 0.01)
    center = ((bounds[0] + bounds[1]) / 2.0).tolist()

    material = manifest.get("physical_material") or infer_physical_material(manifest)
    contact = contact_attrs(material)
    friction = contact.get("friction", [1.0, 0.03, 0.0005])

    texture_asset = ""
    visual_material = "asset_visual_material"
    texture = _mesh_texture_file(visual_mesh)
    if texture is not None:
        texture_asset = (
            f'    <texture name="asset_texture" type="2d" file="{escape(str(texture.resolve()))}"/>\n'
            '    <material name="asset_visual_material" texture="asset_texture" rgba="1 1 1 1"/>\n'
        )
    else:
        texture_asset = '    <material name="asset_visual_material" rgba=".75 .75 .75 1"/>\n'

    mesh_assets = [
        f'    <mesh name="asset_visual_mesh" file="{escape(str(visual_mesh))}" scale="1 1 1"/>'
    ]
    collision_geoms = []
    collision_meshes = _collision_meshes(manifest)
    for index, item in enumerate(collision_meshes):
        path = Path(item["path"]).resolve()
        mesh_name = f"asset_collision_mesh_{index}"
        mesh_assets.append(
            f'    <mesh name="{mesh_name}" file="{escape(str(path))}" scale="1 1 1"/>'
        )
        collision_geoms.append(
            f'      <geom name="asset_collision_{index}" type="mesh" mesh="{mesh_name}" '
            f'mass="{float(manifest.get("mass") or 0.15) / max(1, len(collision_meshes)):.6g}" '
            f'friction="{_fmt(friction)}" condim="{int(contact.get("condim", 4))}" '
            f'contype="{int(contact.get("contype", 1))}" conaffinity="{int(contact.get("conaffinity", 14))}" '
            'rgba=".1 .55 .95 .18" group="3"/>'
        )
    if not collision_geoms:
        fallback = (manifest.get("collision") or {}).get("fallback") or manifest.get("collision") or {}
        size = fallback.get("size") or (np.maximum(extents, 0.002) / 2.0).tolist()
        geom_type = fallback.get("type", "box")
        collision_geoms.append(
            f'      <geom name="asset_collision" type="{escape(str(geom_type))}" size="{_fmt(size)}" '
            f'mass="{float(manifest.get("mass") or 0.15):.6g}" friction="{_fmt(friction)}" '
            f'condim="{int(contact.get("condim", 4))}" contype="{int(contact.get("contype", 1))}" '
            f'conaffinity="{int(contact.get("conaffinity", 14))}" rgba=".1 .55 .95 .18" group="3"/>'
        )

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<mujoco model="AssetPreview">
  <option timestep=".002"/>
  <visual>
    <headlight diffuse=".55 .55 .55" ambient=".45 .45 .45"/>
    <global offheight="1024" offwidth="1024"/>
    <quality offsamples="4"/>
  </visual>
  <asset>
    <texture name="floor_tex" type="2d" builtin="checker" width="512" height="512"
             rgb1=".72 .75 .78" rgb2=".55 .58 .62"/>
    <material name="floor_mat" texture="floor_tex" texrepeat="4 4"/>
{texture_asset.rstrip()}
{chr(10).join(mesh_assets)}
  </asset>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 .01" material="floor_mat"/>
    <light name="key" pos=".4 -.8 2.5" diffuse=".9 .9 .85" specular=".2 .2 .2"/>
    <body name="asset" pos="0 0 {lift_z:.6g}">
{chr(10).join(collision_geoms)}
      <geom name="asset_visual" type="mesh" mesh="asset_visual_mesh" contype="0" conaffinity="0"
            group="1" material="{visual_material}"/>
    </body>
  </worldbody>
</mujoco>
'''
    scene_path.write_text(xml, encoding="utf-8")
    metadata = {
        "bounds": bounds.tolist(),
        "extents_m": extents.tolist(),
        "max_extent_m": max_extent,
        "center": center,
        "lift_z": lift_z,
        "collision_mesh_count": len(collision_meshes),
        "physical_material": material,
    }
    return xml, metadata


def render_asset(manifest_path: Path) -> dict[str, Any]:
    import mujoco

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    preview_dir = manifest_path.parent / "preview"
    preview_dir.mkdir(exist_ok=True)
    scene_path = manifest_path.parent / "asset_scene.xml"
    _, metadata = _asset_scene_xml(manifest, scene_path)
    model = mujoco.MjModel.from_xml_path(scene_path.as_posix())
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=768, width=768, max_geom=20000)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = [0.0, 0.0, max(metadata["extents_m"][2] * 0.5, 0.04)]
    camera.distance = max(0.25, metadata["max_extent_m"] * 2.8)
    views = {
        "front": (135, -20),
        "side": (90, -15),
        "top": (90, -75),
    }
    previews = {}
    mujoco.mj_forward(model, data)
    for name, (azimuth, elevation) in views.items():
        camera.azimuth = azimuth
        camera.elevation = elevation
        renderer.update_scene(data, camera=camera)
        frame = renderer.render()
        path = preview_dir / f"{name}.png"
        imageio.imwrite(path, frame)
        previews[name] = str(path.resolve())
    metadata["previews"] = previews
    write_json(manifest_path.parent / "asset_validation.json", {
        "ok": True,
        "asset_id": manifest.get("asset_id"),
        "source_benchmark": manifest.get("source_benchmark"),
        "scene_xml": str(scene_path.resolve()),
        **metadata,
    })
    renderer.close()
    return {"asset_id": manifest.get("asset_id"), "ok": True, "previews": previews}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="ycb")
    parser.add_argument("--asset-id")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.asset_id:
        manifest_paths = sorted((PROCESSED_ROOT / args.source).glob(f"{args.asset_id}/asset_manifest.json"))
    elif args.all:
        manifest_paths = sorted((PROCESSED_ROOT / args.source).glob("*/asset_manifest.json"))
    else:
        raise SystemExit("Pass --asset-id or --all")
    results = [render_asset(path) for path in manifest_paths]
    print(json.dumps({"count": len(results), "ok": sum(1 for r in results if r["ok"]), "results": results}, indent=2))


if __name__ == "__main__":
    main()
