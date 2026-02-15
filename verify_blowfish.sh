#!/bin/bash

echo "=== Blowfish Files Verification ==="
echo ""

BLOWFISH_DIR="inputs/blowfish"

if [ ! -d "$BLOWFISH_DIR" ]; then
    echo "❌ Directory $BLOWFISH_DIR does not exist"
    echo "   Run: mkdir -p $BLOWFISH_DIR"
    exit 1
fi

echo "Checking files in $BLOWFISH_DIR..."
echo ""

# Expected SHA1 hashes
NTR_BIOS_SHA1="24f67bdea115a2c847c8813a262502ee1607b7df"
DSI_BIOS_SHA1_INCOMPLETE="a3aa751eb6bdaaf8a827ba9e03576a6f1ab0f547"
DSI_BIOS_SHA1_COMPLETE="c7c7570bfe51c3c7c5da3b01331b94e7e7cb4f53"
NTR_BLOWFISH_SHA1="84e467f2485078e401a17a5f231e3fe6e9686648"
TWL_BLOWFISH_SHA1="2dea11191f28c6cc1956dadb8941affd4b2b5102"

check_file() {
    local file="$1"
    local expected_sha1="$2"
    local expected_sha1_alt="$3"
    local name="$4"
    
    if [ -f "$file" ]; then
        actual_sha1=$(sha1sum "$file" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')
        echo "📄 $name"
        echo "   File: $file"
        echo "   SHA1: $actual_sha1"
        
        if [ "$actual_sha1" = "$expected_sha1" ] || [ -n "$expected_sha1_alt" -a "$actual_sha1" = "$expected_sha1_alt" ]; then
            echo "   ✅ Valid!"
        else
            echo "   ❌ Invalid SHA1!"
            echo "   Expected: $expected_sha1"
            [ -n "$expected_sha1_alt" ] && echo "   Or:       $expected_sha1_alt"
        fi
        echo ""
        return 0
    else
        echo "⚠️  $name not found: $file"
        echo ""
        return 1
    fi
}

# Check NTR blowfish
has_ntr=false
check_file "$BLOWFISH_DIR/biosnds7.rom" "$NTR_BIOS_SHA1" "" "NDS ARM7 BIOS" && has_ntr=true
check_file "$BLOWFISH_DIR/ntrBlowfish.bin" "$NTR_BLOWFISH_SHA1" "" "NTR Blowfish Table" && has_ntr=true

# Check TWL blowfish (optional)
has_twl=false
check_file "$BLOWFISH_DIR/biosdsi7.rom" "$DSI_BIOS_SHA1_COMPLETE" "$DSI_BIOS_SHA1_INCOMPLETE" "DSi ARM7 BIOS" && has_twl=true
check_file "$BLOWFISH_DIR/twlBlowfish.bin" "$TWL_BLOWFISH_SHA1" "" "TWL Blowfish Table" && has_twl=true

echo "=== Summary ==="
if $has_ntr; then
    echo "✅ NTR Blowfish: Ready"
else
    echo "❌ NTR Blowfish: MISSING (REQUIRED for DS roms)"
fi

if $has_twl; then
    echo "✅ TWL Blowfish: Ready"
else
    echo "⚠️  TWL Blowfish: Missing (needed for DSi-enhanced/exclusive roms)"
fi

echo ""
echo "=== Recommendations ==="
if ! $has_ntr; then
    echo "You need NTR blowfish to encrypt the bootloader."
    echo ""
    echo "Option 1: Extract from your DS/DSi BIOS dump"
    echo "  - Your biosnds7.rom must have SHA1: $NTR_BIOS_SHA1"
    echo "  - If SHA1 doesn't match, your dump may be corrupted or modified"
    echo ""
    echo "Option 2: Use a BIOS extraction tool"
    echo "  - Use GodMode9 on 3DS: https://3ds.hacks.guide/"
    echo "  - Use no\$gba debugger to dump BIOS from flashcard"
    echo ""
    echo "Option 3: Manually extract ntrBlowfish.bin"
    echo "  - Extract bytes 0x30-0x10CF from biosnds7.rom"
    echo "  - Save as ntrBlowfish.bin (4256 bytes)"
fi
