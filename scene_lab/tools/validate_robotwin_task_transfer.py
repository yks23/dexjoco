#!/usr/bin/env python
"""Validate generated RoboTwin task transfer candidates and write a summary."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import read_json, write_json  # noqa: E402
from scene_lab.tools.validate_scene import validate_candidate  # noqa: E402


def _is_robotwin_transfer(candidate_dir: Path) -> bool:
    task_path = candidate_dir / "task.json"
    if not task_path.exists():
        return False
    try:
        task = read_json(task_path)
    except Exception:
        return False
    return task.get("generator", {}).get("kind") == "robotwin_task_transfer"


def _load_generation_summary(pending: Path) -> dict[str, Any]:
    path = pending.parent / "robotwin_task_generation_summary.json"
    if path.exists():
        return read_json(path)
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    candidates = [path for path in sorted(args.pending.iterdir()) if path.is_dir() and _is_robotwin_transfer(path)]
    if args.limit is not None:
        candidates = candidates[: args.limit]

    validations = []
    ok_count = 0
    for candidate in candidates:
        result = validate_candidate(candidate.resolve(), episodes_steps=args.steps)
        write_json(candidate / "validation.json", result)
        ok_count += int(bool(result.get("ok")))
        validations.append(
            {
                "task_id": candidate.name,
                "ok": bool(result.get("ok")),
                "errors": result.get("errors", []),
                "previews": result.get("previews", []),
                "asset": result.get("asset", {}),
                "success_condition": result.get("success_condition", {}),
            }
        )

    generation = _load_generation_summary(args.pending)
    summary = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "pending": str(args.pending),
        "candidate_count": len(candidates),
        "compiled_ok": ok_count,
        "compiled_bad": len(candidates) - ok_count,
        "registered_spec_count": generation.get("registered_spec_count", 0),
        "failed_generation_count": generation.get("failed_count", 0),
        "registered_specs": generation.get("registered_specs", []),
        "failed_generation": generation.get("failed", []),
        "validations": validations,
    }
    write_json(args.summary, summary)
    print(args.summary)
    if summary["compiled_bad"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
