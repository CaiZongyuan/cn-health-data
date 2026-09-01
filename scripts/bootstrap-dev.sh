#!/usr/bin/env bash
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

for tool in git uv cargo node pnpm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing required development tool: $tool" >&2
    exit 2
  fi
done

uv sync --locked
uv run cn-health-build validate-contracts
pnpm install --frozen-lockfile
pnpm --filter cn-health test
cargo build --locked -p cn-health

runtime_data_dir=${CN_HEALTH_DEV_DATA_DIR:-"$repo_root/.work/runtime"}
if [[ -n ${CN_HEALTH_REGISTRY_URL:-} || -n ${CN_HEALTH_REGISTRY_PUBLIC_KEY:-} ]]; then
  if [[ -z ${CN_HEALTH_REGISTRY_URL:-} || -z ${CN_HEALTH_REGISTRY_PUBLIC_KEY:-} ]]; then
    echo "CN_HEALTH_REGISTRY_URL and CN_HEALTH_REGISTRY_PUBLIC_KEY must be set together" >&2
    exit 2
  fi
  target/debug/cn-health --data-dir "$runtime_data_dir" init \
    --registry "$CN_HEALTH_REGISTRY_URL" \
    --public-key "$CN_HEALTH_REGISTRY_PUBLIC_KEY"
else
  target/debug/cn-health --data-dir "$runtime_data_dir" init
fi

target/debug/cn-health --data-dir "$runtime_data_dir" doctor
target/debug/cn-health --data-dir "$runtime_data_dir" laboratory search 血糖 --json
