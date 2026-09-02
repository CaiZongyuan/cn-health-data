mod manifest;
mod materialize;
mod progress;
mod query;
mod registry;
mod storage;

use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand};
use directories::ProjectDirs;
use serde::Serialize;
use serde_json::json;

use crate::materialize::materialize_release;
use crate::query::{
    SearchResults, diagnosis_get, diagnosis_search, drug_get, drug_search, laboratory_get,
    laboratory_health_check, laboratory_panel_get, laboratory_panel_search, laboratory_search,
    loinc_get, loinc_search,
};
use crate::registry::{install_remote, install_remote_with_key};
use crate::storage::{
    activate_release, current_database, install_local, list_installed, list_versions,
};

const STARTER_DATASET_ID: &str = "laboratory-cn";
const DEFAULT_DATASET_IDS: [&str; 8] = [
    "geography-cn",
    "laboratory-cn",
    "loinc-zh-cn",
    "names-cn",
    "nhc-icd10-clinical",
    "nhc-lab-tests",
    "nhsa-drugs",
    "population-cn",
];
const DEFAULT_REGISTRY_URL: &str =
    "https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/distribution/registry.json";
const DEFAULT_REGISTRY_PUBLIC_KEY: &[u8; 32] = include_bytes!("../../../distribution/registry.pub");

#[derive(Parser)]
#[command(
    name = "cn-health",
    version,
    about = "Local CN Health reference data runtime"
)]
struct Cli {
    #[arg(long, global = true)]
    data_dir: Option<PathBuf>,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Init(InitArgs),
    Doctor(DoctorArgs),
    Dataset(DatasetArgs),
    Drug(LookupArgs),
    Diagnosis(LookupArgs),
    Loinc(LookupArgs),
    Laboratory(LaboratoryArgs),
}

#[derive(Args)]
struct InitArgs {
    #[arg(long, value_delimiter = ',')]
    only: Vec<String>,
    #[arg(long, requires = "public_key")]
    registry: Option<String>,
    #[arg(long, requires = "registry")]
    public_key: Option<PathBuf>,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct DoctorArgs {
    #[arg(long)]
    json: bool,
}

#[derive(Serialize)]
struct DoctorCheck {
    id: String,
    ok: bool,
}

#[derive(Args)]
struct DatasetArgs {
    #[command(subcommand)]
    command: DatasetCommand,
}

#[derive(Subcommand)]
enum DatasetCommand {
    Install {
        dataset_id: Option<String>,
        #[arg(long)]
        local_manifest: Option<PathBuf>,
        #[arg(long)]
        registry: Option<String>,
        #[arg(long)]
        public_key: Option<PathBuf>,
    },
    List {
        #[arg(long)]
        json: bool,
    },
    Materialize {
        dataset_id: String,
        release_id: String,
        #[arg(long)]
        registry: String,
        #[arg(long)]
        public_key: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        json: bool,
    },
    Info {
        dataset_id: String,
        #[arg(long)]
        json: bool,
    },
    Versions {
        dataset_id: String,
        #[arg(long)]
        json: bool,
    },
    Use {
        dataset_id: String,
        release_id: String,
    },
}

#[derive(Args)]
struct LookupArgs {
    #[command(subcommand)]
    command: LookupCommand,
}

#[derive(Args)]
struct LaboratoryArgs {
    #[command(subcommand)]
    command: LaboratoryCommand,
}

#[derive(Subcommand)]
enum LaboratoryCommand {
    Search {
        query: String,
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long)]
        json: bool,
    },
    Get {
        code: String,
        #[arg(long)]
        json: bool,
    },
    Panel(LaboratoryPanelArgs),
}

#[derive(Args)]
struct LaboratoryPanelArgs {
    #[command(subcommand)]
    command: LookupCommand,
}

#[derive(Subcommand)]
enum LookupCommand {
    Search {
        query: String,
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long)]
        json: bool,
    },
    Get {
        code: String,
        #[arg(long)]
        json: bool,
    },
}

