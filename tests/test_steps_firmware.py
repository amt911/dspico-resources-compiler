"""Firmware assembly, and the CMake flag the shell silently failed to set."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.steps.firmware import FIRMWARE_URLS, enable_wrfuxxed_flag, firmware_url

COMMENTED = """\
set(SOURCES main.c)
  #DSPICO_ENABLE_WRFUXXED
target_link_libraries(x)
"""

UNCOMMENTED = """\
set(SOURCES main.c)
  DSPICO_ENABLE_WRFUXXED
target_link_libraries(x)
"""

RENAMED_UPSTREAM = """\
set(SOURCES main.c)
  #DSPICO_ENABLE_WRFU_EXPLOIT
target_link_libraries(x)
"""


def test_uncomments_the_flag(tmp_path: Path) -> None:
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(COMMENTED, encoding="utf-8")
    enable_wrfuxxed_flag(cmakelists)
    assert cmakelists.read_text(encoding="utf-8") == UNCOMMENTED


def test_tolerates_spacing_after_the_hash(tmp_path: Path) -> None:
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text("  #  DSPICO_ENABLE_WRFUXXED\n", encoding="utf-8")
    enable_wrfuxxed_flag(cmakelists)
    assert cmakelists.read_text(encoding="utf-8") == "  DSPICO_ENABLE_WRFUXXED\n"


def test_already_enabled_is_accepted(tmp_path: Path) -> None:
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(UNCOMMENTED, encoding="utf-8")
    enable_wrfuxxed_flag(cmakelists)
    assert cmakelists.read_text(encoding="utf-8") == UNCOMMENTED


def test_upstream_rename_fails_loudly(tmp_path: Path) -> None:
    # The shell ran `sed ... || true`, so this case shipped a firmware with the
    # exploit quietly missing. This is the whole reason the function exists.
    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(RENAMED_UPSTREAM, encoding="utf-8")
    with pytest.raises(BuildError, match="DSPICO_ENABLE_WRFUXXED"):
        enable_wrfuxxed_flag(cmakelists)


def test_missing_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match=r"CMakeLists\.txt"):
        enable_wrfuxxed_flag(tmp_path / "absent" / "CMakeLists.txt")


def test_firmware_urls_are_pinned() -> None:
    assert FIRMWARE_URLS["lnh"] == "https://github.com/LNH-team/dspico-firmware"
    assert FIRMWARE_URLS["edo"] == "https://github.com/edo9300/dspico-firmware"


def test_edo_flag_selects_the_fork() -> None:
    assert firmware_url(edo_firmware=False) == FIRMWARE_URLS["lnh"]
    assert firmware_url(edo_firmware=True) == FIRMWARE_URLS["edo"]
