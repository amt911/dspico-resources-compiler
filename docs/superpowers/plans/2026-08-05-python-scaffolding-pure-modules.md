# PR 1: Python Scaffolding + Pure Modules — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a `dspico/` Python package containing every *decision* the build makes — validated config, host detection, step planning, ROM padding and ntrboot slotting — each built test-first and gated at a 100% mutation score, with **zero change to how the build currently runs**.

**Architecture:** The organizing principle is *separate decision from effect*. This PR delivers only the decision half: four pure modules with no I/O, no subprocess, no network. The shell pipeline (`build_resources.sh`, `compile_resources.sh`) remains the only executable path and is not touched. PR 2 adds the host launcher that consumes these modules; PR 3 adds the pipeline steps.

**Tech Stack:** Python 3.11+ (stdlib only at runtime), pytest, Hypothesis, mypy `--strict`, ruff, mutmut. Dev dependencies only — normal use of the shell build still requires nothing but Docker.

## Global Constraints

- **Runtime dependencies: zero.** `dspico/` imports stdlib only. Third-party packages live exclusively in `[project.optional-dependencies].dev`.
- **Python floor: 3.11.** CI matrix covers 3.11, 3.12, 3.13.
- **Platforms: ubuntu-latest, macos-latest, windows-latest.** Every test must pass on all three. No test may require Docker, network, or the wonderful toolchain.
- **Absolute paths in tests must come from the `tmp_path` fixture.** `Path("/work").is_absolute()` is `True` on POSIX and `False` on Windows — a hardcoded POSIX path will pass on Linux and fail the Windows matrix leg.
- **mypy `--strict` must pass** on `dspico/` and `tests/`. Every function, including tests, is annotated (`-> None` on tests).
- **Line length 100**, enforced by `ruff format`.
- **No behavior change.** `build_resources.sh`, `compile_resources.sh` and `Dockerfile` are not modified in this PR.
- **Commits in English, Conventional Commits.** Scope is `python`, `ci`, or `docs`.
- **Never commit copyrighted binaries.** No test may use or require real Blowfish tables or BIOS dumps.

---

### Task 1: Package scaffolding, tooling config, and the base CI jobs

**Files:**
- Create: `pyproject.toml`
- Create: `dspico/__init__.py`
- Create: `dspico/py.typed`
- Create: `dspico/pipeline/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_package.py`
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable `dspico` package exposing `dspico.__version__: str`. Every later task adds modules under `dspico/`; every later task's tests live under `tests/`.

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` as an empty file, then create `tests/test_package.py`:

```python
"""The package imports cleanly and carries a version. Guards the packaging config."""

import dspico


def test_package_exposes_a_version() -> None:
    assert isinstance(dspico.__version__, str)
    assert dspico.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico'`

- [ ] **Step 3: Create the package**

Create `dspico/__init__.py`:

```python
"""Cross-platform build orchestrator for the DSpico flashcart."""

__version__ = "0.1.0"
```

Create `dspico/py.typed` as an empty file (marks the package as typed for downstream mypy).

Create `dspico/pipeline/__init__.py`:

```python
"""Build pipeline: the ordered steps that produce the SD card layout."""
```

- [ ] **Step 4: Create `pyproject.toml`**

Note there is deliberately **no** `[project.scripts]` entry yet — `dspico.cli:main` does not exist until PR 2, and a dangling entry point breaks `pip install -e .`.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "dspico-resources-compiler"
version = "0.1.0"
description = "Cross-platform build orchestrator for the DSpico flashcart"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "hypothesis>=6",
    "mypy>=1.11",
    "ruff>=0.6",
    "mutmut>=3,<4",
]

[tool.setuptools.packages.find]
include = ["dspico*"]

