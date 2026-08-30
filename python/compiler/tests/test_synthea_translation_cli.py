import json
from pathlib import Path

from cn_health_compiler.cli import app
from typer.testing import CliRunner


def test_inventory_and_batch_cli_use_real_module_json(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "condition.json").write_text(
        json.dumps(
            {
                "states": {
                    "Condition": {
                        "type": "ConditionOnset",
                        "codes": [
                            {
                                "system": "SNOMED-CT",
                                "code": "1",
                                "display": "Example disorder",
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    inventory = tmp_path / "inventory.json"
    inventory_result = CliRunner().invoke(
        app,
        [
            "synthea",
            "translation",
            "inventory",
            "--module-dir",
            str(modules),
            "--output",
            str(inventory),
        ],
    )
    assert inventory_result.exit_code == 0, inventory_result.output
    assert json.loads(inventory.read_text(encoding="utf-8"))["moduleCount"] == 1

    batches = tmp_path / "batches"
    batch_result = CliRunner().invoke(
        app,
        [
            "synthea",
            "translation",
            "make-batches",
            "--module-dir",
            str(modules),
            "--output-dir",
            str(batches),
            "--prompt-version",
            "v1",
        ],
    )
    assert batch_result.exit_code == 0, batch_result.output
    assert json.loads((batches / "batch-index.json").read_text(encoding="utf-8"))["batchCount"] == 1
