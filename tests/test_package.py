"""The package imports cleanly and carries a version. Guards the packaging config."""

import dspico


def test_package_exposes_a_version() -> None:
    assert isinstance(dspico.__version__, str)
    assert dspico.__version__
