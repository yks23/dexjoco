#!/usr/bin/env python
"""Build a RoboTwin task-to-Scene-Lab skill alignment table."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROBOTWIN_ENVS = ROOT / "third_party" / "assets" / "robotwin" / "envs"
OUT_JSON = ROOT / "scene_lab" / "benchmarks" / "robotwin_skill_alignment.json"
OUT_MD = ROOT / "scene_lab" / "benchmarks" / "robotwin_skill_alignment.md"


RULES = [
    (("handover",), "handover_object", "bimanual transfer"),
    (("stack",), "stack_objects", "stacking and spatial ordering"),
    (("open",), "open_articulated_object", "articulated opening"),
    (("press", "click", "stamp"), "press_button_or_tool", "short contact / tool actuation"),
    (("turn", "rotate"), "turn_knob_or_rotate_object", "rotational manipulation"),
    (("shake", "dump"), "pour_or_shake_container", "container dynamics"),
    (("lift",), "lift_object", "grasp and lift"),
    (("pick",), "pick_object", "targeted picking"),
    (("place", "put", "move"), "pick_place_object", "pick and place"),
    (("scan",), "scan_or_present_object", "pose/orientation presentation"),
    (("beat",), "tool_use_strike", "tool use / striking"),
    (("blocks_ranking",), "sort_or_rank_objects", "ordering and sorting"),
]


def _skill_for(task_name: str) -> tuple[str, str]:
    for tokens, skill, description in RULES:
        if any(token in task_name for token in tokens):
            return skill, description
    return "unclassified", "needs manual taxonomy review"


def _instruction_hint(task_name: str) -> str:
    return task_name.replace("_", " ")


def build_alignment(env_root: Path) -> list[dict]:
    tasks = []
    for path in sorted(env_root.glob("*.py")):
        name = path.stem
        if name.startswith("_") or name == "__init__":
            continue
        skill, description = _skill_for(name)
        tasks.append(
            {
                "robotwin_task": name,
                "scene_lab_skill_family": skill,
                "skill_description": description,
                "instruction_hint": _instruction_hint(name),
                "source_file": str(path.relative_to(ROOT)),
            }
        )
    return tasks


def write_markdown(tasks: list[dict], path: Path) -> None:
    lines = [
        "# RoboTwin Skill Alignment",
        "",
        "This table maps RoboTwin task env names to first-pass Scene Lab skill families.",
        "It is rule-based and should be refined during human review.",
        "",
        "| RoboTwin task | Scene Lab skill family | Notes |",
        "| --- | --- | --- |",
    ]
    for task in tasks:
        lines.append(
            f"| `{task['robotwin_task']}` | `{task['scene_lab_skill_family']}` | {task['skill_description']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-root", type=Path, default=ROBOTWIN_ENVS)
    args = parser.parse_args()
    tasks = build_alignment(args.env_root)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"task_count": len(tasks), "tasks": tasks}, indent=2) + "\n", encoding="utf-8")
    write_markdown(tasks, OUT_MD)
    print(OUT_JSON)
    print(OUT_MD)
    print(json.dumps({"task_count": len(tasks)}, indent=2))


if __name__ == "__main__":
    main()
