#!/usr/bin/env bash
# Build the arm64 runtime image on the workstation, push it to a registry and
# start it on the Raspberry Pi 4 over SSH (versioned - never :latest).
#   REGISTRY=ghcr.io/<user> PI_HOST=pi@chotu.local bash scripts/deploy_pi.sh 2.0.0
set -euo pipefail
VERSION="${1:-2.0.0}"
: "${REGISTRY:?set REGISTRY, e.g. ghcr.io/<github-user>}"
: "${PI_HOST:?set PI_HOST, e.g. pi@chotu.local}"
cd "$(dirname "$0")/.."

docker buildx create --use --name chotu-builder 2>/dev/null || docker buildx use chotu-builder
for target in runtime perception; do
  docker buildx build -f docker/Dockerfile --target "$target" --platform linux/arm64 \
    -t "$REGISTRY/chotu/$target:$VERSION" --push .
done

ssh "$PI_HOST" "mkdir -p ~/chotu/docker ~/chotu/models"
scp docker/docker-compose.yml "$PI_HOST:~/chotu/docker/"
ssh "$PI_HOST" "cd ~/chotu/docker && REGISTRY=$REGISTRY/chotu CHOTU_VERSION=$VERSION \
  docker compose --profile robot pull && REGISTRY=$REGISTRY/chotu CHOTU_VERSION=$VERSION \
  docker compose --profile robot up -d && docker compose --profile robot ps"
echo "Deployed chotu $VERSION to $PI_HOST. Rollback: re-run with the previous version."
