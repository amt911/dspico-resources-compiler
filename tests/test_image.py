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
