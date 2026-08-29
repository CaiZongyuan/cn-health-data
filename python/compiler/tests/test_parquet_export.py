import sqlite3
from pathlib import Path

import polars as pl
from cn_health_compiler.core.candidate import write_parquet


def test_write_parquet_uses_declared_sqlite_types_beyond_inference_window(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite"
    output = tmp_path / "data.parquet"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE records(code TEXT PRIMARY KEY, optional_name TEXT, source_row INTEGER)"
        )
        connection.executemany(
            "INSERT INTO records VALUES (?, ?, ?)",
            [
                (f"X{index:03}", "后出现的名称" if index == 150 else None, index)
                for index in range(151)
            ],
        )
        connection.commit()
    finally:
        connection.close()

    write_parquet(database, "records", output)

    frame = pl.read_parquet(output)
    assert frame.schema == {
        "code": pl.String,
        "optional_name": pl.String,
        "source_row": pl.Int64,
    }
    assert frame.filter(pl.col("code") == "X150")["optional_name"].item() == "后出现的名称"
