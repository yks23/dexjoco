#!/usr/bin/env python
"""Generate a simple MJCF scene.xml for a Scene Lab task.json candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.physical_materials import contact_attrs, infer_physical_material  # noqa: E402

PANDA_ALLEGRO = ROOT / "dexjoco" / "dexjoco" / "sim" / "envs" / "xmls" / "panda_allegro_copy.xml"


def _object_by_role(task: dict, role: str) -> dict:
    for obj in task.get("objects", []):
        if obj.get("role") == role:
            return obj
    raise ValueError(f"Missing object with role={role}")


def _fmt(values) -> str:
    return " ".join(f"{float(v):.6g}" for v in values)


def _load_asset_manifest(task: dict, candidate_dir: Path | None) -> dict | None:
    if candidate_dir is None:
        return None
    path = candidate_dir / "asset_manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for obj in task.get("objects", []):
        rel = obj.get("asset_manifest")
        if rel:
            path = Path(rel)
            if not path.is_absolute():
                path = candidate_dir / path
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
    return None


def _load_physical_material(asset_manifest: dict | None, candidate_dir: Path | None) -> dict[str, Any]:
    if candidate_dir is not None:
        path = candidate_dir / "physical_material.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    if asset_manifest:
        material = asset_manifest.get("physical_material")
        if isinstance(material, dict):
            return material
        source = asset_manifest.get("physical_material_path")
        if source:
            path = Path(source)
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return infer_physical_material(asset_manifest)
    return infer_physical_material({})


def _geom_size(collision: dict, fallback_half: list[float]) -> tuple[str, list[float]]:
    geom_type = collision.get("type", "box")
    size = collision.get("size") or fallback_half
    if geom_type == "box" and len(size) != 3:
        geom_type, size = "box", fallback_half
    elif geom_type in ("cylinder", "capsule") and len(size) != 2:
        geom_type, size = "box", fallback_half
    elif geom_type == "sphere" and len(size) != 1:
        geom_type, size = "box", fallback_half
    return geom_type, [float(v) for v in size]


def _collision_meshes(collision: dict) -> list[dict[str, Any]]:
    if collision.get("type") != "mesh":
        return []
    meshes = collision.get("meshes")
    if isinstance(meshes, list):
        return [mesh for mesh in meshes if isinstance(mesh, dict) and mesh.get("path")]
    manifest_path = collision.get("collision_manifest")
    if manifest_path:
        path = Path(manifest_path)
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            meshes = manifest.get("meshes")
            if isinstance(meshes, list):
                return [mesh for mesh in meshes if isinstance(mesh, dict) and mesh.get("path")]
    return []


def _primitive_geom(
    *,
    name: str,
    geom_type: str,
    size: list[float],
    material: str,
    mass: float | None,
    visual_only: bool,
    contact: dict[str, Any] | None = None,
) -> str:
    attrs = [
        f'name="{escape(name)}"',
        f'type="{escape(geom_type)}"',
        f'size="{_fmt(size)}"',
        f'material="{escape(material)}"',
    ]
    if visual_only:
        attrs.extend(['contype="0"', 'conaffinity="0"', 'group="1"'])
    else:
        contact = contact or {}
        attrs.extend(
            [
                f'mass="{float(mass or 0.15):.6g}"',
                f'friction="{_fmt(contact.get("friction", [1.0, 0.03, 0.0005]))}"',
                f'group="{int(contact.get("group", 3))}"',
            ]
        )
        for key in ("condim", "contype", "conaffinity"):
            if key in contact:
                attrs.append(f'{key}="{int(contact[key])}"')
        for key in ("solref", "solimp", "rgba"):
            if key in contact:
                attrs.append(f'{key}="{_fmt(contact[key])}"')
    return "      <geom " + " ".join(attrs) + "/>"


def _contact_xml_attrs(contact: dict[str, Any]) -> list[str]:
    attrs = [
        f'friction="{_fmt(contact.get("friction", [1.0, 0.03, 0.0005]))}"',
        f'group="{int(contact.get("group", 3))}"',
    ]
    for key in ("condim", "contype", "conaffinity"):
        if key in contact:
            attrs.append(f'{key}="{int(contact[key])}"')
    for key in ("solref", "solimp", "rgba"):
        if key in contact:
            attrs.append(f'{key}="{_fmt(contact[key])}"')
    return attrs


def _mesh_collision_assets_and_geoms(
    *,
    object_name: str,
    collision_meshes: list[dict[str, Any]],
    mass: float,
    contact: dict[str, Any],
) -> tuple[str, str]:
    assets = []
    geoms = []
    part_mass = mass / max(1, len(collision_meshes))
    for index, mesh_info in enumerate(collision_meshes):
        mesh_path = Path(mesh_info["path"])
        mesh_name = f"{object_name}_collision_mesh_{index}"
        geom_name = f"{object_name}_collision_{index}"
        assets.append(
            f'    <mesh name="{escape(mesh_name)}" file="{escape(str(mesh_path.resolve()))}" scale="1 1 1"/>'
        )
        attrs = [
            f'name="{escape(geom_name)}"',
            'type="mesh"',
            f'mesh="{escape(mesh_name)}"',
            f'mass="{part_mass:.6g}"',
            'material="generated_object"',
            *_contact_xml_attrs(contact),
        ]
        geoms.append("      <geom " + " ".join(attrs) + "/>")
    return "\n".join(assets), "\n".join(geoms)


def _mesh_texture_file(mesh_path: Path) -> Path | None:
    for name in ("place_holder.png", "texture.png", "material.png"):
        candidate = mesh_path.parent / name
        if candidate.exists():
            return candidate
    images = sorted(
        p
        for p in mesh_path.parent.iterdir()
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")
    )
    return images[0] if images else None


def _mesh_diffuse_rgba(mesh_path: Path) -> list[float] | None:
    mtl_path = mesh_path.with_name("material.mtl")
    if not mtl_path.exists():
        mtllib = None
        try:
            for line in mesh_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0] == "mtllib":
                    mtllib = parts[1]
                    break
        except OSError:
            mtllib = None
        if mtllib:
            candidate = mesh_path.parent / mtllib
            if candidate.exists():
                mtl_path = candidate
    if not mtl_path.exists():
        return None

    try:
        for line in mtl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.strip().split()
            if len(parts) >= 4 and parts[0] == "Kd":
                rgb = [max(0.0, min(1.0, float(value))) for value in parts[1:4]]
                return [*rgb, 1.0]
    except (OSError, ValueError):
        return None
    return None


def generate_scene_xml(task: dict, candidate_dir: Path | None = None) -> str:
    manipulated = _object_by_role(task, "manipulated_object")
    target = _object_by_role(task, "target_region")
    table = next((obj for obj in task.get("objects", []) if obj.get("role") == "support_surface"), {})
    asset_manifest = _load_asset_manifest(task, candidate_dir)
    physical_material = _load_physical_material(asset_manifest, candidate_dir)
    object_contact = contact_attrs(physical_material)
    table_contact = {
        "friction": [1.2, 0.01, 0.0001],
        "group": 3,
        "condim": 3,
    }

    object_name = manipulated.get("name", "object")
    target_name = target.get("name", "goal_zone")
    target_site = task.get("success_condition", {}).get("target", "goal_center")

    obj_pose = manipulated.get("pose", [-0.32, -0.18, 0.945, 1, 0, 0, 0])
    obj_pos = obj_pose[:3]
    obj_quat = obj_pose[3:7] if len(obj_pose) >= 7 else [1, 0, 0, 0]
    obj_size = manipulated.get("size", [0.216, 0.156, 0.046])
    half = [float(obj_size[0]) / 2, float(obj_size[1]) / 2, float(obj_size[2]) / 2]
    collision = asset_manifest.get("collision", {}) if asset_manifest else {}
    geom_type, geom_size = _geom_size(collision, half)
    object_mass = float(asset_manifest.get("mass", 0.28)) if asset_manifest else 0.28
    visual_mesh = Path(asset_manifest.get("visual_mesh", "")) if asset_manifest else None
    mesh_supported = bool(
        visual_mesh
        and visual_mesh.exists()
        and visual_mesh.suffix.lower() in (".obj", ".stl", ".dae")
    )
    mesh_asset = ""
    collision_mesh_asset = ""
    texture_asset = ""
    mesh_material = "generated_object"
    visual_geom = ""
    if mesh_supported:
        mesh_asset = (
            f'    <mesh name="{escape(object_name)}_visual_mesh" '
            f'file="{escape(str(visual_mesh.resolve()))}" scale="1 1 1"/>\n'
        )
        texture_file = _mesh_texture_file(visual_mesh)
        if texture_file is not None:
            texture_asset = (
                f'    <texture name="{escape(object_name)}_texture" type="2d" '
                f'file="{escape(str(texture_file.resolve()))}"/>\n'
                f'    <material name="{escape(object_name)}_textured" '
                f'texture="{escape(object_name)}_texture" rgba="1 1 1 1"/>\n'
            )
            mesh_material = f"{object_name}_textured"
        else:
            diffuse_rgba = _mesh_diffuse_rgba(visual_mesh)
            if diffuse_rgba is not None:
                texture_asset = (
                    f'    <material name="{escape(object_name)}_diffuse" '
                    f'rgba="{_fmt(diffuse_rgba)}" specular=".2" shininess=".25"/>\n'
                )
                mesh_material = f"{object_name}_diffuse"
        visual_geom = (
            f'      <geom name="{escape(object_name)}_visual" type="mesh" '
            f'mesh="{escape(object_name)}_visual_mesh" contype="0" conaffinity="0" '
            f'group="1" material="{escape(mesh_material)}"/>'
        )
    else:
        visual_geom = _primitive_geom(
            name=f"{object_name}_visual",
            geom_type=geom_type,
            size=geom_size,
            material="generated_object",
            mass=None,
            visual_only=True,
        )
    page_hint = ""
    if not asset_manifest:
        page_hint = f'''      <geom name="{object_name}_page_hint" type="box" size="{_fmt([half[0] * .9, half[1] * .85, half[2] * .35])}"
            pos="0.01 0 0" contype="0" conaffinity="0" group="1" material="generated_object_pages"/>'''
    mesh_collisions = _collision_meshes(collision)
    if mesh_collisions:
        collision_mesh_asset, collision_geom = _mesh_collision_assets_and_geoms(
            object_name=object_name,
            collision_meshes=mesh_collisions,
            mass=object_mass,
            contact=object_contact,
        )
    else:
        collision_geom = _primitive_geom(
            name=f"{object_name}_collision",
            geom_type=geom_type,
            size=geom_size,
            material="generated_object",
            mass=object_mass,
            visual_only=False,
            contact=object_contact,
        )

    target_pose = target.get("pose", [0.12, 0.22, 0.925])
    target_size = target.get("size", [0.26, 0.20, 0.008])
    target_half = [float(target_size[0]) / 2, float(target_size[1]) / 2, float(target_size[2]) / 2]

    table_pose = table.get("pose", [-0.15, 0.0, 0.89])
    table_size = table.get("size", [0.90, 1.70, 0.06])
    table_half = [float(table_size[0]) / 2, float(table_size[1]) / 2, float(table_size[2]) / 2]

    return f'''<?xml version="1.0" encoding="utf-8"?>
<mujoco model="SceneLabGenerated">
  <include file="{PANDA_ALLEGRO}"/>
  <option timestep=".002" noslip_iterations="5" noslip_tolerance="0"/>
  <visual>
    <headlight diffuse=".45 .45 .45" ambient=".45 .45 .45"/>
    <global azimuth="150" elevation="-25" offheight="1024" offwidth="1024"/>
    <quality offsamples="4"/>
  </visual>
  <asset>
    <texture name="scene_lab_floor_tex" type="2d" builtin="checker" width="512" height="512"
             rgb1=".72 .75 .78" rgb2=".55 .58 .62"/>
    <texture name="scene_lab_table_tex" type="2d" builtin="checker" width="512" height="512"
             rgb1=".56 .38 .22" rgb2=".64 .46 .28"/>
    <material name="scene_lab_floor" texture="scene_lab_floor_tex" texrepeat="4 4"/>
    <material name="scene_lab_table" texture="scene_lab_table_tex" texrepeat="3 2"/>
    <material name="generated_object" rgba=".08 .18 .55 1" specular=".2" shininess=".25"/>
    <material name="generated_object_pages" rgba=".94 .90 .78 1"/>
    <material name="generated_target" rgba=".1 .75 .35 .35"/>
{mesh_asset.rstrip()}
{collision_mesh_asset.rstrip()}
{texture_asset.rstrip()}
  </asset>
  <worldbody>
    <geom name="floor" type="plane" size="3 3 .01" material="scene_lab_floor"/>
    <body name="table" pos="{_fmt(table_pose[:3])}">
      <geom name="table_collision" type="box" size="{_fmt(table_half)}"
            friction="{_fmt(table_contact["friction"])}" condim="{table_contact["condim"]}" group="{table_contact["group"]}"/>
      <geom name="table_visual" type="box" size="{_fmt(table_half)}" contype="0" conaffinity="0"
            group="1" material="scene_lab_table"/>
    </body>
    <body name="{escape(object_name)}" pos="{_fmt(obj_pos)}" quat="{_fmt(obj_quat)}">
      <freejoint name="{escape(object_name)}_root"/>
{collision_geom}
{visual_geom}
{page_hint}
    </body>
    <body name="{target_name}" pos="{_fmt(target_pose[:3])}">
      <geom name="{target_name}_visual" type="box" size="{_fmt(target_half)}" contype="0" conaffinity="0"
            group="1" material="generated_target"/>
      <site name="{target_site}" pos="0 0 .01" size=".01" rgba=".1 .9 .35 1"/>
    </body>
    <camera name="front" pos="1.15 -.65 1.55" quat=".677 .430 .307 .512" fovy="48"/>
    <camera name="side" pos=".15 -1.35 1.35" quat=".678 .678 .201 .201" fovy="48"/>
    <light name="key_light" pos=".4 -.8 2.8" dir="-.2 .25 -1" diffuse=".9 .9 .85" specular=".2 .2 .2"/>
    <body name="target" pos=".15 0 .55" quat="0 1 0 0" mocap="true">
      <geom name="target" type="box" size=".03 .03 .03" contype="0" conaffinity="0" rgba=".6 .3 .3 0"/>
    </body>
  </worldbody>
</mujoco>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_dir", type=Path)
    args = parser.parse_args()

    candidate_dir = args.candidate_dir.resolve()
    task_path = candidate_dir / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    entrypoint = task.setdefault("simulator", {}).setdefault("entrypoint", {})
    entrypoint.pop("config_mapping_key", None)
    entrypoint["xml_path"] = "scene.xml"
    entrypoint["env_class"] = "scene_lab.runtime.generated_scene_env.PandaGeneratedSceneEnv"
    (candidate_dir / "task.json").write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    scene_path = candidate_dir / "scene.xml"
    scene_path.write_text(generate_scene_xml(task, candidate_dir=candidate_dir), encoding="utf-8")
    print(scene_path)


if __name__ == "__main__":
    main()
