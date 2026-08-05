"""Thin wrappers over the external tools the build drives."""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.context import BuildContext

DLDITOOL_DEFAULT = "/opt/wonderful/thirdparty/blocksds/core/tools/dlditool/dlditool"


def clone(
    ctx: BuildContext,
    url: str,
    dest: Path,
    *,
    recursive: bool = False,
    commit: str | None = None,
) -> None:
    """Clone into ``dest``, wiping any previous checkout first.

    The wipe is what makes a rebuild honest: without it a failed clone leaves the
    previous checkout in place and the build "succeeds" against stale sources.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = ["git", "clone"]
    if recursive:
        argv.append("--recursive")
    argv += [url, str(dest)]
    ctx.runner.run(argv, step="clone")
    if commit is not None:
        ctx.runner.run(["git", "-C", str(dest), "checkout", "--detach", commit], step="clone")


def init_submodules(ctx: BuildContext, repo: Path, *, subdir: Path | None = None) -> None:
    """Initialise submodules, targeting the repo with ``-C`` rather than cwd."""
    target = repo if subdir is None else repo / subdir
    ctx.runner.run(["git", "-C", str(target), "submodule", "update", "--init"], step="submodules")


def make(ctx: BuildContext, repo: Path, *, jobs: int) -> None:
    """Build with make.

    The shell version preferred ``male`` and fell back to ``make``, but no
    ``male`` binary exists in the image (see docs/FINDINGS.md), so only this
    path has ever run.
    """
    ctx.runner.run(["make", "-C", str(repo), f"-j{jobs}"], step="build")


def dldi_patch(
    ctx: BuildContext, dldi: Path, target: Path, *, dlditool: Path | None = None
) -> None:
    """Patch a binary in place with the DSpico DLDI driver."""
    tool = Path(DLDITOOL_DEFAULT) if dlditool is None else dlditool
    if not tool.is_file():
        raise BuildError(f"dlditool not found at: {tool}", step="dldi-patch")
    ctx.runner.run([str(tool), str(dldi), str(target)], step="dldi-patch")
