"""The clone-build-copy shape shared by five steps."""

from collections.abc import Sequence
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

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        super().run(argv, step=step)
        if argv[0] == "make":
            self._artifact.parent.mkdir(parents=True, exist_ok=True)
            self._artifact.write_bytes(b"artifact")


def _context(tmp_path: Path, runner: FakeRunner) -> BuildContext:
    return BuildContext(
        config=BuildConfig(inputs_dir=tmp_path / "in", outputs_dir=tmp_path / "out"),
        runner=runner,
        inputs=tmp_path / "in",
        out_base=tmp_path / "out" / "dspico",
        work=tmp_path / "work",
    )


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
    assert COMPONENTS["pico_loader"].artifact == "picoLoader7.bin"
    assert COMPONENTS["pico_launcher"].artifact == "LAUNCHER.nds"


def test_pico_loader_clones_recursively() -> None:
    assert COMPONENTS["pico_loader"].recursive is True


def test_bootloader_and_launcher_need_submodules() -> None:
    assert COMPONENTS["bootloader"].submodules is True
    assert COMPONENTS["pico_launcher"].submodules is True


def test_only_the_components_the_pipeline_knows_about_exist() -> None:
    assert sorted(COMPONENTS) == [
        "bootloader",
        "dldi",
        "pico_launcher",
        "pico_loader",
        "wrfuxxed",
    ]


def test_build_component_clones_builds_and_copies(tmp_path: Path) -> None:
    component = Component(name="dldi", url="https://example.invalid/d.git", artifact="*.dldi")
    runner = BuildingRunner(tmp_path / "work" / "dldi" / "DSpico.dldi")
    ctx = _context(tmp_path, runner)

    produced = build_component(ctx, component, jobs=2, write_info=False)

    assert produced == tmp_path / "out" / "dspico" / "dldi" / "DSpico.dldi"
    assert produced.read_bytes() == b"artifact"
    assert [c[0] for c in runner.calls] == ["git", "make"]


def test_build_component_initialises_submodules_when_asked(tmp_path: Path) -> None:
    component = Component(
        name="bootloader",
        url="https://example.invalid/b.git",
        artifact="BOOTLOADER.nds",
        submodules=True,
    )
    runner = BuildingRunner(tmp_path / "work" / "bootloader" / "BOOTLOADER.nds")
    ctx = _context(tmp_path, runner)

    build_component(ctx, component, jobs=1, write_info=False)

    assert [c[0] for c in runner.calls] == ["git", "git", "make"]
    assert runner.calls[1][3] == "submodule"


def test_build_component_passes_a_pinned_commit_through(tmp_path: Path) -> None:
    component = Component(name="dldi", url="https://example.invalid/d.git", artifact="*.dldi")
    runner = BuildingRunner(tmp_path / "work" / "dldi" / "DSpico.dldi")
    ctx = _context(tmp_path, runner)

    build_component(ctx, component, jobs=1, commit="deadbee", write_info=False)

    assert runner.calls[1] == (
        "git",
        "-C",
        str(tmp_path / "work" / "dldi"),
        "checkout",
        "--detach",
        "deadbee",
    )


def test_build_component_fails_when_the_build_produced_nothing(tmp_path: Path) -> None:
    from dspico.errors import BuildError

    component = Component(name="dldi", url="https://example.invalid/d.git", artifact="*.dldi")
    # A plain FakeRunner never creates the artifact, standing in for a build that
    # exits 0 without emitting anything.
    ctx = _context(tmp_path, FakeRunner())

    with pytest.raises(BuildError, match="no file matching"):
        build_component(ctx, component, jobs=1, write_info=False)
