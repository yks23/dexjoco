from typing import Literal

from ...sim.envs.panda_move_book_env import PandaMoveBookGymEnv
from ..config import TaskConfigBase
from ..obs_adapters import DexjocoObsAdapter
from ..policy_wrappers import SingleArmPolicyWrapper
from ..sim_teleop import SingleArmTeleopConfig, SingleArmViveHandTeleopWrapper


class TaskConfig(TaskConfigBase):
    proprio_keys = [
        "tcp_pose",
        "gripper_pose",
        "book_pose",
        "goal_pose",
    ]
    teleop = SingleArmTeleopConfig(pose_scale=1.5)

    def get_environment(
        self,
        policy_mode: bool = False,
        render_mode: Literal["rgb_array", "human", "none"] = "human",
        randomize: bool = False,
        **kwargs,
    ):
        env = PandaMoveBookGymEnv(
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
