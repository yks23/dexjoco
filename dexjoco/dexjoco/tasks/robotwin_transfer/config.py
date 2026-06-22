"""Task configs for RoboTwin tasks promoted into DexJoCo format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from ...sim.envs.panda_robotwin_task_env import PandaRoboTwinTaskGymEnv
from ..config import TaskConfigBase
from ..obs_adapters import DexjocoObsAdapter
from ..policy_wrappers import SingleArmPolicyWrapper
from ..sim_teleop import SingleArmTeleopConfig, SingleArmViveHandTeleopWrapper

_HERE = Path(__file__).resolve().parent
_CATALOG_PATH = _HERE / "catalog.json"


def load_catalog() -> dict[str, dict]:
    if not _CATALOG_PATH.exists():
        return {}
    data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return {task["task_id"]: task for task in data.get("tasks", [])}


ROBOTWIN_TASK_CATALOG = load_catalog()


class RoboTwinTaskConfig(TaskConfigBase):
    proprio_keys = [
        "tcp_pose",
        "gripper_pose",
        "object_pose",
        "goal_pose",
    ]
    teleop = SingleArmTeleopConfig(pose_scale=1.5)

    def __init__(self, task_id: str):
        if task_id not in ROBOTWIN_TASK_CATALOG:
            raise KeyError(f"Unknown promoted RoboTwin task_id: {task_id}")
        self.task_id = task_id
        self.task_spec = ROBOTWIN_TASK_CATALOG[task_id]

    def get_environment(
        self,
        policy_mode: bool = False,
        render_mode: Literal["rgb_array", "human", "none"] = "human",
        randomize: bool = False,
        **kwargs,
    ):
        env = PandaRoboTwinTaskGymEnv(
            task_spec=self.task_spec,
            render_mode=render_mode,
            randomize=randomize,
            hz=30,
            **kwargs,
        )
        if policy_mode:
            env = SingleArmPolicyWrapper(env)
        else:
            env = SingleArmViveHandTeleopWrapper(env, self.teleop)
        env = DexjocoObsAdapter(env, proprio_keys=self.proprio_keys)
        return env

    def process_demos(self, demo):
        return demo


def make_task_config(task_id: str):
    class TaskConfig(RoboTwinTaskConfig):
        def __init__(self):
            super().__init__(task_id)

    TaskConfig.__name__ = f"RoboTwinTaskConfig_{task_id}"
    return TaskConfig
