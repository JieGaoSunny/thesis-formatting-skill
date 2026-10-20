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
from .figures import Figure, FigureFontError, generate_demo_figures, resolve_cjk_font
from .study import (
    DEFAULT_SCALE_INPUTS,
    SIMULATED_OBSERVATIONS,
    MethodSummary,
    Observation,
    ScaleInputs,
    SensitivityEnvelope,
    calculate_reported_statistics,
    sensitivity_envelope,
)

__all__ = [
    "Appendix",
    "Chapter",
    "Figure",
    "FigureFontError",
    "DEFAULT_SCALE_INPUTS",
    "SIMULATED_OBSERVATIONS",
    "MethodSummary",
    "Observation",
    "Paragraph",
    "Reference",
    "ScaleInputs",
    "Section",
    "SensitivityEnvelope",
    "Table",
    "Thesis",
    "build_demo_thesis",
    "calculate_reported_statistics",
    "generate_demo_figures",
    "resolve_cjk_font",
    "sensitivity_envelope",
]
