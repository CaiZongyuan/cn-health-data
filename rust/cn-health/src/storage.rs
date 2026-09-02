use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use fs2::FileExt;
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use tempfile::{NamedTempFile, tempdir_in};

use crate::manifest::{Manifest, artifact_path, sha256_file, validate_segment};
use crate::progress::{Progress, copy_with_progress};

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

#[derive(Debug, Clone, Deserialize, Serialize)]
struct InstallMetadata {
    trust: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstalledVersion {
    pub release_id: String,
    pub sequence: u64,
    pub storage_key: String,
    pub source_version: String,
    pub build_revision: u64,
    pub trust: String,
}

pub struct InstalledReleaseFiles {
    pub database_path: PathBuf,
    pub manifest_path: PathBuf,
    pub trust: String,
}

pub fn install_local(data_dir: &Path, manifest_path: &Path) -> Result<InstalledDataset> {
    let progress = Progress::new("install");
    install_manifest(data_dir, manifest_path, "local-untrusted", true, &progress)
}

pub(crate) fn install_manifest(
    data_dir: &Path,
    manifest_path: &Path,
    trust: &str,
    verify_source_artifact: bool,
    progress: &Progress,
) -> Result<InstalledDataset> {
    let manifest_path = manifest_path.canonicalize()?;
    let manifest = Manifest::read(&manifest_path)?;
    let dataset_dir = data_dir.join("datasets").join(&manifest.dataset.id);
    let releases_dir = dataset_dir.join("releases");
    fs::create_dir_all(&releases_dir)?;
    let lock = dataset_lock(data_dir, &manifest.dataset.id)?;
    FileExt::lock_exclusive(&lock)?;

    let final_dir = releases_dir.join(&manifest.release.storage_key);
    let compressed = manifest.compressed_sqlite()?;
    let expected_hash = compressed
        .uncompressed_sha256
        .as_deref()
        .context("Manifest has no uncompressedSha256")?;
    let expected_size = compressed
        .uncompressed_size_bytes
        .context("Manifest has no uncompressedSizeBytes")?;
    let compressed_path = if verify_source_artifact {
        progress.phase("verify compressed artifact");
        Some(verified_compressed_path(&manifest_path, compressed)?)
    } else {
        None
    };

    if final_dir.exists() {
        let existing_manifest_path = final_dir.join("manifest.json");
        let existing_manifest = Manifest::read(&existing_manifest_path)?;
        let (incoming_manifest_hash, _) = sha256_file(&manifest_path)?;
        let (existing_manifest_hash, _) = sha256_file(&existing_manifest_path)?;
        if existing_manifest.release.id != manifest.release.id
            || existing_manifest.dataset.id != manifest.dataset.id
            || existing_manifest_hash != incoming_manifest_hash
        {
            bail!(
                "installed Release {} conflicts with incoming Manifest",
                manifest.release.id
            );
        }
        let database_path = final_dir.join("data.sqlite");
        let (database_hash, database_size) = sha256_file(&database_path)?;
        if database_hash != expected_hash || database_size != expected_size {
            bail!("installed SQLite SHA256 or size does not match Manifest");
        }
        progress.phase("verify installed SQLite");
        verify_database(&database_path)?;
        let existing_metadata: InstallMetadata =
            serde_json::from_reader(File::open(final_dir.join("install.json"))?)?;
        let effective_trust = if existing_metadata.trust.starts_with("signed-registry:")
            && trust == "local-untrusted"
        {
            existing_metadata.trust
        } else {
            trust.to_owned()
        };
        write_json_atomic(
            &final_dir.join("install.json"),
            &InstallMetadata {
                trust: effective_trust.clone(),
            },
        )?;
        let pointer = pointer_from(&manifest, &effective_trust);
        write_json_atomic(&dataset_dir.join("current.json"), &pointer)?;
        FileExt::unlock(&lock)?;
        return Ok(installed_dataset(manifest.dataset.id, pointer));
    }

    let compressed_path = match compressed_path {
        Some(path) => path,
        None => verified_compressed_path(&manifest_path, compressed)?,
    };

    let temporary = tempdir_in(&releases_dir)?;
    let database_path = temporary.path().join("data.sqlite");
    decompress_bounded(&compressed_path, &database_path, expected_size, progress)?;
    let (database_hash, database_size) = sha256_file(&database_path)?;
    if database_hash != expected_hash || database_size != expected_size {
        bail!("uncompressed SQLite SHA256 or size does not match Manifest");
    }
    progress.phase("verify SQLite");
    verify_database(&database_path)?;
    fs::copy(&manifest_path, temporary.path().join("manifest.json"))?;
    fs::write(
        temporary.path().join("install.json"),
        serde_json::to_vec_pretty(&InstallMetadata {
            trust: trust.to_owned(),
        })?,
    )?;
    fs::rename(temporary.path(), &final_dir)?;

    let pointer = pointer_from(&manifest, trust);
    write_json_atomic(&dataset_dir.join("current.json"), &pointer)?;
    FileExt::unlock(&lock)?;
    Ok(installed_dataset(manifest.dataset.id, pointer))
}

fn verified_compressed_path(
    manifest_path: &Path,
    compressed: &crate::manifest::Artifact,
) -> Result<PathBuf> {
    let compressed_path = artifact_path(manifest_path, compressed)?;
    let (compressed_hash, compressed_size) = sha256_file(&compressed_path)?;
    if compressed_hash != compressed.sha256 || compressed_size != compressed.size_bytes {
        bail!("compressed artifact SHA256 or size does not match Manifest");
    }
    Ok(compressed_path)
}

fn installed_dataset(id: String, pointer: CurrentPointer) -> InstalledDataset {
    InstalledDataset {
        id,
        release_id: pointer.release_id,
        source_version: pointer.source_version,
        build_revision: pointer.build_revision,
        trust: pointer.trust,
    }
}

pub fn list_versions(data_dir: &Path, dataset_id: &str) -> Result<Vec<InstalledVersion>> {
    validate_segment(dataset_id, "Dataset ID")?;
    let releases_dir = data_dir.join("datasets").join(dataset_id).join("releases");
    if !releases_dir.exists() {
        return Ok(Vec::new());
    }
    let mut versions = Vec::new();
    for entry in fs::read_dir(releases_dir)? {
        let release_dir = entry?.path();
        if !release_dir.is_dir() {
            continue;
        }
        let manifest = Manifest::read(&release_dir.join("manifest.json"))?;
        let metadata: InstallMetadata =
            serde_json::from_reader(File::open(release_dir.join("install.json"))?)?;
        versions.push(InstalledVersion {
            release_id: manifest.release.id,
            sequence: manifest.release.sequence,
            storage_key: manifest.release.storage_key,
            source_version: manifest.dataset.source_version,
            build_revision: manifest.release.build_revision,
            trust: metadata.trust,
        });
    }
    versions.sort_by_key(|version| version.sequence);
    Ok(versions)
}

pub fn installed_release_files(
    data_dir: &Path,
    dataset_id: &str,
    release_id: &str,
) -> Result<InstalledReleaseFiles> {
    validate_segment(dataset_id, "Dataset ID")?;
    let version = list_versions(data_dir, dataset_id)?
        .into_iter()
        .find(|version| version.release_id == release_id)
        .with_context(|| format!("Release {release_id} is not installed"))?;
    let release_dir = data_dir
        .join("datasets")
        .join(dataset_id)
        .join("releases")
        .join(&version.storage_key);
    let manifest_path = release_dir.join("manifest.json");
    let manifest = Manifest::read(&manifest_path)?;
    if manifest.dataset.id != dataset_id || manifest.release.id != release_id {
        bail!("installed Release identity does not match requested Release");
    }
    let compressed = manifest.compressed_sqlite()?;
    let expected_hash = compressed
        .uncompressed_sha256
        .as_deref()
        .context("Manifest has no uncompressedSha256")?;
    let expected_size = compressed
        .uncompressed_size_bytes
        .context("Manifest has no uncompressedSizeBytes")?;
    let database_path = release_dir.join("data.sqlite");
    let (database_hash, database_size) = sha256_file(&database_path)?;
    if database_hash != expected_hash || database_size != expected_size {
        bail!("installed SQLite SHA256 or size does not match Manifest");
    }
    verify_database(&database_path)?;
    Ok(InstalledReleaseFiles {
        database_path,
        manifest_path,
        trust: version.trust,
    })
}

pub fn activate_release(
    data_dir: &Path,
    dataset_id: &str,
    release_id: &str,
) -> Result<InstalledVersion> {
    let lock = dataset_lock(data_dir, dataset_id)?;
    let version = list_versions(data_dir, dataset_id)?
        .into_iter()
        .find(|version| version.release_id == release_id)
        .with_context(|| format!("Release {release_id} is not installed"))?;
    let manifest_path = data_dir
        .join("datasets")
        .join(dataset_id)
        .join("releases")
        .join(&version.storage_key)
        .join("manifest.json");
    let manifest = Manifest::read(&manifest_path)?;
    let pointer = pointer_from(&manifest, &version.trust);
    write_json_atomic(
        &data_dir
            .join("datasets")
            .join(dataset_id)
            .join("current.json"),
        &pointer,
    )?;
    FileExt::unlock(&lock)?;
    Ok(version)
}

fn pointer_from(manifest: &Manifest, trust: &str) -> CurrentPointer {
    CurrentPointer {
        release_id: manifest.release.id.clone(),
        sequence: manifest.release.sequence,
        storage_key: manifest.release.storage_key.clone(),
        source_version: manifest.dataset.source_version.clone(),
        build_revision: manifest.release.build_revision,
        relative_path: format!("releases/{}", manifest.release.storage_key),
        trust: trust.to_owned(),
    }
}

fn dataset_lock(data_dir: &Path, dataset_id: &str) -> Result<File> {
    validate_segment(dataset_id, "Dataset ID")?;
    fs::create_dir_all(data_dir.join("locks"))?;
    let lock_path = data_dir.join("locks").join(format!("{dataset_id}.lock"));
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(lock_path)?;
    FileExt::lock_exclusive(&lock)?;
    Ok(lock)
}

fn decompress_bounded(
    source: &Path,
    target: &Path,
    expected_size: u64,
    progress: &Progress,
) -> Result<()> {
    let input = File::open(source)?;
    let decoder = zstd::stream::read::Decoder::new(input)?;
    let mut limited = decoder.take(expected_size + 1);
    let mut output = File::create(target)?;
    progress.phase("decompress");
    let copied = copy_with_progress(&mut limited, &mut output, progress, Some(expected_size))?;
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
