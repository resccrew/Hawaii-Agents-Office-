"""Agent + office memory store — the portfolio headline feature: persistent,
human-readable memory that agents read on spawn and write to as they work,
modeled directly on this assistant's own memory system (a MEMORY.md index,
one line per fact, plus one Markdown file per fact with YAML-ish
frontmatter: name / description / type).

Two scopes:
- "office" (OFFICE_SCOPE): state/office-memory/ — shared, project-wide
  memory (a CLAUDE.md-like living doc), not tied to any one agent.
- any agent_id: agent-workspaces/{agent_id}/ — that agent's own memory,
  written directly into its existing workspace directory (alongside
  mcp-config.json and its claude session data), not a subfolder.

Every path built from caller-supplied input (scope, slug) is validated
against a strict pattern AND resolve()+containment-checked before touching
disk — the same defense-in-depth shape as app/core/attachments.py's
session_id fix (a scope or slug of ".." must never be able to escape its
root). Writes are atomic (tempfile + os.replace) and size/count-limited so
one runaway agent can't fill the disk or corrupt a fact mid-write.
"""

from __future__ import annotations

import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

AGENT_WORKSPACES_ROOT = Path.home() / "studio-ops" / "agent-workspaces"
OFFICE_MEMORY_ROOT = Path.home() / "studio-ops" / "state" / "office-memory"
OFFICE_SCOPE = "office"

INDEX_FILENAME = "MEMORY.md"

# Same shape attachments.py's session_id validation already uses for
# agent/session identifiers elsewhere in this codebase.
_SCOPE_RE = re.compile(r"[a-zA-Z0-9_-]{1,128}")
# Facts are filenames (slug.md): lowercase kebab-case, no dots/slashes, so a
# slug can never itself be a path-traversal segment.
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

MAX_FACT_BYTES = 32_000
MAX_FACTS_PER_SCOPE = 500

VALID_TYPES = ("user", "feedback", "project", "reference")


class MemoryError(ValueError):
    """Base for every memory_store validation/not-found error."""


class InvalidScope(MemoryError):
    pass


class InvalidSlug(MemoryError):
    pass


class InvalidType(MemoryError):
    pass


class FactTooLarge(MemoryError):
    pass


class TooManyFacts(MemoryError):
    pass


class FactNotFound(MemoryError):
    pass


@dataclass
class MemoryFact:
    scope: str
    slug: str
    name: str
    description: str
    type: str
    body: str
    updated_at: str  # ISO 8601


@dataclass
class MemoryIndexEntry:
    slug: str
    name: str
    description: str


def _scope_root(scope: str) -> Path:
    """Resolves + validates a scope into its on-disk directory, creating it
    if needed. Raises InvalidScope rather than ever silently falling back to
    some other directory."""
    if scope == OFFICE_SCOPE:
        root = OFFICE_MEMORY_ROOT
    else:
        if not _SCOPE_RE.fullmatch(scope):
            raise InvalidScope(f"invalid scope: {scope!r}")
        candidate = (AGENT_WORKSPACES_ROOT / scope).resolve()
        if candidate.parent != AGENT_WORKSPACES_ROOT.resolve():
            raise InvalidScope(f"scope escapes agent workspaces root: {scope!r}")
        root = candidate
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fact_path(scope_root: Path, slug: str) -> Path:
    if not _SLUG_RE.fullmatch(slug):
        raise InvalidSlug(f"invalid slug: {slug!r}")
    path = (scope_root / f"{slug}.md").resolve()
    if path.parent != scope_root.resolve():
        raise InvalidSlug(f"slug escapes memory root: {slug!r}")
    return path


def _index_path(scope_root: Path) -> Path:
    return scope_root / INDEX_FILENAME


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def _render_fact(name: str, description: str, type_: str, body: str) -> str:
    # Deliberately flat (no nested `metadata:` block) so this can be parsed
    # with a plain key:value scan below instead of pulling in a YAML
    # dependency for three scalar fields.
    frontmatter = "---\n" f"name: {name}\n" f"description: {description}\n" f"type: {type_}\n" "---\n\n"
    return frontmatter + body.strip() + "\n"


