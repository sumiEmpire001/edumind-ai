"""Convert chapter outlines to editable chapters without flattening subsections."""

import re

CHAPTER = re.compile(r"^CHAPTER\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|\d+)\b", re.I)


def sections_from_outline(lines):
    if not any(CHAPTER.match(line) for line in lines):
        if len(lines) > 18:
            raise ValueError(
                "Use at most 18 sections, or group subsections under CHAPTER headings."
            )
        return [{"title": line, "content": "", "last_request_id": None} for line in lines]
    result = []
    for line in lines:
        if CHAPTER.match(line):
            result.append(
                {"title": line, "subheadings": [], "content": "", "last_request_id": None}
            )
        elif not result:
            raise ValueError("Begin a chapter outline with CHAPTER ONE.")
        else:
            current = result[-1]
            # Chapter names (INTRODUCTION / 2.0 LITERATURE REVIEW) sit above subsections.
            if re.fullmatch(r"CHAPTER\s+(?:[A-Z]+|\d+)", current["title"], re.I) and (
                not re.match(r"^\d+\.", line) or re.match(r"^\d+\.0\s", line)
            ):
                title = current["title"] + " — " + line
                if len(title) > 100:
                    raise ValueError("Combined chapter titles must be at most 100 characters.")
                current["title"] = title
            else:
                current["subheadings"].append(line)
    if not 3 <= len(result) <= 18:
        raise ValueError("Use 3–18 chapters with numbered subsection headings underneath.")
    for chapter in result:
        chapter["content"] = "\n\n".join("## " + h for h in chapter["subheadings"])
    return result
