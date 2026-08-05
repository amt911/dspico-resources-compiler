"""Which steps run, in what order, and what they are numbered."""

from dataclasses import dataclass

from dspico.config import BuildConfig


@dataclass(frozen=True)
class Step:
    """One unit of the build. ``name`` is the stable key; ``title`` is for humans."""

    name: str
    title: str


def build_plan(config: BuildConfig) -> tuple[Step, ...]:
    """The ordered steps this configuration will actually run.

    Optional steps are absent rather than present-and-skipped, so the length of
    the returned tuple is the real step count.
    """
    steps: list[Step] = [
        Step("dldi", "Build DSpico DLDI"),
        Step("bootloader", "Build DSpico Bootloader"),
        Step("encryptor", "Build DSRomEncryptor and encrypt the bootloader"),
    ]
    if config.wrfuxxed:
        steps.append(Step("wrfuxxed", "Build WRFUxxed"))
    steps += [
        Step("firmware", "Build DSpico Firmware"),
        Step("pico_loader", "Build Pico Loader"),
        Step("pico_launcher", "Build Pico Launcher"),
        Step("sd_card", "Assemble the SD card structure"),
    ]
    if config.ntrboot_needs_separate_builds:
        steps.append(Step("ntrboot_variants", "Build ntrboot firmware variants"))
    return tuple(steps)


def labelled(steps: tuple[Step, ...]) -> tuple[tuple[str, Step], ...]:
    """Pair each step with its real ``n/total`` label.

    The shell pipeline hardcoded these numerators, so they lied whenever the set
    of enabled steps changed. Deriving them from the plan cannot drift.
    """
    total = len(steps)
    return tuple((f"{index}/{total}", step) for index, step in enumerate(steps, start=1))
