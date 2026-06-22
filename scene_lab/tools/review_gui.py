#!/usr/bin/env python
"""Tiny file-based static review GUI for Scene Lab candidates."""

from __future__ import annotations

import argparse
import html
import io
import json
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "scene_lab" / "registry"
BUCKETS = ("pending", "accepted", "rejected")
SOURCES = ("all", "ycb", "robotwin")
_RENDER_CACHE: dict[Path, "_SceneRenderCache"] = {}
_PANDA_HOME = (0.0, -0.785, 0.0, -2.35, 0.0, 1.57, 0.7853981633974483)
_ALLEGRO_HOME = (
    0.0,
    0.35,
    0.25,
    0.15,
    0.0,
    0.35,
    0.25,
    0.15,
    0.0,
    0.35,
    0.25,
    0.15,
    0.72,
    0.18,
    0.25,
    0.15,
)
_ALLEGRO_JOINT_NAMES = (
    "ffj0",
    "ffj1",
    "ffj2",
    "ffj3",
    "mfj0",
    "mfj1",
    "mfj2",
    "mfj3",
    "rfj0",
    "rfj1",
    "rfj2",
    "rfj3",
    "thj0",
    "thj1",
    "thj2",
    "thj3",
)
_ALLEGRO_ACTUATOR_NAMES = (
    "ffa0",
    "ffa1",
    "ffa2",
    "ffa3",
    "mfa0",
    "mfa1",
    "mfa2",
    "mfa3",
    "rfa0",
    "rfa1",
    "rfa2",
    "rfa3",
    "tha0",
    "tha1",
    "tha2",
    "tha3",
)


def _apply_robot_home(mujoco, model, data) -> None:
    for index, value in enumerate(_PANDA_HOME, start=1):
        try:
            data.qpos[model.joint(f"joint{index}").qposadr] = value
        except KeyError:
            pass
    for name, value in zip(_ALLEGRO_JOINT_NAMES, _ALLEGRO_HOME):
        try:
            data.qpos[model.joint(name).qposadr] = value
        except KeyError:
            pass
    for name, value in zip(_ALLEGRO_ACTUATOR_NAMES, _ALLEGRO_HOME):
        try:
            data.ctrl[model.actuator(name).id] = value
        except KeyError:
            pass
    mujoco.mj_forward(model, data)
    if model.nmocap:
        try:
            data.mocap_pos[0] = data.sensor("franka/flange_pos").data
            data.mocap_quat[0] = data.sensor("franka/flange_quat").data
            mujoco.mj_forward(model, data)
        except KeyError:
            pass


class _SceneRenderCache:
    def __init__(self, scene_xml: Path):
        import mujoco

        self.mujoco = mujoco
        self.model = mujoco.MjModel.from_xml_path(scene_xml.as_posix())
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=720, width=960, max_geom=20000)
        self.lock = threading.Lock()

    def render(self, *, azimuth: float, elevation: float, distance: float) -> bytes:
        import imageio.v2 as imageio

        with self.lock:
            self.mujoco.mj_resetData(self.model, self.data)
            _apply_robot_home(self.mujoco, self.model, self.data)
            camera = self.mujoco.MjvCamera()
            camera.type = self.mujoco.mjtCamera.mjCAMERA_FREE
            camera.lookat[:] = [0.0, 0.0, 0.92]
            camera.distance = max(0.2, float(distance))
            camera.azimuth = float(azimuth)
            camera.elevation = float(elevation)
            self.renderer.update_scene(self.data, camera=camera)
            frame = self.renderer.render()
        buffer = io.BytesIO()
        imageio.imwrite(buffer, frame, format="png")
        return buffer.getvalue()


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".obj": "text/plain; charset=utf-8",
        ".mtl": "text/plain; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }.get(suffix, "application/octet-stream")


def _candidate_dirs(bucket: str) -> list[Path]:
    root = REGISTRY / bucket
    root.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in root.iterdir() if p.is_dir())


def _safe_candidate(bucket: str, name: str) -> Path:
    if bucket not in BUCKETS:
        raise ValueError("bad bucket")
    candidate = (REGISTRY / bucket / name).resolve()
    if not str(candidate).startswith(str((REGISTRY / bucket).resolve())):
        raise ValueError("bad candidate")
    return candidate


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_source(candidate: Path) -> str:
    asset = _read_json(candidate / "asset_manifest.json")
    if asset.get("source_benchmark"):
        return str(asset["source_benchmark"])
    task = _read_json(candidate / "task.json")
    return str(task.get("generator", {}).get("source_benchmark", "unknown"))


