"""The validated description of one build."""

from dataclasses import dataclass
from pathlib import Path

from dspico.errors import ConfigError

DEFAULT_IMAGE_NAME = "dspico-compiler:latest"


@dataclass(frozen=True)
class BuildConfig:
    """Everything a build needs to know, validated at construction.

    Validating here means no later step can be handed a relative path that would
    silently produce a broken ``docker run -v`` mount.
    """

    inputs_dir: Path
    outputs_dir: Path
    wrfuxxed: bool = False
    ntrboot: bool = False
    edo_firmware: bool = False
    image_name: str = DEFAULT_IMAGE_NAME

    def __post_init__(self) -> None:
        for label, value in (
            ("inputs_dir", self.inputs_dir),
            ("outputs_dir", self.outputs_dir),
        ):
            if not value.is_absolute():
                raise ConfigError(f"{label} must be an absolute path, got: {value}")
        if self.inputs_dir == self.outputs_dir:
            raise ConfigError("inputs_dir and outputs_dir must differ")
        if not self.image_name.strip():
            raise ConfigError("image_name must not be empty")

    @property
    def ntrboot_needs_separate_builds(self) -> bool:
        """Whether ntrboot requires its own firmware builds.

        LNH-team firmware exposes 2 ROM slots (default.nds, dsimode.nds), so each
        ntrboot variant needs a dedicated build. The edo9300 fork has 4 slots and
        embeds ntrboot in the single main firmware build instead.
        """
        return self.ntrboot and not self.edo_firmware
