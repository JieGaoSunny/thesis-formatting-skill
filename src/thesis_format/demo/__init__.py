"""Fictional thesis content and deterministic demonstration figures."""

from .content import (
    Appendix,
    Chapter,
    Paragraph,
    Reference,
    Section,
    Table,
    Thesis,
    build_demo_thesis,
)
from .figures import Figure, generate_demo_figures

__all__ = [
    "Appendix",
    "Chapter",
    "Figure",
    "Paragraph",
    "Reference",
    "Section",
    "Table",
    "Thesis",
    "build_demo_thesis",
    "generate_demo_figures",
]
