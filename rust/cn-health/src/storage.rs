use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use fs2::FileExt;
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use tempfile::{NamedTempFile, tempdir_in};

use crate::manifest::{Manifest, artifact_path, sha256_file, validate_segment};

const APPLICATION_ID: i64 = 0x434E4844;

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CurrentPointer {
    pub release_id: String,
    pub sequence: u64,
    pub storage_key: String,
    pub source_version: String,
    pub build_revision: u64,
    pub relative_path: String,
    pub trust: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstalledDataset {
    pub id: String,
    pub release_id: String,
    pub source_version: String,
    pub build_revision: u64,
    pub trust: String,
}

pub fn install_local(data_dir: &Path, manifest_path: &Path) -> Result<InstalledDataset> {
    let manifest_path = manifest_path.canonicalize()?;
    let manifest = Manifest::read(&manifest_path)?;
    let dataset_dir = data_dir.join("datasets").join(&manifest.dataset.id);
    let releases_dir = dataset_dir.join("releases");
    fs::create_dir_all(&releases_dir)?;
    fs::create_dir_all(data_dir.join("locks"))?;
    let lock_path = data_dir
        .join("locks")
        .join(format!("{}.lock", manifest.dataset.id));
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(lock_path)?;
    FileExt::lock_exclusive(&lock)?;

    let final_dir = releases_dir.join(&manifest.release.storage_key);
    if final_dir.exists() {
        bail!("Release {} is already installed", manifest.release.id);
    }
    let compressed = manifest.compressed_sqlite()?;
    let compressed_path = artifact_path(&manifest_path, compressed)?;
    let (compressed_hash, compressed_size) = sha256_file(&compressed_path)?;
    if compressed_hash != compressed.sha256 || compressed_size != compressed.size_bytes {
        bail!("compressed artifact SHA256 or size does not match Manifest");
    }
    let expected_hash = compressed
        .uncompressed_sha256
        .as_deref()
        .context("Manifest has no uncompressedSha256")?;
    let expected_size = compressed
        .uncompressed_size_bytes
        .context("Manifest has no uncompressedSizeBytes")?;

    let temporary = tempdir_in(&releases_dir)?;
    let database_path = temporary.path().join("data.sqlite");
    decompress_bounded(&compressed_path, &database_path, expected_size)?;
    let (database_hash, database_size) = sha256_file(&database_path)?;
    if database_hash != expected_hash || database_size != expected_size {
        bail!("uncompressed SQLite SHA256 or size does not match Manifest");
    }
    verify_database(&database_path)?;
    fs::copy(&manifest_path, temporary.path().join("manifest.json"))?;
    fs::rename(temporary.path(), &final_dir)?;

    let pointer = CurrentPointer {
        release_id: manifest.release.id.clone(),
        sequence: manifest.release.sequence,
        storage_key: manifest.release.storage_key.clone(),
        source_version: manifest.dataset.source_version.clone(),
        build_revision: manifest.release.build_revision,
        relative_path: format!("releases/{}", manifest.release.storage_key),
        trust: "local-untrusted".to_owned(),
    };
    write_json_atomic(&dataset_dir.join("current.json"), &pointer)?;
    FileExt::unlock(&lock)?;
    Ok(InstalledDataset {
        id: manifest.dataset.id,
        release_id: pointer.release_id,
        source_version: pointer.source_version,
        build_revision: pointer.build_revision,
        trust: pointer.trust,
    })
}

fn decompress_bounded(source: &Path, target: &Path, expected_size: u64) -> Result<()> {
    let input = File::open(source)?;
    let decoder = zstd::stream::read::Decoder::new(input)?;
    let mut limited = decoder.take(expected_size + 1);
    let mut output = File::create(target)?;
    let copied = std::io::copy(&mut limited, &mut output)?;
    output.flush()?;
    output.sync_all()?;
    if copied != expected_size {
        bail!("decompressed SQLite size mismatch: expected {expected_size}, found {copied}");
    }
    Ok(())
}

fn verify_database(path: &Path) -> Result<()> {
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    let integrity: String = connection.query_row("PRAGMA integrity_check", [], |row| row.get(0))?;
    if integrity != "ok" {
        bail!("SQLite integrity_check failed: {integrity}");
    }
    let application_id: i64 =
        connection.query_row("PRAGMA application_id", [], |row| row.get(0))?;
    if application_id != APPLICATION_ID {
        bail!("unexpected SQLite application_id {application_id}");
    }
    Ok(())
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let parent = path.parent().context("current.json has no parent")?;
    fs::create_dir_all(parent)?;
    let mut temporary = NamedTempFile::new_in(parent)?;
    serde_json::to_writer_pretty(&mut temporary, value)?;
    temporary.write_all(b"\n")?;
    temporary.flush()?;
    temporary.as_file().sync_all()?;
    temporary.persist(path)?;
    Ok(())
}

pub fn current_pointer(data_dir: &Path, dataset_id: &str) -> Result<CurrentPointer> {
    validate_segment(dataset_id, "Dataset ID")?;
    let path = data_dir
        .join("datasets")
        .join(dataset_id)
        .join("current.json");
    let file =
        File::open(&path).with_context(|| format!("Dataset {dataset_id} is not installed"))?;
    Ok(serde_json::from_reader(file)?)
}

pub fn current_database(data_dir: &Path, dataset_id: &str) -> Result<(PathBuf, CurrentPointer)> {
    let pointer = current_pointer(data_dir, dataset_id)?;
    validate_segment(&pointer.storage_key, "storageKey")?;
    let database = data_dir
        .join("datasets")
        .join(dataset_id)
        .join("releases")
        .join(&pointer.storage_key)
        .join("data.sqlite");
    Ok((database, pointer))
}

pub fn list_installed(data_dir: &Path) -> Result<Vec<InstalledDataset>> {
    let datasets_dir = data_dir.join("datasets");
    if !datasets_dir.exists() {
        return Ok(Vec::new());
    }
    let mut installed = Vec::new();
    for entry in fs::read_dir(datasets_dir)? {
        let entry = entry?;
        if !entry.file_type()?.is_dir() {
            continue;
        }
        let id = entry.file_name().to_string_lossy().into_owned();
        if let Ok(pointer) = current_pointer(data_dir, &id) {
            installed.push(InstalledDataset {
                id,
                release_id: pointer.release_id,
                source_version: pointer.source_version,
                build_revision: pointer.build_revision,
                trust: pointer.trust,
            });
        }
    }
    installed.sort_by(|left, right| left.id.cmp(&right.id));
    Ok(installed)
}
