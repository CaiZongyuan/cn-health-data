use std::fs::{self, File};
use std::io::Write;
use std::path::Path;

use anyhow::{Context, Result, bail};
use serde::Serialize;
use tempfile::tempdir_in;

use crate::manifest::{Manifest, sha256_file};
use crate::registry::install_remote_release;
use crate::storage::installed_release_files;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaterializationReceipt {
    pub schema_version: u32,
    pub command: &'static str,
    pub cli_version: &'static str,
    pub dataset: MaterializedDataset,
    pub registry: MaterializedRegistry,
    pub manifest: MaterializedFile,
    pub sqlite: MaterializedFile,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaterializedDataset {
    pub id: String,
    pub release_id: String,
    pub dataset_schema_version: u32,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaterializedRegistry {
    pub url: String,
    pub key_id: String,
    pub trust: &'static str,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaterializedFile {
    pub path: &'static str,
    pub sha256: String,
    pub size_bytes: u64,
}

pub fn materialize_release(
    data_dir: &Path,
    dataset_id: &str,
    release_id: &str,
    registry_url: &str,
    public_key_path: &Path,
    output_dir: &Path,
) -> Result<MaterializationReceipt> {
    validate_output_directory(output_dir)?;
    let verified = install_remote_release(
        data_dir,
        dataset_id,
        release_id,
        registry_url,
        public_key_path,
    )?;
    let installed = installed_release_files(data_dir, dataset_id, release_id)?;
    if installed.trust != format!("signed-registry:{}", verified.registry_key_id) {
        bail!("installed Release trust does not match verified Registry");
    }
    let manifest = Manifest::read(&installed.manifest_path)?;
    let dataset_schema_version = manifest
        .dataset
        .dataset_schema_version
        .context("Manifest dataset has no datasetSchemaVersion")?;
    let parent = output_dir
        .parent()
        .context("materialization output has no parent")?;
    fs::create_dir_all(parent)?;
    let temporary = tempdir_in(parent)?;
    let manifest_target = temporary.path().join("manifest.json");
    let database_target = temporary.path().join("data.sqlite");
    fs::copy(&installed.manifest_path, &manifest_target)?;
    fs::copy(&installed.database_path, &database_target)?;
    let (manifest_hash, manifest_size) = sha256_file(&manifest_target)?;
    let (database_hash, database_size) = sha256_file(&database_target)?;
    if manifest_hash != verified.manifest_sha256 {
        bail!("materialized Manifest SHA256 does not match verified Registry");
    }
    let receipt = MaterializationReceipt {
        schema_version: 1,
        command: "dataset.materialize",
        cli_version: env!("CARGO_PKG_VERSION"),
        dataset: MaterializedDataset {
            id: verified.installed.id,
            release_id: verified.installed.release_id,
            dataset_schema_version,
        },
        registry: MaterializedRegistry {
            url: registry_url.to_owned(),
            key_id: verified.registry_key_id,
            trust: "signed-registry",
        },
        manifest: MaterializedFile {
            path: "manifest.json",
            sha256: manifest_hash,
            size_bytes: manifest_size,
        },
        sqlite: MaterializedFile {
            path: "data.sqlite",
            sha256: database_hash,
            size_bytes: database_size,
        },
    };
    let mut receipt_file = File::create(temporary.path().join("materialization.json"))?;
    serde_json::to_writer_pretty(&mut receipt_file, &receipt)?;
    receipt_file.write_all(b"\n")?;
    receipt_file.flush()?;
    receipt_file.sync_all()?;
    validate_output_directory(output_dir)?;
    if output_dir.exists() {
        fs::remove_dir(output_dir)?;
    }
    fs::rename(temporary.path(), output_dir)?;
    Ok(receipt)
}

fn validate_output_directory(path: &Path) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    if !path.is_dir() || fs::read_dir(path)?.next().transpose()?.is_some() {
        bail!("output directory must be empty");
    }
    Ok(())
}
