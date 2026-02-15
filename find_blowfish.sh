#!/bin/bash

echo "=== Blowfish Pattern Finder ==="
echo ""
echo "This script searches for Blowfish patterns in your BIOS dump"
echo ""

if [ $# -eq 0 ]; then
    echo "Usage: $0 <biosnds7.rom>"
    exit 1
fi

FILE="$1"

if [ ! -f "$FILE" ]; then
    echo "File not found: $FILE"
    exit 1
fi

SIZE=$(stat -c%s "$FILE" 2>/dev/null || stat -f%z "$FILE" 2>/dev/null)
echo "File: $FILE ($SIZE bytes)"
echo ""

# Try different offsets for 256KB dumps
OFFSETS=(0 16384 32768 65536 131072)

for OFFSET in "${OFFSETS[@]}"; do
    if [ $OFFSET -ge $SIZE ]; then
        continue
    fi
    
    echo "Trying offset $OFFSET..."
    dd if="$FILE" of="/tmp/test_ntr.bin" bs=1 skip=$OFFSET count=16384 2>/dev/null
    
    # Extract blowfish from the 16KB chunk
    dd if="/tmp/test_ntr.bin" of="/tmp/test_blowfish.bin" bs=1 skip=48 count=4256 2>/dev/null
    
    SHA1=$(sha1sum "/tmp/test_blowfish.bin" | awk '{print $1}')
    
    if [ "$SHA1" = "84e467f2485078e401a17a5f231e3fe6e9686648" ]; then
        echo "✅ FOUND VALID NTR BLOWFISH AT OFFSET $OFFSET!"
        echo "   Extracting..."
        dd if="$FILE" of="inputs/blowfish/biosnds7_fixed.rom" bs=1 skip=$OFFSET count=16384 2>/dev/null
        dd if="$FILE" of="inputs/blowfish/ntrBlowfish_fixed.bin" bs=1 skip=$((OFFSET + 48)) count=4256 2>/dev/null
        echo "   Created: inputs/blowfish/biosnds7_fixed.rom"
        echo "   Created: inputs/blowfish/ntrBlowfish_fixed.bin"
        rm -f /tmp/test_ntr.bin /tmp/test_blowfish.bin
        exit 0
    else
        echo "   SHA1: $SHA1 (not valid)"
    fi
done

rm -f /tmp/test_ntr.bin /tmp/test_blowfish.bin
echo ""
echo "❌ Could not find valid NTR Blowfish in file"
echo ""
echo "Your BIOS dump may be:"
echo "  - From a different source (melonDS, DeSmuME, etc.)"
echo "  - Modified or encrypted"
echo "  - From no\$gba with proprietary format"
echo ""
echo "Recommended: Use GodMode9 on 3DS or extract from a clean DS/DSi dump"
