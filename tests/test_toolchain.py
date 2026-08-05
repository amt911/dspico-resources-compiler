"""Toolchain helpers, asserted as exact commands."""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.errors import BuildError
from dspico.pipeline.context import BuildContext
from dspico.pipeline.toolchain import clone, dldi_patch, init_submodules, make
from tests.conftest import FakeRunner


@pytest.fixture
def ctx(tmp_path: Path) -> BuildContext:
    return BuildContext(
        config=BuildConfig(inputs_dir=tmp_path / "in", outputs_dir=tmp_path / "out"),
        runner=FakeRunner(),
        inputs=tmp_path / "in",
        out_base=tmp_path / "out" / "dspico",
        work=tmp_path / "work",
    )


def _calls(ctx: BuildContext) -> list[tuple[str, ...]]:
    runner = ctx.runner
    assert isinstance(runner, FakeRunner)
    return runner.calls


def test_clone_removes_a_stale_destination_first(ctx: BuildContext, tmp_path: Path) -> None:
    # The shell version rm -rf'd the clone dir; without that a rebuild would
    # "succeed" against the previous checkout.
    dest = tmp_path / "work" / "repo"
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("old", encoding="utf-8")

    clone(ctx, "https://example.invalid/r.git", dest)

    assert not dest.exists()
    assert _calls(ctx) == [("git", "clone", "https://example.invalid/r.git", str(dest))]


def test_clone_recursive_passes_the_flag(ctx: BuildContext, tmp_path: Path) -> None:
    clone(ctx, "https://example.invalid/r.git", tmp_path / "r", recursive=True)
    assert _calls(ctx)[0] == (
        "git",
        "clone",
        "--recursive",
        "https://example.invalid/r.git",
        str(tmp_path / "r"),
    )


def test_clone_at_a_pinned_commit_checks_it_out(ctx: BuildContext, tmp_path: Path) -> None:
    dest = tmp_path / "r"
    clone(ctx, "https://example.invalid/r.git", dest, commit="abc1234")
    assert _calls(ctx) == [
        ("git", "clone", "https://example.invalid/r.git", str(dest)),
        ("git", "-C", str(dest), "checkout", "--detach", "abc1234"),
    ]


def test_init_submodules_runs_in_the_repo(ctx: BuildContext, tmp_path: Path) -> None:
    # The shell relied on cwd; passing -C makes the target explicit.
    init_submodules(ctx, tmp_path / "r")
    assert _calls(ctx) == [("git", "-C", str(tmp_path / "r"), "submodule", "update", "--init")]


def test_init_submodules_can_target_a_subdirectory(ctx: BuildContext, tmp_path: Path) -> None:
    # The firmware step needs `(cd pico-sdk && git submodule update --init)`.
    init_submodules(ctx, tmp_path / "r", subdir=Path("pico-sdk"))
    assert _calls(ctx) == [
        ("git", "-C", str(tmp_path / "r" / "pico-sdk"), "submodule", "update", "--init")
    ]


def test_make_uses_parallel_jobs_in_the_repo(ctx: BuildContext, tmp_path: Path) -> None:
    # `male` does not exist in the image (see docs/FINDINGS.md); make is the
    # only path that has ever run.
    make(ctx, tmp_path / "r", jobs=4)
    assert _calls(ctx) == [("make", "-C", str(tmp_path / "r"), "-j4")]


def test_dldi_patch_invokes_dlditool(ctx: BuildContext, tmp_path: Path) -> None:
    dlditool = tmp_path / "dlditool"
    dlditool.write_text("", encoding="utf-8")
    dlditool.chmod(0o755)
    dldi, target = tmp_path / "d.dldi", tmp_path / "t.nds"

    dldi_patch(ctx, dldi, target, dlditool=dlditool)

    assert _calls(ctx) == [(str(dlditool), str(dldi), str(target))]


def test_dldi_patch_fails_loudly_when_dlditool_is_missing(
    ctx: BuildContext, tmp_path: Path
) -> None:
    with pytest.raises(BuildError, match="dlditool"):
        dldi_patch(ctx, tmp_path / "d.dldi", tmp_path / "t.nds", dlditool=tmp_path / "nope")
