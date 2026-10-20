import subprocess


def test_cli_version() -> None:
    result = subprocess.run(
        ["uv", "run", "thesis-format", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "thesis-formatting-skill 0.1.0"


def test_cli_help() -> None:
    result = subprocess.run(
        ["uv", "run", "thesis-format", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "usage: thesis-format" in result.stdout
