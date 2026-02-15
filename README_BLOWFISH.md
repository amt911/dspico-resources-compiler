# Obtaining Blowfish Tables

## The Problem

DSRomEncryptor needs **exact** NTR Blowfish keys to encrypt the bootloader. Your BIOS dumps don't match the expected SHA1 hashes, which means:

1. They may be from no$gba debugger (includes extra data)
2. They may be incomplete/corrupted dumps
3. They may be from different firmware versions

## Solutions

### Option 1: Use the Extraction Scripts (Recommended)

Even if SHA1 doesn't match, the extracted Blowfish tables might work:

```bash
# Check what you have
./verify_blowfish.sh

# Extract from your BIOS dumps
./extract_blowfish.sh inputs/blowfish/biosnds7.rom
./extract_blowfish.sh inputs/blowfish/biosdsi7.rom

# Verify extracted files
./verify_blowfish.sh
```

If the extracted `ntrBlowfish.bin` has SHA1 `84e467f2485078e401a17a5f231e3fe6e9686648`, you're good!

### Option 2: Use GodMode9 on 3DS (Most Reliable)

If you have a hacked 3DS, this gives perfect dumps:

1. Follow https://3ds.hacks.guide/ to install custom firmware
2. Use GodMode9 to dump BIOS:
   - Navigate to `[M:] MEMORY VIRTUAL`
   - Find `boot9.bin` and dump it
   - Extract NTR/TWL Blowfish from boot9.bin

### Option 3: Manual Extraction from Full BIOS

Your `biosnds7.rom` is 256KB (full BIOS dump from no$gba or similar).

The NTR BIOS (ARM7) should be at a specific offset. Try:

```bash
# Check your file
hexdump -C inputs/blowfish/biosnds7.rom | head -20

# If it starts with 0x00000000 and contains ARM code, try:
dd if=inputs/blowfish/biosnds7.rom of=inputs/blowfish/biosnds7_extracted.rom bs=1 skip=0 count=16384
sha1sum inputs/blowfish/biosnds7_extracted.rom
```

Expected SHA1: `24f67bdea115a2c847c8813a262502ee1607b7df`

### Option 4: Use Pre-Verified Sources

If you have access to:
- A DS flashcart with homebrew capability
- A 3DS with custom firmware
- No$gba debugger (can dump BIOS)

Use these tools to dump clean BIOS files.

## File Requirements

### For DS (NTR) Games - REQUIRED
- `biosnds7.rom` (16 KB, SHA1: `24f67bdea115a2c847c8813a262502ee1607b7df`)
- OR `ntrBlowfish.bin` (4256 bytes, SHA1: `84e467f2485078e401a17a5f231e3fe6e9686648`)

### For DSi (TWL) Games - Optional
- `biosdsi7.rom` (64 KB, SHA1: `c7c7570bfe51c3c7c5da3b01331b94e7e7cb4f53`)
- OR `twlBlowfish.bin` (4096 bytes, SHA1: `2dea11191f28c6cc1956dadb8941affd4b2b5102`)

## Current Status

Run `./verify_blowfish.sh` to see what files you have and their validity.

## Why This Matters

The Blowfish keys encrypt the "Secure Area" (0x4000-0x4800) of DS ROMs. Without correct encryption:
- The bootloader won't boot on real hardware
- Your DSpico won't be recognized by the console
- You'll get errors or hangs at the DS splash screen

## Legal Notice

You must own physical DS/DSi/3DS hardware to legally possess BIOS files. These files are copyrighted by Nintendo.
