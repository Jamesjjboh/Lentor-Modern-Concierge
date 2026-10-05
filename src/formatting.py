"""Telegram-friendly text sanitizer.

Gemini emits standard Markdown (`**bold**`, `* bullet`), but Telegram's legacy
`Markdown` parse mode uses `*bold*` and rejects nested/unclosed asterisks. When Telegram
rejects the text, the bot falls back to plain text and the raw symbols become visible.
This module normalises the text so it parses cleanly.
"""

import re


def clean_markdown_for_telegram(text: str) -> str:
    """Normalise LLM Markdown into Telegram legacy-Markdown-safe text."""
    if not text:
        return text

    # 1. Line-start bullets ("* item" / "- item") -> "• item"
    lines = []
    for line in text.split("\n"):
        if re.match(r"^\s*[\*\-]\s+", line):
            line = re.sub(r"^(\s*)[\*\-]\s+", r"\1• ", line)
        lines.append(line)
    text = "\n".join(lines)

    # 2. "**bold**" -> "*bold*" (Telegram legacy bold)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"*\1*", text)

    # 3. Rogue line-start asterisk such as "*Note: ..." with no closing -> bullet
    text = re.sub(r"(?m)^\*(?=[A-Za-z0-9])", "• ", text)

    # 4. If asterisks are still unbalanced on any line, drop them on that line so the
    #    whole message does not fall back to plain text with visible symbols.
    fixed = []
    for line in text.split("\n"):
        if line.count("*") % 2 == 1:
            line = line.replace("*", "")
        fixed.append(line)
    text = "\n".join(fixed)

    # 5. Odd number of backticks on a line also breaks parsing -> remove them there
    fixed = []
    for line in text.split("\n"):
        if line.count("`") % 2 == 1:
            line = line.replace("`", "")
        fixed.append(line)
    return "\n".join(fixed)
