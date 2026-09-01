use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use semver::Version;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Manifest {
    pub schema_version: u32,
    pub release: Release,
    pub dataset: Dataset,
    pub artifacts: Vec<Artifact>,
    pub rights: Rights,
    pub runtime: Runtime,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Release {
    pub id: String,
    pub sequence: u64,
    pub storage_key: String,
    pub build_revision: u64,
    pub revoked: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Dataset {
    pub id: String,
    pub source_version: String,
    #[serde(default)]
    pub dataset_schema_version: Option<u32>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Artifact {
    pub name: String,
    pub url: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub uncompressed_name: Option<String>,
    pub uncompressed_sha256: Option<String>,
    pub uncompressed_size_bytes: Option<u64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Rights {
    pub redistribution: String,
    pub release_eligible: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Runtime {
    pub minimum_cli_version: String,
}

impl Manifest {
    pub fn read(path: &Path) -> Result<Self> {
        let file = File::open(path)
            .with_context(|| format!("failed to open Manifest {}", path.display()))?;
        let manifest: Self = serde_json::from_reader(file)
            .with_context(|| format!("failed to parse Manifest {}", path.display()))?;
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn parse(bytes: &[u8]) -> Result<Self> {
        let manifest: Self = serde_json::from_slice(bytes).context("failed to parse Manifest")?;
        manifest.validate()?;
        Ok(manifest)
    }

    fn validate(&self) -> Result<()> {
        if self.schema_version != 1 {
            bail!("unsupported Manifest schemaVersion {}", self.schema_version);
        }
        validate_segment(&self.dataset.id, "Dataset ID")?;
        validate_segment(&self.release.storage_key, "storageKey")?;
        if self.release.revoked {
            bail!("Release {} is revoked", self.release.id);
        }
        let minimum = Version::parse(&self.runtime.minimum_cli_version).with_context(|| {
            format!(
                "invalid runtime.minimumCliVersion {:?}",
                self.runtime.minimum_cli_version
            )
        })?;
        let current = Version::parse(env!("CARGO_PKG_VERSION"))
            .context("invalid compiled cn-health version")?;
        if current < minimum {
            bail!(
                "CLI_VERSION_INCOMPATIBLE: Manifest requires cn-health >= {minimum}, running {current}"
            );
        }
        Ok(())
    }

    pub fn compressed_sqlite(&self) -> Result<&Artifact> {
        self.artifacts
            .iter()
            .find(|artifact| artifact.name == "data.sqlite.zst")
            .context("Manifest has no data.sqlite.zst artifact")
    }
}

pub fn artifact_path(manifest_path: &Path, artifact: &Artifact) -> Result<PathBuf> {
    let relative = Path::new(&artifact.url);
    if relative.is_absolute()
        || relative.components().count() != 1
        || artifact.url.contains("..")
        || artifact.url != artifact.name
    {
        bail!("unsafe local artifact URL {:?}", artifact.url);
    }
    Ok(manifest_path
        .parent()
        .context("Manifest path has no parent")?
        .join(relative))
}

pub fn sha256_file(path: &Path) -> Result<(String, u64)> {
    let mut file =
        File::open(path).with_context(|| format!("failed to open artifact {}", path.display()))?;
    let mut digest = Sha256::new();
    let mut size = 0_u64;
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
        size += read as u64;
    }
    Ok((hex::encode(digest.finalize()), size))
}

pub fn validate_segment(value: &str, label: &str) -> Result<()> {
    if value.is_empty()
        || value == "."
        || value == ".."
        || value.contains(['/', '\\'])
        || value.chars().any(char::is_control)
    {
        bail!("invalid {label}: {value:?}");
    }
    Ok(())
}