[tool.setuptools.package-data]
dspico = ["py.typed"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["dspico", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_package.py -v
```
Expected: PASS

- [ ] **Step 6: Verify the static gates pass on an empty package**

Run:
```bash
ruff check .
ruff format --check .
mypy
```
Expected: all three exit 0. If `ruff format --check` fails, run `ruff format .` and re-check.

- [ ] **Step 7: Add Python artifacts to `.gitignore`**

Append to `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.mutmut-cache
mutants/
```

- [ ] **Step 8: Add the `test`, `lint` and `types` jobs to CI**

Append these three jobs to `.github/workflows/ci.yml` under the existing `jobs:` key. Leave the existing `shellcheck`, `hadolint` and `sast` jobs exactly as they are — the shell pipeline is still the live one.

```yaml
  test:
    name: pytest (${{ matrix.os }}, py${{ matrix.python-version }})
    runs-on: ${{ matrix.os }}
    # Blocking. These tests need no Docker, network or toolchain, so the full
    # three-OS matrix is cheap — and it is what actually verifies portability
    # rather than merely claiming it.
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ['3.11', '3.12', '3.13']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -v

  lint:
    name: ruff
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .

  types:
    name: mypy --strict
    runs-on: ubuntu-latest
    # ubuntu only: dspico/hostenv.py calls os.getuid(), which mypy only models
    # on POSIX targets. The runtime guard for Windows is covered by the test matrix.
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install -e ".[dev]"
      - run: mypy
```

- [ ] **Step 9: Extend the SAST job to cover Python**

The existing `sast` job scans `--config r/bash` only. Now that Python exists, add the Python ruleset. In `.github/workflows/ci.yml`, change the `sast` job's final `run` from:

```yaml
      - run: >-
          semgrep scan --disable-version-check --metrics=off
          --config r/bash
```

to:

```yaml
      - run: >-
          semgrep scan --disable-version-check --metrics=off
          --config r/bash --config r/python
```

Leave `continue-on-error: true` as it is — SAST stays advisory.

- [ ] **Step 10: Verify the CI file parses**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`. If PyYAML is missing, run `python -m pip install pyyaml` first.

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml dspico tests .gitignore .github/workflows/ci.yml
git commit -m "feat(python): add package scaffolding, tooling config and CI jobs"
```

---

### Task 2: Errors and validated `BuildConfig`

**Files:**
- Create: `dspico/errors.py`
- Create: `dspico/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: the `dspico` package from Task 1.
- Produces:
  - `dspico.errors.BuildError(message: str, *, step: str | None = None)` with attributes `.message: str` and `.step: str | None`.
  - `dspico.errors.ConfigError(BuildError)`.
  - `dspico.config.BuildConfig(inputs_dir: Path, outputs_dir: Path, wrfuxxed: bool = False, ntrboot: bool = False, edo_firmware: bool = False, image_name: str = DEFAULT_IMAGE_NAME)` — frozen dataclass, validates in `__post_init__`.
  - `dspico.config.BuildConfig.ntrboot_needs_separate_builds: bool` (property).
  - `dspico.config.DEFAULT_IMAGE_NAME: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
"""BuildConfig validates at construction, so no later step can be handed a bad path."""

from pathlib import Path

import pytest

from dspico.config import DEFAULT_IMAGE_NAME, BuildConfig
from dspico.errors import BuildError, ConfigError


def test_default_image_name_is_pinned() -> None:
    # Asserted against the literal, not the constant. Comparing a value to the
    # constant it came from mutates on both sides, so that mutant would survive.
    assert DEFAULT_IMAGE_NAME == "dspico-compiler:latest"


def test_accepts_absolute_distinct_directories(tmp_path: Path) -> None:
    config = BuildConfig(inputs_dir=tmp_path / "inputs", outputs_dir=tmp_path / "outputs")
    assert config.image_name == DEFAULT_IMAGE_NAME
    assert config.wrfuxxed is False
    assert config.ntrboot is False
    assert config.edo_firmware is False


def test_rejects_relative_inputs_dir(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="inputs_dir must be an absolute path"):
        BuildConfig(inputs_dir=Path("inputs"), outputs_dir=tmp_path / "outputs")


def test_rejects_relative_outputs_dir(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="outputs_dir must be an absolute path"):
        BuildConfig(inputs_dir=tmp_path / "inputs", outputs_dir=Path("outputs"))


def test_rejects_identical_directories(tmp_path: Path) -> None:
    # inputs is bind-mounted read-only and outputs read-write; the same path
    # cannot be both.
    with pytest.raises(ConfigError, match="must differ"):
        BuildConfig(inputs_dir=tmp_path, outputs_dir=tmp_path)


def test_rejects_blank_image_name(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="image_name must not be empty"):
        BuildConfig(
            inputs_dir=tmp_path / "inputs",
            outputs_dir=tmp_path / "outputs",
            image_name="   ",
        )


def test_config_is_frozen(tmp_path: Path) -> None:
    config = BuildConfig(inputs_dir=tmp_path / "inputs", outputs_dir=tmp_path / "outputs")
    with pytest.raises(AttributeError):
        config.wrfuxxed = True  # type: ignore[misc]


def test_ntrboot_needs_separate_builds_only_without_edo_firmware(tmp_path: Path) -> None:
    # LNH firmware has 2 ROM slots, so each ntrboot variant needs its own build.
    # The edo9300 fork has 4 slots and embeds them in the single firmware build.
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"

    lnh = BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=True)
    assert lnh.ntrboot_needs_separate_builds is True

    edo = BuildConfig(
        inputs_dir=inputs, outputs_dir=outputs, ntrboot=True, edo_firmware=True
    )
    assert edo.ntrboot_needs_separate_builds is False

    off = BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=False)
    assert off.ntrboot_needs_separate_builds is False

    off_edo = BuildConfig(
        inputs_dir=inputs, outputs_dir=outputs, ntrboot=False, edo_firmware=True
    )
    assert off_edo.ntrboot_needs_separate_builds is False


def test_config_error_is_a_build_error() -> None:
    assert issubclass(ConfigError, BuildError)


def test_build_error_carries_the_failing_step() -> None:
    error = BuildError("clone failed", step="dldi")
    assert error.message == "clone failed"
    assert error.step == "dldi"
    assert str(error) == "clone failed"


def test_build_error_step_defaults_to_none() -> None:
    assert BuildError("boom").step is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.errors'`

- [ ] **Step 3: Write `dspico/errors.py`**

```python
"""Failures the orchestrator raises deliberately, as opposed to crashes."""


class BuildError(Exception):
    """A build failure with a loud, attributable message.

    Replaces the shell pipeline's ``error_exit``. Carrying ``step`` lets the CLI
    report which step failed without every call site formatting its own prefix.
    """

    def __init__(self, message: str, *, step: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.step = step


class ConfigError(BuildError):
    """The requested build configuration is not usable."""
```

- [ ] **Step 4: Write `dspico/config.py`**

```python
"""The validated description of one build."""

from dataclasses import dataclass
from pathlib import Path

from dspico.errors import ConfigError

DEFAULT_IMAGE_NAME = "dspico-compiler:latest"


@dataclass(frozen=True)
class BuildConfig:
    """Everything a build needs to know, validated at construction.

    Validating here means no later step can be handed a relative path that would
    silently produce a broken ``docker run -v`` mount.
    """

    inputs_dir: Path
    outputs_dir: Path
    wrfuxxed: bool = False
    ntrboot: bool = False
    edo_firmware: bool = False
    image_name: str = DEFAULT_IMAGE_NAME

    def __post_init__(self) -> None:
        for label, value in (
            ("inputs_dir", self.inputs_dir),
            ("outputs_dir", self.outputs_dir),
        ):
            if not value.is_absolute():
                raise ConfigError(f"{label} must be an absolute path, got: {value}")
        if self.inputs_dir == self.outputs_dir:
            raise ConfigError("inputs_dir and outputs_dir must differ")
        if not self.image_name.strip():
            raise ConfigError("image_name must not be empty")

    @property
    def ntrboot_needs_separate_builds(self) -> bool:
        """Whether ntrboot requires its own firmware builds.

        LNH-team firmware exposes 2 ROM slots (default.nds, dsimode.nds), so each
        ntrboot variant needs a dedicated build. The edo9300 fork has 4 slots and
        embeds ntrboot in the single main firmware build instead.
        """
        return self.ntrboot and not self.edo_firmware
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 11 passed

- [ ] **Step 6: Run the static gates**

Run: `ruff check . && ruff format --check . && mypy`
Expected: all exit 0

- [ ] **Step 7: Commit**

```bash
git add dspico/errors.py dspico/config.py tests/test_config.py
git commit -m "feat(python): add BuildError and validated BuildConfig"
```

---

### Task 3: Host environment detection

**Files:**
- Create: `dspico/hostenv.py`
- Test: `tests/test_hostenv.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (stdlib only).
- Produces:
  - `dspico.hostenv.HostEnv(system: str, machine: str, uid: int, gid: int)` — frozen dataclass with `.arch: str` and `.is_linux: bool` properties and a `HostEnv.detect() -> HostEnv` classmethod.
  - `dspico.hostenv.normalize_arch(machine: str) -> str`
  - `dspico.hostenv.docker_platform(env: HostEnv) -> str | None`
  - `dspico.hostenv.build_user(env: HostEnv) -> tuple[int, int]`
  - `dspico.hostenv.needs_emulation(env: HostEnv) -> bool`
  - Constants `X86_64`, `AARCH64`, `DEFAULT_CONTAINER_UID`, `DEFAULT_CONTAINER_GID`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hostenv.py`:

```python
"""Host detection decides --platform and the image's build UID/GID.

These are the two things that make the build work off Linux/x86_64, so every
branch is pinned here rather than discovered on a user's machine.
"""

import pytest

from dspico.hostenv import (
    AARCH64,
    DEFAULT_CONTAINER_GID,
    DEFAULT_CONTAINER_UID,
    X86_64,
    HostEnv,
    build_user,
    docker_platform,
    needs_emulation,
    normalize_arch,
)


def test_arch_constants_are_pinned() -> None:
    # Against the literals: a test comparing a value to the constant it came from
    # mutates on both sides and would leave that mutant alive.
    assert X86_64 == "x86_64"
    assert AARCH64 == "aarch64"
    assert DEFAULT_CONTAINER_UID == 1000
    assert DEFAULT_CONTAINER_GID == 1000


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("x86_64", X86_64),
        ("X86_64", X86_64),
        ("AMD64", X86_64),  # what platform.machine() returns on Windows
        ("amd64", X86_64),
        ("x64", X86_64),
        ("  x86_64  ", X86_64),
        ("arm64", AARCH64),  # what platform.machine() returns on macOS
        ("aarch64", AARCH64),
        ("ARM64", AARCH64),
    ],
)
def test_normalize_arch_maps_known_spellings(machine: str, expected: str) -> None:
    assert normalize_arch(machine) == expected


