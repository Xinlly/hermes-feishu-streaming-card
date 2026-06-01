from __future__ import annotations

import re

THINK_TAG_RE = re.compile(r"</?think>|</?thinking>", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[。！？!?\.]$")
THINK_TAGS = ("<think>", "</think>", "<thinking>", "</thinking>")
FENCE_RE = re.compile(r"^\s*```")
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.MULTILINE,
)
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def normalize_stream_text(text: str) -> str:
    """移除模型 thinking 标签，保留用户可读内容。"""
    return THINK_TAG_RE.sub("", text or "")


class StreamingTextNormalizer:
    """Filter thinking tags that may be split across streaming chunks."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, delta: str) -> str:
        text = self._pending + (delta or "")
        safe_text, self._pending = self._split_safe_text(text)
        return normalize_stream_text(safe_text)

    @staticmethod
    def _split_safe_text(text: str) -> tuple[str, str]:
        lower_text = text.lower()
        pending_len = 0

        for tag in THINK_TAGS:
            for prefix_len in range(1, len(tag)):
                if lower_text.endswith(tag[:prefix_len]):
                    pending_len = max(pending_len, prefix_len)

        if not pending_len:
            return text, ""
        return text[:-pending_len], text[-pending_len:]


def should_flush_text(
    buffer: str,
    *,
    elapsed_ms: int,
    max_wait_ms: int,
    max_chars: int,
    force: bool = False,
) -> bool:
    if force:
        return True
    if not buffer:
        return False
    if len(buffer) >= max_chars:
        return True
    if elapsed_ms >= max_wait_ms:
        return True
    if buffer.endswith(("\n", "\r\n")):
        return True
    return bool(SENTENCE_END_RE.search(buffer.rstrip()))


def count_markdown_tables(text: str) -> int:
    """统计 Markdown 文本中的表格数量（以 | --- | 分隔行为标志）。"""
    return len(re.findall(r'^\|[-: ]+\|', text, re.MULTILINE))


MAX_CARD_TABLES = 5


def split_markdown_blocks(text: str, max_block_size: int) -> list[str]:
    """Split markdown without cutting tables or fenced code blocks in half."""
    if not text:
        return [""]
    if max_block_size <= 0 or len(text) <= max_block_size:
        return [text]

    blocks = _markdown_structure_blocks(text)
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > max_block_size and _is_fenced_code_block(block):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_fenced_code_block(block, max_block_size))
            continue

        if len(block) > max_block_size and _is_table_block(block):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_table_block(block, max_block_size))
            continue

        if len(block) > max_block_size and not _is_structured_markdown_block(block):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_plain_block(block, max_block_size))
            continue

        if current and len(current) + len(block) > max_block_size:
            chunks.append(current)
            current = block
        else:
            current += block

    if current:
        chunks.append(current)
    return chunks or [""]


def _markdown_structure_blocks(text: str) -> list[str]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return [text]

    blocks: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append("".join(paragraph))
            paragraph = []

    while index < len(lines):
        line = lines[index]
        if FENCE_RE.match(line):
            flush_paragraph()
            code = [line]
            index += 1
            while index < len(lines):
                code.append(lines[index])
                if FENCE_RE.match(lines[index]):
                    index += 1
                    break
                index += 1
            blocks.append("".join(code))
            continue

        if (
            TABLE_ROW_RE.match(line)
            and index + 1 < len(lines)
            and TABLE_SEPARATOR_RE.match(lines[index + 1])
        ):
            flush_paragraph()
            table = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and TABLE_ROW_RE.match(lines[index]):
                table.append(lines[index])
                index += 1
            blocks.append("".join(table))
            continue

        paragraph.append(line)
        index += 1
        if line.strip() == "":
            flush_paragraph()

    flush_paragraph()
    return blocks


def _is_structured_markdown_block(block: str) -> bool:
    return "```" in block or TABLE_SEPARATOR_RE.search(block) is not None


def _is_fenced_code_block(block: str) -> bool:
    lines = block.splitlines(keepends=True)
    return bool(lines) and FENCE_RE.match(lines[0]) is not None


def _is_table_block(block: str) -> bool:
    lines = block.splitlines(keepends=True)
    return (
        len(lines) >= 2
        and TABLE_ROW_RE.match(lines[0]) is not None
        and TABLE_SEPARATOR_RE.match(lines[1]) is not None
    )


def _split_fenced_code_block(block: str, max_block_size: int) -> list[str]:
    lines = block.splitlines(keepends=True)
    if len(lines) < 2:
        return _split_plain_block(block, max_block_size)
    opening = lines[0]
    closing = lines[-1] if FENCE_RE.match(lines[-1]) else "```\n"
    body_lines = lines[1:-1] if closing == lines[-1] else lines[1:]
    overhead = len(opening) + len(closing)
    if overhead >= max_block_size:
        return _split_plain_block(block, max_block_size)
    body_limit = max_block_size - overhead
    chunks: list[str] = []
    current = ""
    for line in body_lines:
        if current and len(current) + len(line) > body_limit:
            chunks.append(_wrap_code_chunk(opening, current, closing))
            current = ""
        if len(line) > body_limit:
            for piece in _split_plain_block(line, body_limit):
                chunks.append(_wrap_code_chunk(opening, piece, closing))
            continue
        current += line
    if current or not chunks:
        chunks.append(_wrap_code_chunk(opening, current, closing))
    return chunks


def _wrap_code_chunk(opening: str, body: str, closing: str) -> str:
    if body and not body.endswith("\n"):
        body += "\n"
    return opening + body + closing


def _split_table_block(block: str, max_block_size: int) -> list[str]:
    lines = block.splitlines(keepends=True)
    if len(lines) < 3:
        return _split_plain_block(block, max_block_size)
    header = "".join(lines[:2])
    rows = lines[2:]
    if len(header) >= max_block_size:
        return _split_plain_block(block, max_block_size)
    row_limit = max_block_size - len(header)
    chunks: list[str] = []
    current = ""
    for row in rows:
        if current and len(current) + len(row) > row_limit:
            chunks.append(header + current)
            current = ""
        if len(row) > row_limit:
            if current:
                chunks.append(header + current)
                current = ""
            chunks.extend(header + piece for piece in _split_plain_block(row, row_limit))
            continue
        current += row
    if current or not chunks:
        chunks.append(header + current)
    return chunks


def _split_plain_block(block: str, max_block_size: int) -> list[str]:
    chunks: list[str] = []
    remaining = block
    while len(remaining) > max_block_size:
        split_at = remaining.rfind(" ", 0, max_block_size + 1)
        newline_at = remaining.rfind("\n", 0, max_block_size + 1)
        split_at = max(split_at, newline_at)
        if split_at <= 0:
            split_at = max_block_size
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks
