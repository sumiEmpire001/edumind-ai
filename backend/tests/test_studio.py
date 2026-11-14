import base64
import io
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.orm import Session

from app.ai.provider import AcademicError
from app.ai.research import ResearchResult, WebLink
from app.auth.crypto import now
from app.models.studio import StudioDocument
from app.services.pdf_export import render
from tests.fake_academic import FixtureProvider
from tests.test_auth import api as api
from tests.test_auth import auth, login, register
from tests.test_auth import engine as engine
from tests.test_knowledge import MemoryStore


@pytest.fixture
def studio(api):
    client, engine, settings = api
    register(client)
    headers = auth(login(client))
    provider = FixtureProvider()
    client.app.state.academic_provider = provider
    return client, engine, headers, provider


def create(studio):
    client, _, headers, _ = studio
    result = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "client_id": str(uuid4()),
            "title": "An introduction to mechanics",
            "brief": "Explain Newtonian mechanics for a first-year student with worked examples.",
            "target_pages": 35,
            "outline": ["Introduction", "Forces and motion", "Worked examples"],
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def generation(client, headers, doc, index=0, rid=None, mode="replace"):
    return client.post(
        f"/api/v1/documents/{doc['id']}/sections/{index}/generate",
        headers=headers,
        json={"request_id": rid or str(uuid4()), "revision": doc["revision"], "mode": mode},
    )


