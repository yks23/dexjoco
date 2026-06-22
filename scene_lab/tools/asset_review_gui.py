#!/usr/bin/env python
"""Asset-only review GUI for processed Scene Lab assets."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "scene_lab" / "assets" / "processed"
SOURCES = ("all", "ycb", "robotwin")


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
        ".json": "application/json; charset=utf-8",
        ".xml": "text/xml; charset=utf-8",
        ".obj": "text/plain; charset=utf-8",
        ".mtl": "text/plain; charset=utf-8",
    }.get(path.suffix.lower(), "application/octet-stream")


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
        detail = f"""
        <section class="detail">
          <h2>{html.escape(str(manifest.get("asset_id", selected.parent.name)))}</h2>
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
  <header><strong>Scene Lab Asset Review</strong><span>source</span>{source_links}</header>
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
