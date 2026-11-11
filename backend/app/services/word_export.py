"""Build an editable Word document from saved Studio sections."""

import base64
import io
import re
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PACKAGE = "http://schemas.openxmlformats.org/package/2006"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
INVALID_XML = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
HEADING = re.compile(r"^#{1,6}\s+(.+)$")


def paragraph(body, text, *, size=None, level=None, code=False):
    p = ET.SubElement(body, f"{{{WORD}}}p")
    if level is not None:
        props = ET.SubElement(p, f"{{{WORD}}}pPr")
        ET.SubElement(props, f"{{{WORD}}}outlineLvl", {f"{{{WORD}}}val": str(level)})
    run = ET.SubElement(p, f"{{{WORD}}}r")
    if size or code:
        props = ET.SubElement(run, f"{{{WORD}}}rPr")
        if code:
            ET.SubElement(props, f"{{{WORD}}}rFonts", {f"{{{WORD}}}ascii": "Courier New"})
        if size:
            ET.SubElement(props, f"{{{WORD}}}b")
            ET.SubElement(props, f"{{{WORD}}}sz", {f"{{{WORD}}}val": str(size)})
    node = ET.SubElement(
        run, f"{{{WORD}}}t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"}
    )
    node.text = INVALID_XML.sub("\ufffd", text)


def export_word(title, author, sections):
    if sum(len(content) for _, content in sections) > 300_000:
        raise ValueError("Export is too large. Split the document into parts.")
    if not any(content.strip() for _, content in sections):
        raise ValueError("Add or generate some text before exporting.")

    root = ET.Element(f"{{{WORD}}}document")
    body = ET.SubElement(root, f"{{{WORD}}}body")
    paragraph(body, title, size=40)
    paragraph(body, author)
    for heading, content in sections:
        paragraph(body, heading, size=30, level=0)
        in_code = False
        for line in content.splitlines():
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            match = HEADING.match(line) if not in_code else None
            if match:
                paragraph(body, match[1], size=24, level=1)
            else:
                paragraph(body, line, code=in_code)

    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'<Types xmlns="{PACKAGE}/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            f'<Override PartName="/word/document.xml" ContentType="{MIME}.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{PACKAGE}/relationships">'
            f'<Relationship Id="rId1" Type="{OFFICE}/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        archive.writestr("word/document.xml", ET.tostring(root, encoding="utf-8"))
    return {"media_type": MIME, "base64": base64.b64encode(output.getvalue()).decode("ascii")}
