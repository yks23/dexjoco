#!/usr/bin/env python
"""Asset-only review GUI for processed Scene Lab assets."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import math
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "scene_lab" / "assets" / "processed"
VIEWER_CACHE = ROOT / "scene_lab" / "assets" / "viewer_cache"
SOURCES = ("all", "ycb", "robotwin")
HARD_TASKS = (
    "hard_sort_objects_by_category",
    "hard_pack_items_into_box_and_close",
    "hard_stack_bowls_stably",
    "hard_pour_granules_proxy",
    "hard_present_object_to_camera",
)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _assets(source: str) -> list[Path]:
    roots = [p for p in PROCESSED.iterdir() if p.is_dir()] if source == "all" else [PROCESSED / source]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(sorted(root.glob("*/asset_manifest.json")))
    return paths


def _asset_source(manifest_path: Path) -> str:
    manifest = _read_json(manifest_path)
    return str(manifest.get("source_benchmark") or manifest_path.parent.parent.name)


def _safe_asset(source: str, asset_id: str) -> Path:
    matches = [path for path in _assets(source) if path.parent.name == asset_id]
    if not matches:
        raise ValueError("unknown asset")
    return matches[0]


def _file_url(path: Path) -> str | None:
    path = path.resolve()
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return None
    return "/asset_file/" + quote(str(rel), safe="/")


def _content_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".glb": "model/gltf-binary",
        ".json": "application/json; charset=utf-8",
        ".xml": "text/xml; charset=utf-8",
        ".obj": "text/plain; charset=utf-8",
        ".mtl": "text/plain; charset=utf-8",
    }.get(path.suffix.lower(), "application/octet-stream")


def _load_visual_mesh(manifest: dict) -> trimesh.Scene:
    visual_mesh = ROOT / str(manifest["visual_mesh"])
    loaded = trimesh.load(visual_mesh, force="scene", process=False)
    if isinstance(loaded, trimesh.Trimesh):
        scene = trimesh.Scene()
        scene.add_geometry(loaded, node_name="mesh")
        return scene
    return loaded


def _bounds_size(scene: trimesh.Scene) -> np.ndarray:
    bounds = np.asarray(scene.bounds, dtype=np.float64)
    if bounds.shape != (2, 3) or not np.isfinite(bounds).all():
        return np.asarray([0.08, 0.08, 0.08], dtype=np.float64)
    return np.maximum(bounds[1] - bounds[0], 1e-4)


def _ensure_asset_glb(manifest_path: Path) -> Path:
    manifest = _read_json(manifest_path)
    asset_id = str(manifest.get("asset_id") or manifest_path.parent.name)
    source = _asset_source(manifest_path)
    out = VIEWER_CACHE / "assets" / source / asset_id / f"{asset_id}.glb"
    visual_mesh = ROOT / str(manifest["visual_mesh"])
    if out.exists() and out.stat().st_mtime >= visual_mesh.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    scene = _load_visual_mesh(manifest)
    scene.export(out)
    return out


def _selected_showroom_assets(source: str, limit: str) -> list[Path]:
    assets = _assets(source)
    if limit == "all":
        return assets
    try:
        count = max(1, min(int(limit), len(assets)))
    except ValueError:
        count = min(120, len(assets))
    return assets[:count]


def _ensure_showroom_glb(source: str, limit: str) -> Path:
    source = source if source in SOURCES else "all"
    selected = _selected_showroom_assets(source, limit)
    safe_limit = "all" if limit == "all" else str(len(selected))
    out = VIEWER_CACHE / "showroom" / f"{source}_{safe_limit}.glb"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    if not selected:
        scene.export(out)
        return out
    cols = max(1, int(math.ceil(math.sqrt(len(selected)))))
    spacing = 0.22
    for idx, manifest_path in enumerate(selected):
        manifest = _read_json(manifest_path)
        asset_id = str(manifest.get("asset_id") or manifest_path.parent.name)
        try:
            asset_scene = _load_visual_mesh(manifest)
        except Exception:
            continue
        size = _bounds_size(asset_scene)
        scale = min(0.10 / float(max(size)), 1.8)
        row, col = divmod(idx, cols)
        x = (col - (cols - 1) / 2.0) * spacing
        y = (row - (math.ceil(len(selected) / cols) - 1) / 2.0) * spacing
        for geom_name, geom in asset_scene.geometry.items():
            mesh = geom.copy()
            mesh.apply_scale(scale)
            b = np.asarray(mesh.bounds, dtype=np.float64)
            center = (b[0] + b[1]) / 2.0
            floor_z = b[0, 2]
            mesh.apply_translation([x - center[0], y - center[1], -floor_z])
            scene.add_geometry(mesh, node_name=f"{idx:03d}_{asset_id}_{geom_name}")
    scene.export(out)
    return out


def _model_viewer_script() -> str:
    return '<script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/3.5.0/model-viewer.min.js"></script>'


_RUBIK_COLORS = {
    "U": [245, 245, 245, 255],
    "D": [245, 220, 30, 255],
    "F": [40, 160, 70, 255],
    "B": [45, 95, 210, 255],
    "R": [215, 40, 35, 255],
    "L": [245, 125, 25, 255],
    "body": [12, 12, 14, 255],
}


def _rotation_matrix(axis: str, turns: int) -> np.ndarray:
    angle = turns * np.pi / 2.0
    c, s = float(np.cos(angle)), float(np.sin(angle))
    if axis == "x":
        return np.asarray([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)
    if axis == "y":
        return np.asarray([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)
    return np.asarray([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def _rubiks_moves(state: str) -> list[tuple[str, int, int]]:
    return {
        "solved": [],
        "u": [("z", 1, 1)],
        "r": [("x", 1, 1)],
        "f": [("y", -1, 1)],
        "scramble": [("z", 1, 1), ("x", 1, 1), ("y", -1, 1), ("z", -1, -1)],
    }.get(state, [])


def _box(extents: tuple[float, float, float], center: np.ndarray, rgba: list[int]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.visual.vertex_colors = np.asarray([rgba] * len(mesh.vertices), dtype=np.uint8)
    mesh.apply_translation(center)
    return mesh


def _rubiks_cubie(position: np.ndarray, basis: np.ndarray, name: str) -> list[trimesh.Trimesh]:
    cubie_size = 0.096
    sticker_size = 0.074
    sticker_thickness = 0.004
    meshes = [_box((cubie_size, cubie_size, cubie_size), position, _RUBIK_COLORS["body"])]
    faces = [
        ("R", np.asarray([1.0, 0.0, 0.0])),
        ("L", np.asarray([-1.0, 0.0, 0.0])),
        ("F", np.asarray([0.0, 1.0, 0.0])),
        ("B", np.asarray([0.0, -1.0, 0.0])),
        ("U", np.asarray([0.0, 0.0, 1.0])),
        ("D", np.asarray([0.0, 0.0, -1.0])),
    ]
    local_coord = np.rint(np.linalg.solve(basis, position / 0.104)).astype(int)
    for face, normal_local in faces:
        axis_index = int(np.argmax(np.abs(normal_local)))
        if local_coord[axis_index] != int(normal_local[axis_index]):
            continue
        normal_world = basis @ normal_local
        center = position + normal_world * (cubie_size / 2.0 + sticker_thickness / 2.0)
        if axis_index == 0:
            extents = (sticker_thickness, sticker_size, sticker_size)
        elif axis_index == 1:
            extents = (sticker_size, sticker_thickness, sticker_size)
        else:
            extents = (sticker_size, sticker_size, sticker_thickness)
        sticker = _box(extents, np.zeros(3), _RUBIK_COLORS[face])
        transform = np.eye(4)
        transform[:3, :3] = basis
        transform[:3, 3] = center
        sticker.apply_transform(transform)
        meshes.append(sticker)
    return meshes


def _rubiks_transformed_cubelets(state: str) -> list[tuple[np.ndarray, np.ndarray, str]]:
    cubelets: list[tuple[np.ndarray, np.ndarray, str]] = []
    spacing = 0.104
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                cubelets.append((np.asarray([x, y, z], dtype=np.float64), np.eye(3), f"{x}_{y}_{z}"))
    for axis, layer, turns in _rubiks_moves(state):
        rot = _rotation_matrix(axis, turns)
        axis_index = {"x": 0, "y": 1, "z": 2}[axis]
        next_cubelets = []
        for coord, basis, name in cubelets:
            if int(round(coord[axis_index])) == layer:
                next_cubelets.append((np.rint(rot @ coord).astype(np.float64), rot @ basis, name))
            else:
                next_cubelets.append((coord, basis, name))
        cubelets = next_cubelets
    return [(coord * spacing, basis, name) for coord, basis, name in cubelets]


def _ensure_rubiks_glb(state: str) -> Path:
    state = state if state in {"solved", "u", "r", "f", "scramble"} else "solved"
    out = VIEWER_CACHE / "rubiks" / f"rubiks_{state}.glb"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    for idx, (position, basis, name) in enumerate(_rubiks_transformed_cubelets(state)):
        for part_idx, mesh in enumerate(_rubiks_cubie(position, basis, name)):
            scene.add_geometry(mesh, node_name=f"cubie_{idx:02d}_{part_idx}_{name}")
    scene.export(out)
    return out


def _rubiks_page() -> str:
    states = ["solved", "u", "r", "f", "scramble"]
    urls = {state: _file_url(_ensure_rubiks_glb(state)) for state in states}
    buttons = "".join(
        f'<button type="button" data-src="{urls[state]}">{html.escape(state.upper())}</button>'
        for state in states
    )
    task_links = "".join(
        f'<a href="/task_scene?task={quote(task_id)}">{html.escape(task_id)}</a>'
        for task_id in HARD_TASKS
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Structured Rubik Cube Demo</title>
  {_model_viewer_script()}
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #111827; color: white; }}
    header {{ height: 60px; display: flex; align-items: center; gap: 10px; padding: 0 18px; background: #0b1220; }}
    button, a {{ border: 0; border-radius: 6px; padding: 8px 12px; background: #2563eb; color: white; text-decoration: none; font: inherit; }}
    button:hover, a:hover {{ background: #1d4ed8; }}
    .note {{ color: #cbd5e1; margin-left: auto; font-size: 13px; }}
    model-viewer {{ width: 100vw; height: calc(100vh - 60px); background: #e5e7eb; }}
  </style>
</head>
<body>
  <header>
    <strong>Structured Rubik Cube</strong>
    {buttons}
    <a href="/viewer?source=ycb&asset=ycb_077_rubiks_cube">YCB rigid cube</a>
    <span class="note">27 cubelets + colored stickers; buttons switch layer-rotation states.</span>
  </header>
  <model-viewer id="rubiks" src="{urls["solved"]}" camera-controls auto-rotate shadow-intensity="1" exposure="1"></model-viewer>
  <script>
    const viewer = document.querySelector("#rubiks");
    for (const button of document.querySelectorAll("button[data-src]")) {{
      button.addEventListener("click", () => {{
        viewer.src = button.dataset.src;
      }});
    }}
  </script>
</body>
</html>"""


