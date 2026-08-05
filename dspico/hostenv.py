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
