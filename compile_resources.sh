#!/bin/bash
set -eu

# =============================================================================
#  DSpico Resources Compiler
# =============================================================================
#  Builds all DSpico components inside the Docker container.
#
#  Expected mounts:
#    /inputs  (read-only)  - Blowfish tables and optional inputs
#    /outputs              - Build artifacts destination
# =============================================================================

# ─── Configuration ────────────────────────────────────────────────────────────

OUT_BASE=/outputs/dspico
DLDITOOL="${DLDITOOL:-/opt/wonderful/thirdparty/blocksds/core/tools/dlditool/dlditool}"

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# ─── Shared state across build steps ─────────────────────────────────────────

DLDI_FILE=""
BOOTLOADER_NDS=""
ENCRYPTED_NDS=""

# =============================================================================
#  Utility functions
# =============================================================================

error_exit() {
  echo -e "${RED}ERROR: $1${NC}" >&2
  exit 1
}

info()  { echo -e "${GREEN}$1${NC}"; }
warn()  { echo -e "${YELLOW}$1${NC}"; }
step()  { echo -e "\n${GREEN}[$1]${NC} $2"; }

# Clone a git repo into a directory and cd into it.
# Pass --recursive as $3 to also init submodules recursively.
clone_repo() {
  local url="$1" dir="$2"
  rm -rf "$dir"
  if [ "${3:-}" = "--recursive" ]; then
    git clone --recursive "$url" "$dir"
  else
    git clone "$url" "$dir"
  fi
  cd "$dir"
}

# Build with male (wonderful) or fall back to make.
build() {
  if command -v male >/dev/null 2>&1; then
    echo "Building with male..."
    male
  else
    echo "Building with make..."
    make -j"$(nproc)"
  fi
}

# Find a single file matching a pattern; error_exit if not found.
find_artifact() {
  local dir="$1" pattern="$2" depth="${3:-2}"
  local result
  result=$(find "$dir" -maxdepth "$depth" -name "$pattern" -type f | head -n 1)
  [ -n "$result" ] || error_exit "Artifact '$pattern' not found in $dir"
  echo "$result"
}

# Write BUILD_INFO.txt with commit metadata for the component.
write_build_info() {
  local repo_dir="$1" output_dir="$2" component="$3"
  cat > "$output_dir/BUILD_INFO.txt" <<EOF
Component: $component
Commit:    $(git -C "$repo_dir" log -1 --format="%H")
Date:      $(git -C "$repo_dir" log -1 --format="%ai")
Summary:   $(git -C "$repo_dir" log -1 --format="%s")
EOF
}

# Copy files matching a glob pattern (unquoted for expansion).
copy_glob() {
  local pattern="$1" dest="$2"
  for f in $pattern; do
    [ -e "$f" ] && cp -v "$f" "$dest"
  done
}

# Copy a file only if it exists.
copy_if_exists() {
  if [ -e "$1" ]; then
    cp -v "$1" "$2"
  fi
}

# Create the output directory tree.
setup_dirs() {
  local dirs="dldi bootloader encryptor firmware pico-loader pico-launcher wrfuxxed"
  mkdir -p "$OUT_BASE"
  for d in $dirs; do
    mkdir -p "$OUT_BASE/$d"
  done
}

# =============================================================================
#  Build steps
# =============================================================================

# ── [1/9] DLDI driver ────────────────────────────────────────────────────────

step_dldi() {
  local repo=/tmp/dspico-dldi
  step "1/9" "Build DSpico DLDI"

  clone_repo https://github.com/LNH-team/dspico-dldi.git "$repo"
  build

  DLDI_FILE=$(find_artifact "$repo" "*.dldi")
  cp -v "$DLDI_FILE" "$OUT_BASE/dldi/"
  DLDI_FILE="$OUT_BASE/dldi/$(basename "$DLDI_FILE")"

  write_build_info "$repo" "$OUT_BASE/dldi" "dspico-dldi"
  info "✓ DLDI built: $DLDI_FILE"
}

# ── [2/9] Bootloader (+ DLDI patch) ──────────────────────────────────────────

step_bootloader() {
  local repo=/tmp/dspico-bootloader
  step "2/9" "Build DSpico Bootloader"

  clone_repo https://github.com/LNH-team/dspico-bootloader.git "$repo"
  git submodule update --init
  build

  # Try BOOTLOADER.nds first, fall back to any .nds
  BOOTLOADER_NDS=$(find "$repo" -maxdepth 2 -name "BOOTLOADER.nds" -type f | head -n 1)
  [ -n "$BOOTLOADER_NDS" ] || \
    BOOTLOADER_NDS=$(find "$repo" -maxdepth 2 -name "*.nds" -type f | head -n 1)
  [ -n "$BOOTLOADER_NDS" ] || error_exit "No bootloader .nds file produced"

  [ -x "$DLDITOOL" ] || error_exit "DLDITOOL not found at: $DLDITOOL"
  "$DLDITOOL" "$DLDI_FILE" "$BOOTLOADER_NDS" || error_exit "DLDI patch failed on bootloader"

  cp -v "$BOOTLOADER_NDS" "$OUT_BASE/bootloader/"
  write_build_info "$repo" "$OUT_BASE/bootloader" "dspico-bootloader"
  info "✓ Bootloader built and patched"
}

