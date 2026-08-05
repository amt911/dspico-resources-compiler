"""The plan decides which steps run and what they are numbered.

compile_resources.sh hardcoded its step labels ("5/$TOTAL_STEPS") while computing
the total separately, so the printed numbering drifted out of sync with the steps
that actually ran. Deriving both from one list removes that class of bug.
"""

from pathlib import Path

import pytest

from dspico.config import BuildConfig
from dspico.pipeline.plan import Step, build_plan, labelled

BASE_STEPS = (
    "dldi",
    "bootloader",
    "encryptor",
    "firmware",
    "pico_loader",
    "pico_launcher",
    "sd_card",
)


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "inputs", tmp_path / "outputs"


def test_default_build_runs_the_seven_base_steps(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs))
    assert tuple(step.name for step in plan) == BASE_STEPS


def test_wrfuxxed_is_inserted_between_encryptor_and_firmware(
    dirs: tuple[Path, Path],
) -> None:
    # It DLDI-patches using the driver from step 1 and its output is consumed by
    # the firmware step, so the position is a real constraint, not cosmetics.
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True))
    names = [step.name for step in plan]
    assert names.index("encryptor") < names.index("wrfuxxed") < names.index("firmware")
    assert len(plan) == 8


def test_lnh_firmware_appends_ntrboot_variants_last(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=True))
    assert plan[-1].name == "ntrboot_variants"
    assert len(plan) == 8


def test_edo_firmware_omits_ntrboot_variants(dirs: tuple[Path, Path]) -> None:
    # The edo9300 fork has 4 ROM slots and embeds ntrboot in the main firmware
    # build, so a separate variants step would rebuild for nothing.
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(inputs_dir=inputs, outputs_dir=outputs, ntrboot=True, edo_firmware=True)
    )
    assert [step.name for step in plan] == list(BASE_STEPS)


def test_edo_firmware_without_ntrboot_omits_variants(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(BuildConfig(inputs_dir=inputs, outputs_dir=outputs, edo_firmware=True))
    assert "ntrboot_variants" not in [step.name for step in plan]


def test_every_flag_on_gives_nine_steps(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True, ntrboot=True)
    )
    assert len(plan) == 9


def test_step_titles_are_pinned(dirs: tuple[Path, Path]) -> None:
    # Titles are user-facing output, and pinning them exactly is also what makes
    # the 100% mutation gate reachable: a test that only checked "title is
    # non-empty" would let every string-literal mutant survive.
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True, ntrboot=True)
    )
    assert {step.name: step.title for step in plan} == {
        "dldi": "Build DSpico DLDI",
        "bootloader": "Build DSpico Bootloader",
        "encryptor": "Build DSRomEncryptor and encrypt the bootloader",
        "wrfuxxed": "Build WRFUxxed",
        "firmware": "Build DSpico Firmware",
        "pico_loader": "Build Pico Loader",
        "pico_launcher": "Build Pico Launcher",
        "sd_card": "Assemble the SD card structure",
        "ntrboot_variants": "Build ntrboot firmware variants",
    }


def test_step_names_are_unique(dirs: tuple[Path, Path]) -> None:
    inputs, outputs = dirs
    plan = build_plan(
        BuildConfig(inputs_dir=inputs, outputs_dir=outputs, wrfuxxed=True, ntrboot=True)
    )
    names = [step.name for step in plan]
    assert len(names) == len(set(names))


def test_labels_are_derived_from_the_actual_plan_length() -> None:
    steps = (Step("a", "A"), Step("b", "B"), Step("c", "C"))
    assert labelled(steps) == (("1/3", steps[0]), ("2/3", steps[1]), ("3/3", steps[2]))


def test_labels_of_an_empty_plan_are_empty() -> None:
    assert labelled(()) == ()
