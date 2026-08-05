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

    No ``--build-arg USER_UID``: the ``Dockerfile`` ends on ``USER root``, so the
    ``builder`` account those args configure never runs the build. Output
    ownership is corrected inside the container instead.
    """
    argv = [engine, "build"]
    platform = docker_platform(env)
    if platform is not None:
        argv += ["--platform", platform]
    argv += ["-t", config.image_name, str(context_dir)]
    return argv
