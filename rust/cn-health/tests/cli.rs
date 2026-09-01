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
    } else if dataset_id == "nhc-icd10-clinical" {
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
    } else if dataset_id == "laboratory-cn" {
        connection
            .execute_batch(
                "
                CREATE TABLE laboratory_concept(
                    code TEXT PRIMARY KEY,
                    system TEXT NOT NULL,
                    terminology_version TEXT NOT NULL,
                    display_zh TEXT NOT NULL,
                    category TEXT NOT NULL,
                    specimen TEXT NOT NULL,
                    result_type TEXT NOT NULL,
                    ucum_unit TEXT,
                    status TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE laboratory_concept_fts USING fts5(
                    display_zh, content='laboratory_concept', content_rowid='rowid', tokenize='trigram'
                );
                CREATE TABLE laboratory_concept_search_bigram(
                    term TEXT NOT NULL, code TEXT NOT NULL,
                    PRIMARY KEY(term, code)
                ) WITHOUT ROWID;
                INSERT INTO laboratory_concept VALUES
                    ('2339-0', 'http://loinc.org', '2.83', '血糖', 'chemistry', 'blood',
                     'quantity', 'mg/dL', 'active'),
                    ('4548-4', 'http://loinc.org', '2.83', '糖化血红蛋白', 'chemistry', 'blood',
                     'quantity', '%', 'active');
                INSERT INTO laboratory_concept_fts(rowid, display_zh)
                    SELECT rowid, display_zh FROM laboratory_concept;
                INSERT INTO laboratory_concept_search_bigram VALUES ('血糖', '2339-0');
                PRAGMA application_id=1129203780;
                PRAGMA user_version=1;
                ",
            )
            .unwrap();
    } else {
        connection
            .execute_batch(
                "
                CREATE TABLE loinc(
                    code TEXT PRIMARY KEY,
                    long_common_name TEXT NOT NULL,
                    zh_display TEXT
                );
                CREATE VIRTUAL TABLE loinc_fts USING fts5(
                    long_common_name, zh_display,
                    content='loinc', content_rowid='rowid', tokenize='trigram'
                );
                CREATE TABLE loinc_search_bigram(
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
                "INSERT INTO loinc VALUES ('4548-4', 'Hemoglobin A1c', '糖化血红蛋白')",
                [],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO loinc_fts(rowid, long_common_name, zh_display)
                 SELECT rowid, long_common_name, zh_display FROM loinc",
                [],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO loinc_search_bigram VALUES ('糖化', '4548-4')",
                [],
            )
            .unwrap();
    }
    drop(connection);

    finish_fixture_release(&release, dataset_id, &database, "0.2.0")
}

fn finish_fixture_release(
    release: &Path,
    dataset_id: &str,
    database: &Path,
    minimum_cli_version: &str,
) -> PathBuf {
    let compressed = release.join("data.sqlite.zst");
    let mut input = File::open(database).unwrap();
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
            "uncompressedSha256": sha256(database),
            "uncompressedSizeBytes": fs::metadata(database).unwrap().len()
        }],
        "rights": {"redistribution": "review-required", "releaseEligible": false},
        "runtime": {
            "minimumCliVersion": minimum_cli_version,
            "minimumSQLiteVersion": "3.34.0"
        }
    });
    let manifest_path = release.join("manifest.json");
    fs::write(
        &manifest_path,
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    manifest_path
}

