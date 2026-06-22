# External Asset Sources

Scene Lab uses external assets as source material, not as finished DexJoCo
objects. A downloaded model still needs scale checks, collision geometry,
sites, joints, mass, friction, and success predicates before it becomes a stable
simulation object.

## Submodules

The current external asset sources are tracked under:

```text
third_party/assets/
```

| Source | Path | Primary use | Notes |
| --- | --- | --- | --- |
| MuJoCo Menagerie | `third_party/assets/mujoco_menagerie` | High-quality MuJoCo robot, gripper, sensor, and platform MJCF models. | Each model directory has its own `LICENSE` and `README.md`; check per-model license before reuse. |
| robosuite | `third_party/assets/robosuite` | MuJoCo object XMLs, arenas, textures, robots, grippers, and examples of procedural object modeling. | Top-level code license is MIT with MuJoCo portions under Apache 2.0. Useful asset root: `robosuite/models/assets`. |
| RoboCasa | `third_party/assets/robocasa` | Household and kitchen task ecosystem, fixture/object modeling patterns, scene/task taxonomy. | Code is MIT; assets and datasets are CC BY 4.0. Full kitchen assets are not included in the repo checkout and require the RoboCasa download script, currently around 10GB. |
| RoboTwin | `third_party/assets/robotwin` | Bimanual manipulation task definitions, object dataset tooling, RoboTwin-OD taxonomy, and benchmark patterns. | Code is MIT. Large assets are downloaded by RoboTwin's own scripts from HuggingFace and should stay outside normal git history. |

## Fetching Submodules

For a fresh clone of this repo:

```bash
git submodule update --init --recursive third_party/assets/mujoco_menagerie
git submodule update --init --recursive third_party/assets/robosuite
git submodule update --init --recursive third_party/assets/robocasa
git submodule update --init --recursive third_party/assets/robotwin
```

The checked-out submodules occupy non-trivial local disk space. In the current
snapshot, approximate sizes are:

```text
mujoco_menagerie  ~1.8GB
robosuite         ~628MB
robocasa          ~46MB before downloading kitchen assets
robotwin          code checkout only; RoboTwin-OD objects.zip is separate and large
```

## What To Reuse

### MuJoCo Menagerie

Best for:

- robot embodiments
- hands and grippers
- cameras and sensors
- proven MJCF modeling patterns

Good future candidates:

- alternate hands, such as LEAP Hand
- alternate arms, such as Franka FR3 or xArm
- mobile platforms or humanoids for future embodied settings
- camera/sensor models

Avoid treating Menagerie as a generic tabletop object library. It is mostly a
robot model library.

### robosuite

Best for:

- simple tabletop objects
- bins, boxes, nuts, pegs, doors, plates, and other manipulation primitives
- arena definitions and textures
- examples of visual/collision geometry separation

Useful paths:

```text
third_party/assets/robosuite/robosuite/models/assets/objects
third_party/assets/robosuite/robosuite/models/assets/arenas
third_party/assets/robosuite/robosuite/models/assets/textures
third_party/assets/robosuite/robosuite/models/objects
```

This is the most immediately useful source for `put_object_in_box`,
`insert_peg`, `press_button`, `turn_knob`, and tabletop placement variants.

### RoboCasa

Best for:

- household/kitchen task taxonomy
- fixtures such as counters, cabinets, drawers, appliances, and receptacles
- kitchen scene generation ideas
- object category lists and asset download scripts

Useful paths:

```text
third_party/assets/robocasa/robocasa/models
third_party/assets/robocasa/robocasa/models/objects
third_party/assets/robocasa/robocasa/models/fixtures
third_party/assets/robocasa/robocasa/models/scenes
third_party/assets/robocasa/robocasa/scripts/asset_scripts
```

Do not run the RoboCasa asset download script as part of normal setup. It is a
large optional download and should be a deliberate step when we start building
kitchen-scale tasks.

### RoboTwin

Best for:

- bimanual manipulation task taxonomy
- object category diversity and RoboTwin-OD metadata
- generated task and episode structure references
- dual-arm reachability and camera/static-review checks

Useful paths:

```text
third_party/assets/robotwin/envs
third_party/assets/robotwin/task_config
third_party/assets/robotwin/description
third_party/assets/robotwin/assets
third_party/assets/robotwin/script/_download_assets.sh
```

The RoboTwin repository is tracked as a submodule, but the full RoboTwin-OD
asset package is not committed into this repo. RoboTwin's own download script
fetches `background_texture.zip`, `embodiments.zip`, and `objects.zip`; treat
those as local raw data inputs for `scene_lab/tools/import_robotwin_asset.py`,
not as files to vendor into DexJoCo history.

## Import Policy

When promoting an external asset into a generated DexJoCo scene:

1. Record the source path, repository URL, commit hash, and license.
2. Normalize scale, orientation, and origin.
3. Use visual mesh for appearance when useful.
4. Prefer simple collision geoms for physics.
5. Add task-relevant sites, such as `center`, `handle`, `spout`, `slot`,
   `grasp`, or `target`.
6. Add joints only when the object's affordance needs them.
7. Validate with Scene Lab preview rendering and static checks before accepting.

The target metadata shape is:

```json
{
  "name": "asset_instance_name",
  "category": "cup",
  "source": {
    "repo": "third_party/assets/robosuite",
    "commit": "85abee228d1c43ab1939bce33028099945d453b4",
    "path": "robosuite/models/assets/objects/...",
    "license": "MIT"
  },
  "visual": {
    "type": "mesh",
    "path": "processed/cups/example.obj"
  },
  "collision": {
    "type": "cylinder",
    "size": [0.045, 0.06]
  },
  "physics": {
    "movable": "free",
    "mass": 0.18,
    "friction": [1.0, 0.005, 0.0001]
  },
  "sites": ["center", "grasp", "spout"]
}
```

## Immediate Mapping To Task Catalog

| Task family | Best source to inspect first |
| --- | --- |
| `place_book_on_mat` | Scene Lab procedural boxes first; robosuite textures second. |
| `put_object_in_box` | robosuite object and bin assets. |
| `sort_objects_by_color` | Procedural MJCF boxes/cylinders; robosuite textures. |
| `push_object_to_zone` | Procedural MJCF objects. |
| `press_button` | robosuite modeling patterns, then custom hinge/slide fixtures. |
| `turn_knob` | custom fixture first; RoboCasa fixture patterns later. |
| `insert_card_into_slot` | custom precision fixture; robosuite peg/plate patterns. |
| `put_food_in_microwave` | existing DexJoCo microwave, RoboCasa fixtures later. |
| `handover_object` | procedural object plus existing bimanual Panda/Allegro setup. |
| `pour_water_proxy` | custom cup/kettle model; RoboCasa receptacle categories later. |
| `pick_place_robotwin_*` | RoboTwin-OD rigid object assets through the Scene Lab asset importer. |
