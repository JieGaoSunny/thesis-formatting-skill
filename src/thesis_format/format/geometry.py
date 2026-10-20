"""Section geometry repairs."""

from __future__ import annotations

from lxml import etree

from thesis_format.profile import FormatProfile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _twips(mm: float) -> str:
    return str(round(mm * 1440 / 25.4))


def _child(parent: etree._Element, name: str) -> etree._Element:
    element = parent.find(f"w:{name}", namespaces=NS)
    if element is None:
        element = etree.SubElement(parent, f"{W}{name}")
    return element


def repair_geometry(
    document: etree._Element,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Repair audited section geometry and return repaired rule/location keys."""

    repaired: set[str] = set()
    sections = document.xpath(".//w:sectPr", namespaces=NS)
    for finding in findings:
        location = str(finding["location"])
        if not location.startswith("section:"):
            continue
        index = int(location.split(":")[1]) - 1
        if not 0 <= index < len(sections):
            continue
        section = sections[index]
        rule_id = str(finding["rule_id"])
        if rule_id == "PAGE.PAPER.SIZE":
            size = _child(section, "pgSz")
            size.set(f"{W}w", _twips(profile.page.paper.width_mm))
            size.set(f"{W}h", _twips(profile.page.paper.height_mm))
        elif rule_id == "PAGE.MARGIN.BODY":
            margin = _child(section, "pgMar")
            for name, value in (
                ("top", profile.page.body.top_mm),
                ("bottom", profile.page.body.bottom_mm),
                ("left", profile.page.body.left_mm),
                ("right", profile.page.body.right_mm),
            ):
                margin.set(f"{W}{name}", _twips(value))
        elif rule_id == "PAGE.HEADER_FOOTER_DISTANCE":
            margin = _child(section, "pgMar")
            margin.set(f"{W}header", _twips(profile.page.header_distance_mm))
            margin.set(f"{W}footer", _twips(profile.page.footer_distance_mm))
        elif rule_id == "PAGE.SECTION.START":
            section_type = _child(section, "type")
            section_type.set(f"{W}val", str(finding["after"]))
        else:
            continue
        repaired.add(f"{rule_id}|{location}")
    return repaired