def test_draft_revision_owner_isolation_and_manual_pdf(studio):
    client, engine, headers, _ = studio
    doc = create(studio)
    assert client.get("/api/v1/conversations", headers=headers).json()["total"] == 0
    with Session(engine) as db:
        hidden = db.get(StudioDocument, UUID(doc["id"])).conversation_id
    assert client.get(f"/api/v1/conversations/{hidden}", headers=headers).status_code == 404
    assert client.delete(f"/api/v1/conversations/{hidden}", headers=headers).status_code == 404
    path = f"/api/v1/documents/{doc['id']}"
    assert client.get("/api/v1/documents", headers=headers).json()[0]["id"] == doc["id"]
    assert client.post(path + "/export-word", headers=headers).status_code == 422
    edited = client.patch(
        path + "/sections/0",
        headers=headers,
        json={
            "revision": 1,
            "title": "Introduction",
            "content": "# Café and force\nForce is measured in newtons. α = 2.",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["revision"] == 2
    assert (
        client.patch(
            path + "/sections/0",
            headers=headers,
            json={"revision": 1, "title": "Stale edit", "content": "Overwrite"},
        ).status_code
        == 409
    )
    exported = client.post(path + "/export", headers=headers)
    assert exported.status_code == 200, exported.text
    payload = exported.json()
    pdf = PdfReader(io.BytesIO(base64.b64decode(payload["base64"])))
    extracted = "\n".join(page.extract_text() for page in pdf.pages)
    assert "Café" in extracted and "α" in extracted and "Contents" in extracted
    assert len(pdf.pages) == payload["page_count"]
    word = client.post(path + "/export-word", headers=headers)
    assert word.status_code == 200, word.text
    payload = word.json()
    assert payload["media_type"].endswith("wordprocessingml.document")
    with ZipFile(io.BytesIO(base64.b64decode(payload["base64"]))) as package:
        assert package.testzip() is None
        xml = ElementTree.fromstring(package.read("word/document.xml"))
        text = [node.text for node in xml.findall(".//{*}t")]
    assert "Café and force" in text
    assert "Force is measured in newtons. α = 2." in text
    register(client, email="other@example.com")
    other = auth(login(client, email="other@example.com"))
    for method, suffix in [
        ("get", ""),
        ("post", "/export"),
        ("post", "/export-word"),
        ("delete", ""),
    ]:
        assert getattr(client, method)(path + suffix, headers=other).status_code == 404


def test_generation_replay_append_and_changed_revision(studio):
    client, _, headers, provider = studio
    doc = create(studio)
    rid = str(uuid4())
    result = generation(client, headers, doc, rid=rid)
    assert result.status_code == 200, result.text
    current = result.json()
    assert current["revision"] == 2 and current["pending"] is None
    first = current["sections"][0]["content"]
    assert "Do not fabricate citations" in provider.contexts[0][-1].content
    assert generation(client, headers, doc, rid=rid).json()["revision"] == 2
    assert provider.calls == 1
    assert generation(client, headers, doc, index=1).status_code == 409
    result = generation(client, headers, current, mode="append")
    assert result.status_code == 200
    assert result.json()["sections"][0]["content"].startswith(first + "\n\n")
    assert "Continue and expand" in provider.contexts[-1][-1].content
    assert provider.calls == 2


def test_generation_failure_keeps_saved_text_and_can_retry(studio):
    client, _, headers, _ = studio
    doc = create(studio)

    class Broken(FixtureProvider):
        async def generate(self, context):
            raise AcademicError("timeout")

    client.app.state.academic_provider = Broken()
    assert generation(client, headers, doc).status_code == 503
    row = client.get(f"/api/v1/documents/{doc['id']}", headers=headers).json()
    assert row["pending"] is None and row["sections"][0]["content"] == ""
    client.app.state.academic_provider = FixtureProvider()
    assert generation(client, headers, row).status_code == 200


def test_pending_reservation_blocks_edits_and_another_generation(studio):
    from sqlalchemy import select

    from app.api.documents import Generate, reserve
    from app.models.identity import AuthSession

    client, engine, headers, _ = studio
    doc = create(studio)
    with Session(engine) as db:
        row = db.get(StudioDocument, UUID(doc["id"]))
        owner = row.owner_id
        sid = db.scalar(select(AuthSession.id).where(AuthSession.user_id == owner))
    data = Generate(revision=1, request_id=uuid4())
    reserve(engine, owner, sid, UUID(doc["id"]), 0, data, "test")
    path = f"/api/v1/documents/{doc['id']}"
    assert (
        client.patch(
            path + "/sections/0",
            headers=headers,
            json={"revision": 1, "title": "Introduction", "content": "Lost edit"},
        ).status_code
        == 409
    )
    assert generation(client, headers, doc, index=1).status_code == 409
    # A retry can resume the original reservation safely.
    assert generation(client, headers, doc, rid=str(data.request_id)).status_code == 200


def test_expired_reservation_recovers_without_new_provider_call_for_replay(studio):
    client, engine, headers, provider = studio
    doc = create(studio)
    with Session(engine) as db:
        row = db.get(StudioDocument, UUID(doc["id"]))
        row.pending = {
            "request_id": str(uuid4()),
            "index": 0,
            "revision": 1,
            "mode": "replace",
            "prompt": "fixture",
            "expires_at": (now() - timedelta(seconds=1)).isoformat(),
        }
        db.commit()
    assert generation(client, headers, doc).status_code == 200
    assert provider.calls == 1


def test_completed_generation_is_recoverable_after_reservation_expiry(studio):
    from unittest.mock import patch

    client, engine, headers, provider = studio
    doc = create(studio)
    rid = str(uuid4())
    with patch("app.api.documents.finish", side_effect=RuntimeError("fixture interruption")):
        assert generation(client, headers, doc, rid=rid).status_code == 500
    with Session(engine) as db:
        row = db.get(StudioDocument, UUID(doc["id"]))
        row.pending = {**row.pending, "expires_at": (now() - timedelta(seconds=1)).isoformat()}
        db.commit()
    result = generation(client, headers, doc, rid=rid)
    assert result.status_code == 200, result.text
    assert result.json()["sections"][0]["content"]
    assert provider.calls == 1


def conversation(studio):
    client, _, headers, _ = studio
    return client.post(
        "/api/v1/conversations", headers=headers, json={"client_id": str(uuid4())}
    ).json()["id"]


def test_create_studio_draft_from_owned_study_chat_answer(studio):
    client, _, headers, provider = studio
    cid = conversation(studio)
    turn = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"request_id": str(uuid4()), "content": "Explain Newton's laws"},
    )
    assert turn.status_code == 201
    question, answer = turn.json()["messages"]
    payload = {
        "client_id": str(uuid4()),
        "title": "Newton's laws",
        "brief": "Develop the answer into a study report.",
        "target_pages": 3,
        "outline": ["Study Chat answer", "Analysis", "Conclusions"],
        "source_answer": {"conversation_id": cid, "message_id": answer["id"]},
    }
    draft = client.post("/api/v1/documents", headers=headers, json=payload)
    assert draft.status_code == 201, draft.text
    assert draft.json()["sections"][0]["content"] == answer["content"]
    assert draft.json()["sections"][1]["content"] == ""
    replay = client.post("/api/v1/documents", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json()["id"] == draft.json()["id"]
    assert replay.json()["sections"] == draft.json()["sections"]
    assert provider.calls == 1

    invalid = {**payload, "client_id": str(uuid4())}
    invalid["source_answer"] = {"conversation_id": cid, "message_id": question["id"]}
    assert client.post("/api/v1/documents", headers=headers, json=invalid).status_code == 404
    register(client, email="other@example.com")
    other = auth(login(client, email="other@example.com"))
    assert (
        client.post(
            "/api/v1/documents", headers=other, json={**payload, "client_id": str(uuid4())}
        ).status_code
        == 404
    )


def test_text_attachment_context_and_pdf_export(studio):
    client, _, headers, provider = studio
    client.app.state.object_store = MemoryStore()
    cid = conversation(studio)
    response = client.post(
        f"/api/v1/conversations/{cid}/attachments?filename=notes.txt",
        headers={**headers, "Content-Type": "text/plain"},
        content=b"Mass is 2 kg and acceleration is 3 m/s2.",
    )
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    rid = str(uuid4())
    body = {"request_id": rid, "content": "Find the force from the note", "attachment_ids": [aid]}
    response = client.post(f"/api/v1/conversations/{cid}/messages", headers=headers, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["messages"][0]["attachments"][0]["filename"] == "notes.txt"
    assert "Mass is 2 kg" in provider.contexts[-1][-1].content
    assert "untrusted reference data" in provider.contexts[-1][-1].content
    assert (
        client.post(f"/api/v1/conversations/{cid}/messages", headers=headers, json=body).status_code
        == 200
    )
    assert provider.calls == 1
    other_rid = {**body, "request_id": str(uuid4())}
    assert (
        client.post(
            f"/api/v1/conversations/{cid}/messages", headers=headers, json=other_rid
        ).status_code
        == 409
    )
    exported = client.post(f"/api/v1/conversations/{cid}/export", headers=headers, json={})
    assert exported.status_code == 200
    assert base64.b64decode(exported.json()["base64"]).startswith(b"%PDF-")


@pytest.mark.parametrize("mode", ["auto", "off", "on"])
def test_web_research_with_attachments_requires_opt_in_and_sends_only_question(studio, mode):
    client, _, headers, provider = studio
    client.app.state.object_store = MemoryStore()
    search = AsyncMock(
        return_value=ResearchResult(
            answer="",
            sources=[
                WebLink(
                    title="Public study guide",
                    url="https://example.org/study-guide",
                    publisher="Source",
                    description="Public evidence about acceleration.",
                )
            ],
            suggestions=[],
        )
    )
    client.app.state.research = search
    cid = conversation(studio)
    upload = client.post(
        f"/api/v1/conversations/{cid}/attachments?filename=private-notes.txt",
        headers={**headers, "Content-Type": "text/plain"},
        content=b"Private lecture excerpt: an example with a mass of 2 kg.",
    )
    assert upload.status_code == 201
    question = "What do the latest studies say about teaching acceleration?"
    turn = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "content": question,
            "attachment_ids": [upload.json()["id"]],
            "research_mode": mode,
        },
    )
    assert turn.status_code == 201, turn.text
    context = provider.contexts[-1][-1]
    assert "Private lecture excerpt" in context.content
    if mode == "on":
        search.assert_awaited_once_with(question)
        assert "Public evidence about acceleration" in context.web_context
        assert "https://example.org/study-guide" in turn.json()["messages"][-1]["content"]
    else:
        search.assert_not_awaited()
        assert not context.web_context


