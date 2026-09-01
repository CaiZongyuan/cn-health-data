#!/usr/bin/env bash
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
private_key=${1:?usage: scripts/sign-starter-registry.sh PRIVATE_KEY [PUBLIC_BASE_URL]}
base_url=${2:-https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/distribution/releases}

cd "$repo_root"
test -f "$private_key"

mapfile -t manifests < <(find distribution/releases -type f -name manifest.json -print | sort)
if [[ ${#manifests[@]} -eq 0 ]]; then
  echo "no public release Manifests found" >&2
  exit 2
fi

uv run cn-health-build registry build "${manifests[@]}" \
  --manifest-base-url "$base_url" \
  --private-key "$private_key" \
  --output distribution/registry.json \
  --signature distribution/registry.json.sig
