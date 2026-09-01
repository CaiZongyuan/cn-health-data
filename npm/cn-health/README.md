# cn-health npm wrapper

This package is the thin launcher for the native runtime. Set
`CN_HEALTH_BINARY` during local development; published builds resolve an
`@cn-health/cli-<platform>-<arch>` optional package.

After installing a release, run `cn-health init` to install the signed starter
Dataset and `cn-health laboratory search 血糖 --json` to verify the runtime.
