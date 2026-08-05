"""The in-container entry point: ``python3 -m dspico.pipeline.run``.

Runs inside the build image, where the toolchain lives. Paths here are the
container's mount points, not the host's.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dspico.config import BuildConfig
from dspico.errors import BuildError
from dspico.pipeline.components import COMPONENTS
from dspico.pipeline.context import BuildContext
from dspico.pipeline.plan import build_plan, labelled
from dspico.pipeline.steps import sd_card
from dspico.pipeline.steps.simple import build_component
from dspico.runtime import SubprocessRunner

CONTAINER_INPUTS = Path("/inputs")
CONTAINER_OUTPUTS = Path("/outputs")
CONTAINER_WORK = Path("/tmp/dspico-build")

# Step names that are satisfied entirely by the clone-build-copy shape.
COMPONENT_STEPS = ("dldi", "bootloader", "wrfuxxed", "pico_loader", "pico_launcher")
# Steps that still need their own driver. Named explicitly so an unimplemented
# step stops the build loudly instead of being silently skipped.
PENDING_STEPS = ("encryptor", "firmware", "ntrboot_variants")


def build_run_parser() -> argparse.ArgumentParser:
    """The in-container argument parser."""
    parser = argparse.ArgumentParser(
        prog="dspico.pipeline.run",
        description="Run the DSpico build inside the container.",
    )
    parser.add_argument("--wrfuxxed", action="store_true")
    parser.add_argument("--ntrboot", action="store_true")
    parser.add_argument("--edo-firmware", action="store_true")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the steps this configuration would run, then exit",
    )
    return parser


def dispatch(ctx: BuildContext, name: str, *, jobs: int) -> None:
    """Run one step by name.

    An unknown or not-yet-ported name raises rather than falling through: a step
    that quietly does nothing produces a build that looks successful and is not.
    """
    if name in COMPONENT_STEPS:
        build_component(ctx, COMPONENTS[name], jobs=jobs)
        return
    if name == "sd_card":
        sd_card.assemble(ctx.out_base)
        return
    if name in PENDING_STEPS:
        raise BuildError(f"step {name!r} is not ported to the python engine yet", step=name)
    raise BuildError(f"unknown step: {name!r}", step=name)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code rather than raising."""
    args = build_run_parser().parse_args(argv)
    config = BuildConfig(
        inputs_dir=CONTAINER_INPUTS,
        outputs_dir=CONTAINER_OUTPUTS,
        wrfuxxed=args.wrfuxxed,
        ntrboot=args.ntrboot,
        edo_firmware=args.edo_firmware,
    )
    plan = labelled(build_plan(config))

    if args.plan_only:
        for label, step in plan:
            print(f"[{label}] {step.name}: {step.title}")
        return 0

    ctx = BuildContext(
        config=config,
        runner=SubprocessRunner(),
        inputs=CONTAINER_INPUTS,
        out_base=CONTAINER_OUTPUTS / "dspico",
        work=CONTAINER_WORK,
    )
    ctx.out_base.mkdir(parents=True, exist_ok=True)
    ctx.work.mkdir(parents=True, exist_ok=True)

    try:
        for label, step in plan:
            print(f"\n[{label}] {step.title}")
            dispatch(ctx, step.name, jobs=args.jobs)
    except BuildError as error:
        print(f"ERROR: {error.message}", file=sys.stderr)
        return 1

    print(f"\nAll components built successfully. Outputs: {ctx.out_base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
