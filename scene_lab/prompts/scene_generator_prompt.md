# Scene Generator Prompt

Use this prompt as the contract for an AI scene/task generator. The generator
should output one JSON object that follows `scene_lab/schemas/task.schema.json`.

```text
You are generating a candidate manipulation task for DexJoCo Scene Lab.

Return only JSON. Do not include markdown.

Required fields:
- task_id: stable snake_case id
- task_name: short task family name
- instruction: natural language instruction for the robot
- robot: arm/hand/dof metadata
- simulator: MuJoCo backend and DexJoCo CONFIG_MAPPING entrypoint if available
- objects: manipulated objects, target regions, support surfaces, and fixtures
- success_condition: measurable success predicate
- static_review: what a human reviewer must inspect

Design constraints:
- The task must be physically plausible.
- Manipulated objects must start on a support surface and not intersect the table.
- Target regions must be reachable by the robot.
- The front and wrist cameras should make the key object and target visible.
- Prefer simple success predicates first: object_near_site, object_inside_region,
  object_above_height, joint_above_threshold.

Output schema example:
{
  "task_id": "move_book_0002",
  "task_name": "move_book",
  "instruction": "Move the red book onto the blue mat.",
  "robot": {
    "name": "panda_allegro_right",
    "arm": "Franka Panda",
    "hand": "Wonik Allegro Hand V3 right",
    "dof": 23
  },
  "simulator": {
    "backend": "mujoco",
    "entrypoint": {
      "config_mapping_key": "move_book",
      "xml_path": "dexjoco/dexjoco/sim/envs/xmls/arena_arm_hand_move_book.xml"
    }
  },
  "objects": [
    {
      "name": "book",
      "role": "manipulated_object",
      "type": "box_composite",
      "pose": [-0.33, -0.18, 0.945, 1.0, 0.0, 0.0, 0.0],
      "size": [0.216, 0.156, 0.046]
    },
    {
      "name": "goal_zone",
      "role": "target_region",
      "type": "flat_box",
      "pose": [0.12, 0.22, 0.925],
      "size": [0.26, 0.20, 0.008]
    }
  ],
  "success_condition": {
    "type": "object_near_site",
    "object": "book",
    "target": "goal_center",
    "radius": 0.08
  },
  "static_review": {
    "must_be_visible": ["book", "goal_zone", "robot hand"],
    "must_be_reachable": ["book", "goal_zone"],
    "common_failure_modes": [
      "Object intersects the table.",
      "Goal is outside workspace.",
      "Instruction does not match visible objects."
    ]
  }
}
```
