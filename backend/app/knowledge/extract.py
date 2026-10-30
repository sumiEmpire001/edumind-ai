import csv
import io
import posixpath
import re
import zipfile
from pathlib import PurePath

from defusedxml import ElementTree
from pypdf import PdfReader

MAX_BYTES = 3 * 1024 * 1024
MIMES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def validate(filename, data, mime):
    ext = PurePath(filename).suffix.lower()
    if not data or len(data) > MAX_BYTES or ext not in MIMES:
        raise ValueError("unsupported_or_oversized_file")
    if mime != MIMES[ext]:
        raise ValueError("file_type_mismatch")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("invalid_pdf")
    if ext in {".docx", ".pptx"}:
        if not data.startswith(b"PK\x03\x04"):
            raise ValueError("invalid_office_signature")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1500 or sum(i.file_size for i in entries) > 20 * MAX_BYTES:
                raise ValueError("archive_limits")
            expected = "word/document.xml" if ext == ".docx" else "ppt/presentation.xml"
            if (
                expected not in archive.namelist()
                or "[Content_Types].xml" not in archive.namelist()
            ):
                raise ValueError("invalid_office_file")
            if any("vbaproject" in i.filename.lower() or i.flag_bits & 1 for i in entries):
                raise ValueError("unsupported_active_content")
    if ext in {".txt", ".csv"}:
        text = data.decode("utf-8-sig")
        if "\x00" in text or text.lstrip().lower().startswith(
            ("<html", "<!doctype html", "<script")
        ):
            raise ValueError("invalid_text")
    return ext


def extract(filename, data, mime):
    ext = validate(filename, data, mime)
    metadata = {"file_type": ext[1:]}
    sections = []
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 500:
            raise ValueError("encrypted_or_oversized_pdf")
        metadata["page_count"] = len(reader.pages)
        info = reader.metadata
        if info:
            for source, key in [
                ("/Title", "embedded_title"),
                ("/Author", "author"),
                ("/Subject", "subject"),
            ]:
                if info.get(source):
                    metadata[key] = str(info[source])[:200]
        sections = [
            (f"Page {i + 1}", page.extract_text() or "") for i, page in enumerate(reader.pages)
        ]
    elif ext in {".docx", ".pptx"}:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if "docProps/core.xml" in archive.namelist():
                core = ElementTree.fromstring(archive.read("docProps/core.xml"))
                fields = {"creator": "author", "title": "embedded_title", "subject": "subject"}
                for item in core:
                    key = fields.get(item.tag.rsplit("}", 1)[-1])
                    if key and item.text and item.text.strip():
                        metadata[key] = item.text.strip()[:200]
            names = ["word/document.xml"]
            if ext == ".pptx":
                presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
                relationships = ElementTree.fromstring(
                    archive.read("ppt/_rels/presentation.xml.rels")
                )
                targets = {
                    item.get("Id"): item.get("Target")
                    for item in relationships
                    if item.get("TargetMode") != "External"
                }
                names = []
                for item in presentation.iter():
                    if item.tag.endswith("}sldId"):
                        rid = item.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                        )
                        target = targets.get(rid)
                        if not target:
                            raise ValueError("invalid_slide_reference")
                        name = posixpath.normpath("ppt/" + target)
                        if not name.startswith("ppt/slides/") or name not in archive.namelist():
                            raise ValueError("invalid_slide_reference")
                        names.append(name)
                metadata["slide_count"] = len(names)
            for i, name in enumerate(names):
                root = ElementTree.fromstring(archive.read(name))
                sections.append(
                    (
                        f"Slide {i + 1}" if ext == ".pptx" else "Document text",
                        " ".join(e.text or "" for e in root.iter() if e.tag.endswith("}t")),
                    )
                )
    else:
        text = data.decode("utf-8-sig")
        if ext == ".csv":
            text = "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(text)))
        sections = [("Text", text)]
    cleaned = [(loc, re.sub(r"[ \t]+", " ", text).strip()) for loc, text in sections]
    if sum(len(t) for _, t in cleaned) > 500000:
        raise ValueError("extracted_text_too_large")
    if not any(t for _, t in cleaned):
        raise ValueError("no_text_ocr_required")
    return cleaned, metadata


def chunk(sections, size=1800, overlap=200):
    result = []
    for location, text in sections:
        for start in range(0, len(text), size - overlap):
            value = text[start : start + size].strip()
            if value:
                result.append((location, value))
    if len(result) > 400:
        raise ValueError("too_many_chunks")
    return result
