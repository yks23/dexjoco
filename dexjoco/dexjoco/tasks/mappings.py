from .bimanual_assembly.config import TaskConfig as BimanualAssemblyConfig
from .bimanual_hanoi.config import TaskConfig as BimanualHanoiConfig
from .bimanual_microwave_cook.config import TaskConfig as BimanualMicrowaveCookConfig
from .bimanual_photograph.config import TaskConfig as BimanualPhotographConfig
from .bimanual_unlock_ipad.config import TaskConfig as BimanualUnlockIpadConfig
from .click_mouse.config import TaskConfig as ClickMouseConfig
from .fold_glasses.config import TaskConfig as FoldGlassesConfig
from .hammer_nail.config import TaskConfig as HammerNailConfig
from .move_book.config import TaskConfig as MoveBookConfig
from .pick_bucket.config import TaskConfig as PickBucketConfig
from .pinch_tongs.config import TaskConfig as PinchTongsConfig
from .robotwin_mappings import ROBOTWIN_CONFIG_MAPPING
from .water_plant.config import TaskConfig as WaterPlantConfig

CONFIG_MAPPING = {
    "bimanual_assembly": BimanualAssemblyConfig,
    "bimanual_hanoi": BimanualHanoiConfig,
    "bimanual_microwave_cook": BimanualMicrowaveCookConfig,
    "bimanual_photograph": BimanualPhotographConfig,
    "bimanual_unlock_ipad": BimanualUnlockIpadConfig,
    "click_mouse": ClickMouseConfig,
    "fold_glasses": FoldGlassesConfig,
    "hammer_nail": HammerNailConfig,
    "move_book": MoveBookConfig,
    "pick_bucket": PickBucketConfig,
    "pinch_tongs": PinchTongsConfig,
    "water_plant": WaterPlantConfig,
}

CONFIG_MAPPING.update(ROBOTWIN_CONFIG_MAPPING)