def test_normalize_arch_passes_unknown_through_lowercased() -> None:
    assert normalize_arch("RISCV64") == "riscv64"


def test_no_platform_override_on_x86_64() -> None:
    env = HostEnv(system="Linux", machine="x86_64", uid=1000, gid=1000)
    assert docker_platform(env) is None
    assert needs_emulation(env) is False


def test_forces_amd64_platform_on_apple_silicon() -> None:
    # The wonderful bootstrap tarball only ships an x86_64 build, so any other
    # host arch must run the image emulated.
    env = HostEnv(system="Darwin", machine="arm64", uid=501, gid=20)
    assert docker_platform(env) == "linux/amd64"
    assert needs_emulation(env) is True


def test_forces_amd64_platform_on_linux_aarch64() -> None:
    env = HostEnv(system="Linux", machine="aarch64", uid=1000, gid=1000)
    assert docker_platform(env) == "linux/amd64"


def test_linux_bakes_the_real_uid_and_gid() -> None:
    # Linux bind mounts pass ownership straight through, so outputs/ would land
    # owned by the wrong user if the image kept a hardcoded 1000.
    env = HostEnv(system="Linux", machine="x86_64", uid=1234, gid=5678)
    assert build_user(env) == (1234, 5678)


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
def test_docker_desktop_hosts_keep_the_default_user(system: str) -> None:
    # Docker Desktop maps ownership itself; keeping 1000 means those hosts share
    # one cached image instead of rebuilding per user.
    env = HostEnv(system=system, machine="x86_64", uid=501, gid=20)
    assert build_user(env) == (DEFAULT_CONTAINER_UID, DEFAULT_CONTAINER_GID)


def test_arch_property_normalizes() -> None:
    assert HostEnv(system="Windows", machine="AMD64", uid=1, gid=1).arch == X86_64


