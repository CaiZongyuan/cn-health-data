use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use ed25519_dalek::{Signer, SigningKey};
use predicates::prelude::*;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tempfile::TempDir;
use tiny_http::{Response, Server};

fn sha256(path: &Path) -> String {
    let mut digest = Sha256::new();
    let mut file = File::open(path).unwrap();
    let mut buffer = [0_u8; 8192];
    loop {
        let size = file.read(&mut buffer).unwrap();
        if size == 0 {
            break;
        }
        digest.update(&buffer[..size]);
    }
    hex::encode(digest.finalize())
}

fn fixture_release(root: &Path, dataset_id: &str) -> PathBuf {
    let release = root.join(dataset_id);
    fs::create_dir_all(&release).unwrap();
    let database = release.join("data.sqlite");
    let connection = Connection::open(&database).unwrap();
    if dataset_id == "nhsa-drugs" {
        connection
            .execute_batch(
                "
                CREATE TABLE drug(
                    code TEXT PRIMARY KEY,
                    registered_name TEXT NOT NULL,
                    trade_name TEXT NOT NULL,
                    market_status TEXT NOT NULL,
                    insurance_name TEXT
                );
                CREATE VIRTUAL TABLE drug_fts USING fts5(
                    registered_name, trade_name, insurance_name,
                    content='drug', content_rowid='rowid', tokenize='trigram'
                );
                CREATE TABLE drug_search_bigram(
                    term TEXT NOT NULL, code TEXT NOT NULL,
                    PRIMARY KEY(term, code)
                ) WITHOUT ROWID;
                PRAGMA application_id=1129203780;
                PRAGMA user_version=1;
                ",
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO drug VALUES (?1, ?2, '无', '上市', ?3)",
                params!["XA01", "盐酸二甲双胍片", "二甲双胍"],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO drug_fts(rowid, registered_name, trade_name, insurance_name)
                 SELECT rowid, registered_name, trade_name, insurance_name FROM drug",
                [],
            )
            .unwrap();
        connection
            .execute("INSERT INTO drug_search_bigram VALUES ('二甲', 'XA01')", [])
            .unwrap();
    } else {
        connection
            .execute_batch(
                "
                CREATE TABLE diagnosis(
                    code TEXT PRIMARY KEY,
                    main_code TEXT,
                    additional_code TEXT,
                    name TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE diagnosis_fts USING fts5(
                    name, content='diagnosis', content_rowid='rowid', tokenize='trigram'
                );
                CREATE TABLE diagnosis_search_bigram(
                    term TEXT NOT NULL, code TEXT NOT NULL,
                    PRIMARY KEY(term, code)
                ) WITHOUT ROWID;
                PRAGMA application_id=1129203780;
                PRAGMA user_version=1;
                ",
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO diagnosis VALUES ('E11.900', 'E11.900', NULL, '2型糖尿病')",
                [],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO diagnosis_fts(rowid, name) SELECT rowid, name FROM diagnosis",
                [],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO diagnosis_search_bigram VALUES ('糖尿', 'E11.900')",
                [],
            )
            .unwrap();
    }
    drop(connection);

    let compressed = release.join("data.sqlite.zst");
    let mut input = File::open(&database).unwrap();
    let mut output = File::create(&compressed).unwrap();
    zstd::stream::copy_encode(&mut input, &mut output, 3).unwrap();
    output.flush().unwrap();
    let manifest = json!({
        "schemaVersion": 1,
        "release": {
            "id": format!("{dataset_id}@fixture.r1"),
            "sequence": 1,
            "storageKey": "fixture.r1",
            "buildRevision": 1,
            "revoked": false
        },
        "dataset": {"id": dataset_id, "sourceVersion": "fixture"},
        "artifacts": [{
            "name": "data.sqlite.zst",
            "url": "data.sqlite.zst",
            "sha256": sha256(&compressed),
            "sizeBytes": fs::metadata(&compressed).unwrap().len(),
            "uncompressedName": "data.sqlite",
            "uncompressedSha256": sha256(&database),
            "uncompressedSizeBytes": fs::metadata(&database).unwrap().len()
        }],
        "rights": {"redistribution": "review-required", "releaseEligible": false}
    });
    let manifest_path = release.join("manifest.json");
    fs::write(
        &manifest_path,
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    manifest_path
}

fn command(data_dir: &Path) -> Command {
    let mut command = Command::cargo_bin("cn-health").unwrap();
    command.arg("--data-dir").arg(data_dir);
    command
}

#[test]
fn installs_lists_and_queries_local_candidates() {
    let temporary = TempDir::new().unwrap();
    let fixtures = temporary.path().join("fixtures");
    let data_dir = temporary.path().join("data");
    let drug_manifest = fixture_release(&fixtures, "nhsa-drugs");
    let diagnosis_manifest = fixture_release(&fixtures, "nhc-icd10-clinical");

    command(&data_dir)
        .args(["dataset", "install", "--local-manifest"])
        .arg(&drug_manifest)
        .assert()
        .success();
    command(&data_dir)
        .args(["dataset", "install", "--local-manifest"])
        .arg(&diagnosis_manifest)
        .assert()
        .success();

    let second_manifest = fixture_release(&temporary.path().join("fixtures-v2"), "nhsa-drugs");
    let mut second: Value = serde_json::from_slice(&fs::read(&second_manifest).unwrap()).unwrap();
    second["release"]["id"] = Value::String("nhsa-drugs@fixture.r2".to_owned());
    second["release"]["storageKey"] = Value::String("fixture.r2".to_owned());
    second["release"]["sequence"] = Value::from(2);
    fs::write(
        &second_manifest,
        serde_json::to_vec_pretty(&second).unwrap(),
    )
    .unwrap();
    command(&data_dir)
        .args(["dataset", "install", "--local-manifest"])
        .arg(&second_manifest)
        .assert()
        .success();
    command(&data_dir)
        .args(["dataset", "versions", "nhsa-drugs", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("fixture.r1"))
        .stdout(predicate::str::contains("fixture.r2"));
    command(&data_dir)
        .args(["dataset", "use", "nhsa-drugs", "nhsa-drugs@fixture.r1"])
        .assert()
        .success();

    command(&data_dir)
        .args(["dataset", "list", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("nhsa-drugs"))
        .stdout(predicate::str::contains("nhc-icd10-clinical"));

    let drug_output = command(&data_dir)
        .args(["drug", "search", "二甲双胍", "--limit", "1", "--json"])
        .output()
        .unwrap();
    assert!(drug_output.status.success());
    let drug_json: Value = serde_json::from_slice(&drug_output.stdout).unwrap();
    assert_eq!(drug_json["items"][0]["code"], "XA01");
    assert_eq!(drug_json["page"]["truncated"], false);

    let diagnosis_output = command(&data_dir)
        .args(["diagnosis", "search", "糖尿病", "--json"])
        .output()
        .unwrap();
    assert!(diagnosis_output.status.success());
    let diagnosis_json: Value = serde_json::from_slice(&diagnosis_output.stdout).unwrap();
    assert_eq!(diagnosis_json["items"][0]["code"], "E11.900");

    command(&data_dir)
        .args(["drug", "get", "XA01", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("盐酸二甲双胍片"));
}

#[test]
fn emits_json_error_for_missing_dataset() {
    let temporary = TempDir::new().unwrap();
    let output = command(&temporary.path().join("data"))
        .args(["diagnosis", "search", "糖尿病", "--json"])
        .output()
        .unwrap();

    assert_eq!(output.status.code(), Some(3));
    assert!(output.stderr.is_empty());
    let error: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(error["error"]["code"], "DATASET_NOT_INSTALLED");
}

#[test]
fn rejects_corrupt_compressed_artifact_without_installing() {
    let temporary = TempDir::new().unwrap();
    let manifest = fixture_release(&temporary.path().join("fixtures"), "nhsa-drugs");
    let compressed = manifest.parent().unwrap().join("data.sqlite.zst");
    fs::OpenOptions::new()
        .append(true)
        .open(compressed)
        .unwrap()
        .write_all(b"corrupt")
        .unwrap();
    let data_dir = temporary.path().join("data");

    command(&data_dir)
        .args(["dataset", "install", "--local-manifest"])
        .arg(manifest)
        .assert()
        .failure()
        .stderr(predicate::str::contains("SHA256"));
    assert!(!data_dir.join("datasets/nhsa-drugs/current.json").exists());
}

#[test]
fn installs_from_a_signed_registry() {
    let temporary = TempDir::new().unwrap();
    let manifest_path = fixture_release(&temporary.path().join("fixtures"), "nhsa-drugs");
    let mut manifest: Value = serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
    manifest["rights"]["releaseEligible"] = Value::Bool(true);
    let manifest_bytes = serde_json::to_vec(&manifest).unwrap();
    fs::write(&manifest_path, &manifest_bytes).unwrap();
    let compressed = manifest_path.parent().unwrap().join("data.sqlite.zst");

    let server = Server::http("127.0.0.1:0").unwrap();
    let base_url = format!("http://{}", server.server_addr());
    let manifest_sha256 = hex::encode(Sha256::digest(&manifest_bytes));
    let registry = json!({
        "schemaVersion": 1,
        "datasets": {
            "nhsa-drugs": {
                "recommendedRelease": "nhsa-drugs@fixture.r1",
                "releases": [{
                    "id": "nhsa-drugs@fixture.r1",
                    "manifestUrl": format!("{base_url}/manifest.json"),
                    "manifestSha256": manifest_sha256,
                    "revoked": false
                }]
            }
        },
        "signature": {
            "algorithm": "Ed25519",
            "keyId": "placeholder",
            "url": "registry.json.sig"
        }
    });
    let signing_key = SigningKey::from_bytes(&[7_u8; 32]);
    let public_bytes = signing_key.verifying_key().to_bytes();
    let key_id = hex::encode(Sha256::digest(public_bytes));
    let mut registry = registry;
    registry["signature"]["keyId"] = Value::String(key_id[..16].to_owned());
    let registry_bytes = serde_json::to_vec(&registry).unwrap();
    let signature_bytes = signing_key.sign(&registry_bytes).to_bytes().to_vec();
    let compressed_bytes = fs::read(compressed).unwrap();
    let server_thread = std::thread::spawn(move || {
        for _ in 0..4 {
            let request = server.recv().unwrap();
            let body = match request.url() {
                "/registry.json" => registry_bytes.clone(),
                "/registry.json.sig" => signature_bytes.clone(),
                "/manifest.json" => manifest_bytes.clone(),
                "/data.sqlite.zst" => compressed_bytes.clone(),
                path => panic!("unexpected request {path}"),
            };
            request.respond(Response::from_data(body)).unwrap();
        }
    });
    let public_key_path = temporary.path().join("registry.pub");
    fs::write(&public_key_path, public_bytes).unwrap();
    let data_dir = temporary.path().join("data");

    command(&data_dir)
        .args(["dataset", "install", "nhsa-drugs", "--registry"])
        .arg(format!("{base_url}/registry.json"))
        .arg("--public-key")
        .arg(public_key_path)
        .assert()
        .success();
    server_thread.join().unwrap();
    command(&data_dir)
        .args(["dataset", "list", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("signed-registry"));
}
