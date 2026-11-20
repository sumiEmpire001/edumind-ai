"""Editable OOXML reports, rendered locally without fetching remote content."""

import base64
import io
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from app.services.export_format import INVALID_XML, blocks, column_widths, spans

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006"
ET.register_namespace("w", WORD)
ET.register_namespace("r", OFFICE)


def node(parent, tag, **attrs):
    return ET.SubElement(
        parent, f"{{{WORD}}}{tag}", {f"{{{WORD}}}{k}": str(v) for k, v in attrs.items()}
    )


def paragraph(body, text="", style="Normal", marker=None, depth=0):
    p = node(body, "p")
    props = node(p, "pPr")
    node(props, "pStyle", val=style)
    if marker:
        node(props, "ind", left=360 * (depth + 1), hanging=360)
        text = marker + "  " + text
    for value, kind in [(text, "code")] if style == "Code" else spans(text):
        run = node(p, "r")
        rp = node(run, "rPr")
        if kind in ("bold", "italic"):
            node(rp, "b" if kind == "bold" else "i")
        if kind == "code":
            node(rp, "rFonts", ascii="Courier New", hAnsi="Courier New")
            node(rp, "sz", val=18)
        t = node(run, "t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = INVALID_XML.sub("\ufffd", value)
    return p


def pagebreak(body):
    node(node(node(body, "p"), "r"), "br", type="page")


def table(body, rows):
    widths = column_widths(rows)
    if len(widths) > 6:
        for row in rows:
            paragraph(body, " | ".join(row))
        return
    tbl = node(body, "tbl")
    props = node(tbl, "tblPr")
    node(props, "tblW", w=9026, type="dxa")
    node(props, "tblLayout", type="fixed")
    borders = node(props, "tblBorders")
    for edge in ("top", "bottom", "left", "right", "insideH", "insideV"):
        node(borders, edge, val="single", sz=4, color="D9D9D9")
    margins = node(props, "tblCellMar")
    for edge in ("top", "bottom", "left", "right"):
        node(margins, edge, w=100, type="dxa")
    grid = node(tbl, "tblGrid")
    for width in widths:
        node(grid, "gridCol", w=round(width * 20))
    for index, row in enumerate(rows):
        tr = node(tbl, "tr")
        if index == 0:
            node(node(tr, "trPr"), "tblHeader")
        for col, width in enumerate(widths):
            cell = node(tr, "tc")
            cp = node(cell, "tcPr")
            node(cp, "tcW", w=round(width * 20), type="dxa")
            node(cp, "vAlign", val="center")
            if index == 0:
                node(cp, "shd", fill="EAEAEA")
            paragraph(
                cell,
                row[col] if col < len(row) else "",
                "TableHeader" if index == 0 else "TableText",
            )
    paragraph(body, "", "TableText")


def styles_xml():
    root = ET.Element(f"{{{WORD}}}styles")
    specs = [
        ("Normal", 24),
        ("Title", 54),
        ("Subtitle", 24),
        ("Contents", 32),
        *[(f"Heading{i}", 32 if i == 1 else 28 if i == 2 else 24) for i in range(1, 7)],
        ("TableText", 20),
        ("TableHeader", 20),
        ("Code", 18),
        ("Footer", 18),
    ]
    for name, size in specs:
        s = node(root, "style", type="paragraph", styleId=name)
        node(s, "name", val=name)
        if name != "Normal":
            node(s, "basedOn", val="Normal")
        p = node(s, "pPr")
        node(
            p,
            "spacing",
            before=2200 if name == "Title" else 240 if name.startswith("Heading") else 0,
            after=120,
            line=360 if name == "Normal" else 260,
            lineRule="auto",
        )
        node(p, "widowControl")
        if name.startswith("Heading"):
            node(p, "keepNext")
            node(p, "outlineLvl", val=int(name[-1]) - 1)
        if name in ("Title", "Subtitle", "Footer"):
            node(p, "jc", val="center")
        r = node(s, "rPr")
        node(
            r,
            "rFonts",
            ascii="Times New Roman",
            hAnsi="Times New Roman",
            eastAsia="Times New Roman",
        )
        node(r, "sz", val=size)
        node(r, "color", val="000000")
        if name.startswith("Heading") or name in ("Title", "Contents", "TableHeader"):
            node(r, "b")
    return ET.tostring(root, encoding="utf-8")


def export_word(title, author, sections):
    if sum(len(content) for _, content in sections) > 300_000:
        raise ValueError("Export is too large. Split the document into parts.")
    if not any(content.strip() for _, content in sections):
        raise ValueError("Add or generate some text before exporting.")
    root = ET.Element(f"{{{WORD}}}document")
    body = node(root, "body")
    paragraph(body, title, "Title")
    paragraph(body, author, "Subtitle")
    pagebreak(body)
    paragraph(body, "Contents", "Contents")
    for heading, _ in sections:
        paragraph(body, heading)
    pagebreak(body)
    for heading, content in sections:
        paragraph(body, heading, "Heading1")
        for kind, value, level in blocks(content or "This section has not been drafted."):
            if kind == "table":
                table(body, value)
            elif kind == "list":
                paragraph(body, value[1], marker=value[0], depth=level)
            else:
                paragraph(
                    body,
                    value,
                    f"Heading{level}"
                    if kind == "heading"
                    else "Code"
                    if kind == "code"
                    else "Normal",
                )
    section = node(body, "sectPr")
    footer_ref = node(section, "footerReference", type="default")
    footer_ref.set(f"{{{OFFICE}}}id", "rId2")
    node(section, "pgSz", w=11906, h=16838)
    node(
        section,
        "pgMar",
        top=1440,
        bottom=1440,
        left=1440,
        right=1440,
        header=720,
        footer=720,
        gutter=0,
    )
    footer = ET.Element(f"{{{WORD}}}ftr")
    p = paragraph(footer, "Page ", "Footer")
    field = node(p, "fldSimple", instr=" PAGE ")
    node(node(field, "r"), "t").text = "1"
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'<Types xmlns="{PACKAGE}/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + "".join(
                f'<Override PartName="/word/{part}.xml" '
                f'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>'
                for part, kind in [
                    ("document", "document.main"),
                    ("styles", "styles"),
                    ("footer1", "footer"),
                ]
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{PACKAGE}/relationships">'
            f'<Relationship Id="rId1" Type="{OFFICE}/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            f'<Relationships xmlns="{PACKAGE}/relationships">'
            f'<Relationship Id="rId1" Type="{OFFICE}/styles" Target="styles.xml"/>'
            f'<Relationship Id="rId2" Type="{OFFICE}/footer" Target="footer1.xml"/>'
            "</Relationships>",
        )
        archive.writestr("word/document.xml", ET.tostring(root, encoding="utf-8"))
        archive.writestr("word/styles.xml", styles_xml())
        archive.writestr("word/footer1.xml", ET.tostring(footer, encoding="utf-8"))
    return {"media_type": MIME, "base64": base64.b64encode(output.getvalue()).decode("ascii")}
