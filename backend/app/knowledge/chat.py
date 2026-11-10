"""Find approved passages directly from Study Chat."""

import re

from sqlalchemy.orm import Session

from app.knowledge.learning import KnowledgeQueryTooBroad, search

COMMAND = re.compile(r"^(?:/knowledge\b|search (?:the )?approved knowledge\b(?: for\b)?)", re.I)
PROVIDER = "knowledge"


def topic(question: str) -> str | None:
    match = COMMAND.match(question)
    return question[match.end() :].strip(" :\t\n") if match else None


def plain_markdown(value: str) -> str:
    text = " ".join(value.split())
    return re.sub(r"([\\\x60*_\[\]<>~|])", r"\\\1", text)


def find(engine, query):
    if not 2 <= len(query) <= 2000:
        return "Enter a short topic after /knowledge, such as /knowledge Sutterby.", []

    with Session(engine) as db:
        try:
            matches = search(db, query)[:3]
        except KnowledgeQueryTooBroad:
            return "Too many approved passages matched. Add a more specific keyword.", []

    if not matches:
        return "No matching approved knowledge. Try a shorter topic or a document keyword.", []

    blocks = ["### Approved knowledge"]
    sources = []
    for index, match in enumerate(matches, 1):
        label = f"S{index}"
        title = plain_markdown(match["title"][:200])
        location = plain_markdown((match["location"] or "")[:150])
        blocks.append(
            f"**[{label}] {title}**"
            + (f" · {location}" if location else "")
            + f"\n\n> {plain_markdown(match['excerpt'][:1200])}"
        )
        if match["kind"] == "document":
            sources.append(
                {
                    "id": label,
                    "title": match["title"],
                    "location": match["location"],
                    "document_id": match["document_id"],
                    "chunk_id": match["id"],
                }
            )
    return "\n\n".join(blocks), sources
