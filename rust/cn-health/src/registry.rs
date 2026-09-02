use std::fmt;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::Path;
use std::thread;
use std::time::{Duration, SystemTime};

use anyhow::{Context, Error, Result, anyhow, bail};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use reqwest::blocking::{Client, Response};
use reqwest::header::RETRY_AFTER;
use reqwest::redirect::Policy;
use reqwest::{StatusCode, Url};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use tempfile::TempDir;

use crate::manifest::Manifest;
use crate::progress::Progress;
use crate::storage::{InstalledDataset, install_manifest, list_versions};

const MAX_METADATA_BYTES: u64 = 10 * 1024 * 1024;
const MAX_ATTEMPTS: u32 = 4;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_RETRY_AFTER: Duration = Duration::from_secs(30);
const RETRY_CAPS: [Duration; 3] = [
    Duration::from_millis(250),
    Duration::from_secs(1),
    Duration::from_secs(4),
];

#[derive(Debug)]
pub(crate) struct RemoteUnavailable {
    attempts: u32,
    reason: String,
}

impl RemoteUnavailable {
    pub(crate) fn attempts(&self) -> u32 {
        self.attempts
    }
}

impl fmt::Display for RemoteUnavailable {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "remote unavailable after {} attempts: {}",
            self.attempts, self.reason
        )
    }
}

impl std::error::Error for RemoteUnavailable {}

enum RemoteAttemptError {
    Retryable {
        reason: String,
        retry_after: Option<Duration>,
    },
    Fatal(Error),
}