def test_pdf_attachment_supplies_original_page_numbers_to_study_chat(studio):
    client, _, headers, provider = studio
    client.app.state.object_store = MemoryStore()
    buffer = io.BytesIO()
    pdf = Canvas(buffer)
    pdf.showPage()
    pdf.drawString(40, 700, "Acceleration is the rate of change of velocity.")
    pdf.save()

    cid = conversation(studio)
    upload = client.post(
        f"/api/v1/conversations/{cid}/attachments?filename=lecture.pdf",
        headers={**headers, "Content-Type": "application/pdf"},
        content=buffer.getvalue(),
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["mime"] == "application/pdf"
    response = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "content": "Explain the definition from the lecture.",
            "attachment_ids": [attachment["id"]],
        },
    )
    assert response.status_code == 201, response.text
    context = provider.contexts[-1][-1]
    assert '"file": "lecture.pdf"' in context.content
    assert '"page": 2' in context.content
    assert "Acceleration is the rate of change of velocity." in context.content
    assert not context.media
    assert attachment["id"] in context.content

    path = f"/api/v1/conversations/{cid}/attachments/{attachment['id']}/pages"
    assert client.get(f"{path}/2", headers=headers).json() == {
        "filename": "lecture.pdf",
        "page": 2,
        "text": "Acceleration is the rate of change of velocity.",
    }
    assert client.get(f"{path}/1", headers=headers).status_code == 404
    assert client.get(f"{path}/2").status_code == 401
    wrong_cid = conversation(studio)
    assert client.get(f"{path.replace(cid, wrong_cid)}/2", headers=headers).status_code == 404


