# Embodied Benchmark Notes For Scene Lab

These notes preserve task and scene construction patterns from common embodied
manipulation benchmarks. They are intended as references for AI-generated
DexJoCo scenes and for static review criteria.

## RoboTwin 2.0

- **Focus:** scalable synthetic data generation and benchmarking for bimanual
  robotic manipulation.
- **Scale:** 50-task benchmark, 731 objects, 147 object categories.
- **Task pattern:** bimanual manipulation, generated task programs, strong
  domain randomization, object diversity.
- **Scene pattern:** object-centric generated scenes with flexible dual-arm
  configurations.
- **Scene Lab takeaway:** add review checks for bimanual reachability, whether
  both arms/hands are visible, and whether generated spatial relations are
  physically plausible.
- **Sources:** https://robotwin-platform.github.io/,
  https://openreview.net/forum?id=vAPIIscwc7

## LIBERO

- **Focus:** lifelong robot learning and transfer in language-conditioned
  manipulation.
- **Scale:** 130 tasks in four suites: LIBERO-Spatial, LIBERO-Object,
  LIBERO-Goal, and LIBERO-100.
- **Task pattern:** suites isolate spatial transfer, object transfer, goal
  transfer, or mixed/entangled transfer.
- **Scene pattern:** procedurally generated tabletop scenes, controlled object
  placements/goals, human teleoperated demonstrations.
- **Scene Lab takeaway:** represent object, spatial, and goal variations
  separately in `task.json`; rejected scenes should record which transfer axis
  failed.
- **Sources:** https://github.com/Lifelong-Robot-Learning/LIBERO,
  https://libero-project.github.io/main.html, https://arxiv.org/abs/2306.03310

## RoboCasa / RoboCasa365

- **Focus:** realistic household/kitchen manipulation.
- **Scale:** RoboCasa originally describes 100 tasks; RoboCasa365 describes 365
  everyday tasks, 2,500 kitchen scenes, and large human/synthetic demo sets.
- **Task pattern:** ten foundational skills: pick/place, doors, drawers, knobs,
  levers, buttons, insertion, navigation, sliding racks, lids.
- **Scene pattern:** kitchen layouts, interactable appliances/furniture,
  diverse object categories and textures.
- **Scene Lab takeaway:** maintain a skill taxonomy and add static checks for
  articulated affordances such as handles, knobs, buttons, doors, and drawers.
- **Sources:** https://robocasa.ai/, https://github.com/robocasa/robocasa,
  https://arxiv.org/html/2603.04356v1

## ManiSkill

- **Focus:** generalizable manipulation skill benchmarking with diverse objects
  and fast simulation.
- **Task pattern:** manipulation skills plus community external benchmark/task
  integrations.
- **Scene pattern:** physics-rich scenes, task cards, environment definitions,
  reproducible assets.
- **Scene Lab takeaway:** every generated scene should produce a task card:
  previews, objects, success condition, action/observation shape, and assets.
- **Sources:** https://maniskill.readthedocs.io/en/latest/tasks/external/,
  https://www.maniskill.ai/research,
  https://sapien.ucsd.edu/challenges/maniskill/2021/

## Meta-World

- **Focus:** multi-task and meta-RL for continuous-control robotic
  manipulation.
- **Scale:** 50 tabletop manipulation tasks.
- **Task pattern:** reach, push, pick-place, door/drawer/window operations,
  buttons, peg insertion, hammering, assembly.
- **Scene pattern:** compact MuJoCo tabletop scenes with parametric object and
  goal variation.
- **Scene Lab takeaway:** use it as a seed library for small task primitives.
- **Sources:** https://meta-world.github.io/,
  https://github.com/Farama-Foundation/Metaworld

## RLBench

- **Focus:** vision-guided manipulation, imitation learning, few-shot learning,
  and task creation tooling.
- **Scale:** 100 hand-designed tasks.
- **Task pattern:** tasks range from reaching/door opening to multi-stage
  operations such as opening an oven and placing a tray inside.
- **Scene pattern:** task-specific scenes, RGB/depth/segmentation/proprioception,
  over-the-shoulder and wrist cameras, waypoint-based demonstrations.
- **Scene Lab takeaway:** static validation should eventually check camera
  coverage and waypoint/demo feasibility, not only XML loading.
- **Sources:** https://sites.google.com/view/rlbench,
  https://arxiv.org/abs/1909.12271, https://github.com/stepjam/RLBench

## CALVIN

- **Focus:** long-horizon language-conditioned manipulation.
- **Task pattern:** language instructions composed over long horizons.
- **Scene pattern:** simulated Franka tabletop environments, play-style
  teleoperation data, language labels.
- **Scene Lab takeaway:** review whether the rendered scene unambiguously
  supports the natural-language instruction.
- **Sources:** https://calvin.cs.uni-freiburg.de/,
  https://github.com/mees/calvin, https://arxiv.org/abs/2112.03227

## BEHAVIOR-1K

- **Focus:** human-centered embodied AI with everyday household activities.
- **Scale:** 1,000 activities, 50 scenes, 9,000+ objects.
- **Task pattern:** long-horizon household activities grounded in human needs,
  including state changes such as cleaning, cooking, organizing, deformables,
  and liquids.
- **Scene pattern:** realistic homes, gardens, restaurants, offices, semantic
  object properties, OMNIGIBSON simulation.
- **Scene Lab takeaway:** long term, generated tasks should include semantic
  state predicates, not only object geometry.
- **Sources:** https://behavior.stanford.edu/index.html,
  https://proceedings.mlr.press/v205/li23a.html,
  https://github.com/StanfordVL/BEHAVIOR-1K

## DexJoCo

- **Focus:** MuJoCo-based task-oriented dexterous manipulation.
- **Scale:** 11 tasks.
- **Task pattern:** tool use, bimanual coordination, long-horizon execution, and
  reasoning.
- **Scene pattern:** MJCF XML scenes, Panda + Allegro hand, reusable object and
  table assets, teleoperation/replay pipeline.
- **Scene Lab takeaway:** current integration target; generated scenes should
  become `CONFIG_MAPPING`-compatible envs or be handled by a future generic
  generated-scene env.
- **Sources:** repository `README.md`, https://dexjoco.github.io/,
  https://arxiv.org/abs/2605.16257
