"""The clone-build-copy shape shared by five of the nine steps.

The shell version wrote this sequence out five times. Expressing the variation
as data leaves one code path to get right.
"""

from pathlib import Path

from dspico.pipeline.artifacts import copy_into, find_artifact, write_build_info
from dspico.pipeline.components import Component
from dspico.pipeline.context import BuildContext
from dspico.pipeline.toolchain import clone, init_submodules, make


def build_component(
    ctx: BuildContext,
    component: Component,
    *,
    jobs: int,
    commit: str | None = None,
    write_info: bool = True,
) -> Path:
    """Clone, build, and copy the component's primary artifact into outputs.

    Returns the copied path so the caller can hand it to a later step, replacing
    the shell version's shared globals.
    """
    repo = ctx.work / component.name
    clone(ctx, component.url, repo, recursive=component.recursive, commit=commit)
    if component.submodules:
        init_submodules(ctx, repo)
    make(ctx, repo, jobs=jobs)

    found = find_artifact(repo, component.artifact, depth=5)
    destination = ctx.component_dir(component.name)
    copied = copy_into(found, destination)
    if write_info:
        write_build_info(ctx, repo, destination, component.name)
    return copied
