# DSpico Resources Compiler

Automated Docker-based build system for compiling all DSpico components and assembling the SD card structure.

## Prerequisites

1. **Linux or WSL** environment
2. **Docker** installed and running
3. **Blowfish encryption tables** (see below)

## Quick Start

### 1. Obtain Blowfish Tables (REQUIRED)

The bootloader must be encrypted with Nintendo DS Blowfish keys. These can be **legally obtained** from a DS/DSi console you own.

⚠️ **Legal Note:** You must own a physical DS/DSi console to legally possess these files. Downloading them from the internet may violate copyright laws in your jurisdiction.

#### Quick Verification

```bash
# Check if your files are valid
./verify_blowfish.sh

# Try to extract Blowfish from BIOS dumps (if they don't match expected SHA1)
./extract_blowfish.sh inputs/blowfish/biosnds7.rom

# Search for valid Blowfish patterns in large dumps
./find_blowfish.sh inputs/blowfish/biosnds7.rom
```

#### Option A: Use GodMode9 on 3DS (MOST RELIABLE)

If you have a hacked 3DS, this is the best method:

1. Follow https://3ds.hacks.guide/ to install custom firmware
2. Boot GodMode9
3. Navigate to `[M:] MEMORY VIRTUAL`
4. Dump `boot9.bin`
5. Extract with https://github.com/d0k3/boot9strap/releases (boot9_prot extractor)
6. Use the extracted ARM7 BIOS

#### Option B: Extract from BIOS dumps

Place your BIOS files in `inputs/blowfish/`:
- `biosnds7.rom` - DS ARM7 BIOS (16 KB, SHA1: `24f67bdea115a2c847c8813a262502ee1607b7df`)
- `biosdsi7.rom` - DSi ARM7 BIOS (64 KB, SHA1: `c7c7570bfe51c3c7c5da3b01331b94e7e7cb4f53`)

**OR** the extracted Blowfish tables:
- `ntrBlowfish.bin` (4256 bytes, SHA1: `84e467f2485078e401a17a5f231e3fe6e9686648`)
- `twlBlowfish.bin` (4096 bytes, SHA1: `2dea11191f28c6cc1956dadb8941affd4b2b5102`)

#### Option C: Use extracted files (if SHA1 doesn't match)

If your BIOS dumps don't match expected SHA1, **the build may still work**. DSRomEncryptor will attempt to use the files anyway. You can proceed and see if the firmware boots on real hardware.

**Setup:**
```bash
mkdir -p inputs/blowfish
cp /path/to/biosnds7.rom inputs/blowfish/  # 16 KB or larger
cp /path/to/biosdsi7.rom inputs/blowfish/  # 64 KB (optional, for DSi)
```

### 2. Build All Components

```bash
./build_resources.sh
```

This will:
1. Build Docker image with all dependencies
2. Compile DLDI driver
3. Build and patch bootloader
4. Encrypt bootloader with Blowfish keys
5. Compile firmware (`.uf2` for Raspberry Pi Pico)
6. Build Pico Loader
7. Build Pico Launcher
8. Assemble SD card structure in `outputs/dspico/sd_card/`

### 3. Optional: Enable WRFUxxed Exploit

WRFUxxed allows booting DSpico on **unmodified DSi and 3DS** systems.

**How to obtain WRFU Tester v0.60:**

The WRFU Tester ROM is created by Gericom and is distributed as part of the WRFUxxed exploit. You can find it through the DSi homebrew community:

