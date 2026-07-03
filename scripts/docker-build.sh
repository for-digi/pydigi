#!/usr/bin/env bash
#
# Build pydigi's sdist + wheel inside Docker and drop them into ./dist on the
# host. Fully isolated: the host's Python is never used.
#
#   ./build/docker-build.sh
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
