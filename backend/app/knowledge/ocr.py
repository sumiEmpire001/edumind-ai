"""Bounded local OCR for approved PDFs; no document bytes leave the service."""

import csv
import os
import subprocess
import tempfile
import time
from pathlib import Path

MAX_OCR_PAGES = 40


def pdf_ocr(data, pages):
    if len(pages) > MAX_OCR_PAGES:
        raise ValueError("ocr_page_limit")
    deadline = time.monotonic() + 180
    results = {}
    with tempfile.TemporaryDirectory(prefix="edumind-ocr-") as folder:
        root = Path(folder)
        pdf = root / "source.pdf"
        pdf.write_bytes(data)
        for page in pages:

            def run(args):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("ocr_timeout")
                try:
                    subprocess.run(
                        args,
                        check=True,
                        timeout=min(20, remaining),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                    )
                except subprocess.TimeoutExpired:
                    raise ValueError("ocr_timeout") from None
                except (OSError, subprocess.CalledProcessError):
                    raise ValueError("ocr_unavailable") from None

            image = root / "page"
            run(
                [
                    "pdftoppm",
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-singlefile",
                    "-scale-to",
                    "2000",
                    "-gray",
                    str(pdf),
                    str(image),
                ]
            )
            run(
                [
                    "tesseract",
                    str(image.with_suffix(".pgm")),
                    str(root / "result"),
                    "-l",
                    "eng",
                    "--psm",
                    "3",
                    "tsv",
                ]
            )
            tsv = root / "result.tsv"
            if tsv.stat().st_size > 2_000_000:
                raise ValueError("ocr_output_limit")
            lines, confidences = {}, []
            with tsv.open(encoding="utf-8") as stream:
                for row in csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
                    word = (row.get("text") or "").strip()
                    if row.get("level") != "5" or not word:
                        continue
                    confidence = float(row["conf"])
                    confidences.append(confidence)
                    key = (row["block_num"], row["par_num"], row["line_num"])
                    lines.setdefault(key, []).append(word)
            text = "\n".join(" ".join(words) for words in lines.values())
            # Never silently publish a partial document when a page cannot be read.
            if not confidences or sum(confidences) / len(confidences) < 60:
                raise ValueError("ocr_review_required")
            results[page] = text
    return results
