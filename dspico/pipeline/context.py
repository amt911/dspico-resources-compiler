"""What every build step is handed.

Replaces the shell pipeline's shared globals (DLDI_FILE, BOOTLOADER_NDS,
ENCRYPTED_NDS, ENCRYPTOR_BIN) with an explicit argument, so a step's inputs are
visible in its signature rather than implied by call order.
"""

from dataclasses import dataclass
from pathlib import Path

from dspico.config import BuildConfig
from dspico.runtime import Runner


@dataclass(frozen=True)
class BuildContext:
    """Config, the command runner, and the resolved locations for one build."""

    config: BuildConfig
    runner: Runner
    inputs: Path
    out_base: Path
    work: Path

    def component_dir(self, name: str) -> Path:
        """The output directory for a component, created if needed."""
        path = self.out_base / name
        path.mkdir(parents=True, exist_ok=True)
        return path
