"""ROM-level decisions: how much padding, and which ROM goes in which slot."""

from dataclasses import dataclass

SECURE_AREA_END = 0x8000
"""DSRomEncryptor writes test patterns at 0x3000-0x3FFF and processes the secure
area at 0x4000-0x8000, so a shorter ROM must be padded before encryption."""

SOURCE_3DS = "3ds"
SOURCE_DSI = "dsi"


def needs_padding(size: int) -> bool:
    """Whether a ROM of this size is too short for DSRomEncryptor."""
    if size < 0:
        raise ValueError(f"ROM size cannot be negative: {size}")
    return size < SECURE_AREA_END


def pad_rom(data: bytes) -> bytes:
    """Zero-pad up to the secure-area end, never shortening the input.

    Returns the original object untouched when it is already long enough, so a
    caller can cheaply tell whether padding happened.

    Defers the threshold comparison to ``needs_padding`` rather than repeating
    it. Duplicating it here left a boundary mutant (``>=`` to ``>``) that no test
    could kill: at exactly ``SECURE_AREA_END`` the mutated branch falls through
    to ``data + bytes(0)``, which CPython returns as the very same object.
    """
    if needs_padding(len(data)):
        return data + bytes(SECURE_AREA_END - len(data))
    return data


@dataclass(frozen=True)
class NtrbootSlots:
    """Which ntrboot source lands in which firmware ROM slot.

    ``None`` means the slot is unused. Applies to the edo9300 fork, which has
    dedicated ``ntrboot.nds`` and ``ntrbootdsi.nds`` slots.
    """

    ntrboot_nds: str | None
    ntrbootdsi_nds: str | None


def ntrboot_slots(*, has_3ds: bool, has_dsi: bool) -> NtrbootSlots:
    """Assign available ntrboot sources to the edo9300 firmware's slots.

    With both present, 3DS takes the primary slot and DSi the secondary. With
    only one, it takes the primary slot whichever it is.
    """
    if has_3ds and has_dsi:
        return NtrbootSlots(SOURCE_3DS, SOURCE_DSI)
    if has_3ds:
        return NtrbootSlots(SOURCE_3DS, None)
    if has_dsi:
        return NtrbootSlots(SOURCE_DSI, None)
    return NtrbootSlots(None, None)


def ntrboot_variants(*, has_3ds: bool, has_dsi: bool) -> tuple[str, ...]:
    """The separate firmware builds LNH-team firmware needs for ntrboot.

    That firmware exposes only 2 ROM slots, both already taken by the bootloader
    and WRFUxxed, so every ntrboot source requires its own full build.
    """
    variants: list[str] = []
    if has_3ds:
        variants.append(SOURCE_3DS)
    if has_dsi:
        variants.append(SOURCE_DSI)
    return tuple(variants)
