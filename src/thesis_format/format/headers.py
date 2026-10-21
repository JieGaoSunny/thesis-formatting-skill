"""Header, footer, linking, and page-number repairs."""

from __future__ import annotations

from copy import deepcopy
import re

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.ooxml import OoxmlPackage, resolve_relationship_target
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W_NS, "r": R_NS}
W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
PR = f"{{{PR_NS}}}"
RELATIONSHIP_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
CONTENT_TYPES = {
    "header": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.header+xml"
    ),
    "footer": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.footer+xml"
    ),
}


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


def _semantic_section(
    semantic: SemanticDocument,
    paragraph_number: int,
) -> int:
    section_number = 1
    for index, section in enumerate(semantic.sections, start=1):
        if section.start_paragraph <= paragraph_number:
            section_number = index
        else:
            break
    return section_number


def _front_part(
    semantic: SemanticDocument,
    profile: FormatProfile,
    section_number: int,
    body_paragraph: int | None,
):
    nodes = [
        node
        for node in semantic.paragraphs
        if (
            body_paragraph is None
            or int(node.location.split(":")[1]) < body_paragraph
        )
        and _semantic_section(
            semantic, int(node.location.split(":")[1])
        )
        == section_number
    ]
    for part in profile.front_matter.parts:
        expected_styles = {
            value.casefold()
            for value in profile.styles[part.heading_role].word_styles
        }
        if any(
            node.role == part.heading_role
            or (
                node.style_id is not None
                and node.style_id.casefold() in expected_styles
            )
            for node in nodes
        ):
            return part
    return None


def _story_has_field(root: etree._Element, prefix: str) -> bool:
    return any(
        re.sub(r"\s+", " ", value).strip().upper().startswith(prefix.upper())
        for value in root.xpath(".//w:instrText/text()", namespaces=NS)
    )


def _next_part_name(package: OoxmlPackage, kind: str) -> str:
    existing = set(package.parts) | set(package._xml)
    number = 1
    while f"word/{kind}{number}.xml" in existing:
        number += 1
    return f"word/{kind}{number}.xml"


def _next_relationship_id(root: etree._Element) -> str:
    existing = {
        element.get("Id")
        for element in root.findall(f"{PR}Relationship")
    }
    number = 1
    while f"rId{number}" in existing:
        number += 1
    return f"rId{number}"


def _ensure_override(
    package: OoxmlPackage,
    part_name: str,
    kind: str,
) -> None:
    root = package.xml("[Content_Types].xml")
    part = f"/{part_name}"
    matches = root.xpath(
        "./ct:Override[@PartName=$part]",
        namespaces={"ct": CT_NS},
        part=part,
    )
    override = matches[0] if matches else etree.SubElement(
        root, f"{{{CT_NS}}}Override"
    )
    override.set("PartName", part)
    override.set("ContentType", CONTENT_TYPES[kind])


def _new_story_root(kind: str) -> etree._Element:
    return etree.Element(
        f"{W}{'hdr' if kind == 'header' else 'ftr'}",
        nsmap={"w": W_NS, "r": R_NS},
    )


def _set_paragraph_style(
    paragraph: etree._Element,
    style_id: str | None,
) -> etree._Element:
    p_pr = paragraph.find("w:pPr", namespaces=NS)
    if p_pr is None:
        p_pr = etree.Element(f"{W}pPr")
        paragraph.insert(0, p_pr)
    if style_id:
        p_style = p_pr.find("w:pStyle", namespaces=NS)
        if p_style is None:
            p_style = etree.Element(f"{W}pStyle")
            _insert_by_schema_order(p_pr, p_style)
        p_style.set(f"{W}val", style_id)
    return p_pr


