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

    edo = BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=True, edo_firmware=True)
    assert edo.ntrboot_needs_separate_builds is False

    off = BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=False)
    assert off.ntrboot_needs_separate_builds is False

    off_edo = BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=False, edo_firmware=True)
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