def test_is_linux_property() -> None:
    assert HostEnv(system="Linux", machine="x86_64", uid=1, gid=1).is_linux is True
    assert HostEnv(system="Darwin", machine="arm64", uid=1, gid=1).is_linux is False


def test_detect_returns_a_usable_env_on_this_host() -> None:
    # Runs on all three CI platforms. On Windows os.getuid does not exist, so
    # this asserts the fallback rather than crashing with AttributeError.
    env = HostEnv.detect()
    assert env.system
    assert env.machine
    assert env.uid >= 0
    assert env.gid >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hostenv.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.hostenv'`

- [ ] **Step 3: Write `dspico/hostenv.py`**

```python
"""What the host machine is, and what that forces the container invocation to be."""

import os
import platform
from dataclasses import dataclass

X86_64 = "x86_64"
AARCH64 = "aarch64"

_ARCH_ALIASES = {
    "x86_64": X86_64,
    "amd64": X86_64,
    "x64": X86_64,
    "aarch64": AARCH64,
    "arm64": AARCH64,
}

DEFAULT_CONTAINER_UID = 1000
DEFAULT_CONTAINER_GID = 1000


def normalize_arch(machine: str) -> str:
    """Collapse the many spellings of a CPU architecture onto a canonical one.

    ``platform.machine()`` says ``AMD64`` on Windows, ``x86_64`` on Linux and
    ``arm64`` on macOS for what are only two architectures here.
    """
    cleaned = machine.strip().lower()
    return _ARCH_ALIASES.get(cleaned, cleaned)


@dataclass(frozen=True)
class HostEnv:
    """The host facts that change how the container is built and run."""

    system: str
    machine: str
    uid: int
    gid: int

    @classmethod
    def detect(cls) -> "HostEnv":
        """Read the current host. The only impure function in this module."""
        # os.getuid/os.getgid do not exist on Windows.
        uid = os.getuid() if hasattr(os, "getuid") else DEFAULT_CONTAINER_UID
        gid = os.getgid() if hasattr(os, "getgid") else DEFAULT_CONTAINER_GID
        return cls(
            system=platform.system(),
            machine=platform.machine(),
            uid=uid,
            gid=gid,
        )

    @property
    def arch(self) -> str:
        return normalize_arch(self.machine)

    @property
    def is_linux(self) -> bool:
        return self.system == "Linux"


def docker_platform(env: HostEnv) -> str | None:
    """The ``--platform`` value to force, or None when the host needs none.

    The wonderful toolchain bootstrap ships an x86_64 build only, so anything
    else has to run the image under emulation.
    """
    return None if env.arch == X86_64 else "linux/amd64"


def needs_emulation(env: HostEnv) -> bool:
    """Whether the build will run under QEMU, and therefore slowly."""
    return docker_platform(env) is not None


def build_user(env: HostEnv) -> tuple[int, int]:
    """The (uid, gid) to bake into the image so ``outputs/`` is owned by the caller.

    Only Linux bind mounts pass ownership straight through. Docker Desktop on
    macOS and Windows maps it, so those keep the default and share one cached image.
    """
    if env.is_linux:
        return env.uid, env.gid
    return DEFAULT_CONTAINER_UID, DEFAULT_CONTAINER_GID
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hostenv.py -v`
Expected: 20 passed (each parametrized case counts individually)

- [ ] **Step 5: Run the static gates**

Run: `ruff check . && ruff format --check . && mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/hostenv.py tests/test_hostenv.py
git commit -m "feat(python): detect host arch and UID for portable container invocation"
```

---

### Task 4: Step planning with derived numbering

**Files:**
- Create: `dspico/pipeline/plan.py`
- Test: `tests/test_plan.py`

**Interfaces:**
- Consumes: `dspico.config.BuildConfig` (Task 2).
- Produces:
  - `dspico.pipeline.plan.Step(name: str, title: str)` — frozen dataclass.
  - `dspico.pipeline.plan.build_plan(config: BuildConfig) -> tuple[Step, ...]`
  - `dspico.pipeline.plan.labelled(steps: tuple[Step, ...]) -> tuple[tuple[str, Step], ...]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plan.py`:

```python
"""The plan decides which steps run and what they are numbered.

compile_resources.sh hardcoded its step labels ("5/$TOTAL_STEPS") while computing
the total separately, so the printed numbering drifted out of sync with the steps
that actually ran. Deriving both from one list removes that class of bug.
"""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.pipeline.plan import Step, build_plan, labelled

BASE_STEPS = (
    "dldi",
    "bootloader",
    "encryptor",
    "firmware",
    "pico_loader",
    "pico_launcher",
    "sd_card",
)


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "inputs", tmp_path / "outputs"


def test_default_build_runs_the_seven_base_steps(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs))
    assert tuple(step.name for step in plan) == BASE_STEPS


def test_wrfuxxed_is_inserted_between_encryptor_and_firmware(
    dirs: tuple[Path, Path],
) -> None:
    # It DLDI-patches using the driver from step 1 and its output is consumed by
    # the firmware step, so the position is a real constraint, not cosmetics.
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True))
    names = [step.name for step in plan]
    assert names.index("encryptor") < names.index("wrfuxxed") < names.index("firmware")
    assert len(plan) == 8


def test_lnh_firmware_appends_ntrboot_variants_last(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=True))
    assert plan[-1].name == "ntrboot_variants"
    assert len(plan) == 8


def test_edo_firmware_omits_ntrboot_variants(dirs: tuple[Path, Path]) -> None:
    # The edo9300 fork has 4 ROM slots and embeds ntrboot in the main firmware
    # build, so a separate variants step would rebuild for nothing.
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(
            inputs_dir=inputs, outputs_dir=outputs, ntrboot=True, edo_firmware=True
        )
    )
    assert [step.name for step in plan] == list(BASE_STEPS)


def test_edo_firmware_without_ntrboot_omits_variants(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(inputs_dir=inputs, outputs_dir=outputs, edo_firmware=True)
    )
    assert "ntrboot_variants" not in [step.name for step in plan]


def test_every_flag_on_gives_nine_steps(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(
            inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True, ntrboot=True
        )
    )
    assert len(plan) == 9


def test_step_titles_are_pinned(dirs: tuple[Path, Path]) -> None:
    # Titles are user-facing output, and pinning them exactly is also what makes
    # the 100% mutation gate reachable: a test that only checked "title is
    # non-empty" would let every string-literal mutant survive.
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(
            inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True, ntrboot=True
        )
    )
    assert {step.name: step.title for step in plan} == {
        "dldi": "Build DSpico DLDI",
        "bootloader": "Build DSpico Bootloader",
        "encryptor": "Build DSRomEncryptor and encrypt the bootloader",
        "wrfuxxed": "Build WRFUxxed",
        "firmware": "Build DSpico Firmware",
        "pico_loader": "Build Pico Loader",
        "pico_launcher": "Build Pico Launcher",
        "sd_card": "Assemble the SD card structure",
        "ntrboot_variants": "Build ntrboot firmware variants",
    }


def test_step_names_are_unique(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(
            inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True, ntrboot=True
        )
    )
    names = [step.name for step in plan]
    assert len(names) == len(set(names))


def test_labels_are_derived_from_the_actual_plan_length() -> None:
    steps = (Step("a", "A"), Step("b", "B"), Step("c", "C"))
    assert labelled(steps) == (("1/3", steps[0]), ("2/3", steps[1]), ("3/3", steps[2]))


def test_labels_of_an_empty_plan_are_empty() -> None:
    assert labelled(()) == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.pipeline.plan'`

- [ ] **Step 3: Write `dspico/pipeline/plan.py`**

```python
"""Which steps run, in what order, and what they are numbered."""

from dataclasses import dataclass

from dspico.config import BuildConfig


@dataclass(frozen=True)
class Step:
    """One unit of the build. ``name`` is the stable key; ``title`` is for humans."""

    name: str
    title: str


def build_plan(config: BuildConfig) -> tuple[Step, ...]:
    """The ordered steps this configuration will actually run.

    Optional steps are absent rather than present-and-skipped, so the length of
    the returned tuple is the real step count.
    """
    steps: list[Step] = [
        Step("dldi", "Build DSpico DLDI"),
        Step("bootloader", "Build DSpico Bootloader"),
        Step("encryptor", "Build DSRomEncryptor and encrypt the bootloader"),
    ]
    if config.wrfuxxed:
        steps.append(Step("wrfuxxed", "Build WRFUxxed"))
    steps += [
        Step("firmware", "Build DSpico Firmware"),
        Step("pico_loader", "Build Pico Loader"),
        Step("pico_launcher", "Build Pico Launcher"),
        Step("sd_card", "Assemble the SD card structure"),
    ]
    if config.ntrboot_needs_separate_builds:
        steps.append(Step("ntrboot_variants", "Build ntrboot firmware variants"))
    return tuple(steps)


def labelled(steps: tuple[Step, ...]) -> tuple[tuple[str, Step], ...]:
    """Pair each step with its real ``n/total`` label.

    The shell pipeline hardcoded these numerators, so they lied whenever the set
    of enabled steps changed. Deriving them from the plan cannot drift.
    """
    total = len(steps)
    return tuple((f"{index}/{total}", step) for index, step in enumerate(steps, start=1))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plan.py -v`
Expected: 10 passed

- [ ] **Step 5: Run the static gates**

Run: `ruff check . && ruff format --check . && mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/pipeline/plan.py tests/test_plan.py
git commit -m "feat(python): derive step plan and numbering from the config"
```

---

### Task 5: ROM padding and ntrboot slot assignment

