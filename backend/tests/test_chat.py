import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.provider import AcademicError, UnconfiguredProvider
from app.auth.crypto import now
from app.core.config import Settings
from app.main import create_app
from app.models.chat import ChatRequest, Conversation, Message
from app.models.identity import AuditLog, AuthSession
from app.schemas.chat import TurnCreate
from app.services.chat import complete, prepare
from tests.fake_academic import FixtureProvider
from tests.test_auth import account, auth, login, register
from tests.test_auth import api as api
from tests.test_auth import engine as engine


@pytest.fixture
def chat(api):
    client, db_engine, settings = api
    settings.chat_user_limit = 1000
    provider = FixtureProvider()
    client.app.state.academic_provider = provider
    uid = UUID(register(client).json()["id"])
    logged_in = login(client)
    with Session(db_engine) as db:
        sid = db.scalar(select(AuthSession.id).where(AuthSession.user_id == uid))
    return SimpleNamespace(
        client=client,
        engine=db_engine,
        settings=settings,
        provider=provider,
        uid=uid,
        sid=sid,
        headers=auth(logged_in),
    )


def create(chat, cid=None):
    response = chat.client.post(
        "/api/v1/conversations", headers=chat.headers, json={"client_id": str(cid or uuid4())}
    )
    assert response.status_code == 201
    return response.json()["id"]


def send(chat, cid, content="Explain force", rid=None):
    return chat.client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=chat.headers,
        json={"request_id": str(rid or uuid4()), "content": content},
    )


def detail(chat, cid, query=""):
    return chat.client.get(f"/api/v1/conversations/{cid}{query}", headers=chat.headers)


def test_conversation_crud_and_idempotent_creation(chat):
    cid = uuid4()
    assert create(chat, cid) == create(chat, cid)
    listing = chat.client.get("/api/v1/conversations", headers=chat.headers).json()
    assert listing["total"] == 1
    assert detail(chat, cid).json()["messages"] == []
    assert (
        chat.client.patch(
            f"/api/v1/conversations/{cid}", headers=chat.headers, json={"title": "Mechanics"}
        ).json()["title"]
        == "Mechanics"
    )
    assert (
        chat.client.delete(f"/api/v1/conversations/{cid}", headers=chat.headers).status_code == 204
    )
    assert (
        chat.client.delete(f"/api/v1/conversations/{cid}", headers=chat.headers).status_code == 204
    )
    assert detail(chat, cid).status_code == 404
    assert chat.client.get("/api/v1/conversations", headers=chat.headers).json()["total"] == 0
    with Session(chat.engine) as db:
        assert db.get(Conversation, cid).deleted_at is not None


def test_success_followups_and_durable_duplicate_protection(chat):
    cid = create(chat)
    rid = uuid4()
    first = send(chat, cid, "Explain force", rid)
    assert first.status_code == 201
    assert [m["role"] for m in first.json()["messages"]] == ["user", "assistant"]
    replay = send(chat, cid, "Explain force", rid)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["messages"] == first.json()["messages"]
    assert chat.provider.calls == 1
    followup = send(chat, cid, "Why are the units newtons?")
    assert followup.status_code == 201
    assert [t.role for t in chat.provider.contexts[1]] == ["user", "assistant", "user"]
    assert chat.provider.contexts[1][0].content == "Explain force"
    saved = detail(chat, cid).json()
    assert [m["sequence"] for m in saved["messages"]] == [1, 2, 3, 4]
    assert saved["conversation"]["title"] == "Explain force"
    assert all(
        m["provider"] == "verification" for m in saved["messages"] if m["role"] == "assistant"
    )


def test_request_key_cannot_change_content_or_conversation(chat):
    cid, other, rid = create(chat), create(chat), uuid4()
    assert send(chat, cid, "First question", rid).status_code == 201
    assert send(chat, cid, "Changed question", rid).status_code == 409
    assert send(chat, other, "First question", rid).status_code == 409
    assert detail(chat, other).json()["messages"] == []
    assert chat.provider.calls == 1


@pytest.mark.parametrize("role", ["student", "contributor", "admin"])
def test_other_accounts_including_admin_cannot_read_or_mutate_private_chats(chat, role):
    cid = create(chat)
    send(chat, cid, "Private academic question")
    account(chat.engine, role=role, email="other@example.com")
    foreign = auth(login(chat.client, "other@example.com"))
    assert chat.client.get("/api/v1/conversations", headers=foreign).json()["items"] == []
    for method, suffix, body in [
        ("GET", "", None),
        ("PATCH", "", {"title": "Hijacked"}),
        ("DELETE", "", None),
        ("POST", "/messages", {"request_id": str(uuid4()), "content": "Leak context"}),
    ]:
        response = chat.client.request(
            method, f"/api/v1/conversations/{cid}{suffix}", headers=foreign, json=body
        )
        assert response.status_code == 404
        assert "Private academic question" not in response.text
    assert chat.provider.calls == 1


