#!/usr/bin/env bash
set -euo pipefail

artifact_root=${1:?usage: scripts/publish-npm-packages.sh ARTIFACT_DIRECTORY}
test -n "${NODE_AUTH_TOKEN:-}"
test -d "$artifact_root"

mapfile -d '' platform_packages < <(
  find "$artifact_root" -name 'cn-health-cli-*.tgz' -print0 | sort -z
)
test "${#platform_packages[@]}" -eq 4
launcher=$(find "$artifact_root" -name 'cn-health-*.tgz' ! -name 'cn-health-cli-*.tgz' -print -quit)
test -n "$launcher"

packages=("${platform_packages[@]}" "$launcher")
for package in "${packages[@]}"; do
  package_path=$(realpath "$package")
  metadata=$(tar -xOf "$package_path" package/package.json)
  package_name=$(node -e 'process.stdout.write(JSON.parse(require("fs").readFileSync(0, "utf8")).name)' <<<"$metadata")
  package_version=$(node -e 'process.stdout.write(JSON.parse(require("fs").readFileSync(0, "utf8")).version)' <<<"$metadata")
  case "$package_name" in
    cn-health | @cn-health/cli-*) ;;
    *)
      echo "refusing to publish unexpected package: $package_name" >&2
      exit 2
      ;;
  esac

  if published_version=$(npm view "$package_name@$package_version" version 2>/dev/null); then
    test "$published_version" = "$package_version"
    echo "$package_name@$package_version already published"
  else
    npm publish "$package_path" --access public
  fi
done
