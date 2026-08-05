"""ROM padding and ntrboot slot assignment.

The shell version padded with `truncate -s 32768`, which would have SHORTENED a
larger ROM had its size guard ever been wrong. The property test below makes that
failure mode impossible rather than merely unlikely.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dspico.pipeline.rom import (
    SECURE_AREA_END,
    SOURCE_3DS,
    SOURCE_DSI,
    NtrbootSlots,
    needs_padding,
    ntrboot_slots,
    ntrboot_variants,
    pad_rom,
)


def test_constants_are_pinned() -> None:
    # Against the literals: comparing a value to the constant it came from
    # mutates on both sides and would leave that mutant alive.
    assert SECURE_AREA_END == 0x8000 == 32768
    assert SOURCE_3DS == "3ds"
    assert SOURCE_DSI == "dsi"


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, True),
        (1, True),
        (SECURE_AREA_END - 1, True),
        (SECURE_AREA_END, False),
        (SECURE_AREA_END + 1, False),
        (1 << 20, False),
    ],
)
def test_needs_padding_boundary(size: int, expected: bool) -> None:
    # DSRomEncryptor writes test patterns at 0x3000-0x3FFF and processes the
    # secure area at 0x4000-0x8000, so 0x8000 is the exact threshold.
    assert needs_padding(size) is expected


def test_needs_padding_rejects_a_negative_size() -> None:
    with pytest.raises(ValueError, match="negative"):
        needs_padding(-1)


def test_pad_rom_extends_a_short_rom_with_zeros() -> None:
    padded = pad_rom(b"\xff" * 16)
    assert len(padded) == SECURE_AREA_END
    assert padded[:16] == b"\xff" * 16
    assert padded[16:] == bytes(SECURE_AREA_END - 16)


def test_pad_rom_leaves_a_large_rom_untouched() -> None:
    data = b"\xab" * (SECURE_AREA_END + 512)
    assert pad_rom(data) is data


def test_pad_rom_leaves_an_exact_size_rom_untouched() -> None:
    data = b"\xcd" * SECURE_AREA_END
    assert pad_rom(data) is data


@given(st.binary(max_size=SECURE_AREA_END * 2))
def test_pad_rom_never_truncates(data: bytes) -> None:
    padded = pad_rom(data)
    assert len(padded) >= SECURE_AREA_END
    assert len(padded) >= len(data)
    assert padded.startswith(data)


@pytest.mark.parametrize(
    ("has_3ds", "has_dsi", "expected"),
    [
        (True, True, NtrbootSlots(SOURCE_3DS, SOURCE_DSI)),
        (True, False, NtrbootSlots(SOURCE_3DS, None)),
        (False, True, NtrbootSlots(SOURCE_DSI, None)),
        (False, False, NtrbootSlots(None, None)),
    ],
)
def test_ntrboot_slots_covers_every_combination(
    has_3ds: bool, has_dsi: bool, expected: NtrbootSlots
) -> None:
    # With only one source available it goes in the primary slot, whichever it is.
    assert ntrboot_slots(has_3ds=has_3ds, has_dsi=has_dsi) == expected


@pytest.mark.parametrize(
    ("has_3ds", "has_dsi", "expected"),
    [
        (True, True, (SOURCE_3DS, SOURCE_DSI)),
        (True, False, (SOURCE_3DS,)),
        (False, True, (SOURCE_DSI,)),
        (False, False, ()),
    ],
)
def test_ntrboot_variants_covers_every_combination(
    has_3ds: bool, has_dsi: bool, expected: tuple[str, ...]
) -> None:
    # LNH firmware has 2 slots only, so each available source needs its own build.
    assert ntrboot_variants(has_3ds=has_3ds, has_dsi=has_dsi) == expected


def test_slots_are_frozen() -> None:
    slots = NtrbootSlots(SOURCE_3DS, SOURCE_DSI)
    with pytest.raises(AttributeError):
        slots.ntrboot_nds = SOURCE_DSI  # type: ignore[misc]
