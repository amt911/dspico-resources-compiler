"""The CLI turns flags into a BuildConfig and a pair of commands."""

from pathlib import Path

import pytest

from dspico.cli import build_parser, config_from_args, main


def test_flags_default_to_off(tmp_path: Path) -> None:
    args = build_parser().parse_args(["build"])
    config = config_from_args(args, cwd=tmp_path)
    assert config.wrfuxxed is False
    assert config.ntrboot is False
    assert config.edo_firmware is False


def test_inputs_and_outputs_default_to_the_working_directory(tmp_path: Path) -> None:
    args = build_parser().parse_args(["build"])
    config = config_from_args(args, cwd=tmp_path)
    assert config.inputs_dir == tmp_path / "inputs"
    assert config.outputs_dir == tmp_path / "outputs"


def test_relative_directory_arguments_are_resolved_against_cwd(tmp_path: Path) -> None:
    # BuildConfig rejects relative paths, so the CLI must absolutise first.
    args = build_parser().parse_args(["build", "--inputs", "my-in"])
    config = config_from_args(args, cwd=tmp_path)
    assert config.inputs_dir.is_absolute()
    assert config.inputs_dir == tmp_path / "my-in"


@pytest.mark.parametrize(
    ("flag", "attribute"),
    [
        ("--wrfuxxed", "wrfuxxed"),
        ("--ntrboot", "ntrboot"),
        ("--edo-firmware", "edo_firmware"),
    ],
)
def test_each_feature_flag_sets_its_field(tmp_path: Path, flag: str, attribute: str) -> None:
    args = build_parser().parse_args(["build", flag])
    config = config_from_args(args, cwd=tmp_path)
    assert getattr(config, attribute) is True


def test_image_name_is_overridable(tmp_path: Path) -> None:
    args = build_parser().parse_args(["build", "--image", "mine:dev"])
    assert config_from_args(args, cwd=tmp_path).image_name == "mine:dev"


def _make_context(tmp_path: Path) -> None:
    (tmp_path / "inputs").mkdir(exist_ok=True)
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "compile_resources.sh").write_text("#!/bin/bash\n", encoding="utf-8")


def test_dry_run_prints_both_commands_and_runs_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)

    code = main(
        [
            "build",
            "--dry-run",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(tmp_path / "outputs"),
            "--context",
            str(tmp_path),
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "$ docker build" in out
    assert "$ docker run --rm" in out
    # Must not claim a build finished when nothing ran.
    assert "Dry run: nothing was executed." in out
    assert "Finished." not in out


def test_dry_run_does_not_create_the_outputs_directory(tmp_path: Path) -> None:
    _make_context(tmp_path)
    outputs = tmp_path / "outputs"

    main(
        [
            "build",
            "--dry-run",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(outputs),
            "--context",
            str(tmp_path),
        ]
    )

    assert not outputs.exists()


def test_skip_image_build_emits_only_the_run_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)

    code = main(
        [
            "build",
            "--dry-run",
            "--skip-image-build",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(tmp_path / "outputs"),
            "--context",
            str(tmp_path),
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "$ docker build" not in out
    assert "$ docker run --rm" in out


def test_missing_dockerfile_fails_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A wrong --context is an easy mistake and would otherwise surface as an
    # opaque docker error several seconds later.
    code = main(
        [
            "build",
            "--dry-run",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(tmp_path / "outputs"),
            "--context",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert "Dockerfile" in capsys.readouterr().err


def test_missing_pipeline_script_fails_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    code = main(
        [
            "build",
            "--dry-run",
            "--inputs",
            str(tmp_path / "inputs"),
            "--outputs",
            str(tmp_path / "outputs"),
            "--context",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert "compile_resources.sh" in capsys.readouterr().err


def test_identical_inputs_and_outputs_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["build", "--dry-run", "--inputs", str(tmp_path), "--outputs", str(tmp_path)])
    assert code == 1
    assert "differ" in capsys.readouterr().err


def test_no_subcommand_shows_usage() -> None:
    assert main([]) == 2
