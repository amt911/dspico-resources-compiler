"""Finding, copying and recording build artifacts.

These functions are where the pipeline asserts. A missing or ambiguous artifact
must stop the build rather than be papered over.
"""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.context import BuildContext
from dspico.runtime import capture


def _glob_to_depth(root: Path, pattern: str, depth: int) -> list[Path]:
    matches: set[Path] = set()
    for level in range(depth + 1):
        prefix = "*/" * level
        matches.update(p for p in root.glob(f"{prefix}{pattern}") if p.is_file())
    return sorted(matches)


def find_artifacts(root: Path, pattern: str, *, depth: int = 2) -> list[Path]:
    """Every file matching ``pattern`` within ``depth`` levels of ``root``."""
    return _glob_to_depth(root, pattern, depth)


def find_artifact(root: Path, pattern: str, *, depth: int = 2) -> Path:
    """The one file matching ``pattern``.

    Raises when nothing matches, and equally when several do: the shell version
    took ``head -n 1`` and could ship an arbitrary binary without a word.
    """
    matches = _glob_to_depth(root, pattern, depth)
    if not matches:
        raise BuildError(f"no file matching {pattern!r} under {root}", step="artifact")
    if len(matches) > 1:
        listed = ", ".join(str(m) for m in matches)
        raise BuildError(f"ambiguous match for {pattern!r} under {root}: {listed}", step="artifact")
    return matches[0]


def copy_into(source: Path, dest_dir: Path) -> Path:
    """Copy a file into a directory, returning its new path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / source.name
    shutil.copy2(source, destination)
    return destination


def copy_glob(
    root: Path, pattern: str, dest_dir: Path, *, depth: int = 2, required: bool = True
) -> list[Path]:
    """Copy every match into ``dest_dir``.

    ``required=False`` is only for genuinely optional artifacts, mirroring the
    shell's ``copy_if_exists``.
    """
    matches = _glob_to_depth(root, pattern, depth)
    if not matches and required:
        raise BuildError(f"no file matching {pattern!r} under {root}", step="artifact")
    return [copy_into(match, dest_dir) for match in matches]


def write_build_info(ctx: BuildContext, repo: Path, dest_dir: Path, component: str) -> Path:
    """Record the upstream commit for a component.

    Upstream clones float to their default branch, so without this a build is
    untraceable.
    """
    del ctx  # provenance is read directly; the runner drives the build, not queries
    # Column alignment matches the shell version so the two engines' BUILD_INFO
    # files differ only where the content genuinely differs.
    fields = (("Commit", "%H"), ("Date", "%ai"), ("Summary", "%s"))
    lines = [f"Component: {component}"]
    lines += [
        f"{label + ':':<10} {capture(['git', '-C', str(repo), 'log', '-1', f'--format={fmt}'])}"
        for label, fmt in fields
    ]
    destination = dest_dir / "BUILD_INFO.txt"
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
