const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

test("forwards arguments to CN_HEALTH_BINARY", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cn-health-wrapper-"));
  const binary = path.join(directory, "fake-cn-health");
  fs.writeFileSync(binary, "#!/bin/sh\nprintf '%s\\n' \"$@\"\nexit 7\n", { mode: 0o755 });

  const result = spawnSync(
    process.execPath,
    [path.join(__dirname, "../bin/cn-health.js"), "drug", "search", "二甲双胍"],
    {
      encoding: "utf8",
      env: { ...process.env, CN_HEALTH_BINARY: binary },
    },
  );

  assert.equal(result.status, 7);
  assert.equal(result.stdout, "drug\nsearch\n二甲双胍\n");
});

test("resolves a packaged platform binary", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cn-health-package-"));
  const packageRoot = path.join(directory, "node_modules", "cn-health");
  const launcherDirectory = path.join(packageRoot, "bin");
  fs.mkdirSync(launcherDirectory, { recursive: true });
  const launcher = path.join(launcherDirectory, "cn-health.js");
  fs.copyFileSync(path.join(__dirname, "../bin/cn-health.js"), launcher);

  const platformRoot = path.join(
    directory,
    "node_modules",
    "@cn-health",
    `cli-${process.platform}-${process.arch}`,
  );
  const platformBin = path.join(platformRoot, "bin", "cn-health");
  fs.mkdirSync(path.dirname(platformBin), { recursive: true });
  fs.writeFileSync(
    path.join(platformRoot, "package.json"),
    JSON.stringify({ name: "fixture", cnHealthBinary: "bin/cn-health" }),
  );
  fs.writeFileSync(platformBin, "#!/bin/sh\nprintf '%s\\n' packaged \"$@\"\n", {
    mode: 0o755,
  });

  const environment = { ...process.env };
  delete environment.CN_HEALTH_BINARY;
  const result = spawnSync(process.execPath, [launcher, "doctor"], {
    encoding: "utf8",
    env: environment,
  });

  assert.equal(result.status, 0);
  assert.equal(result.stdout, "packaged\ndoctor\n");
});
