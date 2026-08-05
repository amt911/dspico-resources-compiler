# PR 3: Python Pipeline Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port all nine build steps to Python behind `--engine=python`, with `--engine=bash` remaining the default, so the two engines can be run side by side and compared before the shell is deleted.

**Architecture:** The pipeline runs *inside* the container, where the toolchain lives. The host launcher bind-mounts the repository and invokes `python3 -m dspico.pipeline.run` instead of `bash compile_resources.sh`. Inside, a `BuildContext` carries the config, a `Runner` and the resolved paths; each step is a function taking that context and returning what it produced, replacing the shell version's shared globals.

**Tech Stack:** Python 3.11 stdlib only (the container ships 3.11.2 — verified), pytest, mypy `--strict`, ruff, mutmut.

## Global Constraints

PR 1 and PR 2's Global Constraints all still apply. In addition:

- **The in-container code must run on Python 3.11.2 with no installed package.** It is imported via `PYTHONPATH=/dspico`, not `pip install`. No dependency may be added, and no 3.12+ syntax may be used.
- **`--engine=bash` stays the default** and must keep working identically. `compile_resources.sh` is not modified in this PR.
- **No test may invoke docker, git, make, dotnet or the network.** Every step is tested through `FakeRunner` plus `tmp_path`.
- **Build with `make`, not `male`.** Verified: no `male` binary exists in the image (see `docs/FINDINGS.md`). The fallback is kept for fidelity but `make` is the real path.
- **Never write to `/inputs`.** It is mounted read-only; copy into a temp directory instead.
- **Preserve every guard.** Each `error_exit` / `find_artifact` / `[ -f … ]` in the shell becomes a raised `BuildError`. A step that silently continues where the shell aborted is a regression.

## Verified facts this plan relies on

Checked against the real `dspico-compiler:latest` image, not assumed:

- `python3` is **3.11.2**; `PYTHONPATH=/repo python3 -c "import dspico"` works with the repo bind-mounted read-only.
- `dlditool` is at `/opt/wonderful/thirdparty/blocksds/core/tools/dlditool/dlditool`.
- `make` is at `/usr/bin/make`; **`male` does not exist anywhere on the filesystem.**
- `PATH` already contains `/opt/wonderful/bin`; `/etc/profile.d/wonderful.sh` sources `wf-env`, so the toolchain needs a **login shell** (`bash -lc`) to be fully set up.

That last point drives a design decision: the in-container command must still go through `bash -lc`, because `wf-env` is what puts the BlocksDS toolchain into the environment. The launcher therefore runs `bash -lc 'PYTHONPATH=/dspico python3 -m dspico.pipeline.run …'`.

---

### Task 1: Build context and toolchain helpers

**Files:**
- Create: `dspico/pipeline/context.py`
- Create: `dspico/pipeline/toolchain.py`
- Test: `tests/test_context.py`, `tests/test_toolchain.py`

**Interfaces:**
- Produces:
  - `dspico.pipeline.context.BuildContext(config: BuildConfig, runner: Runner, inputs: Path, out_base: Path, work: Path)` — frozen dataclass, with `component_dir(name: str) -> Path`.
  - `dspico.pipeline.toolchain.clone(ctx, url: str, dest: Path, *, recursive: bool = False, commit: str | None = None) -> None`
  - `dspico.pipeline.toolchain.init_submodules(ctx, repo: Path, *, subdir: Path | None = None) -> None`
  - `dspico.pipeline.toolchain.make(ctx, repo: Path, *, jobs: int) -> None`
  - `dspico.pipeline.toolchain.dldi_patch(ctx, dldi: Path, target: Path) -> None`
  - `dspico.pipeline.toolchain.DLDITOOL_DEFAULT: str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context.py`:

```python
"""BuildContext replaces the shell pipeline's shared globals."""

from pathlib import Path

from dspico.config import BuildConfig
from dspico.pipeline.context import BuildContext
from tests.conftest import FakeRunner


def _ctx(tmp_path: Path) -> BuildContext:
    return BuildContext(
        config=BuildConfig(inputs_dir=tmp_path / "in", outputs_dir=tmp_path / "out"),
        runner=FakeRunner(),
        inputs=tmp_path / "in",
        out_base=tmp_path / "out" / "dspico",
        work=tmp_path / "work",
    )


def test_component_dir_is_under_out_base(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert ctx.component_dir("dldi") == tmp_path / "out" / "dspico" / "dldi"


def test_component_dir_is_created_on_demand(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    created = ctx.component_dir("bootloader")
    assert created.is_dir()


def test_context_is_frozen(tmp_path: Path) -> None:
    import pytest

    ctx = _ctx(tmp_path)
    with pytest.raises(AttributeError):
        ctx.work = tmp_path  # type: ignore[misc]
```

Create `tests/test_toolchain.py`:

```python
"""Toolchain helpers, asserted as exact commands."""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
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
    from dspico.errors import BuildError

    with pytest.raises(BuildError, match="dlditool"):
        dldi_patch(ctx, tmp_path / "d.dldi", tmp_path / "t.nds", dlditool=tmp_path / "nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_context.py tests/test_toolchain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dspico.pipeline.context'`

- [ ] **Step 3: Write `dspico/pipeline/context.py`**

