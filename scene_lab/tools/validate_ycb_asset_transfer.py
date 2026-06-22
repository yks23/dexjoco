#!/usr/bin/env python
"""Validate generated YCB pick/place candidates and write a summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.tools.validate_scene import validate_candidate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", type=Path, default=ROOT / "scene_lab" / "registry" / "pending")
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "scene_lab" / "registry" / "ycb_asset_transfer_summary.json",
    )
    args = parser.parse_args()

    pending = args.pending.resolve()
    candidates = sorted(
        path
        for path in pending.glob("pick_place_ycb_*")
        if (path / "task.json").exists()
    )
    results = []
    for candidate in candidates:
        result = validate_candidate(candidate)
        (candidate / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        results.append(
            {
                "task_id": result.get("task_id") or candidate.name,
                "candidate_dir": str(candidate),
                "ok": bool(result.get("ok")),
                "errors": result.get("errors", []),
                "previews": result.get("previews", []),
            }
        )
    summary = {
        "candidate_count": len(candidates),
        "ok": sum(1 for item in results if item["ok"]),
        "bad": sum(1 for item in results if not item["ok"]),
        "results": results,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(args.summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    if summary["bad"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
