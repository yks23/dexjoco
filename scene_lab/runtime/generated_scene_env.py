"""Generic Panda + Allegro env for Scene Lab generated MJCF candidates."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

import mujoco
import numpy as np
from gymnasium import spaces
from scipy.spatial.transform import Rotation as R

from dexjoco.sim.controllers import opspace
from dexjoco.sim.mujoco_gym_env import MujocoGymEnv
from dexjoco.sim.rendering import MujocoRenderer
from scene_lab.predicates import evaluate_predicate


_PANDA_HOME = np.asarray((0, -0.785, 0, -2.35, 0, 1.57, np.pi / 4), dtype=np.float64)
_ALLEGRO_HOME = np.asarray(
    (
        0.0,
        0.35,
        0.25,
        0.15,
        0.0,
        0.35,
        0.25,
        0.15,
        0.0,
        0.35,
        0.25,
        0.15,
        0.72,
        0.18,
        0.25,
        0.15,
    ),
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


class PandaGeneratedSceneEnv(MujocoGymEnv):
    """Load a generated MJCF scene and expose a stable static-review env.

    The generated scene must include the standard DexJoCo single-arm
    `panda_allegro_copy.xml` robot and should define:

    - a freejoint manipulated object named by `success_condition.object`
    - a target site named by `success_condition.target`
    - cameras named `front` and `handcam_rgb`
    """

    def __init__(
        self,
        xml_path: str | Path,
        task: dict[str, Any],
        render_mode: Literal["rgb_array", "human", "none"] = "rgb_array",
        seed: int = 0,
        control_dt: float = 0.02,
        physics_dt: float = 0.002,
        hz: int = 30,
    ):
        self.xml_path = Path(xml_path)
        self.task = task
        self.hz = hz
        self.render_mode = render_mode
        self.image_obs = render_mode != "none"

        success = task.get("success_condition", {})
        self._object_name = success.get("object", "book")
        self._target_name = success.get("target", "goal_center")
        self._predicate_type = success.get("type", "object_near_site")
        self._predicate_params = dict(success.get("params", {}))
        self._predicate_params.setdefault("radius", success.get("radius", 0.08))
        if "min_z" in success:
            self._predicate_params.setdefault("min_z", success["min_z"])
        self._success_radius = float(success.get("radius", 0.08))

        super().__init__(
            xml_path=self.xml_path,
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
            [int(self._model.joint(n).qposadr) for n in _ALLEGRO_JOINT_NAMES],
            dtype=int,
        )
        self._allegro_ctrl_ids = np.asarray(
            [self._model.actuator(name).id for name in _ALLEGRO_ACTUATOR_NAMES],
            dtype=int,
        )

        self._object_body_id = int(self._model.body(self._object_name).id)
        self._target_site_id = int(self._model.site(self._target_name).id)
        self._object_joint_qposadr = None
        root_joint = f"{self._object_name}_root"
        try:
            self._object_joint_qposadr = int(self._model.joint(root_joint).qposadr)
        except KeyError:
            self._object_joint_qposadr = None

        self._initial_object_pose = self._find_initial_object_pose()

        self._mj_viewer = None
        if self.image_obs:
            self._mj_viewer = MujocoRenderer(self.model, self.data)
            self._mj_viewer.render(self.render_mode)
        self._front_camera_id = int(self._model.camera("front").id)
        self._side_camera_id = int(self._model.camera("side").id)
        self._wrist_camera_id = int(self._model.camera("handcam_rgb").id)

        image_h = int(self._model.vis.global_.offheight)
        image_w = int(self._model.vis.global_.offwidth)
        self.observation_space = spaces.Dict(
            {
                "state": spaces.Dict(
                    {
                        "tcp_pose": spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float64),
                        "gripper_pose": spaces.Box(
                            -np.inf, np.inf, shape=(_N_ALLEGRO,), dtype=np.float64
                        ),
                        "object_pose": spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float64),
                        "target_pose": spaces.Box(-np.inf, np.inf, shape=(3,), dtype=np.float64),
                    }
                )
            }
        )
        if self.image_obs:
            self.observation_space["images"] = spaces.Dict(
                {
                    "front": spaces.Box(0, 255, shape=(image_h, image_w, 3), dtype=np.uint8),
                    "side": spaces.Box(0, 255, shape=(image_h, image_w, 3), dtype=np.uint8),
                    "wrist": spaces.Box(0, 255, shape=(image_h, image_w, 3), dtype=np.uint8),
                }
            )

        self.action_space = spaces.Box(
            low=np.full(7 + _N_ALLEGRO, -1.0, dtype=np.float32),
            high=np.full(7 + _N_ALLEGRO, 1.0, dtype=np.float32),
            dtype=np.float32,
        )
        self.env_step = 0

    def _find_initial_object_pose(self) -> np.ndarray:
        for obj in self.task.get("objects", []):
            if obj.get("name") == self._object_name and len(obj.get("pose", [])) >= 7:
                return np.asarray(obj["pose"][:7], dtype=np.float64)
        pos = np.asarray(self._model.body(self._object_name).pos, dtype=np.float64)
        quat = np.asarray(self._model.body(self._object_name).quat, dtype=np.float64)
        return np.concatenate([pos, quat])

    def reset(self, seed=None, **kwargs):
        mujoco.mj_resetData(self._model, self._data)

        if self._object_joint_qposadr is not None:
            start = self._object_joint_qposadr
            self._data.qpos[start : start + 7] = self._initial_object_pose

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

        if self._mj_viewer is not None:
            self._mj_viewer.render(render_mode="rgb_array", camera_id=self._front_camera_id)
            self._mj_viewer.render(render_mode="rgb_array", camera_id=self._side_camera_id)
            self._mj_viewer.render(render_mode="rgb_array", camera_id=self._wrist_camera_id)

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

        self.env_step += 1
        predicate = self._compute_predicate()
        success = bool(predicate["ok"])
        obs = self._compute_observation()
        if self.render_mode == "human":
            self._mj_viewer.render("human")
        dt = time.time() - start_time
        time.sleep(max(0, (1.0 / self.hz) - dt))
        return obs, 1.0 if success else 0.0, success, False, {"succeed": success, "predicate": predicate}

    def _compute_success(self) -> bool:
        return bool(self._compute_predicate()["ok"])

    def _compute_predicate(self) -> dict[str, Any]:
        obj_xy = self._data.body(self._object_name).xpos[:2]
        obj_pos = self._data.body(self._object_name).xpos.copy()
        target_pos = self._data.site_xpos[self._target_site_id].copy()
        if self._predicate_type == "object_near_site" and "radius" not in self._predicate_params:
            self._predicate_params["radius"] = self._success_radius
        result = evaluate_predicate(
            self._predicate_type,
            obj_pos,
            target_pos,
            self._predicate_params,
        )
        result["object_pos"] = obj_pos.tolist()
        result["target_pos"] = target_pos.tolist()
        result["legacy_xy_distance"] = float(np.linalg.norm(obj_xy - target_pos[:2]))
        return result

    def render(self):
        if self._mj_viewer is None:
            raise RuntimeError("Rendering is disabled because render_mode='none'.")
        front = self._mj_viewer.render(
            render_mode="rgb_array",
            camera_id=self._front_camera_id,
        )
        side = self._mj_viewer.render(
            render_mode="rgb_array",
            camera_id=self._side_camera_id,
        )
        wrist = self._mj_viewer.render(
            render_mode="rgb_array",
            camera_id=self._wrist_camera_id,
        )
        return front, side, wrist

    def _compute_observation(self) -> dict:
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
                "target_pose": self._data.site_xpos[self._target_site_id].copy(),
            }
        }
        if self.image_obs:
            obs["images"] = {}
            obs["images"]["front"], obs["images"]["side"], obs["images"]["wrist"] = self.render()
        return obs

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
