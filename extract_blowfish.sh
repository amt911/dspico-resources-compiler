#!/bin/bash

echo "=== Blowfish Extraction Tool ==="
echo ""

BLOWFISH_DIR="inputs/blowfish"

if [ ! -d "$BLOWFISH_DIR" ]; then
    echo "Creating $BLOWFISH_DIR..."
    mkdir -p "$BLOWFISH_DIR"
fi

# Function to extract NTR blowfish from biosnds7.rom
extract_ntr() {
    local input="$1"
    local output="$BLOWFISH_DIR/ntrBlowfish.bin"
    
    echo "Extracting NTR Blowfish from $input..."
    
    # Extract bytes 0x30-0x10CF (4256 bytes) from biosnds7.rom
    dd if="$input" of="$output" bs=1 skip=48 count=4256 2>/dev/null
    
    if [ $? -eq 0 ]; then
        sha1=$(sha1sum "$output" | awk '{print $1}')
        echo "✅ Created: $output"
        echo "   SHA1: $sha1"
        
        if [ "$sha1" = "84e467f2485078e401a17a5f231e3fe6e9686648" ]; then
            echo "   ✅ Valid NTR Blowfish!"
            return 0
        else
            echo "   ⚠️  SHA1 doesn't match expected (may still work)"
            return 0
        fi
    else
        echo "❌ Failed to extract"
        return 1
    fi
}

# Function to extract TWL blowfish from biosdsi7.rom
extract_twl() {
    local input="$1"
    local output="$BLOWFISH_DIR/twlBlowfish.bin"
    
    echo "Extracting TWL Blowfish from $input..."
    
    # Extract bytes 0x8B8-0x18B7 (4096 bytes) from biosdsi7.rom
    dd if="$input" of="$output" bs=1 skip=2232 count=4096 2>/dev/null
    
    if [ $? -eq 0 ]; then
        sha1=$(sha1sum "$output" | awk '{print $1}')
        echo "✅ Created: $output"
        echo "   SHA1: $sha1"
        
        if [ "$sha1" = "2dea11191f28c6cc1956dadb8941affd4b2b5102" ]; then
            echo "   ✅ Valid TWL Blowfish!"
            return 0
        else
            echo "   ⚠️  SHA1 doesn't match expected (may still work)"
            return 0
        fi
    else
        echo "❌ Failed to extract"
        return 1
    fi
}

# Main logic
if [ $# -eq 0 ]; then
    echo "Usage: $0 <bios_file>"
    echo ""
    echo "This script extracts Blowfish tables from BIOS dumps."
    echo ""
    echo "Examples:"
    echo "  $0 biosnds7.rom     # Extract NTR blowfish from DS BIOS"
    echo "  $0 biosdsi7.rom     # Extract TWL blowfish from DSi BIOS"
    echo ""
    echo "Files in $BLOWFISH_DIR:"
    ls -lh "$BLOWFISH_DIR" 2>/dev/null || echo "  (empty)"
    exit 1
fi

INPUT="$1"

if [ ! -f "$INPUT" ]; then
    echo "❌ File not found: $INPUT"
    exit 1
fi

# Detect file type by size
SIZE=$(stat -c%s "$INPUT" 2>/dev/null || stat -f%z "$INPUT" 2>/dev/null)

echo "File: $INPUT"
echo "Size: $SIZE bytes"
echo ""

if [ "$SIZE" -eq 16384 ]; then
    echo "Detected: NDS ARM7 BIOS (16 KB)"
    extract_ntr "$INPUT"
elif [ "$SIZE" -eq 65536 ] || [ "$SIZE" -eq 65160 ]; then
    echo "Detected: DSi ARM7 BIOS (64 KB)"
    extract_twl "$INPUT"
else
    echo "⚠️  Unknown file size. Trying both extractions..."
    echo ""
    extract_ntr "$INPUT" || true
    echo ""
    extract_twl "$INPUT" || true
fi

echo ""
echo "Done! Run ./verify_blowfish.sh to check results."
