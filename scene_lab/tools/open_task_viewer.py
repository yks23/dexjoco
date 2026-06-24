#!/usr/bin/env python
"""Open a registered DexJoCo task in the native MuJoCo human viewer."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEXJOCO_SRC = ROOT / "dexjoco"
if str(DEXJOCO_SRC) not in sys.path:
    sys.path.insert(0, str(DEXJOCO_SRC))

from dexjoco.tasks import CONFIG_MAPPING  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_id",
        nargs="?",
        default="hard_pack_items_into_box_and_close",
        help="DexJoCo task id registered in CONFIG_MAPPING.",
    )
    parser.add_argument(
        "--render-mode",
        default="human",
        choices=("human", "rgb_array", "none"),
        help="DexJoCo render mode. Use human for the native MuJoCo viewer.",
    )
    parser.add_argument(
        "--policy-mode",
        action="store_true",
        help="Use policy wrapper instead of teleop wrapper.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=-1,
        help="Number of zero-action steps to run. Default keeps the viewer open.",
    )
    args = parser.parse_args()

    if args.task_id not in CONFIG_MAPPING:
        known = "\n".join(sorted(CONFIG_MAPPING))
        raise SystemExit(f"Unknown task_id: {args.task_id}\n\nKnown tasks:\n{known}")

    env = CONFIG_MAPPING[args.task_id]().get_environment(
        policy_mode=args.policy_mode,
        render_mode=args.render_mode,
    )
    obs, info = env.reset()
    print(args.task_id, info, flush=True)

    action = env.action_space.sample() * 0
    step = 0
    while args.steps < 0 or step < args.steps:
        env.step(action)
        step += 1
        time.sleep(0.01)


if __name__ == "__main__":
    main()
