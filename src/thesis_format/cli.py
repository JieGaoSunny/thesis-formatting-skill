"""Command-line entry point for thesis-formatting-skill."""

import argparse

from thesis_format import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="thesis-format")
    parser.add_argument(
        "--version",
        action="version",
        version=f"thesis-formatting-skill {__version__}",
    )
    parser.parse_args()