```python
"""What every build step is handed.

Replaces the shell pipeline's shared globals (DLDI_FILE, BOOTLOADER_NDS,
ENCRYPTED_NDS, ENCRYPTOR_BIN) with an explicit argument, so a step's inputs are
visible in its signature rather than implied by call order.
"""

from dataclasses import dataclass
from pathlib import Path

from dspico.config import BuildConfig
from dspico.runtime import Runner


@dataclass(frozen=True)
class BuildContext:
    """Config, the command runner, and the resolved locations for one build."""

    config: BuildConfig
    runner: Runner
    inputs: Path
    out_base: Path
    work: Path

    def component_dir(self, name: str) -> Path:
        """The output directory for a component, created if needed."""
        path = self.out_base / name
        path.mkdir(parents=True, exist_ok=True)
        return path
```

- [ ] **Step 4: Write `dspico/pipeline/toolchain.py`**

```python
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
    ``male`` binary exists in the image, so only this path has ever run.
    """
    ctx.runner.run(["make", "-C", str(repo), f"-j{jobs}"], step="build")


def dldi_patch(
    ctx: BuildContext, dldi: Path, target: Path, *, dlditool: Path | None = None
) -> None:
    """Patch a binary with the DSpico DLDI driver."""
    tool = Path(DLDITOOL_DEFAULT) if dlditool is None else dlditool
    if not tool.is_file():
        raise BuildError(f"dlditool not found at: {tool}", step="dldi-patch")
    ctx.runner.run([str(tool), str(dldi), str(target)], step="dldi-patch")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_context.py tests/test_toolchain.py -v`
Expected: 11 passed

- [ ] **Step 6: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 7: Commit**

```bash
git add dspico/pipeline/context.py dspico/pipeline/toolchain.py tests/test_context.py tests/test_toolchain.py
git commit -m "feat(pipeline): add the build context and toolchain wrappers"
```

---

### Task 2: Artifact discovery and provenance

**Files:**
- Create: `dspico/pipeline/artifacts.py`
- Test: `tests/test_artifacts.py`

**Interfaces:**
- Produces:
  - `find_artifact(root: Path, pattern: str, *, depth: int = 2) -> Path`
  - `find_artifacts(root: Path, pattern: str, *, depth: int = 2) -> list[Path]`
  - `copy_into(source: Path, dest_dir: Path) -> Path`
  - `copy_glob(root: Path, pattern: str, dest_dir: Path, *, required: bool = True) -> list[Path]`
  - `write_build_info(ctx: BuildContext, repo: Path, dest_dir: Path, component: str) -> Path`

`find_artifact` raises when a pattern matches nothing **and when it matches more than one file**. The shell version took `head -n 1`, silently picking an arbitrary match.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_artifacts.py`:

```python
"""Artifact discovery. These functions are the pipeline's assertions."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.artifacts import (
    copy_glob,
    copy_into,
    find_artifact,
    find_artifacts,
)


def _touch(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_finds_a_single_match(tmp_path: Path) -> None:
    wanted = _touch(tmp_path / "build" / "DSpico.dldi")
    assert find_artifact(tmp_path, "*.dldi") == wanted


def test_missing_artifact_raises(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="no file matching"):
        find_artifact(tmp_path, "*.dldi")


def test_ambiguous_artifact_raises(tmp_path: Path) -> None:
    # The shell used `find ... | head -n 1`, which picked one arbitrarily and
    # could ship the wrong binary without a word.
    _touch(tmp_path / "a" / "one.uf2")
    _touch(tmp_path / "b" / "two.uf2")
    with pytest.raises(BuildError, match="ambiguous"):
        find_artifact(tmp_path, "*.uf2")


def test_depth_is_respected(tmp_path: Path) -> None:
    _touch(tmp_path / "a" / "b" / "c" / "deep.bin")
    with pytest.raises(BuildError, match="no file matching"):
        find_artifact(tmp_path, "deep.bin", depth=2)
    assert find_artifact(tmp_path, "deep.bin", depth=4).name == "deep.bin"


def test_find_artifacts_returns_every_match_sorted(tmp_path: Path) -> None:
    _touch(tmp_path / "b.uf2")
    _touch(tmp_path / "a.uf2")
    assert [p.name for p in find_artifacts(tmp_path, "*.uf2")] == ["a.uf2", "b.uf2"]


def test_find_artifacts_may_return_nothing(tmp_path: Path) -> None:
    assert find_artifacts(tmp_path, "*.none") == []


def test_copy_into_returns_the_destination(tmp_path: Path) -> None:
    source = _touch(tmp_path / "src" / "f.bin", "payload")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    copied = copy_into(source, dest_dir)
    assert copied == dest_dir / "f.bin"
    assert copied.read_text(encoding="utf-8") == "payload"


def test_copy_glob_copies_every_match(tmp_path: Path) -> None:
    _touch(tmp_path / "picoLoader7.bin")
    _touch(tmp_path / "picoLoader9e.bin")
    dest = tmp_path / "out"
    dest.mkdir()
    copied = copy_glob(tmp_path, "picoLoader*.bin", dest)
    assert sorted(p.name for p in copied) == ["picoLoader7.bin", "picoLoader9e.bin"]


def test_required_copy_glob_raises_when_nothing_matches(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(BuildError, match="no file matching"):
        copy_glob(tmp_path, "*.missing", dest)


def test_optional_copy_glob_tolerates_no_match(tmp_path: Path) -> None:
    # Only for genuinely optional artifacts, mirroring copy_if_exists.
    dest = tmp_path / "out"
    dest.mkdir()
    assert copy_glob(tmp_path, "*.missing", dest, required=False) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_artifacts.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `dspico/pipeline/artifacts.py`**

```python
"""Finding, copying and recording build artifacts.

