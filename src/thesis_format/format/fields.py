"""Generated field and bookmark-safe repairs."""

from __future__ import annotations

import re

from lxml import etree

from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def repair_fields(
    document: etree._Element,
    settings: etree._Element | None,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Repair known field codes, mark fields dirty, and never invent bookmarks."""

    repaired: set[str] = set()
    required = {
        "FIELD.TOC.REQUIRED": profile.fields.toc.field_code,
        "FIELD.LIST_OF_FIGURES.REQUIRED": profile.fields.list_of_figures.field_code,
        "FIELD.LIST_OF_TABLES.REQUIRED": profile.fields.list_of_tables.field_code,
    }
    codes = document.xpath(".//w:instrText", namespaces=NS)
    for finding in findings:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        if rule_id == "FIELD.CROSS_REFERENCE.TARGET":
            continue
        expected = required.get(rule_id)
        if expected is None:
            continue
        expected_prefix = (
            "TOC \\o"
            if rule_id == "FIELD.TOC.REQUIRED"
            else 'TOC \\h \\z \\c "图"'
            if rule_id == "FIELD.LIST_OF_FIGURES.REQUIRED"
            else 'TOC \\h \\z \\c "表"'
        )
        candidate = next(
            (
                code
                for code in codes
                if (
                    _normalized(code.text or "").upper().startswith("TOC")
                    and (
                        rule_id == "FIELD.TOC.REQUIRED"
                        and "\\O" in _normalized(code.text or "").upper()
                        or rule_id == "FIELD.LIST_OF_FIGURES.REQUIRED"
                        and '"图"' in _normalized(code.text or "")
                        or rule_id == "FIELD.LIST_OF_TABLES.REQUIRED"
                        and '"表"' in _normalized(code.text or "")
                    )
                )
            ),
            None,
        )
        if candidate is not None:
            candidate.text = f" {expected} "
            repaired.add(f"{rule_id}|{location}")
        elif any(
            _normalized(field).casefold() == _normalized(expected_prefix).casefold()
            for node in semantic.paragraphs
            for field in node.fields
        ):
            repaired.add(f"{rule_id}|{location}")

    for begin in document.xpath(
        ".//w:fldChar[@w:fldCharType='begin']", namespaces=NS
    ):
        begin.set(f"{W}dirty", "true")
    if settings is not None:
        update = settings.find("w:updateFields", namespaces=NS)
        if update is None:
            update = etree.Element(f"{W}updateFields")
            successors = {
                "hdrShapeDefaults",
                "footnotePr",
                "endnotePr",
                "compat",
                "docVars",
                "rsids",
                "mathPr",
                "attachedSchema",
                "themeFontLang",
                "clrSchemeMapping",
                "doNotIncludeSubdocsInStats",
                "doNotAutoCompressPictures",
                "forceUpgrade",
                "captions",
                "readModeInkLockDown",
                "smartTagType",
                "schemaLibrary",
                "shapeDefaults",
                "doNotEmbedSmartTags",
                "decimalSymbol",
                "listSeparator",
            }
            for index, child in enumerate(settings):
                if etree.QName(child).localname in successors:
                    settings.insert(index, update)
                    break
            else:
                settings.append(update)
        update.set(f"{W}val", "true")
    return repaired