def _write_header(
    root: etree._Element,
    region_profile,
    expected_style: str | None,
    paragraph_style: str,
) -> None:
    if expected_style and _story_has_field(
        root, f'STYLEREF "{expected_style}"'
    ):
        return
    expected_text = re.sub(
        r"\s+", " ", region_profile.header_text or ""
    ).strip()
    if (
        region_profile.header_source in {"fixed", "fixed_text"}
        and any(
            re.sub(r"\s+", " ", text).strip() == expected_text
            for text in root.xpath(".//w:p//w:t/text()", namespaces=NS)
        )
    ):
        return
    paragraphs = root.xpath(".//w:p", namespaces=NS)
    paragraph = paragraphs[0] if paragraphs else etree.SubElement(root, f"{W}p")
    _set_paragraph_style(paragraph, paragraph_style)
    if expected_style:
        _field(paragraph, f'STYLEREF "{expected_style}"', "")
    elif region_profile.header_source in {"fixed", "fixed_text"}:
        for child in list(paragraph):
            if etree.QName(child).localname != "pPr":
                paragraph.remove(child)
        run = etree.SubElement(paragraph, f"{W}r")
        text = etree.SubElement(run, f"{W}t")
        text.text = region_profile.header_text or ""


def _write_footer(root: etree._Element, alignment: str) -> None:
    page_paragraph = next(
        (
            paragraph
            for paragraph in root.xpath(".//w:p", namespaces=NS)
            if _story_has_field(paragraph, "PAGE")
        ),
        None,
    )
    if page_paragraph is not None:
        p_pr = _set_paragraph_style(page_paragraph, None)
        jc = p_pr.find("w:jc", namespaces=NS)
        if jc is None:
            jc = etree.SubElement(p_pr, f"{W}jc")
        jc.set(f"{W}val", alignment)
        return
    paragraph = etree.SubElement(root, f"{W}p")
    p_pr = _set_paragraph_style(paragraph, None)
    jc = etree.SubElement(p_pr, f"{W}jc")
    jc.set(f"{W}val", alignment)
    _field(paragraph, "PAGE", "")