1. Go to the [DS(i) Mode Hacking](https://discord.gg/yD3spjv) Discord server or the [DSpico Discord](https://discord.gg/dspico)
2. Look for `wrfu_tester_v060.nds` in the resources/releases channels
3. Verify SHA-1: `2d65fb7a0c62a4f08954b98c95f42b804fccfd26`

**Setup:**
```bash
mkdir -p inputs/wrfuxxed
cp /path/to/wrfu_tester_v060.nds inputs/wrfuxxed/dsimode.nds
```

**Build with WRFUxxed:**
```bash
ENABLE_WRFUXXED=1 ./build_resources.sh
```

The `uartBufv060.bin` file will be automatically generated during the build process.

### 4. Optional: Enable ntrboot (DSi / 3DS CFW install)

ntrboot allows using DSpico as a **ntrboot flashcart** to install custom firmware ([boot9strap](https://3ds.hacks.guide/) on 3DS, or [Unlaunch](https://dsi.cfw.guide/) on DSi) **without any pre-existing software modification** on the target console.

The LNH-team firmware has **2 ROM slots** (`default.nds` + `dsimode.nds`), so the build system produces **separate firmware files** for each ntrboot variant: `DSpico_ntrboot_3ds.uf2` and `DSpico_ntrboot_dsi.uf2`. Flash the one you need when using ntrboot, then flash the normal `DSpico.uf2` back for regular use.

#### Required ntrboot files

| File | Destination | Description |
|------|-------------|-------------|
<<<<<<< Updated upstream
| 3DS ntrboot ROM | `inputs/ntrboot/default.nds` | **Required.** NDS ROM with header + NTR blowfish keys + boot9strap firm. |
| DSi ntrboot ROM (GCD) | `inputs/ntrboot/dsimode.nds` | **Optional.** GCD-signed NDS ROM with GCD blowfish keys. Only needed for DSi ntrboot. |

#### How to obtain the ntrboot ROMs

**3DS ntrboot ROM (`default.nds`):**

This is a specially crafted NDS ROM containing the boot9strap payload. The ROM consists of a header, NTR blowfish keys, and the boot9strap firm.

1. Download `boot9strap_ntr.zip` from the [boot9strap releases](https://github.com/SciresM/boot9strap/releases) (contains `boot9strap_ntr.firm`)
2. The firm must be packed into the NDS format that DSpico expects (header + blowfish keys + firm). Check the [dspico-firmware](https://github.com/LNH-team/dspico-firmware) repository or the [DSpico Discord](https://discord.gg/dspico) for:
   - A pre-built ntrboot NDS ROM ready for DSpico
   - Or a tool/instructions to build it from `boot9strap_ntr.firm`
3. The [3DS Hacks Guide ntrboot page](https://3ds.hacks.guide/ntrboot) has general information about the ntrboot process

**DSi ntrboot ROM (`dsimode.nds`):**

This is a GCD (Game Card Developer) signed NDS ROM used for the DSi ntrboot exploit. It is more specialized than the 3DS variant.

1. The ROM must contain **GCD blowfish keys** and be **properly signed**
2. Check the [DSpico Discord](https://discord.gg/dspico) or the [DS(i) Mode Hacking](https://discord.gg/yD3spjv) Discord for pre-built GCD ROMs compatible with DSpico
3. The [DSi CFW Guide](https://dsi.cfw.guide/) has general information about DSi exploits

> ⚠️ **DSi ntrboot requires USB power:** The DSpico must be powered via USB (e.g., connected to a PC or USB charger) so the firmware boots **before** the DSi starts its ntrboot sequence. Without external power, the firmware does not boot fast enough.
=======
| `boot9strap_ntr.firm` | `inputs/ntrboot/boot9strap_ntr.firm` | **3DS ntrboot.** Raw FIRM placed into the `default.nds` slot → separate `DSpico_ntrboot_3ds.uf2`. |
| `default.gcd` | `inputs/ntrboot/default.gcd` | **DSi ntrboot.** GCD-signed ROM placed into the `default.nds` slot → separate `DSpico_ntrboot_dsi.uf2`. |

> Each ntrboot variant is built as a **separate firmware** since only 2 ROM slots are available. The ntrboot file is copied directly into `roms/default.nds` — no encryption needed.

#### How to obtain the files

**3DS — `boot9strap_ntr.firm`:**
1. Download `boot9strap_ntr.zip` from [boot9strap releases](https://github.com/SciresM/boot9strap/releases) (**v1.3** — not v1.4, as per [3ds.hacks.guide](https://3ds.hacks.guide/))
2. Extract `boot9strap_ntr.firm` from the zip
3. SHA1: `26bf0b603ec1c72fa648b27c5d547de05d447748`

**DSi — `default.gcd`:**
1. Check the [DSpico Discord](https://discord.gg/dspico) or the [DS(i) Mode Hacking](https://discord.gg/yD3spjv) Discord
2. SHA1: `eca89918bbff86090a43e67f2805d9743e2ac343`

> ⚠️ **DSi ntrboot requires USB power:** The DSpico must be powered via USB (e.g., connected to a PC or USB charger) so the firmware boots **before** the DSi starts its ntrboot sequence.
>>>>>>> Stashed changes

#### ntrboot setup and build

```bash
mkdir -p inputs/ntrboot
<<<<<<< Updated upstream
cp /path/to/your/3ds_ntrboot.nds inputs/ntrboot/default.nds
cp /path/to/your/dsi_gcd_rom.nds inputs/ntrboot/dsimode.nds  # optional, for DSi
=======

# 3DS ntrboot
cp /path/to/boot9strap_ntr.firm inputs/ntrboot/

# DSi ntrboot (optional)
cp /path/to/default.gcd inputs/ntrboot/
>>>>>>> Stashed changes
```

**Build with everything (recommended):**
```bash
ENABLE_WRFUXXED=1 ENABLE_NTRBOOT=1 ./build_resources.sh
```

This produces:
- `outputs/dspico/firmware/DSpico.uf2` — Normal firmware (bootloader + WRFUxxed)
- `outputs/dspico/firmware/DSpico_ntrboot_3ds.uf2` — 3DS ntrboot firmware
- `outputs/dspico/firmware/DSpico_ntrboot_dsi.uf2` — DSi ntrboot firmware

## Output Structure

After building, you'll find:

```
outputs/dspico/
├── bootloader/
│   └── BOOTLOADER.nds          # DLDI-patched bootloader
├── dldi/
│   └── DSpico.dldi             # DLDI driver
├── encryptor/
│   └── default.nds             # Encrypted bootloader
├── firmware/
│   ├── DSpico.uf2              # ⭐ Normal firmware (bootloader + WRFUxxed)
│   ├── DSpico_ntrboot_3ds.uf2  # 3DS ntrboot (if ENABLE_NTRBOOT=1)
│   └── DSpico_ntrboot_dsi.uf2  # DSi ntrboot (if ENABLE_NTRBOOT=1)
├── pico-loader/
│   ├── picoLoader7.bin
│   ├── picoLoader9_DSPICO.bin
│   ├── aplist.bin
│   ├── savelist.bin
│   └── patchlist.bin
├── pico-launcher/
│   ├── LAUNCHER.nds
│   └── _pico/                  # Theme files
├── wrfuxxed/                   # (if ENABLE_WRFUXXED=1)
│   └── uartBufv060.bin
└── sd_card/                    # ⭐ READY TO COPY TO SD CARD
    ├── _picoboot.nds
    └── _pico/
        ├── themes/
        ├── picoLoader7.bin
        ├── picoLoader9.bin
        ├── aplist.bin
        └── savelist.bin
```

> With `ENABLE_NTRBOOT=1`, separate ntrboot `.uf2` files are produced for 3DS and DSi. Flash the appropriate one when using ntrboot, then flash `DSpico.uf2` back for normal use.

## Usage

### Flash the Firmware to DSpico

1. Connect DSpico to PC while holding BOOTSEL button
2. Copy `outputs/dspico/firmware/DSpico.uf2` to the USB drive that appears
3. DSpico will reboot with new firmware

### Prepare SD Card

1. Format your microSD card (FAT32, 32KB cluster size recommended)
   - **DO NOT use Windows built-in formatter**
   - Use: https://dsi.cfw.guide/sd-card-setup.html

2. Copy SD card contents:
```bash
cp -r outputs/dspico/sd_card/* /path/to/your/sdcard/
```

3. Add your DS ROMs:
```bash
mkdir /path/to/your/sdcard/roms
cp /path/to/your/games/*.nds /path/to/your/sdcard/roms/
```

### Boot DSpico

1. Insert microSD into DSpico
2. Insert DSpico into your DS/DSi/3DS
3. Power on

**On DS Lite / DS Phat:**
- Launch DSpico from menu

**On DSi/3DS with WRFUxxed:**
- Pico Launcher will auto-boot after exploit runs

### Use ntrboot to install CFW

If you built with `ENABLE_NTRBOOT=1`:

1. **For 3DS:** Flash `DSpico_ntrboot_3ds.uf2` to DSpico, then follow the [ntrboot section of 3ds.hacks.guide](https://3ds.hacks.guide/ntrboot)
2. **For DSi:** Flash `DSpico_ntrboot_dsi.uf2` to DSpico, connect to USB power before powering on the DSi, then follow [dsi.cfw.guide](https://dsi.cfw.guide/)
3. Once CFW is installed, flash `DSpico.uf2` back to restore normal firmware for games

## All Input Files Summary

Complete reference of all files you may need to provide:

| File | Destination | Required? | Description |
|------|-------------|-----------|-------------|
| DS ARM7 BIOS | `inputs/blowfish/biosnds7.rom` | **Yes** (or `ntrBlowfish.bin`) | 16 KB, for bootloader encryption |
| DSi ARM7 BIOS | `inputs/blowfish/biosdsi7.rom` | Recommended | 64 KB, for TWL blowfish keys |
| NTR Blowfish | `inputs/blowfish/ntrBlowfish.bin` | Alt. to BIOS | 4256 bytes, extracted blowfish table |
| TWL Blowfish | `inputs/blowfish/twlBlowfish.bin` | Alt. to BIOS | 4096 bytes, extracted blowfish table |
| WRFU Tester v0.60 | `inputs/wrfuxxed/dsimode.nds` | If `ENABLE_WRFUXXED=1` | WRFUxxed exploit ROM |
<<<<<<< Updated upstream
| 3DS ntrboot ROM | `inputs/ntrboot/default.nds` | If `ENABLE_NTRBOOT=1` | boot9strap payload in NDS format |
| DSi ntrboot ROM | `inputs/ntrboot/dsimode.nds` | Optional | GCD-signed ROM for DSi ntrboot |
=======
| boot9strap NTR FIRM | `inputs/ntrboot/boot9strap_ntr.firm` | If `ENABLE_NTRBOOT=1` (3DS) | Raw FIRM, copied as-is into firmware |
| DSi ntrboot GCD ROM | `inputs/ntrboot/default.gcd` | If `ENABLE_NTRBOOT=1` (DSi) | GCD-signed ROM, copied as-is into firmware |
>>>>>>> Stashed changes

## Troubleshooting

### ❌ "Blowfish tables not found"
- Make sure `biosnds7.rom` or `ntrBlowfish.bin` is in `inputs/blowfish/`
- These must be extracted from a DS/DSi console you own

### ❌ "No .dldi file produced"
- Check Docker logs for compilation errors
- Ensure BlocksDS tools are installed in Docker image

### ❌ "Firmware compilation failed"
- Verify `default.nds` was created in `outputs/dspico/encryptor/`
- Check that Blowfish encryption succeeded

### ❌ DSpico not detected by console
- Bootloader may not be properly encrypted
- Verify you used correct Blowfish keys
- Try rebuilding firmware in `RelWithDebInfo` mode

### ❌ ntrboot not working on DSi
- DSpico **must be powered via USB** — the firmware needs to boot before the DSi starts its ntrboot sequence
- Verify `inputs/ntrboot/default.gcd` is a properly signed GCD ROM
- Verify SHA1: `eca89918bbff86090a43e67f2805d9743e2ac343`

### ❌ ntrboot not working on 3DS
<<<<<<< Updated upstream
- Verify `inputs/ntrboot/default.nds` contains the correct ntrboot payload (header + blowfish keys + firm)
- Try re-downloading the boot9strap ntr release
=======
- Make sure you have `boot9strap_ntr.firm` (the **NTR** variant, not regular `boot9strap.firm`)
- Use **v1.3** from [boot9strap releases](https://github.com/SciresM/boot9strap/releases) (not v1.4)
- Verify SHA1: `26bf0b603ec1c72fa648b27c5d547de05d447748`
- The file must be at `inputs/ntrboot/boot9strap_ntr.firm`
>>>>>>> Stashed changes

### ❌ "Failed to mount SD card" (blue screen)
- SD card may be corrupted or incompatible
- Reformat using proper tool (see SD card setup guide)
- Try a different SD card

### ❌ "Failed to open Pico Loader" (red screen)
- Check that `_pico/picoLoader7.bin` and `_pico/picoLoader9.bin` exist
- Verify SD card structure matches expected layout

## Advanced Configuration

### Custom Input/Output Directories

```bash
./build_resources.sh /path/to/inputs /path/to/outputs
```

### Docker Image Name

```bash
IMAGE_NAME=my-dspico-compiler:v1 ./build_resources.sh
```

### Environment Variables

```bash
DLDITOOL=/custom/path/to/dlditool \
ENABLE_WRFUXXED=1 \
ENABLE_NTRBOOT=1 \
IMAGE_NAME=custom:latest \
./build_resources.sh
```

> `ENABLE_WRFUXXED` and `ENABLE_NTRBOOT` can be combined. Both flags are additive.

## Components Built

This script automatically clones and builds:

1. [dspico-dldi](https://github.com/LNH-team/dspico-dldi) - DLDI driver
2. [dspico-bootloader](https://github.com/LNH-team/dspico-bootloader) - Cartridge bootloader
3. [DSRomEncryptor](https://github.com/Gericom/DSRomEncryptor) - ROM encryption tool
4. [dspico-wrfuxxed](https://github.com/LNH-team/dspico-wrfuxxed) - DSi/3DS exploit (optional)
5. [dspico-firmware](https://github.com/LNH-team/dspico-firmware) - Raspberry Pi Pico firmware
6. [pico-loader](https://github.com/LNH-team/pico-loader) - Game loader
7. [pico-launcher](https://github.com/LNH-team/pico-launcher) - UI launcher

## License

Each component has its own license. Please check individual repositories.

## Credits

- LNH-team for DSpico hardware and software
- Gericom for DSRomEncryptor and WRFUxxed exploit
- BlocksDS team for development tools
