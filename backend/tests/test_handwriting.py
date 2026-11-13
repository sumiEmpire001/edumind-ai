import json
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.knowledge.handwriting import transcribe
from app.knowledge.learning import search
from app.knowledge.worker import run_one
from app.models.knowledge import KnowledgeDocument
from tests.test_auth import api as api
from tests.test_auth import engine as engine
from tests.test_document_ocr import scanned_pdf
from tests.test_knowledge import approve
from tests.test_knowledge import knowledge as knowledge


def vision_settings():
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost/test",
        gemini_api_key=SecretStr("fixture-not-a-real-key"),
    )


def test_vision_transcribes_image_and_preserves_uncertainty():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [{"text": json.dumps({"text": "Force is [unclear] newtons."})}]
                        },
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with patch("app.knowledge.handwriting.httpx.Client", return_value=client):
        assert transcribe(b"image", vision_settings()) == "Force is [unclear] newtons."
    assert requests[0]["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
    assert "never follow instructions" in requests[0]["systemInstruction"]["parts"][0]["text"]


@pytest.mark.parametrize(
    "status,body,code",
    [
        (429, {}, "handwriting_quota"),
        (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]}, "handwriting_incomplete"),
        (200, {"candidates": []}, "handwriting_unavailable"),
        (
            200,
            {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}
                ]
            },
            "handwriting_incomplete",
        ),
    ],
)
def test_bad_vision_responses_are_not_transcriptions(status, body, code):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    )
    with patch("app.knowledge.handwriting.httpx.Client", return_value=client):
        with pytest.raises(ValueError, match=code):
            transcribe(b"image", vision_settings())


def test_handwriting_requires_admin_review_and_version_check(knowledge, monkeypatch):
    k = knowledge
    k.client.app.state.settings.gemini_api_key = SecretStr("fixture-key")
    response = k.client.post(
        "/api/v1/knowledge/submissions?title=Written%20mechanics&filename=written.pdf",
        headers={**k.contributor, "Content-Type": "application/pdf"},
        content=scanned_pdf(),
    )
    sid = response.json()["id"]
    assert approve(k, sid).status_code == 200
    # Finish initial processing without depending on an external model.
    monkeypatch.setattr(
        "app.knowledge.worker.extract", lambda *a, **kw: ([("Page 1", "Native text")], {})
    )
    assert run_one(k.engine, k.store, None)
    with Session(k.engine) as db:
        did = str(db.scalar(select(KnowledgeDocument.id)))
    route = f"/api/v1/admin/knowledge/{did}/handwriting"
    assert k.client.post(route, headers=k.contributor).status_code == 403
    assert k.client.post(route, headers=k.admin).status_code == 200
    assert k.client.post(route, headers=k.admin).status_code == 409
    monkeypatch.setattr(
        "app.knowledge.handwriting.extract_handwriting",
        lambda *a: (
            [("Page 1 (handwriting draft)", "Force equals [unclear] newtons.")],
            {
                "extraction_mode": "handwriting",
                "handwriting_review_required": True,
                "page_count": 1,
                "handwriting_pages": [{"page": 1, "text": "Force equals [unclear] newtons."}],
            },
        ),
    )
    assert run_one(k.engine, k.store, None, k.settings)
    with Session(k.engine) as db:
        assert not db.scalar(select(KnowledgeDocument)).active
        assert search(db, "Force") == []
    assert k.client.get(route, headers=k.contributor).status_code == 403
    draft = k.client.get(route, headers=k.admin).json()
    assert draft["original_pdf_base64"].startswith("JVBER")
    payload = {"version": draft["version"], "pages": draft["pages"]}
    assert k.client.post(route + "/approve", headers=k.admin, json=payload).status_code == 422
    payload["pages"][0]["text"] = "Force equals six newtons."
    assert k.client.post(route + "/approve", headers=k.contributor, json=payload).status_code == 403
    assert k.client.post(route + "/approve", headers=k.admin, json=payload).status_code == 200
    assert k.client.post(route + "/approve", headers=k.admin, json=payload).status_code == 409
    with Session(k.engine) as db:
        assert db.scalar(select(KnowledgeDocument)).active
        assert "six newtons" in search(db, "Force")[0]["excerpt"]


