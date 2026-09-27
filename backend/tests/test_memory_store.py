"""Unit tests for app/core/memory_store.py — path safety (traversal via
scope/slug), atomicity, size/count limits, and the list/read/write/delete
round trip for both the office scope and an agent scope.

Every test monkeypatches AGENT_WORKSPACES_ROOT/OFFICE_MEMORY_ROOT to a
tmp_path so nothing here ever touches the real ~/studio-ops/state or
~/studio-ops/agent-workspaces."""

from __future__ import annotations

import pytest

from app.core import memory_store as ms


@pytest.fixture(autouse=True)
def _isolated_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "AGENT_WORKSPACES_ROOT", tmp_path / "agent-workspaces")
    monkeypatch.setattr(ms, "OFFICE_MEMORY_ROOT", tmp_path / "state" / "office-memory")
    yield


def test_write_then_read_round_trips(tmp_path) -> None:
    fact = ms.write_memory(
        ms.OFFICE_SCOPE, "trading-style", name="Trading Style", description="user prefers X", type="user", body="Body text."
    )
    assert fact.slug == "trading-style"
    assert fact.name == "Trading Style"
    assert fact.type == "user"

    got = ms.read_memory(ms.OFFICE_SCOPE, "trading-style")
    assert got.body == "Body text."
    assert got.description == "user prefers X"


def test_write_upserts_index_and_list_reflects_it() -> None:
    ms.write_memory(ms.OFFICE_SCOPE, "a", name="A", description="first", type="project", body="a")
    ms.write_memory(ms.OFFICE_SCOPE, "b", name="B", description="second", type="reference", body="b")

    index = ms.list_memory(ms.OFFICE_SCOPE)
    slugs = {e.slug for e in index}
    assert slugs == {"a", "b"}

    # Overwrite "a" with a new description — index line updates in place,
    # doesn't duplicate.
    ms.write_memory(ms.OFFICE_SCOPE, "a", name="A", description="updated", type="project", body="a2")
    index = ms.list_memory(ms.OFFICE_SCOPE)
    assert len(index) == 2
    a_entry = next(e for e in index if e.slug == "a")
    assert a_entry.description == "updated"


def test_delete_removes_fact_and_index_entry() -> None:
    ms.write_memory(ms.OFFICE_SCOPE, "temp", name="Temp", description="d", type="project", body="x")
    assert len(ms.list_memory(ms.OFFICE_SCOPE)) == 1

    ms.delete_memory(ms.OFFICE_SCOPE, "temp")
    assert ms.list_memory(ms.OFFICE_SCOPE) == []
    with pytest.raises(ms.FactNotFound):
        ms.read_memory(ms.OFFICE_SCOPE, "temp")


def test_delete_missing_fact_raises_not_found() -> None:
    with pytest.raises(ms.FactNotFound):
        ms.delete_memory(ms.OFFICE_SCOPE, "nope")


def test_agent_scope_is_isolated_from_office_scope() -> None:
    ms.write_memory("agent-abc123", "note", name="Note", description="d", type="project", body="agent body")
    ms.write_memory(ms.OFFICE_SCOPE, "note", name="Note", description="d", type="project", body="office body")

    agent_fact = ms.read_memory("agent-abc123", "note")
    office_fact = ms.read_memory(ms.OFFICE_SCOPE, "note")
    assert agent_fact.body == "agent body"
    assert office_fact.body == "office body"


@pytest.mark.parametrize("slug", ["..", "../../etc", "a/b", "", ".hidden", "UPPER", "a" * 100])
def test_rejects_invalid_slugs(slug: str) -> None:
    with pytest.raises(ms.InvalidSlug):
        ms.write_memory(ms.OFFICE_SCOPE, slug, name="x", description="x", type="project", body="x")


@pytest.mark.parametrize("scope", ["..", "../../etc", "a/b", "", "a" * 200])
def test_rejects_invalid_agent_scopes(scope: str) -> None:
    with pytest.raises(ms.InvalidScope):
        ms.write_memory(scope, "fact", name="x", description="x", type="project", body="x")


def test_write_never_escapes_agent_workspaces_root(tmp_path) -> None:
    with pytest.raises(ms.InvalidScope):
        ms.write_memory("..", "fact", name="x", description="x", type="project", body="x")
    # Nothing should have been created one level up from the workspaces root.
    assert not (tmp_path / "fact.md").exists()


