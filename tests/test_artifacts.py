"""Artifact discovery. These functions are the pipeline's assertions."""

from pathlib import Path

import pytest

from dspico.errors import BuildError
from dspico.pipeline.artifacts import copy_glob, copy_into, find_artifact, find_artifacts


def _touch(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_finds_a_single_match(tmp_path: Path) -> None:
    wanted = _touch(tmp_path / "build" / "DSpico.dldi")
    assert find_artifact(tmp_path, "*.dldi") == wanted


def test_missing_artifact_raises(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="no file matching"):
        find_artifact(tmp_path, "*.dldi")


def test_ambiguous_artifact_raises(tmp_path: Path) -> None:
    # The shell used `find ... | head -n 1`, which picked one arbitrarily and
    # could ship the wrong binary without a word.
    _touch(tmp_path / "a" / "one.uf2")
    _touch(tmp_path / "b" / "two.uf2")
    with pytest.raises(BuildError, match="ambiguous"):
        find_artifact(tmp_path, "*.uf2")


def test_depth_is_respected(tmp_path: Path) -> None:
    _touch(tmp_path / "a" / "b" / "c" / "deep.bin")
    with pytest.raises(BuildError, match="no file matching"):
        find_artifact(tmp_path, "deep.bin", depth=2)
    assert find_artifact(tmp_path, "deep.bin", depth=4).name == "deep.bin"


def test_find_artifacts_returns_every_match_sorted(tmp_path: Path) -> None:
    _touch(tmp_path / "b.uf2")
    _touch(tmp_path / "a.uf2")
    assert [p.name for p in find_artifacts(tmp_path, "*.uf2")] == ["a.uf2", "b.uf2"]


def test_find_artifacts_may_return_nothing(tmp_path: Path) -> None:
    assert find_artifacts(tmp_path, "*.none") == []


def test_copy_into_returns_the_destination(tmp_path: Path) -> None:
    source = _touch(tmp_path / "src" / "f.bin", "payload")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    copied = copy_into(source, dest_dir)
    assert copied == dest_dir / "f.bin"
    assert copied.read_text(encoding="utf-8") == "payload"


def test_copy_glob_copies_every_match(tmp_path: Path) -> None:
    _touch(tmp_path / "picoLoader7.bin")
    _touch(tmp_path / "picoLoader9e.bin")
    dest = tmp_path / "out"
    dest.mkdir()
    copied = copy_glob(tmp_path, "picoLoader*.bin", dest)
    assert sorted(p.name for p in copied) == ["picoLoader7.bin", "picoLoader9e.bin"]


def test_required_copy_glob_raises_when_nothing_matches(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(BuildError, match="no file matching"):
        copy_glob(tmp_path, "*.missing", dest)


def test_optional_copy_glob_tolerates_no_match(tmp_path: Path) -> None:
    # Only for genuinely optional artifacts, mirroring copy_if_exists.
    dest = tmp_path / "out"
    dest.mkdir()
    assert copy_glob(tmp_path, "*.missing", dest, required=False) == []
