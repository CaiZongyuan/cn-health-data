use std::path::Path;

use anyhow::{Result, bail};
use rusqlite::{Connection, OpenFlags, OptionalExtension, params};
use serde::Serialize;

const WST_886_SYSTEM: &str = "urn:cn-health:terminology:wst-886-2026";

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

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoincItem {
    pub code: String,
    pub long_common_name: String,
    pub zh_display: Option<String>,
    pub rank: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum LaboratoryItem {
    V1(LaboratoryV1Item),
    V2(LaboratoryV2Item),
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LaboratoryV1Item {
    pub code: String,
    pub system: String,
    pub terminology_version: String,
    pub display_zh: String,
    pub category: String,
    pub specimen: String,
    pub result_type: String,
    pub ucum_unit: Option<String>,
    pub status: String,
    pub rank: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LaboratoryReference {
    pub sex: String,
    pub reference_kind: String,
    pub low_value: Option<f64>,
    pub high_value: Option<f64>,
    pub normal_value: Option<String>,
    pub simulation_low: Option<f64>,
    pub simulation_high: Option<f64>,
    pub source_type: String,
    pub source_standard: String,
    pub source_version: String,
    pub source_location: String,
    pub notes: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LaboratoryV2Item {
    pub code: String,
    pub system: String,
    pub name: String,
    pub category: String,
    pub analyte: String,
    pub specimen: String,
    pub scale: String,
    pub result_kind: String,
    pub unit_display: Option<String>,
    pub unit_ucum: Option<String>,
    pub precision: i64,
    pub healthy_strategy: String,
    pub loinc_code: Option<String>,
    pub status: String,
    pub source_version: String,
    pub references: Vec<LaboratoryReference>,
    pub rank: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LaboratoryPanelMember {
    pub sort_order: i64,
    pub test: LaboratoryV2Item,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LaboratoryPanelItem {
    pub code: String,
    pub name: String,
    pub specimen: String,
    pub status: String,
    pub source_type: String,
    pub source_location: String,
    pub notes: String,
    pub member_count: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub members: Option<Vec<LaboratoryPanelMember>>,
    pub rank: usize,
}

trait Ranked {
    fn set_rank(&mut self, rank: usize);
}

impl Ranked for DrugItem {
    fn set_rank(&mut self, rank: usize) {
        self.rank = rank;
    }
}

impl Ranked for DiagnosisItem {
    fn set_rank(&mut self, rank: usize) {
        self.rank = rank;
    }
}

impl Ranked for LoincItem {
    fn set_rank(&mut self, rank: usize) {
        self.rank = rank;
    }
}

impl Ranked for LaboratoryItem {
    fn set_rank(&mut self, rank: usize) {
        match self {
            Self::V1(item) => item.rank = rank,
            Self::V2(item) => item.rank = rank,
        }
    }
}

impl Ranked for LaboratoryPanelItem {
    fn set_rank(&mut self, rank: usize) {
        self.rank = rank;
    }
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
    let characters = query_length(query)?;
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
    Ok(finish_search(
        rows.collect::<rusqlite::Result<Vec<_>>>()?,
        limit,
    ))
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
    let characters = query_length(query)?;
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
    Ok(finish_search(
        rows.collect::<rusqlite::Result<Vec<_>>>()?,
        limit,
    ))
}

pub fn loinc_get(path: &Path, code: &str) -> Result<Option<LoincItem>> {
    let connection = connection(path)?;
    Ok(connection
        .query_row(
            "SELECT code, long_common_name, zh_display FROM loinc WHERE code = ?1",
            [code],
            |row| {
                Ok(LoincItem {
                    code: row.get(0)?,
                    long_common_name: row.get(1)?,
                    zh_display: row.get(2)?,
                    rank: 1,
                })
            },
        )
        .optional()?)
}

pub fn loinc_search(path: &Path, query: &str, limit: usize) -> Result<SearchResults<LoincItem>> {
    let connection = connection(path)?;
    let characters = query_length(query)?;
    let (sql, argument) = if characters == 2 {
        (
            "SELECT l.code, l.long_common_name, l.zh_display
             FROM loinc_search_bigram b JOIN loinc l USING(code)
             WHERE b.term = ?1
               AND (instr(l.long_common_name, ?2) > 0 OR instr(COALESCE(l.zh_display,''), ?2) > 0)
             ORDER BY l.code LIMIT ?3",
            query.to_owned(),
        )
    } else {
        (
            "SELECT l.code, l.long_common_name, l.zh_display
             FROM loinc_fts JOIN loinc l ON l.rowid = loinc_fts.rowid
             WHERE loinc_fts MATCH ?1 ORDER BY bm25(loinc_fts), l.code LIMIT ?3",
            literal_fts_query(query),
        )
    };
    let mut statement = connection.prepare(sql)?;
    let rows = statement.query_map(params![argument, query, limit as i64 + 1], |row| {
        Ok(LoincItem {
            code: row.get(0)?,
            long_common_name: row.get(1)?,
            zh_display: row.get(2)?,
            rank: 0,
        })
    })?;
    Ok(finish_search(
        rows.collect::<rusqlite::Result<Vec<_>>>()?,
        limit,
    ))
}

pub fn laboratory_get(path: &Path, code: &str) -> Result<Option<LaboratoryItem>> {
    let connection = connection(path)?;
    if table_exists(&connection, "laboratory_test")? {
        Ok(laboratory_v2_get(&connection, code)?.map(LaboratoryItem::V2))
    } else if table_exists(&connection, "laboratory_concept")? {
        Ok(laboratory_v1_get(&connection, code)?.map(LaboratoryItem::V1))
    } else {
        bail!("unsupported laboratory database schema")
    }
}

fn laboratory_v1_get(connection: &Connection, code: &str) -> Result<Option<LaboratoryV1Item>> {
    Ok(connection
        .query_row(
            "SELECT code, system, terminology_version, display_zh, category, specimen,
                    result_type, ucum_unit, status
             FROM laboratory_concept WHERE code = ?1",
            [code],
            |row| {
                Ok(LaboratoryV1Item {
                    code: row.get(0)?,
                    system: row.get(1)?,
                    terminology_version: row.get(2)?,
                    display_zh: row.get(3)?,
                    category: row.get(4)?,
                    specimen: row.get(5)?,
                    result_type: row.get(6)?,
                    ucum_unit: row.get(7)?,
                    status: row.get(8)?,
                    rank: 1,
                })
            },
        )
        .optional()?)
}

fn laboratory_v2_get(connection: &Connection, code: &str) -> Result<Option<LaboratoryV2Item>> {
    let mut item = connection
        .query_row(
            "SELECT code, name, category, analyte, specimen, scale, result_kind,
                    unit_display, unit_ucum, precision, healthy_strategy, loinc_code,
                    status, source_version
             FROM laboratory_test WHERE code = ?1",
            [code],
            laboratory_v2_row,
        )
        .optional()?;
    if let Some(item) = &mut item {
        item.references = laboratory_references(connection, &item.code)?;
        item.rank = 1;
    }
    Ok(item)
}

fn laboratory_v2_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<LaboratoryV2Item> {
    Ok(LaboratoryV2Item {
        code: row.get(0)?,
        system: WST_886_SYSTEM.to_owned(),
        name: row.get(1)?,
        category: row.get(2)?,
        analyte: row.get(3)?,
        specimen: row.get(4)?,
        scale: row.get(5)?,
        result_kind: row.get(6)?,
        unit_display: row.get(7)?,
        unit_ucum: row.get(8)?,
        precision: row.get(9)?,
        healthy_strategy: row.get(10)?,
        loinc_code: row.get(11)?,
        status: row.get(12)?,
        source_version: row.get(13)?,
        references: Vec::new(),
        rank: 0,
    })
}

fn laboratory_references(
    connection: &Connection,
    test_code: &str,
) -> Result<Vec<LaboratoryReference>> {
    let mut statement = connection.prepare(
        "SELECT sex, reference_kind, low_value, high_value, normal_value,
                simulation_low, simulation_high, source_type, source_standard,
                source_version, source_location, notes
         FROM laboratory_reference WHERE test_code = ?1 ORDER BY sex",
    )?;
    let rows = statement.query_map([test_code], |row| {
        Ok(LaboratoryReference {
            sex: row.get(0)?,
            reference_kind: row.get(1)?,
            low_value: row.get(2)?,
            high_value: row.get(3)?,
            normal_value: row.get(4)?,
            simulation_low: row.get(5)?,
            simulation_high: row.get(6)?,
            source_type: row.get(7)?,
            source_standard: row.get(8)?,
            source_version: row.get(9)?,
            source_location: row.get(10)?,
            notes: row.get(11)?,
        })
    })?;
    Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
}

pub fn laboratory_search(
    path: &Path,
    query: &str,
    limit: usize,
) -> Result<SearchResults<LaboratoryItem>> {
    let connection = connection(path)?;
    if table_exists(&connection, "laboratory_test")? {
        laboratory_v2_search(&connection, query, limit)
    } else if table_exists(&connection, "laboratory_concept")? {
        laboratory_v1_search(&connection, query, limit)
    } else {
        bail!("unsupported laboratory database schema")
    }
}

fn laboratory_v1_search(
    connection: &Connection,
    query: &str,
    limit: usize,
) -> Result<SearchResults<LaboratoryItem>> {
    let characters = query_length(query)?;
    let (sql, argument) = if characters == 2 {
        (
            "SELECT l.code, l.system, l.terminology_version, l.display_zh, l.category,
                    l.specimen, l.result_type, l.ucum_unit, l.status
             FROM laboratory_concept_search_bigram b JOIN laboratory_concept l USING(code)
             WHERE b.term = ?1 AND instr(l.display_zh, ?2) > 0
             ORDER BY l.code LIMIT ?3",
            query.to_owned(),
        )
    } else {
        (
            "SELECT l.code, l.system, l.terminology_version, l.display_zh, l.category,
                    l.specimen, l.result_type, l.ucum_unit, l.status
             FROM laboratory_concept_fts
             JOIN laboratory_concept l ON l.rowid = laboratory_concept_fts.rowid
             WHERE laboratory_concept_fts MATCH ?1
             ORDER BY bm25(laboratory_concept_fts), l.code LIMIT ?3",
            literal_fts_query(query),
        )
    };
    let mut statement = connection.prepare(sql)?;
    let rows = statement.query_map(params![argument, query, limit as i64 + 1], |row| {
        Ok(LaboratoryItem::V1(LaboratoryV1Item {
            code: row.get(0)?,
            system: row.get(1)?,
            terminology_version: row.get(2)?,
            display_zh: row.get(3)?,
            category: row.get(4)?,
            specimen: row.get(5)?,
            result_type: row.get(6)?,
            ucum_unit: row.get(7)?,
            status: row.get(8)?,
            rank: 0,
        }))
    })?;
    Ok(finish_search(
        rows.collect::<rusqlite::Result<Vec<_>>>()?,
        limit,
    ))
}

fn laboratory_v2_search(
    connection: &Connection,
    query: &str,
    limit: usize,
) -> Result<SearchResults<LaboratoryItem>> {
    let characters = query_length(query)?;
    let (sql, argument) = if characters == 2 {
        (
            "SELECT l.code, l.name, l.category, l.analyte, l.specimen, l.scale,
                    l.result_kind, l.unit_display, l.unit_ucum, l.precision,
                    l.healthy_strategy, l.loinc_code, l.status, l.source_version
             FROM laboratory_test_search_bigram b JOIN laboratory_test l USING(code)
             WHERE b.term = ?1 AND instr(l.name, ?2) > 0
             ORDER BY l.code LIMIT ?3",
            query.to_owned(),
        )
    } else {
        (
            "SELECT l.code, l.name, l.category, l.analyte, l.specimen, l.scale,
                    l.result_kind, l.unit_display, l.unit_ucum, l.precision,
                    l.healthy_strategy, l.loinc_code, l.status, l.source_version
             FROM laboratory_test_fts
             JOIN laboratory_test l ON l.rowid = laboratory_test_fts.rowid
             WHERE laboratory_test_fts MATCH ?1
             ORDER BY bm25(laboratory_test_fts), l.code LIMIT ?3",
            literal_fts_query(query),
        )
    };
    let mut statement = connection.prepare(sql)?;
    let rows = statement.query_map(
        params![argument, query, limit as i64 + 1],
        laboratory_v2_row,
    )?;
    let mut items = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    drop(statement);
    for item in &mut items {
        item.references = laboratory_references(connection, &item.code)?;
    }
    Ok(finish_search(
        items.into_iter().map(LaboratoryItem::V2).collect(),
        limit,
    ))
}

pub fn laboratory_panel_get(path: &Path, code: &str) -> Result<Option<LaboratoryPanelItem>> {
    let connection = connection(path)?;
    require_laboratory_v2(&connection)?;
    let mut panel = connection
        .query_row(
            "SELECT p.code, p.name, p.specimen, p.status, p.source_type,
                    p.source_location, p.notes, count(m.test_code)
             FROM laboratory_panel p
             JOIN laboratory_panel_member m ON m.panel_code = p.code
             WHERE p.code = ?1 GROUP BY p.code",
            [code],
            laboratory_panel_row,
        )
        .optional()?;
    if let Some(panel) = &mut panel {
        panel.members = Some(laboratory_panel_members(&connection, &panel.code)?);
        panel.rank = 1;
    }
    Ok(panel)
}

pub fn laboratory_panel_search(
    path: &Path,
    query: &str,
    limit: usize,
) -> Result<SearchResults<LaboratoryPanelItem>> {
    let connection = connection(path)?;
    require_laboratory_v2(&connection)?;
    let characters = query_length(query)?;
    let (sql, argument) = if characters == 2 {
        (
            "SELECT p.code, p.name, p.specimen, p.status, p.source_type,
                    p.source_location, p.notes,
                    (SELECT count(*) FROM laboratory_panel_member m
                     WHERE m.panel_code = p.code)
             FROM laboratory_panel_search_bigram b
             JOIN laboratory_panel p USING(code)
             WHERE b.term = ?1 AND instr(p.name, ?2) > 0
             ORDER BY p.code LIMIT ?3",
            query.to_owned(),
        )
    } else {
        (
            "SELECT p.code, p.name, p.specimen, p.status, p.source_type,
                    p.source_location, p.notes,
                    (SELECT count(*) FROM laboratory_panel_member m
                     WHERE m.panel_code = p.code)
             FROM laboratory_panel_fts
             JOIN laboratory_panel p ON p.rowid = laboratory_panel_fts.rowid
             WHERE laboratory_panel_fts MATCH ?1
             ORDER BY bm25(laboratory_panel_fts), p.code LIMIT ?3",
            literal_fts_query(query),
        )
    };
    let mut statement = connection.prepare(sql)?;
    let rows = statement.query_map(
        params![argument, query, limit as i64 + 1],
        laboratory_panel_row,
    )?;
    Ok(finish_search(
        rows.collect::<rusqlite::Result<Vec<_>>>()?,
        limit,
    ))
}

fn laboratory_panel_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<LaboratoryPanelItem> {
    Ok(LaboratoryPanelItem {
        code: row.get(0)?,
        name: row.get(1)?,
        specimen: row.get(2)?,
        status: row.get(3)?,
        source_type: row.get(4)?,
        source_location: row.get(5)?,
        notes: row.get(6)?,
        member_count: row.get(7)?,
        members: None,
        rank: 0,
    })
}

fn laboratory_panel_members(
    connection: &Connection,
    panel_code: &str,
) -> Result<Vec<LaboratoryPanelMember>> {
    let mut statement = connection.prepare(
        "SELECT m.sort_order, t.code, t.name, t.category, t.analyte, t.specimen,
                t.scale, t.result_kind, t.unit_display, t.unit_ucum, t.precision,
                t.healthy_strategy, t.loinc_code, t.status, t.source_version
         FROM laboratory_panel_member m
         JOIN laboratory_test t ON t.code = m.test_code
         WHERE m.panel_code = ?1 ORDER BY m.sort_order",
    )?;
    let rows = statement.query_map([panel_code], |row| {
        let test = LaboratoryV2Item {
            code: row.get(1)?,
            system: WST_886_SYSTEM.to_owned(),
            name: row.get(2)?,
            category: row.get(3)?,
            analyte: row.get(4)?,
            specimen: row.get(5)?,
            scale: row.get(6)?,
            result_kind: row.get(7)?,
            unit_display: row.get(8)?,
            unit_ucum: row.get(9)?,
            precision: row.get(10)?,
            healthy_strategy: row.get(11)?,
            loinc_code: row.get(12)?,
            status: row.get(13)?,
            source_version: row.get(14)?,
            references: Vec::new(),
            rank: 1,
        };
        Ok((row.get(0)?, test))
    })?;
    let records = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    drop(statement);
    let mut members = Vec::with_capacity(records.len());
    for (sort_order, mut test) in records {
        test.references = laboratory_references(connection, &test.code)?;
        members.push(LaboratoryPanelMember { sort_order, test });
    }
    Ok(members)
}

pub fn laboratory_health_check(path: &Path) -> Result<bool> {
    let connection = connection(path)?;
    let application_id: i64 =
        connection.query_row("PRAGMA application_id", [], |row| row.get(0))?;
    let integrity: String = connection.query_row("PRAGMA integrity_check", [], |row| row.get(0))?;
    if application_id != 0x434E4844 || integrity != "ok" {
        return Ok(false);
    }
    if table_exists(&connection, "laboratory_test")? {
        let tests: i64 =
            connection.query_row("SELECT count(*) FROM laboratory_test", [], |row| row.get(0))?;
        let references: i64 =
            connection.query_row("SELECT count(*) FROM laboratory_reference", [], |row| {
                row.get(0)
            })?;
        let panels: i64 =
            connection.query_row("SELECT count(*) FROM laboratory_panel", [], |row| {
                row.get(0)
            })?;
        Ok(tests > 0 && references > 0 && panels > 0)
    } else if table_exists(&connection, "laboratory_concept")? {
        let concepts: i64 =
            connection.query_row("SELECT count(*) FROM laboratory_concept", [], |row| {
                row.get(0)
            })?;
        Ok(concepts > 0)
    } else {
        Ok(false)
    }
}

fn table_exists(connection: &Connection, table: &str) -> Result<bool> {
    Ok(connection
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1",
            [table],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

fn require_laboratory_v2(connection: &Connection) -> Result<()> {
    if !table_exists(connection, "laboratory_test")? {
        bail!("laboratory panels require a schema v2 laboratory-cn Release")
    }
    Ok(())
}

fn query_length(query: &str) -> Result<usize> {
    let characters = query.chars().count();
    if characters < 2 {
        bail!("search query must contain at least two Unicode characters");
    }
    Ok(characters)
}

fn finish_search<T: Ranked>(mut items: Vec<T>, limit: usize) -> SearchResults<T> {
    let truncated = items.len() > limit;
    items.truncate(limit);
    for (index, item) in items.iter_mut().enumerate() {
        item.set_rank(index + 1);
    }
    SearchResults { items, truncated }
}

fn literal_fts_query(query: &str) -> String {
    format!("\"{}\"", query.replace('"', "\"\""))
}
