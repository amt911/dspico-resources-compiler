"""Assembling the ready-to-copy SD card layout.

This is the deliverable: everything else exists to produce this directory.
"""

import shutil
from pathlib import Path

from dspico.errors import BuildError
from dspico.pipeline.artifacts import copy_glob, find_artifact

BOOT_FILE = "_picoboot.nds"
ARM9_LOADER = "picoLoader9.bin"
OPTIONAL_LISTS = ("aplist.bin", "savelist.bin", "patchlist.bin")


def assemble(out_base: Path) -> Path:
    """Build ``sd_card/`` from the component outputs, from scratch.

    Rebuilt rather than updated so a stale artifact from a previous flag
    combination cannot survive into the deliverable.
    """
    sd = out_base / "sd_card"
    if sd.exists():
        shutil.rmtree(sd)
    pico = sd / "_pico"
    pico.mkdir(parents=True)

    themes = out_base / "pico_launcher" / "_pico"
    if themes.is_dir():
        shutil.copytree(themes, pico, dirs_exist_ok=True)

    loader = out_base / "pico_loader"
    if loader.is_dir():
        copy_glob(loader, "picoLoader7*.bin", pico, depth=0, required=False)
        for optional in OPTIONAL_LISTS:
            copy_glob(loader, optional, pico, depth=0, required=False)
        # Upstream emits picoLoader9<variant>.bin; the launcher opens exactly
        # picoLoader9.bin, and a missing one is the "Failed to open Pico Loader"
        # red screen, so this is required rather than best-effort.
        arm9 = find_artifact(loader, "picoLoader9*.bin", depth=0)
        shutil.copy2(arm9, pico / ARM9_LOADER)

    launcher = out_base / "pico_launcher" / "LAUNCHER.nds"
    if not launcher.is_file():
        raise BuildError(f"LAUNCHER.nds not found at {launcher}", step="sd_card")
    shutil.copy2(launcher, sd / BOOT_FILE)
    return sd