def test_rejects_invalid_type() -> None:
    with pytest.raises(ms.InvalidType):
        ms.write_memory(ms.OFFICE_SCOPE, "bad-type", name="x", description="x", type="not-a-type", body="x")


def test_rejects_oversized_fact() -> None:
    huge = "x" * (ms.MAX_FACT_BYTES + 1)
    with pytest.raises(ms.FactTooLarge):
        ms.write_memory(ms.OFFICE_SCOPE, "huge", name="x", description="x", type="project", body=huge)


def test_rejects_new_fact_past_the_per_scope_cap(monkeypatch) -> None:
    monkeypatch.setattr(ms, "MAX_FACTS_PER_SCOPE", 2)
    ms.write_memory(ms.OFFICE_SCOPE, "a", name="a", description="d", type="project", body="x")
    ms.write_memory(ms.OFFICE_SCOPE, "b", name="b", description="d", type="project", body="x")
    with pytest.raises(ms.TooManyFacts):
        ms.write_memory(ms.OFFICE_SCOPE, "c", name="c", description="d", type="project", body="x")
    # Overwriting an EXISTING fact must still be allowed once at the cap.
    ms.write_memory(ms.OFFICE_SCOPE, "a", name="a", description="d2", type="project", body="x2")
    assert ms.read_memory(ms.OFFICE_SCOPE, "a").description == "d2"


def test_write_is_atomic_no_tmp_file_left_behind() -> None:
    fact = ms.write_memory(ms.OFFICE_SCOPE, "atomic", name="x", description="d", type="project", body="x")
    root = fact.scope
    scope_root = ms._scope_root(root)
    leftovers = [p for p in scope_root.iterdir() if p.name.startswith(".") and p.name.endswith(".tmp")]
    assert leftovers == []


def test_read_missing_fact_raises_not_found() -> None:
    with pytest.raises(ms.FactNotFound):
        ms.read_memory(ms.OFFICE_SCOPE, "does-not-exist")


def test_fact_file_is_readable_plain_markdown(tmp_path) -> None:
    ms.write_memory(ms.OFFICE_SCOPE, "plain", name="Plain", description="d", type="reference", body="Hello.")
    scope_root = ms._scope_root(ms.OFFICE_SCOPE)
    raw = (scope_root / "plain.md").read_text()
    assert raw.startswith("---\n")
    assert "name: Plain" in raw
    assert "type: reference" in raw
    assert raw.strip().endswith("Hello.")


def test_write_sanitizes_name_with_newline_and_bracket() -> None:
    """A name containing a raw newline and "]" must not corrupt the
    MEMORY.md index line format (`- [name](slug.md) — description`) —
    newlines/tabs collapse to spaces and structurally significant
    characters are stripped before the index line is written."""
    ms.write_memory(
        ms.OFFICE_SCOPE,
        "weird-name",
        name="Bad]Name\nSecond Line",
        description="desc\twith\ttabs",
        type="project",
        body="body",
    )

    index = ms.list_memory(ms.OFFICE_SCOPE)
    assert len(index) == 1
    entry = index[0]
    assert entry.slug == "weird-name"
    assert "\n" not in entry.name
    assert "]" not in entry.name
    assert "\t" not in entry.description

    # Round-trips cleanly: the index file itself stays one line per fact.
    scope_root = ms._scope_root(ms.OFFICE_SCOPE)
    index_text = (scope_root / ms.INDEX_FILENAME).read_text()
    lines = [line for line in index_text.splitlines() if line.startswith("- [")]
    assert len(lines) == 1


def test_concurrent_writes_all_land_in_index() -> None:
    """20 threads each writing a distinct fact into the same scope must
    all end up represented in MEMORY.md — without the flock-guarded
    read-modify-write, two threads reading the same index before either
    writes back would race and one write clobbers the other's line."""
    import threading

    barrier = threading.Barrier(20)

    def _write(i: int) -> None:
        barrier.wait()
        ms.write_memory(
            ms.OFFICE_SCOPE,
            f"fact-{i}",
            name=f"Fact {i}",
            description="concurrent write",
            type="project",
            body=f"body {i}",
        )

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    index = ms.list_memory(ms.OFFICE_SCOPE)
    assert sorted(e.slug for e in index) == sorted(f"fact-{i}" for i in range(20))
