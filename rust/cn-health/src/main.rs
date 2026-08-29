mod manifest;
mod query;
mod storage;

use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand};
use directories::ProjectDirs;
use serde::Serialize;
use serde_json::json;

use crate::query::{diagnosis_get, diagnosis_search, drug_get, drug_search};
use crate::storage::{current_database, install_local, list_installed};

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
}

#[derive(Args)]
struct DatasetArgs {
    #[command(subcommand)]
    command: DatasetCommand,
}

#[derive(Subcommand)]
enum DatasetCommand {
    Install {
        #[arg(long)]
        local_manifest: PathBuf,
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
    if let Err(error) = run(Cli::parse()) {
        eprintln!("{error:#}");
        std::process::exit(1);
    }
}

fn run(cli: Cli) -> Result<()> {
    let data_dir = cli.data_dir.unwrap_or_else(default_data_dir);
    match cli.command {
        Command::Dataset(args) => run_dataset(&data_dir, args.command),
        Command::Drug(args) => run_lookup(&data_dir, "nhsa-drugs", args.command),
        Command::Diagnosis(args) => run_lookup(&data_dir, "nhc-icd10-clinical", args.command),
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
        DatasetCommand::Install { local_manifest } => {
            let installed = install_local(data_dir, &local_manifest)?;
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
            let items = drug_search(&database, &query, limit)?;
            output_search(
                dataset_id,
                &current.release_id,
                "drug.search",
                query,
                limit,
                items,
                json,
            )
        }
        ("nhsa-drugs", LookupCommand::Get { code, json }) => {
            let item = drug_get(&database, &code)?.context("drug code not found")?;
            output_item(item, json)
        }
        (_, LookupCommand::Search { query, limit, json }) => {
            let items = diagnosis_search(&database, &query, limit)?;
            output_search(
                dataset_id,
                &current.release_id,
                "diagnosis.search",
                query,
                limit,
                items,
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
    items: Vec<T>,
    json_output: bool,
) -> Result<()> {
    if json_output {
        let returned = items.len();
        print_json(&json!({
            "schemaVersion": 1,
            "command": command,
            "dataset": {"id": dataset_id, "releaseId": release_id},
            "query": {"text": query, "mode": "literal", "limit": limit},
            "items": items,
            "page": {"returned": returned, "limit": limit, "truncated": returned == limit}
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
