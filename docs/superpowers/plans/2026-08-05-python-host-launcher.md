# PR 2: Portable Host Launcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m dspico build` builds the image and runs the container on Windows, macOS (including Apple Silicon) and Linux, while still executing the existing `compile_resources.sh` — so portability is proven before the pipeline itself is ported.

**Architecture:** Two command builders (`host/image.py`, `host/launcher.py`) turn a `BuildConfig` plus a `HostEnv` into an exact `argv`. A single `runtime.py` seam executes it. Tests assert the argv and never spawn a process. The only shell change is a final ownership fix inside `compile_resources.sh`.

**Tech Stack:** Python 3.11+ stdlib (`argparse`, `subprocess`, `shlex`, `pathlib`), pytest, mypy `--strict`, ruff, mutmut.

## Global Constraints

Everything in PR 1's Global Constraints still applies (zero runtime dependencies, Python 3.11 floor, three-OS matrix, `tmp_path` for absolute paths, mypy `--strict`, line length 100, Conventional Commits, no copyrighted binaries in tests). In addition:

- **`build_resources.sh` stays working and untouched.** It is deleted in PR 4, not here. Both launchers must produce equivalent builds.
- **`compile_resources.sh` gets exactly one additive change** — the ownership fix in Task 6. Nothing else in it moves.
- **`Dockerfile` is not modified.** See "Two spec corrections" below.
- **No test may invoke docker or podman.** The container-level check in Task 6 is a manual step, run once, with its output recorded.

## Two spec corrections

The spec's portability section was wrong about UID handling. Both corrections were verified on the target machine, and this plan supersedes it.

**1. `--build-arg USER_UID` would be a no-op.** `Dockerfile:62` switches to `USER root` for the blocksds symlink and the .NET 9 install and never switches back, so the final `USER` is root and the `builder` account it creates is never the one running the build. (This is the "final USER is root" finding hadolint already reports and `CLAUDE.md` already lists as known.) Passing build args for a user nothing runs as is cargo cult, so `build_image_argv` does not pass them.

**2. The chown target is not the host's UID.** Artifacts land root-owned under rootful Docker, which is the real bug. But under rootless podman the host user maps to *container root*, so chowning `/outputs` to the literal host UID (1000) would hand every artifact to an unrelated subuid (10999) — actively breaking a case that currently works. The correct target is the owner the container sees on the mount point itself: the host created `outputs/` as the invoking user, so `stat -c %u /outputs` resolves to the right UID under rootful Docker, rootless podman, `--userns=keep-id` and Docker Desktop alike. That needs no engine detection and no environment variables, which is why `build_resources.sh` needs no change.

**Dockerfile `WF_BOOTSTRAP_ARCH` is dropped as YAGNI.** The spec proposed parameterising the bootstrap architecture, but `--platform linux/amd64` makes the container itself x86_64, so the existing x86_64 bootstrap is already the correct one to fetch. A build arg for a native arm64 bootstrap that does not exist buys nothing and costs a full image rebuild.

---

### Task 1: The subprocess seam

**Files:**
- Create: `dspico/runtime.py`
- Create: `tests/conftest.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `dspico.errors.BuildError`.
- Produces:
  - `dspico.runtime.CommandError(argv: Sequence[str], returncode: int, *, step: str | None = None)` with `.argv: tuple[str, ...]`, `.returncode: int`.
  - `dspico.runtime.Runner` — Protocol with `run(self, argv: Sequence[str], *, step: str | None = None) -> None`.
  - `dspico.runtime.SubprocessRunner(*, echo: Callable[[str], None] = print)`.
  - `dspico.runtime.DryRunRunner(*, echo: Callable[[str], None] = print)`.
  - `tests/conftest.py` provides a `FakeRunner` class and a `runner` fixture, used by Tasks 3-5.

- [ ] **Step 1: Write the failing tests**

Create `tests/conftest.py`:

```python
"""Shared test doubles."""

from collections.abc import Sequence