fn fixture_laboratory_v2(root: &Path) -> PathBuf {
    let dataset_id = "laboratory-cn";
    let release = root.join(dataset_id);
    fs::create_dir_all(&release).unwrap();
    let database = release.join("data.sqlite");
    let connection = Connection::open(&database).unwrap();
    connection
        .execute_batch(
            "
            CREATE TABLE laboratory_test(
                code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                analyte TEXT NOT NULL, specimen TEXT NOT NULL, scale TEXT NOT NULL,
                result_kind TEXT NOT NULL, unit_display TEXT, unit_ucum TEXT,
                precision INTEGER NOT NULL, healthy_strategy TEXT NOT NULL,
                loinc_code TEXT, status TEXT NOT NULL, source_version TEXT NOT NULL
            );
            CREATE TABLE laboratory_reference(
                test_code TEXT NOT NULL, sex TEXT NOT NULL, reference_kind TEXT NOT NULL,
                low_value REAL, high_value REAL, normal_value TEXT, simulation_low REAL,
                simulation_high REAL, source_type TEXT NOT NULL, source_standard TEXT NOT NULL,
                source_version TEXT NOT NULL, source_location TEXT NOT NULL, notes TEXT NOT NULL,
                PRIMARY KEY(test_code, sex)
            );
            CREATE TABLE laboratory_panel(
                code TEXT PRIMARY KEY, name TEXT NOT NULL, specimen TEXT NOT NULL,
                status TEXT NOT NULL, source_type TEXT NOT NULL,
                source_location TEXT NOT NULL, notes TEXT NOT NULL
            );
            CREATE TABLE laboratory_panel_member(
                panel_code TEXT NOT NULL, test_code TEXT NOT NULL, sort_order INTEGER NOT NULL,
                PRIMARY KEY(panel_code, test_code)
            );
            CREATE VIRTUAL TABLE laboratory_test_fts USING fts5(
                name, analyte, category,
                content='laboratory_test', content_rowid='rowid', tokenize='trigram'
            );
            CREATE TABLE laboratory_test_search_bigram(
                term TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(term, code)
            ) WITHOUT ROWID;
            CREATE VIRTUAL TABLE laboratory_panel_fts USING fts5(
                name, content='laboratory_panel', content_rowid='rowid', tokenize='trigram'
            );
            CREATE TABLE laboratory_panel_search_bigram(
                term TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(term, code)
            ) WITHOUT ROWID;
            INSERT INTO laboratory_test VALUES
                ('0100101A', '白细胞计数', '血细胞分析', '白细胞(数量)', '全血', '定量',
                 'quantity', '×10^9/L', '10*9/L', 1, 'uniform', '6690-2', 'active',
                 '2026-09-01'),
                ('0100201A', '红细胞计数', '血细胞分析', '红细胞(数量)', '全血', '定量',
                 'quantity', '×10^12/L', '10*12/L', 1, 'uniform', '789-8', 'active',
                 '2026-09-01');
            INSERT INTO laboratory_reference VALUES
                ('0100101A', 'all', 'range', 3.5, 9.5, NULL, 3.5, 9.5,
                 'national-standard', 'WS/T 405-2012', '2012', '表 1', '成人静脉血'),
                ('0100201A', 'male', 'range', 4.3, 5.8, NULL, 4.3, 5.8,
                 'national-standard', 'WS/T 405-2012', '2012', '表 1', '成年男性'),
                ('0100201A', 'female', 'range', 3.8, 5.1, NULL, 3.8, 5.1,
                 'national-standard', 'WS/T 405-2012', '2012', '表 1', '成年女性');
            INSERT INTO laboratory_panel VALUES
                ('CN-LAB-CBC-5DIFF', '血常规（五分类）', '全血', 'active',
                 'project-authored', 'fixture/row 6', 'fixture');
            INSERT INTO laboratory_panel_member VALUES
                ('CN-LAB-CBC-5DIFF', '0100101A', 1),
                ('CN-LAB-CBC-5DIFF', '0100201A', 2);
            INSERT INTO laboratory_test_fts(rowid, name, analyte, category)
                SELECT rowid, name, analyte, category FROM laboratory_test;
            INSERT INTO laboratory_test_search_bigram VALUES ('白细', '0100101A');
            INSERT INTO laboratory_panel_fts(rowid, name)
                SELECT rowid, name FROM laboratory_panel;
            INSERT INTO laboratory_panel_search_bigram VALUES ('血常', 'CN-LAB-CBC-5DIFF');
            PRAGMA application_id=1129203780;
            PRAGMA user_version=2;
            ",
        )
        .unwrap();
    drop(connection);
    finish_fixture_release(&release, dataset_id, &database, "0.4.0")
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
    let loinc_manifest = fixture_release(&fixtures, "loinc-zh-cn");
    let laboratory_manifest = fixture_release(&fixtures, "laboratory-cn");

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
        .args(["dataset", "install", "--local-manifest"])
        .arg(&loinc_manifest)
        .assert()
        .success();
    command(&data_dir)
        .args(["dataset", "install", "--local-manifest"])
        .arg(&laboratory_manifest)
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

    let loinc_output = command(&data_dir)
        .args(["loinc", "search", "糖化血红蛋白", "--json"])
        .output()
        .unwrap();
    assert!(loinc_output.status.success());
    let loinc_json: Value = serde_json::from_slice(&loinc_output.stdout).unwrap();
    assert_eq!(loinc_json["items"][0]["code"], "4548-4");

    let laboratory_output = command(&data_dir)
        .args(["laboratory", "search", "血糖", "--json"])
        .output()
        .unwrap();
    assert!(laboratory_output.status.success());
    let laboratory_json: Value = serde_json::from_slice(&laboratory_output.stdout).unwrap();
    assert_eq!(laboratory_json["items"][0]["code"], "2339-0");
    assert_eq!(laboratory_json["items"][0]["ucumUnit"], "mg/dL");

    command(&data_dir)
        .args(["laboratory", "get", "4548-4", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("糖化血红蛋白"));

    command(&data_dir)
        .args(["drug", "get", "XA01", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("盐酸二甲双胍片"));
}

#[test]
fn queries_schema_v2_laboratory_references_and_panels() {
    let temporary = TempDir::new().unwrap();
    let data_dir = temporary.path().join("data");
    let manifest = fixture_laboratory_v2(&temporary.path().join("fixtures-v2"));
    command(&data_dir)
        .args(["dataset", "install", "--local-manifest"])
        .arg(manifest)
        .assert()
        .success();

    let search = command(&data_dir)
        .args(["laboratory", "search", "白细", "--json"])
        .output()
        .unwrap();
    assert!(search.status.success());
    let search_json: Value = serde_json::from_slice(&search.stdout).unwrap();
    assert_eq!(search_json["items"][0]["code"], "0100101A");
    assert_eq!(search_json["items"][0]["unitUcum"], "10*9/L");
    assert_eq!(search_json["items"][0]["references"][0]["lowValue"], 3.5);

    let get = command(&data_dir)
        .args(["laboratory", "get", "0100201A", "--json"])
        .output()
        .unwrap();
    assert!(get.status.success());
    let get_json: Value = serde_json::from_slice(&get.stdout).unwrap();
    assert_eq!(get_json["name"], "红细胞计数");
    assert_eq!(get_json["rank"], 1);
    assert_eq!(get_json["references"][0]["sex"], "female");
    assert_eq!(get_json["references"][1]["sex"], "male");

    command(&data_dir)
        .args(["laboratory", "panel", "search", "血常规", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("CN-LAB-CBC-5DIFF"));

    let panel = command(&data_dir)
        .args(["laboratory", "panel", "get", "CN-LAB-CBC-5DIFF", "--json"])
        .output()
        .unwrap();
    assert!(panel.status.success());
    let panel_json: Value = serde_json::from_slice(&panel.stdout).unwrap();
    assert_eq!(panel_json["memberCount"], 2);
    assert_eq!(panel_json["members"][0]["sortOrder"], 1);
    assert_eq!(panel_json["members"][0]["test"]["code"], "0100101A");
    assert_eq!(
        panel_json["members"][1]["test"]["references"][1]["sex"],
        "male"
    );
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
fn doctor_reports_an_uninitialized_data_directory() {
    let temporary = TempDir::new().unwrap();
    let output = command(&temporary.path().join("data"))
        .args(["doctor", "--json"])
        .output()
        .unwrap();

    assert_eq!(output.status.code(), Some(1));
    let report: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["command"], "doctor");
    assert_eq!(report["ok"], false);
    assert_eq!(report["checks"][0]["id"], "dataset:geography-cn");
}

#[test]
fn rejects_incompatible_or_invalid_manifest_cli_versions() {
    for minimum in ["99.0.0", "next"] {
        let temporary = TempDir::new().unwrap();
        let manifest = fixture_release(&temporary.path().join("fixtures"), "laboratory-cn");
        let mut value: Value = serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
        value["runtime"]["minimumCliVersion"] = Value::String(minimum.to_owned());
        fs::write(&manifest, serde_json::to_vec_pretty(&value).unwrap()).unwrap();

        command(&temporary.path().join("data"))
            .args(["dataset", "install", "--local-manifest"])
            .arg(manifest)
            .assert()
            .code(6)
            .stderr(predicate::str::contains(if minimum == "next" {
                "minimumCliVersion"
            } else {
                "CLI_VERSION_INCOMPATIBLE"
            }));
    }
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
fn initializes_queries_and_diagnoses_from_a_signed_registry() {
    let temporary = TempDir::new().unwrap();
    let manifest_path = fixture_release(&temporary.path().join("fixtures"), "laboratory-cn");
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
            "laboratory-cn": {
                "recommendedRelease": "laboratory-cn@fixture.r1",
                "releases": [{
                    "id": "laboratory-cn@fixture.r1",
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
        for _ in 0..8 {
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

    let first = command(&data_dir)
        .args(["init", "--only", "laboratory-cn", "--registry"])
        .arg(format!("{base_url}/registry.json"))
        .arg("--public-key")
        .arg(&public_key_path)
        .arg("--json")
        .output()
        .unwrap();
    assert!(first.status.success());
    let first_json: Value = serde_json::from_slice(&first.stdout).unwrap();
    assert_eq!(first_json["schemaVersion"], 2);
    assert_eq!(first_json["selection"], "only");
    assert_eq!(first_json["items"][0]["status"], "installed");

    let second = command(&data_dir)
        .args(["init", "--only", "laboratory-cn", "--registry"])
        .arg(format!("{base_url}/registry.json"))
        .arg("--public-key")
        .arg(&public_key_path)
        .arg("--json")
        .output()
        .unwrap();
    assert!(second.status.success());
    let second_json: Value = serde_json::from_slice(&second.stdout).unwrap();
    assert_eq!(second_json["items"][0]["status"], "already-installed");
    server_thread.join().unwrap();

    command(&data_dir)
        .args(["laboratory", "search", "血糖", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("2339-0"));
    command(&data_dir)
        .args(["dataset", "list", "--json"])
        .assert()
        .success()
        .stdout(predicate::str::contains("signed-registry"));
}

#[test]
fn init_rejects_unknown_dataset_before_network_access() {
    let temporary = TempDir::new().unwrap();
    command(&temporary.path().join("data"))
        .args(["init", "--only", "not-a-dataset", "--json"])
        .assert()
        .failure()
        .stdout(predicate::str::contains(
            "unknown or unavailable Dataset ID",
        ));
}
