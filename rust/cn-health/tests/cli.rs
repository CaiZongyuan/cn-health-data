use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use predicates::prelude::*;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tempfile::TempDir;

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

    command(&data_dir)
        .args(["dataset", "list", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("nhsa-drugs"))
        .stdout(predicate::str::contains("nhc-icd10-clinical"));

    let drug_output = command(&data_dir)
        .args(["drug", "search", "二甲双胍", "--json"])
        .output()
        .unwrap();
    assert!(drug_output.status.success());
    let drug_json: Value = serde_json::from_slice(&drug_output.stdout).unwrap();
    assert_eq!(drug_json["items"][0]["code"], "XA01");

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