def test_default_provider_is_honest_and_saves_no_unsent_question(chat):
    cid = create(chat)
    chat.client.app.state.academic_provider = UnconfiguredProvider()
    caps = chat.client.get("/api/v1/chat/capabilities", headers=chat.headers).json()
    assert caps["available"] is False and caps["mode"] == "unconfigured"
    assert send(chat, cid).status_code == 503
    assert detail(chat, cid).json()["messages"] == []
    assert send(chat, uuid4()).status_code == 404


def test_cached_answer_can_be_recovered_even_when_provider_is_unavailable(chat):
    cid, rid = create(chat), uuid4()
    assert send(chat, cid, rid=rid).status_code == 201
    chat.client.app.state.academic_provider = UnconfiguredProvider()
    assert send(chat, cid, rid=rid).status_code == 200
    assert chat.provider.calls == 1


def test_custom_title_is_not_overwritten_and_history_is_paginated(chat):
    cid = create(chat)
    chat.client.patch(
        f"/api/v1/conversations/{cid}", headers=chat.headers, json={"title": "My mechanics notes"}
    )
    send(chat, cid)
    send(chat, cid, "Follow up")
    latest = detail(chat, cid, "?limit=2").json()
    assert latest["conversation"]["title"] == "My mechanics notes"
    assert latest["has_older"] is True
    older = detail(
        chat, cid, f"?limit=2&before_sequence={latest['messages'][0]['sequence']}"
    ).json()
    assert [m["sequence"] for m in older["messages"]] == [1, 2]
    assert older["has_older"] is False
    create(chat)
    page = chat.client.get("/api/v1/conversations?limit=1&offset=1", headers=chat.headers).json()
    assert page["total"] == 2 and len(page["items"]) == 1


class FailingProvider(FixtureProvider):
    def __init__(self, failure):
        super().__init__()
        self.failure = failure

    async def generate(self, context):
        self.calls += 1
        if isinstance(self.failure, Exception):
            raise self.failure
        return self.failure


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (AcademicError("unavailable"), 503, "unavailable"),
        (AcademicError("rate_limited"), 429, "rate_limited"),
        ("", 502, "empty_response"),
        (" " * 10, 502, "empty_response"),
        ("x" * 12001, 502, "provider_failure"),
        (RuntimeError("private-provider-secret"), 502, "provider_failure"),
    ],
)
def test_provider_failures_are_persisted_without_fake_answers_or_internal_details(
    chat, failure, status, code, caplog
):
    provider = FailingProvider(failure)
    chat.client.app.state.academic_provider = provider
    cid, rid = create(chat), uuid4()
    response = send(chat, cid, rid=rid)
    assert response.status_code == status
    assert "private-provider-secret" not in response.text
    saved = detail(chat, cid).json()
    assert len(saved["messages"]) == 1
    assert saved["requests"][0]["status"] == "failed" and saved["requests"][0]["error_code"] == code
    assert send(chat, cid, rid=rid).status_code == status
    assert provider.calls == 1
    assert "private-provider-secret" not in caplog.text


def test_real_provider_timeout_is_bounded(chat):
    class Slow(FixtureProvider):
        async def generate(self, context):
            await asyncio.sleep(2)
            return "too late"

    chat.settings.chat_timeout_seconds = 0.05
    chat.client.app.state.academic_provider = Slow()
    cid = create(chat)
    assert send(chat, cid).status_code == 504
    assert detail(chat, cid).json()["requests"][0]["error_code"] == "timeout"


def test_stale_pending_request_fails_closed_without_reinvoking_provider(chat):
    cid, rid = UUID(create(chat)), uuid4()
    data = TurnCreate(request_id=rid, content="Interrupted question")
    prepare(chat.engine, chat.uid, chat.sid, cid, data, chat.settings, True, "test")
    with Session(chat.engine) as db:
        db.get(ChatRequest, rid).deadline_at = now() - timedelta(seconds=1)
        db.commit()
    assert detail(chat, cid).json()["requests"][0]["error_code"] == "interrupted"
    assert send(chat, cid, "Interrupted question", rid).status_code == 504
    assert chat.provider.calls == 0
    assert send(chat, cid, "Next question").status_code == 201
    assert len(chat.provider.contexts[0]) == 1


