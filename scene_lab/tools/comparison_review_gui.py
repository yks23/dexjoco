#!/usr/bin/env python
"""Comparison review GUI for original asset views vs Scene Lab previews."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "scene_lab" / "registry"
BUCKETS = ("pending", "accepted", "rejected")


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


def _candidates(bucket: str) -> list[Path]:
    root = REGISTRY / bucket
    root.mkdir(parents=True, exist_ok=True)
    return sorted(
        p
        for p in root.glob("pick_place_robotwin_*")
        if p.is_dir() and (p / "comparison" / "comparison.json").exists()
    )


def _img(bucket: str, candidate: str, rel: str, label: str) -> str:
    if not rel:
        return f'<figure class="missing"><div>missing</div><figcaption>{html.escape(label)}</figcaption></figure>'
    return (
        f'<figure><img src="/file/{bucket}/{html.escape(candidate)}/{html.escape(rel)}">'
        f"<figcaption>{html.escape(label)}</figcaption></figure>"
    )


def _page(bucket: str = "pending") -> str:
    if bucket not in BUCKETS:
        bucket = "pending"
    rows = []
    for candidate in _candidates(bucket):
        comparison = _read_json(candidate / "comparison" / "comparison.json")
        validation = _read_json(candidate / "validation.json")
        asset = _read_json(candidate / "asset_manifest.json")
        original = comparison.get("original_views", {})
        middleware = comparison.get("middleware_views", {})
        actions = ""
        if bucket == "pending":
            actions = f"""
            <form method="POST" action="/review">
              <input type="hidden" name="bucket" value="pending">
              <input type="hidden" name="name" value="{html.escape(candidate.name)}">
              <textarea name="notes" placeholder="Review notes"></textarea>
              <div class="buttons">
                <button class="accept" name="decision" value="accepted">✓ OK</button>
                <button class="reject" name="decision" value="rejected">✕ Reject</button>
              </div>
            </form>
            """
        rows.append(
            f"""
            <article class="card">
              <div class="title">
                <h2>{html.escape(candidate.name.replace("pick_place_robotwin_", ""))}</h2>
                <span>{html.escape(str(asset.get("asset_id", "")))}</span>
                <span class="status">validation: {html.escape(str(validation.get("ok", "missing")))}</span>
              </div>
              <div class="compare">
                <section>
                  <h3>RoboTwin Asset</h3>
                  <div class="views">
                    {_img(bucket, candidate.name, original.get("front"), "front")}
                    {_img(bucket, candidate.name, original.get("side"), "side")}
                    {_img(bucket, candidate.name, original.get("top"), "top")}
                  </div>
                </section>
                <section>
                  <h3>Scene Lab / DexJoCo</h3>
                  <div class="views">
                    {_img(bucket, candidate.name, middleware.get("front"), "front")}
                    {_img(bucket, candidate.name, middleware.get("side"), "side")}
                    {_img(bucket, candidate.name, middleware.get("wrist"), "wrist")}
                  </div>
                </section>
              </div>
              {actions}
            </article>
            """
        )
    nav = " ".join(
        f'<a class="{("active" if b == bucket else "")}" href="/?bucket={b}">{b}</a>'
        for b in BUCKETS
    )
    content = "".join(rows) if rows else "<p>No comparison candidates in this bucket.</p>"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>RoboTwin Comparison Review</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #202124; background: #f5f6f7; }}
    header {{ position: sticky; top: 0; z-index: 2; background: white; border-bottom: 1px solid #d9dce0; padding: 12px 18px; display: flex; gap: 18px; align-items: center; }}
    header a {{ color: #2f5f91; text-decoration: none; }}
    header a.active {{ color: #111; font-weight: 700; }}
    main {{ padding: 18px; display: grid; gap: 18px; }}
    .card {{ background: white; border: 1px solid #d8dde3; border-radius: 8px; padding: 14px; }}
    .title {{ display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; }}
    h2 {{ margin: 0; font-size: 18px; }}
    h3 {{ margin: 10px 0 8px; font-size: 14px; }}
    .status {{ color: #51606f; }}
    .compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .views {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    figure {{ margin: 0; border: 1px solid #d8dde3; background: white; }}
    img {{ width: 100%; display: block; aspect-ratio: 4 / 3; object-fit: contain; background: white; }}
    figcaption {{ padding: 5px 7px; font-size: 12px; color: #586473; border-top: 1px solid #e5e8eb; }}
    .missing div {{ aspect-ratio: 4 / 3; display: grid; place-items: center; color: #8a94a3; }}
    textarea {{ width: 100%; height: 56px; margin-top: 12px; box-sizing: border-box; }}
    .buttons {{ display: flex; gap: 10px; margin-top: 8px; }}
    button {{ border: 1px solid #c9d0d8; background: #fff; padding: 8px 16px; border-radius: 6px; font-size: 15px; cursor: pointer; }}
    button.accept {{ border-color: #138a45; color: #0a6d35; }}
    button.reject {{ border-color: #b33a3a; color: #972222; }}
    @media (max-width: 980px) {{ .compare {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header><strong>RoboTwin Comparison Review</strong>{nav}</header>
  <main>{content}</main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/file/"):
            self._serve_file(parsed.path)
            return
        bucket = parse_qs(parsed.query).get("bucket", ["pending"])[0]
        body = _page(bucket).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
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
            "review_surface": "comparison_review_gui",
        }
        (src / "review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        self.send_response(303)
        self.send_header("Location", "/?bucket=pending")
        self.end_headers()

    def _serve_file(self, request_path: str) -> None:
        parts = [unquote(p) for p in request_path.split("/")[2:]]
        if len(parts) < 3:
            self.send_error(404)
            return
        bucket, name = parts[0], parts[1]
        base = _safe_candidate(bucket, name)
        target = (base / Path(*parts[2:])).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.exists():
            self.send_error(404)
            return
        body = target.read_bytes()
        content_type = "image/png" if target.suffix.lower() == ".png" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
