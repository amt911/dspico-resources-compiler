"""Building DSRomEncryptor and preparing ROMs for encryption."""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.rom import needs_padding, pad_rom

ENCRYPTOR_URL = "https://github.com/Gericom/DSRomEncryptor"
NTR_SOURCES = ("ntrBlowfish.bin", "biosnds7.rom")
TWL_SOURCES = ("twlBlowfish.bin", "biosdsi7.rom")


def stage_blowfish(blowfish_dir: Path, bin_dir: Path) -> None:
    """Copy the Blowfish tables next to the encryptor and check NTR is present.

    Copies rather than reading in place because ``/inputs`` is mounted read-only
    and DSRomEncryptor expects the tables in its own working directory.
    """
    if blowfish_dir.is_dir():
        for source in sorted(blowfish_dir.iterdir()):
            if source.is_file():
                shutil.copy2(source, bin_dir / source.name)

    if not any((bin_dir / name).is_file() for name in NTR_SOURCES):
        raise BuildError(
            f"NTR Blowfish not found (need {' or '.join(NTR_SOURCES)} in inputs/blowfish/)",
            step="encryptor",
        )


def has_twl_blowfish(bin_dir: Path) -> bool:
    """Whether DSi encryption is possible. Optional, so callers warn rather than fail."""
    return any((bin_dir / name).is_file() for name in TWL_SOURCES)


def prepare_rom(source: Path, work_dir: Path) -> Path:
    """Return a ROM at least 0x8000 bytes long, padding a copy if needed.

    DSRomEncryptor writes test patterns at 0x3000-0x3FFF and processes the
    secure area at 0x4000-0x8000, so a shorter ROM cannot be encrypted. The
    original is never modified — the bash engine may still be reading it.
    """
    data = source.read_bytes()
    if not needs_padding(len(data)):
        return source
    work_dir.mkdir(parents=True, exist_ok=True)
    padded = work_dir / f"{source.stem}_padded.nds"
    padded.write_bytes(pad_rom(data))
    return padded
