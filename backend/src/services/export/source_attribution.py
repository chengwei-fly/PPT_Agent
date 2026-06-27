"""Source attribution writer (T251 / R11).

Per spec R11: write to XMP / customXml/item1.xml — NOT into rendered PPTX content.
This keeps audit metadata separate from user-visible content.
"""

from __future__ import annotations

from typing import Any

from lxml import etree

from src.core.observability import get_logger

logger = get_logger("export.source_attribution")

CUSTOM_XML_NS = "pptagent:source"
CUSTOM_XML_KEY = "{pptagent:source}attribution"

# Office custom XML namespace
OPC_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CUSTOM_XML_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
)


def _build_attribution_xml(
    source_type: str,
    material_id: str | None = None,
    stage_id: str | None = None,
    sample_id: str | None = None,
    page_index: int | None = None,
) -> bytes:
    """Build the custom XML document for source attribution."""
    root = etree.Element(
        f"{{{CUSTOM_XML_NS}}}source",
        attrib={"type": source_type},
        nsmap={None: CUSTOM_XML_NS},
    )
    if material_id:
        root.set("materialId", material_id)
    if stage_id:
        root.set("stageId", stage_id)
    if sample_id:
        root.set("sampleId", sample_id)
    if page_index is not None:
        root.set("pageIndex", str(page_index))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def add_source_to_slide(
    slide: Any,
    source_type: str,
    material_id: str | None = None,
    stage_id: str | None = None,
    sample_id: str | None = None,
    page_index: int | None = None,
) -> None:
    """Write per-slide source attribution into the slide.

    Strategy:
    1. Set slide.name with attribution summary (accessibility tree)
    2. Add custom properties to the package if available
    3. Attach custom XML part to the slide's package part
    """
    # Build attribution summary for slide.name fallback
    attr_summary = f"type={source_type}"
    if material_id:
        attr_summary += f";material={material_id}"
    if stage_id:
        attr_summary += f";stage={stage_id}"
    if sample_id:
        attr_summary += f";sample={sample_id}"
    if page_index is not None:
        attr_summary += f";page={page_index}"

    # 1. Set slide name (always works, visible in accessibility tree)
    try:
        slide.name = f"slide-{source_type} | {attr_summary}"
    except Exception as e:
        logger.debug("attribution_name_failed", error=str(e))

    # 2. Set custom properties on the package
    try:
        pkg = slide.part.package
        if hasattr(pkg, "custom_properties") and pkg.custom_properties is not None:
            props = pkg.custom_properties
            props[f"pptagent:sourceType:{slide.name}"] = source_type
            if material_id:
                props[f"pptagent:materialId:{slide.name}"] = material_id
            if sample_id:
                props[f"pptagent:sampleId:{slide.name}"] = sample_id
            if page_index is not None:
                props[f"pptagent:pageIndex:{slide.name}"] = str(page_index)
    except Exception as e:
        logger.debug("attribution_props_failed", error=str(e))

    # 3. Attach custom XML to slide part
    try:
        xml_bytes = _build_attribution_xml(
            source_type=source_type,
            material_id=material_id,
            stage_id=stage_id,
            sample_id=sample_id,
            page_index=page_index,
        )
        slide_part = slide.part
        pkg = slide_part.package

        # Create a custom XML part
        from pptx.opc.packuri import PackURI
        from pptx.opc.part import Part

        # Generate a unique part name
        existing_count = len(
            [
                p
                for p in pkg.part_related_by.values()
                if "customXml" in str(getattr(p, "partname", ""))
            ]
        )
        part_name = f"/customXml/item{existing_count + 2}.xml"  # item1.xml is often reserved

        custom_part = Part(
            PackURI(part_name),
            "application/xml",
            xml_bytes,
            pkg,
        )

        # Add relationship from slide to custom XML
        slide_part.relate_to(custom_part, CUSTOM_XML_REL_TYPE)
    except Exception as e:
        # Custom XML attachment is best-effort; slide.name is the fallback
        logger.debug("attribution_xml_failed", error=str(e))


def get_source_from_slide(slide: Any) -> dict[str, str | int | None]:
    """Extract source attribution from a slide (reverse of add_source_to_slide).

    Returns a dict with source_type, material_id, stage_id, sample_id, page_index.
    """
    result: dict[str, str | int | None] = {
        "source_type": "manual",
        "material_id": None,
        "stage_id": None,
        "sample_id": None,
        "page_index": None,
    }

    try:
        name = slide.name or ""
        if " | " in name:
            _, attr_part = name.split(" | ", 1)
            for kv in attr_part.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k == "type":
                        result["source_type"] = v
                    elif k == "material":
                        result["material_id"] = v
                    elif k == "stage":
                        result["stage_id"] = v
                    elif k == "sample":
                        result["sample_id"] = v
                    elif k == "page":
                        try:
                            result["page_index"] = int(v)
                        except ValueError:
                            logger.debug("attribution_parse_page_failed", value=v)
    except Exception as e:
        logger.debug("attribution_parse_failed", error=str(e))

    return result
