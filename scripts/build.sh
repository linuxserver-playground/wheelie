#!/usr/bin/env bash
# Build the wheels for one distro and arch on a native runner, into ./out (no registry round trip).
#
# Env: IMAGE (base image), INDEX (index name), PACKAGES; INDEX_URL defaults to the Pages index.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib.sh
source "${here}/lib.sh"

: "${IMAGE:?}" "${INDEX:?}" "${PACKAGES:?}"
INDEX_URL="${INDEX_URL:-https://linuxserver-playground.github.io/wheelie}"

cd "${here}/.."
rm -rf out
# retry_ghcr only retries registry rate limits; a failing compile returns at once.
retry_ghcr docker buildx build --pull \
  --build-arg BASE="${IMAGE}" \
  --build-arg PACKAGES="${PACKAGES}" \
  --build-arg FIND_LINKS="${INDEX_URL}/${INDEX}/" \
  --target artifacts \
  --output type=local,dest=out \
  .
ls -l out
