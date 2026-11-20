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

from app.services.export_format import WIDTH, blocks, column_widths, spans

slots = BoundedSemaphore(2)
font_dir = Path(reportlab.__file__).parent / "fonts"
system_fonts = Path("/usr/share/fonts/truetype/dejavu")
for name, file in [
    ("Studio", "Vera.ttf"),
    ("Studio-Bold", "VeraBd.ttf"),
    ("Studio-Italic", "VeraIt.ttf"),
    ("Studio-BoldItalic", "VeraBI.ttf"),
]:
    unicode_name = {
        "Studio": "DejaVuSerif.ttf",
        "Studio-Bold": "DejaVuSerif-Bold.ttf",
        "Studio-Italic": "DejaVuSerif-Italic.ttf",
        "Studio-BoldItalic": "DejaVuSerif-BoldItalic.ttf",
    }[name]
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
        "body", fontName="Studio", fontSize=12, leading=18, spaceAfter=9, splitLongWords=True
    ),
    "heading": ParagraphStyle(
        "heading",
        fontName="Studio-Bold",
        fontSize=17,
        leading=23,
        spaceAfter=14,
        keepWithNext=True,
        textColor=colors.black,
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
    parts = []
    for text, kind in spans(value):
        text = escape(text)
        tag = {"bold": "b", "italic": "i"}.get(kind)
        parts.append(
            f"<{tag}>{text}</{tag}>"
            if tag
            else f"<font name='Courier'>{text}</font>"
            if kind == "code"
            else text
        )
    return "".join(parts)


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
    flow = []
    for kind, value, level in blocks(content):
        if kind == "table":
            widths = column_widths(value)
            # Very wide tables stay readable as text; no rows are discarded.
            if len(widths) > 6:
                flow.extend(Paragraph(inline(" | ".join(row)), styles["body"]) for row in value)
                continue
            cell_style = ParagraphStyle(
                "cell", parent=styles["body"], fontSize=10, leading=14, spaceAfter=0
            )
            data = [
                [
                    Paragraph(
                        ("<b>" + inline(cell) + "</b>") if index == 0 else inline(cell), cell_style
                    )
                    for cell in row + [""] * (len(widths) - len(row))
                ]
                for index, row in enumerate(value)
            ]
            table = Table(data, colWidths=widths, repeatRows=1, splitInRow=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaeaea")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d9d9")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            flow.extend([table, Spacer(1, 12)])
        elif kind == "code":
            flow.append(Paragraph(escape(value).replace(" ", "&#160;") or "&#160;", styles["code"]))
        elif kind == "heading":
            style = ParagraphStyle(
                f"heading{level}", parent=styles["subheading"], fontSize=14 if level == 2 else 12
            )
            flow.append(Paragraph(inline(value), style))
        elif kind == "list":
            style = ParagraphStyle(
                "list",
                parent=styles["body"],
                leftIndent=18 * (level + 1),
                firstLineIndent=0,
                bulletIndent=18 * level,
                bulletFontName="Studio",
                bulletFontSize=12,
            )
            flow.append(Paragraph(inline(value[1]), style, bulletText=value[0]))
        else:
            flow.append(Paragraph(inline(value), styles["body"]))
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
        leftMargin=72,
        rightMargin=72,
        topMargin=72,
        bottomMargin=72,
        title=title,
        author=author,
        pageCompression=1,
    )

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Studio", 8)
        canvas.setFillColor(colors.HexColor("#52645e"))

        canvas.drawCentredString(A4[0] / 2, 36, f"Page {doc.page}")
        canvas.restoreState()

    frame = Frame(
        72,
        72,
        WIDTH,
        A4[1] - 144,
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
        Paragraph(
            inline(author), ParagraphStyle("author", parent=styles["body"], alignment=TA_CENTER)
        ),
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
