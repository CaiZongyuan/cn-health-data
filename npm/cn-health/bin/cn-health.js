#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function platformBinaryName() {
  return process.platform === "win32" ? "cn-health.exe" : "cn-health";
}

function optionalPlatformBinary() {
  const packageName = `@cn-health/cli-${process.platform}-${process.arch}`;
  try {
    const packageManifest = require.resolve(`${packageName}/package.json`);
    const packageRoot = path.dirname(packageManifest);
    const metadata = JSON.parse(fs.readFileSync(packageManifest, "utf8"));
    const relativeBin =
      typeof metadata.cnHealthBinary === "string" ? metadata.cnHealthBinary : null;
    const binary = relativeBin ? path.resolve(packageRoot, relativeBin) : null;
    return binary && fs.existsSync(binary) ? binary : null;
  } catch (error) {
    if (error.code === "MODULE_NOT_FOUND") {
      return null;
    }
    throw error;
  }
}

function resolveBinary() {
  if (process.env.CN_HEALTH_BINARY) {
    return process.env.CN_HEALTH_BINARY;
  }
  const packaged = optionalPlatformBinary();
  if (packaged) {
    return packaged;
  }
  const development = path.resolve(
    __dirname,
    "../../../target/release",
    platformBinaryName(),
  );
  if (fs.existsSync(development)) {
    return development;
  }
  throw new Error(
    `No cn-health binary for ${process.platform}/${process.arch}; ` +
      "install a supported platform package or set CN_HEALTH_BINARY",
  );
}

try {
  const result = spawnSync(resolveBinary(), process.argv.slice(2), {
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.signal) {
    process.kill(process.pid, result.signal);
  }
  process.exit(result.status ?? 1);
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
