"""Small predicate registry for Scene Lab generated task validation."""

from __future__ import annotations

from typing import Any

import numpy as np


def object_near_site(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    radius = float(params.get("radius", params.get("xy_radius", 0.08)))
    xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
    ok = xy_distance <= radius
    return {
        "ok": ok,
        "xy_distance": xy_distance,
        "radius": radius,
        "reason": "ok" if ok else f"xy_distance {xy_distance:.4f} exceeds radius {radius:.4f}",
    }


def object_lifted(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    min_z = float(params.get("min_z", params.get("height", 1.0)))
    z = float(object_pos[2])
    ok = z >= min_z
    return {
        "ok": ok,
        "z": z,
        "min_z": min_z,
        "reason": "ok" if ok else f"object z {z:.4f} is below min_z {min_z:.4f}",
    }


def object_in_region(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    near = object_near_site(object_pos, target_pos, params)
    min_z = float(params.get("min_z", 0.0))
    z = float(object_pos[2])
    z_ok = z >= min_z
    ok = bool(near["ok"] and z_ok)
    reason = "ok"
    if not near["ok"]:
        reason = near["reason"]
    elif not z_ok:
        reason = f"object z {z:.4f} is below min_z {min_z:.4f}"
    return {
        "ok": ok,
        "xy_distance": near["xy_distance"],
        "radius": near["radius"],
        "z": z,
        "min_z": min_z,
        "reason": reason,
    }


def object_near_object(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    return object_near_site(object_pos, target_pos, params)


def object_pose_relative_to_object(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    xy_radius = float(params.get("xy_radius", params.get("radius", 0.08)))
    z_offset = float(params.get("z_offset", 0.0))
    z_tolerance = float(params.get("z_tolerance", 0.04))
    xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
    z_error = float(abs((object_pos[2] - target_pos[2]) - z_offset))
    ok = xy_distance <= xy_radius and z_error <= z_tolerance
    reason = "ok"
    if xy_distance > xy_radius:
        reason = f"xy_distance {xy_distance:.4f} exceeds radius {xy_radius:.4f}"
    elif z_error > z_tolerance:
        reason = f"z_error {z_error:.4f} exceeds tolerance {z_tolerance:.4f}"
    return {
        "ok": ok,
        "xy_distance": xy_distance,
        "xy_radius": xy_radius,
        "z_error": z_error,
        "z_offset": z_offset,
        "z_tolerance": z_tolerance,
        "reason": reason,
    }


def objects_stacked(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    params = {**params}
    params.setdefault("z_offset", 0.05)
    params.setdefault("z_tolerance", 0.025)
    return object_pose_relative_to_object(object_pos, target_pos, params)


def object_contact_object(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    params = {**params}
    params.setdefault("radius", 0.06)
    result = object_near_site(object_pos, target_pos, params)
    result["contact_is_approximated"] = True
    return result


def tool_contact_target(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    result = object_contact_object(object_pos, target_pos, params)
    result["tool_contact_is_approximated"] = True
    return result


def articulation_joint_threshold(
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": "articulation_joint_threshold is registered but not executable in PandaGeneratedSceneEnv",
        "required_joint": params.get("joint"),
        "threshold": params.get("threshold"),
    }


PREDICATES = {
    "object_near_site": object_near_site,
    "object_lifted": object_lifted,
    "object_in_region": object_in_region,
    "object_near_object": object_near_object,
    "object_pose_relative_to_object": object_pose_relative_to_object,
    "objects_stacked": objects_stacked,
    "object_contact_object": object_contact_object,
    "tool_contact_target": tool_contact_target,
    "articulation_joint_threshold": articulation_joint_threshold,
}


def evaluate_predicate(
    predicate_type: str,
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
) -> dict[str, Any]:
    if predicate_type not in PREDICATES:
        return {
            "ok": False,
            "reason": f"Unsupported predicate type: {predicate_type}",
            "predicate_type": predicate_type,
        }
    result = PREDICATES[predicate_type](object_pos, target_pos, params)
    result["predicate_type"] = predicate_type
    return result