fn main() {
    let cli = Cli::parse();
    let json_output = cli.wants_json();
    match run(cli) {
        Ok(true) => {}
        Ok(false) => std::process::exit(1),
        Err(error) => {
            let message = format!("{error:#}");
            let (code, exit_code) = classify_error(&message);
            if json_output {
                println!(
                    "{}",
                    serde_json::to_string(&json!({
                        "schemaVersion": 1,
                        "error": {"code": code, "message": message}
                    }))
                    .expect("JSON error serialization cannot fail")
                );
            } else {
                eprintln!("{message}");
            }
            std::process::exit(exit_code);
        }
    }
}

impl Cli {
    fn wants_json(&self) -> bool {
        match &self.command {
            Command::Init(args) => args.json,
            Command::Doctor(args) => args.json,
            Command::Dataset(DatasetArgs { command }) => match command {
                DatasetCommand::List { json }
                | DatasetCommand::Info { json, .. }
                | DatasetCommand::Versions { json, .. }
                | DatasetCommand::Materialize { json, .. } => *json,
                DatasetCommand::Install { .. } | DatasetCommand::Use { .. } => false,
            },
            Command::Drug(LookupArgs { command })
            | Command::Diagnosis(LookupArgs { command })
            | Command::Loinc(LookupArgs { command }) => match command {
                LookupCommand::Search { json, .. } | LookupCommand::Get { json, .. } => *json,
            },
            Command::Laboratory(LaboratoryArgs { command }) => match command {
                LaboratoryCommand::Search { json, .. } | LaboratoryCommand::Get { json, .. } => {
                    *json
                }
                LaboratoryCommand::Panel(LaboratoryPanelArgs { command }) => match command {
                    LookupCommand::Search { json, .. } | LookupCommand::Get { json, .. } => *json,
                },
            },
        }
    }
}

fn classify_error(message: &str) -> (&'static str, i32) {
    if message.contains("CLI_VERSION_INCOMPATIBLE") || message.contains("runtime.minimumCliVersion")
    {
        ("CLI_VERSION_INCOMPATIBLE", 6)
    } else if message.contains("is not installed") {
        ("DATASET_NOT_INSTALLED", 3)
    } else if message.contains("SHA256") || message.contains("integrity_check") {
        ("ARTIFACT_VERIFICATION_FAILED", 4)
    } else {
        ("RUNTIME_ERROR", 5)
    }
}

fn run(cli: Cli) -> Result<bool> {
    let data_dir = cli.data_dir.unwrap_or_else(default_data_dir);
    match cli.command {
        Command::Init(args) => {
            run_init(&data_dir, args)?;
            Ok(true)
        }
        Command::Doctor(args) => run_doctor(&data_dir, args),
        Command::Dataset(args) => {
            run_dataset(&data_dir, args.command)?;
            Ok(true)
        }
        Command::Drug(args) => {
            run_lookup(&data_dir, "nhsa-drugs", args.command)?;
            Ok(true)
        }
        Command::Diagnosis(args) => {
            run_lookup(&data_dir, "nhc-icd10-clinical", args.command)?;
            Ok(true)
        }
        Command::Loinc(args) => {
            run_lookup(&data_dir, "loinc-zh-cn", args.command)?;
            Ok(true)
        }
        Command::Laboratory(args) => {
            run_laboratory(&data_dir, args.command)?;
            Ok(true)
        }
    }
}

fn default_data_dir() -> PathBuf {
    ProjectDirs::from("org", "cn-health", "cn-health")
        .expect("platform has no user data directory")
        .data_dir()
        .to_path_buf()
}