These functions are where the pipeline asserts. A missing or ambiguous artifact
must stop the build rather than be papered over.
"""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.context import BuildContext


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
    fields = {"Commit": "%H", "Date": "%ai", "Summary": "%s"}
    lines = [f"Component: {component}"]
    for label, fmt in fields.items():
        lines.append(f"{label}: {_git_show(ctx, repo, fmt)}")
    destination = dest_dir / "BUILD_INFO.txt"
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def _git_show(ctx: BuildContext, repo: Path, fmt: str) -> str:
    from dspico.runtime import capture

    return capture(["git", "-C", str(repo), "log", "-1", f"--format={fmt}"])
```

`write_build_info` needs command *output*, which the `Runner` protocol does not provide. Add a
module-level `capture` helper to `dspico/runtime.py`:

```python
def capture(argv: Sequence[str]) -> str:
    """Run a command and return its stdout, stripped.

    Separate from Runner because it is only used for provenance metadata, never
    to drive the build, and its output is the point.
    """
    completed = subprocess.run(list(argv), check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise CommandError(argv, completed.returncode)
    return completed.stdout.strip()
```

`write_build_info` is therefore covered by the step tests that assert the file's shape, not by a unit
test that would need a real git repository.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_artifacts.py -v`
Expected: 10 passed

- [ ] **Step 5: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/pipeline/artifacts.py dspico/runtime.py tests/test_artifacts.py
git commit -m "feat(pipeline): add artifact discovery that refuses ambiguous matches"
```

---

### Task 3: The component-shaped steps

**Files:**
- Create: `dspico/pipeline/components.py`
- Create: `dspico/pipeline/steps/__init__.py`
- Create: `dspico/pipeline/steps/simple.py`
- Test: `tests/test_steps_simple.py`

Five of the nine steps share one shape — clone, build, find an artifact, copy it, record provenance — which the shell repeated five times. Expressing them as data removes that repetition.

**Interfaces:**
- Produces:
  - `dspico.pipeline.components.Component(name, url, artifact, recursive=False, submodules=False)` — frozen dataclass.
  - `dspico.pipeline.components.COMPONENTS: dict[str, Component]` with keys `dldi`, `bootloader`, `wrfuxxed`, `pico_loader`, `pico_launcher`.
  - `dspico.pipeline.steps.simple.build_component(ctx, component, *, jobs, commit=None) -> Path` returning the copied primary artifact.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_steps_simple.py`:

```python
"""The clone-build-copy shape shared by five steps."""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.pipeline.components import COMPONENTS, Component
from dspico.pipeline.context import BuildContext
from dspico.pipeline.steps.simple import build_component
from tests.conftest import FakeRunner


class BuildingRunner(FakeRunner):
    """A FakeRunner that also creates the artifact a real build would produce."""

    def __init__(self, artifact: Path) -> None:
        super().__init__()
        self._artifact = artifact

    def run(self, argv, *, step=None):  # type: ignore[no-untyped-def]
        super().run(argv, step=step)
        if argv[0] == "make":
            self._artifact.parent.mkdir(parents=True, exist_ok=True)
            self._artifact.write_bytes(b"artifact")


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return tmp_path / "in", tmp_path / "out" / "dspico", tmp_path / "work"


def test_every_component_url_is_pinned() -> None:
    # Each URL is a supply-chain surface; pinning them in a test means a typo or
    # a redirected fork cannot land unnoticed.
    assert COMPONENTS["dldi"].url == "https://github.com/LNH-team/dspico-dldi.git"
    assert COMPONENTS["bootloader"].url == "https://github.com/LNH-team/dspico-bootloader.git"
    assert COMPONENTS["wrfuxxed"].url == "https://github.com/LNH-team/dspico-wrfuxxed"
    assert COMPONENTS["pico_loader"].url == "https://github.com/LNH-team/pico-loader"
    assert COMPONENTS["pico_launcher"].url == "https://github.com/LNH-team/pico-launcher"


def test_component_artifact_patterns_are_pinned() -> None:
    assert COMPONENTS["dldi"].artifact == "*.dldi"
    assert COMPONENTS["bootloader"].artifact == "BOOTLOADER.nds"
    assert COMPONENTS["wrfuxxed"].artifact == "uartBufv060.bin"
    assert COMPONENTS["pico_launcher"].artifact == "LAUNCHER.nds"


def test_pico_loader_clones_recursively() -> None:
    assert COMPONENTS["pico_loader"].recursive is True


def test_bootloader_and_launcher_need_submodules() -> None:
    assert COMPONENTS["bootloader"].submodules is True
    assert COMPONENTS["pico_launcher"].submodules is True


def test_build_component_clones_builds_and_copies(
    tmp_path: Path, paths: tuple[Path, Path, Path]
) -> None:
    inputs, out_base, work = paths
    component = Component(name="dldi", url="https://example.invalid/d.git", artifact="*.dldi")
    runner = BuildingRunner(work / "dldi" / "DSpico.dldi")
    ctx = BuildContext(
        config=BuildConfig(inputs_dir=inputs, outputs_dir=tmp_path / "out"),
        runner=runner,
        inputs=inputs,
        out_base=out_base,
        work=work,
    )

    produced = build_component(ctx, component, jobs=2, write_info=False)

    assert produced == out_base / "dldi" / "DSpico.dldi"
    assert produced.read_bytes() == b"artifact"
    assert [c[0] for c in runner.calls] == ["git", "make"]


def test_build_component_initialises_submodules_when_asked(
    tmp_path: Path, paths: tuple[Path, Path, Path]
) -> None:
    inputs, out_base, work = paths
    component = Component(
        name="bootloader",
        url="https://example.invalid/b.git",
        artifact="BOOTLOADER.nds",
        submodules=True,
    )
    runner = BuildingRunner(work / "bootloader" / "BOOTLOADER.nds")
    ctx = BuildContext(
        config=BuildConfig(inputs_dir=inputs, outputs_dir=tmp_path / "out"),
        runner=runner,
        inputs=inputs,
        out_base=out_base,
        work=work,
    )

    build_component(ctx, component, jobs=1, write_info=False)

    assert [c[0] for c in runner.calls] == ["git", "git", "make"]
    assert runner.calls[1][3] == "submodule"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_steps_simple.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `dspico/pipeline/components.py`**

```python
"""The upstream components this repository orchestrates.

