# Scene Lab

Scene Lab is a lightweight human-AI loop for generated DexJoCo scenes.

The intended flow is:

```text
task idea / AI proposal
  -> generated scene folder
  -> static validation and preview rendering
  -> human review GUI
  -> accepted or rejected registry
```

This first version is intentionally small and file-based. A scene candidate is a
directory with at least:

```text
task.json
```

Validation adds:

```text
validation.json
preview/front.png
preview/wrist.png
```

Human review adds:

```text
review.json
```

## Quick Start

Create the bundled example candidate:

```bash
python scene_lab/tools/create_example_candidate.py
```

Or import an AI-generated task JSON into the pending queue:

```bash
python scene_lab/tools/import_ai_candidate.py path/to/generated_task.json
```

Import a local YCB or RoboTwin object into the processed asset registry:

```bash
python scene_lab/tools/import_ycb_asset.py \
  --source /path/to/ycb/003_cracker_box \
  --asset-id ycb_003_cracker_box

python scene_lab/tools/import_robotwin_asset.py \
  --source /path/to/robotwin/objects/001_Bottle \
  --asset-id robotwin_001_bottle
```

Create a pick/place candidate from any processed asset whose manifest has
`status=ready_for_pick_place`:

```bash
python scene_lab/tools/create_pick_place_candidate.py \
  --asset-id robotwin_001_bottle \
  --task-id pick_place_robotwin_bottle_demo
```

Generate a simple MJCF `scene.xml` for a candidate whose objects follow the
current box/table/target schema:

```bash
python scene_lab/tools/generate_mjcf_scene.py \
  scene_lab/registry/pending/move_book_demo
```

Validate and render previews:

```bash
conda activate dexjoco
python scene_lab/tools/validate_scene.py \
  scene_lab/registry/pending/move_book_demo
```

Import RoboTwin assets with strict RoboTwin scale, parse RoboTwin task env
files, generate transferable candidates, and validate the batch:

```bash
python scene_lab/tools/bulk_import_robotwin_assets.py \
  --objects-root third_party/assets/robotwin/assets/objects \
  --replace \
  --scale-mode robotwin_strict

python scene_lab/tools/build_collision_meshes.py \
  --all \
  --source robotwin

python scene_lab/tools/parse_robotwin_tasks.py \
  --source third_party/assets/robotwin/envs \
  --out scene_lab/benchmarks/robotwin_task_specs.json

python scene_lab/tools/generate_robotwin_task_candidates.py \
  --spec scene_lab/benchmarks/robotwin_task_specs.json \
  --assets scene_lab/assets/processed/robotwin \
  --out scene_lab/registry/pending \
  --max-candidates-per-task 8 \
  --seed 0 \
  --replace

/opt/homebrew/Caskroom/miniconda/base/envs/dexjoco/bin/python \
  scene_lab/tools/validate_robotwin_task_transfer.py \
  --pending scene_lab/registry/pending \
  --summary scene_lab/registry/robotwin_task_transfer_summary.json

python scene_lab/tools/promote_robotwin_tasks_to_dexjoco.py \
  --pending scene_lab/registry/pending \
  --replace

python scene_lab/tools/materialize_robotwin_native_task_dirs.py \
  --catalog dexjoco/dexjoco/tasks/robotwin_transfer/catalog.json

/opt/homebrew/Caskroom/miniconda/base/envs/dexjoco/bin/python \
  scene_lab/tools/verify_robotwin_dexjoco_alignment.py \
  --full-reset \
  --out dexjoco/dexjoco/tasks/robotwin_transfer/structure_alignment_summary.json
```

Import local YCB object models with strict metric mesh scale, generate
asset manifests, build mesh collisions, and render asset-only review previews:

```bash
export YCB_ROOT=/path/to/ycb/object_models

python scene_lab/tools/download_ycb_models.py \
  --out scene_lab/assets/raw/ycb/habitat_ycb \
  --repo ai-habitat/ycb

export YCB_ROOT=scene_lab/assets/raw/ycb/habitat_ycb

python scene_lab/tools/bulk_import_ycb_assets.py \
  --objects-root "$YCB_ROOT" \
  --replace \
  --unit-scale 1.0

python scene_lab/tools/build_collision_meshes.py \
  --all \
  --source ycb

python scene_lab/tools/render_asset_previews.py \
  --all \
  --source ycb

python scene_lab/tools/asset_review_gui.py --port 8768
```

Launch the review GUI:

```bash
python scene_lab/tools/review_gui.py
```

Open:

```text
http://127.0.0.1:8765
```

The GUI lets you inspect pending, accepted, and rejected candidates, then write a
review decision that moves the folder into the matching registry bucket.

Candidates with `asset_manifest.json` show the source benchmark, category,
collision approximation, mass, mesh path, success predicate, and previews.

## Asset Pipeline

External benchmark objects are normalized into:

```text
scene_lab/assets/
  raw/
    ycb/
    robotwin/
  processed/
    ycb/<asset_id>/
      asset_manifest.json
      visual/
      collision.json
    robotwin/<asset_id>/
      asset_manifest.json
      visual/
      collision.json
```

The first importers consume local dataset directories only; they do not download
YCB, RoboTwin-OD, or other large assets automatically. RoboTwin processed assets
prefer textured visual meshes plus generated mesh collision parts and physical
material metadata when those files exist.

RoboTwin strict scale uses `model_data*.json` exactly: raw GLB vertices are
centered by `model_data.center`, multiplied by `model_data.scale`, rotated from
RoboTwin Y-up to MuJoCo Z-up, and exported with no extra uniform scale. The
older review-only category target scaling is still available as
`--scale-mode category_target_max`, but should not be used for exact RoboTwin
alignment.

YCB strict scale preserves the local YCB mesh coordinates as metric object
model coordinates and records `unit_scale_to_meters` in
`dexjoco_calibration`. The default `--unit-scale 1.0` should be used for
official YCB object models; override it only for a known non-meter export.
YCB import does not generate task logic by default; use `--create-candidates`
only for temporary debugging previews.

## Candidate Schema

See:

```text
scene_lab/schemas/task.schema.json
```

The schema is deliberately close to what an AI scene generator should produce:
instruction, objects, robot, simulator entrypoint, success condition, and static
review checklist.

Two validation modes are supported:

- `config_mapping_key`: use a registered DexJoCo task such as `move_book`.
- `scene.xml`: use `scene_lab.runtime.PandaGeneratedSceneEnv` for a generated
  candidate directory without adding a new DexJoCo task registration.

The generator prompt contract lives at:

```text
scene_lab/prompts/scene_generator_prompt.md
```

## Benchmark Notes

Common embodied manipulation benchmarks are summarized in:

```text
scene_lab/benchmarks/embodied_benchmarks.md
scene_lab/benchmarks/embodied_benchmarks.json
```

The notes are meant as design references for future scene/task generators.

## Task And Object Design

The first task-family backlog lives in:

```text
scene_lab/task_catalog.md
```

The object modeling conventions for generated scenes live in:

```text
scene_lab/object_modeling.md
```

External asset sources are tracked as git submodules and summarized in:

```text
scene_lab/asset_sources.md
```