def test_context_is_bounded_and_does_not_mix_conversations(chat):
    first, second = create(chat), create(chat)
    send(chat, first, "A private first topic")
    send(chat, second, "A separate topic")
    assert len(chat.provider.contexts[1]) == 1
    assert "private" not in chat.provider.contexts[1][0].content
    chat.settings.chat_context_characters = 4000
    for _ in range(4):
        send(chat, first, "x" * 900)
    assert sum(len(t.content) for t in chat.provider.contexts[-1]) <= 4000
    assert len(chat.provider.contexts[-1]) <= 21


def test_revoked_identity_cannot_receive_a_late_answer(chat):
    cid, rid = UUID(create(chat)), uuid4()
    prepare(
        chat.engine,
        chat.uid,
        chat.sid,
        cid,
        TurnCreate(request_id=rid, content="Question"),
        chat.settings,
        True,
        "test",
    )
    with Session(chat.engine) as db:
        db.get(AuthSession, chat.sid).revoked_at = now()
        db.commit()
    with pytest.raises(HTTPException) as error:
        complete(
            chat.engine, chat.uid, chat.sid, cid, rid, "Do not save", None, "verification", "test"
        )
    assert error.value.status_code == 401
    with Session(chat.engine) as db:
        assert db.get(ChatRequest, rid).error_code == "cancelled"
        assert (
            db.scalar(select(func.count()).select_from(Message).where(Message.role == "assistant"))
            == 0
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"content": "   "},
        {"content": "x" * 4001},
        {"content": "ok", "role": "system"},
        {"content": "ok", "owner_id": str(uuid4())},
    ],
)
def test_input_limits_and_role_injection_are_rejected(chat, payload):
    cid = create(chat)
    response = chat.client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=chat.headers,
        json={"request_id": str(uuid4()), **payload},
    )
    assert response.status_code == 422
    assert detail(chat, cid).json()["messages"] == []


def test_chat_write_quota_is_enforced(chat):
    cid = create(chat)
    chat.settings.chat_user_limit = 1
    assert send(chat, cid).status_code == 429


def test_unauthenticated_chat_endpoints_are_protected(api):
    client, _, _ = api
    assert client.get("/api/v1/chat/capabilities").status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401


def test_provider_injection_cannot_enable_a_fake_in_normal_runtime():
    config = Settings(
        database_url="postgresql+psycopg://test:test@localhost/unused", app_env="development"
    )
    with pytest.raises(ValueError, match="restricted"):
        create_app(config, provider=FixtureProvider())


class BlockingProvider(FixtureProvider):
    def __init__(self):
        super().__init__()
        self.entered, self.release = Event(), Event()

    async def generate(self, context):
        self.calls += 1
        self.entered.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        return "A scripted answer"


@pytest.mark.integration
def test_concurrent_duplicates_have_one_provider_call_and_different_requests_conflict(chat):
    if chat.engine.dialect.name != "postgresql":
        pytest.skip("Row locks require PostgreSQL")
    cid, rid = create(chat), uuid4()
    provider = BlockingProvider()
    chat.client.app.state.academic_provider = provider
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(send, chat, cid, "Concurrent question", rid)
        try:
            assert provider.entered.wait(5)
            assert send(chat, cid, "Concurrent question", rid).status_code == 202
            assert send(chat, cid, "Another question").status_code == 409
        finally:
            provider.release.set()
        assert future.result(timeout=10).status_code == 201
    assert provider.calls == 1
    assert len(detail(chat, cid).json()["messages"]) == 2


@pytest.mark.integration
def test_removing_a_conversation_discards_an_inflight_answer(chat):
    if chat.engine.dialect.name != "postgresql":
        pytest.skip("Concurrent transaction check requires PostgreSQL")
    cid = create(chat)
    provider = BlockingProvider()
    chat.client.app.state.academic_provider = provider
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(send, chat, cid)
        try:
            assert provider.entered.wait(5)
            assert (
                chat.client.delete(f"/api/v1/conversations/{cid}", headers=chat.headers).status_code
                == 204
            )
        finally:
            provider.release.set()
        assert future.result(timeout=10).status_code == 404
    with Session(chat.engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Message).where(Message.role == "assistant"))
            == 0
        )
        assert db.scalar(select(ChatRequest.error_code)) == "cancelled"
        assert "chat.removed" in list(db.scalars(select(AuditLog.action)))
