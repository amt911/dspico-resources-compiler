"""SD card assembly — the actual deliverable."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.steps.sd_card import assemble


def _populate(out_base: Path) -> None:
    launcher = out_base / "pico_launcher"
    (launcher / "_pico").mkdir(parents=True)
    (launcher / "_pico" / "theme.bin").write_bytes(b"theme")
    (launcher / "LAUNCHER.nds").write_bytes(b"launcher")

    loader = out_base / "pico_loader"
    loader.mkdir(parents=True)
    (loader / "picoLoader7.bin").write_bytes(b"l7")
    (loader / "picoLoader9e.bin").write_bytes(b"l9")
    (loader / "aplist.bin").write_bytes(b"ap")


def test_launcher_becomes_the_boot_file(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    _populate(out_base)
    sd = assemble(out_base)
    assert (sd / "_picoboot.nds").read_bytes() == b"launcher"


def test_themes_and_loader_land_in_pico(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    _populate(out_base)
    sd = assemble(out_base)
    assert (sd / "_pico" / "theme.bin").read_bytes() == b"theme"
    assert (sd / "_pico" / "picoLoader7.bin").read_bytes() == b"l7"
    assert (sd / "_pico" / "aplist.bin").read_bytes() == b"ap"


def test_the_arm9_loader_is_renamed_to_a_fixed_name(tmp_path: Path) -> None:
    # Upstream emits picoLoader9<variant>.bin but the launcher looks for exactly
    # picoLoader9.bin, so the rename is load-bearing.
    out_base = tmp_path / "dspico"
    _populate(out_base)
    sd = assemble(out_base)
    assert (sd / "_pico" / "picoLoader9.bin").read_bytes() == b"l9"


def test_assembly_starts_from_scratch(tmp_path: Path) -> None:
    # sd_card/ is the deliverable; a leftover file from a previous flag
    # combination must not survive into it.
    out_base = tmp_path / "dspico"
    _populate(out_base)
    stale = out_base / "sd_card" / "_pico" / "stale.bin"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")

    sd = assemble(out_base)

    assert not (sd / "_pico" / "stale.bin").exists()


def test_optional_lists_may_be_absent(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    _populate(out_base)
    (out_base / "pico_loader" / "aplist.bin").unlink()
    sd = assemble(out_base)
    assert not (sd / "_pico" / "aplist.bin").exists()
    assert (sd / "_picoboot.nds").exists()


def test_missing_launcher_fails_loudly(tmp_path: Path) -> None:
    out_base = tmp_path / "dspico"
    (out_base / "pico_loader").mkdir(parents=True)
    (out_base / "pico_loader" / "picoLoader9e.bin").write_bytes(b"l9")
    with pytest.raises(BuildError, match=r"LAUNCHER\.nds"):
        assemble(out_base)


def test_missing_arm9_loader_fails_loudly(tmp_path: Path) -> None:
    # Without picoLoader9.bin the launcher shows the "Failed to open Pico
    # Loader" red screen, so an absent one must stop the build.
    out_base = tmp_path / "dspico"
    _populate(out_base)
    (out_base / "pico_loader" / "picoLoader9e.bin").unlink()
    with pytest.raises(BuildError, match="picoLoader9"):
        assemble(out_base)
