"""The container run command, asserted exactly.

Must stay equivalent to build_resources.sh:14-22 for as long as both launchers
exist, so the two paths cannot silently diverge.
"""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.host.launcher import (
    CONTAINER_INPUTS,
    CONTAINER_OUTPUTS,
    CONTAINER_SCRIPT,
    run_container_argv,
)
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


def test_container_paths_are_pinned() -> None:
    assert CONTAINER_INPUTS == "/inputs"
    assert CONTAINER_OUTPUTS == "/outputs"
    assert CONTAINER_SCRIPT == "/dspico/compile_resources.sh"


def test_full_default_invocation(config: BuildConfig, tmp_path: Path) -> None:
    script = tmp_path / "compile_resources.sh"
    argv = run_container_argv(config, X86_LINUX, script_path=script)
    assert argv == [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{(tmp_path / 'inputs').as_posix()}:/inputs:ro",
        "-v",
        f"{(tmp_path / 'outputs').as_posix()}:/outputs",
        "-v",
        f"{script.as_posix()}:/dspico/compile_resources.sh:ro",
        "-e",
        "ENABLE_WRFUXXED=0",
        "-e",
        "ENABLE_NTRBOOT=0",
        "-e",
        "USE_EDO_FIRMWARE=0",
        "--entrypoint",
        "bash",
        "dspico-compiler:test",
        "-lc",
        "/dspico/compile_resources.sh",
    ]


def test_inputs_are_mounted_read_only(config: BuildConfig, tmp_path: Path) -> None:
    # /inputs holds the user's copyrighted dumps and the pipeline must never
    # write there; losing :ro would be silent until something corrupted them.
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    inputs_mount = next(a for a in argv if a.endswith(":/inputs:ro"))
    assert inputs_mount.endswith(":ro")


def test_outputs_are_mounted_writable(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    assert any(a.endswith(":/outputs") for a in argv)


def test_apple_silicon_forces_amd64(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(config, APPLE_SILICON, script_path=tmp_path / "s.sh")
    assert argv[:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]


@pytest.mark.parametrize(
    ("wrfuxxed", "ntrboot", "edo_firmware", "expected"),
    [
        (False, False, False, ["ENABLE_WRFUXXED=0", "ENABLE_NTRBOOT=0", "USE_EDO_FIRMWARE=0"]),
        (True, False, False, ["ENABLE_WRFUXXED=1", "ENABLE_NTRBOOT=0", "USE_EDO_FIRMWARE=0"]),
        (False, True, False, ["ENABLE_WRFUXXED=0", "ENABLE_NTRBOOT=1", "USE_EDO_FIRMWARE=0"]),
        (False, False, True, ["ENABLE_WRFUXXED=0", "ENABLE_NTRBOOT=0", "USE_EDO_FIRMWARE=1"]),
        (True, True, True, ["ENABLE_WRFUXXED=1", "ENABLE_NTRBOOT=1", "USE_EDO_FIRMWARE=1"]),
    ],
)
def test_flags_become_the_env_vars_the_shell_pipeline_reads(
    tmp_path: Path,
    wrfuxxed: bool,
    ntrboot: bool,
    edo_firmware: bool,
    expected: list[str],
) -> None:
    # compile_resources.sh still reads these names; the CLI flag is only the
    # host-side spelling.
    config = BuildConfig(
        inputs_dir=tmp_path / "inputs",
        outputs_dir=tmp_path / "outputs",
        wrfuxxed=wrfuxxed,
        ntrboot=ntrboot,
        edo_firmware=edo_firmware,
    )
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh")
    env_values = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert env_values == expected


def test_engine_is_overridable(config: BuildConfig, tmp_path: Path) -> None:
    argv = run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh", engine="podman")
    assert argv[0] == "podman"


def test_python_engine_runs_the_package_through_a_login_shell(
    config: BuildConfig, tmp_path: Path
) -> None:
    # Still bash -lc: /etc/profile.d/wonderful.sh sources wf-env, which is what
    # puts the BlocksDS toolchain on PATH. Only the payload changes.
    argv = run_container_argv(
        config, X86_LINUX, script_path=tmp_path / "s.sh", engine_kind="python"
    )
    assert argv[argv.index("--entrypoint") + 1] == "bash"
    assert argv[-2] == "-lc"
    payload = argv[-1]
    assert "python3 -m dspico.pipeline.run" in payload
    assert "PYTHONPATH=/dspico" in payload


def test_python_engine_mounts_the_repository_read_only(config: BuildConfig, tmp_path: Path) -> None:
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


def test_unknown_engine_kind_is_rejected(config: BuildConfig, tmp_path: Path) -> None:
    from dspico.errors import BuildError

    with pytest.raises(BuildError, match="engine"):
        run_container_argv(config, X86_LINUX, script_path=tmp_path / "s.sh", engine_kind="perl")
