"""Conservative Markdown blocks shared by local document exporters."""

import re

WIDTH = 451.2756  # A4 with one-inch margins, in points.
INVALID_XML = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
TOKEN = re.compile(r"(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*|\[[^\]\n]+\]\(https?://[^\s)]+\))")


def spans(text):
    for part in TOKEN.split(INVALID_XML.sub("\ufffd", text)):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            yield part[2:-2], "bold"
        elif part.startswith("`") and part.endswith("`"):
            yield part[1:-1], "code"
        elif part.startswith("*") and part.endswith("*"):
            yield part[1:-1], "italic"
        elif part.startswith("[") and "](" in part:
            label, url = part[1:-1].split("](", 1)
            yield f"{label} ({url})", "text"
        else:
            yield part, "text"


def cells(line):
    return [s.strip().replace(r"\|", "|") for s in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def blocks(content):
    lines, i = content.splitlines(), 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.startswith("```"):
            while i < len(lines) and not lines[i].strip().startswith("```"):
                yield "code", lines[i], 0
                i += 1
            i += 1
        elif (
            "|" in line
            and i < len(lines)
            and all(re.fullmatch(r":?-{3,}:?", c) for c in cells(lines[i]))
        ):
            rows = [cells(line)]
            i += 1
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1
            yield "table", rows, 0
        elif match := re.match(r"^(#{1,6})\s+(.+)", line):
            yield "heading", match[2], min(len(match[1]) + 1, 6)
        elif match := re.match(r"^(\s*)([-+*]|\d+[.)])\s+(.+)", lines[i - 1]):
            yield (
                "list",
                (("•" if match[2] in "-+*" else match[2]), match[3]),
                min(len(match[1]) // 2, 4),
            )
        elif re.fullmatch(r"([-*_])\1{2,}", line):
            continue
        else:
            # Soft Markdown line breaks belong to a single paragraph.
            paragraph = [line]
            while (
                i < len(lines)
                and lines[i].strip()
                and not re.match(r"^\s*(?:#|```|[-+*]\s|\d+[.)]\s|\|)", lines[i])
                and not (
                    i + 1 < len(lines) and "|" in lines[i] and re.match(r"^[| :\-]+$", lines[i + 1])
                )
            ):
                paragraph.append(lines[i].strip())
                i += 1
            yield "body", " ".join(paragraph), 0


def column_widths(rows):
    count = max(map(len, rows))
    weights = [
        min(48, max(10, max((len(r[i]) if i < len(r) else 0) for r in rows))) for i in range(count)
    ]
    return [WIDTH * w / sum(weights) for w in weights]
