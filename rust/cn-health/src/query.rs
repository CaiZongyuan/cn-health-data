use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OpenFlags, OptionalExtension, params};
use serde::Serialize;

pub struct SearchResults<T> {
    pub items: Vec<T>,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DrugItem {
    pub code: String,
    pub registered_name: String,
    pub trade_name: String,
    pub market_status: String,
    pub insurance_name: Option<String>,
    pub rank: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosisItem {
    pub code: String,
    pub main_code: Option<String>,
    pub additional_code: Option<String>,
    pub name: String,
    pub rank: usize,
}

fn connection(path: &Path) -> Result<Connection> {
    Ok(Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?)
}

pub fn drug_get(path: &Path, code: &str) -> Result<Option<DrugItem>> {
    let connection = connection(path)?;
    Ok(connection
        .query_row(
            "SELECT code, registered_name, trade_name, market_status, insurance_name
             FROM drug WHERE code = ?1",
            [code],
            |row| {
                Ok(DrugItem {
                    code: row.get(0)?,
                    registered_name: row.get(1)?,
                    trade_name: row.get(2)?,
                    market_status: row.get(3)?,
                    insurance_name: row.get(4)?,
                    rank: 1,
                })
            },
        )
        .optional()?)
}

pub fn drug_search(path: &Path, query: &str, limit: usize) -> Result<SearchResults<DrugItem>> {
    let connection = connection(path)?;
    let characters = query.chars().count();
    if characters < 2 {
        bail!("search query must contain at least two Unicode characters");
    }
    let (sql, argument) = if characters == 2 {
        (
            "SELECT d.code, d.registered_name, d.trade_name, d.market_status, d.insurance_name
             FROM drug_search_bigram b JOIN drug d USING(code)
             WHERE b.term = ?1
               AND (instr(d.registered_name, ?2) > 0 OR instr(COALESCE(d.insurance_name,''), ?2) > 0)
             ORDER BY d.code LIMIT ?3",
            query.to_owned(),
        )
    } else {
        (
            "SELECT d.code, d.registered_name, d.trade_name, d.market_status, d.insurance_name
             FROM drug_fts JOIN drug d ON d.rowid = drug_fts.rowid
             WHERE drug_fts MATCH ?1 ORDER BY bm25(drug_fts), d.code LIMIT ?3",
            literal_fts_query(query),
        )
    };
    let mut statement = connection.prepare(sql)?;
    let rows = statement.query_map(params![argument, query, limit as i64 + 1], |row| {
        Ok(DrugItem {
            code: row.get(0)?,
            registered_name: row.get(1)?,
            trade_name: row.get(2)?,
            market_status: row.get(3)?,
            insurance_name: row.get(4)?,
            rank: 0,
        })
    })?;
    let mut items = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    let truncated = items.len() > limit;
    items.truncate(limit);
    for (index, item) in items.iter_mut().enumerate() {
        item.rank = index + 1;
    }
    Ok(SearchResults { items, truncated })
}

pub fn diagnosis_get(path: &Path, code: &str) -> Result<Option<DiagnosisItem>> {
    let connection = connection(path)?;
    Ok(connection
        .query_row(
            "SELECT code, main_code, additional_code, name FROM diagnosis WHERE code = ?1",
            [code],
            |row| {
                Ok(DiagnosisItem {
                    code: row.get(0)?,
                    main_code: row.get(1)?,
                    additional_code: row.get(2)?,
                    name: row.get(3)?,
                    rank: 1,
                })
            },
        )
        .optional()?)
}

pub fn diagnosis_search(
    path: &Path,
    query: &str,
    limit: usize,
) -> Result<SearchResults<DiagnosisItem>> {
    let connection = connection(path)?;
    let characters = query.chars().count();
    if characters < 2 {
        bail!("search query must contain at least two Unicode characters");
    }
    let (sql, argument) = if characters == 2 {
        (
            "SELECT d.code, d.main_code, d.additional_code, d.name
             FROM diagnosis_search_bigram b JOIN diagnosis d USING(code)
             WHERE b.term = ?1 AND instr(d.name, ?2) > 0
             ORDER BY d.code LIMIT ?3",
            query.to_owned(),
        )
    } else {
        (
            "SELECT d.code, d.main_code, d.additional_code, d.name
             FROM diagnosis_fts JOIN diagnosis d ON d.rowid = diagnosis_fts.rowid
             WHERE diagnosis_fts MATCH ?1 ORDER BY bm25(diagnosis_fts), d.code LIMIT ?3",
            literal_fts_query(query),
        )
    };
    let mut statement = connection.prepare(sql)?;
    let rows = statement.query_map(params![argument, query, limit as i64 + 1], |row| {
        Ok(DiagnosisItem {
            code: row.get(0)?,
            main_code: row.get(1)?,
            additional_code: row.get(2)?,
            name: row.get(3)?,
            rank: 0,
        })
    })?;
    let mut items = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    let truncated = items.len() > limit;
    items.truncate(limit);
    for (index, item) in items.iter_mut().enumerate() {
        item.rank = index + 1;
    }
    Ok(SearchResults { items, truncated })
}

fn literal_fts_query(query: &str) -> String {
    format!("\"{}\"", query.replace('"', "\"\""))
}