Every URL here is a supply-chain surface. Adding one is a deliberate decision,
not a refactor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Component:
    """An upstream repository and the artifact its build is expected to produce."""

    name: str
    url: str
    artifact: str
    recursive: bool = False
    submodules: bool = False


COMPONENTS: dict[str, Component] = {
    "dldi": Component(
        name="dldi",
        url="https://github.com/LNH-team/dspico-dldi.git",
        artifact="*.dldi",
    ),
    "bootloader": Component(
        name="bootloader",
        url="https://github.com/LNH-team/dspico-bootloader.git",
        artifact="BOOTLOADER.nds",
        submodules=True,
    ),
    "wrfuxxed": Component(
        name="wrfuxxed",
        url="https://github.com/LNH-team/dspico-wrfuxxed",
        artifact="uartBufv060.bin",
    ),
    "pico_loader": Component(
        name="pico_loader",
        url="https://github.com/LNH-team/pico-loader",
        artifact="picoLoader7.bin",
        recursive=True,
    ),
    "pico_launcher": Component(
        name="pico_launcher",
        url="https://github.com/LNH-team/pico-launcher",
        artifact="LAUNCHER.nds",
        submodules=True,
    ),
}
```

Create `dspico/pipeline/steps/__init__.py`:

```python
"""The individual build steps."""
```

Create `dspico/pipeline/steps/simple.py`:

```python
"""The clone-build-copy shape shared by five of the nine steps."""

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_steps_simple.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 6: Commit**

```bash
git add dspico/pipeline/components.py dspico/pipeline/steps tests/test_steps_simple.py
git commit -m "feat(pipeline): express the clone-build-copy steps as data"
```

---

### Task 4: Encryption, firmware, SD assembly and ntrboot

**Files:**
- Create: `dspico/pipeline/steps/encryptor.py`
- Create: `dspico/pipeline/steps/firmware.py`
- Create: `dspico/pipeline/steps/sd_card.py`
- Test: `tests/test_steps_encryptor.py`, `tests/test_steps_firmware.py`, `tests/test_steps_sd_card.py`

These four steps have genuinely distinct shapes and keep their own modules.

**Interfaces:**
- `encryptor.build_encryptor(ctx) -> Path` — returns the encryptor binary path.
- `encryptor.encrypt(ctx, encryptor_bin: Path, source: Path, destination: Path) -> Path`
- `encryptor.stage_blowfish(ctx, bin_dir: Path) -> None` — copies from `/inputs`, validates NTR presence.
- `firmware.build_firmware(ctx, *, encrypted: Path, wrfuxxed: Path | None, jobs: int) -> list[Path]`
- `firmware.enable_wrfuxxed_flag(cmakelists: Path) -> None` — **raises** if the substitution did not apply.
- `sd_card.assemble(ctx) -> Path`

The single most important behaviour change: `enable_wrfuxxed_flag` asserts. The shell used
`sed … || true`, so an upstream rename silently dropped the exploit from the build.

- [ ] **Step 1: Write the failing tests for the WRFUxxed flag**

Create `tests/test_steps_firmware.py`:

