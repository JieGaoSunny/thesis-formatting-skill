"""Header, footer, linking, and page-number repairs."""

from __future__ import annotations

import re

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.ooxml import OoxmlPackage, resolve_relationship_target
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W_NS, "r": R_NS}
W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"


def _new(name: str, **attributes: str) -> etree._Element:
    element = etree.Element(f"{W}{name}")
    for key, value in attributes.items():
        element.set(f"{W}{key}", value)
    return element


def _field(paragraph: etree._Element, instruction: str, placeholder: str) -> None:
    for kind, value in (
        ("begin", None),
        (None, instruction),
        ("separate", None),
        (None, placeholder),
        ("end", None),
    ):
        run = _new("r")
        if kind:
            field = _new("fldChar", fldCharType=kind)
            if kind == "begin":
                field.set(f"{W}dirty", "true")
            run.append(field)
        elif value == instruction:
            code = _new("instrText")
            code.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            code.text = f" {instruction} "
            run.append(code)
        else:
            text = _new("t")
            text.text = value
            run.append(text)
        paragraph.append(run)


def _section_for_paragraph(sections: list[etree._Element], paragraph_index: int) -> int:
    for section_index, section in enumerate(sections, start=1):
        owner = section.getparent()
        if owner is not None and etree.QName(owner).localname == "pPr":
            paragraph = owner.getparent()
            preceding = paragraph.xpath(
                "count(preceding::w:p)", namespaces=NS
            )
            if paragraph_index <= int(preceding) + 1:
                return section_index
    return len(sections)


def _regions(
    sections: list[etree._Element], semantic: SemanticDocument
) -> tuple[int | None, int | None]:
    body = next(
        (
            _section_for_paragraph(
                sections, int(node.location.split(":")[1])
            )
            for node in semantic.paragraphs
            if node.role == "heading_1"
        ),
        None,
    )
    appendix = next(
        (
            _section_for_paragraph(
                sections, int(node.location.split(":")[1])
            )
            for node in semantic.paragraphs
            if node.role == "appendix_heading"
        ),
        None,
    )
    return body, appendix


def _story_has_field(root: etree._Element, prefix: str) -> bool:
    return any(
        re.sub(r"\s+", " ", value).strip().upper().startswith(prefix.upper())
        for value in root.xpath(".//w:instrText/text()", namespaces=NS)
    )