fn run_init(data_dir: &Path, args: InitArgs) -> Result<()> {
    let dataset_ids = selected_dataset_ids(&args.only)?;
    let selection = if args.only.is_empty() { "all" } else { "only" };
    let (registry_url, public_key) = match (args.registry, args.public_key) {
        (None, None) => (
            DEFAULT_REGISTRY_URL.to_owned(),
            DEFAULT_REGISTRY_PUBLIC_KEY.to_vec(),
        ),
        (Some(registry), Some(public_key)) => (registry, fs::read(public_key)?),
        _ => anyhow::bail!("--registry and --public-key must be provided together"),
    };
    let mut items = Vec::with_capacity(dataset_ids.len());
    for dataset_id in dataset_ids {
        let versions_before = list_versions(data_dir, dataset_id)?;
        let installed = install_remote_with_key(data_dir, dataset_id, &registry_url, &public_key)?;
        let status = if versions_before
            .iter()
            .any(|version| version.release_id == installed.release_id)
        {
            "already-installed"
        } else {
            "installed"
        };
        if !args.json {
            println!("{}\t{}\t{}", installed.id, installed.release_id, status);
        }
        items.push(json!({
            "datasetId": installed.id,
            "releaseId": installed.release_id,
            "status": status
        }));
    }
    if args.json {
        print_json(&json!({
            "schemaVersion": 2,
            "command": "init",
            "selection": selection,
            "items": items
        }))?;
    }
    Ok(())
}

fn selected_dataset_ids(only: &[String]) -> Result<Vec<&'static str>> {
    if only.is_empty() {
        return Ok(DEFAULT_DATASET_IDS.to_vec());
    }
    for requested in only {
        if requested.is_empty() || !DEFAULT_DATASET_IDS.contains(&requested.as_str()) {
            anyhow::bail!("unknown or unavailable Dataset ID in --only: {requested:?}");
        }
    }
    Ok(DEFAULT_DATASET_IDS
        .iter()
        .copied()
        .filter(|dataset_id| only.iter().any(|requested| requested == dataset_id))
        .collect())
}

fn run_doctor(data_dir: &Path, args: DoctorArgs) -> Result<bool> {
    let installed = list_installed(data_dir)?;
    let mut checks = Vec::new();
    for dataset_id in DEFAULT_DATASET_IDS {
        let dataset_ok = installed.iter().any(|dataset| {
            dataset.id == dataset_id
                && dataset.trust.starts_with("signed-registry:")
                && current_database(data_dir, dataset_id).is_ok_and(|(path, _)| path.is_file())
        });
        checks.push(DoctorCheck {
            id: format!("dataset:{dataset_id}"),
            ok: dataset_ok,
        });
    }
    let drug_query_ok = current_database(data_dir, "nhsa-drugs")
        .and_then(|(database, _)| drug_get(&database, "XA10BAE021A010010201650"))
        .is_ok_and(|item| item.is_some());
    let diagnosis_query_ok = current_database(data_dir, "nhc-icd10-clinical")
        .and_then(|(database, _)| diagnosis_get(&database, "E14.900x001"))
        .is_ok_and(|item| item.is_some());
    let loinc_query_ok = current_database(data_dir, "loinc-zh-cn")
        .and_then(|(database, _)| loinc_get(&database, "2339-0"))
        .is_ok_and(|item| item.is_some());
    let laboratory_query_ok = current_database(data_dir, STARTER_DATASET_ID)
        .and_then(|(database, _)| laboratory_health_check(&database))
        .unwrap_or(false);
    checks.extend([
        DoctorCheck {
            id: "query:drug".to_owned(),
            ok: drug_query_ok,
        },
        DoctorCheck {
            id: "query:diagnosis".to_owned(),
            ok: diagnosis_query_ok,
        },
        DoctorCheck {
            id: "query:loinc".to_owned(),
            ok: loinc_query_ok,
        },
        DoctorCheck {
            id: "query:laboratory".to_owned(),
            ok: laboratory_query_ok,
        },
    ]);
    let ok = checks.iter().all(|check| check.ok);
    if args.json {
        print_json(&json!({
            "schemaVersion": 1,
            "command": "doctor",
            "ok": ok,
            "cliVersion": env!("CARGO_PKG_VERSION"),
            "dataDir": data_dir,
            "defaultRegistry": DEFAULT_REGISTRY_URL,
            "checks": checks
        }))?;
    } else {
        println!("cn-health {}", env!("CARGO_PKG_VERSION"));
        println!("data-dir\t{}", data_dir.display());
        for check in checks {
            println!("{}\t{}", check.id, if check.ok { "ok" } else { "failed" });
        }
    }
    Ok(ok)
}

