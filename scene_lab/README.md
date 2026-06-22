# Scene Lab Converted Asset Pack

This directory documents the public, cleaned result branch for converted
RoboTwin and YCB assets. The branch keeps the portable DexJoCo task definitions,
the asset review GUI, and this README. The converted asset payload is published
as a separate GitHub Release artifact because the processed meshes, textures,
collision parts, manifests, and previews are about 3.2 GB after extraction.

The one-off download, import, and generation scripts are intentionally not part
of this cleaned branch.

Release:

```text
https://github.com/yks23/dexjoco/releases/tag/assets-trans-20260622
```

## Public Layout

Keep large generated files outside git. The expected public structure is:

```text
dexjoco/                               # git checkout
  scene_lab/
    README.md
    tools/asset_review_gui.py
    assets/
      processed/                       # restored from the release artifact

GitHub Release assets-trans-20260622/  # large public artifact, not git
  scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-00
  scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-01
  scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-02
  scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-03
  scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-04
  SHA256SUMS.txt
```

After extraction, all runtime paths are repository-relative. Do not place the
archive parts inside `scene_lab/assets/processed`; that directory should contain
the extracted `robotwin/` and `ycb/` folders only.

## Contents

```text
scene_lab/assets/processed/            # restored from the release artifact
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

## Restore Artifact

Recommended download with the GitHub CLI:

```bash
gh release download assets-trans-20260622 \
  --repo yks23/dexjoco \
  --dir /tmp/dexjoco-assets-trans
```

Manual download also works: download all five `part-*` files and
`SHA256SUMS.txt` from the release page into the same temporary directory.

The release files are:

```text
scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-00
scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-01
scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-02
scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-03
scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-04
SHA256SUMS.txt
```

From the repository root, reconstruct the archive, check it, and extract it:

```bash
cat /tmp/dexjoco-assets-trans/scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst.part-* \
  > /tmp/dexjoco-assets-trans/scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst

shasum -a 256 /tmp/dexjoco-assets-trans/scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst
tar --use-compress-program=unzstd \
  -xf /tmp/dexjoco-assets-trans/scene_lab_processed_assets_robotwin_ycb_20260622.tar.zst
```

Expected archive checksum:

```text
c2c39b27dd591bac511ec5e54595b70ef90df12690b03f301b4fd5e12835967b
```

If `unzstd` is missing, install Zstandard first, for example:

```bash
brew install zstd
```

After extraction, this path must exist:

```text
scene_lab/assets/processed/robotwin/
scene_lab/assets/processed/ycb/
```

## Review Assets

First restore the processed asset artifact so these directories exist:

```text
scene_lab/assets/processed/robotwin/
scene_lab/assets/processed/ycb/
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
conversion pipeline and it does not require the original RoboTwin or YCB raw
downloads.

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

Quick task registration check:

```bash
python - <<'PY'
from dexjoco.tasks import CONFIG_MAPPING
print("robotwin_adjust_bottle_001_bottle" in CONFIG_MAPPING)
PY
```

## Notes

- YCB is included as an asset library only. No YCB task logic is generated.
- RoboTwin task transfer includes the executable rigid-object subset that was
  promoted to DexJoCo. Unsupported articulated or complex specs are preserved
  in `dexjoco/dexjoco/tasks/robotwin_transfer/catalog.json`.
- Raw benchmark downloads are not included in this cleaned branch.
- Keep `scene_lab/assets/processed/` out of git. It is ignored intentionally and
  should be restored from the public release artifact when reproducing.
