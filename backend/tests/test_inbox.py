from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.crypto import now
from app.models.knowledge import InboxCredential, KnowledgeDocument, KnowledgeSubmission
from tests.test_auth import api as api
from tests.test_auth import engine as engine
from tests.test_knowledge import knowledge as knowledge


def mint(k):
    response = k.client.post(
        "/api/v1/admin/inbox-credentials",
        headers=k.admin,
        json={"name": "Windows study inbox", "valid_days": 30},
    )
    assert response.status_code == 201
    return response.json()


def send(k, token, body=b"A valid academic lesson."):
    return k.client.post(
        "/api/v1/inbox/submissions?filename=inbox.txt&title=Inbox%20lesson",
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=body,
    )


def test_credential_can_only_create_pending_submissions(knowledge):
    k = knowledge
    credential = mint(k)
    token = credential["token"]
    assert credential["scope"] == "submissions:create"
    result = send(k, token)
    assert result.status_code == 201
    assert result.json()["status"] == "pending"
    assert (
        k.client.get(
            "/api/v1/admin/users", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )
    sid = result.json()["id"]
    assert (
        k.client.post(
            f"/api/v1/admin/submissions/{sid}/review",
            headers={"Authorization": "Bearer " + token},
            json={"decision": "approved"},
        ).status_code
        == 401
    )
    with Session(k.engine) as db:
        assert db.scalar(select(KnowledgeDocument)) is None
        stored = db.get(InboxCredential, UUID(credential["id"]))
        assert token not in stored.token_hash
        assert stored.last_used_at is not None
    listing = k.client.get("/api/v1/admin/inbox-credentials", headers=k.admin)
    assert token not in listing.text
    assert "token_hash" not in listing.text


def test_revoked_and_expired_tokens_rejected(knowledge):
    k = knowledge
    credential = mint(k)
    assert (
        k.client.delete(
            f"/api/v1/admin/inbox-credentials/{credential['id']}", headers=k.admin
        ).status_code
        == 200
    )
    assert send(k, credential["token"]).status_code == 401
    credential = mint(k)
    with Session(k.engine) as db:
        db.get(InboxCredential, UUID(credential["id"])).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert send(k, credential["token"]).status_code == 401


def test_contributors_cannot_mint_credentials(knowledge):
    k = knowledge
    assert (
        k.client.post(
            "/api/v1/admin/inbox-credentials", headers=k.contributor, json={"name": "forbidden"}
        ).status_code
        == 403
    )
    assert send(k, "emi_invalid").status_code == 401


def test_inbox_duplicate_still_requires_existing_review(knowledge):
    k = knowledge
    credential = mint(k)
    assert send(k, credential["token"]).status_code == 201
    assert send(k, credential["token"]).status_code == 409
    with Session(k.engine) as db:
        assert len(list(db.scalars(select(KnowledgeSubmission)))) == 1
        assert db.scalar(select(KnowledgeSubmission)).status == "pending"


def test_inbox_validates_types_and_size(knowledge):
    k = knowledge
    token = mint(k)["token"]
    response = k.client.post(
        "/api/v1/inbox/submissions?filename=bad.pdf&title=Bad",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/pdf"},
        content=b"not pdf",
    )
    assert response.status_code == 422
    assert send(k, token, b"x" * (3 * 1024 * 1024 + 1)).status_code == 413