def _parse_fact(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw_frontmatter = text[4:end]
    # _render_fact always writes body.strip() + a single trailing "\n" —
    # strip() here mirrors that canonicalization so read_memory() returns
    # exactly what write_memory() was given, not an extra trailing newline.
    body = text[end + 4 :].strip()
    meta: dict[str, str] = {}
    for line in raw_frontmatter.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body


_INDEX_LINE_RE = re.compile(r"^-\s*\[(?P<name>[^\]]*)\]\((?P<slug>[a-z0-9][a-z0-9_-]{0,63})\.md\)\s*(?:—|-)\s*(?P<description>.*)$")


def _read_index_entries(scope_root: Path) -> list[MemoryIndexEntry]:
    path = _index_path(scope_root)
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _INDEX_LINE_RE.match(line.strip())
        if m:
            entries.append(MemoryIndexEntry(slug=m["slug"], name=m["name"], description=m["description"]))
    return entries


def _write_index_entries(scope_root: Path, entries: list[MemoryIndexEntry]) -> None:
    header = "# Memory Index\n\n"
    lines = [f"- [{e.name}]({e.slug}.md) — {e.description}" for e in entries]
    _atomic_write(_index_path(scope_root), header + "\n".join(lines) + ("\n" if lines else ""))


def _upsert_index(scope_root: Path, *, slug: str, name: str, description: str) -> None:
    entries = _read_index_entries(scope_root)
    new_entry = MemoryIndexEntry(slug=slug, name=name, description=description)
    for i, e in enumerate(entries):
        if e.slug == slug:
            entries[i] = new_entry
            break
    else:
        entries.append(new_entry)
    _write_index_entries(scope_root, entries)


def _remove_from_index(scope_root: Path, slug: str) -> None:
    entries = [e for e in _read_index_entries(scope_root) if e.slug != slug]
    _write_index_entries(scope_root, entries)


def list_memory(scope: str) -> list[MemoryIndexEntry]:
    """The MEMORY.md index for a scope — what an agent should read first,
    before opening any individual fact."""
    return _read_index_entries(_scope_root(scope))


def read_memory(scope: str, slug: str) -> MemoryFact:
    root = _scope_root(scope)
    path = _fact_path(root, slug)
    if not path.is_file():
        raise FactNotFound(f"no such memory fact: {scope}/{slug}")
    meta, body = _parse_fact(path.read_text(encoding="utf-8"))
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    return MemoryFact(
        scope=scope,
        slug=slug,
        name=meta.get("name", slug),
        description=meta.get("description", ""),
        type=meta.get("type", "project"),
        body=body,
        updated_at=updated_at,
    )


def write_memory(scope: str, slug: str, *, name: str, description: str, type: str, body: str) -> MemoryFact:
    """Creates or overwrites one fact file, then upserts its MEMORY.md index
    line. Both writes are atomic individually; a crash between the two
    leaves the fact file itself intact (the index is rebuildable from the
    fact files' own frontmatter if it were ever needed, though nothing here
    does that automatically today)."""
    if type not in VALID_TYPES:
        raise InvalidType(f"invalid type: {type!r} (must be one of {VALID_TYPES})")
    root = _scope_root(scope)
    path = _fact_path(root, slug)
    content = _render_fact(name, description, type, body)
    if len(content.encode("utf-8")) > MAX_FACT_BYTES:
        raise FactTooLarge(f"fact body too large (max {MAX_FACT_BYTES} bytes)")
    if not path.exists():
        existing_count = len(_read_index_entries(root))
        if existing_count >= MAX_FACTS_PER_SCOPE:
            raise TooManyFacts(f"scope {scope!r} already has {MAX_FACTS_PER_SCOPE} facts, the max")
    _atomic_write(path, content)
    _upsert_index(root, slug=slug, name=name, description=description)
    return read_memory(scope, slug)


def delete_memory(scope: str, slug: str) -> None:
    root = _scope_root(scope)
    path = _fact_path(root, slug)
    if not path.is_file():
        raise FactNotFound(f"no such memory fact: {scope}/{slug}")
    path.unlink()
    _remove_from_index(root, slug)
