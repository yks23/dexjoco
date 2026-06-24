"""DexJoCo-native Panda + Allegro environments for transferred RoboTwin tasks."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

import mujoco
import numpy as np
from gymnasium import spaces
from scipy.spatial.transform import Rotation as R

from ..controllers import opspace
from ..mujoco_gym_env import MujocoGymEnv
from ..rendering import MujocoRenderer

_PANDA_HOME = np.asarray((0, -0.785, 0, -2.35, 0, 1.57, np.pi / 4), dtype=np.float64)
_ALLEGRO_HOME = np.asarray(
    (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.263, 0, 0, 0),
    dtype=np.float32,
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
_ALLEGRO_SENSOR_NAMES = (
    "allegro_right/ffj0_pos",
    "allegro_right/ffj1_pos",
    "allegro_right/ffj2_pos",
    "allegro_right/ffj3_pos",
    "allegro_right/mfj0_pos",
    "allegro_right/mfj1_pos",
    "allegro_right/mfj2_pos",
    "allegro_right/mfj3_pos",
    "allegro_right/rfj0_pos",
    "allegro_right/rfj1_pos",
    "allegro_right/rfj2_pos",
    "allegro_right/rfj3_pos",
    "allegro_right/thj0_pos",
    "allegro_right/thj1_pos",
    "allegro_right/thj2_pos",
    "allegro_right/thj3_pos",
)
_N_ALLEGRO = len(_ALLEGRO_JOINT_NAMES)
_MAX_EPISODE_STEPS = 800


def _predicate(
    predicate_type: str,
    object_pos: np.ndarray,
    target_pos: np.ndarray,
    params: dict[str, Any],
    object_quat: np.ndarray | None = None,
) -> dict[str, Any]:
    if predicate_type in {"object_near_site", "object_near_object"}:
        radius = float(params.get("radius", params.get("xy_radius", 0.08)))
        xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
        ok = xy_distance <= radius
        return {"ok": ok, "xy_distance": xy_distance, "radius": radius}
    if predicate_type == "object_lifted":
        min_z = float(params.get("min_z", params.get("height", 0.98)))
        z = float(object_pos[2])
        return {"ok": z >= min_z, "z": z, "min_z": min_z}
    if predicate_type == "object_in_region":
        radius = float(params.get("radius", params.get("xy_radius", 0.08)))
        min_z = float(params.get("min_z", 0.90))
        xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
        z = float(object_pos[2])
        return {
            "ok": xy_distance <= radius and z >= min_z,
            "xy_distance": xy_distance,
            "radius": radius,
            "z": z,
            "min_z": min_z,
        }
    if predicate_type in {"object_contact_object", "tool_contact_target"}:
        radius = float(params.get("radius", 0.06))
        xyz_distance = float(np.linalg.norm(object_pos - target_pos))
        return {
            "ok": xyz_distance <= radius,
            "xyz_distance": xyz_distance,
            "radius": radius,
            "contact_is_approximated": True,
        }
    if predicate_type in {"object_pose_relative_to_object", "objects_stacked"}:
        xy_radius = float(params.get("xy_radius", params.get("radius", 0.04)))
        z_offset = float(params.get("z_offset", 0.05))
        z_tolerance = float(params.get("z_tolerance", 0.025))
        xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
        z_error = float(abs((object_pos[2] - target_pos[2]) - z_offset))
        return {
            "ok": xy_distance <= xy_radius and z_error <= z_tolerance,
            "xy_distance": xy_distance,
            "xy_radius": xy_radius,
            "z_error": z_error,
            "z_offset": z_offset,
            "z_tolerance": z_tolerance,
        }
    if predicate_type == "object_above_object":
        xy_radius = float(params.get("xy_radius", params.get("radius", 0.05)))
        min_z_offset = float(params.get("min_z_offset", 0.025))
        max_z_offset = float(params.get("max_z_offset", 0.20))
        xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
        z_offset = float(object_pos[2] - target_pos[2])
        return {
            "ok": xy_distance <= xy_radius and min_z_offset <= z_offset <= max_z_offset,
            "xy_distance": xy_distance,
            "xy_radius": xy_radius,
            "z_offset": z_offset,
            "min_z_offset": min_z_offset,
            "max_z_offset": max_z_offset,
        }
    if predicate_type == "object_tilted_toward_site":
        if object_quat is None:
            return {"ok": False, "reason": "object_tilted_toward_site requires object_quat"}
        max_up_dot = float(params.get("max_up_dot", 0.55))
        xy_radius = float(params.get("xy_radius", 0.12))
        quat_xyzw = np.asarray([object_quat[1], object_quat[2], object_quat[3], object_quat[0]])
        local_z_world = R.from_quat(quat_xyzw).as_matrix()[:, 2]
        up_dot = float(local_z_world @ np.asarray([0.0, 0.0, 1.0]))
        xy_distance = float(np.linalg.norm(object_pos[:2] - target_pos[:2]))
        return {
            "ok": up_dot <= max_up_dot and xy_distance <= xy_radius,
            "up_dot": up_dot,
            "max_up_dot": max_up_dot,
            "xy_distance": xy_distance,
            "xy_radius": xy_radius,
            "proxy_note": "Proxy for pouring: object is tilted near the target container.",
        }
    if predicate_type == "object_facing_site":
        if object_quat is None:
            return {"ok": False, "reason": "object_facing_site requires object_quat"}
        min_dot = float(params.get("min_dot", 0.65))
        local_axis = np.asarray(params.get("local_axis", [1.0, 0.0, 0.0]), dtype=np.float64)
        quat_xyzw = np.asarray([object_quat[1], object_quat[2], object_quat[3], object_quat[0]])
        axis_world = R.from_quat(quat_xyzw).as_matrix() @ local_axis
        target_vec = target_pos - object_pos
        norm = float(np.linalg.norm(target_vec))
        if norm <= 1e-8:
            return {"ok": False, "reason": "object and target are colocated"}
        dot = float(axis_world @ (target_vec / norm))
        return {
            "ok": dot >= min_dot,
            "dot": dot,
            "min_dot": min_dot,
            "proxy_note": "Proxy for presenting: a chosen object local axis faces the target site.",
        }
    return {
        "ok": False,
        "reason": f"Unsupported RoboTwin predicate in native DexJoCo env: {predicate_type}",
    }


class PandaRoboTwinTaskGymEnv(MujocoGymEnv):
    """Native DexJoCo runtime for a transferred single-arm RoboTwin task."""

    def __init__(
        self,
        task_spec: dict[str, Any],
        render_mode: Literal["rgb_array", "human", "none"],
        randomize: bool,
        seed: int = 0,
        control_dt: float = 0.02,
        physics_dt: float = 0.002,
        hz: int = 30,
    ):
        self.task_spec = task_spec
        self.hz = hz
        self.randomize = randomize
        self.render_mode = render_mode
        self.image_obs = render_mode != "none"
        self.env_step = 0

        xml_path = Path(task_spec["xml_path"])
        super().__init__(
            xml_path=xml_path,
            seed=seed,
            control_dt=control_dt,
            physics_dt=physics_dt,
        )

        self._panda_dof_ids = np.asarray(
            [self._model.joint(f"joint{i}").id for i in range(1, 8)]
        )
        self._panda_ctrl_ids = np.asarray(
            [self._model.actuator(f"actuator{i}").id for i in range(1, 8)]
        )
        self._site_id = self._model.site("attachment_site").id
        self._allegro_dof_ids = np.asarray(
            [int(self._model.joint(name).qposadr) for name in _ALLEGRO_JOINT_NAMES],
            dtype=int,
        )
        self._allegro_ctrl_ids = np.asarray(
            [self._model.actuator(name).id for name in _ALLEGRO_ACTUATOR_NAMES],
            dtype=int,
        )

        success = task_spec.get("success_condition", {})
        self._object_specs = list(task_spec.get("objects", []))
        if not self._object_specs:
            self._object_specs = [
                {
                    "name": success.get("object", "object"),
                    "pose": task_spec["object_pose"],
                    "role": "primary",
                }
            ]
        self._object_names = [obj.get("name", "object") for obj in self._object_specs]
        self._object_name = success.get("object", self._object_names[0])
        self._target_name = success.get("target", "goal_center")
        self._predicate_type = success.get("type", "object_in_region")
        self._predicate_params = dict(success.get("params", {}))
        self._success_conditions = list(task_spec.get("success_conditions", []))
        if not self._success_conditions:
            self._success_conditions = [success]
        self._object_body_id = int(self._model.body(self._object_name).id)
        self._target_site_id = int(self._model.site(self._target_name).id)
        self._object_joint_qposadrs = {
            name: int(self._model.joint(f"{name}_root").qposadr) for name in self._object_names
        }
        self._initial_object_poses = {
            obj.get("name", "object"): np.asarray(obj["pose"], dtype=np.float64)
            for obj in self._object_specs
        }
        self._object_joint_qposadr = self._object_joint_qposadrs[self._object_name]
        self._initial_object_pose = self._initial_object_poses[self._object_name]

        self._mj_viewer = None
        if self.image_obs:
            self._mj_viewer = MujocoRenderer(self.model, self.data)
            self._mj_viewer.render(self.render_mode)
        self._front_camera_id = int(self._model.camera("front").id)
        self._wrist_camera_id = int(self._model.camera("handcam_rgb").id)

        image_h = int(self._model.vis.global_.offheight)
        image_w = int(self._model.vis.global_.offwidth)
        self.observation_space = spaces.Dict(
            {
                "state": spaces.Dict(
                    {
                        "tcp_pose": spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float64),
                        "gripper_pose": spaces.Box(-np.inf, np.inf, shape=(_N_ALLEGRO,), dtype=np.float64),
                        "object_pose": spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float64),
                        "goal_pose": spaces.Box(-np.inf, np.inf, shape=(3,), dtype=np.float64),
                    }
                )
            }
        )
        if self.image_obs:
            self.observation_space["images"] = spaces.Dict(
                {
                    "wrist": spaces.Box(0, 255, shape=(image_h, image_w, 3), dtype=np.uint8),
                    "front": spaces.Box(0, 255, shape=(image_h, image_w, 3), dtype=np.uint8),
                }
            )

        self.action_space = spaces.Box(
            low=np.full(7 + _N_ALLEGRO, -1.0, dtype=np.float32),
            high=np.full(7 + _N_ALLEGRO, 1.0, dtype=np.float32),
            dtype=np.float32,
        )

    def reset(self, seed=None, **kwargs):
        mujoco.mj_resetData(self._model, self._data)
        for name, pose in self._initial_object_poses.items():
            qposadr = self._object_joint_qposadrs[name]
            self._data.qpos[qposadr : qposadr + 7] = pose
        self._data.qpos[self._panda_dof_ids] = _PANDA_HOME
        self._data.qpos[self._allegro_dof_ids] = _ALLEGRO_HOME
        self._data.ctrl[self._allegro_ctrl_ids] = _ALLEGRO_HOME
        mujoco.mj_forward(self._model, self._data)

        tcp_pos = self._data.sensor("franka/flange_pos").data
        tcp_quat = self._data.sensor("franka/flange_quat").data
        self._data.mocap_pos[0] = tcp_pos
        self._data.mocap_quat[0] = tcp_quat
        self.env_step = 0
        mujoco.mj_forward(self._model, self._data)
        self._prime_rgb_array_renderer()
        predicate = self._compute_predicate()
        return self._compute_observation(), {"succeed": bool(predicate["ok"]), "predicate": predicate}

    def step(self, action: np.ndarray):
        start_time = time.time()
        action = np.asarray(action, dtype=np.float64)
        xyz = action[:3]
        wxyz_quat = action[3:7]
        allegro_angles = np.asarray(action[7 : 7 + _N_ALLEGRO], dtype=np.float64)
        if np.allclose(allegro_angles, 0.0):
            allegro_angles = _ALLEGRO_HOME

        if not (np.allclose(xyz, 0.0) and np.allclose(wxyz_quat, 0.0)):
            self._data.mocap_pos[0] = xyz
            self._data.mocap_quat[0] = wxyz_quat

        for _ in range(self._n_substeps):
            tau = opspace(
                model=self._model,
                data=self._data,
                site_id=self._site_id,
                dof_ids=self._panda_dof_ids,
                pos=self._data.mocap_pos[0],
                ori=self._data.mocap_quat[0],
                joint=_PANDA_HOME,
                gravity_comp=True,
                pos_gains=(400.0, 400.0, 400.0),
                damping_ratio=4,
            )
            self._data.ctrl[self._panda_ctrl_ids] = tau
            self._data.ctrl[self._allegro_ctrl_ids] = allegro_angles
            mujoco.mj_step(self._model, self._data)

        obs = self._compute_observation()
        self.env_step += 1
        predicate = self._compute_predicate()
        success = bool(predicate["ok"])
        terminated = self.env_step >= _MAX_EPISODE_STEPS or success

        if self.render_mode == "human":
            self._mj_viewer.render("human")

        dt = time.time() - start_time
        time.sleep(max(0, (1.0 / self.hz) - dt))
        return obs, 1.0 if success else 0.0, terminated, False, {"succeed": success, "predicate": predicate}

    def _compute_predicate(self) -> dict[str, Any]:
        results = []
        for condition in self._success_conditions:
            object_name = condition.get("object", self._object_name)
            target_name = condition.get("target", self._target_name)
            predicate_type = condition.get("type", self._predicate_type)
            params = dict(condition.get("params", {}))
            object_body = self._data.body(object_name)
            object_pos = object_body.xpos.copy()
            object_quat = object_body.xquat.copy()
            target_pos = self._target_position(target_name)
            result = _predicate(predicate_type, object_pos, target_pos, params, object_quat)
            result["predicate_type"] = predicate_type
            result["object"] = object_name
            result["target"] = target_name
            result["object_pos"] = object_pos.tolist()
            result["target_pos"] = target_pos.tolist()
            results.append(result)
        ok = all(bool(result["ok"]) for result in results)
        if len(results) == 1:
            result = dict(results[0])
            result["ok"] = ok
            return result
        return {"ok": ok, "mode": "all", "conditions": results}

    def _target_position(self, name: str) -> np.ndarray:
        try:
            return self._data.site(name).xpos.copy()
        except KeyError:
            return self._data.body(name).xpos.copy()

    def _compute_success(self) -> bool:
        return bool(self._compute_predicate()["ok"])

    def render(self):
        if self._mj_viewer is None:
            raise RuntimeError("Rendering is disabled because render_mode='none'.")
        wrist_frame = self._mj_viewer.render(
            render_mode="rgb_array",
            camera_id=self._wrist_camera_id,
        )
        front_frame = self._mj_viewer.render(
            render_mode="rgb_array",
            camera_id=self._front_camera_id,
        )
        return wrist_frame, front_frame

    def _compute_observation(self) -> dict[str, Any]:
        tcp_pos = self._data.sensor("franka/flange_pos").data
        tcp_quat = self._data.sensor("franka/flange_quat").data
        allegro_qpos = np.array(
            [float(self._data.sensor(name).data) for name in _ALLEGRO_SENSOR_NAMES],
            dtype=np.float32,
        )
        obs = {
            "state": {
                "tcp_pose": np.concatenate([tcp_pos, tcp_quat]),
                "gripper_pose": allegro_qpos,
                "object_pose": np.concatenate(
                    [
                        self._data.body(self._object_name).xpos.copy(),
                        self._data.body(self._object_name).xquat.copy(),
                    ]
                ),
                "goal_pose": self._data.site_xpos[self._target_site_id].copy(),
            }
        }
        if self.image_obs:
            wrist_frame, front_frame = self.render()
            obs["images"] = {"wrist": wrist_frame, "front": front_frame}
        return obs

    def _prime_rgb_array_renderer(self) -> None:
        if self._mj_viewer is None:
            return
        self._mj_viewer.render(render_mode="rgb_array", camera_id=self._front_camera_id)
        self._mj_viewer.render(render_mode="rgb_array", camera_id=self._wrist_camera_id)

    def close(self):
        viewer = getattr(self, "_mj_viewer", None)
        if viewer is not None:
            try:
                viewer.close()
            except Exception:
                pass
        super().close()

    def get_end_effector_pose_matrix(self) -> np.ndarray:
        pos = self._data.mocap_pos[0]
        quat = self._data.mocap_quat[0]
        quat = np.array([quat[1], quat[2], quat[3], quat[0]])
        rot_mat = R.from_quat(quat).as_matrix()
        transform = np.eye(4)
        transform[:3, :3] = rot_mat
        transform[:3, 3] = pos
        return transform
