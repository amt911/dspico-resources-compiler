"""runtime.py is the only place the orchestrator talks to the outside world."""

import sys
from collections.abc import Sequence

import pytest

from dspico.errors import BuildError
from dspico.runtime import CommandError, DryRunRunner, Runner, SubprocessRunner


def test_command_error_is_a_build_error() -> None:
    assert issubclass(CommandError, BuildError)


def test_command_error_reports_the_command_and_code() -> None:
    error = CommandError(["docker", "build", "."], 2, step="image")
    assert error.argv == ("docker", "build", ".")
    assert error.returncode == 2
    assert error.step == "image"
    assert "exit code 2" in error.message
    assert "docker build ." in error.message


def test_subprocess_runner_runs_a_successful_command() -> None:
    echoed: list[str] = []
    SubprocessRunner(echo=echoed.append).run([sys.executable, "-c", "pass"])
    assert len(echoed) == 1
    assert echoed[0].startswith("$ ")


def test_subprocess_runner_raises_on_a_failing_command() -> None:
    with pytest.raises(CommandError) as caught:
        SubprocessRunner(echo=lambda _: None).run(
            [sys.executable, "-c", "raise SystemExit(3)"], step="dldi"
        )
    assert caught.value.returncode == 3
    assert caught.value.step == "dldi"


def test_dry_run_runner_echoes_without_executing() -> None:
    # Uses a command that would fail loudly if it were actually executed.
    echoed: list[str] = []
    DryRunRunner(echo=echoed.append).run([sys.executable, "-c", "raise SystemExit(9)"])
    assert len(echoed) == 1
    assert "SystemExit(9)" in echoed[0]


def test_both_runners_satisfy_the_protocol() -> None:
    # Structural check: the CLI accepts either, so they must stay interchangeable.
    real: Runner = SubprocessRunner()
    dry: Runner = DryRunRunner()
    assert callable(real.run)
    assert callable(dry.run)


def test_fake_runner_satisfies_the_protocol() -> None:
    from tests.conftest import FakeRunner

    fake = FakeRunner()
    # The annotation is the assertion: if FakeRunner ever drifts from the
    # protocol, mypy fails here rather than the step tests failing obscurely.
    as_protocol: Runner = fake
    as_protocol.run(["a", "b"], step="s")
    recorded: Sequence[tuple[str, ...]] = fake.calls
    assert recorded == [("a", "b")]
    assert fake.steps == ["s"]