# ── [3/9] DSRomEncryptor (encrypt bootloader) ────────────────────────────────

step_encryptor() {
  local repo=/tmp/DSRomEncryptor
  local bin_dir="$repo/DSRomEncryptor/bin/Debug/net9.0"
  step "3/9" "Build DSRomEncryptor"

  clone_repo https://github.com/Gericom/DSRomEncryptor "$repo"
  dotnet build -c Debug || error_exit "DSRomEncryptor build failed"
  [ -d "$bin_dir" ] || error_exit "Build output not found at $bin_dir"

  # Copy Blowfish tables from inputs
  if [ -d /inputs/blowfish ]; then
    echo "Copying Blowfish tables..."
    for f in /inputs/blowfish/*; do
      [ -f "$f" ] && cp -v "$f" "$bin_dir/" || true
    done
  fi

  # Validate Blowfish availability
  local ntr_ok=0 twl_ok=0
  if [ -f "$bin_dir/ntrBlowfish.bin" ] || [ -f "$bin_dir/biosnds7.rom" ]; then
    ntr_ok=1
  fi
  if [ -f "$bin_dir/twlBlowfish.bin" ] || [ -f "$bin_dir/biosdsi7.rom" ]; then
    twl_ok=1
  fi
  [ "$ntr_ok" -eq 1 ] || error_exit "NTR Blowfish not found (need ntrBlowfish.bin or biosnds7.rom in inputs/blowfish/)"
  [ "$twl_ok" -eq 1 ] || warn "⚠ TWL Blowfish not found (twlBlowfish.bin or biosdsi7.rom)"

  # Encrypt bootloader
  ENCRYPTED_NDS="$repo/default.nds"
  if [ -f "$bin_dir/DSRomEncryptor" ]; then
    "$bin_dir/DSRomEncryptor" "$BOOTLOADER_NDS" "$ENCRYPTED_NDS" || error_exit "Encryption failed"
  elif [ -f "$bin_dir/DSRomEncryptor.dll" ]; then
    dotnet "$bin_dir/DSRomEncryptor.dll" "$BOOTLOADER_NDS" "$ENCRYPTED_NDS" || error_exit "Encryption failed"
  else
    error_exit "DSRomEncryptor executable not found in $bin_dir"
  fi

  [ -f "$ENCRYPTED_NDS" ] || error_exit "default.nds was not created"
  cp -v "$ENCRYPTED_NDS" "$OUT_BASE/encryptor/"

  write_build_info "$repo" "$OUT_BASE/encryptor" "DSRomEncryptor"
  info "✓ Bootloader encrypted"
}

# ── [4/9] WRFUxxed (optional) ────────────────────────────────────────────────

step_wrfuxxed() {
  step "4/9" "Build WRFUxxed (optional)"

  if [ "${ENABLE_WRFUXXED:-0}" != "1" ]; then
    warn "⊗ Skipped (set ENABLE_WRFUXXED=1 to enable)"
    return
  fi

  local repo=/tmp/dspico-wrfuxxed
  clone_repo https://github.com/LNH-team/dspico-wrfuxxed "$repo"
  build

  local wrf_bin
  wrf_bin=$(find_artifact "$repo" "uartBufv060.bin")
  "$DLDITOOL" "$DLDI_FILE" "$wrf_bin" || error_exit "DLDI patch failed on wrfuxxed"

  cp -v "$wrf_bin" "$OUT_BASE/wrfuxxed/"
  write_build_info "$repo" "$OUT_BASE/wrfuxxed" "dspico-wrfuxxed"
  info "✓ WRFUxxed built and patched"
}

# ── [5/9] Firmware ────────────────────────────────────────────────────────────

step_firmware() {
  local repo=/tmp/dspico-firmware
  step "5/9" "Build DSpico Firmware"

  clone_repo https://github.com/LNH-team/dspico-firmware "$repo"
  git submodule update --init
  (cd pico-sdk && git submodule update --init)

  # Inject encrypted bootloader
  [ -f "$ENCRYPTED_NDS" ] || error_exit "default.nds not available"
  cp -v "$ENCRYPTED_NDS" "$repo/roms/default.nds"

  # WRFUxxed integration
  if [ "${ENABLE_WRFUXXED:-0}" = "1" ]; then
    if [ -f /inputs/wrfuxxed/dsimode.nds ]; then
      cp -v /inputs/wrfuxxed/dsimode.nds "$repo/roms/dsimode.nds"
    else
      warn "⚠ /inputs/wrfuxxed/dsimode.nds not found"
    fi
    copy_if_exists /tmp/dspico-wrfuxxed/uartBufv060.bin "$repo/data/uartBufv060.bin"
    sed -i 's/^#\s*\(.*DSPICO_ENABLE_WRFUXXED.*\)/\1/' CMakeLists.txt || true
  fi

  chmod +x compile.sh
  ./compile.sh || error_exit "Firmware compilation failed"

  find_artifact "$repo/build" "*.uf2" >/dev/null
  copy_glob "$repo/build/*.uf2" "$OUT_BASE/firmware/"

  write_build_info "$repo" "$OUT_BASE/firmware" "dspico-firmware"
  info "✓ Firmware built"
}

# ── [6/9] Pico Loader ────────────────────────────────────────────────────────

step_pico_loader() {
  local repo=/tmp/pico-loader
  step "6/9" "Build Pico Loader"

  clone_repo https://github.com/LNH-team/pico-loader "$repo" --recursive
  build

  # Verify key artifacts exist
  find_artifact "$repo" "picoLoader7.bin" 5 >/dev/null
  find_artifact "$repo" "picoLoader9*.bin" 5 >/dev/null

  copy_glob "$repo/picoLoader7.bin"       "$OUT_BASE/pico-loader/"
  copy_glob "$repo/picoLoader9*.bin"      "$OUT_BASE/pico-loader/"
  copy_glob "$repo/data/aplist.bin"       "$OUT_BASE/pico-loader/"
  copy_glob "$repo/data/savelist.bin"     "$OUT_BASE/pico-loader/"
  copy_glob "$repo/data/patchlist.bin"    "$OUT_BASE/pico-loader/"

  write_build_info "$repo" "$OUT_BASE/pico-loader" "pico-loader"
  info "✓ Pico Loader built"
}

# ── [7/9] Pico Launcher ──────────────────────────────────────────────────────

step_pico_launcher() {
  local repo=/tmp/pico-launcher
  step "7/9" "Build Pico Launcher"

  clone_repo https://github.com/LNH-team/pico-launcher "$repo"
  git submodule update --init
  build

  [ -f "$repo/LAUNCHER.nds" ] || error_exit "LAUNCHER.nds not produced"
  cp -v "$repo/LAUNCHER.nds" "$OUT_BASE/pico-launcher/"

  [ -d "$repo/_pico" ] || error_exit "_pico directory not found"
  cp -r "$repo/_pico" "$OUT_BASE/pico-launcher/"

  write_build_info "$repo" "$OUT_BASE/pico-launcher" "pico-launcher"
  info "✓ Pico Launcher built"
}

# ── [8/9] Assemble SD card ───────────────────────────────────────────────────

step_assemble_sd() {
  step "8/9" "Assemble SD card structure"

  local sd="$OUT_BASE/sd_card"
  rm -rf "$sd"
  mkdir -p "$sd/_pico"

  # Copy _pico contents from pico-launcher
  if [ -d "$OUT_BASE/pico-launcher/_pico" ]; then
    cp -r "$OUT_BASE/pico-launcher/_pico"/* "$sd/_pico/" || true
  fi

  # Copy pico loader binaries
  if [ -d "$OUT_BASE/pico-loader" ]; then
    copy_glob "$OUT_BASE/pico-loader/picoLoader7*.bin" "$sd/_pico/"
    for f in "$OUT_BASE/pico-loader"/picoLoader9*.bin; do
      if [ -e "$f" ]; then
        cp -v "$f" "$sd/_pico/picoLoader9.bin"
        break
      fi
    done
    copy_if_exists "$OUT_BASE/pico-loader/aplist.bin"    "$sd/_pico/aplist.bin"
    copy_if_exists "$OUT_BASE/pico-loader/savelist.bin"  "$sd/_pico/savelist.bin"
    copy_if_exists "$OUT_BASE/pico-loader/patchlist.bin" "$sd/_pico/patchlist.bin"
  fi

  # Set LAUNCHER.nds as boot file
  [ -f "$OUT_BASE/pico-launcher/LAUNCHER.nds" ] || \
    error_exit "LAUNCHER.nds not found for SD card assembly"
  cp -v "$OUT_BASE/pico-launcher/LAUNCHER.nds" "$sd/_picoboot.nds"

  info "✓ SD card assembled: $sd"
}

# =============================================================================
#  Main
# =============================================================================

main() {
  setup_dirs
  [ -f /opt/wonderful/bin/wf-env ] && . /opt/wonderful/bin/wf-env || true

  step_dldi
  step_bootloader
  step_encryptor
  step_wrfuxxed
  step_firmware
  step_pico_loader
  step_pico_launcher
  step_assemble_sd

  step "9/9" "Build complete!"
  info "════════════════════════════════════════"
  info "  All components built successfully!"
  info "════════════════════════════════════════"
  echo "Outputs: $OUT_BASE"
}

main "$@"