import pytest


class FakeRunner:
    """Records commands instead of running them.

    Every step test asserts against ``calls``, so the suite never needs docker,
    a network, or the toolchain.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.steps: list[str | None] = []

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        self.calls.append(tuple(argv))
        self.steps.append(step)


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()
```

Create `tests/test_runtime.py`:

```python
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


def test_dry_run_runner_echoes_without_executing(tmp_path: object) -> None:
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

    fake: Runner = FakeRunner()
    fake.run(["a", "b"], step="s")
    assert isinstance(fake, FakeRunner)
    recorded: Sequence[tuple[str, ...]] = fake.calls
    assert recorded == [("a", "b")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.runtime'`

- [ ] **Step 3: Write `dspico/runtime.py`**

```python
"""The single seam between the orchestrator and the outside world.

Everything that spawns a process goes through here, so tests can swap in a
recorder and stay offline. Nothing else in the package imports ``subprocess``.
"""

import shlex
import subprocess
from collections.abc import Callable, Sequence
from typing import Protocol

from dspico.errors import BuildError


class CommandError(BuildError):
    """A command exited non-zero."""

    def __init__(
        self, argv: Sequence[str], returncode: int, *, step: str | None = None
    ) -> None:
        super().__init__(
            f"command failed with exit code {returncode}: {shlex.join(argv)}", step=step
        )
        self.argv = tuple(argv)
        self.returncode = returncode


class Runner(Protocol):
    """Runs a command, raising :class:`CommandError` if it fails."""

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None: ...


class SubprocessRunner:
    """Runs commands for real.

    Echoes each command first so that a failed build can be reproduced by hand
    from the log. ``shlex.join`` quotes POSIX-style even on Windows; that is fine
    because the echo is for humans and the command itself is passed as a list,
    never through a shell.
    """

    def __init__(self, *, echo: Callable[[str], None] = print) -> None:
        self._echo = echo

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        self._echo(f"$ {shlex.join(argv)}")
        completed = subprocess.run(list(argv), check=False)  # noqa: S603
        if completed.returncode != 0:
            raise CommandError(argv, completed.returncode, step=step)


class DryRunRunner:
    """Echoes commands without running them, for ``--dry-run``.

    Lets a user confirm the exact docker invocation on a new platform without
    paying for a full build.
    """

    def __init__(self, *, echo: Callable[[str], None] = print) -> None:
        self._echo = echo

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        self._echo(f"$ {shlex.join(argv)}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runtime.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/runtime.py tests/conftest.py tests/test_runtime.py
git commit -m "feat(python): add the subprocess seam and its test doubles"
```

---

### Task 2: Render host paths for bind mounts

**Files:**
- Modify: `dspico/hostenv.py`
- Test: `tests/test_hostenv.py`

**Interfaces:**
- Produces: `dspico.hostenv.docker_mount_path(path: PurePath) -> str`.

This lands in `hostenv.py` deliberately: it is pure, and that module is gated at a 100% mutation score.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hostenv.py` (and add `from pathlib import PurePosixPath, PureWindowsPath` to its imports, plus `docker_mount_path` to the `dspico.hostenv` import list):

```python
def test_windows_paths_render_with_forward_slashes() -> None:
    # Asserted with PureWindowsPath so the case is covered on every CI platform,
    # not only on the Windows leg.
    rendered = docker_mount_path(PureWindowsPath(r"C:\Users\a\inputs"))
    assert rendered == "C:/Users/a/inputs"


def test_windows_drive_letter_is_preserved() -> None:
    # Docker needs the drive letter; stripping it would mount the wrong thing.
    assert docker_mount_path(PureWindowsPath(r"D:\build\outputs")).startswith("D:/")


def test_posix_paths_are_unchanged() -> None:
    assert docker_mount_path(PurePosixPath("/home/a/inputs")) == "/home/a/inputs"


def test_spaces_are_preserved_verbatim() -> None:
    # The argv is passed as a list, never through a shell, so no quoting here.
    assert docker_mount_path(PureWindowsPath(r"C:\My Files\in")) == "C:/My Files/in"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_hostenv.py -k mount_path -v`
Expected: FAIL with `ImportError: cannot import name 'docker_mount_path'`

- [ ] **Step 3: Add the function to `dspico/hostenv.py`**

Add `from pathlib import PurePath` to the imports and append:

```python
def docker_mount_path(path: PurePath) -> str:
    """Render a host path for a ``-v`` argument.

    Docker accepts forward slashes on every platform, and
    ``PureWindowsPath.as_posix()`` keeps the drive letter intact
    (``C:\\Users\\a`` becomes ``C:/Users/a``). Backslashes would also be accepted
    but make the colon-separated ``-v`` argument needlessly ambiguous to read.
    """
    return path.as_posix()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_hostenv.py -v`
Expected: 24 passed

- [ ] **Step 5: Run the static gates and the mutation gate**

Run:
```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
.venv/bin/mutmut run >/dev/null 2>&1; .venv/bin/mutmut results
```
Expected: gates exit 0; `mutmut results` prints nothing. `hostenv.py` is gated at 100%, so any survivor here is a missing test.

- [ ] **Step 6: Commit**

```bash
git add dspico/hostenv.py tests/test_hostenv.py
git commit -m "feat(python): render host paths for docker bind mounts"
```

---

### Task 3: The image build command

**Files:**
- Create: `dspico/host/__init__.py`
- Create: `dspico/host/image.py`
- Test: `tests/test_image.py`

**Interfaces:**
- Consumes: `BuildConfig`, `HostEnv`, `docker_platform`.
- Produces: `dspico.host.image.build_image_argv(config: BuildConfig, env: HostEnv, *, context_dir: Path, engine: str = "docker") -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image.py`:

```python
"""The image build command, asserted exactly.

