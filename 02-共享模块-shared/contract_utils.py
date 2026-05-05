from __future__ import annotations

import sys
from pathlib import Path


def read_text(path: str | None) -> str:
    return Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()


def nonempty_lines(markdown: str) -> list[str]:
    return [line.strip() for line in markdown.strip().splitlines() if line.strip()]


def section(lines: list[str], heading: str, headings: list[str]) -> list[str]:
    index = lines.index(heading)
    next_index = next((idx for idx in range(index + 1, len(lines)) if lines[idx] in headings), len(lines))
    return [line for line in lines[index + 1 : next_index] if line]


def validate_headings(lines: list[str], headings: list[str], order_error: str) -> list[str]:
    errors: list[str] = []
    positions: list[int] = []
    for heading in headings:
        matches = [idx for idx, line in enumerate(lines) if line == heading]
        if len(matches) != 1:
            errors.append(f"heading must appear exactly once: {heading}")
        else:
            positions.append(matches[0])
    if len(positions) == len(headings) and positions != sorted(positions):
        errors.append(order_error)
    return errors


def validate_banned(markdown: str, banned: tuple[str, ...], message: str = "banned wording") -> list[str]:
    return [f"{message}: {term}" for term in banned if term in markdown]


def validate_plain_output_format(markdown: str, lines: list[str]) -> list[str]:
    errors: list[str] = []
    if any(line.startswith("#") for line in lines):
        errors.append("markdown heading syntax is not allowed; display script output headings verbatim")
    if any(line in {"---", "***", "___"} for line in lines):
        errors.append("horizontal rules are not allowed")
    if any(line.startswith(">") for line in lines):
        errors.append("blockquotes or extra disclaimer blocks are not allowed")
    if "**" in markdown:
        errors.append("bold markdown markers are not allowed; keep generated plain text")
    if any(line.startswith("|") and line.endswith("|") for line in lines):
        errors.append("markdown tables are not allowed; keep fixed plain-line sections")
    if any(line.startswith(("- ", "* ")) for line in lines):
        errors.append("markdown bullet lists are not allowed; keep generated plain-line sections")
    if "不构成投资建议" in markdown:
        errors.append("extra investment disclaimer is not allowed; return only generated output")
    return errors
