"""Shared helper: fold text-attachment content into a message string. Every
provider does this identically (inlining text is provider-agnostic — it's
just more prompt), so it lives here once instead of copy-pasted four times.
Image handling, by contrast, genuinely differs per provider's API shape and
stays in each provider's own module."""

from __future__ import annotations

from app.core.attachments import SavedAttachment


def augment_with_text_attachments(message: str, attachments: list[SavedAttachment] | None) -> str:
    if not attachments:
        return message
    blocks = [
        f"\n\n--- attached file: {a.filename} ---\n{a.text_content}\n--- end {a.filename} ---"
        for a in attachments
        if a.is_text and a.text_content is not None
    ]
    return message + "".join(blocks)


def image_attachments(attachments: list[SavedAttachment] | None) -> list[SavedAttachment]:
    return [a for a in (attachments or []) if a.is_image]


def other_attachments(attachments: list[SavedAttachment] | None) -> list[SavedAttachment]:
    """Binary/non-text/non-image files (PDFs, archives, ...) — no provider
    can meaningfully embed these inline, so callers just note they exist."""
    return [a for a in (attachments or []) if not a.is_text and not a.is_image]
