"""Unit tests for the session_id validation added to save_attachment() —
see the docstring in app/core/attachments.py for the path-traversal finding
this closes (session_id="..' previously escaped ATTACH_ROOT entirely)."""

from __future__ import annotations

import pytest

from app.core.attachments import ATTACH_ROOT, AttachmentIn, InvalidSessionId, save_attachment


def _attachment(name: str = "note.txt") -> AttachmentIn:
    return AttachmentIn(filename=name, mime_type="text/plain", data=b"hello")


@pytest.mark.parametrize(
    "session_id",
    [
        "..",
        "../../etc",
        "../..",
        "a/../../b",
        "",
        "has space",
        "semi;colon",
        "a" * 129,  # one over the event pipeline's own 128-char cap
    ],
)
def test_rejects_traversal_and_invalid_session_ids(session_id: str) -> None:
    with pytest.raises(InvalidSessionId):
        save_attachment(session_id, _attachment())


def test_accepts_a_normal_session_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.core.attachments.ATTACH_ROOT", tmp_path)
    saved = save_attachment("fixture-session-001", _attachment())
    assert saved.path.is_file()
    assert saved.path.is_relative_to(tmp_path)


def test_saved_file_never_lands_outside_attach_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.core.attachments.ATTACH_ROOT", tmp_path)
    saved = save_attachment("abc-123_ok", _attachment())
    assert saved.path.is_relative_to(ATTACH_ROOT.__class__(tmp_path))