def _ensure_task_scene_previews(task_id: str) -> Path:
    safe_task_id = "".join(ch for ch in task_id if ch.isalnum() or ch in "._-")
    out = VIEWER_CACHE / "task_scenes" / safe_task_id
    front = out / "front.png"
    wrist = out / "wrist.png"
    if front.exists() and wrist.exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    script = f"""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, 'dexjoco')
from dexjoco.sim.envs.panda_robotwin_task_env import PandaRoboTwinTaskGymEnv
from dexjoco.tasks.robotwin_transfer.config import ROBOTWIN_TASK_CATALOG
env = PandaRoboTwinTaskGymEnv(ROBOTWIN_TASK_CATALOG[{task_id!r}], render_mode='rgb_array', randomize=False)
env.reset()
wrist, front = env.render()
Image.fromarray(front).save({str(front)!r})
Image.fromarray(wrist).save({str(wrist)!r})
env.close()
"""
    python = shutil.which("python") or "python"
    conda_python = Path("/opt/homebrew/Caskroom/miniconda/base/envs/dexjoco/bin/python")
    if conda_python.exists():
        python = str(conda_python)
    subprocess.run([python, "-c", script], cwd=ROOT, check=True)
    return out


def _task_scene_page(task_id: str) -> str:
    task_id = task_id or "hard_pack_items_into_box_and_close"
    preview_dir = _ensure_task_scene_previews(task_id)
    front_url = _file_url(preview_dir / "front.png")
    wrist_url = _file_url(preview_dir / "wrist.png")
    task_links = list(HARD_TASKS)
    links = "".join(
        f'<a class="{ "active" if task_id == tid else "" }" href="/task_scene?task={quote(tid)}">{html.escape(tid)}</a>'
        for tid in task_links
    )
    launch_url = f"/launch_task_viewer?task={quote(task_id)}"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DexJoCo Task Scene View</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #eef2f6; color: #1f2933; }}
    header {{ min-height: 58px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 18px; background: #101820; color: white; }}
    header a {{ color: #dbeafe; text-decoration: none; padding: 6px 10px; border-radius: 6px; font-size: 13px; }}
    header a.active {{ background: #2f80ed; color: white; }}
    main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 14px; }}
    figure {{ margin: 0; background: white; border: 1px solid #d8dee6; border-radius: 8px; overflow: hidden; }}
    img {{ width: 100%; display: block; }}
    figcaption {{ padding: 10px 12px; color: #475467; font-size: 14px; }}
    .note {{ padding: 0 14px 14px; color: #667085; }}
  </style>
</head>
<body>
  <header><strong>DexJoCo Task Scene View</strong>{links}<a class="launch" href="{launch_url}">Open native MuJoCo viewer</a><a href="/showroom?source=all&limit=120">Asset showroom</a><a href="/rubiks">Rubik demo</a></header>
  <main>
    <figure><img src="{front_url}"><figcaption>{html.escape(task_id)} / front camera</figcaption></figure>
    <figure><img src="{wrist_url}"><figcaption>{html.escape(task_id)} / wrist camera</figcaption></figure>
  </main>
  <div class="note">This page shows the actual MuJoCo task scene render: robot, table, objects, and target regions. Images are generated from the DexJoCo environment, not from the asset-only GLB showroom.</div>
</body>
</html>"""


def _launch_task_viewer(task_id: str) -> tuple[bool, str]:
    task_id = task_id if task_id in HARD_TASKS else "hard_pack_items_into_box_and_close"
    script = ROOT / "scene_lab" / "tools" / "open_task_viewer.py"
    log_dir = VIEWER_CACHE / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task_id}.log"
    python = sys.executable
    with log_path.open("ab") as log:
        subprocess.Popen(
            [python, str(script), task_id],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return True, f"Launched native MuJoCo viewer for {task_id}. Log: {log_path}"


def _launch_result_page(task_id: str) -> str:
    ok, message = _launch_task_viewer(task_id)
    status = "Started" if ok else "Failed"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{status} native viewer</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f6f8; color: #1f2933; }}
    main {{ max-width: 760px; margin: 60px auto; background: white; border: 1px solid #d8dee6; border-radius: 8px; padding: 24px; }}
    a {{ color: #2563eb; }}
    code {{ background: #eef2f6; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <main>
    <h1>{status}</h1>
    <p>{html.escape(message)}</p>
    <p>The viewer is DexJoCo's native <code>render_mode="human"</code> MuJoCo viewer. It opens as a local window, not inside this browser tab.</p>
    <p><a href="/task_scene?task={quote(task_id)}">Back to task scene page</a></p>
  </main>
</body>
</html>"""


def _viewer_page(source: str, asset_id: str) -> str:
    manifest_path = _safe_asset(source, asset_id)
    manifest = _read_json(manifest_path)
    glb = _ensure_asset_glb(manifest_path)
    glb_url = _file_url(glb)
    title = html.escape(str(manifest.get("asset_id") or manifest_path.parent.name))
    back = f"/?source={quote(source)}&asset={quote(str(manifest.get('asset_id') or manifest_path.parent.name))}"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title} 3D Viewer</title>
  {_model_viewer_script()}
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #111827; color: white; }}
    header {{ height: 52px; display: flex; align-items: center; gap: 14px; padding: 0 18px; background: #0b1220; }}
    a {{ color: #bfdbfe; text-decoration: none; }}
    model-viewer {{ width: 100vw; height: calc(100vh - 52px); background: #e5e7eb; }}
  </style>
</head>
<body>
  <header><strong>{title}</strong><a href="{back}">Back</a><a href="{glb_url}">Download GLB</a></header>
  <model-viewer src="{glb_url}" camera-controls auto-rotate shadow-intensity="1" exposure="1" ar ar-modes="webxr scene-viewer quick-look"></model-viewer>
</body>
</html>"""


def _showroom_page(source: str, limit: str) -> str:
    source = source if source in SOURCES else "all"
    selected = _selected_showroom_assets(source, limit)
    glb = _ensure_showroom_glb(source, limit)
    glb_url = _file_url(glb)
    count = len(selected)
    source_links = " ".join(
        f'<a class="{ "active" if source == item else "" }" href="/showroom?source={item}&limit={quote(limit)}">{item}</a>'
        for item in SOURCES
    )
    asset_list = "".join(
        f'<li><a href="/viewer?source={quote(source)}&asset={quote(path.parent.name)}">{html.escape(path.parent.name)}</a></li>'
        for path in selected
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Scene Lab Asset Showroom</title>
  {_model_viewer_script()}
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f6f8; color: #1f2933; }}
    header {{ height: 56px; display: flex; align-items: center; gap: 14px; padding: 0 18px; background: #101820; color: white; }}
    header a {{ color: #dbeafe; text-decoration: none; padding: 6px 10px; border-radius: 6px; }}
    header a.active {{ background: #2f80ed; color: white; }}
    main {{ display: grid; grid-template-columns: 1fr 320px; height: calc(100vh - 56px); }}
    model-viewer {{ width: 100%; height: 100%; background: #e5e7eb; }}
    aside {{ overflow: auto; background: white; border-left: 1px solid #d8dee6; padding: 12px; }}
    li {{ margin-bottom: 6px; overflow-wrap: anywhere; }}
    .note {{ color: #667085; font-size: 13px; line-height: 1.4; }}
  </style>
</head>
<body>
  <header><strong>Asset Showroom</strong><span>{count} assets</span>{source_links}<a href="/showroom?source={source}&limit=120">120</a><a href="/showroom?source={source}&limit=all">all</a><a href="{glb_url}">Download GLB</a></header>
  <main>
    <model-viewer src="{glb_url}" camera-controls auto-rotate shadow-intensity="1" exposure="1"></model-viewer>
    <aside>
      <p class="note">Google model-viewer scene generated from converted assets. Use mouse drag to rotate, wheel to zoom. Full all-assets GLB may take time the first time it is built.</p>
      <ol>{asset_list}</ol>
    </aside>
  </main>
</body>
</html>"""


def _page(source: str, asset_id: str | None) -> str:
    source = source if source in SOURCES else "all"
    assets = _assets(source)
    selected = _safe_asset(source, asset_id) if asset_id else (assets[0] if assets else None)
    rows = []
    for manifest_path in assets:
        manifest = _read_json(manifest_path)
        aid = manifest.get("asset_id") or manifest_path.parent.name
        cls = "selected" if selected and selected.parent == manifest_path.parent else ""
        rows.append(
            f'<li class="{cls}"><a href="/?source={quote(source)}&asset={quote(str(aid))}">{html.escape(str(aid))}</a>'
            f'<span>{html.escape(_asset_source(manifest_path))}</span></li>'
        )

    detail = "<p>No processed assets.</p>"
    if selected:
        manifest = _read_json(selected)
        validation = _read_json(selected.parent / "asset_validation.json")
        review = _read_json(selected.parent / "asset_review.json")
        collision = manifest.get("collision") or {}
        material = manifest.get("physical_material") or validation.get("physical_material") or {}
        contact = material.get("contact") or {}
        previews = sorted((selected.parent / "preview").glob("*.png"))
        imgs = "".join(
            f'<figure><img src="{_file_url(p)}"><figcaption>{html.escape(p.stem)}</figcaption></figure>'
            for p in previews
        ) or "<p>No previews yet. Run render_asset_previews.py.</p>"
        asset_id_text = str(manifest.get("asset_id", selected.parent.name))
        detail = f"""
        <section class="detail">
          <h2>{html.escape(asset_id_text)}</h2>
          <div class="actions">
            <a href="/viewer?source={quote(source)}&asset={quote(asset_id_text)}">Open Google 3D Viewer</a>
            <a href="/showroom?source={quote(source)}&limit=120">Open Asset Showroom</a>
          </div>
          <div class="summary">
            <div><strong>Source</strong><span>{html.escape(str(manifest.get("source_benchmark", "")))}</span></div>
            <div><strong>Category</strong><span>{html.escape(str(manifest.get("category", "")))}</span></div>
            <div><strong>Status</strong><span>{html.escape(str(manifest.get("status", "")))}</span></div>
            <div><strong>Mass</strong><span>{html.escape(str(manifest.get("mass", "")))}</span></div>
            <div><strong>Collision</strong><span>{html.escape(str(collision.get("mode") or collision.get("type") or ""))}</span></div>
            <div><strong>Collision parts</strong><span>{len(collision.get("meshes") or [])}</span></div>
            <div><strong>Friction</strong><span>{html.escape(str(contact.get("friction", "")))}</span></div>
            <div><strong>condim</strong><span>{html.escape(str(contact.get("condim", "")))}</span></div>
            <div><strong>Scale</strong><span>{html.escape(str((manifest.get("scale_policy") or {}).get("mode", "")))}</span></div>
          </div>
          <div class="previews">{imgs}</div>
          <details open><summary>asset_manifest.json</summary><pre>{html.escape(json.dumps(manifest, indent=2))}</pre></details>
          <details><summary>asset_validation.json</summary><pre>{html.escape(json.dumps(validation, indent=2))}</pre></details>
          <form method="post" action="/review">
            <input type="hidden" name="source" value="{html.escape(source)}">
            <input type="hidden" name="asset" value="{html.escape(str(manifest.get("asset_id", selected.parent.name)))}">
            <textarea name="notes" placeholder="review notes">{html.escape(str(review.get("notes", "")))}</textarea>
            <button name="decision" value="accepted">Accept</button>
            <button name="decision" value="rejected">Reject</button>
          </form>
        </section>
        """
    source_links = " ".join(
        f'<a class="{ "active" if source == item else "" }" href="/?source={item}">{item}</a>'
        for item in SOURCES
    )
    task_links = " ".join(
        f'<a href="/task_scene?task={quote(task_id)}">{html.escape(task_id)}</a>'
        for task_id in HARD_TASKS
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Scene Lab Asset Review</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f6f8; color: #1f2933; }}
    header {{ height: 54px; display: flex; align-items: center; gap: 18px; padding: 0 20px; background: #101820; color: white; }}
    header a {{ color: #dbeafe; text-decoration: none; padding: 6px 10px; border-radius: 6px; }}
    header a.active {{ background: #2f80ed; color: white; }}
    .actions {{ display: flex; gap: 10px; margin-bottom: 16px; }}
    .actions a {{ background: #2f80ed; color: white; text-decoration: none; padding: 8px 12px; border-radius: 6px; }}
    main {{ display: grid; grid-template-columns: 330px 1fr; min-height: calc(100vh - 54px); }}
    aside {{ background: white; border-right: 1px solid #d8dee6; overflow: auto; }}
    ul {{ list-style: none; margin: 0; padding: 8px; }}
    li {{ display: flex; justify-content: space-between; gap: 8px; padding: 8px; border-radius: 6px; font-size: 13px; }}
    li.selected {{ background: #e8f1ff; }}
    li a {{ color: #17324d; text-decoration: none; overflow-wrap: anywhere; }}
    li span {{ color: #6b7280; }}
    .detail {{ padding: 22px; }}
    h2 {{ margin: 0 0 14px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 18px; }}
    .summary div {{ background: white; border: 1px solid #d8dee6; border-radius: 6px; padding: 10px; }}
    .summary strong {{ display: block; font-size: 12px; color: #667085; margin-bottom: 4px; }}
    .previews {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin-bottom: 18px; }}
    figure {{ margin: 0; background: white; border: 1px solid #d8dee6; border-radius: 6px; padding: 8px; }}
    img {{ width: 100%; height: auto; display: block; }}
    figcaption {{ color: #667085; font-size: 12px; margin-top: 6px; }}
    details {{ background: white; border: 1px solid #d8dee6; border-radius: 6px; padding: 10px; margin-top: 12px; }}
    pre {{ white-space: pre-wrap; font-size: 12px; }}
    textarea {{ width: 100%; min-height: 70px; margin-top: 12px; box-sizing: border-box; }}
    button {{ margin-top: 8px; margin-right: 8px; padding: 8px 14px; border: 0; border-radius: 6px; background: #2f80ed; color: white; }}
    button[value="rejected"] {{ background: #d92d20; }}
  </style>
</head>
<body>
  <header><strong>Scene Lab Asset Review</strong><span>source</span>{source_links}<span>tasks</span>{task_links}<a href="/rubiks">rubiks</a></header>
  <main><aside><ul>{''.join(rows)}</ul></aside>{detail}</main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/asset_file/":
            rel = unquote(parsed.path.removeprefix("/asset_file/"))
        if parsed.path.startswith("/asset_file/"):
            rel = unquote(parsed.path.removeprefix("/asset_file/"))
            path = (ROOT / rel).resolve()
            if not str(path).startswith(str(ROOT.resolve())) or not path.exists():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", _content_type(path))
            self.end_headers()
            self.wfile.write(path.read_bytes())
            return
        query = parse_qs(parsed.query)
        if parsed.path == "/viewer":
            source = query.get("source", ["all"])[0]
            asset_id = query.get("asset", [""])[0]
            html_text = _viewer_page(source, asset_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_text.encode("utf-8"))
            return
        if parsed.path == "/showroom":
            source = query.get("source", ["all"])[0]
            limit = query.get("limit", ["120"])[0]
            html_text = _showroom_page(source, limit)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_text.encode("utf-8"))
            return
        if parsed.path == "/rubiks":
            html_text = _rubiks_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_text.encode("utf-8"))
            return
        if parsed.path == "/task_scene":
            task_id = query.get("task", ["hard_pack_items_into_box_and_close"])[0]
            html_text = _task_scene_page(task_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_text.encode("utf-8"))
            return
        if parsed.path == "/launch_task_viewer":
            task_id = query.get("task", ["hard_pack_items_into_box_and_close"])[0]
            html_text = _launch_result_page(task_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_text.encode("utf-8"))
            return
        html_text = _page(query.get("source", ["all"])[0], query.get("asset", [None])[0])
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_text.encode("utf-8"))

    def do_POST(self) -> None:
        if self.path != "/review":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = parse_qs(self.rfile.read(length).decode("utf-8"))
        source = data.get("source", ["all"])[0]
        asset_id = data.get("asset", [""])[0]
        decision = data.get("decision", [""])[0]
        notes = data.get("notes", [""])[0]
        manifest_path = _safe_asset(source, asset_id)
        review = {
            "asset_id": asset_id,
            "decision": decision,
            "notes": notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "review_surface": "asset_review_gui",
        }
        (manifest_path.parent / "asset_review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        self.send_response(303)
        self.send_header("Location", f"/?source={quote(source)}&asset={quote(asset_id)}")
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Serving asset review GUI at http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