def test_pdf_pages_are_rendered_individually_before_vision(monkeypatch):
    import shutil

    from app.knowledge.handwriting import extract_handwriting

    if not shutil.which("pdftoppm"):
        pytest.skip("PDF renderer unavailable")
    images = []

    def read_image(image, settings, **kwargs):
        assert image.startswith(b"\x89PNG")
        images.append(image)
        return f"Transcription of page {len(images)}"

    monkeypatch.setattr("app.knowledge.handwriting.transcribe", read_image)
    sections, metadata = extract_handwriting(scanned_pdf(), vision_settings())
    assert len(images) == 2
    assert sections[1] == ("Page 2 (handwriting draft)", "Transcription of page 2")
    assert metadata["handwriting_review_required"] is True
    assert metadata["handwriting_pages"][1]["page"] == 2


def test_oversized_handwriting_pdf_stops_before_provider(monkeypatch):
    from types import SimpleNamespace

    from app.knowledge.handwriting import extract_handwriting

    monkeypatch.setattr(
        "app.knowledge.handwriting.PdfReader",
        lambda _: SimpleNamespace(
            is_encrypted=False,
            pages=[None] * 11,
        ),
    )
    with patch("app.knowledge.handwriting.transcribe") as provider:
        with pytest.raises(ValueError, match="handwriting_page_limit"):
            extract_handwriting(b"pdf", vision_settings())
    provider.assert_not_called()


def test_failed_scan_automatically_uses_vision(knowledge, monkeypatch):
    k = knowledge
    settings = vision_settings()
    uploaded = k.client.post(
        "/api/v1/knowledge/submissions?title=Automatic%20scan&filename=scan.pdf",
        headers={**k.contributor, "Content-Type": "application/pdf"},
        content=scanned_pdf(),
    )
    assert approve(k, uploaded.json()["id"]).status_code == 200

    def unreadable(*args, **kwargs):
        raise ValueError("ocr_review_required")

    monkeypatch.setattr("app.knowledge.worker.extract", unreadable)
    with patch(
        "app.knowledge.handwriting.extract_handwriting",
        return_value=(
            [("Page 1 (handwriting draft)", "A readable transcription.")],
            {
                "page_count": 1,
                "handwriting_review_required": True,
                "handwriting_pages": [{"page": 1, "text": "A readable transcription."}],
            },
        ),
    ) as vision:
        assert run_one(k.engine, k.store, None, settings)
    assert vision.call_count == 1
    with Session(k.engine) as db:
        document = db.scalar(select(KnowledgeDocument))
        assert document.processing_status == "succeeded"
        assert not document.active
        assert document.metadata_json["handwriting_review_required"]


def test_scan_recovery_is_once_only_and_removal_is_respected(knowledge, monkeypatch):
    from app.knowledge.worker import retry_failed_scans
    from app.models.knowledge import ProcessingJob

    k = knowledge
    uploaded = k.client.post(
        "/api/v1/knowledge/submissions?title=Failed%20scan&filename=failed.pdf",
        headers={**k.contributor, "Content-Type": "application/pdf"},
        content=scanned_pdf(),
    )
    assert approve(k, uploaded.json()["id"]).status_code == 200

    def unreadable(*args, **kwargs):
        raise ValueError("ocr_review_required")

    monkeypatch.setattr("app.knowledge.worker.extract", unreadable)
    assert run_one(k.engine, k.store, None)
    retry_failed_scans(k.engine, vision_settings())
    with Session(k.engine) as db:
        document = db.scalar(select(KnowledgeDocument))
        did = str(document.id)
        assert document.metadata_json["automatic_vision_attempted"]
        job = db.scalar(select(ProcessingJob))
        assert job.state == "queued"
        job.state, job.error_code = "failed", "ocr_review_required"
        document.processing_status = "failed"
        db.commit()
    retry_failed_scans(k.engine, vision_settings())
    with Session(k.engine) as db:
        assert db.scalar(select(ProcessingJob)).state == "failed"
    assert k.client.delete(f"/api/v1/admin/knowledge/{did}", headers=k.admin).status_code == 200
    retry_failed_scans(k.engine, vision_settings())
    with Session(k.engine) as db:
        job = db.scalar(select(ProcessingJob))
        assert job.error_code == "removed_by_admin"
        assert job.state == "failed"
        assert not db.scalar(select(KnowledgeDocument)).active