@pytest.mark.parametrize("page_count, encrypted", [(1, False), (21, False), (1, True)])
def test_pdf_attachment_rejects_scans_oversized_page_counts_and_encryption(page_count, encrypted):
    from fastapi import HTTPException

    from app.services.attachments import validate

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("fixture-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(HTTPException) as error:
        validate("lecture.pdf", buffer.getvalue(), "application/pdf")
    assert error.value.status_code == 422


def test_image_attachment_reaches_provider_and_followups(studio):
    client, _, headers, provider = studio
    client.app.state.object_store = MemoryStore()
    cid = conversation(studio)
    source = io.BytesIO()
    Image.new("RGB", (30, 30), "green").save(source, format="PNG")
    response = client.post(
        f"/api/v1/conversations/{cid}/attachments?filename=exercise.png",
        headers={**headers, "Content-Type": "image/png"},
        content=source.getvalue(),
    )
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    preview = client.get(f"/api/v1/conversations/{cid}/attachments/{aid}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["mime"] == "image/jpeg"
    assert base64.b64decode(preview.json()["base64"]).startswith(b"\xff\xd8")
    assert (
        client.get(f"/api/v1/conversations/{cid}/attachments", headers=headers).json()[0]["id"]
        == aid
    )
    for i in range(2):
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=headers,
            json={
                "request_id": str(uuid4()),
                "content": "Explain this image" if i == 0 else "Explain further",
                "attachment_ids": [response.json()["id"]] if i == 0 else [],
            },
        )
        assert response.status_code == 201, response.text
    assert provider.contexts[0][-1].media[0].mime == "image/jpeg"
    assert provider.contexts[1][0].media[0].data.startswith(b"\xff\xd8")
    assert "data=" not in repr(provider.contexts[0][-1].media[0])
    assert client.get(f"/api/v1/conversations/{cid}/attachments", headers=headers).json() == []


def test_attachment_pending_limit_and_pixel_guard(studio):
    client, _, headers, _ = studio
    client.app.state.object_store = MemoryStore()
    cid = conversation(studio)
    path = f"/api/v1/conversations/{cid}/attachments"
    for name in ("one.txt", "two.txt"):
        assert (
            client.post(
                path + "?filename=" + name,
                headers={**headers, "Content-Type": "text/plain"},
                content=b"note",
            ).status_code
            == 201
        )
    assert (
        client.post(
            path + "?filename=three.txt",
            headers={**headers, "Content-Type": "text/plain"},
            content=b"note",
        ).status_code
        == 409
    )
    large = io.BytesIO()
    Image.new("RGB", (2100, 2100)).save(large, format="PNG")
    assert (
        client.post(
            path + "?filename=large.png",
            headers={**headers, "Content-Type": "image/png"},
            content=large.getvalue(),
        ).status_code
        == 422
    )


def test_image_resource_limit_returns_retryable_failure(studio):
    from unittest.mock import patch

    from app.services.attachments import image_slots

    client, _, headers, _ = studio
    client.app.state.object_store = MemoryStore()
    cid = conversation(studio)
    source = io.BytesIO()
    Image.new("RGB", (16, 16), "green").save(source, format="PNG")
    path = f"/api/v1/conversations/{cid}/attachments?filename=fixture.png"
    with patch.object(image_slots, "acquire", return_value=False):
        assert (
            client.post(
                path, headers={**headers, "Content-Type": "image/png"}, content=source.getvalue()
            ).status_code
            == 503
        )
    assert (
        client.post(
            path, headers={**headers, "Content-Type": "image/png"}, content=source.getvalue()
        ).status_code
        == 201
    )


@pytest.mark.integration
def test_document_removal_during_generation_does_not_save_answer(studio):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    client, engine, headers, _ = studio
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    doc = create(studio)
    entered, release = Event(), Event()

    class Holding(FixtureProvider):
        async def generate(self, context):
            entered.set()
            await asyncio.to_thread(release.wait, 10)
            return "This answer must never enter a removed draft."

    client.app.state.academic_provider = Holding()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(generation, client, headers, doc)
        try:
            assert entered.wait(10)
            assert (
                client.delete(f"/api/v1/documents/{doc['id']}", headers=headers).status_code == 204
            )
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 404
    with Session(engine) as db:
        assert db.get(StudioDocument, UUID(doc["id"])).sections[0]["content"] == ""


@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("unsafe.svg", "image/svg+xml", b"<svg/>"),
        ("fake.pdf", "application/pdf", b"not a PDF"),
        ("fake.png", "image/png", b"not an image"),
        ("fake.jpg", "image/png", b"not an image"),
        ("note.txt", "text/plain", b"\x00bad text"),
        ("note.txt", "text/plain", b"x" * 8001),
    ],
)
def test_invalid_attachments_are_rejected(studio, name, mime, data):
    client, _, headers, _ = studio
    client.app.state.object_store = MemoryStore()
    cid = conversation(studio)
    assert (
        client.post(
            f"/api/v1/conversations/{cid}/attachments?filename={name}",
            headers={**headers, "Content-Type": mime},
            content=data,
        ).status_code
        == 422
    )


