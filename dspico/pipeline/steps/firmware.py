"""The Pico firmware build, including the WRFUxxed CMake flag."""

import re
from pathlib import Path

from dspico.errors import BuildError

WRFUXXED_FLAG = "DSPICO_ENABLE_WRFUXXED"
_COMMENTED = re.compile(rf"^(\s*)#\s*({re.escape(WRFUXXED_FLAG)})", re.MULTILINE)
_ENABLED = re.compile(rf"^\s*{re.escape(WRFUXXED_FLAG)}\b", re.MULTILINE)

FIRMWARE_URLS = {
    "lnh": "https://github.com/LNH-team/dspico-firmware",
    "edo": "https://github.com/edo9300/dspico-firmware",
}


def firmware_url(*, edo_firmware: bool) -> str:
    """Which firmware repository this build uses.

    The edo9300 fork exposes 4 ROM slots instead of 2, which is what lets
    ntrboot be embedded in the single firmware build.
    """
    return FIRMWARE_URLS["edo"] if edo_firmware else FIRMWARE_URLS["lnh"]


def enable_wrfuxxed_flag(cmakelists: Path) -> None:
    """Uncomment the WRFUxxed flag in the upstream CMakeLists.

    Raises if the flag is nowhere to be found. The shell version ended this
    substitution in ``|| true``, so an upstream rename produced a firmware with
    the exploit silently missing — a build that looked entirely successful.
    """
    if not cmakelists.is_file():
        raise BuildError(f"CMakeLists.txt not found at: {cmakelists}", step="firmware")

    text = cmakelists.read_text(encoding="utf-8")
    patched, count = _COMMENTED.subn(r"\1\2", text)
    if count:
        cmakelists.write_text(patched, encoding="utf-8")
        return
    if _ENABLED.search(text):
        return
    raise BuildError(
        f"{WRFUXXED_FLAG} not found in {cmakelists}; upstream may have renamed it",
        step="firmware",
    )
