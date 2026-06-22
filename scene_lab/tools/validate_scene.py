#!/usr/bin/env python
"""Validate a generated scene candidate and render static preview images."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _extract_images(obs: dict[str, Any]) -> dict[str, np.ndarray]:
    images: dict[str, np.ndarray] = {}
    nested = obs.get("images")
    if isinstance(nested, dict):
        for key, value in nested.items():
            if isinstance(value, np.ndarray):
                images[key] = value
    for key, value in obs.items():
        if key in ("state", "images"):
            continue
        if isinstance(value, np.ndarray) and value.ndim == 3:
            images[key] = value
    return images


def _state_summary(state: Any) -> dict[str, Any]:
    if hasattr(state, "shape"):
        return {"shape": list(state.shape)}
    if isinstance(state, dict):
        return {
            "keys": sorted(state.keys()),
            "shapes": {
                key: list(value.shape) if hasattr(value, "shape") else None
                for key, value in state.items()
            },
        }
    return {"shape": None}


def validate_candidate(candidate_dir: Path, episodes_steps: int = 3) -> dict[str, Any]:
    task_path = candidate_dir / "task.json"
    result: dict[str, Any] = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_dir": str(candidate_dir),
        "ok": False,
        "checks": {},
        "errors": [],
        "previews": [],
    }

    if not task_path.exists():
        result["errors"].append("Missing task.json")
        return result

    task = json.loads(task_path.read_text(encoding="utf-8"))
    result["task_id"] = task.get("task_id")
    asset_manifest_path = candidate_dir / "asset_manifest.json"
    if asset_manifest_path.exists():
        asset_manifest = json.loads(asset_manifest_path.read_text(encoding="utf-8"))
        result["asset"] = {
            "asset_id": asset_manifest.get("asset_id"),
            "source_benchmark": asset_manifest.get("source_benchmark"),
            "category": asset_manifest.get("category"),
            "status": asset_manifest.get("status"),
            "visual_mesh": asset_manifest.get("visual_mesh"),
            "collision": asset_manifest.get("collision"),
            "mass": asset_manifest.get("mass"),
        }
    result["success_condition"] = task.get("success_condition", {})
    entrypoint = task.get("simulator", {}).get("entrypoint", {})
    mapping_key = (
        task.get("simulator", {})
        .get("entrypoint", {})
        .get("config_mapping_key")
    )
    xml_path = entrypoint.get("xml_path")

    try:
        if mapping_key:
            from dexjoco.tasks import CONFIG_MAPPING

            result["checks"]["config_mapping_key_exists"] = mapping_key in CONFIG_MAPPING
            if mapping_key not in CONFIG_MAPPING:
                result["errors"].append(f"Unknown CONFIG_MAPPING key: {mapping_key}")
                return result

            env = CONFIG_MAPPING[mapping_key]().get_environment(
                policy_mode=True,
                render_mode="rgb_array",
                randomize=False,
            )
        else:
            if not xml_path:
                result["errors"].append(
                    "Missing simulator.entrypoint.config_mapping_key or xml_path"
                )
                return result
            from scene_lab.runtime.generated_scene_env import PandaGeneratedSceneEnv

            scene_path = Path(xml_path)
            if not scene_path.is_absolute():
                scene_path = candidate_dir / scene_path
            result["checks"]["scene_xml_exists"] = scene_path.exists()
            if not scene_path.exists():
                result["errors"].append(f"Missing scene XML: {scene_path}")
                return result
            env = PandaGeneratedSceneEnv(
                xml_path=scene_path,
                task=task,
                render_mode="rgb_array",
            )
        try:
            obs, info = env.reset()
            result["checks"]["reset_ok"] = True
            result["reset_info"] = {k: _jsonable(v) for k, v in info.items()}

            state = obs.get("state")
            images = _extract_images(obs)
            result["observation"] = {
                "keys": sorted(obs.keys()),
                "state": _state_summary(state),
                "image_keys": sorted(images.keys()),
            }

            for _ in range(episodes_steps):
                obs, rew, terminated, truncated, info = env.step(env.action_space.sample() * 0)
                if terminated or truncated:
                    break
            result["checks"]["step_ok"] = True
            result["last_step"] = {
                "reward": float(rew),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "info": {k: _jsonable(v) for k, v in info.items()},
            }
            if isinstance(info, dict) and isinstance(info.get("predicate"), dict):
                result["predicate"] = info["predicate"]

            preview_dir = candidate_dir / "preview"
            preview_dir.mkdir(exist_ok=True)
            images = _extract_images(obs)
            for image_key, frame in images.items():
                image_path = preview_dir / f"{image_key}.png"
                imageio.imwrite(image_path, frame)
                result["previews"].append(str(image_path.relative_to(candidate_dir)))
                result.setdefault("preview_stats", {})[image_key] = {
                    "shape": list(frame.shape),
                    "mean": float(np.mean(frame)),
                }
            result["checks"]["render_ok"] = bool(result["previews"])
        finally:
            env.close()

    except Exception as exc:  # pragma: no cover - CLI diagnostic path
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        result["traceback"] = traceback.format_exc()

    result["ok"] = not result["errors"] and all(result["checks"].values())
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--steps", type=int, default=3)
    args = parser.parse_args()

    candidate_dir = args.candidate_dir.resolve()
    result = validate_candidate(candidate_dir, episodes_steps=args.steps)
    output_path = candidate_dir / "validation.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(output_path)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
