from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from tutor_bot.config import PROJECT_ROOT

TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
THEORY_LIMIT = 4000


def looks_like_html(value: str | None) -> bool:
    return bool(TAG_RE.search(value or ""))


def media_path(raw: str) -> Path:
    src = (raw or "").split("?")[0].replace("\\", "/")
    if src.startswith("/media/"):
        return PROJECT_ROOT / "media" / src[len("/media/") :]
    if src.startswith("media/"):
        return PROJECT_ROOT / src
    path = Path(src)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / src


@dataclass
class Block:
    kind: str
    content: str


def _youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        return parsed.path.strip("/").split("/")[0] or None
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else None
        return parse_qs(parsed.query).get("v", [None])[0]
    return None


def _render_formula(tex: str) -> Path | None:
    tex = (tex or "").strip().strip("$")
    if not tex:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    folder = PROJECT_ROOT / "media" / "formulas"
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(tex.encode("utf-8")).hexdigest()[:16]
    dest = folder / f"{digest}.png"
    if dest.is_file():
        return dest
    try:
        fig = plt.figure(figsize=(7.5, 1.4), dpi=160)
        fig.patch.set_facecolor("white")
        fig.text(0.5, 0.5, f"${tex}$", fontsize=18, ha="center", va="center")
        fig.savefig(dest, bbox_inches="tight", pad_inches=0.18, facecolor="white")
        plt.close(fig)
        return dest if dest.is_file() else None
    except Exception:
        plt.close("all")
        return None


class _HtmlBlocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.buf: list[str] = []
        self.li_index = 0
        self.in_ol = False
        self.in_pre = False
        self.href: str | None = None
        self.in_math = False

    def _flush(self) -> None:
        text = "".join(self.buf).strip()
        self.buf = []
        if text:
            self.blocks.append(Block("text", text))

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        mapping = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "tr"}:
            if self.buf and not "".join(self.buf).endswith("\n"):
                self.buf.append("\n")
            if tag.startswith("h"):
                self.buf.append("<b>")
            return
        if tag == "br":
            self.buf.append("\n")
            return
        if tag == "hr":
            self.buf.append("\n— — —\n")
            return
        if tag in {"b", "strong"}:
            self.buf.append("<b>")
        elif tag in {"i", "em"}:
            self.buf.append("<i>")
        elif tag in {"u", "ins"}:
            self.buf.append("<u>")
        elif tag in {"s", "strike", "del"}:
            self.buf.append("<s>")
        elif tag == "code":
            self.buf.append("<code>")
        elif tag == "pre":
            self.in_pre = True
            self.buf.append("<pre>")
        elif tag == "blockquote":
            self.buf.append("<blockquote>")
        elif tag == "a":
            href = mapping.get("href")
            if href:
                self.href = href
                self.buf.append(f'<a href="{html.escape(href, quote=True)}">')
        elif tag == "ul":
            self.in_ol = False
            self.buf.append("\n")
        elif tag == "ol":
            self.in_ol = True
            self.li_index = 0
            self.buf.append("\n")
        elif tag == "li":
            if self.in_ol:
                self.li_index += 1
                self.buf.append(f"{self.li_index}. ")
            else:
                self.buf.append("• ")
        elif tag == "img":
            self._flush()
            src = mapping.get("src")
            if src:
                self.blocks.append(Block("photo", src))
        elif tag == "video":
            self._flush()
            src = mapping.get("src")
            if src:
                self.blocks.append(Block("video", src))
        elif tag == "source":
            src = mapping.get("src")
            if src:
                self._flush()
                self.blocks.append(Block("video", src))
        elif tag == "iframe":
            self._flush()
            src = mapping.get("src")
            if src:
                video_id = _youtube_id(src)
                url = f"https://youtu.be/{video_id}" if video_id else src
                self.blocks.append(Block("text", html.escape(url)))
        elif tag == "span" and (
            "math" in mapping.get("class", "").split()
            or mapping.get("data-tex")
            or mapping.get("data-formula")
        ):
            self._flush()
            tex = mapping.get("data-tex") or mapping.get("data-formula") or ""
            self.blocks.append(Block("formula", tex))
            self.in_math = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"p", "div", "li", "tr"}:
            self.buf.append("\n")
        elif tag.startswith("h") and len(tag) == 2:
            self.buf.append("</b>\n")
        elif tag in {"b", "strong"}:
            self.buf.append("</b>")
        elif tag in {"i", "em"}:
            self.buf.append("</i>")
        elif tag in {"u", "ins"}:
            self.buf.append("</u>")
        elif tag in {"s", "strike", "del"}:
            self.buf.append("</s>")
        elif tag == "code":
            self.buf.append("</code>")
        elif tag == "pre":
            self.in_pre = False
            self.buf.append("</pre>")
        elif tag == "blockquote":
            self.buf.append("</blockquote>")
        elif tag == "a" and self.href:
            self.buf.append("</a>")
            self.href = None
        elif tag == "span":
            self.in_math = False

    def handle_data(self, data: str) -> None:
        if not data or self.in_math:
            return
        if self.in_pre:
            self.buf.append(html.escape(data, quote=False))
            return
        self.buf.append(html.escape(data, quote=False))