```python
"""Firmware assembly, and the CMake flag the shell silently failed to set."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.steps.firmware import enable_wrfuxxed_flag

COMMENTED = """\
set(SOURCES main.c)
  #DSPICO_ENABLE_WRFUXXED
target_link_libraries(x)
"""

UNCOMMENTED = """\
set(SOURCES main.c)
  DSPICO_ENABLE_WRFUXXED
target_link_libraries(x)
"""

RENAMED_UPSTREAM = """\
set(SOURCES main.c)
  #DSPICO_ENABLE_WRFU_EXPLOIT
target_link_libraries(x)
"""


def test_uncomments_the_flag(tmp_path: Path) -> None:
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(COMMENTED, encoding="utf-8")
    enable_wrfuxxed_flag(cmakelists)
    assert cmakelists.read_text(encoding="utf-8") == UNCOMMENTED


def test_tolerates_spacing_after_the_hash(tmp_path: Path) -> None:
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text("  #  DSPICO_ENABLE_WRFUXXED\n", encoding="utf-8")
    enable_wrfuxxed_flag(cmakelists)
    assert cmakelists.read_text(encoding="utf-8") == "  DSPICO_ENABLE_WRFUXXED\n"


def test_already_enabled_is_accepted(tmp_path: Path) -> None:
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(UNCOMMENTED, encoding="utf-8")
    enable_wrfuxxed_flag(cmakelists)
    assert cmakelists.read_text(encoding="utf-8") == UNCOMMENTED


def test_upstream_rename_fails_loudly(tmp_path: Path) -> None:
    # The shell ran `sed ... || true`, so this case shipped a firmware with the
    # exploit quietly missing. This is the whole reason the function exists.
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(RENAMED_UPSTREAM, encoding="utf-8")
    with pytest.raises(BuildError, match="DSPICO_ENABLE_WRFUXXED"):
        enable_wrfuxxed_flag(cmakelists)


def test_missing_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="CMakeLists.txt"):
        enable_wrfuxxed_flag(tmp_path / "absent" / "CMakeLists.txt")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_steps_firmware.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the flag function into `dspico/pipeline/steps/firmware.py`**

```python
"""The Pico firmware build, including ROM slot injection."""

import re
from pathlib import Path

from dspico.errors import BuildError

WRFUXXED_FLAG = "DSPICO_ENABLE_WRFUXXED"
_COMMENTED = re.compile(rf"^(\s*)#\s*({re.escape(WRFUXXED_FLAG)})", re.MULTILINE)
_ENABLED = re.compile(rf"^\s*{re.escape(WRFUXXED_FLAG)}\b", re.MULTILINE)


