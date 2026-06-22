# Scene Lab Task Catalog

This document is the first backlog for AI-generated DexJoCo task families. Each
task should eventually map to a structured `task.json`, a generated or hand-made
MJCF scene, a success predicate, preview renders, and a static review checklist.

## Phase 1: Basic Rigid-Body Manipulation

| Task | Description | Core capability tested |
| --- | --- | --- |
| `move_book` | Move a book from its start pose to a target region. | Basic object displacement, contact control, target localization. |
| `place_book_on_mat` | Pick up a book and place it on a mat. | Grasping, lifting, placing, pose stabilization. |
| `push_object_to_zone` | Push an object into a target zone without grasping it. | Non-prehensile manipulation, contact planning, pushing direction control. |
| `put_object_in_box` | Place a small object inside an open box. | 3D placement, receptacle reasoning, endpoint alignment. |
| `place_object_on_plate` | Place an object on a plate or tray. | Planar placement, region constraints, light precision control. |
| `move_object_between_two_zones` | Move an object from zone A to zone B. | Pick-and-place fundamentals, start-goal transfer. |

## Phase 2: Multi-Object And Language-Conditioned Tasks

| Task | Description | Core capability tested |
| --- | --- | --- |
| `sort_objects_by_color` | Put objects into target regions with matching colors. | Visual-semantic binding, target selection, multi-object planning. |
| `sort_objects_by_shape` | Sort cubes, cylinders, cards, or books by shape. | Shape recognition, symbolic condition execution. |
| `pick_named_object` | Pick the object named by the instruction, such as the blue book. | Language grounding, object disambiguation. |
| `arrange_objects_in_order` | Arrange objects by color, size, label, or index. | Spatial relations, ordering constraints, compositional reasoning. |
| `swap_two_objects` | Swap two objects' positions. | Multi-step planning, state memory, interference avoidance. |
| `clear_table` | Move several tabletop objects into a box or target area. | Repeated manipulation, multi-object bookkeeping, clutter handling. |

## Phase 3: Articulated Object Tasks

| Task | Description | Core capability tested |
| --- | --- | --- |
| `open_microwave_door` | Open a microwave door past a target angle. | Articulated-object manipulation, pulling, hinge control. |
| `close_microwave_door` | Close a microwave door. | Reverse articulation, contact stability, terminal-state control. |
| `put_food_in_microwave` | Place a food box inside a microwave. | Placement in articulated scenes, reachability through openings. |
| `open_drawer` | Pull a drawer open. | Slide-joint manipulation, handle grasping, directional constraints. |
| `close_drawer` | Push a drawer closed. | Articulated pushing, stopping at a target joint state. |
| `press_button` | Press a button down. | Short-horizon contact, normal-force control, fingertip precision. |
| `turn_knob` | Rotate a knob to a target angle. | Rotational contact, finger coordination, angular control. |
| `pull_lever` | Pull a lever to a target position. | Lever articulation, constrained trajectory following. |
| `open_lid` | Open a hinged box lid or container lid. | Hinge affordance use, manipulation under partial occlusion. |

## Phase 4: Precision Manipulation And Assembly

| Task | Description | Core capability tested |
| --- | --- | --- |
| `insert_card_into_slot` | Insert a thin card into a narrow slot. | High-precision pose control, thin-object handling. |
| `insert_peg` | Insert a cylindrical peg into a hole. | Assembly, orientation alignment, contact tolerance. |
| `place_lid_on_box` | Place a lid onto a box. | Pose matching, alignment, stable placement. |
| `align_book_with_shelf` | Insert or align a book into a shelf slot. | Planar object insertion, orientation constraints. |
| `hang_object_on_hook` | Hang a holed object on a hook. | Spatial alignment, non-planar constraints, contact geometry. |
| `thread_ring_on_peg` | Put a ring over a peg. | Hole/peg relation reasoning, fine registration, contact-guided insertion. |

## Phase 5: Bimanual And Dual-Hand Coordination

| Task | Description | Core capability tested |
| --- | --- | --- |
| `handover_object` | Transfer an object from one hand or arm to the other. | Bimanual coordination, transfer timing, grasp switching. |
| `hold_box_and_insert_object` | Hold a box with one hand while placing an object with the other. | Cooperative stabilization, role assignment, relative motion control. |
| `open_container_and_place_item` | Open a lid or door with one hand and place an item with the other. | Long-horizon bimanual coordination, articulation plus placement. |
| `hold_object_while_pressing_button` | Hold an object while pressing a button with the other hand. | Parallel constraints, multi-object control. |
| `stretch_and_place_object` | Hold a long object at both ends and place it. | Synchronized two-hand motion, object pose control. |
| `assemble_two_parts_bimanual` | Hold two parts separately and assemble them. | Relative-pose control, bimanual assembly. |

## Phase 6: Proxy Fluids, Granular Objects, And Tool Use

| Task | Description | Core capability tested |
| --- | --- | --- |
| `pour_water_proxy` | Tilt a cup or kettle and visually pour water into another cup. | Container pose control, spout-target alignment, temporal hold. |
| `pour_beads_into_bowl` | Pour small rigid beads from a container into a bowl. | Granular rigid-body manipulation, container tilting, count-based success. |
| `spray_plant` | Aim a sprayer at a plant and trigger it. | Tool use, orientation control, trigger-state reasoning. |
| `shake_object_out_of_box` | Tilt or shake a box to release an object. | Dynamic control, gravity use, non-grasp release. |
| `fill_container_proxy` | Transfer a visual liquid proxy from one container to another. | Continuous-process approximation, target-container detection. |

## Phase 7: Long-Horizon Compositions

| Task | Description | Core capability tested |
| --- | --- | --- |
| `open_drawer_and_put_object_inside` | Open a drawer, place an object inside, optionally close it. | Sequential planning, articulation plus placement. |
| `open_microwave_put_food_close_door` | Open a microwave, place food inside, and close the door. | Multi-stage state dependency, household sequence execution. |
| `sort_then_stack_objects` | Sort objects first, then stack objects from the same group. | Compositional generalization, multi-goal planning. |
| `pick_place_press_button` | Place an object on a platform and press a confirmation button. | Conditional triggering, task-completion signaling. |
| `prepare_simple_table` | Arrange cups, plates, books, or tools at target locations. | Multi-object layout, spatial relations, long-horizon execution. |
| `clean_table_into_bins` | Sort tabletop objects into category-specific bins. | Semantic classification, repeated manipulation, receptacle placement. |

## First Implementation Batch

The recommended first batch is:

1. `place_book_on_mat`
2. `put_object_in_box`
3. `sort_objects_by_color`
4. `push_object_to_zone`
5. `press_button`
6. `turn_knob`
7. `insert_card_into_slot`
8. `put_food_in_microwave`
9. `handover_object`
10. `pour_water_proxy`

This batch covers rigid placement, receptacles, language-conditioned object
selection, non-prehensile contact, articulated controls, precision insertion,
bimanual transfer, and a first proxy-fluid task.