def html_to_blocks(raw: str | None) -> list[Block]:
    text = raw or ""
    if not looks_like_html(text):
        return [Block("text", html.escape(text, quote=False))] if text.strip() else []
    parser = _HtmlBlocks()
    parser.feed(text)
    parser.close()
    parser._flush()
    merged: list[Block] = []
    for block in parser.blocks:
        if (
            merged
            and block.kind == "text"
            and merged[-1].kind == "text"
        ):
            merged[-1].content = f"{merged[-1].content}\n{block.content}".strip()
        elif block.content or block.kind in {"photo", "video"}:
            merged.append(block)
    return merged


def _chunks(text: str, limit: int = THEORY_LIMIT) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    parts = []
    rest = text
    while rest:
        parts.append(rest[:limit])
        rest = rest[limit:]
    return parts


async def send_rich(
    target: Message,
    raw_html: str | None,
    *,
    header: str = "",
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    extra_photo: str | None = None,
) -> list[int]:
    blocks = html_to_blocks(raw_html)
    if extra_photo:
        blocks.insert(0, Block("photo", extra_photo))
    if header:
        if blocks and blocks[0].kind == "text":
            blocks[0].content = f"{header}\n\n{blocks[0].content}"
        else:
            blocks.insert(0, Block("text", header))
    if not blocks:
        sent = await target.bot.send_message(
            target.chat.id, header or "…", reply_markup=reply_markup
        )
        return [sent.message_id]

    ids: list[int] = []
    bot = target.bot
    chat_id = target.chat.id
    last_index = len(blocks) - 1
    for index, block in enumerate(blocks):
        is_last = index == last_index
        markup = reply_markup if is_last else None
        if block.kind == "text":
            pieces = _chunks(block.content)
            if not pieces:
                continue
            for piece_i, piece in enumerate(pieces):
                piece_last = is_last and piece_i == len(pieces) - 1
                sent = await bot.send_message(
                    chat_id, piece, reply_markup=markup if piece_last else None
                )
                ids.append(sent.message_id)
            continue
        if block.kind == "formula":
            path = _render_formula(block.content)
            if path and path.is_file():
                sent = await bot.send_photo(
                    chat_id, FSInputFile(path), reply_markup=markup
                )
            else:
                sent = await bot.send_message(
                    chat_id,
                    f"<code>{html.escape(block.content)}</code>",
                    reply_markup=markup,
                )
            ids.append(sent.message_id)
            continue
        path = media_path(block.content)
        if block.kind == "photo" and path.is_file():
            sent = await bot.send_photo(
                chat_id, FSInputFile(path), reply_markup=markup
            )
            ids.append(sent.message_id)
            continue
        if block.kind == "video" and path.is_file():
            sent = await bot.send_video(
                chat_id, FSInputFile(path), reply_markup=markup
            )
            ids.append(sent.message_id)
            continue
        sent = await bot.send_message(
            chat_id, html.escape(block.content), reply_markup=markup
        )
        ids.append(sent.message_id)
    return ids
