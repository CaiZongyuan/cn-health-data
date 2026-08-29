mod manifest;
mod query;
mod registry;
mod storage;

use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand};
use directories::ProjectDirs;
use serde::Serialize;
use serde_json::json;

use crate::query::{
    SearchResults, diagnosis_get, diagnosis_search, drug_get, drug_search, loinc_get, loinc_search,
};
use crate::registry::install_remote;
use crate::storage::{
    activate_release, current_database, install_local, list_installed, list_versions,
};

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
    Dataset(DatasetArgs),
    Drug(LookupArgs),
    Diagnosis(LookupArgs),
    Loinc(LookupArgs),
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
    if let Err(error) = run(cli) {
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

impl Cli {
    fn wants_json(&self) -> bool {
        match &self.command {
            Command::Dataset(DatasetArgs { command }) => match command {
                DatasetCommand::List { json }
                | DatasetCommand::Info { json, .. }
                | DatasetCommand::Versions { json, .. } => *json,
                DatasetCommand::Install { .. } | DatasetCommand::Use { .. } => false,
            },
            Command::Drug(LookupArgs { command })
            | Command::Diagnosis(LookupArgs { command })
            | Command::Loinc(LookupArgs { command }) => match command {
                LookupCommand::Search { json, .. } | LookupCommand::Get { json, .. } => *json,
            },
        }
    }
}

fn classify_error(message: &str) -> (&'static str, i32) {
    if message.contains("is not installed") {
        ("DATASET_NOT_INSTALLED", 3)
    } else if message.contains("SHA256") || message.contains("integrity_check") {
        ("ARTIFACT_VERIFICATION_FAILED", 4)
    } else {
        ("RUNTIME_ERROR", 5)
    }
}

fn run(cli: Cli) -> Result<()> {
    let data_dir = cli.data_dir.unwrap_or_else(default_data_dir);
    match cli.command {
        Command::Dataset(args) => run_dataset(&data_dir, args.command),
        Command::Drug(args) => run_lookup(&data_dir, "nhsa-drugs", args.command),
        Command::Diagnosis(args) => run_lookup(&data_dir, "nhc-icd10-clinical", args.command),
        Command::Loinc(args) => run_lookup(&data_dir, "loinc-zh-cn", args.command),
    }
}

fn default_data_dir() -> PathBuf {
    ProjectDirs::from("org", "cn-health", "cn-health")
        .expect("platform has no user data directory")
        .data_dir()
        .to_path_buf()
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
