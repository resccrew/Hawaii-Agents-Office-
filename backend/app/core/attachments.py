"""File attachments for chat turns — "attach a file to the chat with an
agent." Saves the raw bytes to disk (durable, and the one thing every
provider can fall back to: a path Claude's own Read tool can open, images
included) and classifies each attachment so callers know how to hand it to
a given provider's API — inline the text, base64 it into a multimodal
content block, or just point at the saved path.

Kept deliberately provider-agnostic: this module only saves and classifies.
Each provider (claude_provider.py, openai_provider.py, ...) decides how to
actually incorporate an AttachmentIn into its own request shape.
"""

from __future__ import annotations

import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

ATTACH_ROOT = Path.home() / "studio-ops" / "chat-uploads"

# Same shape the event pipeline already validates session_id against
# (app/models/events.py's _EventBase.validate_session_id) — dot is
# deliberately excluded, so a segment like ".." can never match. Kept as
# its own constant here (not imported from models/events.py) so this
# module has no dependency on the event-schema layer, just like the
# module docstring's "deliberately provider-agnostic" framing.
_SESSION_ID_RE = re.compile(r"[a-zA-Z0-9_-]{1,128}")


class InvalidSessionId(ValueError):
    """Raised when a session_id can't be trusted to build a filesystem path."""


# Text-ish MIME types get their content inlined directly into the prompt
# (cheap, and works identically for every provider, multimodal or not).
# Above this size they're treated like any other binary attachment — path
# reference only — so one large log file can't blow up every request.
MAX_INLINE_TEXT_BYTES = 64_000

IMAGE_MIME_PREFIXES = ("image/",)
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_EXACT = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/javascript",
    "application/typescript",
}


@dataclass
class AttachmentIn:
    filename: str
    mime_type: str
    data: bytes


@dataclass
class SavedAttachment:
    filename: str
    mime_type: str
    path: Path
    is_image: bool
    is_text: bool
    text_content: str | None  # populated only when is_text and under the inline size cap


def _guess_mime(filename: str, provided: str) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or provided or "application/octet-stream"


def save_attachment(session_id: str, attachment: AttachmentIn) -> SavedAttachment:
    """Persists one attachment under a per-session directory and classifies
    it. Filenames are namespaced with a short random prefix so two uploads
    with the same name in the same session don't collide, and any path
    components in the original filename are stripped (defense against a
    crafted filename like "../../etc/passwd").

    `session_id` is attacker-reachable too (it's a URL path segment on
    `POST /chat/{session_id}/messages`) and was previously used to build
    `dir_` with no validation at all — a session_id of ".." resolves to
    `ATTACH_ROOT/..`, i.e. the studio-ops repo root, one directory above
    where attachments are supposed to live. Validated against the same
    shape the event pipeline already requires of session_id
    (alphanumeric/dash/underscore only — no ".", so ".." can't match), then
    `resolve()`d and re-checked against `ATTACH_ROOT` as defense in depth
    in case that regex is ever loosened without this check being revisited.
    """
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise InvalidSessionId(f"invalid session_id: {session_id!r}")
    mime_type = _guess_mime(attachment.filename, attachment.mime_type)
    safe_name = Path(attachment.filename).name or "file"
    dir_ = (ATTACH_ROOT / session_id).resolve()
    if dir_ != ATTACH_ROOT.resolve() and ATTACH_ROOT.resolve() not in dir_.parents:
        raise InvalidSessionId(f"session_id escapes attachment root: {session_id!r}")
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    path.write_bytes(attachment.data)

    is_image = mime_type.startswith(IMAGE_MIME_PREFIXES)
    is_text = (
        mime_type.startswith(TEXT_MIME_PREFIXES) or mime_type in TEXT_MIME_EXACT
    ) and len(attachment.data) <= MAX_INLINE_TEXT_BYTES

    text_content = None
    if is_text:
        try:
            text_content = attachment.data.decode("utf-8", errors="replace")
        except Exception:
            is_text = False

    return SavedAttachment(
        filename=safe_name,
        mime_type=mime_type,
        path=path,
        is_image=is_image,
        is_text=is_text,
        text_content=text_content,
    )
