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
