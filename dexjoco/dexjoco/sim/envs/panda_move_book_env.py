"""Minimal MuJoCo move-book task for scene prototyping."""

import random
import time
from pathlib import Path
from typing import Any, Dict, Literal, Tuple

import mujoco
import numpy as np
from gymnasium import spaces
from scipy.spatial.transform import Rotation as R

from ..controllers import opspace
from ..mujoco_gym_env import MujocoGymEnv
from ..rendering import MujocoRenderer

_HERE = Path(__file__).parent
_XML_PATH = _HERE / "xmls" / "arena_arm_hand_move_book.xml"
_PANDA_HOME = np.asarray((0, -0.785, 0, -2.35, 0, 1.57, np.pi / 4), dtype=np.float64)
_ALLEGRO_HOME = np.asarray(
    (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.263, 0, 0, 0),
    dtype=np.float32,
)
_BOOK_START_POS = np.asarray((-0.33, -0.18, 0.945), dtype=np.float64)
_BOOK_START_QUAT = np.asarray((1.0, 0.0, 0.0, 0.0), dtype=np.float64)
_BOOK_SAMPLE_LOW = np.asarray((-0.36, -0.24), dtype=np.float64)
_BOOK_SAMPLE_HIGH = np.asarray((-0.27, -0.10), dtype=np.float64)
_GOAL_POS = np.asarray((0.12, 0.22, 0.945), dtype=np.float64)
_MAX_EPISODE_STEPS = 800
_SUCCESS_RADIUS = 0.08

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


class PandaMoveBookGymEnv(MujocoGymEnv):
    def __init__(
        self,
        render_mode: Literal["rgb_array", "human", "none"],
        randomize: bool,
        seed: int = 0,
        control_dt: float = 0.02,
        physics_dt: float = 0.002,
        hz: int = 30,
    ):
        self.hz = hz
        self.randomize = randomize
        self.image_obs = render_mode != "none"

        super().__init__(
            xml_path=_XML_PATH,
            seed=seed,
            control_dt=control_dt,
            physics_dt=physics_dt,
        )

        random.seed(seed)
        np.random.seed(seed)

        self.render_mode = render_mode
        self.env_step = 0

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

        self._book_joint_qposadr = int(self._model.joint("book_root").qposadr)
        self._book_body_id = int(self._model.body("book").id)
        self._goal_site_id = int(self._model.site("goal_center").id)

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
                        "gripper_pose": spaces.Box(
                            -np.inf, np.inf, shape=(_N_ALLEGRO,), dtype=np.float64
                        ),
                        "book_pose": spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float64),
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

    def reset(self, seed=None, **kwargs) -> Tuple[Dict[str, np.ndarray], Dict[str, Any]]:
        mujoco.mj_resetData(self._model, self._data)

        book_pos = _BOOK_START_POS.copy()
        if self.randomize:
            book_pos[:2] = np.random.uniform(_BOOK_SAMPLE_LOW, _BOOK_SAMPLE_HIGH)

        self._data.qpos[self._book_joint_qposadr : self._book_joint_qposadr + 7] = np.concatenate(
            [book_pos, _BOOK_START_QUAT]
        )
        self._data.qpos[self._panda_dof_ids] = _PANDA_HOME
        self._data.qpos[self._allegro_dof_ids] = _ALLEGRO_HOME

        mujoco.mj_forward(self._model, self._data)

        tcp_pos = self._data.sensor("franka/flange_pos").data
        tcp_quat = self._data.sensor("franka/flange_quat").data
        self._data.mocap_pos[0] = tcp_pos
        self._data.mocap_quat[0] = tcp_quat

        self.env_step = 0
        mujoco.mj_forward(self._model, self._data)
        self._prime_rgb_array_renderer()

        return self._compute_observation(), {"succeed": False}

    def step(self, action: np.ndarray):
        start_time = time.time()
        action = np.asarray(action, dtype=np.float64)

        xyz = action[:3]
        wxyz_quat = action[3:7]
        allegro_angles = np.asarray(action[7 : 7 + _N_ALLEGRO], dtype=np.float64)

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
        success = self._compute_success()
        terminated = self.env_step >= _MAX_EPISODE_STEPS or success

        if self.render_mode == "human":
            self._mj_viewer.render("human")

        dt = time.time() - start_time
        time.sleep(max(0, (1.0 / self.hz) - dt))

        return obs, 1.0 if success else 0.0, terminated, False, {"succeed": success}

    def _compute_success(self) -> bool:
        book_xy = self._data.body("book").xpos[:2]
        goal_xy = self._data.site_xpos[self._goal_site_id][:2]
        return bool(np.linalg.norm(book_xy - goal_xy) <= _SUCCESS_RADIUS)

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
        return [wrist_frame, front_frame]

    def _prime_rgb_array_renderer(self):
        if self._mj_viewer is None:
            return
        self._mj_viewer.render(render_mode="rgb_array", camera_id=self._wrist_camera_id)
        self._mj_viewer.render(render_mode="rgb_array", camera_id=self._front_camera_id)

    def _compute_observation(self) -> dict:
        tcp_pos = self._data.sensor("franka/flange_pos").data
        tcp_quat = self._data.sensor("franka/flange_quat").data
        tcp_pose = np.concatenate([tcp_pos, tcp_quat])

        allegro_qpos = np.array(
            [self._data.sensor(name).data for name in _ALLEGRO_SENSOR_NAMES],
            dtype=np.float32,
        )
        book_pose = np.concatenate(
            [
                self._data.body("book").xpos.copy(),
                self._data.body("book").xquat.copy(),
            ]
        )
        goal_pose = self._data.site_xpos[self._goal_site_id].copy()

        obs = {
            "state": {
                "tcp_pose": tcp_pose,
                "gripper_pose": allegro_qpos,
                "book_pose": book_pose,
                "goal_pose": goal_pose,
            }
        }
        if self.image_obs:
            obs["images"] = {}
            obs["images"]["wrist"], obs["images"]["front"] = self.render()
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
