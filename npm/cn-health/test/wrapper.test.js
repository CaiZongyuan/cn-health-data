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