fn run_dataset(data_dir: &std::path::Path, command: DatasetCommand) -> Result<()> {
    match command {
        DatasetCommand::Install {
            dataset_id,
            local_manifest,
            registry,
            public_key,
        } => {
            let installed = match (dataset_id, local_manifest, registry, public_key) {
                (None, Some(manifest), None, None) => install_local(data_dir, &manifest)?,
                (Some(id), None, Some(registry), Some(public_key)) => {
                    install_remote(data_dir, &id, &registry, &public_key)?
                }
                _ => anyhow::bail!(
                    "use either --local-manifest PATH or DATASET_ID --registry URL --public-key PATH"
                ),
            };
            println!("{} {}", installed.id, installed.release_id);
        }
        DatasetCommand::List { json: json_output } => {
            let installed = list_installed(data_dir)?;
            if json_output {
                print_json(&json!({
                    "schemaVersion": 1,
                    "command": "dataset.list",
                    "items": installed
                }))?;
            } else {
                for dataset in installed {
                    println!("{}\t{}\t{}", dataset.id, dataset.release_id, dataset.trust);
                }
            }
        }
        DatasetCommand::Materialize {
            dataset_id,
            release_id,
            registry,
            public_key,
            output,
            json: json_output,
        } => {
            let receipt = materialize_release(
                data_dir,
                &dataset_id,
                &release_id,
                &registry,
                &public_key,
                &output,
            )?;
            if json_output {
                print_json(&receipt)?;
            } else {
                println!("{} {} {}", dataset_id, release_id, output.display());
            }
        }
        DatasetCommand::Info {
            dataset_id,
            json: json_output,
        } => {
            let installed = list_installed(data_dir)?
                .into_iter()
                .find(|dataset| dataset.id == dataset_id)
                .with_context(|| format!("Dataset {dataset_id} is not installed"))?;
            if json_output {
                print_json(&installed)?;
            } else {
                println!(
                    "{}\t{}\t{}",
                    installed.id, installed.release_id, installed.trust
                );
            }
        }
        DatasetCommand::Versions {
            dataset_id,
            json: json_output,
        } => {
            let versions = list_versions(data_dir, &dataset_id)?;
            if json_output {
                print_json(&json!({
                    "schemaVersion": 1,
                    "command": "dataset.versions",
                    "dataset": dataset_id,
                    "items": versions
                }))?;
            } else {
                for version in versions {
                    println!(
                        "{}\t{}\t{}",
                        version.release_id, version.source_version, version.trust
                    );
                }
            }
        }
        DatasetCommand::Use {
            dataset_id,
            release_id,
        } => {
            let version = activate_release(data_dir, &dataset_id, &release_id)?;
            println!("{} {}", dataset_id, version.release_id);
        }
    }
    Ok(())
}

fn run_laboratory(data_dir: &Path, command: LaboratoryCommand) -> Result<()> {
    match command {
        LaboratoryCommand::Search { query, limit, json } => run_lookup(
            data_dir,
            STARTER_DATASET_ID,
            LookupCommand::Search { query, limit, json },
        ),
        LaboratoryCommand::Get { code, json } => run_lookup(
            data_dir,
            STARTER_DATASET_ID,
            LookupCommand::Get { code, json },
        ),
        LaboratoryCommand::Panel(LaboratoryPanelArgs { command }) => {
            run_laboratory_panel(data_dir, command)
        }
    }
}

