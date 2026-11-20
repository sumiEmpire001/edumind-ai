"""Check content fidelity and standard page structure in both download formats."""

import base64
import io
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from pypdf import PdfReader

from app.services.export_format import blocks
from app.services.pdf_export import render
from app.services.word_export import WORD, export_word

CONTENT = """## Method
A **bold result** with *emphasis*, `code`, α and β.
This is a soft line break.

- First item
  - Nested item
7. Preserve the supplied numbering

| Name | Observation |
| --- | --- |
| Sample A | Escaped pipe: a\\|b |
| Sample B | An observation that must remain editable |

```python
    print("<literal>")
```

[Reference](https://example.org/research)
"""


def test_word_has_page_geometry_styles_tables_and_complete_content():
    data = export_word("Report", "Author", [("Method", CONTENT)])
    with ZipFile(io.BytesIO(base64.b64decode(data["base64"]))) as z:
        assert z.testzip() is None
        root = ET.fromstring(z.read("word/document.xml"))
        styles = ET.fromstring(z.read("word/styles.xml"))
        footer = ET.fromstring(z.read("word/footer1.xml"))
        assert root.find(".//{*}pgSz").get(f"{{{WORD}}}w") == "11906"
        assert root.find(".//{*}pgMar").get(f"{{{WORD}}}left") == "1440"
        assert len(root.findall(".//{*}tbl")) == 1
        assert len(root.findall(".//{*}tr")) == 3
        assert root.find(".//{*}tblHeader") is not None
        assert footer.find(".//{*}fldSimple").get(f"{{{WORD}}}instr").strip() == "PAGE"
        assert any(s.get(f"{{{WORD}}}styleId") == "Heading2" for s in styles)
        text = "".join(t.text or "" for t in root.findall(".//{*}t"))
        assert "**" not in text and "```" not in text
        for expected in [
            "bold result",
            "α and β",
            "a|b",
            '    print("<literal>")',
            "7.",
            "https://example.org/research",
        ]:
            assert expected in text
        assert root.find(".//{*}b") is not None
        assert root.find(".//{*}i") is not None


def test_pdf_long_table_wraps_and_repeats_headers_without_losing_last_row():
    rows = "\n".join(
        f"| Record {i} | " + "Measured value and observation. " * 4 + " |" for i in range(65)
    )
    result = render(
        "Report", "Author", [("Results", "| Record | Observation |\n| --- | --- |\n" + rows)]
    )
    pages = PdfReader(io.BytesIO(base64.b64decode(result["base64"]))).pages
    text = "\n".join(p.extract_text() for p in pages)
    assert len(pages) > 4
    assert text.count("Observation") >= len(pages) - 2
    assert "Record 64" in text
    assert float(pages[0].mediabox.width) == pytest.approx(595.276, abs=0.01)


def test_both_exports_keep_references_and_escape_untrusted_markup():
    result = render("Report", "Author", [("Method", CONTENT + '\n<img src="file:///etc/passwd">')])
    text = "\n".join(
        p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(result["base64"]))).pages
    )
    assert "https://example.org/research" in text
    assert '<img src="file:///etc/passwd">' in text
    assert "soft line break" in text
    assert "**" not in text


def test_parser_keeps_nested_lists_code_and_soft_lines():
    parsed = list(blocks(CONTENT))
    assert ("list", ("•", "Nested item"), 1) in parsed
    assert ("code", '    print("<literal>")', 0) in parsed
    assert any("This is a soft line break." in value for kind, value, _ in parsed if kind == "body")


@pytest.mark.parametrize("exporter", [render, export_word])
def test_export_limits_and_empty_documents(exporter):
    with pytest.raises(ValueError, match="Add or generate"):
        exporter("Report", "Author", [("Blank", "")])
    with pytest.raises(ValueError, match="too large"):
        exporter("Report", "Author", [("Large", "a" * 300001)])