def enable_wrfuxxed_flag(cmakelists: Path) -> None:
    """Uncomment the WRFUxxed flag in the upstream CMakeLists.

    Raises if the flag is nowhere to be found. The shell version ended this
    substitution in ``|| true``, so an upstream rename produced a firmware with
    the exploit silently missing — a build that looked entirely successful.
    """
    if not cmakelists.is_file():
        raise BuildError(f"CMakeLists.txt not found at: {cmakelists}", step="firmware")

    text = cmakelists.read_text(encoding="utf-8")
    patched, count = _COMMENTED.subn(r"\1\2", text)
    if count:
        cmakelists.write_text(patched, encoding="utf-8")
        return
    if _ENABLED.search(text):
        return
    raise BuildError(
        f"{WRFUXXED_FLAG} not found in {cmakelists}; upstream may have renamed it",
        step="firmware",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_steps_firmware.py -v`
Expected: 5 passed

- [ ] **Step 5: Add the Blowfish staging tests**

Create `tests/test_steps_encryptor.py`:

```python
"""Blowfish staging and ROM encryption."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.steps.encryptor import stage_blowfish


def test_copies_every_input_file(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "ntrBlowfish.bin").write_bytes(b"\x00" * 16)
    (inputs / "twlBlowfish.bin").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    stage_blowfish(inputs, bin_dir)

    assert (bin_dir / "ntrBlowfish.bin").exists()
    assert (bin_dir / "twlBlowfish.bin").exists()


def test_bios_dumps_satisfy_the_requirement(tmp_path: Path) -> None:
    # Either the extracted table or the BIOS dump it comes from is accepted.
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "biosnds7.rom").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    stage_blowfish(inputs, bin_dir)

    assert (bin_dir / "biosnds7.rom").exists()


def test_missing_ntr_blowfish_fails_loudly(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "twlBlowfish.bin").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    with pytest.raises(BuildError, match="NTR Blowfish"):
        stage_blowfish(inputs, bin_dir)


def test_missing_blowfish_directory_fails_loudly(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    with pytest.raises(BuildError, match="NTR Blowfish"):
        stage_blowfish(tmp_path / "absent", bin_dir)


def test_inputs_are_never_written_to(tmp_path: Path) -> None:
    # /inputs is mounted read-only; a step that wrote there would fail only on a
    # real run, long after the tests passed.
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "ntrBlowfish.bin").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    before = sorted(p.name for p in inputs.iterdir())
    stage_blowfish(inputs, bin_dir)
    assert sorted(p.name for p in inputs.iterdir()) == before
```

- [ ] **Step 6: Write `dspico/pipeline/steps/encryptor.py`**

```python
"""Building DSRomEncryptor and encrypting the bootloader."""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.rom import needs_padding, pad_rom

NTR_SOURCES = ("ntrBlowfish.bin", "biosnds7.rom")
TWL_SOURCES = ("twlBlowfish.bin", "biosdsi7.rom")


def stage_blowfish(blowfish_dir: Path, bin_dir: Path) -> None:
    """Copy the Blowfish tables next to the encryptor and check NTR is present.

    Copies rather than reads in place because ``/inputs`` is mounted read-only
    and DSRomEncryptor expects the tables in its own working directory.
    """
    if blowfish_dir.is_dir():
        for source in sorted(blowfish_dir.iterdir()):
            if source.is_file():
                shutil.copy2(source, bin_dir / source.name)

    if not any((bin_dir / name).is_file() for name in NTR_SOURCES):
        raise BuildError(
            "NTR Blowfish not found (need one of "
            f"{' or '.join(NTR_SOURCES)} in inputs/blowfish/)",
            step="encryptor",
        )


def prepare_rom(source: Path, work_dir: Path) -> Path:
    """Return a ROM at least 0x8000 bytes long, padding a copy if needed.

    DSRomEncryptor writes test patterns at 0x3000-0x3FFF and processes the
    secure area at 0x4000-0x8000, so a shorter ROM cannot be encrypted.
    """
    data = source.read_bytes()
    if not needs_padding(len(data)):
        return source
    work_dir.mkdir(parents=True, exist_ok=True)
    padded = work_dir / f"{source.stem}_padded.nds"
    padded.write_bytes(pad_rom(data))
    return padded
```

- [ ] **Step 7: Write the SD assembly tests and module**

Create `tests/test_steps_sd_card.py`:

```python
"""SD card assembly — the actual deliverable."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.steps.sd_card import assemble


def _populate(out_base: Path) -> None:
    launcher = out_base / "pico_launcher"
    (launcher / "_pico").mkdir(parents=True)
    (launcher / "_pico" / "theme.bin").write_bytes(b"theme")
    (launcher / "LAUNCHER.nds").write_bytes(b"launcher")

    loader = out_base / "pico_loader"
    loader.mkdir(parents=True)
    (loader / "picoLoader7.bin").write_bytes(b"l7")
    (loader / "picoLoader9e.bin").write_bytes(b"l9")
    (loader / "aplist.bin").write_bytes(b"ap")


def test_launcher_becomes_the_boot_file(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    _populate(out_base)
    sd = assemble(out_base)
    assert (sd / "_picoboot.nds").read_bytes() == b"launcher"


def test_themes_and_loader_land_in_pico(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    _populate(out_base)
    sd = assemble(out_base)
    assert (sd / "_pico" / "theme.bin").read_bytes() == b"theme"
    assert (sd / "_pico" / "picoLoader7.bin").read_bytes() == b"l7"
    assert (sd / "_pico" / "aplist.bin").read_bytes() == b"ap"


def test_the_arm9_loader_is_renamed_to_a_fixed_name(tmp_path: Path) -> None:
    # Upstream emits picoLoader9<variant>.bin but the launcher looks for exactly
    # picoLoader9.bin, so the rename is load-bearing.
    out_base = tmp_path / "dspico"
    _populate(out_base)
    sd = assemble(out_base)
    assert (sd / "_pico" / "picoLoader9.bin").read_bytes() == b"l9"


def test_assembly_starts_from_scratch(tmp_path: Path) -> None:
    # sd_card/ is the deliverable; a leftover file from a previous flag
    # combination must not survive into it.
    out_base = tmp_path / "dspico"
    _populate(out_base)
    stale = out_base / "sd_card" / "_pico" / "stale.bin"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")

    sd = assemble(out_base)

    assert not (sd / "_pico" / "stale.bin").exists()


def test_missing_launcher_fails_loudly(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    (out_base / "pico_loader").mkdir(parents=True)
    with pytest.raises(BuildError, match="LAUNCHER.nds"):
        assemble(out_base)
```

Create `dspico/pipeline/steps/sd_card.py`:

```python
"""Assembling the ready-to-copy SD card layout.

This is the deliverable: everything else exists to produce this directory.
"""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.artifacts import copy_glob, find_artifact

BOOT_FILE = "_picoboot.nds"
ARM9_LOADER = "picoLoader9.bin"


def assemble(out_base: Path) -> Path:
    """Build ``sd_card/`` from the component outputs, from scratch.

    Rebuilt rather than updated so a stale artifact from a previous flag
    combination cannot survive into the deliverable.
    """
    sd = out_base / "sd_card"
    if sd.exists():
        shutil.rmtree(sd)
    pico = sd / "_pico"
    pico.mkdir(parents=True)

    themes = out_base / "pico_launcher" / "_pico"
    if themes.is_dir():
        shutil.copytree(themes, pico, dirs_exist_ok=True)

    loader = out_base / "pico_loader"
    if loader.is_dir():
        copy_glob(loader, "picoLoader7*.bin", pico, depth=0, required=False)
        for optional in ("aplist.bin", "savelist.bin", "patchlist.bin"):
            copy_glob(loader, optional, pico, depth=0, required=False)
        # Upstream emits picoLoader9<variant>.bin; the launcher opens exactly
        # picoLoader9.bin, so this rename is load-bearing.
        arm9 = find_artifact(loader, "picoLoader9*.bin", depth=0)
        shutil.copy2(arm9, pico / ARM9_LOADER)

    launcher = out_base / "pico_launcher" / "LAUNCHER.nds"
    if not launcher.is_file():
        raise BuildError(f"LAUNCHER.nds not found at {launcher}", step="sd_card")
    shutil.copy2(launcher, sd / BOOT_FILE)
    return sd
```

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_steps_encryptor.py tests/test_steps_sd_card.py tests/test_steps_firmware.py -v`
Expected: 15 passed

- [ ] **Step 9: Run the static gates**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy`
Expected: all exit 0

- [ ] **Step 10: Commit**

```bash
git add dspico/pipeline/steps tests/test_steps_encryptor.py tests/test_steps_firmware.py tests/test_steps_sd_card.py
git commit -m "feat(pipeline): add encryption, firmware flag and SD assembly steps"
```

---

### Task 5: The in-container entry point and the `--engine` flag

**Files:**
- Create: `dspico/pipeline/run.py`
- Modify: `dspico/host/launcher.py`
- Modify: `dspico/cli.py`
- Test: `tests/test_pipeline_run.py`, `tests/test_launcher.py`, `tests/test_cli.py`

**Interfaces:**
- `dspico.pipeline.run.build_run_parser() -> argparse.ArgumentParser`
- `dspico.pipeline.run.main(argv: Sequence[str] | None = None) -> int`
- `dspico.host.launcher.run_container_argv(..., engine_kind: str = "bash")` — `"bash"` keeps the current command; `"python"` runs the package.
- `dspico.host.launcher.PYTHON_ENTRY: str` = `"dspico.pipeline.run"`

The in-container command must still go through `bash -lc`, because `/etc/profile.d/wonderful.sh`
sources `wf-env` and that is what puts the BlocksDS toolchain in the environment. Only the payload
changes.

- [ ] **Step 1: Write the failing launcher tests**

Append to `tests/test_launcher.py`:

```python
def test_python_engine_runs_the_package_through_a_login_shell(
    config: BuildConfig, tmp_path: Path
) -> None:
    # Still bash -lc: /etc/profile.d/wonderful.sh sources wf-env, which is what
    # puts the BlocksDS toolchain on PATH. Only the payload changes.
    argv = run_container_argv(
        config, X86_LINUX, script_path=tmp_path / "s.sh", engine_kind="python"
    )
    assert argv[-3:-1] == ["bash", "-lc"]
    payload = argv[-1]
    assert "python3 -m dspico.pipeline.run" in payload
    assert "PYTHONPATH=" in payload


def test_python_engine_mounts_the_repository(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(
        config, X86_LINUX, script_path=tmp_path / "s.sh", engine_kind="python"
    )
    assert any(a.endswith(":/dspico:ro") for a in argv)


def test_python_engine_passes_flags_not_env_vars(tmp_path: Path) -> None:
    config = BuildConfig(
        inputs_dir=tmp_path / "inputs",
        outputs_dir=tmp_path / "outputs",
        wrfuxxed=True,
        ntrboot=True,
    )
    argv = run_container_argv(
        config, X86_LINUX, script_path=tmp_path / "s.sh", engine_kind="python"
    )
    payload = argv[-1]
    assert "--wrfuxxed" in payload
    assert "--ntrboot" in payload
    assert "--edo-firmware" not in payload


def test_bash_engine_is_unchanged(config: BuildConfig, tmp_path: Path) -> None:
    # The default path must stay byte-identical while both engines exist.
    default = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    explicit = run_container_argv(
        config, X86_LINUX, script_path=tmp_path / "s.sh", engine_kind="bash"
    )
    assert default == explicit
    assert default[-1] == "/dspico/compile_resources.sh"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_launcher.py -v`
Expected: FAIL with `TypeError: run_container_argv() got an unexpected keyword argument 'engine_kind'`

- [ ] **Step 3: Extend `dspico/host/launcher.py`**

Add near the other constants:

```python
CONTAINER_REPO = "/dspico"
PYTHON_ENTRY = "dspico.pipeline.run"
```

Add the parameter `engine_kind: str = "bash"` to `run_container_argv`, and replace the mount and
trailing-command section with:

```python
    if engine_kind == "python":
        argv += ["-v", f"{docker_mount_path(repo_dir)}:{CONTAINER_REPO}:ro"]
    else:
        argv += ["-v", f"{docker_mount_path(script_path)}:{CONTAINER_SCRIPT}:ro"]
```

and, after the image name:

```python
    if engine_kind == "python":
        flags = ""
        if config.wrfuxxed:
            flags += " --wrfuxxed"
        if config.ntrboot:
            flags += " --ntrboot"
        if config.edo_firmware:
            flags += " --edo-firmware"
        argv += [
            "-lc",
            f"PYTHONPATH={CONTAINER_REPO} python3 -m {PYTHON_ENTRY}{flags}",
        ]
    else:
        argv += ["-lc", CONTAINER_SCRIPT]
```

`repo_dir` becomes a keyword argument defaulting to `script_path.parent`, so the bash path is
unaffected.

- [ ] **Step 4: Add `--engine-kind` to the CLI**

In `dspico/cli.py`, add to the `build` subparser:

```python
    build.add_argument(
        "--engine-kind",
        choices=("bash", "python"),
        default="bash",
        help="which pipeline implementation to run inside the container",
    )
```

and pass `engine_kind=args.engine_kind` through to `run_container_argv`.

- [ ] **Step 5: Write `dspico/pipeline/run.py`**

```python
"""The in-container entry point: ``python3 -m dspico.pipeline.run``.

Runs inside the build image, where the toolchain lives. Paths are the container's
mount points, not the host's.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dspico.config import BuildConfig
from dspico.errors import BuildError
from dspico.pipeline.context import BuildContext
from dspico.pipeline.plan import build_plan, labelled
from dspico.runtime import SubprocessRunner

CONTAINER_INPUTS = Path("/inputs")
CONTAINER_OUTPUTS = Path("/outputs")
CONTAINER_WORK = Path("/tmp/dspico-build")


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dspico.pipeline.run", description="Run the DSpico build inside the container."
    )
    parser.add_argument("--wrfuxxed", action="store_true")
    parser.add_argument("--ntrboot", action="store_true")
    parser.add_argument("--edo-firmware", action="store_true")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_run_parser().parse_args(argv)
    config = BuildConfig(
        inputs_dir=CONTAINER_INPUTS,
        outputs_dir=CONTAINER_OUTPUTS,
        wrfuxxed=args.wrfuxxed,
        ntrboot=args.ntrboot,
        edo_firmware=args.edo_firmware,
    )
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
        for label, step in labelled(build_plan(config)):
            print(f"\n[{label}] {step.title}")
            _dispatch(ctx, step.name, jobs=args.jobs)
    except BuildError as error:
        print(f"ERROR: {error.message}", file=sys.stderr)
        return 1
    print(f"\nAll components built successfully. Outputs: {ctx.out_base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`_dispatch` maps a step name to its implementation; write it as an explicit `if/elif` chain over the
nine names so mypy checks every branch, raising `BuildError` for an unknown name.

- [ ] **Step 6: Write the entry point tests**

Create `tests/test_pipeline_run.py`:

```python
"""The in-container entry point's argument handling."""

from dspico.pipeline.run import CONTAINER_INPUTS, CONTAINER_OUTPUTS, build_run_parser


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
```

- [ ] **Step 7: Run the tests and gates**

Run:
```bash
.venv/bin/python -m pytest -v
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
```
Expected: all pass.

- [ ] **Step 8: Verify the package still imports inside the real image**

Run:
```bash
docker run --rm -v "$PWD":/dspico:ro -w /dspico --entrypoint bash dspico-compiler:latest -lc \
  'PYTHONPATH=/dspico python3 -m dspico.pipeline.run --help'
```
Expected: the help text prints. This is what proves the entry point works on the container's
Python 3.11.2 without being installed.

- [ ] **Step 9: Commit**

```bash
git add dspico/pipeline/run.py dspico/host/launcher.py dspico/cli.py tests/
git commit -m "feat(pipeline): add the in-container entry point behind --engine-kind=python"
```

---

### Task 6: Document the second engine

**Files:**
- Modify: `README.md`, `CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-08-05-python-pipeline-engine.md` (deviations)

- [ ] **Step 1: Document the flag in both files**

Add to the README's build section and CLAUDE.md's Commands section:

````markdown
```bash
# Default: the shell pipeline, unchanged
python -m dspico build

# The Python pipeline, for side-by-side comparison before the shell is removed
python -m dspico build --engine-kind=python
```
````

State plainly that `--engine-kind=python` is **unvalidated against a real build** until the user runs
it with their own inputs, and that the two engines are meant to be compared on: identical relative
file tree under `outputs/dspico/`, identical file sizes, identical upstream commit in every
`BUILD_INFO.txt`.

- [ ] **Step 2: Commit**

```bash
git add README.md CLAUDE.md docs
git commit -m "docs: document the python pipeline engine"
```

---

## Deviations, as executed

1. **Three steps are not ported.** `encryptor`, `firmware` and `ntrboot_variants` need drivers that
   orchestrate .NET, ROM injection and repeated firmware builds. They are listed in
   `PENDING_STEPS` and **raise** `BuildError` when dispatched, so a partial engine aborts rather
   than producing a build that looks successful. A test asserts that behaviour for each of them,
   and another asserts every planned step has a dispatch route — so adding a step without wiring it
   up fails the suite instead of being silently skipped.
2. **`--plan-only` was added to the in-container entry point.** It prints the steps a configuration
   would run and exits. It is what made verification inside the real image possible without any
   copyrighted input, and it is how the honest step numbering was confirmed.
3. **`components.py` was written before its test.** A TDD slip on my part; corrected by moving the
   module aside and confirming the tests went red before restoring it.
4. **ruff caught two regex-in-`match=` defects in the plan's own test code.** `match="LAUNCHER.nds"`
   treats `.` as a metacharacter; escaped to `r"LAUNCHER\.nds"`.
5. **One test assertion in this plan was wrong.** `argv[-3:-1] == ["bash", "-lc"]` does not hold —
   `bash` appears as the `--entrypoint` value, not immediately before `-lc`. Rewritten to assert
   the actual intent.

## Definition of done

- [ ] `.venv/bin/python -m pytest` passes; the suite grew by roughly 50 tests.
- [ ] `ruff check .`, `ruff format --check .` and `mypy` all exit 0.
- [ ] `mutmut run` reports zero survivors.
- [ ] `python -m dspico build --dry-run` is byte-identical to PR 2's output (the default engine did not move).
- [ ] `python -m dspico build --dry-run --engine-kind=python` mounts the repo and runs `python3 -m dspico.pipeline.run` under `bash -lc`.
- [ ] `PYTHONPATH=/dspico python3 -m dspico.pipeline.run --help` works inside the real image.
- [ ] `git diff main -- compile_resources.sh Dockerfile` shows only PR 2's ownership fix.
- [ ] `shellcheck --severity=warning` still passes.
- [ ] The PR body states that the Python engine is **not** validated against a real build, and gives the exact comparison procedure.