**Files:**
- Create: `dspico/pipeline/rom.py`
- Test: `tests/test_rom.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (stdlib only).
- Produces:
  - `dspico.pipeline.rom.SECURE_AREA_END: int` (`0x8000`)
  - `dspico.pipeline.rom.needs_padding(size: int) -> bool`
  - `dspico.pipeline.rom.pad_rom(data: bytes) -> bytes`
  - `dspico.pipeline.rom.NtrbootSlots(ntrboot_nds: str | None, ntrbootdsi_nds: str | None)` — frozen dataclass.
  - `dspico.pipeline.rom.ntrboot_slots(*, has_3ds: bool, has_dsi: bool) -> NtrbootSlots`
  - `dspico.pipeline.rom.ntrboot_variants(*, has_3ds: bool, has_dsi: bool) -> tuple[str, ...]`
  - Constants `SOURCE_3DS = "3ds"`, `SOURCE_DSI = "dsi"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rom.py`:

```python
"""ROM padding and ntrboot slot assignment.

The shell version padded with `truncate -s 32768`, which would have SHORTENED a
larger ROM had its size guard ever been wrong. The property test below makes that
failure mode impossible rather than merely unlikely.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dspico.pipeline.rom import (
    SECURE_AREA_END,
    SOURCE_3DS,
    SOURCE_DSI,
    NtrbootSlots,
    needs_padding,
    ntrboot_slots,
    ntrboot_variants,
    pad_rom,
)


def test_constants_are_pinned() -> None:
    # Against the literals: comparing a value to the constant it came from
    # mutates on both sides and would leave that mutant alive.
    assert SECURE_AREA_END == 0x8000 == 32768
    assert SOURCE_3DS == "3ds"
    assert SOURCE_DSI == "dsi"


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, True),
        (1, True),
        (SECURE_AREA_END - 1, True),
        (SECURE_AREA_END, False),
        (SECURE_AREA_END + 1, False),
        (1 << 20, False),
    ],
)
def test_needs_padding_boundary(size: int, expected: bool) -> None:
    # DSRomEncryptor writes test patterns at 0x3000-0x3FFF and processes the
    # secure area at 0x4000-0x8000, so 0x8000 is the exact threshold.
    assert needs_padding(size) is expected


def test_needs_padding_rejects_a_negative_size() -> None:
    with pytest.raises(ValueError, match="negative"):
        needs_padding(-1)


def test_pad_rom_extends_a_short_rom_with_zeros() -> None:
    padded = pad_rom(b"\xff" * 16)
    assert len(padded) == SECURE_AREA_END
    assert padded[:16] == b"\xff" * 16
    assert padded[16:] == bytes(SECURE_AREA_END - 16)


def test_pad_rom_leaves_a_large_rom_untouched() -> None:
    data = b"\xab" * (SECURE_AREA_END + 512)
    assert pad_rom(data) is data


def test_pad_rom_leaves_an_exact_size_rom_untouched() -> None:
    data = b"\xcd" * SECURE_AREA_END
    assert pad_rom(data) is data


@given(st.binary(max_size=SECURE_AREA_END * 2))
def test_pad_rom_never_truncates(data: bytes) -> None:
    padded = pad_rom(data)
    assert len(padded) >= SECURE_AREA_END
    assert len(padded) >= len(data)
    assert padded.startswith(data)


@pytest.mark.parametrize(
    ("has_3ds", "has_dsi", "expected"),
    [
        (True, True, NtrbootSlots(SOURCE_3DS, SOURCE_DSI)),
        (True, False, NtrbootSlots(SOURCE_3DS, None)),
        (False, True, NtrbootSlots(SOURCE_DSI, None)),
        (False, False, NtrbootSlots(None, None)),
    ],
)
def test_ntrboot_slots_covers_every_combination(
    has_3ds: bool, has_dsi: bool, expected: NtrbootSlots
) -> None:
    # With only one source available it goes in the primary slot, whichever it is.
    assert ntrboot_slots(has_3ds=has_3ds, has_dsi=has_dsi) == expected


@pytest.mark.parametrize(
    ("has_3ds", "has_dsi", "expected"),
    [
        (True, True, (SOURCE_3DS, SOURCE_DSI)),
        (True, False, (SOURCE_3DS,)),
        (False, True, (SOURCE_DSI,)),
        (False, False, ()),
    ],
)
def test_ntrboot_variants_covers_every_combination(
    has_3ds: bool, has_dsi: bool, expected: tuple[str, ...]
) -> None:
    # LNH firmware has 2 slots only, so each available source needs its own build.
    assert ntrboot_variants(has_3ds=has_3ds, has_dsi=has_dsi) == expected


def test_slots_are_frozen() -> None:
    slots = NtrbootSlots(SOURCE_3DS, SOURCE_DSI)
    with pytest.raises(AttributeError):
        slots.ntrboot_nds = SOURCE_DSI  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rom.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.pipeline.rom'`

- [ ] **Step 3: Write `dspico/pipeline/rom.py`**

```python
"""ROM-level decisions: how much padding, and which ROM goes in which slot."""

from dataclasses import dataclass

SECURE_AREA_END = 0x8000
"""DSRomEncryptor writes test patterns at 0x3000-0x3FFF and processes the secure
area at 0x4000-0x8000, so a shorter ROM must be padded before encryption."""

SOURCE_3DS = "3ds"
SOURCE_DSI = "dsi"


def needs_padding(size: int) -> bool:
    """Whether a ROM of this size is too short for DSRomEncryptor."""
    if size < 0:
        raise ValueError(f"ROM size cannot be negative: {size}")
    return size < SECURE_AREA_END


def pad_rom(data: bytes) -> bytes:
    """Zero-pad up to the secure-area end, never shortening the input.

    Returns the original object untouched when it is already long enough, so a
    caller can cheaply tell whether padding happened.
    """
    if len(data) >= SECURE_AREA_END:
        return data
    return data + bytes(SECURE_AREA_END - len(data))


@dataclass(frozen=True)
class NtrbootSlots:
    """Which ntrboot source lands in which firmware ROM slot.

    ``None`` means the slot is unused. Applies to the edo9300 fork, which has
    dedicated ``ntrboot.nds`` and ``ntrbootdsi.nds`` slots.
    """

    ntrboot_nds: str | None
    ntrbootdsi_nds: str | None


def ntrboot_slots(*, has_3ds: bool, has_dsi: bool) -> NtrbootSlots:
    """Assign available ntrboot sources to the edo9300 firmware's slots.

    With both present, 3DS takes the primary slot and DSi the secondary. With
    only one, it takes the primary slot whichever it is.
    """
    if has_3ds and has_dsi:
        return NtrbootSlots(SOURCE_3DS, SOURCE_DSI)
    if has_3ds:
        return NtrbootSlots(SOURCE_3DS, None)
    if has_dsi:
        return NtrbootSlots(SOURCE_DSI, None)
    return NtrbootSlots(None, None)


def ntrboot_variants(*, has_3ds: bool, has_dsi: bool) -> tuple[str, ...]:
    """The separate firmware builds LNH-team firmware needs for ntrboot.

    That firmware exposes only 2 ROM slots, both already taken by the bootloader
    and WRFUxxed, so every ntrboot source requires its own full build.
    """
    variants: list[str] = []
    if has_3ds:
        variants.append(SOURCE_3DS)
    if has_dsi:
        variants.append(SOURCE_DSI)
    return tuple(variants)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rom.py -v`
Expected: 21 passed (each parametrized case counts individually)

- [ ] **Step 5: Run the static gates**

Run: `ruff check . && ruff format --check . && mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/pipeline/rom.py tests/test_rom.py
git commit -m "feat(python): add ROM padding and ntrboot slot assignment"
```

---

### Task 6: Mutation-testing gate on the pure modules

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/MUTATION_TESTING.md`

**Interfaces:**
- Consumes: all four pure modules from Tasks 2-5.
- Produces: a CI job that fails when any mutant of a pure module survives. No Python API.

- [ ] **Step 1: Add the mutmut configuration**

Append to `pyproject.toml`:

```toml
[tool.mutmut]
# Only the pure decision modules are gated. steps/ and host/ (PRs 2-3) build
# command strings, which generate many equivalent mutants; a hard gate there
# would only buy tautological tests.
paths_to_mutate = [
    "dspico/config.py",
    "dspico/hostenv.py",
    "dspico/pipeline/plan.py",
    "dspico/pipeline/rom.py",
]
tests_dir = ["tests/"]
```

- [ ] **Step 2: Run mutmut and confirm every mutant dies**

Run:
```bash
mutmut run
echo "exit code: $?"
mutmut results
```
Expected: the summary reports killed mutants and **zero survived**. If any survived, the test suite has a gap — add the missing test to the relevant `tests/test_*.py`, re-run, and only continue once the count is zero. Do **not** exclude the mutant.

The most likely survivor is a **string or number literal**. A test written as `assert value == SOME_CONSTANT` mutates on both sides at once and can never fail, so the mutant lives. The fix is to pin the literal in its own test (`assert SOME_CONSTANT == "the actual value"`) — Tasks 2-5 already include one such test per module, and any new constant needs the same treatment.

- [ ] **Step 3: Record the observed exit code**

The gate depends on `mutmut run` exiting non-zero when mutants survive. Step 5 verifies that empirically rather than trusting it. Note the exit code printed in Step 2 — it must be `0` on a clean run.

- [ ] **Step 4: Add the `mutation` CI job**

Append to `.github/workflows/ci.yml` under `jobs:`:

```yaml
  mutation:
    name: mutmut (pure modules)
    runs-on: ubuntu-latest
    # Blocking, 100% kill rate. These four modules are pure decision logic; a
    # surviving mutant there is a missing test, not noise. Paths-filtered so a
    # docs-only PR does not pay for it.
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install -e ".[dev]"
      - run: mutmut run
      - name: Report surviving mutants
        if: failure()
        run: mutmut results
```

- [ ] **Step 5: Verify the gate actually fails (sabotage test)**

This proves the gate works instead of assuming mutmut's exit-code semantics.

Temporarily add an untested branch to `dspico/pipeline/rom.py`:

```python
def needs_padding(size: int) -> bool:
    if size < 0:
        raise ValueError(f"ROM size cannot be negative: {size}")
    if size == 4242:  # SABOTAGE - untested branch, remove after verifying
        return False
    return size < SECURE_AREA_END
```

Run: `mutmut run; echo "exit code: $?"`
Expected: **non-zero** exit code, and `mutmut results` lists at least one survived mutant.

If the exit code is `0` despite survivors, mutmut is not signalling through its exit status. In that case replace the `- run: mutmut run` line in the job with:

```yaml
      - name: Run mutation testing and fail on survivors
        run: |
          mutmut run || true
          if mutmut results | grep -qi survived; then
            echo "::error::Surviving mutants in pure modules"
            mutmut results
            exit 1
          fi
```

- [ ] **Step 6: Revert the sabotage and confirm green**

Remove the `if size == 4242:` branch, then run:
```bash
git diff --stat dspico/pipeline/rom.py   # must be empty
mutmut run; echo "exit code: $?"
```
Expected: no diff, exit code `0`.

- [ ] **Step 7: Document the policy**

Create `docs/MUTATION_TESTING.md`:

```markdown
# Mutation testing

## What is gated

`mutmut` runs against the four pure decision modules only:

- `dspico/config.py`
- `dspico/hostenv.py`
- `dspico/pipeline/plan.py`
- `dspico/pipeline/rom.py`

The threshold is **100% of mutants killed**, blocking in CI.

## Why only those

These modules hold every branch that decides what the build does: which steps
run, whether a ROM is padded, which ntrboot source lands in which slot, what
`--platform` and UID the container gets. They are pure, so every mutant is
reachable from a fast unit test. A surviving mutant is a missing test.

`dspico/host/` and `dspico/pipeline/steps/` are deliberately **not** gated. They
assemble command lines, where mutating a string literal often produces an
equivalent mutant no honest test can kill. Gating them would produce tests that
assert the implementation back at itself. They target 80% informally instead.

## Running it

    mutmut run       # run the mutants
    mutmut results   # list survivors

A surviving mutant is fixed by adding the missing test, never by excluding the
mutant.
```

- [ ] **Step 8: Run the full local gate**

Run:
```bash
python -m pytest -v
ruff check . && ruff format --check . && mypy
mutmut run
```
Expected: all pass, zero surviving mutants.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml docs/MUTATION_TESTING.md
git commit -m "ci: gate pure modules at a 100% mutation score"
```

---

### Task 7: Bring the docs back in sync

**Files:**
- Modify: `README.md:19-30`
- Modify: `CLAUDE.md` (the **Tests and quality** section)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

The README documents `verify_blowfish.sh`, `extract_blowfish.sh` and `find_blowfish.sh`, which were deleted in `c5b4abe` and do not exist on `main`. A reader following the Quick Start hits three "command not found" errors before reaching anything that works.

The Prerequisites section still says "Linux or WSL", which is **correct for this PR** — the portable launcher lands in PR 2. Do not change it here.

- [ ] **Step 1: Confirm the scripts really are gone**

Run: `ls verify_blowfish.sh extract_blowfish.sh find_blowfish.sh 2>&1`
Expected: "No such file or directory" for all three.

- [ ] **Step 2: Replace the Quick Verification block**

Replace `README.md` lines 19-30 — the `#### Quick Verification` heading and the fenced block that follows it — with:

````markdown
#### Quick Verification

Check your files against the SHA-1s listed in **All Input Files Summary** below:

```bash
sha1sum inputs/blowfish/*
```

If a hash does not match, use one of the options below to obtain a good dump.
````

- [ ] **Step 3: Verify no stale references remain**

Run: `grep -n "verify_blowfish\|extract_blowfish\|find_blowfish" README.md`
Expected: no output (exit code 1).

- [ ] **Step 4: Correct the CLAUDE.md testing claim**

`CLAUDE.md` opens its **Tests and quality** section with "This project has **no unit/integration test suite**", which this PR makes false. Replace that opening paragraph and add the Python commands to the bullet list.

Replace:

```markdown
This project has **no unit/integration test suite** — the deliverable is the build itself, and its
"tests" are the fail-fast guards inside the pipeline. Quality here means **script correctness, build
reproducibility and artifact smoke-checks**, not coverage.
```

with:

```markdown
The deliverable is the build itself, so the pipeline's fail-fast guards remain part of its test
story — but the decision logic now lives in `dspico/`, which has a real suite.

- **`python -m pytest`** — unit tests for the pure modules. Runs on Linux, macOS and Windows,
  Python 3.11-3.13, and needs no Docker, network or toolchain.
- **`mypy --strict` and `ruff`** — blocking in CI. For typed Python these play the role ShellCheck
  plays for the shell scripts.
- **`mutmut run`** — mutation testing, gated at 100% killed on `config.py`, `hostenv.py`,
  `pipeline/plan.py` and `pipeline/rom.py`. See `docs/MUTATION_TESTING.md` for why only those.

The shell pipeline is still the only executable build path and is still covered by ShellCheck; it
has no unit tests by design, and is deleted rather than tested once the Python engine is validated.
```

- [ ] **Step 5: Verify the claim is gone**

Run: `grep -n "no unit/integration test suite" CLAUDE.md`
Expected: no output (exit code 1).

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: drop deleted blowfish scripts and record the Python test suite"
```

---

## Deviations, as executed

Recorded after running the plan. Each is a correction the plan was wrong about, not a shortcut.

1. **Python 3.14 added to the CI matrix.** Local development runs 3.14.6, so the planned
   3.11-3.13 matrix would not have covered the machine the code is written on.
2. **`ruff` excludes `docs/`.** Current ruff formats Python code blocks *inside markdown*, so
   `ruff format --check .` tried to rewrite the illustrative snippets in this very plan.
3. **mutmut config keys were wrong.** mutmut 3.7.0 deprecates `paths_to_mutate` and `tests_dir` in
   favour of `source_paths` and `only_mutate`. The shipped config uses `source_paths = ["dspico"]`
   plus an `only_mutate` allowlist, which also stays correct when PRs 2-3 add impure modules.
4. **The gate does not use mutmut's exit code.** The sabotage step (Task 6, Step 5) earned its
   keep: with two survivors present, `mutmut run` still exited `0`. The job greps `mutmut results`
   instead — the contingency the plan wrote down.
5. **No paths filter on the `mutation` job.** 130 mutants run in about two seconds, and job-level
   path filtering in GitHub Actions needs a third-party action — new supply-chain surface for no
   gain.
6. **`pad_rom` was refactored to call `needs_padding`.** Reaching 100% surfaced one genuinely
   equivalent mutant (`>=` to `>`): at exactly `SECURE_AREA_END` the mutated branch falls through
   to `data + bytes(0)`, and CPython returns the original object for concatenation with empty
   bytes, so even an identity assertion passes. Deleting the duplicated threshold removed the
   mutant and left the boundary defined in one place.

## Definition of done

- [ ] `python -m pytest` passes on ubuntu, macos and windows for Python 3.11, 3.12 and 3.13.
- [ ] `ruff check .`, `ruff format --check .` and `mypy` all exit 0.
- [ ] `mutmut run` reports zero surviving mutants across the four pure modules.
- [ ] The mutation gate has been empirically proven to fail on a sabotaged branch (Task 6, Step 5).
- [ ] `git diff main -- build_resources.sh compile_resources.sh Dockerfile` is **empty** — this PR changes no build behavior.
- [ ] `shellcheck --severity=warning build_resources.sh compile_resources.sh` still passes.
- [ ] The PR body carries a **How to test manually** section per `CLAUDE.md`. For this PR that is: clone, `pip install -e ".[dev]"`, run the four commands above, and confirm `./build_resources.sh` is unchanged and still the documented way to build.
