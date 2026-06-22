"""DexJoCo-native RoboTwin transferred task: robotwin_place_fan_box_demo."""

from ..robotwin_transfer.config import RoboTwinTaskConfig


class TaskConfig(RoboTwinTaskConfig):
    def __init__(self):
        super().__init__("robotwin_place_fan_box_demo")
