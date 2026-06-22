# YCB Strict Scale Review

This workflow mirrors the RoboTwin asset-review path for YCB object models.
It can consume local official YCB object model folders or the Habitat-ready YCB
mirror on Hugging Face, imports the meshes into the Scene Lab processed asset
format, generates pick/place candidates, validates MuJoCo loading, and serves
them in the review GUI.

## Scale Rule

YCB does not provide per-variant `model_data*.json` files like RoboTwin. The
strict importer therefore preserves YCB mesh coordinates as metric model
coordinates:

```text
raw_ycb_mesh_vertex -> multiply --unit-scale
                    -> export/link processed visual mesh
                    -> extra_uniform_scale = 1.0
```

Default:

```text
--unit-scale 1.0
```

Use a different `--unit-scale` only when the local YCB export is known to be in
non-meter units.  Do not use category-size normalization for exact alignment.

For Habitat-ready YCB, the importer reads each
`configs/*.object_config.json`, uses `render_asset` for the textured visual
mesh, prefers the uncompressed `.glb.orig` asset for texture extraction, and
uses `collision_asset` for convex mesh collision.

## Pull And Prepare

```bash
git fetch origin
git checkout ycb-trans
git pull
```

Use the DexJoCo Python environment:

```bash
export PY=/opt/homebrew/Caskroom/miniconda/base/envs/dexjoco/bin/python
```

Point `YCB_ROOT` at a local YCB object-model directory.  The expected shape is
one object per subdirectory, for example:

```text
$YCB_ROOT/
  003_cracker_box/google_16k/textured.obj
  004_sugar_box/google_16k/textured.obj
  ...
```

Alternatively, download the Habitat-ready full YCB asset set:

```bash
$PY scene_lab/tools/download_ycb_models.py \
  --out scene_lab/assets/raw/ycb/habitat_ycb \
  --repo ai-habitat/ycb

export YCB_ROOT=scene_lab/assets/raw/ycb/habitat_ycb
```

## Rebuild Strict Assets

```bash
$PY scene_lab/tools/bulk_import_ycb_assets.py \
  --objects-root "$YCB_ROOT" \
  --replace \
  --unit-scale 1.0

$PY scene_lab/tools/build_collision_meshes.py \
  --all \
  --source ycb
```

If collision meshes should also be copied into pending candidates after
candidate generation:

```bash
$PY scene_lab/tools/build_collision_meshes.py \
  --pending-candidates \
  --source ycb
```

## Validate And View

```bash
$PY scene_lab/tools/validate_ycb_asset_transfer.py
$PY scene_lab/tools/review_gui.py --port 8768
```

Open:

```text
http://127.0.0.1:8768/?bucket=pending&source=ycb
```

Each candidate contains `task.json`, `scene.xml`, `asset_manifest.json`,
`validation.json`, and `preview/front.png`, `preview/side.png`,
`preview/wrist.png` after validation.
