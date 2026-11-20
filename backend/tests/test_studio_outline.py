import pytest

from app.services.studio_outline import sections_from_outline


def test_long_numbered_chapter_outline_is_not_flattened():
    lines = []
    for number in range(1, 6):
        lines += [f"CHAPTER {number}", f"{number}.0 CHAPTER TITLE"]
        lines += [f"{number}.{i} SUBSECTION {i}" for i in range(1, 11)]
    from uuid import uuid4

    from app.api.documents import DocumentCreate

    validated = DocumentCreate(
        client_id=uuid4(),
        title="Project",
        brief="A complete engineering project report",
        outline=lines,
    )
    chapters = sections_from_outline(validated.outline)
    assert len(chapters) == 5
    assert all(len(c["subheadings"]) == 10 for c in chapters)
    assert "## 5.10 SUBSECTION 10" in chapters[-1]["content"]


def test_plain_outlines_stay_backwards_compatible():
    rows = sections_from_outline(["Introduction", "Methods", "Conclusion"])
    assert all(row["content"] == "" for row in rows)
    assert "subheadings" not in rows[0]
    with pytest.raises(ValueError):
        sections_from_outline(["Heading"] * 19)


def test_inline_chapter_titles_do_not_consume_first_subsection():
    chapters = sections_from_outline(
        [
            "CHAPTER ONE INTRODUCTION",
            "1.1 BACKGROUND",
            "CHAPTER TWO REVIEW",
            "2.1 PRIOR WORK",
            "CHAPTER THREE CONCLUSION",
            "3.1 RECOMMENDATION",
        ]
    )
    assert chapters[0]["subheadings"] == ["1.1 BACKGROUND"]
