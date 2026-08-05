"""Blowfish staging and ROM preparation."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.rom import SECURE_AREA_END
from dspico.pipeline.steps.encryptor import prepare_rom, stage_blowfish


def test_copies_every_input_file(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "ntrBlowfish.bin").write_bytes(b"\x00" * 16)
    (inputs / "twlBlowfish.bin").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    stage_blowfish(inputs, bin_dir)

    assert (bin_dir / "ntrBlowfish.bin").exists()
    assert (bin_dir / "twlBlowfish.bin").exists()


def test_bios_dumps_satisfy_the_requirement(tmp_path: Path) -> None:
    # Either the extracted table or the BIOS dump it comes from is accepted.
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "biosnds7.rom").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    stage_blowfish(inputs, bin_dir)

    assert (bin_dir / "biosnds7.rom").exists()


def test_missing_ntr_blowfish_fails_loudly(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "twlBlowfish.bin").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    with pytest.raises(BuildError, match="NTR Blowfish"):
        stage_blowfish(inputs, bin_dir)


def test_missing_blowfish_directory_fails_loudly(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    with pytest.raises(BuildError, match="NTR Blowfish"):
        stage_blowfish(tmp_path / "absent", bin_dir)


def test_inputs_are_never_written_to(tmp_path: Path) -> None:
    # /inputs is mounted read-only; a step that wrote there would fail only on a
    # real run, long after the tests passed.
    inputs = tmp_path / "inputs" / "blowfish"
    inputs.mkdir(parents=True)
    (inputs / "ntrBlowfish.bin").write_bytes(b"\x00" * 16)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    before = sorted(p.name for p in inputs.iterdir())
    stage_blowfish(inputs, bin_dir)
    assert sorted(p.name for p in inputs.iterdir()) == before


def test_short_rom_is_padded_into_the_work_directory(tmp_path: Path) -> None:
    source = tmp_path / "BOOTLOADER.nds"
    source.write_bytes(b"\xaa" * 1024)
    work = tmp_path / "work"

    prepared = prepare_rom(source, work)

    assert prepared != source
    assert prepared.parent == work
    assert len(prepared.read_bytes()) == SECURE_AREA_END
    # The original must be left untouched for the bash engine to reuse.
    assert len(source.read_bytes()) == 1024


def test_large_enough_rom_is_used_as_is(tmp_path: Path) -> None:
    source = tmp_path / "big.nds"
    source.write_bytes(b"\xbb" * (SECURE_AREA_END + 128))
    assert prepare_rom(source, tmp_path / "work") == source
