#!/usr/bin/env bash
#
# Build pydigi's wheel inside Docker and drop it into ./dist on the host.
# Fully isolated: the host's Python is never used.
#
#   ./scripts/docker-build.sh
#
set -euo pipefail

# Run from the repository root regardless of where the script is called from.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

dest="${1:-dist}"
mkdir -p "$dest"

echo "Building pydigi artifacts in Docker -> ./$dest"
DOCKER_BUILDKIT=1 docker build \
    --target export \
    --output "type=local,dest=${dest}" \
    -f Dockerfile \
    .

echo
echo "Artifacts in ./$dest:"
ls -1 "$dest"
