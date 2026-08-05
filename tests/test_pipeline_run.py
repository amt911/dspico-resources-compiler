"""The in-container entry point."""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.errors import BuildError
from dspico.pipeline.context import BuildContext
from dspico.pipeline.plan import build_plan
from dspico.pipeline.run import (
    COMPONENT_STEPS,
    CONTAINER_INPUTS,
    CONTAINER_OUTPUTS,
    PENDING_STEPS,
    build_run_parser,
    dispatch,
    main,
)
from tests.conftest import FakeRunner


def test_container_mount_points_are_pinned() -> None:
    assert str(CONTAINER_INPUTS) == "/inputs"
    assert str(CONTAINER_OUTPUTS) == "/outputs"


def test_flags_default_to_off() -> None:
    args = build_run_parser().parse_args([])
    assert args.wrfuxxed is False
    assert args.ntrboot is False
    assert args.edo_firmware is False


def test_flags_can_be_enabled() -> None:
    args = build_run_parser().parse_args(["--wrfuxxed", "--ntrboot", "--edo-firmware"])
    assert args.wrfuxxed is True
    assert args.ntrboot is True
    assert args.edo_firmware is True


def test_jobs_defaults_to_something_positive() -> None:
    assert build_run_parser().parse_args([]).jobs >= 1


def test_every_planned_step_has_a_dispatch_route(tmp_path: Path) -> None:
    # The guard that matters: if a step is added to the plan and nobody wires
    # it up, this fails instead of the build quietly skipping it.
    config = BuildConfig(
        inputs_dir=tmp_path / "in",
        outputs_dir=tmp_path / "out",
        wrfuxxed=True,
        ntrboot=True,
    )
    routed = set(COMPONENT_STEPS) | set(PENDING_STEPS) | {"sd_card"}
    assert {step.name for step in build_plan(config)} <= routed


def test_unknown_step_raises(tmp_path: Path) -> None:
    ctx = BuildContext(
        config=BuildConfig(inputs_dir=tmp_path / "in", outputs_dir=tmp_path / "out"),
        runner=FakeRunner(),
        inputs=tmp_path / "in",
        out_base=tmp_path / "out" / "dspico",
        work=tmp_path / "work",
    )
    with pytest.raises(BuildError, match="unknown step"):
        dispatch(ctx, "does_not_exist", jobs=1)


@pytest.mark.parametrize("name", PENDING_STEPS)
def test_unported_steps_fail_loudly(tmp_path: Path, name: str) -> None:
    # A not-yet-ported step must abort, never no-op: a silently skipped step
    # produces a build that looks successful and is not.
    ctx = BuildContext(
        config=BuildConfig(inputs_dir=tmp_path / "in", outputs_dir=tmp_path / "out"),
        runner=FakeRunner(),
        inputs=tmp_path / "in",
        out_base=tmp_path / "out" / "dspico",
        work=tmp_path / "work",
    )
    with pytest.raises(BuildError, match="not ported"):
        dispatch(ctx, name, jobs=1)


def test_plan_only_lists_the_steps_without_building(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--plan-only", "--wrfuxxed"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[1/8] dldi" in out
    assert "wrfuxxed" in out


def test_plan_only_reflects_the_edo_ntrboot_rule(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--plan-only", "--ntrboot", "--edo-firmware"])
    assert "ntrboot_variants" not in capsys.readouterr().out