fn run_laboratory_panel(data_dir: &Path, command: LookupCommand) -> Result<()> {
    let (database, current) = current_database(data_dir, STARTER_DATASET_ID)?;
    if let LookupCommand::Search { limit, .. } = &command
        && !(1..=200).contains(limit)
    {
        anyhow::bail!("limit must be between 1 and 200");
    }
    match command {
        LookupCommand::Search { query, limit, json } => {
            let results = laboratory_panel_search(&database, &query, limit)?;
            output_search(
                STARTER_DATASET_ID,
                &current.release_id,
                "laboratory.panel.search",
                query,
                limit,
                results,
                json,
            )
        }
        LookupCommand::Get { code, json } => {
            let item = laboratory_panel_get(&database, &code)?
                .context("laboratory panel code not found")?;
            output_item(item, json)
        }
    }
}

fn run_lookup(data_dir: &std::path::Path, dataset_id: &str, command: LookupCommand) -> Result<()> {
    let (database, current) = current_database(data_dir, dataset_id)?;
    if let LookupCommand::Search { limit, .. } = &command
        && !(1..=200).contains(limit)
    {
        anyhow::bail!("limit must be between 1 and 200");
    }
    match (dataset_id, command) {
        ("nhsa-drugs", LookupCommand::Search { query, limit, json }) => {
            let results = drug_search(&database, &query, limit)?;
            output_search(
                dataset_id,
                &current.release_id,
                "drug.search",
                query,
                limit,
                results,
                json,
            )
        }
        ("nhsa-drugs", LookupCommand::Get { code, json }) => {
            let item = drug_get(&database, &code)?.context("drug code not found")?;
            output_item(item, json)
        }
        ("loinc-zh-cn", LookupCommand::Search { query, limit, json }) => {
            let results = loinc_search(&database, &query, limit)?;
            output_search(
                dataset_id,
                &current.release_id,
                "loinc.search",
                query,
                limit,
                results,
                json,
            )
        }
        ("loinc-zh-cn", LookupCommand::Get { code, json }) => {
            let item = loinc_get(&database, &code)?.context("LOINC code not found")?;
            output_item(item, json)
        }
        ("laboratory-cn", LookupCommand::Search { query, limit, json }) => {
            let results = laboratory_search(&database, &query, limit)?;
            output_search(
                dataset_id,
                &current.release_id,
                "laboratory.search",
                query,
                limit,
                results,
                json,
            )
        }
        ("laboratory-cn", LookupCommand::Get { code, json }) => {
            let item = laboratory_get(&database, &code)?.context("laboratory code not found")?;
            output_item(item, json)
        }
        (_, LookupCommand::Search { query, limit, json }) => {
            let results = diagnosis_search(&database, &query, limit)?;
            output_search(
                dataset_id,
                &current.release_id,
                "diagnosis.search",
                query,
                limit,
                results,
                json,
            )
        }
        (_, LookupCommand::Get { code, json }) => {
            let item = diagnosis_get(&database, &code)?.context("diagnosis code not found")?;
            output_item(item, json)
        }
    }
}

fn output_search<T: Serialize>(
    dataset_id: &str,
    release_id: &str,
    command: &str,
    query: String,
    limit: usize,
    results: SearchResults<T>,
    json_output: bool,
) -> Result<()> {
    let SearchResults { items, truncated } = results;
    if json_output {
        let returned = items.len();
        print_json(&json!({
            "schemaVersion": 1,
            "command": command,
            "dataset": {"id": dataset_id, "releaseId": release_id},
            "query": {"text": query, "mode": "literal", "limit": limit},
            "items": items,
            "page": {"returned": returned, "limit": limit, "truncated": truncated}
        }))?;
    } else {
        for item in items {
            println!("{}", serde_json::to_string(&item)?);
        }
    }
    Ok(())
}

fn output_item<T: Serialize>(item: T, _json_output: bool) -> Result<()> {
    print_json(&item)
}

fn print_json<T: Serialize>(value: &T) -> Result<()> {
    println!("{}", serde_json::to_string(value)?);
    Ok(())
}
