import io
import shutil
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from app.knowledge.extract import extract
from app.knowledge.ocr import pdf_ocr


def scanned_pdf():
    image = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 36)
    draw.multiline_text(
        (60, 60),
        "Sutterby nanofluid research\nThe experiment uses water as the base "
        "fluid.\nThe measured temperature is 300 kelvin.",
        font=font,
        fill="black",
        spacing=25,
    )
    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(
        40,
        780,
        "Native page: this is the introduction to our experiment with fluids and heat transfer.",
    )
    canvas.showPage()
    canvas.drawImage(ImageReader(image), 30, 350, width=540, height=270)
    canvas.save()
    return stream.getvalue()


def test_mixed_pdf_keeps_page_numbers_and_ocr_provenance():
    data = scanned_pdf()
    with patch("app.knowledge.ocr.pdf_ocr", return_value={2: "Water is the base fluid."}) as ocr:
        sections, metadata = extract("scan.pdf", data, "application/pdf", allow_ocr=True)
    assert "Native page" in sections[0][1]
    assert sections[1] == ("Page 2 (OCR)", "Water is the base fluid.")
    assert metadata["ocr_pages"] == [2]
    assert ocr.call_args.args == (data, [2])


def test_preview_does_not_launch_ocr():
    with patch("app.knowledge.ocr.pdf_ocr") as ocr:
        _, metadata = extract("scan.pdf", scanned_pdf(), "application/pdf")
    ocr.assert_not_called()
    assert metadata["ocr_required_pages"] == [2]


def test_ocr_limits_and_failure_do_not_publish_partial_text():
    with pytest.raises(ValueError, match="ocr_page_limit"):
        pdf_ocr(b"pdf", list(range(1, 42)))
    with patch("app.knowledge.ocr.pdf_ocr", side_effect=ValueError("ocr_review_required")):
        with pytest.raises(ValueError, match="ocr_review_required"):
            extract("scan.pdf", scanned_pdf(), "application/pdf", allow_ocr=True)


@pytest.mark.skipif(
    not shutil.which("tesseract") or not shutil.which("pdftoppm"), reason="OCR binaries unavailable"
)
def test_real_local_ocr_reads_image_text():
    sections, metadata = extract("scan.pdf", scanned_pdf(), "application/pdf", allow_ocr=True)
    assert "water" in sections[1][1].lower()
    assert "300" in sections[1][1]
    assert metadata["ocr_pages"] == [2]