def repair_headers(
    package: OoxmlPackage,
    document: etree._Element,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Repair section stories using only existing package parts and targets."""

    repaired: set[str] = set()
    sections = document.xpath(".//w:sectPr", namespaces=NS)
    body_section, appendix_section = _regions(sections, semantic)
    relationships = {
        (relationship.type.rsplit("/", 1)[-1], relationship.id): (
            resolve_relationship_target(
                relationship.source_part, relationship.target
            )
        )
        for relationship in package.relationships()
        if relationship.source_part == "word/document.xml"
        and relationship.target_mode != "External"
    }
    ids_by_target = {
        (kind, target): relationship_id
        for (kind, relationship_id), target in relationships.items()
    }
    header_targets = [
        target
        for target in package.parts
        if re.fullmatch(r"word/header\d+\.xml", target)
    ]
    footer_targets = [
        target
        for target in package.parts
        if re.fullmatch(r"word/footer\d+\.xml", target)
    ]

    for index, section in enumerate(sections, start=1):
        region = (
            "appendix"
            if appendix_section is not None and index >= appendix_section
            else "body"
            if body_section is not None and index >= body_section
            else "front_matter"
        )
        region_profile = getattr(profile.headers_footers, region)
        expected_role = {
            "current_front_heading": "front_heading",
            "current_heading_1": "heading_1",
            "current_appendix": "appendix_heading",
            "current_appendix_heading": "appendix_heading",
        }.get(region_profile.header_source)
        if expected_role:
            expected_style = profile.styles[expected_role].word_styles[0]
            reference = section.find(
                "w:headerReference[@w:type='default']", namespaces=NS
            )
            current_target = (
                relationships.get(("header", reference.get(f"{R}id", "")))
                if reference is not None
                else None
            )
            if current_target is not None:
                root = package.xml(current_target)
                if not _story_has_field(
                    root, f'STYLEREF "{expected_style}"'
                ):
                    paragraphs = root.xpath(".//w:p", namespaces=NS)
                    paragraph = (
                        paragraphs[0]
                        if paragraphs
                        else etree.SubElement(root, f"{W}p")
                    )
                    placeholder = "".join(
                        paragraph.xpath(".//w:t/text()", namespaces=NS)
                    )
                    for child in list(paragraph):
                        if etree.QName(child).localname != "pPr":
                            paragraph.remove(child)
                    _field(
                        paragraph,
                        f'STYLEREF "{expected_style}"',
                        "",
                    )
                    if placeholder:
                        run = _new("r")
                        text = _new("t")
                        text.text = placeholder
                        run.append(text)
                        paragraph.append(run)
            else:
                target = next(
                    (
                        name
                        for name in header_targets
                        if _story_has_field(
                            package.xml(name),
                            f'STYLEREF "{expected_style}"',
                        )
                    ),
                    None,
                )
                relationship_id = (
                    ids_by_target.get(("header", target)) if target else None
                )
                if relationship_id:
                    if reference is None:
                        reference = etree.Element(f"{W}headerReference")
                        reference.set(f"{W}type", "default")
                        section.insert(0, reference)
                    reference.set(f"{R}id", relationship_id)

        footer_reference = section.find(
            "w:footerReference[@w:type='default']", namespaces=NS
        )
        footer_target = None
        if footer_reference is not None:
            footer_target = relationships.get(
                ("footer", footer_reference.get(f"{R}id", ""))
            )
        if footer_target is None and footer_targets:
            footer_target = footer_targets[0]
        if footer_target and region_profile.page_number_enabled:
            root = package.xml(footer_target)
            page_paragraph = next(
                (
                    paragraph
                    for paragraph in root.xpath(".//w:p", namespaces=NS)
                    if _story_has_field(paragraph, "PAGE")
                ),
                None,
            )
            if page_paragraph is None:
                paragraphs = root.xpath(".//w:p", namespaces=NS)
                page_paragraph = paragraphs[0] if paragraphs else etree.SubElement(
                    root, f"{W}p"
                )
                placeholder = "".join(
                    page_paragraph.xpath(".//w:t/text()", namespaces=NS)
                ) or "1"
                for child in list(page_paragraph):
                    if etree.QName(child).localname != "pPr":
                        page_paragraph.remove(child)
                _field(page_paragraph, "PAGE", "")
                if placeholder != "1":
                    run = _new("r")
                    text = _new("t")
                    text.text = placeholder
                    run.append(text)
                    page_paragraph.append(run)
            p_pr = page_paragraph.find("w:pPr", namespaces=NS)
            if p_pr is None:
                p_pr = etree.Element(f"{W}pPr")
                page_paragraph.insert(0, p_pr)
            jc = p_pr.find("w:jc", namespaces=NS)
            if jc is None:
                jc = etree.SubElement(p_pr, f"{W}jc")
            jc.set(f"{W}val", region_profile.page_number_alignment)

        pg_num = section.find("w:pgNumType", namespaces=NS)
        if pg_num is None:
            pg_num = etree.Element(f"{W}pgNumType")
            _insert_by_schema_order(section, pg_num)
        page_style = region_profile.page_number_style
        pg_num.set(
            f"{W}fmt",
            {"upper_roman": "upperRoman", "decimal": "decimal"}.get(
                page_style, "decimal"
            ),
        )
        if index == body_section:
            pg_num.set(f"{W}start", str(profile.fields.page_number.body_start))

    for finding in findings:
        rule_id = str(finding["rule_id"])
        if rule_id.startswith("HEADER.FOOTER."):
            location = str(finding["location"])
            if location.startswith("section:"):
                section = sections[int(location.split(":")[1]) - 1]
                pg_num = section.find("w:pgNumType", namespaces=NS)
                if pg_num is None:
                    pg_num = etree.Element(f"{W}pgNumType")
                    _insert_by_schema_order(section, pg_num)
                if rule_id == "HEADER.FOOTER.PAGE_RESET":
                    if finding["after"] is None:
                        pg_num.attrib.pop(f"{W}start", None)
                    else:
                        pg_num.set(f"{W}start", str(finding["after"]))
                elif rule_id == "HEADER.FOOTER.PAGE_STYLE":
                    if finding["after"] is None:
                        pg_num.attrib.pop(f"{W}fmt", None)
                    else:
                        pg_num.set(f"{W}fmt", str(finding["after"]))
            repaired.add(f"{rule_id}|{finding['location']}")
    return repaired
