#!/usr/bin/env python
"""Build a PDF review packet for RoboTwin asset previews."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
PENDING = ROOT / "scene_lab" / "registry" / "pending"


_TMP_IMAGES: list[Path] = []


def _trim_whitespace(image_path: Path, padding: int = 14) -> Path:
    with Image.open(image_path) as src:
        image = src.convert("RGB")
        arr = np.asarray(image)
        mask = np.any(arr < 245, axis=2)
        ys, xs = np.where(mask)
        if not len(xs) or not len(ys):
            return image_path
        left = max(0, int(xs.min()) - padding)
        top = max(0, int(ys.min()) - padding)
        right = min(image.width, int(xs.max()) + padding + 1)
        bottom = min(image.height, int(ys.max()) + padding + 1)
        cropped = image.crop((left, top, right, bottom))
        tmp = Path(tempfile.NamedTemporaryFile(suffix=".png", delete=False).name)
        cropped.save(tmp)
        _TMP_IMAGES.append(tmp)
        return tmp


def _fit_draw(
    c: canvas.Canvas,
    image_path: Path,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    trim_white: bool = False,
) -> None:
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.rect(x, y, w, h, stroke=1, fill=0)
    if not image_path.exists():
        c.setFillColor(colors.HexColor("#b91c1c"))
        c.setFont("Helvetica", 7)
        c.drawCentredString(x + w / 2, y + h / 2, "missing")
        return

    draw_path = _trim_whitespace(image_path) if trim_white else image_path
    with Image.open(draw_path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(
        str(draw_path),
        x + (w - dw) / 2,
        y + (h - dh) / 2,
        dw,
        dh,
        preserveAspectRatio=True,
        mask="auto",
    )


def _draw_label(c: canvas.Canvas, text: str, x: float, y: float, size: int = 7) -> None:
    c.setFont("Helvetica", size)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(x, y, text)


def _asset_title(candidate_dir: Path) -> tuple[str, str]:
    manifest_path = candidate_dir / "asset_manifest.json"
    if not manifest_path.exists():
        return candidate_dir.name, ""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    category = str(manifest.get("category") or "")
    variant = str(manifest.get("robotwin_variant") or "")
    calib = manifest.get("dexjoco_calibration", {})
    extents = calib.get("calibrated_extents_m") or []
    extents_text = ", ".join(f"{float(v):.3f}" for v in extents[:3])
    subtitle = f"{manifest.get('asset_id')} | {category}"
    if variant:
        subtitle += f" | {variant}"
    if extents_text:
        subtitle += f" | extents(m): [{extents_text}]"
    return str(manifest.get("robotwin_object_id") or candidate_dir.name), subtitle


def _draw_candidate(c: canvas.Canvas, candidate_dir: Path, index: int, x: float, y: float, w: float, h: float) -> None:
    title, subtitle = _asset_title(candidate_dir)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y + h - 5 * mm, f"{index:03d}. {title}")
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 7)
    c.drawString(x, y + h - 9 * mm, subtitle[:150])

    gap = 3 * mm
    label_h = 3.5 * mm
    mesh_h = 42 * mm
    scene_h = 30 * mm
    img_w = (w - 2 * gap) / 3
    mesh_y = y + h - 9 * mm - label_h - mesh_h
    scene_y = y + 8 * mm

    for col, name in enumerate(("front", "side", "top")):
        ix = x + col * (img_w + gap)
        _draw_label(c, f"converted asset {name}", ix, mesh_y + mesh_h + 1.2 * mm)
        _fit_draw(
            c,
            candidate_dir / "comparison" / f"original_{name}.png",
            ix,
            mesh_y,
            img_w,
            mesh_h,
            trim_white=True,
        )

    for col, name in enumerate(("front", "side", "wrist")):
        ix = x + col * (img_w + gap)
        _draw_label(c, f"scene {name}", ix, scene_y + scene_h + 1.2 * mm)
        _fit_draw(c, candidate_dir / "preview" / f"{name}.png", ix, scene_y, img_w, scene_h)

    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.rect(x, y + 1.6 * mm, 4 * mm, 4 * mm)
    _draw_label(c, "OK", x + 5.5 * mm, y + 2.2 * mm, 8)
    c.rect(x + 22 * mm, y + 1.6 * mm, 4 * mm, 4 * mm)
    _draw_label(c, "Reject", x + 27.5 * mm, y + 2.2 * mm, 8)


def build_pdf(candidate_dirs: list[Path], output: Path, sample: int | None = None) -> Path:
    if sample:
        candidate_dirs = candidate_dirs[:sample]

    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = landscape(A4)
    margin = 10 * mm
    gap = 7 * mm
    card_w = page_w - 2 * margin
    card_h = (page_h - 2 * margin - gap) / 2

    c = canvas.Canvas(str(output), pagesize=landscape(A4))
    total = len(candidate_dirs)
    for offset in range(0, total, 2):
        page = offset // 2 + 1
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, page_h - margin + 1 * mm, "RoboTwin -> Scene Lab Asset Preview Packet")
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica", 8)
        c.drawRightString(page_w - margin, page_h - margin + 1 * mm, f"Page {page} | assets {offset + 1}-{min(offset + 2, total)} / {total}")

        for slot, candidate_dir in enumerate(candidate_dirs[offset : offset + 2]):
            y = page_h - margin - (slot + 1) * card_h - slot * gap
            _draw_candidate(c, candidate_dir, offset + slot + 1, margin, y, card_w, card_h)
        c.showPage()
    c.save()
    for path in _TMP_IMAGES:
        try:
            path.unlink()
        except OSError:
            pass
    return output


def _bulk_candidates() -> list[Path]:
    summary_path = PENDING / "robotwin_bulk_import_summary.json"
    if not summary_path.exists():
        return []
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    candidates = []
    for item in summary.get("results", []):
        if not item.get("candidate_created"):
            continue
        asset_id = item.get("asset_id")
        if asset_id:
            candidates.append(PENDING / f"pick_place_{asset_id}")
    return [path for path in candidates if (path / "asset_manifest.json").exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "pdf" / "robotwin_all_asset_preview_zoom.pdf")
    parser.add_argument("--sample", type=int)
    args = parser.parse_args()

    candidates = _bulk_candidates()
    if not candidates:
        candidates = sorted(PENDING.glob("pick_place_robotwin_*"))
        candidates = [path for path in candidates if (path / "asset_manifest.json").exists()]
    out = build_pdf(candidates, args.output, sample=args.sample)
    print(out)


if __name__ == "__main__":
    main()
