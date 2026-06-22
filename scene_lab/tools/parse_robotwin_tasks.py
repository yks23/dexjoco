#!/usr/bin/env python
"""Parse RoboTwin env files into Scene Lab task transfer specs.

The parser is intentionally static: it does not import RoboTwin or execute
Sapien code.  It extracts enough structure for batch transfer and records
unsupported dynamic pieces in the resulting spec.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_lab.asset_pipeline import write_json  # noqa: E402

ROBOTWIN_OBJECT_RE = re.compile(r"\b[0-9]{3}_[A-Za-z0-9_-]+\b")
TASK_FILES_TO_SKIP = {"__init__.py", "_base_task.py", "_GLOBAL_CONFIGS.py"}
ARTICULATED_SKILLS = {"open_articulated_object", "turn_knob_or_rotate_object"}
COMPLEX_SKILLS = {"handover_object"}


def _safe_literal(node: ast.AST) -> Any:
    if not isinstance(
        node,
        (
            ast.Constant,
            ast.List,
            ast.Tuple,
            ast.Dict,
            ast.Set,
            ast.UnaryOp,
        ),
    ):
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _attr_name(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _keyword(call: ast.Call, *names: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg in names:
            return kw.value
    return None


def _eval_node(node: ast.AST, names: dict[str, Any]) -> Any:
    literal = _safe_literal(node)
    if literal is not None:
        return literal
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute):
        attr = _attr_name(node)
        if attr:
            return names.get(attr)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _eval_node(node.operand, names)
        if isinstance(value, (int, float)):
            return -value
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, names)
        right = _eval_node(node.right, names)
        if isinstance(node.op, ast.Add) and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left + right
        if isinstance(node.op, ast.Sub) and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left - right
        if isinstance(node.op, ast.Mult) and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left * right
        if isinstance(node.op, ast.Div) and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left / right
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name.endswith("np.random.randint") or name.endswith("random.randint"):
            args = [_eval_node(arg, names) for arg in node.args]
            if len(args) == 1 and isinstance(args[0], int):
                return list(range(args[0]))
            if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], int):
                return list(range(args[0], args[1]))
        if name.endswith("np.random.choice") or name.endswith("random.choice"):
            if node.args:
                values = _eval_node(node.args[0], names)
                if isinstance(values, tuple):
                    return list(values)
                return values
        if name.endswith("np.array") and node.args:
            return _eval_node(node.args[0], names)
    if isinstance(node, ast.Subscript):
        container = _eval_node(node.value, names)
        index = _eval_node(node.slice, names)
        if isinstance(container, (list, tuple)) and isinstance(index, int):
            if 0 <= index < len(container):
                return container[index]
        if isinstance(container, dict) and not isinstance(index, (list, dict, set)) and index in container:
            return container[index]
    return None


def _collect_assignments(tree: ast.AST) -> dict[str, Any]:
    names: dict[str, Any] = {}
    assigns = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    for _ in range(3):
        changed = False
        for node in assigns:
            value = _eval_node(node.value, names)
            if value is None:
                continue
            for target in node.targets:
                key = _attr_name(target) if isinstance(target, ast.Attribute) else target.id if isinstance(target, ast.Name) else None
                if key and names.get(key) != value:
                    names[key] = value
                    changed = True
        if not changed:
            break
    return names


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _asset_id_for(modelname: str, model_id: Any | None) -> str:
    normalized = modelname.replace("-", "_")
    if model_id is None:
        return f"robotwin_{normalized}"
    return f"robotwin_{normalized}_base{model_id}"


def _extract_call_assets(tree: ast.AST, names: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = _call_name(node.func).split(".")[-1]
        if call not in {
            "create_actor",
            "rand_create_actor",
            "rand_create_sapien_urdf_obj",
            "create_box",
        }:
            continue
        if call == "create_box":
            assets.append(
                {
                    "kind": "procedural_box",
                    "role_hint": "box",
                    "source_call": call,
                    "half_size": _eval_node(_keyword(node, "half_size") or ast.Constant(None), names),
                    "color": _eval_node(_keyword(node, "color") or ast.Constant(None), names),
                }
            )
            continue
        model_node = _keyword(node, "modelname")
        modelname = _eval_node(model_node, names) if model_node else None
        model_id_node = _keyword(node, "model_id", "modelid")
        model_ids = _as_list(_eval_node(model_id_node, names) if model_id_node else None)
        if isinstance(modelname, list):
            modelnames = [value for value in modelname if isinstance(value, str)]
        elif isinstance(modelname, str):
            modelnames = [modelname]
        else:
            modelnames = []
        if not modelnames:
            assets.append(
                {
                    "kind": "robotwin_mesh",
                    "source_call": call,
                    "modelname": "dynamic",
                    "model_ids": [],
                    "asset_ids": [],
                    "dynamic": True,
                }
            )
            continue
        if not model_ids:
            model_ids = [None]
        for name in modelnames:
            ids = [value for value in model_ids if isinstance(value, int) or value is None]
            assets.append(
                {
                    "kind": "robotwin_mesh",
                    "source_call": call,
                    "modelname": name,
                    "model_ids": ids,
                    "asset_ids": [_asset_id_for(name, model_id) for model_id in ids],
                    "dynamic": False,
                    "articulated_source": call == "rand_create_sapien_urdf_obj",
                }
            )
    return assets


def _skill_alignment(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {task["robotwin_task"]: task for task in data.get("tasks", [])}


def _skill_sequence(source: str) -> list[str]:
    calls = []
    for name in (
        "grasp_actor",
        "move_by_displacement",
        "place_actor",
        "open_gripper",
        "close_gripper",
        "move_to_pose",
        "check_actors_contact",
        "pick_and_place",
        "pick_and_place_block",
    ):
        if name in source:
            calls.append(name)
    return calls


def _predicate_for(task_name: str, skill: str, source: str) -> dict[str, Any]:
    if skill == "lift_object":
        return {"type": "object_lifted", "params": {"min_z": 0.82}}
    if skill == "stack_objects":
        return {"type": "objects_stacked", "params": {"xy_radius": 0.04, "z_offset": 0.05}}
    if skill == "tool_use_strike":
        return {"type": "tool_contact_target", "params": {"radius": 0.06}}
    if skill == "press_button_or_tool":
        return {"type": "tool_contact_target", "params": {"radius": 0.045}}
    if skill == "open_articulated_object":
        return {"type": "articulation_joint_threshold", "params": {"threshold": "source_check_success"}}
    if skill == "pick_object":
        return {"type": "object_lifted", "params": {"min_z": 0.82}}
    if "check_actors_contact" in source:
        return {"type": "object_contact_object", "params": {"radius": 0.08}}
    return {"type": "object_in_region", "params": {"xy_radius": 0.08, "min_z": 0.90}}


def parse_task(path: Path, alignment: dict[str, dict[str, str]]) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    task_name = path.stem
    aligned = alignment.get(task_name, {})
    skill = aligned.get("scene_lab_skill_family", "unclassified")
    names = _collect_assignments(tree)
    assets = _extract_call_assets(tree, names)
    object_mentions = sorted(set(ROBOTWIN_OBJECT_RE.findall(source)))
    unsupported = []
    if skill in ARTICULATED_SKILLS:
        unsupported.append("articulated_runtime")
    if skill in COMPLEX_SKILLS:
        unsupported.append("bimanual_runtime")
    if any(asset.get("dynamic") for asset in assets):
        unsupported.append("dynamic_asset_selection")
    if "rand_create_sapien_urdf_obj" in source:
        unsupported.append("sapien_urdf_source")
    transfer_status = "executable"
    if skill in ARTICULATED_SKILLS or skill in COMPLEX_SKILLS:
        transfer_status = "registered_spec"
    elif not assets and not object_mentions:
        transfer_status = "failed"
        unsupported.append("no_assets_detected")

    return {
        "source_task": task_name,
        "source_file": str(path),
        "skill_family": skill,
        "skill_description": aligned.get("skill_description", ""),
        "instruction_hint": aligned.get("instruction_hint", task_name.replace("_", " ")),
        "assets": assets,
        "object_mentions": object_mentions,
        "sampling": {
            key: value
            for key, value in names.items()
            if key.endswith("_id") or key.endswith("_name") or key in {"model_id", "model_name"}
        },
        "skill_sequence": _skill_sequence(source),
        "success_predicate": _predicate_for(task_name, skill, source),
        "transfer_status": transfer_status,
        "unsupported_features": sorted(set(unsupported)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--alignment",
        type=Path,
        default=ROOT / "scene_lab" / "benchmarks" / "robotwin_skill_alignment.json",
    )
    args = parser.parse_args()

    alignment = _skill_alignment(args.alignment)
    tasks = [
        parse_task(path, alignment)
        for path in sorted(args.source.glob("*.py"))
        if path.name not in TASK_FILES_TO_SKIP
    ]
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(args.source),
        "task_count": len(tasks),
        "tasks": tasks,
        "status_counts": {
            status: sum(1 for task in tasks if task["transfer_status"] == status)
            for status in sorted({task["transfer_status"] for task in tasks})
        },
    }
    write_json(args.out, data)
    print(args.out)


if __name__ == "__main__":
    main()
