from cn_health_compiler import __version__
from cn_health_compiler.cli import app
from typer.testing import CliRunner


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
