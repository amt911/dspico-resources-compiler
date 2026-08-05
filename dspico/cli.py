"""The command-line entry point.

Flags rather than environment variables, because ``ENABLE_X=1 ./script`` is not
valid PowerShell and this has to work the same way on every host.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dspico.config import DEFAULT_IMAGE_NAME, BuildConfig
from dspico.errors import BuildError, ConfigError
from dspico.host.image import build_image_argv
from dspico.host.launcher import run_container_argv
from dspico.hostenv import HostEnv, needs_emulation
from dspico.runtime import DryRunRunner, Runner, SubprocessRunner

PIPELINE_SCRIPT = "compile_resources.sh"


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, kept separate so tests can exercise parsing alone."""
    parser = argparse.ArgumentParser(
        prog="dspico", description="Build every DSpico component in a container."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build", help="build the image and run the pipeline")
    build.add_argument("--inputs", default="inputs", help="directory holding the input files")
    build.add_argument("--outputs", default="outputs", help="directory to write artifacts to")
    build.add_argument("--image", default=DEFAULT_IMAGE_NAME, help="container image name")
    build.add_argument("--context", default=".", help="directory holding the Dockerfile")
    build.add_argument("--engine", default="docker", help="container CLI to invoke")
    build.add_argument("--wrfuxxed", action="store_true", help="build the WRFUxxed exploit ROM")
    build.add_argument("--ntrboot", action="store_true", help="build the ntrboot variants")
    build.add_argument("--edo-firmware", action="store_true", help="use the edo9300 firmware fork")
    build.add_argument(
        "--engine-kind",
        choices=("bash", "python"),
        default="bash",
        help="which pipeline implementation runs inside the container",
    )
    build.add_argument("--skip-image-build", action="store_true", help="reuse the existing image")
    build.add_argument(
        "--dry-run", action="store_true", help="print the commands without running them"
    )
    return parser


def config_from_args(args: argparse.Namespace, *, cwd: Path) -> BuildConfig:
    """Absolutise the directory arguments; BuildConfig rejects relative paths."""
    return BuildConfig(
        inputs_dir=(cwd / args.inputs).resolve(),
        outputs_dir=(cwd / args.outputs).resolve(),
        wrfuxxed=args.wrfuxxed,
        ntrboot=args.ntrboot,
        edo_firmware=args.edo_firmware,
        image_name=args.image,
    )


def _run_build(args: argparse.Namespace, *, cwd: Path) -> None:
    config = config_from_args(args, cwd=cwd)
    context_dir = (cwd / args.context).resolve()

    # Checked here so a mistyped --context fails immediately, instead of as an
    # opaque docker error several seconds into a build.
    if not (context_dir / "Dockerfile").is_file():
        raise ConfigError(f"no Dockerfile in the build context: {context_dir}")
    script_path = context_dir / PIPELINE_SCRIPT
    if not script_path.is_file():
        raise ConfigError(f"no {PIPELINE_SCRIPT} in the build context: {context_dir}")

    env = HostEnv.detect()
    if needs_emulation(env):
        print(
            f"Host is {env.arch}; the toolchain image is x86_64 only, so the build "
            "runs emulated and will be considerably slower.",
            file=sys.stderr,
        )

    runner: Runner = DryRunRunner() if args.dry_run else SubprocessRunner()

    if not args.skip_image_build:
        runner.run(
            build_image_argv(config, env, context_dir=context_dir, engine=args.engine),
            step="image",
        )

    if not args.dry_run:
        config.outputs_dir.mkdir(parents=True, exist_ok=True)
    runner.run(
        run_container_argv(
            config,
            env,
            script_path=script_path,
            engine=args.engine,
            engine_kind=args.engine_kind,
            repo_dir=context_dir,
        ),
        step="pipeline",
    )

    if args.dry_run:
        print("Dry run: nothing was executed.")
    else:
        print(f"Finished. Outputs are in {config.outputs_dir}")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code rather than raising."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)

    try:
        _run_build(args, cwd=Path.cwd())
    except BuildError as error:
        print(f"ERROR: {error.message}", file=sys.stderr)
        return 1
    return 0