def test_attachment_storage_disabled_and_cross_conversation_access(studio):
    client, _, headers, _ = studio
    cid = conversation(studio)
    assert not client.get("/api/v1/chat/capabilities", headers=headers).json()[
        "attachments_available"
    ]
    path = f"/api/v1/conversations/{cid}/attachments?filename=notes.txt"
    assert (
        client.post(
            path, headers={**headers, "Content-Type": "text/plain"}, content=b"Private note"
        ).status_code
        == 503
    )
    client.app.state.object_store = MemoryStore()
    aid = client.post(
        path, headers={**headers, "Content-Type": "text/plain"}, content=b"Private note"
    ).json()["id"]
    other_cid = conversation(studio)
    response = client.post(
        f"/api/v1/conversations/{other_cid}/messages",
        headers=headers,
        json={"request_id": str(uuid4()), "content": "Read this", "attachment_ids": [aid]},
    )
    assert response.status_code == 404
    register(client, email="outsider@example.com")
    other = auth(login(client, email="outsider@example.com"))
    assert (
        client.delete(f"/api/v1/conversations/{cid}/attachments/{aid}", headers=other).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/conversations/{cid}/attachments/{aid}", headers=headers).status_code
        == 204
    )


def test_pdf_rejects_empty_and_preserves_untrusted_markup_as_text():
    with pytest.raises(ValueError, match="Add or generate"):
        render("Empty", "Fixture", [("Empty", "")])
    result = render(
        "Markup fixture",
        "Test author",
        [("Notes", '<img src="http://127.0.0.1/private">\n**Bold** and `code`')],
    )
    text = "\n".join(
        p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(result["base64"]))).pages
    )
    assert '<img src="http://127.0.0.1/private">' in text


def test_long_pdf_layout_reports_actual_pages(tmp_path):
    paragraph = (
        "This synthetic layout fixture checks readable academic paragraphs and page flow. "
        "Each paragraph discusses an example with clear terms, assumptions, methods and results. "
        "The content is deliberately generated for renderer testing and is not academic evidence. "
    )
    sections = [
        (
            f"Section {i + 1}: Layout verification",
            "\n\n".join(f"Example {j + 1}. {paragraph}" for j in range(25)),
        )
        for i in range(12)
    ]
    result = render("Long document layout fixture", "EduMind verification", sections)
    data = base64.b64decode(result["base64"])
    (tmp_path / "long-layout.pdf").write_bytes(data)
    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == result["page_count"]
    assert 30 <= len(pages) <= 45
    assert all(page.extract_text().strip() for page in pages)


def test_long_chat_answer_import_is_complete_and_editable(studio):
    from unittest.mock import AsyncMock

    client, _, headers, provider = studio
    content = "## Report\n\n" + "A substantive paragraph.\n\n" * 1800 + "Final conclusion."
    provider.generate = AsyncMock(return_value=content)
    cid = conversation(studio)
    reply = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={"request_id": str(uuid4()), "content": "Write a detailed report"},
    )
    assert reply.status_code == 201, reply.text
    answer = reply.json()["messages"][-1]
    draft = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "client_id": str(uuid4()),
            "title": "Long report",
            "brief": "Develop this report.",
            "target_pages": 30,
            "outline": ["Imported answer", "Analysis", "Conclusions"],
            "source_answer": {"conversation_id": cid, "message_id": answer["id"]},
        },
    )
    assert draft.status_code == 201, draft.text
    sections = draft.json()["sections"]
    assert "".join(s["content"] for s in sections) == content
    assert all(len(s["content"]) <= 28000 for s in sections)
