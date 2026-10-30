"""Bounded, local-only PDF rendering. Input is text, never executable HTML or remote URLs."""

import base64
import io
import re
from pathlib import Path
from threading import BoundedSemaphore
from xml.sax.saxutils import escape

import reportlab
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

slots = BoundedSemaphore(2)
font_dir = Path(reportlab.__file__).parent / "fonts"
system_fonts = Path("/usr/share/fonts/truetype/dejavu")
for name, file in [
    ("Studio", "Vera.ttf"),
    ("Studio-Bold", "VeraBd.ttf"),
    ("Studio-Italic", "VeraIt.ttf"),
    ("Studio-BoldItalic", "VeraBI.ttf"),
]:
    unicode_name = "DejaVuSans-Bold.ttf" if "Bold" in name else "DejaVuSans.ttf"
    unicode_font = system_fonts / unicode_name
    pdfmetrics.registerFont(
        TTFont(name, str(unicode_font if unicode_font.exists() else font_dir / file))
    )
pdfmetrics.registerFontFamily(
    "Studio",
    normal="Studio",
    bold="Studio-Bold",
    italic="Studio-Italic",
    boldItalic="Studio-BoldItalic",
)

styles = {
    "body": ParagraphStyle(
        "body", fontName="Studio", fontSize=10.5, leading=16, spaceAfter=9, splitLongWords=True
    ),
    "heading": ParagraphStyle(
        "heading",
        fontName="Studio-Bold",
        fontSize=17,
        leading=23,
        spaceAfter=14,
        keepWithNext=True,
        textColor=colors.HexColor("#173c34"),
    ),
    "subheading": ParagraphStyle(
        "subheading",
        fontName="Studio-Bold",
        fontSize=12.5,
        leading=18,
        spaceBefore=12,
        spaceAfter=8,
        keepWithNext=True,
    ),
    "cover": ParagraphStyle(
        "cover", fontName="Studio-Bold", fontSize=27, leading=35, alignment=TA_CENTER, spaceAfter=24
    ),
    "small": ParagraphStyle(
        "small",
        fontName="Studio",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#52645e"),
        spaceAfter=10,
    ),
    "code": ParagraphStyle(
        "code",
        fontName="Courier",
        fontSize=8.5,
        leading=12,
        spaceAfter=8,
        backColor=colors.HexColor("#f1f4f2"),
        borderPadding=7,
        splitLongWords=True,
    ),
}


def inline(value):
    value = escape(value.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-"))
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    return re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", value)


class Document(BaseDocTemplate):
    def beforeDocument(self):
        self.heading_index = 0

    def afterFlowable(self, flowable):
        if getattr(flowable, "toc_entry", False):
            key = f"section-{self.heading_index}"
            self.heading_index += 1
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page, key))

    def afterPage(self):
        if self.page > 100:
            raise ValueError("Export exceeds 100 pages. Split this document into parts.")


def markdown(content):
    flow, lines, i = [], content.splitlines(), 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            # Separate paragraphs allow long code blocks to split across pages.
            for source_line in code:
                flow.append(
                    Paragraph(
                        escape(source_line).replace(" ", "&#160;") or "&#160;", styles["code"]
                    )
                )
        elif (
            line.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|?\s*:?-", lines[i + 1].strip())
        ):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                values = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\-\s]+", cell) for cell in values):
                    rows.append(values)
                i += 1
            i -= 1
            columns = max(map(len, rows))
            if columns <= 6 and all(len(cell) < 400 for row in rows for cell in row):
                data = [
                    [
                        Paragraph(inline(cell), styles["small"])
                        for cell in row + [""] * (columns - len(row))
                    ]
                    for row in rows
                ]
                table = Table(data, colWidths=[(A4[0] - 100) / columns] * columns, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3eee8")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cad8d0")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ]
                    )
                )
                flow.extend([table, Spacer(1, 12)])
            else:
                flow.extend(Paragraph(inline(" | ".join(row)), styles["body"]) for row in rows)
        elif line.startswith("#"):
            flow.append(Paragraph(inline(line.lstrip("# ")), styles["subheading"]))
        else:
            flow.append(Paragraph(inline(line), styles["body"]))
        i += 1
    return flow


def render(title, author, sections, note=""):
    if sum(len(content) for _, content in sections) > 300_000:
        raise ValueError("Export is too large. Split the document into parts.")
    if not any(content.strip() for _, content in sections):
        raise ValueError("Add or generate some text before exporting.")
    output = io.BytesIO()
    document = Document(
        output,
        pagesize=A4,
        leftMargin=50,
        rightMargin=50,
        topMargin=57,
        bottomMargin=53,
        title=title,
        author=author,
        pageCompression=1,
    )

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Studio", 8)
        canvas.setFillColor(colors.HexColor("#52645e"))
        canvas.drawString(50, A4[1] - 32, "EDUMIND STUDIO")
        canvas.drawRightString(A4[0] - 50, 29, f"Page {doc.page}")
        canvas.restoreState()

    frame = Frame(
        50,
        53,
        A4[0] - 100,
        A4[1] - 110,
        id="normal",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    document.addPageTemplates([PageTemplate(id="normal", frames=[frame], onPage=page)])
    story = [
        Spacer(1, 110),
        Paragraph(inline(title), styles["cover"]),
        Paragraph(inline(author), styles["body"]),
    ]
    if note:
        story.append(Paragraph(inline(note), styles["small"]))
    story.extend([PageBreak(), Paragraph("Contents", styles["heading"])])
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "toc",
            fontName="Studio",
            fontSize=10,
            leading=18,
            leftIndent=10,
            firstLineIndent=-10,
            spaceBefore=6,
        )
    ]
    story.extend([toc, PageBreak()])
    for heading, content in sections:
        entry = Paragraph(inline(heading), styles["heading"])
        entry.toc_entry = True
        story.extend([entry, *markdown(content or "This section has not been drafted.")])
        story.append(Spacer(1, 14))
    document.multiBuild(story)
    data = output.getvalue()
    return {
        "filename": "edumind-document.pdf",
        "media_type": "application/pdf",
        "base64": base64.b64encode(data).decode(),
        "page_count": len(PdfReader(io.BytesIO(data)).pages),
        "word_count": sum(len(re.findall(r"\S+", content)) for _, content in sections),
    }


def export(title, author, sections, note=""):
    if not slots.acquire(blocking=False):
        from fastapi import HTTPException

        raise HTTPException(503, "PDF export is busy. Please try again.")
    try:
        return render(title, author, sections, note)
    except ValueError:
        raise
    except Exception:
        raise ValueError(
            "This layout could not be exported. Shorten unusually long rows or headings."
        ) from None
    finally:
        slots.release()
