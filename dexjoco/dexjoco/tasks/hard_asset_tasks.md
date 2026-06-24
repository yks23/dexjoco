# Hard Asset-Composition Tasks

These tasks are hand-composed from the converted RoboTwin/YCB asset pack and
the CSV task-taxonomy motifs in `train_task_translations_v2.csv`. They are not
simple one-object move tasks: each task uses multiple objects or a proxy
predicate such as stacking, category sorting, lid closure, pouring pose, or
camera-facing presentation.

All five tasks are registered in the normal DexJoCo `CONFIG_MAPPING` through
`dexjoco/dexjoco/tasks/robotwin_mappings.py`.

| Task ID | Instruction | Main Source Motif | Converted Assets | Success Logic |
| --- | --- | --- | --- | --- |
| `hard_sort_objects_by_category` | Sort the can, bottle, and toy car into their matching category zones. | CSV `T90` assorted items into storage box; `T01/T03/T16/T23/T27` pick/place variants; RoboTwin `blocks_ranking_*` and `place_object_basket`. | RoboTwin can, bottle, toy car. | All objects must be in their category-specific regions. |
| `hard_pack_items_into_box_and_close` | Pack the bread and can into the box, then place the lid proxy on top. | CSV `T50` multi-item bag packing and closure; `T90` lidded storage box; RoboTwin `put_object_cabinet`, `place_cans_plasticbox`, `put_bottles_dustbin`. | RoboTwin bread/can; YCB foam brick as lid proxy. | Bread and can must be in the box region, and the lid proxy must be on the close marker. |
| `hard_stack_bowls_stably` | Stack three bowls into one stable vertical stack. | RoboTwin `stack_bowls_three`; CSV bowl/container placement motifs made harder by requiring stable relative pose. | Three RoboTwin bowl variants. | Bottom bowl must be at the base region; middle and top bowls must be vertically above the previous bowl with XY alignment. |
| `hard_pour_granules_proxy` | Tilt the bottle over the bowl to proxy pouring granules or liquid. | CSV `T51`, `T55`, `T56`, `T97`, `T99` pour liquid/granules; RoboTwin `shake_bottle`. | RoboTwin bottle; YCB bowl. | Bowl stays in the receiving region and the bottle is tilted near the bowl. This is a proxy, not fluid simulation. |
| `hard_present_object_to_camera` | Pick up the playing cards and present their front side toward the camera focus point. | CSV `T84/T85` show booklet/brochure cover; RoboTwin `scan_object` and `move_playingcard_away`. | RoboTwin playing cards and phone distractor. | Target card must be lifted near the presentation spot and face the camera-focus site. |

Quick reset check:

```bash
PYTHONPATH=dexjoco python - <<'PY'
from dexjoco.tasks import CONFIG_MAPPING

for task_id in [
    "hard_sort_objects_by_category",
    "hard_pack_items_into_box_and_close",
    "hard_stack_bowls_stably",
    "hard_pour_granules_proxy",
    "hard_present_object_to_camera",
]:
    env = CONFIG_MAPPING[task_id]().get_environment(
        policy_mode=True,
        render_mode="none",
    )
    obs, info = env.reset()
    print(task_id, obs["state"].shape, info["succeed"], info["predicate"]["mode"])
    env.close()
PY
```

