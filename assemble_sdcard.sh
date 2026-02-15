#!/bin/sh
set -eu

OUT_BASE=${1:-$(pwd)/outputs/dspico}
SD_DIR="$OUT_BASE/sd_card"

echo "Assembling SD card contents in $SD_DIR"
rm -rf "$SD_DIR"
mkdir -p "$SD_DIR" "$SD_DIR/_pico"

copy_if_exists() {
  if [ -e "$1" ]; then
    cp -v "$1" "$2"
  fi
}

# Copy _pico from pico-launcher if available
if [ -d "$OUT_BASE/pico-launcher/_pico" ]; then
  cp -r "$OUT_BASE/pico-launcher/_pico" "$SD_DIR/_pico"
fi

# Copy pico loader files into _pico
if [ -d "$OUT_BASE/pico-loader" ]; then
  # picoLoader7
  for f in "$OUT_BASE/pico-loader"/picoLoader7*.bin; do
    if [ -e "$f" ]; then
      copy_if_exists "$f" "$SD_DIR/_pico/$(basename "$f")"
    fi
  done
  # picoLoader9 -> normalize to picoLoader9.bin (take first match)
  for f in "$OUT_BASE/pico-loader"/picoLoader9*.bin; do
    if [ -e "$f" ]; then
      copy_if_exists "$f" "$SD_DIR/_pico/picoLoader9.bin"
      break
    fi
  done
  copy_if_exists "$OUT_BASE/pico-loader/data/aplist.bin" "$SD_DIR/_pico/aplist.bin"
  copy_if_exists "$OUT_BASE/pico-loader/data/savelist.bin" "$SD_DIR/_pico/savelist.bin"
  copy_if_exists "$OUT_BASE/pico-loader/data/patchlist.bin" "$SD_DIR/_pico/patchlist.bin"
fi

# Copy LAUNCHER.nds to root as _picoboot.nds
if [ -e "$OUT_BASE/pico-launcher/LAUNCHER.nds" ]; then
  copy_if_exists "$OUT_BASE/pico-launcher/LAUNCHER.nds" "$SD_DIR/_picoboot.nds"
fi

echo "SD card assembly complete: $SD_DIR"
echo " - Root: _picoboot.nds (LAUNCHER.nds)"
echo " - Folder: _pico (pico loader + data)"

echo "If files are missing, run ./build_resources.sh and ensure each component built successfully."