This is where "arm64 silently lost its --platform" would be caught.
"""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.host.image import build_image_argv
from dspico.hostenv import HostEnv

X86_LINUX = HostEnv(system="Linux", machine="x86_64", uid=1000, gid=1000)
APPLE_SILICON = HostEnv(system="Darwin", machine="arm64", uid=501, gid=20)


@pytest.fixture
def config(tmp_path: Path) -> BuildConfig:
    return BuildConfig(
        inputs_dir=tmp_path / "inputs",
        outputs_dir=tmp_path / "outputs",
        image_name="dspico-compiler:test",
    )


def test_x86_build_has_no_platform_flag(config: BuildConfig, tmp_path: Path) -> None:
    argv = build_image_argv(config, X86_LINUX, context_dir=tmp_path)
    assert argv == ["docker", "build", "-t", "dspico-compiler:test", str(tmp_path)]


def test_apple_silicon_build_forces_amd64(config: BuildConfig, tmp_path: Path) -> None:
    argv = build_image_argv(config, APPLE_SILICON, context_dir=tmp_path)
    assert argv[:4] == ["docker", "build", "--platform", "linux/amd64"]
    assert argv[-1] == str(tmp_path)


def test_engine_is_overridable(config: BuildConfig, tmp_path: Path) -> None:
    # podman ships a docker-compatible CLI; the caller picks the binary.
    argv = build_image_argv(config, X86_LINUX, context_dir=tmp_path, engine="podman")
    assert argv[0] == "podman"


def test_no_user_build_args_are_passed(config: BuildConfig, tmp_path: Path) -> None:
    # Dockerfile:62 leaves the final USER as root, so the `builder` account the
    # USER_UID/USER_GID args configure is never what runs the build. Passing them
    # would be cargo cult; ownership is fixed inside the container instead.
    argv = build_image_argv(config, X86_LINUX, context_dir=tmp_path)
    assert "--build-arg" not in argv


def test_image_name_comes_from_the_config(tmp_path: Path) -> None:
    config = BuildConfig(
        inputs_dir=tmp_path / "in",
        outputs_dir=tmp_path / "out",
        image_name="custom:tag",
    )
    argv = build_image_argv(config, X86_LINUX, context_dir=tmp_path)
    assert argv[argv.index("-t") + 1] == "custom:tag"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_image.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.host'`

- [ ] **Step 3: Write the module**

Create `dspico/host/__init__.py`:

```python
"""Host-side concerns: building the image and launching the container."""
```

Create `dspico/host/image.py`:

```python
"""The command that builds the container image."""

from pathlib import Path

from dspico.config import BuildConfig
from dspico.hostenv import HostEnv, docker_platform


def build_image_argv(
    config: BuildConfig,
    env: HostEnv,
    *,
    context_dir: Path,
    engine: str = "docker",
) -> list[str]:
    """The full ``docker build`` invocation for this host.

    No ``--build-arg USER_UID``: ``Dockerfile`` ends on ``USER root``, so the
    ``builder`` account those args configure never runs the build. Output
    ownership is corrected inside the container instead.
    """
    argv = [engine, "build"]
    platform = docker_platform(env)
    if platform is not None:
        argv += ["--platform", platform]
    argv += ["-t", config.image_name, str(context_dir)]
    return argv
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_image.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/host tests/test_image.py
git commit -m "feat(python): build the docker build command for the host"
```

---

### Task 4: The container run command

**Files:**
- Create: `dspico/host/launcher.py`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Produces:
  - `dspico.host.launcher.run_container_argv(config: BuildConfig, env: HostEnv, *, script_path: Path, engine: str = "docker") -> list[str]`
  - Constants `CONTAINER_INPUTS = "/inputs"`, `CONTAINER_OUTPUTS = "/outputs"`, `CONTAINER_SCRIPT = "/dspico/compile_resources.sh"`.

The argv must stay equivalent to `build_resources.sh:14-22`, which is the whole point of the parallel-migration strategy.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_launcher.py`:

```python
"""The container run command, asserted exactly.

