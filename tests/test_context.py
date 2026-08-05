"""BuildContext replaces the shell pipeline's shared globals."""

from pathlib import Path

import pytest

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
    ctx = _ctx(tmp_path)
    with pytest.raises(AttributeError):
        ctx.work = tmp_path  # type: ignore[misc]
