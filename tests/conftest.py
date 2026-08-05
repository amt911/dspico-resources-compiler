"""Shared test doubles."""

from collections.abc import Sequence

import pytest


class FakeRunner:
    """Records commands instead of running them.

    Every step test asserts against ``calls``, so the suite never needs docker,
    a network, or the toolchain.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.steps: list[str | None] = []

    def run(self, argv: Sequence[str], *, step: str | None = None) -> None:
        self.calls.append(tuple(argv))
        self.steps.append(step)


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()