def repair_headers(
    package: OoxmlPackage,
    document: etree._Element,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Create and repair section stories, relationships, and package metadata."""

    repaired: set[str] = set()
    sections = document.xpath(".//w:sectPr", namespaces=NS)
    body_section, appendix_section = _regions(sections, semantic)
    body_paragraph = next(
        (
            int(node.location.split(":")[1])
            for node in semantic.paragraphs
            if node.role == "heading_1"
        ),
        None,
    )
    rels_name = "word/_rels/document.xml.rels"
    if rels_name in package.parts:
        rels_root = package.xml(rels_name)
    else:
        rels_root = etree.Element(
            f"{PR}Relationships", nsmap={None: PR_NS}
        )
        package._xml[rels_name] = rels_root

    def relationship_target(relationship_id: str | None) -> str | None:
        if not relationship_id:
            return None
        relationship = rels_root.find(
            f"{PR}Relationship[@Id='{relationship_id}']"
        )
        if relationship is None or relationship.get("TargetMode") == "External":
            return None
        target = relationship.get("Target")
        return (
            resolve_relationship_target("word/document.xml", target)
            if target
            else None
        )

    def relationship_id(kind: str, target: str) -> str:
        relative = target.removeprefix("word/")
        for relationship in rels_root.findall(f"{PR}Relationship"):
            if (
                relationship.get("Type") == f"{RELATIONSHIP_TYPE}/{kind}"
                and relationship.get("Target") == relative
            ):
                return str(relationship.get("Id"))
        identifier = _next_relationship_id(rels_root)
        relationship = etree.SubElement(rels_root, f"{PR}Relationship")
        relationship.set("Id", identifier)
        relationship.set("Type", f"{RELATIONSHIP_TYPE}/{kind}")
        relationship.set("Target", relative)
        return identifier

    def create_story(
        kind: str,
        source_target: str | None = None,
    ) -> tuple[str, str]:
        target = _next_part_name(package, kind)
        package._xml[target] = (
            deepcopy(package.xml(source_target))
            if source_target is not None
            else _new_story_root(kind)
        )
        _ensure_override(package, target, kind)
        return target, relationship_id(kind, target)

    def set_reference(
        section: etree._Element,
        kind: str,
        identifier: str,
    ) -> None:
        reference = section.find(
            f"w:{kind}Reference[@w:type='default']", namespaces=NS
        )
        if reference is None:
            reference = etree.Element(f"{W}{kind}Reference")
            reference.set(f"{W}type", "default")
            section.insert(0, reference)
        reference.set(f"{R}id", identifier)

    previous_targets: dict[str, str | None] = {"header": None, "footer": None}
    previous_header_link_key: tuple[str, str, str, str | None] | None = None

    for index, section in enumerate(sections, start=1):
        region = (
            "appendix"
            if appendix_section is not None and index >= appendix_section
            else "body"
            if body_section is not None and index >= body_section
            else "front_matter"
        )
        region_profile = getattr(profile.headers_footers, region)
        front_part = (
            _front_part(
                semantic,
                profile,
                index,
                body_paragraph,
            )
            if region == "front_matter"
            else None
        )
        header_enabled = region_profile.header_enabled and (
            front_part is None or front_part.show_header
        )
        page_number_enabled = region_profile.page_number_enabled and (
            front_part is None or front_part.page_number_style != "none"
        )
        page_number_style = (
            front_part.page_number_style
            if front_part is not None
            else region_profile.page_number_style
        )
        expected_role = {
            "current_front_heading": "front_heading",
            "current_heading_1": "heading_1",
            "current_appendix": "appendix_heading",
            "current_appendix_heading": "appendix_heading",
        }.get(region_profile.header_source)
        expected_style = (
            profile.styles[expected_role].word_styles[0]
            if expected_role
            else None
        )
        linking = profile.headers_footers.section_linking
        header_link_key = (
            region,
            region_profile.header_source,
            region_profile.header_style_role,
            region_profile.header_text,
        )
        link_header = (
            index > 1
            and {
                "front_matter": False,
                "body": linking.link_body_headers,
                "appendix": linking.link_appendix_headers,
            }[region]
            and header_enabled
            and header_link_key == previous_header_link_key
        )
        link_footer = (
            index > 1
            and {
                "front_matter": False,
                "body": linking.link_body_footers,
                "appendix": linking.link_appendix_footers,
            }[region]
            and page_number_enabled
        )

        if header_enabled:
            header_reference = section.find(
                "w:headerReference[@w:type='default']", namespaces=NS
            )
            header_target = (
                previous_targets["header"] if link_header else None
            ) or relationship_target(
                header_reference.get(f"{R}id")
                if header_reference is not None
                else None
            )
            if (
                header_target is None
                or (
                    not link_header
                    and header_target == previous_targets["header"]
                )
            ):
                header_target, header_id = create_story(
                    "header", header_target
                )
            else:
                header_id = relationship_id("header", header_target)
            set_reference(section, "header", header_id)
            _write_header(
                package.xml(header_target),
                region_profile,
                expected_style,
                profile.styles[
                    region_profile.header_style_role
                ].word_styles[0],
            )
            previous_targets["header"] = header_target
        else:
            previous_targets["header"] = relationship_target(
                section.xpath(
                    "./w:headerReference[@w:type='default']/@r:id",
                    namespaces=NS,
                )[0]
                if section.xpath(
                    "./w:headerReference[@w:type='default']/@r:id",
                    namespaces=NS,
                )
                else None
            )
        previous_header_link_key = header_link_key if header_enabled else None

        if page_number_enabled:
            footer_reference = section.find(
                "w:footerReference[@w:type='default']", namespaces=NS
            )
            footer_target = (
                previous_targets["footer"] if link_footer else None
            ) or relationship_target(
                footer_reference.get(f"{R}id")
                if footer_reference is not None
                else None
            )
            if (
                footer_target is None
                or (
                    not link_footer
                    and footer_target == previous_targets["footer"]
                )
            ):
                footer_target, footer_id = create_story(
                    "footer", footer_target
                )
            else:
                footer_id = relationship_id("footer", footer_target)
            set_reference(section, "footer", footer_id)
            _write_footer(
                package.xml(footer_target),
                region_profile.page_number_alignment,
            )
            previous_targets["footer"] = footer_target

        if page_number_enabled:
            pg_num = section.find("w:pgNumType", namespaces=NS)
            if pg_num is None:
                pg_num = etree.Element(f"{W}pgNumType")
                _insert_by_schema_order(section, pg_num)
            pg_num.set(
                f"{W}fmt",
                {"upper_roman": "upperRoman", "decimal": "decimal"}.get(
                    page_number_style, "decimal"
                ),
            )
            if index == body_section:
                pg_num.set(
                    f"{W}start", str(profile.fields.page_number.body_start)
                )

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
