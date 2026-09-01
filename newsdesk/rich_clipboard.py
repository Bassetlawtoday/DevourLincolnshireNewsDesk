"""Windows rich clipboard support for complete newsroom copy and source images."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from html import escape
import mimetypes
from pathlib import Path
import sys
import time


def _html_payload(fragment: str) -> bytes:
    body = f"<html><body><!--StartFragment-->{fragment}<!--EndFragment--></body></html>"
    template = (
        "Version:0.9\r\nStartHTML:{start_html:010d}\r\nEndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_fragment:010d}\r\nEndFragment:{end_fragment:010d}\r\n"
    )
    placeholder = template.format(start_html=0, end_html=0, start_fragment=0, end_fragment=0)
    html_bytes = body.encode("utf-8")
    start_html = len(placeholder.encode("ascii"))
    start_fragment = start_html + html_bytes.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
    end_fragment = start_html + html_bytes.index(b"<!--EndFragment-->")
    header = template.format(
        start_html=start_html, end_html=start_html + len(html_bytes),
        start_fragment=start_fragment, end_fragment=end_fragment,
    ).encode("ascii")
    return header + html_bytes + b"\0"


def _set_windows_clipboard(text: str, html: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE

    for _attempt in range(12):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("The Windows clipboard is busy. Try COPY TO CLIPBOARD again.")
    handles = []
    try:
        if not user32.EmptyClipboard():
            raise OSError("The Windows clipboard could not be cleared.")
        formats = (
            (13, (str(text) + "\0").encode("utf-16-le")),  # CF_UNICODETEXT
            (user32.RegisterClipboardFormatW("HTML Format"), _html_payload(html)),
        )
        for clipboard_format, payload in formats:
            handle = kernel32.GlobalAlloc(0x0002, len(payload))  # GMEM_MOVEABLE
            if not handle:
                raise MemoryError("Clipboard memory could not be allocated.")
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise MemoryError("Clipboard memory could not be locked.")
            ctypes.memmove(pointer, payload, len(payload))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(clipboard_format, handle):
                raise OSError("Rich clipboard data could not be stored.")
            handles.append(handle)  # ownership transferred to Windows
    finally:
        user32.CloseClipboard()


def copy_rich_article(
    widget, *, title: str, body: str, image_path: str | Path | None = None,
    caption: str = "", source_url: str = "", source_name: str = "",
) -> None:
    """Copy full text plus an inline image for rich-capable paste targets."""
    title = str(title or "").strip()
    body = str(body or "").strip()
    caption = str(caption or "").strip()
    source_url = str(source_url or "").strip()
    source_name = str(source_name or "").strip()
    plain_parts = [title]
    if caption:
        plain_parts.append(caption)
    if body:
        plain_parts.append(body)
    if source_url:
        plain_parts.append(f"Source: {source_name or source_url}\n{source_url}")
    plain = "\n\n".join(part for part in plain_parts if part)

    parts = [f"<h1>{escape(title)}</h1>"] if title else []
    path = Path(image_path) if image_path else None
    if path and path.is_file():
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        parts.append(f'<p><img src="data:{mime};base64,{encoded}" alt="{escape(caption or title)}"></p>')
    if caption:
        parts.append(f"<p><em>{escape(caption)}</em></p>")
    for paragraph in body.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            parts.append(f"<p>{escape(paragraph).replace(chr(10), '<br>')}</p>")
    if source_url:
        parts.append(f'<p>Source: <a href="{escape(source_url, quote=True)}">{escape(source_name or source_url)}</a></p>')
    rich = "".join(parts)

    if sys.platform == "win32":
        _set_windows_clipboard(plain, rich)
    else:
        widget.clipboard_clear(); widget.clipboard_append(plain); widget.update()


__all__ = ["copy_rich_article"]
