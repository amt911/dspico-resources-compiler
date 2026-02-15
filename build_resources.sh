#!/bin/sh
set -eu

IMAGE_NAME=${IMAGE_NAME:-dspico-compiler:latest}
INPUT_DIR=${1:-$(pwd)/inputs}
OUTPUT_DIR=${2:-$(pwd)/outputs}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Building Docker image $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

echo "Running container (inputs: $INPUT_DIR, outputs: $OUTPUT_DIR)..."
mkdir -p "$OUTPUT_DIR"
docker run --rm \
  -v "$INPUT_DIR":/inputs:ro \
  -v "$OUTPUT_DIR":/outputs \
  -v "$SCRIPT_DIR/compile_resources.sh":/dspico/compile_resources.sh:ro \
  -e ENABLE_WRFUXXED="${ENABLE_WRFUXXED:-0}" \
  --entrypoint bash \
  "$IMAGE_NAME" -lc '/dspico/compile_resources.sh'

echo "Finished. Outputs are in $OUTPUT_DIR"
