# Scene Lab Converted Asset Pack

This branch is a cleaned result branch for converted RoboTwin and YCB assets.
It keeps the portable DexJoCo task definitions, the asset review GUI, and a
small README. The converted asset directory is distributed as a separate
artifact because the processed meshes, textures, collision parts, and previews
are about 3.2 GB.

It intentionally does not keep the one-off download/import/generation scripts.

## Contents

```text
scene_lab/assets/processed/        # restored from the asset artifact
  robotwin/<asset_id>/
    asset_manifest.json
    asset_scene.xml
    asset_validation.json
    visual/
    collision/
    preview/
  ycb/<asset_id>/
    asset_manifest.json
    asset_scene.xml
    asset_validation.json
    visual/
    collision/
    preview/

dexjoco/dexjoco/sim/envs/xmls/robotwin_tasks/
dexjoco/dexjoco/tasks/robotwin_*/
dexjoco/dexjoco/tasks/robotwin_transfer/
```

Current artifact counts:

```text
RoboTwin processed assets: 600
YCB processed assets: 77
RoboTwin promoted DexJoCo tasks: 247
```

## Review Assets

First restore the processed asset artifact so this directory exists:

```text
scene_lab/assets/processed/
```

```bash
python scene_lab/tools/asset_review_gui.py --port 8768
```

Open:

```text
http://127.0.0.1:8768/?source=all
http://127.0.0.1:8768/?source=robotwin
http://127.0.0.1:8768/?source=ycb
```

The GUI reads `scene_lab/assets/processed` directly. It does not run any
conversion pipeline.

## Use RoboTwin Tasks

Promoted RoboTwin tasks are registered through the normal DexJoCo mapping:

```python
from dexjoco.tasks import CONFIG_MAPPING

env = CONFIG_MAPPING["robotwin_adjust_bottle_001_bottle"]().get_environment(
    policy_mode=True,
    render_mode="none",
)
obs, info = env.reset()
```

The task XML files reference `scene_lab/assets/processed/robotwin` with
repository-relative paths, so they are portable after the asset artifact is
restored into this checkout.

## Notes

- YCB is included as an asset library only. No YCB task logic is generated.
- RoboTwin task transfer includes the executable rigid-object subset that was
  promoted to DexJoCo. Unsupported articulated or complex specs are preserved
  in `dexjoco/dexjoco/tasks/robotwin_transfer/catalog.json`.
- Raw benchmark downloads are not included in this cleaned branch.
