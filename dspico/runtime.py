"""The single seam between the orchestrator and the outside world.

Everything that spawns a process goes through here, so tests can swap in a
recorder and stay offline. Nothing else in the package imports ``subprocess``.
"""

import shlex
import subprocess
from collections.abc import Callable, Sequence
from typing import Protocol

from dspico.errors import BuildError


class CommandError(BuildError):
    """A command exited non-zero."""

    def __init__(self, argv: Sequence[str], returncode: int, *, step: str | None = None) -> None:
        super().__init__(
            f"command failed with exit code {returncode}: {shlex.join(argv)}", step=step
        )
        self.argv = tuple(argv)
        self.returncode = returncode


def capture(argv: Sequence[str]) -> str:
    """Run a command and return its stdout, stripped.

    Deliberately not part of :class:`Runner`: it is only used to read provenance
    metadata, never to drive the build, and its output is the point rather than
    a side effect.
    """
    completed = subprocess.run(list(argv), check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise CommandError(argv, completed.returncode)
    return completed.stdout.strip()


class Runner(Protocol):
    """Runs a command, raising :class:`CommandError` if it fails."""

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None: ...


class SubprocessRunner:
    """Runs commands for real.

    Echoes each command first so that a failed build can be reproduced by hand
    from the log. ``shlex.join`` quotes POSIX-style even on Windows; that is fine
    because the echo is for humans and the command itself is passed as a list,
    never through a shell.
    """

    def __init__(self, *, echo: Callable[[str], None] = print) -> None:
        self._echo = echo

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        self._echo(f"$ {shlex.join(argv)}")
        completed = subprocess.run(list(argv), check=False)
        if completed.returncode != 0:
            raise CommandError(argv, completed.returncode, step=step)


class DryRunRunner:
    """Echoes commands without running them, for ``--dry-run``.

    Lets a user confirm the exact docker invocation on a new platform without
    paying for a full build.
    """

    def __init__(self, *, echo: Callable[[str], None] = print) -> None:
        self._echo = echo

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        self._echo(f"$ {shlex.join(argv)}")