pub struct VerifiedRemoteRelease {
    pub installed: InstalledDataset,
    pub manifest_sha256: String,
    pub registry_key_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Registry {
    schema_version: u32,
    datasets: std::collections::HashMap<String, RegistryDataset>,
    signature: RegistrySignature,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RegistryDataset {
    recommended_release: Option<String>,
    releases: Vec<RegistryRelease>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RegistryRelease {
    id: String,
    manifest_url: String,
    manifest_sha256: String,
    revoked: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RegistrySignature {
    algorithm: String,
    key_id: String,
    url: String,
}

pub fn install_remote(
    data_dir: &Path,
    dataset_id: &str,
    registry_url: &str,
    public_key_path: &Path,
) -> Result<InstalledDataset> {
    let public_bytes = fs::read(public_key_path)?;
    install_remote_with_key(data_dir, dataset_id, registry_url, &public_bytes)
}

pub fn install_remote_with_key(
    data_dir: &Path,
    dataset_id: &str,
    registry_url: &str,
    public_bytes: &[u8],
) -> Result<InstalledDataset> {
    Ok(
        install_remote_release_with_key(data_dir, dataset_id, None, registry_url, public_bytes)?
            .installed,
    )
}

pub fn install_remote_release(
    data_dir: &Path,
    dataset_id: &str,
    release_id: &str,
    registry_url: &str,
    public_key_path: &Path,
) -> Result<VerifiedRemoteRelease> {
    let public_bytes = fs::read(public_key_path)?;
    install_remote_release_with_key(
        data_dir,
        dataset_id,
        Some(release_id),
        registry_url,
        &public_bytes,
    )
}

fn install_remote_release_with_key(
    data_dir: &Path,
    dataset_id: &str,
    requested_release_id: Option<&str>,
    registry_url: &str,
    public_bytes: &[u8],
) -> Result<VerifiedRemoteRelease> {
    let client = Client::builder()
        .redirect(Policy::none())
        .connect_timeout(CONNECT_TIMEOUT)
        .build()?;
    let registry_url = Url::parse(registry_url)?;
    require_secure_or_loopback(&registry_url)?;
    let registry_progress = Progress::new(requested_release_id.unwrap_or(dataset_id));
    let registry_bytes = fetch_bytes(
        &client,
        registry_url.clone(),
        MAX_METADATA_BYTES,
        &registry_progress,
        "registry",
    )?;
    let registry: Registry = serde_json::from_slice(&registry_bytes)?;
    if registry.schema_version != 1 || registry.signature.algorithm != "Ed25519" {
        bail!("unsupported Registry signature or schema");
    }
    let public_array: [u8; 32] = public_bytes
        .try_into()
        .context("Registry public key must contain 32 raw bytes")?;
    let key_id = hex::encode(Sha256::digest(public_bytes));
    if !key_id.starts_with(&registry.signature.key_id) {
        bail!("Registry keyId does not match the supplied public key");
    }
    let signature_url = registry_url.join(&registry.signature.url)?;
    require_same_origin(&registry_url, &signature_url)?;
    let signature_bytes = fetch_bytes(
        &client,
        signature_url,
        64,
        &registry_progress,
        "registry signature",
    )?;
    let signature = Signature::from_slice(&signature_bytes)?;
    VerifyingKey::from_bytes(&public_array)?.verify(&registry_bytes, &signature)?;

    let dataset = registry
        .datasets
        .get(dataset_id)
        .with_context(|| format!("Dataset {dataset_id} is not present in Registry"))?;
    let selected_release_id = match requested_release_id {
        Some(release_id) => release_id,
        None => dataset
            .recommended_release
            .as_deref()
            .context("Dataset has no recommended Release")?,
    };
    let release = dataset
        .releases
        .iter()
        .find(|release| release.id == selected_release_id)
        .with_context(|| format!("Release {selected_release_id} is missing from Registry"))?;
    if release.revoked {
        bail!("Release {} is revoked", release.id);
    }
    let progress = Progress::new(release.id.clone());
    let manifest_url = Url::parse(&release.manifest_url)?;
    require_secure_or_loopback(&manifest_url)?;
    require_same_origin(&registry_url, &manifest_url)?;
    let manifest_bytes = fetch_bytes(
        &client,
        manifest_url.clone(),
        MAX_METADATA_BYTES,
        &progress,
        "manifest",
    )?;
    if sha256_bytes(&manifest_bytes) != release.manifest_sha256 {
        bail!("Manifest SHA256 does not match signed Registry");
    }
    let manifest = Manifest::parse(&manifest_bytes)?;
    if manifest.dataset.id != dataset_id || manifest.release.id != release.id {
        bail!("Manifest identity does not match signed Registry");
    }
    if !manifest.rights.release_eligible {
        bail!("remote Manifest is not release-eligible");
    }
    let temporary = TempDir::new()?;
    let manifest_path = temporary.path().join("manifest.json");
    write_synced(&manifest_path, &manifest_bytes)?;
    let already_installed = list_versions(data_dir, dataset_id)?
        .iter()
        .any(|version| version.release_id == release.id);
    if !already_installed {
        let artifact = manifest.compressed_sqlite()?;
        let artifact_url = manifest_url.join(&artifact.url)?;
        require_same_origin(&manifest_url, &artifact_url)?;
        let artifact_path = temporary.path().join(&artifact.name);
        download_exact(
            &client,
            artifact_url,
            &artifact_path,
            artifact.size_bytes,
            &progress,
        )?;
    }
    let installed = install_manifest(
        data_dir,
        &manifest_path,
        &format!("signed-registry:{}", registry.signature.key_id),
        !already_installed,
        &progress,
    )?;
    progress.finish(if already_installed {
        "already installed"
    } else {
        "installed"
    });
    Ok(VerifiedRemoteRelease {
        installed,
        manifest_sha256: release.manifest_sha256.clone(),
        registry_key_id: registry.signature.key_id,
    })
}

fn fetch_bytes(
    client: &Client,
    url: Url,
    maximum: u64,
    progress: &Progress,
    phase: &str,
) -> Result<Vec<u8>> {
    retry_remote(progress, phase, || {
        let response = response_once(client, url.clone())?;
        let content_length = response.content_length();
        if content_length.is_some_and(|length| length > maximum) {
            return Err(RemoteAttemptError::Fatal(anyhow!(
                "remote response exceeds size limit"
            )));
        }
        let mut bytes = Vec::new();
        response
            .take(maximum + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| RemoteAttemptError::Retryable {
                reason: "response body interrupted".to_owned(),
                retry_after: None,
            })?;
        if bytes.len() as u64 > maximum {
            return Err(RemoteAttemptError::Fatal(anyhow!(
                "remote response exceeds size limit"
            )));
        }
        if content_length.is_some_and(|length| length != bytes.len() as u64) {
            return Err(RemoteAttemptError::Retryable {
                reason: "response body ended before Content-Length".to_owned(),
                retry_after: None,
            });
        }
        Ok(bytes)
    })
}

fn download_exact(
    client: &Client,
    url: Url,
    path: &Path,
    expected_size: u64,
    progress: &Progress,
) -> Result<()> {
    retry_remote(progress, "download", || {
        let response = response_once(client, url.clone())?;
        if response
            .content_length()
            .is_some_and(|length| length != expected_size)
        {
            return Err(RemoteAttemptError::Fatal(anyhow!(
                "remote artifact Content-Length does not match Manifest"
            )));
        }
        progress.phase("download");
        let mut output = File::create(path).map_err(|error| {
            RemoteAttemptError::Fatal(
                Error::new(error).context("failed to create artifact download"),
            )
        })?;
        let copied = copy_remote_with_progress(
            &mut response.take(expected_size + 1),
            &mut output,
            progress,
            expected_size,
        )?;
        output.flush().map_err(|error| {
            RemoteAttemptError::Fatal(
                Error::new(error).context("failed to flush artifact download"),
            )
        })?;
        output.sync_all().map_err(|error| {
            RemoteAttemptError::Fatal(Error::new(error).context("failed to sync artifact download"))
        })?;
        if copied != expected_size {
            return Err(RemoteAttemptError::Retryable {
                reason: "artifact download ended before expected size".to_owned(),
                retry_after: None,
            });
        }
        Ok(())
    })
}

fn write_synced(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = File::create(path)?;
    file.write_all(bytes)?;
    file.flush()?;
    file.sync_all()?;
    Ok(())
}

fn sha256_bytes(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn response_once(client: &Client, url: Url) -> std::result::Result<Response, RemoteAttemptError> {
    let response = client.get(url).send().map_err(|error| {
        if error.is_builder() {
            RemoteAttemptError::Fatal(error.into())
        } else {
            RemoteAttemptError::Retryable {
                reason: transport_reason(&error).to_owned(),
                retry_after: None,
            }
        }
    })?;
    if response.status().is_success() {
        return Ok(response);
    }
    if retryable_status(response.status()) {
        return Err(RemoteAttemptError::Retryable {
            reason: format!("HTTP {}", response.status()),
            retry_after: retry_after(&response),
        });
    }
    Err(RemoteAttemptError::Fatal(anyhow!(
        "remote server returned HTTP {}",
        response.status()
    )))
}

fn retry_remote<T>(
    progress: &Progress,
    phase: &str,
    mut operation: impl FnMut() -> std::result::Result<T, RemoteAttemptError>,
) -> Result<T> {
    for attempt in 1..=MAX_ATTEMPTS {
        match operation() {
            Ok(value) => return Ok(value),
            Err(RemoteAttemptError::Fatal(error)) => return Err(error),
            Err(RemoteAttemptError::Retryable {
                reason,
                retry_after,
            }) if attempt < MAX_ATTEMPTS => {
                let delay = retry_delay(attempt, retry_after);
                progress.retry(phase, attempt + 1, MAX_ATTEMPTS, delay, &reason);
                thread::sleep(delay);
            }
            Err(RemoteAttemptError::Retryable { reason, .. }) => {
                return Err(RemoteUnavailable {
                    attempts: attempt,
                    reason,
                }
                .into());
            }
        }
    }
    unreachable!("retry loop returns on success or the final attempt")
}

fn retry_delay(failed_attempt: u32, retry_after: Option<Duration>) -> Duration {
    if let Some(delay) = retry_after {
        return delay.min(MAX_RETRY_AFTER);
    }
    let cap = RETRY_CAPS[(failed_attempt - 1) as usize];
    let maximum_millis = cap.as_millis() as u64;
    Duration::from_millis(fastrand::u64(0..=maximum_millis))
}

fn retry_after(response: &Response) -> Option<Duration> {
    let value = response.headers().get(RETRY_AFTER)?.to_str().ok()?;
    parse_retry_after(value, SystemTime::now())
}

fn parse_retry_after(value: &str, now: SystemTime) -> Option<Duration> {
    if let Ok(seconds) = value.parse::<u64>() {
        return Some(Duration::from_secs(seconds).min(MAX_RETRY_AFTER));
    }
    let retry_at = httpdate::parse_http_date(value).ok()?;
    Some(
        retry_at
            .duration_since(now)
            .unwrap_or(Duration::ZERO)
            .min(MAX_RETRY_AFTER),
    )
}

fn retryable_status(status: StatusCode) -> bool {
    matches!(
        status,
        StatusCode::REQUEST_TIMEOUT
            | StatusCode::TOO_MANY_REQUESTS
            | StatusCode::INTERNAL_SERVER_ERROR
            | StatusCode::BAD_GATEWAY
            | StatusCode::SERVICE_UNAVAILABLE
            | StatusCode::GATEWAY_TIMEOUT
    )
}

fn transport_reason(error: &reqwest::Error) -> &'static str {
    if error.is_timeout() {
        "request timed out"
    } else if error.is_connect() {
        "connection failed"
    } else if error.is_body() {
        "response body interrupted"
    } else {
        "request transport failed"
    }
}

fn copy_remote_with_progress<R: Read>(
    reader: &mut R,
    writer: &mut File,
    progress: &Progress,
    expected_size: u64,
) -> std::result::Result<u64, RemoteAttemptError> {
    let mut buffer = vec![0_u8; 256 * 1024];
    let mut copied = 0_u64;
    loop {
        let size = reader
            .read(&mut buffer)
            .map_err(|_| RemoteAttemptError::Retryable {
                reason: "artifact response body interrupted".to_owned(),
                retry_after: None,
            })?;
        if size == 0 {
            break;
        }
        writer.write_all(&buffer[..size]).map_err(|error| {
            RemoteAttemptError::Fatal(
                Error::new(error).context("failed to write artifact download"),
            )
        })?;
        copied += size as u64;
        progress.update(copied, Some(expected_size));
    }
    Ok(copied)
}

fn require_secure_or_loopback(url: &Url) -> Result<()> {
    let loopback = matches!(url.host_str(), Some("127.0.0.1" | "::1" | "localhost"));
    if url.scheme() != "https" && !loopback {
        bail!("remote Registry and artifacts require HTTPS");
    }
    Ok(())
}

fn require_same_origin(base: &Url, target: &Url) -> Result<()> {
    if base.scheme() != target.scheme()
        || base.host_str() != target.host_str()
        || base.port_or_known_default() != target.port_or_known_default()
    {
        bail!("remote URL escaped the trusted Registry origin");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_cross_origin_and_insecure_urls() {
        let registry = Url::parse("https://data.example/registry.json").unwrap();
        let same_origin = Url::parse("https://data.example/releases/manifest.json").unwrap();
        let other_origin = Url::parse("https://cdn.example/manifest.json").unwrap();
        assert!(require_same_origin(&registry, &same_origin).is_ok());
        assert!(require_same_origin(&registry, &other_origin).is_err());
        assert!(require_secure_or_loopback(&Url::parse("http://data.example/x").unwrap()).is_err());
        assert!(
            require_secure_or_loopback(&Url::parse("http://127.0.0.1:8080/x").unwrap()).is_ok()
        );
    }

    #[test]
    fn retries_only_transient_http_statuses() {
        for status in [408, 429, 500, 502, 503, 504] {
            assert!(retryable_status(StatusCode::from_u16(status).unwrap()));
        }
        for status in [400, 401, 403, 404, 409, 422] {
            assert!(!retryable_status(StatusCode::from_u16(status).unwrap()));
        }
    }

    #[test]
    fn bounds_full_jitter_and_retry_after_delays() {
        for failed_attempt in 1..=3 {
            for _ in 0..100 {
                assert!(
                    retry_delay(failed_attempt, None) <= RETRY_CAPS[failed_attempt as usize - 1]
                );
            }
        }
        assert_eq!(
            retry_delay(1, Some(Duration::from_secs(60))),
            MAX_RETRY_AFTER
        );

        let now = SystemTime::UNIX_EPOCH + Duration::from_secs(1_000_000);
        assert_eq!(parse_retry_after("7", now), Some(Duration::from_secs(7)));
        assert_eq!(
            parse_retry_after(&httpdate::fmt_http_date(now + Duration::from_secs(5)), now),
            Some(Duration::from_secs(5))
        );
        assert_eq!(
            parse_retry_after(&httpdate::fmt_http_date(now - Duration::from_secs(5)), now),
            Some(Duration::ZERO)
        );
        assert_eq!(parse_retry_after("invalid", now), None);
    }
}
