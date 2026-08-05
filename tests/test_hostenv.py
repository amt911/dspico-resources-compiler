"""Host detection decides --platform and the image's build UID/GID.

These are the two things that make the build work off Linux/x86_64, so every
branch is pinned here rather than discovered on a user's machine.
"""

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from dspico.hostenv import (
    AARCH64,
    DEFAULT_CONTAINER_GID,
    DEFAULT_CONTAINER_UID,
    X86_64,
    HostEnv,
    build_user,
    docker_mount_path,
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


def test_detect_returns_a_usable_env_on_this_host() -> None:
    # Runs on all three CI platforms. On Windows os.getuid does not exist, so
    # this asserts the fallback rather than crashing with AttributeError.
    env = HostEnv.detect()
    assert env.system
    assert env.machine
    assert env.uid >= 0
    assert env.gid >= 0
