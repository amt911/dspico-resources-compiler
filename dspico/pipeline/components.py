"""The upstream components this repository orchestrates.

Every URL here is a supply-chain surface. Adding one is a deliberate decision,
not a refactor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Component:
    """An upstream repository and the artifact its build is expected to produce."""

    name: str
    url: str
    artifact: str
    recursive: bool = False
    submodules: bool = False


COMPONENTS: dict[str, Component] = {
    "dldi": Component(
        name="dldi",
        url="https://github.com/LNH-team/dspico-dldi.git",
        artifact="*.dldi",
    ),
    "bootloader": Component(
        name="bootloader",
        url="https://github.com/LNH-team/dspico-bootloader.git",
        artifact="BOOTLOADER.nds",
        submodules=True,
    ),
    "wrfuxxed": Component(
        name="wrfuxxed",
        url="https://github.com/LNH-team/dspico-wrfuxxed",
        artifact="uartBufv060.bin",
    ),
    "pico_loader": Component(
        name="pico_loader",
        url="https://github.com/LNH-team/pico-loader",
        artifact="picoLoader7.bin",
        recursive=True,
    ),
    "pico_launcher": Component(
        name="pico_launcher",
        url="https://github.com/LNH-team/pico-launcher",
        artifact="LAUNCHER.nds",
        submodules=True,
    ),
}