Must stay equivalent to build_resources.sh:14-22 for as long as both launchers
exist, so the two paths cannot silently diverge.
"""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.host.launcher import (
    CONTAINER_INPUTS,
    CONTAINER_OUTPUTS,
    CONTAINER_SCRIPT,
    run_container_argv,
)
from dspico.hostenv import HostEnv

X86_LINUX = HostEnv(system="Linux", machine="x86_64", uid=1000, gid=1000)
APPLE_SILICON = HostEnv(system="Darwin", machine="arm64", uid=501, gid=20)


@pytest.fixture
def config(tmp_path: Path) -> BuildConfig:
    return BuildConfig(
        inputs_dir=tmp_path / "inputs",
        outputs_dir=tmp_path / "outputs",
        image_name="dspico-compiler:test",
    )


def test_container_paths_are_pinned() -> None:
    assert CONTAINER_INPUTS == "/inputs"
    assert CONTAINER_OUTPUTS == "/outputs"
    assert CONTAINER_SCRIPT == "/dspico/compile_resources.sh"


def test_full_default_invocation(config: BuildConfig, tmp_path: Path) -> None:
    script = tmp_path / "compile_resources.sh"
    argv = run_container_argv(config, X86_LINUX, script_path=script)
    assert argv == [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{(tmp_path / 'inputs').as_posix()}:/inputs:ro",
        "-v",
        f"{(tmp_path / 'outputs').as_posix()}:/outputs",
        "-v",
        f"{script.as_posix()}:/dspico/compile_resources.sh:ro",
        "-e",
        "ENABLE_WRFUXXED=0",
        "-e",
        "ENABLE_NTRBOOT=0",
        "-e",
        "USE_EDO_FIRMWARE=0",
        "--entrypoint",
        "bash",
        "dspico-compiler:test",
        "-lc",
        "/dspico/compile_resources.sh",
    ]


def test_inputs_are_mounted_read_only(config: BuildConfig, tmp_path: Path) -> None:
    # /inputs holds the user's copyrighted dumps and the pipeline must never
    # write there; losing :ro would be silent until something corrupted them.
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    inputs_mount = next(a for a in argv if a.endswith(":/inputs:ro"))
    assert inputs_mount.endswith(":ro")


def test_outputs_are_mounted_writable(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    assert any(a.endswith(":/outputs") for a in argv)


def test_apple_silicon_forces_amd64(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(config, APPLE_SILICON, script_path=tmp_path / "s.sh")
    assert argv[:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, ["ENABLE_WRFUXXED=0", "ENABLE_NTRBOOT=0", "USE_EDO_FIRMWARE=0"]),
        ({"wrfuxxed": True}, ["ENABLE_WRFUXXED=1", "ENABLE_NTRBOOT=0", "USE_EDO_FIRMWARE=0"]),
        ({"ntrboot": True}, ["ENABLE_WRFUXXED=0", "ENABLE_NTRBOOT=1", "USE_EDO_FIRMWARE=0"]),
        (
            {"edo_firmware": True},
            ["ENABLE_WRFUXXED=0", "ENABLE_NTRBOOT=0", "USE_EDO_FIRMWARE=1"],
        ),
        (
            {"wrfuxxed": True, "ntrboot": True, "edo_firmware": True},
            ["ENABLE_WRFUXXED=1", "ENABLE_NTRBOOT=1", "USE_EDO_FIRMWARE=1"],
        ),
    ],
)
def test_flags_become_the_env_vars_the_shell_pipeline_reads(
    tmp_path: Path, flags: dict[str, bool], expected: list[str]
) -> None:
    # compile_resources.sh still reads these names; the CLI flag is only the
    # host-side spelling.
    config = BuildConfig(
        inputs_dir=tmp_path / "inputs", outputs_dir=tmp_path / "outputs", **flags
    )
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    env_values = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert env_values == expected


def test_engine_is_overridable(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(
        config, X86_LINUX, script_path=tmp_path / "s.sh", engine="podman"
    )
    assert argv[0] == "podman"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_launcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.host.launcher'`

- [ ] **Step 3: Write `dspico/host/launcher.py`**

```python
"""The command that runs the build inside the container."""

from pathlib import Path

from dspico.config import BuildConfig
from dspico.hostenv import HostEnv, docker_mount_path, docker_platform

CONTAINER_INPUTS = "/inputs"
CONTAINER_OUTPUTS = "/outputs"
CONTAINER_SCRIPT = "/dspico/compile_resources.sh"


def run_container_argv(
    config: BuildConfig,
    env: HostEnv,
    *,
    script_path: Path,
    engine: str = "docker",
) -> list[str]:
    """The full ``docker run`` invocation for this build.

    Kept equivalent to ``build_resources.sh`` while both launchers exist: the
    pipeline script is bind-mounted rather than baked into the image, so editing
    it does not cost an image rebuild.
    """
    argv = [engine, "run", "--rm"]
    platform = docker_platform(env)
    if platform is not None:
        argv += ["--platform", platform]
    argv += [
        "-v",
        f"{docker_mount_path(config.inputs_dir)}:{CONTAINER_INPUTS}:ro",
        "-v",
        f"{docker_mount_path(config.outputs_dir)}:{CONTAINER_OUTPUTS}",
        "-v",
        f"{docker_mount_path(script_path)}:{CONTAINER_SCRIPT}:ro",
        "-e",
        f"ENABLE_WRFUXXED={int(config.wrfuxxed)}",
        "-e",
        f"ENABLE_NTRBOOT={int(config.ntrboot)}",
        "-e",
        f"USE_EDO_FIRMWARE={int(config.edo_firmware)}",
        "--entrypoint",
        "bash",
        config.image_name,
        "-lc",
        CONTAINER_SCRIPT,
    ]
    return argv
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_launcher.py -v`
Expected: 11 passed

- [ ] **Step 5: Confirm equivalence with the shell launcher by eye**

Run: `sed -n '14,22p' build_resources.sh`
Compare against `test_full_default_invocation`. Every flag, mount and the `bash -lc` entrypoint must match. The one intended difference is `--platform`, which the shell version never had.

- [ ] **Step 6: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 7: Commit**

```bash
git add dspico/host/launcher.py tests/test_launcher.py
git commit -m "feat(python): build the docker run command for the pipeline"
```

---

### Task 5: The command-line interface

**Files:**
- Create: `dspico/cli.py`
- Create: `dspico/__main__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `dspico.cli.build_parser() -> argparse.ArgumentParser`
  - `dspico.cli.config_from_args(args: argparse.Namespace, *, cwd: Path) -> BuildConfig`
  - `dspico.cli.main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
"""The CLI turns flags into a BuildConfig and a pair of commands."""

from pathlib import Path

import pytest

from dspico.cli import build_parser, config_from_args, main


def test_flags_default_to_off(tmp_path: Path) -> None:
    args = build_parser().parse_args(["build"])
    config = config_from_args(args, cwd=tmp_path)
    assert config.wrfuxxed is False
    assert config.ntrboot is False
    assert config.edo_firmware is False


def test_inputs_and_outputs_default_to_the_working_directory(tmp_path: Path) -> None:
    args = build_parser().parse_args(["build"])
    config = config_from_args(args, cwd=tmp_path)
    assert config.inputs_dir == tmp_path / "inputs"
    assert config.outputs_dir == tmp_path / "outputs"


def test_relative_directory_arguments_are_resolved_against_cwd(tmp_path: Path) -> None:
    # BuildConfig rejects relative paths, so the CLI must absolutise first.
    args = build_parser().parse_args(["build", "--inputs", "my-in"])
    config = config_from_args(args, cwd=tmp_path)
    assert config.inputs_dir.is_absolute()
    assert config.inputs_dir == tmp_path / "my-in"


@pytest.mark.parametrize(
    ("flag", "attribute"),
    [
        ("--wrfuxxed", "wrfuxxed"),
        ("--ntrboot", "ntrboot"),
        ("--edo-firmware", "edo_firmware"),
    ],
)
def test_each_feature_flag_sets_its_field(
    tmp_path: Path, flag: str, attribute: str
) -> None:
    args = build_parser().parse_args(["build", flag])
    config = config_from_args(args, cwd=tmp_path)
    assert getattr(config, attribute) is True


def test_image_name_is_overridable(tmp_path: Path) -> None:
    args = build_parser().parse_args(["build", "--image", "mine:dev"])
    assert config_from_args(args, cwd=tmp_path).image_name == "mine:dev"


def test_dry_run_prints_both_commands_and_runs_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "compile_resources.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    code = main(
        [
            "build",
            "--dry-run",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(tmp_path / "outputs"),
            "--context",
            str(tmp_path),
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "build" in out
    assert "run --rm" in out or "run" in out


def test_missing_dockerfile_fails_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A wrong --context is an easy mistake and would otherwise surface as an
    # opaque docker error several seconds later.
    code = main(
        [
            "build",
            "--dry-run",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(tmp_path / "outputs"),
            "--context",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert "Dockerfile" in capsys.readouterr().err


def test_identical_inputs_and_outputs_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["build", "--dry-run", "--inputs", str(tmp_path), "--outputs", str(tmp_path)]
    )
    assert code == 1
    assert "differ" in capsys.readouterr().err


def test_no_subcommand_shows_usage() -> None:
    assert main([]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.cli'`

- [ ] **Step 3: Write `dspico/cli.py`**

```python
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
    build.add_argument(
        "--edo-firmware", action="store_true", help="use the edo9300 firmware fork"
    )
    build.add_argument(
        "--skip-image-build", action="store_true", help="reuse the existing image"
    )
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

    dockerfile = context_dir / "Dockerfile"
    if not dockerfile.is_file():
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

    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    runner.run(
        run_container_argv(config, env, script_path=script_path, engine=args.engine),
        step="pipeline",
    )
    print(f"Finished. Outputs are in {config.outputs_dir}")


def main(argv: Sequence[str] | None = None) -> int:
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
```

- [ ] **Step 4: Write `dspico/__main__.py`**

```python
"""Entry point for ``python -m dspico``."""

import sys

from dspico.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Register the console script**

Add to `pyproject.toml` after the `[project]` table:

```toml
[project.scripts]
dspico = "dspico.cli:main"
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
.venv/bin/python -m pip install -q -e ".[dev]"
.venv/bin/python -m pytest tests/test_cli.py -v
```
Expected: 12 passed

- [ ] **Step 7: Confirm the CLI works end to end in dry-run**

Run: `.venv/bin/python -m dspico build --dry-run --wrfuxxed --ntrboot --edo-firmware`
Expected: two `$ docker …` lines, the second carrying `ENABLE_WRFUXXED=1 … ENABLE_NTRBOOT=1 … USE_EDO_FIRMWARE=1`, and no build actually starting.

- [ ] **Step 8: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 9: Commit**

```bash
git add dspico/cli.py dspico/__main__.py pyproject.toml tests/test_cli.py
git commit -m "feat(python): add the dspico build CLI with a dry-run mode"
```

---

### Task 6: Correct artifact ownership inside the container

**Files:**
- Modify: `compile_resources.sh`

**Interfaces:**
- Consumes: nothing from the Python package. Deliberately self-contained so `build_resources.sh` also gets the fix without changing.
- Produces: nothing importable.

The container runs as root (`Dockerfile:62` never switches back from `USER root`), so under rootful Docker every artifact lands root-owned and the user cannot delete their own `outputs/`.

The chown target must **not** be the host's UID. Under rootless podman the host user maps to container root, so chowning to the literal host UID hands the files to an unrelated subuid. Reading the owner the container sees on `/outputs` is correct under every engine, because the host created that directory as the invoking user.

- [ ] **Step 1: Add the function**

In `compile_resources.sh`, after `setup_dirs`, add:

```bash
# Hand /outputs back to whoever owns the mount point on the host.
#
# The container runs as root, so artifacts would land root-owned under rootful
# Docker. The right target is NOT the host's UID: under rootless podman the host
# user maps to container root, and chowning to the literal host UID would hand
# every artifact to an unrelated subuid. The mount point was created on the host
# by the invoking user, so whatever UID the container sees on it is the correct
# target under rootful Docker, rootless podman and Docker Desktop alike.
fix_ownership() {
  local uid gid
  uid=$(stat -c %u /outputs 2>/dev/null) || return 0
  gid=$(stat -c %g /outputs 2>/dev/null) || return 0
  if ! chown -R "$uid:$gid" "$OUT_BASE" 2>/dev/null; then
    warn "⚠ Could not set ownership of $OUT_BASE to $uid:$gid; artifacts may be root-owned"
  fi
}
```

Ownership is cosmetic relative to the artifacts themselves, so a failure warns rather than aborting a build that otherwise succeeded — the same treatment `copy_if_exists` already gets.

- [ ] **Step 2: Call it at the end of `main`**

In `main()`, immediately after `step_firmware_ntrboot` and before the `echo ""` that starts the summary, add:

```bash
  fix_ownership
```

- [ ] **Step 3: Verify the script still lints and parses**

Run:
```bash
shellcheck --severity=warning build_resources.sh compile_resources.sh
bash -n compile_resources.sh && sh -n build_resources.sh && echo "syntax ok"
```
Expected: shellcheck silent, "syntax ok".

- [ ] **Step 4: Verify the ownership logic in a real container**

This needs no copyrighted inputs and no toolchain — a plain debian image is enough.

```bash
rm -rf /tmp/own-test && mkdir -p /tmp/own-test/dspico
docker run --rm -v /tmp/own-test:/outputs debian:bookworm bash -c '
  set -eu
  OUT_BASE=/outputs/dspico
  warn() { echo "$1"; }
  uid=$(stat -c %u /outputs); gid=$(stat -c %g /outputs)
  echo "container sees /outputs as ${uid}:${gid}"
  touch "$OUT_BASE/artifact.bin"
  chown -R "$uid:$gid" "$OUT_BASE"
'
ls -ln /tmp/own-test/dspico/artifact.bin
stat -c "%u:%u" /tmp/own-test /tmp/own-test/dspico/artifact.bin
```
Expected: the artifact's host UID equals the host UID of `/tmp/own-test` — that is, your own. Record the observed output in the commit message.

- [ ] **Step 5: Commit**

```bash
git add compile_resources.sh
git commit -m "fix(compile): give build artifacts back to the invoking user"
```

---

### Task 7: Document the portable launcher

**Files:**
- Modify: `README.md` (Prerequisites, Quick Start, Advanced Configuration)
- Modify: `CLAUDE.md` (Commands section)

**Interfaces:** none.

- [ ] **Step 1: Update the README Prerequisites**

Replace:

```markdown
1. **Linux or WSL** environment
2. **Docker** installed and running
3. **Blowfish encryption tables** (see below)
```

with:

```markdown
1. **Docker** (or Podman) installed and running
2. **Python 3.11+** on the host
3. **Blowfish encryption tables** (see below)

Runs on Linux, macOS (Intel and Apple Silicon) and Windows. On a non-x86_64 host
the toolchain image runs emulated, so expect a considerably slower build.
```

- [ ] **Step 2: Document the new command in the README**

In **2. Build All Components**, add above the existing `./build_resources.sh` examples:

````markdown
```bash
# Portable launcher — same on Linux, macOS and Windows
python -m dspico build

# Feature flags are CLI flags, so they work identically in PowerShell
python -m dspico build --wrfuxxed --ntrboot --edo-firmware

# See the exact docker commands without running a build
python -m dspico build --dry-run

# Custom directories and image name
python -m dspico build --inputs /path/to/inputs --outputs /path/to/outputs --image mine:dev
```

`./build_resources.sh` still works and produces the same result, but it needs a
POSIX shell. It will be removed once the Python pipeline is validated.
````

- [ ] **Step 3: Update the CLAUDE.md Commands section**

Add above the existing `./build_resources.sh` block:

````markdown
```bash
# Portable launcher (Linux/macOS/Windows). Runs the same compile_resources.sh.
python -m dspico build --wrfuxxed --ntrboot --edo-firmware
python -m dspico build --dry-run     # print the docker commands, run nothing
```
````

- [ ] **Step 4: Verify the documented commands actually parse**

Run:
```bash
.venv/bin/python -m dspico build --dry-run --wrfuxxed --ntrboot --edo-firmware >/dev/null && echo "documented flags accepted"
.venv/bin/python -m dspico build --help >/dev/null && echo "help works"
```
Expected: both lines print.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document the portable python launcher"
```

---

## Definition of done

- [ ] `.venv/bin/python -m pytest` passes; the suite grew by roughly 35 tests.
- [ ] `ruff check .`, `ruff format --check .` and `mypy` all exit 0.
- [ ] `mutmut run` still reports zero survivors (`hostenv.py` gained `docker_mount_path`).
- [ ] `python -m dspico build --dry-run` prints a `docker build` and a `docker run` whose flags match `build_resources.sh:14-22`, plus `--platform` where the host needs it.
- [ ] `shellcheck --severity=warning` passes on both shell scripts.
- [ ] `git diff main -- Dockerfile` is empty.
- [ ] The only `compile_resources.sh` change is `fix_ownership` and its single call site.
- [ ] The ownership behaviour was observed in a real container (Task 6, Step 4), not assumed.
- [ ] The PR body carries a **How to test manually** section: the exact flags, which input files must be present, the expected `outputs/dspico/sd_card/` contents, and confirmation that a missing Blowfish table still fails loudly.
