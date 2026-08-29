use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::Path;

use anyhow::{Context, Result, bail};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use reqwest::Url;
use reqwest::blocking::Client;
use reqwest::redirect::Policy;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use tempfile::TempDir;

use crate::manifest::Manifest;
use crate::storage::{InstalledDataset, install_manifest};

const MAX_METADATA_BYTES: u64 = 10 * 1024 * 1024;

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
    let client = Client::builder().redirect(Policy::none()).build()?;
    let registry_url = Url::parse(registry_url)?;
    require_secure_or_loopback(&registry_url)?;
    let registry_bytes = fetch_bytes(&client, registry_url.clone(), MAX_METADATA_BYTES)?;
    let registry: Registry = serde_json::from_slice(&registry_bytes)?;
    if registry.schema_version != 1 || registry.signature.algorithm != "Ed25519" {
        bail!("unsupported Registry signature or schema");
    }
    let public_bytes = fs::read(public_key_path)?;
    let public_array: [u8; 32] = public_bytes
        .as_slice()
        .try_into()
        .context("Registry public key must contain 32 raw bytes")?;
    let key_id = hex::encode(Sha256::digest(&public_bytes));
    if !key_id.starts_with(&registry.signature.key_id) {
        bail!("Registry keyId does not match the supplied public key");
    }
    let signature_url = registry_url.join(&registry.signature.url)?;
    require_same_origin(&registry_url, &signature_url)?;
    let signature_bytes = fetch_bytes(&client, signature_url, 64)?;
    let signature = Signature::from_slice(&signature_bytes)?;
    VerifyingKey::from_bytes(&public_array)?.verify(&registry_bytes, &signature)?;

    let dataset = registry
        .datasets
        .get(dataset_id)
        .with_context(|| format!("Dataset {dataset_id} is not present in Registry"))?;
    let recommended = dataset
        .recommended_release
        .as_deref()
        .context("Dataset has no recommended Release")?;
    let release = dataset
        .releases
        .iter()
        .find(|release| release.id == recommended)
        .context("recommended Release is missing from Registry")?;
    if release.revoked {
        bail!("recommended Release is revoked");
    }
    let manifest_url = Url::parse(&release.manifest_url)?;
    require_secure_or_loopback(&manifest_url)?;
    require_same_origin(&registry_url, &manifest_url)?;
    let manifest_bytes = fetch_bytes(&client, manifest_url.clone(), MAX_METADATA_BYTES)?;
    if sha256_bytes(&manifest_bytes) != release.manifest_sha256 {
        bail!("Manifest SHA256 does not match signed Registry");
    }
    let manifest: Manifest = serde_json::from_slice(&manifest_bytes)?;
    if manifest.dataset.id != dataset_id || manifest.release.id != release.id {
        bail!("Manifest identity does not match signed Registry");
    }
    if !manifest.rights.release_eligible {
        bail!("remote Manifest is not release-eligible");
    }
    let artifact = manifest.compressed_sqlite()?;
    let artifact_url = manifest_url.join(&artifact.url)?;
    require_same_origin(&manifest_url, &artifact_url)?;
    let temporary = TempDir::new()?;
    let manifest_path = temporary.path().join("manifest.json");
    let artifact_path = temporary.path().join(&artifact.name);
    write_synced(&manifest_path, &manifest_bytes)?;
    download_exact(&client, artifact_url, &artifact_path, artifact.size_bytes)?;
    install_manifest(
        data_dir,
        &manifest_path,
        &format!("signed-registry:{}", registry.signature.key_id),
    )
}

fn fetch_bytes(client: &Client, url: Url, maximum: u64) -> Result<Vec<u8>> {
    let response = successful_response(client, url)?;
    if response
        .content_length()
        .is_some_and(|length| length > maximum)
    {
        bail!("remote response exceeds size limit");
    }
    let mut bytes = Vec::new();
    response.take(maximum + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > maximum {
        bail!("remote response exceeds size limit");
    }
    Ok(bytes)
}

fn download_exact(client: &Client, url: Url, path: &Path, expected_size: u64) -> Result<()> {
    let response = successful_response(client, url)?;
    if response
        .content_length()
        .is_some_and(|length| length != expected_size)
    {
        bail!("remote artifact Content-Length does not match Manifest");
    }
    let mut output = File::create(path)?;
    let copied = std::io::copy(&mut response.take(expected_size + 1), &mut output)?;
    output.flush()?;
    output.sync_all()?;
    if copied != expected_size {
        bail!("remote artifact size does not match Manifest");
    }
    Ok(())
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

fn successful_response(client: &Client, url: Url) -> Result<reqwest::blocking::Response> {
    let response = client.get(url).send()?;
    if !response.status().is_success() {
        bail!("remote server returned HTTP {}", response.status());
    }
    Ok(response)
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
}