def _asset_url(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).resolve()
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return None
    return "/asset/" + quote(str(rel), safe="/")


def _candidate_file_url(bucket: str, candidate: Path, rel: str) -> str | None:
    path = candidate / rel
    if not path.exists():
        return None
    return f"/file/{bucket}/{quote(candidate.name)}/{quote(rel, safe='/')}"


def _page(bucket: str, name: str | None = None, source: str = "all") -> str:
    all_candidates = _candidate_dirs(bucket)
    candidates = [
        item
        for item in all_candidates
        if source == "all" or _candidate_source(item) == source
    ]
    selected = None
    if name:
        maybe_selected = _safe_candidate(bucket, name)
        if maybe_selected.exists() and maybe_selected in candidates:
            selected = maybe_selected
    if selected is None:
        selected = candidates[0] if candidates else None
    rows = []
    for item in candidates:
        cls = "selected" if selected and item.name == selected.name else ""
        rows.append(
            f'<li class="{cls}"><a href="/?bucket={bucket}&source={source}&name={html.escape(item.name)}">'
            f"{html.escape(item.name)}</a><span>{html.escape(_candidate_source(item))}</span></li>"
        )

    detail = "<p>No candidates in this bucket.</p>"
    if selected:
        task = _read_json(selected / "task.json")
        validation = _read_json(selected / "validation.json")
        review = _read_json(selected / "review.json")
        asset = _read_json(selected / "asset_manifest.json")
        success = task.get("success_condition", {})
        asset_card = "<p>No asset_manifest.json for this candidate.</p>"
        if asset:
            collision = asset.get("collision", {})
            collision_desc = collision.get("mode") or collision.get("type") or ""
            asset_card = f"""
            <div class="asset-card">
              <div><strong>Asset:</strong> {html.escape(str(asset.get("asset_id", "")))}</div>
              <div><strong>Source:</strong> {html.escape(str(asset.get("source_benchmark", "")))}</div>
              <div><strong>Category:</strong> {html.escape(str(asset.get("category", "")))}</div>
              <div><strong>Status:</strong> {html.escape(str(asset.get("status", "")))}</div>
              <div><strong>Collision:</strong> {html.escape(str(collision_desc))}</div>
              <div><strong>Mass:</strong> {html.escape(str(asset.get("mass", "")))}</div>
            </div>
            """
        previews = sorted((selected / "preview").glob("*.png"))
        preview_by_name = {p.stem: p for p in previews}
        primary_preview = (
            preview_by_name.get("front")
            or preview_by_name.get("side")
            or preview_by_name.get("wrist")
            or (previews[0] if previews else None)
        )
        scene_url = _candidate_file_url(bucket, selected, "scene.xml")
        viewer = ""
        if scene_url:
            if primary_preview is not None:
                render_url = (
                    f"/file/{bucket}/{quote(selected.name)}/preview/"
                    f"{quote(primary_preview.name)}"
                )
                render_hint = "Validated MuJoCo preview"
            else:
                render_url = (
                    f"/render_scene?bucket={quote(bucket)}&name={quote(selected.name)}"
                )
                render_hint = "MuJoCo scene render"
            viewer = f"""
            <h3>Scene Render</h3>
            <div id="viewer" class="viewer">
              <div class="viewer-hint">{html.escape(render_hint)}</div>
              <img id="scene-render" src="{html.escape(render_url)}" alt="MuJoCo scene render" draggable="false">
            </div>
            <form method="POST" action="/launch_viewer" class="viewer-actions" target="viewer-launch-result">
              <input type="hidden" name="bucket" value="{html.escape(bucket)}">
              <input type="hidden" name="name" value="{html.escape(selected.name)}">
              <button type="submit">Open Native MuJoCo Viewer</button>
              <span class="viewer-note">Opens a local MuJoCo window for the full scene.xml.</span>
            </form>
            <iframe name="viewer-launch-result" class="launch-result"></iframe>
            """
        imgs = "".join(
            f'<figure><img src="/file/{bucket}/{selected.name}/preview/{p.name}">'
            f"<figcaption>{html.escape(p.stem)}</figcaption></figure>"
            for p in previews
        )
        if not imgs:
            imgs = "<p>No previews yet. Run validate_scene.py for this candidate.</p>"

        actions = ""
        if bucket == "pending":
            actions = f"""
            <form method="POST" action="/review">
              <input type="hidden" name="bucket" value="{bucket}">
              <input type="hidden" name="name" value="{html.escape(selected.name)}">
              <textarea name="notes" placeholder="Review notes"></textarea>
              <div class="buttons">
                <button name="decision" value="accepted">Accept</button>
                <button name="decision" value="rejected">Reject</button>
              </div>
            </form>
            """

        detail = f"""
        <h2>{html.escape(selected.name)}</h2>
        <p><strong>Instruction:</strong> {html.escape(task.get("instruction", ""))}</p>
        {asset_card}
        <div class="predicate"><strong>Success:</strong> {html.escape(str(success.get("type", "")))} {html.escape(json.dumps(success.get("params", {})))}</div>
        {viewer}
        <h3>Rendered Previews</h3>
        <div class="previews">{imgs}</div>
        {actions}
        """

    nav = " ".join(
        f'<a class="{("active" if b == bucket else "")}" href="/?bucket={b}&source={source}">{b}</a>'
        for b in BUCKETS
    )
    source_nav = " ".join(
        f'<a class="{("active" if s == source else "")}" href="/?bucket={bucket}&source={s}">{s}</a>'
        for s in SOURCES
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Scene Lab Review</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #202124; }}
    header {{ padding: 12px 18px; border-bottom: 1px solid #ddd; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }}
    header a {{ color: #315a8a; text-decoration: none; }}
    header a.active {{ font-weight: 700; color: #111; }}
    main {{ display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 50px); }}
    aside {{ border-right: 1px solid #ddd; padding: 14px; background: #f7f7f7; }}
    li {{ margin: 8px 0; }}
    li span {{ display: block; color: #777; font-size: 12px; }}
    li.selected a {{ font-weight: 700; }}
    section {{ padding: 18px; }}
    .filter {{ display: flex; gap: 10px; margin-left: auto; }}
    .asset-card {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px 16px; border: 1px solid #ddd; background: #fafafa; padding: 12px; overflow-wrap: anywhere; }}
    .predicate {{ margin: 12px 0 16px; padding: 10px 12px; border: 1px solid #ddd; background: #f8f9fa; overflow-wrap: anywhere; }}
    .viewer {{ position: relative; height: min(66vh, 680px); min-height: 420px; border: 1px solid #cfd4dc; background: #eef1f4; margin: 12px 0 10px; }}
    .viewer img {{ display: block; width: 100%; height: 100%; object-fit: contain; user-select: none; -webkit-user-drag: none; }}
    .viewer-hint {{ position: absolute; left: 12px; top: 10px; z-index: 2; color: #4d5663; background: rgba(255,255,255,.82); padding: 5px 8px; font-size: 13px; }}
    .viewer-actions {{ display: flex; align-items: center; gap: 12px; margin: 0 0 20px; }}
    .viewer-note {{ color: #5f6875; font-size: 13px; }}
    .launch-result {{ width: 0; height: 0; border: 0; position: absolute; left: -9999px; }}
    .previews {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
    figure {{ margin: 0; border: 1px solid #ddd; padding: 8px; background: white; }}
    img {{ width: 100%; height: auto; display: block; }}
    figcaption {{ margin-top: 6px; color: #666; }}
    textarea {{ width: 100%; height: 80px; margin-top: 16px; }}
    .buttons {{ margin: 10px 0 20px; display: flex; gap: 10px; }}
    button {{ padding: 8px 14px; }}
    pre {{ background: #f4f4f4; border: 1px solid #ddd; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <header><strong>Scene Lab Review</strong>{nav}<div class="filter"><strong>source</strong>{source_nav}</div></header>
  <main>
    <aside><ul>{''.join(rows)}</ul></aside>
    <section>{detail}</section>
  </main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/file/"):
            self._serve_file(parsed.path)
            return
        if parsed.path.startswith("/asset/"):
            self._serve_asset(parsed.path)
            return
        if parsed.path == "/render_scene":
            self._serve_scene_render(parsed.query)
            return
        qs = parse_qs(parsed.query)
        bucket = qs.get("bucket", ["pending"])[0]
        name = qs.get("name", [None])[0]
        source = qs.get("source", ["all"])[0]
        if bucket not in BUCKETS:
            bucket = "pending"
        if source not in SOURCES:
            source = "all"
        body = _page(bucket, name, source).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path == "/launch_viewer":
            self._launch_viewer()
            return
        if self.path != "/review":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = parse_qs(self.rfile.read(length).decode("utf-8"))
        bucket = data.get("bucket", ["pending"])[0]
        name = data.get("name", [""])[0]
        decision = data.get("decision", [""])[0]
        notes = data.get("notes", [""])[0]
        if bucket != "pending" or decision not in ("accepted", "rejected"):
            self.send_error(400)
            return
        src = _safe_candidate(bucket, name)
        dst = REGISTRY / decision / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        review = {
            "decision": decision,
            "notes": notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        (src / "review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        self.send_response(303)
        self.send_header("Location", f"/?bucket={decision}&name={dst.name}")
        self.end_headers()

    def _launch_viewer(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = parse_qs(self.rfile.read(length).decode("utf-8"))
        bucket = data.get("bucket", ["pending"])[0]
        name = data.get("name", [""])[0]
        try:
            candidate = _safe_candidate(bucket, name)
            scene_xml = candidate / "scene.xml"
            if not scene_xml.exists():
                self.send_error(404, "Missing scene.xml")
                return
            _launch_native_viewer(candidate)
        except Exception as exc:
            self.send_error(500, f"Launch failed: {exc}")
            return
        body = b"Native MuJoCo viewer launched."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, request_path: str) -> None:
        parts = [unquote(p) for p in request_path.split("/")[2:]]
        if len(parts) < 2:
            self.send_error(404)
            return
        bucket = parts[0]
        name = parts[1]
        base = _safe_candidate(bucket, name)
        target = (base / Path(*parts[2:])).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.exists():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _content_type(target))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_asset(self, request_path: str) -> None:
        rel = unquote(request_path.removeprefix("/asset/"))
        target = (ROOT / rel).resolve()
        if not str(target).startswith(str(ROOT.resolve())) or not target.exists() or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _content_type(target))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_scene_render(self, query: str) -> None:
        qs = parse_qs(query)
        bucket = qs.get("bucket", ["pending"])[0]
        name = qs.get("name", [""])[0]
        try:
            candidate = _safe_candidate(bucket, name)
            scene_xml = candidate / "scene.xml"
            if not scene_xml.exists():
                self.send_error(404, "Missing scene.xml")
                return
            azimuth = float(qs.get("azimuth", ["145"])[0])
            elevation = float(qs.get("elevation", ["-28"])[0])
            distance = float(qs.get("distance", ["1.9"])[0])
            body = _render_scene_png(scene_xml, azimuth=azimuth, elevation=elevation, distance=distance)
        except Exception as exc:
            self.send_error(500, f"Render failed: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _render_scene_png(scene_xml: Path, *, azimuth: float, elevation: float, distance: float) -> bytes:
    scene_xml = scene_xml.resolve()
    cache = _RENDER_CACHE.get(scene_xml)
    if cache is None:
        cache = _SceneRenderCache(scene_xml)
        _RENDER_CACHE[scene_xml] = cache
    return cache.render(azimuth=azimuth, elevation=elevation, distance=distance)


def _launch_native_viewer(candidate: Path) -> None:
    mjpython = Path(sys.executable).with_name("mjpython")
    executable = str(mjpython if mjpython.exists() else Path(sys.executable))
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "import time\n"
        "import mujoco\n"
        "import mujoco.viewer\n"
        "from scene_lab.runtime.generated_scene_env import PandaGeneratedSceneEnv\n"
        "candidate = Path(sys.argv[1])\n"
        "task = json.loads((candidate / 'task.json').read_text(encoding='utf-8'))\n"
        "env = PandaGeneratedSceneEnv(candidate / 'scene.xml', task, render_mode='none')\n"
        "env.reset()\n"
        "viewer = mujoco.viewer.launch_passive(env.model, env.data)\n"
        "while viewer.is_running():\n"
        "    with viewer.lock():\n"
        "        mujoco.mj_forward(env.model, env.data)\n"
        "    viewer.sync()\n"
        "    time.sleep(0.03)\n"
        "env.close()\n"
    )
    subprocess.Popen(
        [executable, "-c", code, str(candidate.resolve())],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=(candidate / "viewer_stderr.log").open("ab"),
        start_new_session=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    for bucket in BUCKETS:
        (REGISTRY / bucket).mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
