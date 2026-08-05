"""The command that runs the build inside the container."""

from pathlib import Path

from dspico.config import BuildConfig
from dspico.errors import BuildError
from dspico.hostenv import HostEnv, docker_mount_path, docker_platform

CONTAINER_INPUTS = "/inputs"
CONTAINER_OUTPUTS = "/outputs"
CONTAINER_SCRIPT = "/dspico/compile_resources.sh"
CONTAINER_REPO = "/dspico"
PYTHON_ENTRY = "dspico.pipeline.run"

ENGINE_KINDS = ("bash", "python")


def _python_payload(config: BuildConfig) -> str:
    """The in-container command for the Python engine.

    Still routed through ``bash -lc`` by the caller: /etc/profile.d/wonderful.sh
    sources wf-env, and that is what puts the BlocksDS toolchain on PATH.
    """
    flags = ""
    if config.wrfuxxed:
        flags += " --wrfuxxed"
    if config.ntrboot:
        flags += " --ntrboot"
    if config.edo_firmware:
        flags += " --edo-firmware"
    return f"PYTHONPATH={CONTAINER_REPO} python3 -m {PYTHON_ENTRY}{flags}"


def run_container_argv(
    config: BuildConfig,
    env: HostEnv,
    *,
    script_path: Path,
    engine: str = "docker",
    engine_kind: str = "bash",
    repo_dir: Path | None = None,
) -> list[str]:
    """The full ``docker run`` invocation for this build.

    ``engine`` is the container CLI; ``engine_kind`` selects which pipeline
    implementation runs inside. The bash path is kept byte-identical to
    ``build_resources.sh`` while both engines exist.
    """
    if engine_kind not in ENGINE_KINDS:
        raise BuildError(
            f"unknown engine kind {engine_kind!r}; expected one of {', '.join(ENGINE_KINDS)}"
        )

    argv = [engine, "run", "--rm"]
    platform = docker_platform(env)
    if platform is not None:
        argv += ["--platform", platform]
    argv += [
        "-v",
        f"{docker_mount_path(config.inputs_dir)}:{CONTAINER_INPUTS}:ro",
        "-v",
        f"{docker_mount_path(config.outputs_dir)}:{CONTAINER_OUTPUTS}",
    ]

    if engine_kind == "python":
        # The package is imported over PYTHONPATH, never installed, so the whole
        # repository is mounted read-only rather than just the one script.
        repo = script_path.parent if repo_dir is None else repo_dir
        argv += ["-v", f"{docker_mount_path(repo)}:{CONTAINER_REPO}:ro"]
    else:
        argv += ["-v", f"{docker_mount_path(script_path)}:{CONTAINER_SCRIPT}:ro"]

    argv += [
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
        _python_payload(config) if engine_kind == "python" else CONTAINER_SCRIPT,
    ]
    return argv
