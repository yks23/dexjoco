# RoboTwin Strict Scale Review

This workflow imports RoboTwin assets without any DexJoCo-specific heuristic
rescaling.  The only size transform is the scale provided by RoboTwin in each
`model_data*.json` file.

## Scale Rule

For each RoboTwin object variant:

```text
raw_glb_vertex -> subtract model_data.center
               -> multiply model_data.scale
               -> rotate Y-up to MuJoCo Z-up: (x, y, z) -> (x, -z, y)
               -> export processed OBJ
```

The strict extra uniform scale is always:

```text
extra_uniform_scale = 1.0
```

Do not use the older `category_target_max` review normalization when exact
RoboTwin alignment is required.

## Pull And Prepare

```bash
git fetch origin
git checkout codex/move-book-scene
git pull
git submodule update --init --recursive third_party/assets/robotwin
```

Use the DexJoCo Python environment:

```bash
export PY=/opt/homebrew/Caskroom/miniconda/base/envs/dexjoco/bin/python
```

## Rebuild Strict Assets

```bash
$PY scene_lab/tools/bulk_import_robotwin_assets.py \
  --objects-root third_party/assets/robotwin/assets/objects \
  --replace \
  --scale-mode robotwin_strict

$PY scene_lab/tools/build_collision_meshes.py \
  --all \
  --source robotwin
```

## Rebuild Task Candidates

```bash
$PY scene_lab/tools/parse_robotwin_tasks.py \
  --source third_party/assets/robotwin/envs \
  --out scene_lab/benchmarks/robotwin_task_specs.json

$PY scene_lab/tools/generate_robotwin_task_candidates.py \
  --spec scene_lab/benchmarks/robotwin_task_specs.json \
  --assets scene_lab/assets/processed/robotwin \
  --out scene_lab/registry/pending \
  --max-candidates-per-task 8 \
  --seed 0 \
  --replace

$PY scene_lab/tools/validate_robotwin_task_transfer.py \
  --pending scene_lab/registry/pending \
  --summary scene_lab/registry/robotwin_task_transfer_summary.json
```

## View

```bash
$PY scene_lab/tools/review_gui.py --port 8767
```

Open:

```text
http://127.0.0.1:8767/?bucket=pending&source=robotwin
```

For the current bottle check:

```text
http://127.0.0.1:8767/?bucket=pending&source=robotwin&name=pick_place_robotwin_001_bottle_base22
```

The large review image uses the validated `preview/front.png`, so it matches
the generated front/side/wrist preview state.  The native MuJoCo viewer button
uses `mjpython` on macOS and launches a passive viewer from the same
`PandaGeneratedSceneEnv.reset()` state.

