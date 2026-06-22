# Object Modeling Notes

DexJoCo scenes are MuJoCo MJCF/XML scenes. A generated task should model objects
with the simplest physical representation that preserves the task's core
affordance.

## Main Object Types

### Fixed scene geometry

Use fixed bodies and geoms for tables, floors, walls, shelves, target mats,
visual labels, and static obstacles.

Typical MJCF pattern:

```xml
<body name="target_zone" pos="0.45 0.0 0.76">
  <geom name="target_zone_visual" type="box" size="0.09 0.09 0.003"
        rgba="0.1 0.8 0.25 0.35" contype="0" conaffinity="0"/>
</body>
```

Target zones are usually visual-only geoms with collision disabled.

### Free rigid objects

Use a `freejoint` for objects the robot can move freely: books, blocks, food
boxes, cards, cups, lids, and small tools.

Typical MJCF pattern:

```xml
<body name="book" pos="0.42 -0.16 0.80">
  <freejoint name="book_joint"/>
  <geom name="book_collision" type="box" size="0.08 0.055 0.012"
        rgba="0.1 0.25 0.9 1" mass="0.18"/>
  <site name="book_center" pos="0 0 0" size="0.01" rgba="0 0 1 1"/>
</body>
```

For generated scenes, boxes and cylinders are preferred first because they are
stable, inspectable, and easy to randomize.

### Articulated objects

Use jointed bodies for doors, drawers, knobs, buttons, levers, and lids. The
body is still rigid, but the joint allows one constrained degree of freedom.

Common joint choices:

- `hinge`: doors, lids, knobs, levers.
- `slide`: drawers, buttons, linear switches.

Typical knob pattern:

```xml
<body name="panel" pos="0.52 0.0 0.88">
  <geom type="box" size="0.02 0.12 0.10" rgba="0.5 0.5 0.5 1"/>
  <body name="knob" pos="-0.025 0 0">
    <joint name="knob_joint" type="hinge" axis="1 0 0" limited="true"
           range="-1.57 1.57" damping="0.02"/>
    <geom name="knob_collision" type="cylinder" size="0.025 0.025"
          rgba="0.2 0.2 0.2 1" mass="0.03"/>
  </body>
</body>
```

Success predicates should usually read joint position, for example
`knob_joint > target_angle` or `button_joint > target_displacement`.

### Mesh assets

Use mesh assets when object shape matters visually or physically, such as the
existing microwave, iPad, mouse, plant, camera, or hand assets. Meshes should be
paired with simple collision geoms when possible.

Recommended split:

- visual mesh for realistic appearance.
- simple boxes, cylinders, or capsules for collision.

This keeps simulation more stable than using detailed visual meshes as
collision geometry.

### Proxy fluids and particles

For early tasks such as `pour_water_proxy`, do not model true fluid first. Use
one of these approximations:

- visual-only stream geom or transparent cylinder that appears while pouring.
- small rigid beads for granular pouring.
- a scalar state variable such as `poured_amount` driven by pose predicates.

The first useful success condition is geometric: source container tilted enough,
spout near the target cup, spout direction aimed at the target, and the pose held
for several steps.

## How Scene Lab Generates Objects

The current `scene_lab/tools/generate_mjcf_scene.py` path is intentionally
simple:

1. Read a candidate `task.json`.
2. Create a table, camera setup, Panda + Allegro include, objects, and target
   sites.
3. Emit `scene.xml` into the candidate folder.
4. Let `scene_lab.runtime.generated_scene_env.PandaGeneratedSceneEnv` load the
   local XML for reset, step, render, and basic success checking.

Today this generator is best suited for box-like free rigid objects plus target
zones. The next modeling extensions should be:

1. receptacles: boxes, trays, bowls.
2. articulated fixtures: buttons, knobs, drawers, hinged doors.
3. precision fixtures: slots, holes, hooks, pegs.
4. proxy-fluid visuals: stream geoms and bead containers.

## Object Modeling Checklist

Every generated object should declare:

- stable `name`
- category, such as `book`, `box`, `button`, or `drawer`
- body pose
- dimensions or mesh asset
- movable type: `fixed`, `free`, `hinge`, or `slide`
- collision shape
- visual material or color
- optional sites for grasp point, center, handle, spout, slot, or target
- mass and friction when it is movable
- success-relevant names, such as joint names or site names

For the human review GUI, the important question is not whether the object is
beautiful. It is whether the affordance is unambiguous: can a person tell what
should be grasped, pushed, inserted, opened, poured, or pressed from the preview
image and `task.json`.
