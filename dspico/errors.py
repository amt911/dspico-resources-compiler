"""Failures the orchestrator raises deliberately, as opposed to crashes."""


class BuildError(Exception):
    """A build failure with a loud, attributable message.

    Replaces the shell pipeline's ``error_exit``. Carrying ``step`` lets the CLI
    report which step failed without every call site formatting its own prefix.
    """

    def __init__(self, message: str, *, step: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.step = step


class ConfigError(BuildError):
    """The requested build configuration is not usable."""
